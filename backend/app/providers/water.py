"""Named water bodies inside a circle, with outlines for the map (Feature 2).

Two sources, merged by name and kind:
- Nominatim (OpenStreetMap): beaches, bays, and rivers. A category search finds them,
  then /lookup returns their outlines. Public Overpass was at capacity on 2026-10-25.
- USGS National Hydrography Dataset (NHD), waterbody layer: lakes, reservoirs, and
  estuaries. US only. Nominatim category search does not find lakes.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from typing import Any

from ..cache import OfflineMiss, cached_call
from ..config import MI_TO_KM, NOMINATIM_LIMIT, SHAPE_TOLERANCE_DEG, TTL_PLACES
from ..net import get_json, haversine_km, km_to_deg_lat, km_to_deg_lon
from .places import NOMINATIM, NOMINATIM_BASE, nominatim_get

NOMINATIM_LOOKUP = f"{NOMINATIM_BASE}/lookup"
NHD_WATERBODY = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/12/query"
LOOKUP_BATCH = 50
NHD_MAX_RECORDS = 300
NHD_SOURCE = "USGS NHD"
OSM_SOURCE = "OpenStreetMap"

# Nominatim category phrase -> the OSM (category, type) a result must have. The phrase is also our kind.
OSM_PHRASES: dict[str, tuple[str, str]] = {
    "beach": ("natural", "beach"),
    "bay": ("natural", "bay"),
    "river": ("waterway", "river"),
}
PLURAL = {"beach": "beaches", "bay": "bays", "river": "rivers"}
# NHD FTYPE -> our kind. 466 is swamp/marsh: kept only when the name says "lagoon".
NHD_KINDS = {390: "lake", 436: "reservoir", 493: "estuary"}
NHD_MARSH = 466


def viewbox(lat: float, lon: float, radius_km: float) -> str:
    """Nominatim viewbox (the square around the circle)."""
    dlat, dlon = km_to_deg_lat(radius_km), km_to_deg_lon(radius_km, lat)
    return f"{lon - dlon:.4f},{lat + dlat:.4f},{lon + dlon:.4f},{lat - dlat:.4f}"


def _round_coords(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 5)
    if isinstance(value, list):
        return [_round_coords(v) for v in value]
    if isinstance(value, dict):
        return {k: _round_coords(v) for k, v in value.items()}
    return value


def positions(geom: dict) -> Iterator[tuple[float, float]]:
    """Every (lat, lon) vertex of a GeoJSON geometry."""
    if geom["type"] == "GeometryCollection":
        for g in geom["geometries"]:
            yield from positions(g)
        return

    def walk(coords: list) -> Iterator[tuple[float, float]]:
        if coords and isinstance(coords[0], int | float):
            yield coords[1], coords[0]
        else:
            for c in coords:
                yield from walk(c)

    yield from walk(geom["coordinates"])


def min_distance_km(lat: float, lon: float, geom: dict) -> float:
    return min(haversine_km(lat, lon, la, lo) for la, lo in positions(geom))


def parse_nominatim(rows: list[dict], phrase: str) -> list[dict]:
    category, osm_type = OSM_PHRASES[phrase]
    out = []
    for r in rows:
        if r.get("category") != category or r.get("type") != osm_type or not r.get("name"):
            continue
        out.append(
            {
                "name": r["name"],
                "kind": phrase,
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "osm_id": f"{r['osm_type'][0].upper()}{r['osm_id']}",
                "geometry": None,
                "source": OSM_SOURCE,
            }
        )
    return out


def parse_nhd(payload: dict) -> list[dict]:
    out = []
    for f in payload.get("features", []):
        props = {k.lower(): v for k, v in (f.get("properties") or {}).items()}
        name, ftype, geom = props.get("gnis_name"), props.get("ftype"), f.get("geometry")
        if not name or not geom:
            continue
        kind = NHD_KINDS.get(ftype)
        if kind is None and ftype == NHD_MARSH and "lagoon" in name.lower():
            kind = "lagoon"
        if kind is None:
            continue
        pts = list(positions(geom))
        lats, lons = [p[0] for p in pts], [p[1] for p in pts]
        out.append(
            {
                "name": name,
                "kind": kind,
                "lat": round((min(lats) + max(lats)) / 2, 5),
                "lon": round((min(lons) + max(lons)) / 2, 5),
                "geometry": _round_coords(geom),
                "source": NHD_SOURCE,
            }
        )
    return out


def merge(features: list[dict], lat: float, lon: float, radius_km: float) -> list[dict]:
    """One entry per (name, kind), nearest first. Drops OSM results in the square's corners."""
    groups: dict[tuple[str, str], dict] = {}
    for f in features:
        geom = f["geometry"] or {"type": "Point", "coordinates": [f["lon"], f["lat"]]}
        dist = min_distance_km(lat, lon, geom)
        # NHD already filtered by distance to the outline, which can pass between two vertices.
        if f["source"] != NHD_SOURCE and dist > radius_km:
            continue
        key = (re.sub(r"[^a-z0-9]", "", f["name"].lower()), f["kind"])
        group = groups.get(key)
        if group is None:
            groups[key] = {
                "id": f"{f['kind']}-{key[0]}",
                "name": f["name"],
                "kind": f["kind"],
                "lat": f["lat"],
                "lon": f["lon"],
                "distance_km": dist,
                "source": f["source"],
                "parts": [geom],
            }
            continue
        group["parts"].append(geom)
        if dist < group["distance_km"]:
            group.update(lat=f["lat"], lon=f["lon"], distance_km=dist)

    out = []
    for group in groups.values():
        parts = group.pop("parts")
        shapes = [p for p in parts if p["type"] != "Point"] or parts[:1]
        group["geometry"] = shapes[0] if len(shapes) == 1 else {"type": "GeometryCollection", "geometries": shapes}
        group["distance_km"] = round(group["distance_km"], 2)
        out.append(group)
    return sorted(out, key=lambda g: g["distance_km"])


async def _osm_search(phrase: str, box: str) -> list[dict]:
    params = {"q": phrase, "viewbox": box, "bounded": 1, "format": "jsonv2", "limit": NOMINATIM_LIMIT}

    async def fetch() -> list[dict]:
        return await nominatim_get(NOMINATIM, params)

    result = await cached_call("nominatim_area", (phrase, box), TTL_PLACES, fetch, NOMINATIM)
    return result.data


async def _osm_outlines(osm_ids: list[str]) -> dict[str, dict]:
    shapes: dict[str, dict] = {}
    for i in range(0, len(osm_ids), LOOKUP_BATCH):
        batch = ",".join(osm_ids[i : i + LOOKUP_BATCH])
        params = {"osm_ids": batch, "format": "jsonv2", "polygon_geojson": 1, "polygon_threshold": SHAPE_TOLERANCE_DEG}

        async def fetch(params: dict = params) -> list[dict]:
            return await nominatim_get(NOMINATIM_LOOKUP, params)

        result = await cached_call("nominatim_lookup", (batch, SHAPE_TOLERANCE_DEG), TTL_PLACES, fetch, NOMINATIM_LOOKUP)
        for r in result.data:
            if r.get("geojson"):
                shapes[f"{r['osm_type'][0].upper()}{r['osm_id']}"] = _round_coords(r["geojson"])
    return shapes


async def osm_water(lat: float, lon: float, radius_km: float) -> tuple[list[dict], list[str]]:
    box = viewbox(lat, lon, radius_km)
    features: list[dict] = []
    warnings: list[str] = []
    for phrase in OSM_PHRASES:  # one at a time: Nominatim allows 1 request per second
        rows = await _osm_search(phrase, box)
        if len(rows) >= NOMINATIM_LIMIT:
            warnings.append(
                f"OpenStreetMap returned its limit of {NOMINATIM_LIMIT} results for {PLURAL[phrase]}. "
                "Some can be missing. Use a smaller radius."
            )
        features.extend(parse_nominatim(rows, phrase))
    ids = sorted({f["osm_id"] for f in features if f["osm_id"][0] in "WR"})
    try:
        shapes = await _osm_outlines(ids)
    except Exception as exc:  # noqa: BLE001 - keep the points without outlines
        warnings.append(f"OpenStreetMap outlines unavailable ({_reason(exc)}). Beaches, bays, and rivers show as points.")
        shapes = {}
    for f in features:
        f["geometry"] = shapes.get(f["osm_id"])
    return features, warnings


async def nhd_water(lat: float, lon: float, radius_km: float) -> tuple[list[dict], list[str]]:
    codes = ", ".join(str(t) for t in (*NHD_KINDS, NHD_MARSH))
    params = {
        "geometry": f"{lon:.4f},{lat:.4f}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "distance": round(radius_km / MI_TO_KM, 3),
        "units": "esriSRUnit_StatuteMile",
        "where": f"gnis_name IS NOT NULL AND ftype IN ({codes})",
        "outFields": "gnis_name,ftype",
        "returnGeometry": "true",
        "outSR": 4326,
        "maxAllowableOffset": SHAPE_TOLERANCE_DEG,
        "geometryPrecision": 5,
        "resultRecordCount": NHD_MAX_RECORDS,
        "f": "geojson",
    }

    async def fetch() -> dict:
        # A cold query took 9 to 40 s on 2026-10-25. The same query took under 1 s once warm.
        payload = await get_json(NHD_WATERBODY, params=params, timeout=45.0)
        if "error" in payload:
            raise RuntimeError(str(payload["error"].get("message", "NHD error")))
        return payload

    result = await cached_call("nhd", (params,), TTL_PLACES, fetch, NHD_WATERBODY)
    warnings = []
    if result.data.get("exceededTransferLimit") or (result.data.get("properties") or {}).get("exceededTransferLimit"):
        warnings.append(f"USGS returned its limit of {NHD_MAX_RECORDS} lakes and reservoirs. Use a smaller radius.")
    return parse_nhd(result.data), warnings


def _reason(exc: BaseException) -> str:
    return "not in the offline cache" if isinstance(exc, OfflineMiss) else type(exc).__name__


async def water_bodies(lat: float, lon: float, radius_km: float) -> tuple[list[dict], list[str]]:
    """Merged water bodies (nearest first) and warnings about missing or cut-off data."""
    osm, nhd = await asyncio.gather(osm_water(lat, lon, radius_km), nhd_water(lat, lon, radius_km), return_exceptions=True)
    features: list[dict] = []
    warnings: list[str] = []
    for outcome, label in ((osm, "Beaches, bays, and rivers"), (nhd, "Lakes and reservoirs")):
        if isinstance(outcome, Exception):
            warnings.append(f"{label} unavailable ({_reason(outcome)}).")
            continue
        found, notes = outcome
        features.extend(found)
        warnings.extend(notes)
    return merge(features, lat, lon, radius_km), warnings
