"""Nominatim geocoding, Overpass beach/cliff discovery, and OSRM drive times."""

from __future__ import annotations

from ..cache import cached_call
from ..config import (
    OSRM_BATCH,
    STRAIGHT_LINE_KM_PER_MIN,
    TTL_DRIVE,
    TTL_GEOCODE,
    TTL_PLACES,
)
from ..net import client, get_json, haversine_km

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
OSRM_TABLE = "https://router.project-osrm.org/table/v1/driving/"
DEDUPE_KM = 1.0


async def geocode(query: str) -> list[dict]:
    q = " ".join(query.split())[:200]
    params = {"q": q, "format": "jsonv2", "limit": 5, "addressdetails": 0}

    async def fetch() -> list[dict]:
        rows = await get_json(NOMINATIM, params=params)
        return [
            {
                "name": r.get("name") or r["display_name"].split(",")[0],
                "display_name": r["display_name"],
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "category": r.get("category"),
                "type": r.get("type"),
            }
            for r in rows
        ]

    result = await cached_call("nominatim", (q.lower(),), TTL_GEOCODE, fetch, NOMINATIM)
    return result.data


def _kind(tags: dict) -> str:
    return "cliff" if tags.get("natural") == "cliff" else "beach"


def parse_overpass(payload: dict) -> list[dict]:
    spots: list[dict] = []
    for el in payload.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        center = el.get("center") or ({"lat": el.get("lat"), "lon": el.get("lon")} if "lat" in el else None)
        if not name or not center:
            continue
        spot = {"name": name, "lat": float(center["lat"]), "lon": float(center["lon"]), "kind": _kind(tags)}
        if any(
            s["name"] == spot["name"] and haversine_km(s["lat"], s["lon"], spot["lat"], spot["lon"]) < DEDUPE_KM for s in spots
        ):
            continue
        spots.append(spot)
    return spots


async def water_spots(lat: float, lon: float, radius_km: float) -> list[dict]:
    """Named beaches and named cliffs within radius_km (cached per rounded center)."""
    key_lat, key_lon, radius_m = round(lat, 2), round(lon, 2), int(radius_km * 1000)
    query = (
        f"[out:json][timeout:25];("
        f'nwr["natural"="beach"]["name"](around:{radius_m},{key_lat},{key_lon});'
        f'nwr["natural"="cliff"]["name"](around:{radius_m},{key_lat},{key_lon});'
        f");out center tags;"
    )

    async def fetch() -> list[dict]:
        resp = await client().post(OVERPASS, data={"data": query}, timeout=30.0)
        resp.raise_for_status()
        return parse_overpass(resp.json())

    result = await cached_call("overpass", (query,), TTL_PLACES, fetch, OVERPASS)
    spots = result.data
    for s in spots:
        s["distance_km"] = round(haversine_km(lat, lon, s["lat"], s["lon"]), 2)
    return sorted(spots, key=lambda s: s["distance_km"])


async def drive_minutes(origin: tuple[float, float], dests: list[tuple[float, float]]) -> tuple[list[float | None], str]:
    """OSRM durations in minutes; returns (durations, method)."""
    durations: list[float | None] = []
    try:
        for i in range(0, len(dests), OSRM_BATCH):
            batch = dests[i : i + OSRM_BATCH]
            coords = ";".join(f"{lo:.5f},{la:.5f}" for la, lo in [origin, *batch])
            url = f"{OSRM_TABLE}{coords}"

            async def fetch(url: str = url) -> list:
                data = await get_json(url, params={"sources": "0", "annotations": "duration"}, timeout=45.0)
                if data.get("code") != "Ok":
                    raise RuntimeError(data.get("message", "OSRM error"))
                return data["durations"][0][1:]

            result = await cached_call("osrm", (url,), TTL_DRIVE, fetch, OSRM_TABLE)
            durations.extend(None if d is None else round(d / 60, 1) for d in result.data)
        return durations, "osrm"
    except Exception:  # noqa: BLE001 - fall back to a labeled estimate
        return [
            round(haversine_km(origin[0], origin[1], la, lo) / STRAIGHT_LINE_KM_PER_MIN, 1) for la, lo in dests
        ], "straight-line"
