"""Nominatim geocoding and Overpass beach/cliff discovery."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..cache import cached_call
from ..config import NOMINATIM_MIN_INTERVAL_S, TTL_GEOCODE, TTL_PLACES
from ..net import client, get_json, haversine_km

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
NOMINATIM = f"{NOMINATIM_BASE}/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
DEDUPE_KM = 1.0

_nominatim_lock = asyncio.Lock()
_nominatim_last = 0.0


async def nominatim_get(url: str, params: dict[str, Any]) -> Any:
    """GET from Nominatim, one request at a time and at most one per second (usage policy)."""
    global _nominatim_last
    async with _nominatim_lock:
        wait = _nominatim_last + NOMINATIM_MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await get_json(url, params=params)
        finally:
            _nominatim_last = time.monotonic()


async def geocode(query: str) -> list[dict]:
    q = " ".join(query.split())[:200]
    params = {"q": q, "format": "jsonv2", "limit": 5, "addressdetails": 0}

    async def fetch() -> list[dict]:
        rows = await nominatim_get(NOMINATIM, params)
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
