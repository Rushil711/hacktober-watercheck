"""Assemble a beach report from independent providers (partial results allowed)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from . import config as C
from .cache import OfflineMiss, is_offline, now_iso
from .models import (
    BeachReport,
    BestTime,
    ChlorophyllBlock,
    Imagery,
    Measurement,
    OfficialStatus,
    Receipt,
    SeaTempBlock,
    Spot,
    Station,
)
from .providers import advisories, erddap, gibs
from .providers import tides_weather as tw
from .scoring import (
    best_time,
    chlorophyll_block,
    compute_feel,
    compute_halo,
    data_age_summary,
    sea_temp_block,
    tide_now,
)


def _why(exc: Exception) -> str:
    if isinstance(exc, OfflineMiss):
        return "not in the offline cache"
    if isinstance(exc, erddap.MetadataError):
        return f"metadata check failed: {exc}"
    return type(exc).__name__


def grid_receipt(grid: erddap.Grid | None, ds: C.GridDataset) -> Receipt:
    return Receipt(
        source="NOAA CoastWatch ERDDAP",
        dataset=f"{ds.dataset_id} ({ds.variable})",
        fetched_at=grid.fetched_at if grid else None,
        url=grid.url.replace(".json?", ".htmlTable?") if grid else erddap.dataset_page(ds),
        cached=grid.cached if grid else False,
    )


async def satellite_blocks(spot: Spot, warnings: list[str]) -> tuple[ChlorophyllBlock, SeaTempBlock]:
    async def chl():
        meta = await erddap.get_metadata(C.CHL_DATASET)
        b = erddap.box_bounds(spot.lat, spot.lon, C.OFFSHORE_BOX_KM, meta.lat_res)
        return await erddap.fetch_grid(C.CHL_DATASET, *b, days=C.CHL_LOOKBACK_DAYS)

    async def sst():
        meta = await erddap.get_metadata(C.SST_DATASET)
        b = erddap.box_bounds(spot.lat, spot.lon, C.OFFSHORE_BOX_KM, meta.lat_res)
        return await erddap.fetch_grid(C.SST_DATASET, *b, days=3)

    chl_grid, sst_grid = await asyncio.gather(chl(), sst(), return_exceptions=True)
    if isinstance(chl_grid, Exception):
        warnings.append(f"Chlorophyll unavailable ({_why(chl_grid)}).")
        chl_block = ChlorophyllBlock(
            current=Measurement(label="Chlorophyll-a", unit="mg/m³", receipt=grid_receipt(None, C.CHL_DATASET))
        )
    else:
        days = erddap.daily_means(erddap.cells_in_box(chl_grid, spot.lat, spot.lon, C.OFFSHORE_BOX_KM))
        chl_block = chlorophyll_block(days, grid_receipt(chl_grid, C.CHL_DATASET), chl_grid.meta.time_end)
    if isinstance(sst_grid, Exception):
        warnings.append(f"Sea temperature unavailable ({_why(sst_grid)}).")
        sst_blk = SeaTempBlock(
            current=Measurement(label="Sea surface temperature", unit="°F", receipt=grid_receipt(None, C.SST_DATASET))
        )
    else:
        days = erddap.daily_means(erddap.cells_in_box(sst_grid, spot.lat, spot.lon, C.OFFSHORE_BOX_KM))
        sst_blk = sea_temp_block(days, grid_receipt(sst_grid, C.SST_DATASET))
    if chl_block.stale:
        warnings.append(f"Latest cloud-free chlorophyll is {chl_block.age_days:.0f} days old.")
    if sst_blk.stale:
        warnings.append(f"Latest sea temperature is {sst_blk.age_days:.0f} days old.")
    return chl_block, sst_blk


async def tide_and_weather(spot: Spot, warnings: list[str]) -> tuple[BestTime, list[dict]]:
    tides: list[dict] = []
    periods: list[dict] = []
    tz_name = None
    station = None
    tide_receipt = weather_receipt = None
    try:
        wx = await tw.nws_hourly(spot.lat, spot.lon)
        periods, tz_name = wx.data["periods"], wx.data["time_zone"]
        weather_receipt = Receipt(
            source="National Weather Service",
            dataset="Hourly forecast (api.weather.gov)",
            observed_at=wx.data.get("updated"),
            fetched_at=wx.fetched_at,
            url=f"https://forecast.weather.gov/MapClick.php?lat={spot.lat:.4f}&lon={spot.lon:.4f}",
            cached=wx.cached,
            note="Forecast, not an observation. Daylight uses the NWS day/night flag.",
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Air temperature forecast unavailable ({_why(exc)}).")
    tz = ZoneInfo(tz_name or C.DEFAULT_TIMEZONE)
    try:
        stations = await tw.tide_stations()
        picked, dist = tw.pick_station(stations.data, spot.lat, spot.lon)
        if picked is None:
            raise LookupError("no tide station nearby")
        station = Station(id=picked["id"], name=picked["name"], distance_km=round(dist, 1))
        start = datetime.now(UTC).astimezone(tz)
        pred = await tw.tide_predictions(picked["id"], start)
        tides = pred.data
        tide_receipt = Receipt(
            source="NOAA CO-OPS Tides & Currents",
            dataset=f"Hourly tide predictions, station {picked['id']} (MLLW, feet)",
            observed_at=None,
            fetched_at=pred.fetched_at,
            url=tw.station_page(picked["id"]),
            cached=pred.cached,
            note=f"Predictions for {picked['name']}, {dist:.1f} km away.",
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Tide predictions unavailable ({_why(exc)}).")
    bt = best_time(tides, periods, tz_name)
    bt.tide_station = station
    bt.tide_receipt = tide_receipt
    bt.weather_receipt = weather_receipt
    return bt, tides


async def imagery_block(spot: Spot, warnings: list[str]) -> Imagery:
    try:
        return await gibs.imagery_for(spot.lat, spot.lon)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Satellite photo unavailable ({_why(exc)}).")
        return Imagery(layer=C.GIBS_LAYER, max_zoom=C.GIBS_MAX_ZOOM, receipt=Receipt(source="NASA GIBS (Worldview)"))


async def official_block(spot: Spot, warnings: list[str]) -> OfficialStatus:
    status, extra = await advisories.official_status(spot.lat, spot.lon)
    warnings.extend(extra)
    return status


async def build_report(spot: Spot) -> BeachReport:
    warnings: list[str] = []
    (chl, sst), (bt, tides), imagery, official = await asyncio.gather(
        satellite_blocks(spot, warnings),
        tide_and_weather(spot, warnings),
        imagery_block(spot, warnings),
        official_block(spot, warnings),
    )
    day_tides = [h.tide_ft for h in bt.hours if h.tide_ft is not None]
    feel = compute_feel(sst, official, tide_now(tides), day_tides)
    halo = compute_halo(official.status, chl.level, chl.stale, sst.current.value is not None)
    return BeachReport(
        spot=spot,
        generated_at=now_iso(),
        offline=is_offline(),
        chlorophyll=chl,
        sea_temp=sst,
        official=official,
        imagery=imagery,
        best_time=bt,
        feel=feel,
        halo=halo,
        data_age=data_age_summary(("chlorophyll", chl.age_days), ("sea temperature", sst.age_days)),
        warnings=warnings,
    )
