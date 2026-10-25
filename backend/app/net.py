"""Shared HTTP client and small geo helpers."""

from __future__ import annotations

import math
from typing import Any

import httpx

from .config import user_agent

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": user_agent()},
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    if _client is not None and not _client.is_closed:
        await _client.aclose()


async def get_json(url: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
    kwargs: dict[str, Any] = {"params": params}
    if timeout is not None:
        kwargs["timeout"] = timeout
    resp = await client().get(url, **kwargs)
    resp.raise_for_status()
    return resp.json()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def km_to_deg_lat(km: float) -> float:
    return km / 111.32


def km_to_deg_lon(km: float, lat: float) -> float:
    return km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
