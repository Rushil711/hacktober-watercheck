"""Feature 1 search candidates and Feature 2 "water near me"."""

from __future__ import annotations

import asyncio

from . import config as C
from .cache import OfflineMiss
from .models import Candidate, NearbyResult, NearbySpot, SearchResult, Spot
from .net import haversine_km
from .providers import advisories, erddap, places
from .scoring import c_to_f, chl_level, compute_halo


async def search(query: str) -> SearchResult:
    warnings: list[str] = []
    results = await places.geocode(query)
    if not results:
        return SearchResult(query=query, place=None, candidates=[], warnings=["No place found for that search."])
    top = results[0]
    place = Candidate(
        name=top["display_name"][:120],
        lat=top["lat"],
        lon=top["lon"],
        kind=top.get("type") or "place",
        distance_km=0.0,
        source="Nominatim",
    )
    candidates: list[Candidate] = []
    if top.get("category") == "natural" and top.get("type") in ("beach", "cliff", "bay", "water"):
        candidates.append(
            Candidate(name=top["name"], lat=top["lat"], lon=top["lon"], kind=top["type"], distance_km=0.0, source="Nominatim")
        )
    try:
        spots = await places.water_spots(top["lat"], top["lon"], C.SEARCH_RADIUS_KM)
        for s in spots:
            if any(c.name == s["name"] and haversine_km(c.lat, c.lon, s["lat"], s["lon"]) < 0.5 for c in candidates):
                continue
            candidates.append(
                Candidate(
                    name=s["name"],
                    lat=s["lat"],
                    lon=s["lon"],
                    kind=s["kind"],
                    distance_km=s["distance_km"],
                    source="OpenStreetMap",
                )
            )
    except Exception as exc:  # noqa: BLE001
        reason = "not in the offline cache" if isinstance(exc, OfflineMiss) else type(exc).__name__
        warnings.append(f"Beach discovery unavailable ({reason}).")
    return SearchResult(query=query, place=place, candidates=candidates[:12], warnings=warnings)


def _sample(grid: erddap.Grid | None, lat: float, lon: float) -> tuple[float | None, float | None]:
    """(latest value, age in days) for one spot from a regional grid."""
    if grid is None:
        return None, None
    days = erddap.daily_means(erddap.cells_in_box(grid, lat, lon, C.OFFSHORE_BOX_KM))
    latest = erddap.latest_valid(days)
    if latest is None:
        return None, None
    return latest.mean, erddap.age_days(latest.time)


async def nearby(lat: float, lon: float, drive_min: int) -> NearbyResult:
    warnings: list[str] = []
    radius_km = drive_min * C.MAX_KM_PER_MIN
    origin = Spot(name="Search center", lat=lat, lon=lon, kind="origin")
    try:
        spots = await places.water_spots(lat, lon, radius_km)
    except Exception as exc:  # noqa: BLE001
        reason = "not in the offline cache" if isinstance(exc, OfflineMiss) else type(exc).__name__
        return NearbyResult(
            origin=origin, drive_min=drive_min, ring_km=radius_km, spots=[], warnings=[f"Beach discovery unavailable ({reason})."]
        )
    spots = spots[: C.MAX_NEARBY_SPOTS * 2]
    durations, method = await places.drive_minutes((lat, lon), [(s["lat"], s["lon"]) for s in spots])
    if method == "straight-line":
        warnings.append("OSRM drive times unavailable; using a straight-line estimate.")
    in_range = [(s, d) for s, d in zip(spots, durations, strict=True) if d is not None and d <= drive_min]
    in_range = in_range[: C.MAX_NEARBY_SPOTS]
    if not in_range:
        return NearbyResult(origin=origin, drive_min=drive_min, ring_km=radius_km, spots=[], warnings=warnings)

    lats = [s["lat"] for s, _ in in_range]
    lons = [s["lon"] for s, _ in in_range]
    pad = 0.08

    async def grid(ds: C.GridDataset, days: int):
        return await erddap.fetch_grid(ds, min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad, days)

    chl_grid, sst_grid, snapshot = await asyncio.gather(
        grid(C.CHL_DATASET, C.TREND_DAYS), grid(C.SST_DATASET, 2), advisories.status_lookup_bulk(), return_exceptions=True
    )
    if isinstance(chl_grid, Exception):
        warnings.append("Chlorophyll unavailable for the map.")
        chl_grid = None
    if isinstance(sst_grid, Exception):
        warnings.append("Sea temperature unavailable for the map.")
        sst_grid = None
    if isinstance(snapshot, Exception) or not snapshot:
        warnings.append("County beach status unavailable; halos treat official status as unverified.")
        snapshot = {}

    out: list[NearbySpot] = []
    for s, d in in_range:
        chl, chl_age = _sample(chl_grid, s["lat"], s["lon"])
        sst_c, _ = _sample(sst_grid, s["lat"], s["lon"])
        if s["kind"] == "cliff" and sst_grid is not None and sst_c is None:
            continue  # inland cliff: no ocean cell nearby
        status = advisories.quick_status(snapshot, s["lat"], s["lon"]) if snapshot else "unverified"
        level = chl_level(chl)
        halo = compute_halo(status, level, chl_age is not None and chl_age > C.CHL_STALE_DAYS, sst_c is not None)
        out.append(
            NearbySpot(
                name=s["name"],
                lat=s["lat"],
                lon=s["lon"],
                kind=s["kind"],
                drive_min=d,
                drive_method=method,
                halo=halo,
                official_status=status,
                sea_temp_f=None if sst_c is None else round(c_to_f(sst_c), 1),
                chl=None if chl is None else round(chl, 2),
            )
        )
    out.sort(key=lambda x: x.drive_min)
    return NearbyResult(origin=origin, drive_min=drive_min, ring_km=radius_km, spots=out, warnings=warnings)
