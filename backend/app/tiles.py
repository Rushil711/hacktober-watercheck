"""Cached tile proxy so the map keeps working in offline mode.

- base: CARTO dark basemap (OpenStreetMap data)
- gibs: NASA GIBS NOAA-20 true color (native zoom <= 9)
- chl:  ERDDAP WMS chlorophyll overlay. The WMS only offers EPSG:4326, so each
        Web Mercator tile is requested by its lat/lon bounds.
"""

from __future__ import annotations

import io
import math
import re

from fastapi import HTTPException
from fastapi.responses import Response
from PIL import Image

from . import config as C
from .cache import OfflineMiss, cached_bytes
from .net import client

BASE_TEMPLATE = "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")


def _empty_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


EMPTY_PNG = _empty_png()  # served for tiles missing offline


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2**z

    def lat(yy: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))

    lon_w = x / n * 360 - 180
    lon_e = (x + 1) / n * 360 - 180
    return lat(y + 1), lon_w, lat(y), lon_e


def _check_zxy(z: int, x: int, y: int) -> None:
    if not (0 <= z <= 19 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(status_code=400, detail="Bad tile coordinates")


async def _fetch(url: str, params: dict | None = None) -> tuple[bytes, str]:
    resp = await client().get(url, params=params)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "image/png").split(";")[0]


async def tile(provider: str, z: int, x: int, y: int, date: str | None = None) -> Response:
    _check_zxy(z, x, y)
    if provider == "base":
        url, params = BASE_TEMPLATE.format(z=z, x=x, y=y), None
    elif provider == "gibs":
        if not date or not _DATE_RE.match(date) or z > C.GIBS_MAX_ZOOM:
            raise HTTPException(status_code=400, detail="gibs tiles need ?date=YYYY-MM-DD and z <= 9")
        url, params = C.GIBS_TILE_TEMPLATE.format(date=date, z=z, y=y, x=x), None
    elif provider == "chl":
        if date and not _TIME_RE.match(date):
            raise HTTPException(status_code=400, detail="Bad time")
        south, west, north, east = tile_bounds(z, x, y)
        url = f"{C.ERDDAP_BASE}/wms/{C.CHL_DATASET.dataset_id}/request"
        params = {
            "service": "WMS",
            "request": "GetMap",
            "version": "1.3.0",
            "layers": f"{C.CHL_DATASET.dataset_id}:{C.CHL_DATASET.variable}",
            "styles": "",
            "crs": "EPSG:4326",
            "bbox": f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}",
            "width": "256",
            "height": "256",
            "format": "image/png",
            "transparent": "true",
            "elevation": "0.0",
            **({"time": date if "T" in date else f"{date}T12:00:00Z"} if date else {}),
        }
    else:
        raise HTTPException(status_code=404, detail="Unknown tile provider")
    try:
        content, media_type, cached = await cached_bytes(
            f"tiles-{provider}", (url, sorted((params or {}).items())), C.TTL_TILES, lambda: _fetch(url, params)
        )
    except OfflineMiss:
        return Response(EMPTY_PNG, media_type="image/png", headers={"X-WaterCheck-Cache": "miss"})
    except Exception:  # noqa: BLE001 - a missing tile should not break the map
        return Response(EMPTY_PNG, media_type="image/png", headers={"X-WaterCheck-Cache": "error"})
    return Response(
        content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600", "X-WaterCheck-Cache": "hit" if cached else "live"},
    )
