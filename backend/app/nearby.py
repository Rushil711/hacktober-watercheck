"""Feature 1 search candidates and Feature 2 "search nearby" (water bodies inside a radius)."""

from __future__ import annotations

import asyncio

from . import config as C
from .cache import OfflineMiss
from .models import Candidate, NearbyResult, SearchResult, Spot, WaterBody
from .net import haversine_km
from .providers import advisories, erddap, places, water
from .scoring import c_to_f, chl_level, compute_halo

COASTAL_KINDS = ("beach", "bay")  # the kinds the ocean report and halos cover


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


async def nearby(origin: Spot, radius_km: float) -> NearbyResult:
    bodies, warnings = await water.water_bodies(origin.lat, origin.lon, radius_km)
    bodies = bodies[: C.MAX_NEARBY_SPOTS]
    coastal = [b for b in bodies if b["kind"] in COASTAL_KINDS]
    chl_grid = sst_grid = None
    snapshot: dict = {}
    if coastal:
        lats = [b["lat"] for b in coastal]
        lons = [b["lon"] for b in coastal]
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

    out: list[WaterBody] = []
    for b in bodies:
        body = WaterBody(**b)
        if b["kind"] in COASTAL_KINDS:
            # Ocean grids only: a lake or river near the coast would pick up ocean cells.
            chl, chl_age = _sample(chl_grid, b["lat"], b["lon"])
            sst_c, _ = _sample(sst_grid, b["lat"], b["lon"])
            status = advisories.quick_status(snapshot, b["lat"], b["lon"]) if snapshot else "unverified"
            body.report_available = True
            body.official_status = status
            stale = chl_age is not None and chl_age > C.CHL_STALE_DAYS
            body.halo = compute_halo(status, chl_level(chl), stale, sst_c is not None)
            body.sea_temp_f = None if sst_c is None else round(c_to_f(sst_c), 1)
            body.chl = None if chl is None else round(chl, 2)
        out.append(body)
    return NearbyResult(origin=origin, radius_km=round(radius_km, 3), spots=out, warnings=warnings)
