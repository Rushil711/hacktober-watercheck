"""Cached tile proxy so the map keeps working in offline mode.

- base:  NASA Blue Marble, under the imagery while it loads. CARTO dark tiles now return
         "API KEY REQUIRED" (checked 2026-10-25), so they are not used.
- ortho: USGS The National Map orthoimagery (USDA/USGS aerial, public domain); native zoom <= 16
- gibs:  NASA GIBS NOAA-20 daily true color; native zoom <= 9 (about 250 m per pixel)
- fill:  NASA Blue Marble (static, global, native zoom <= 8). Not served alone: it fills the
         blank pixels of ortho and gibs tiles, so the map never shows white or black gaps.
- chl:   ERDDAP WMS chlorophyll overlay. The WMS only offers EPSG:4326, so each
         Web Mercator tile is fetched by its lat/lon bounds and its rows are
         remapped to Mercator so the overlay lines up with the imagery.
"""

from __future__ import annotations

import io
import math
import re
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi.responses import Response
from PIL import Image, ImageChops, ImageFilter

from . import config as C
from .cache import OfflineMiss, cached_bytes
from .net import client

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")
TILE = 256
WMS_SRC_HEIGHT = 512  # extra source rows so the Mercator remap stays sub-pixel


def _empty_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


EMPTY_PNG = _empty_png()  # served for tiles missing offline


def tile_lat(z: int, yy: float) -> float:
    n = 2**z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2**z
    return tile_lat(z, y + 1), x / n * 360 - 180, tile_lat(z, y), (x + 1) / n * 360 - 180


def mercator_source_rows(z: int, y: int, src_height: int) -> list[int]:
    """For each output row of a Web Mercator tile, the matching row of a lat/lon image of the same bounds."""
    south, _, north, _ = tile_bounds(z, 0, y)
    rows = []
    for j in range(TILE):
        lat = tile_lat(z, y + (j + 0.5) / TILE)
        r = int((north - lat) / (north - south) * src_height)
        rows.append(min(max(r, 0), src_height - 1))
    return rows


def reproject_to_mercator(png_4326: bytes, z: int, y: int) -> bytes:
    src = Image.open(io.BytesIO(png_4326)).convert("RGBA")
    if src.width != TILE:
        src = src.resize((TILE, src.height), Image.Resampling.NEAREST)
    out = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    for j, r in enumerate(mercator_source_rows(z, y, src.height)):
        out.paste(src.crop((0, r, TILE, r + 1)), (0, j))
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def wms_params(layer: str, z: int, x: int, y: int, time: str | None) -> dict:
    south, west, north, east = tile_bounds(z, x, y)
    return {
        "service": "WMS",
        "request": "GetMap",
        "version": "1.3.0",
        "layers": layer,
        "styles": "",
        "crs": "EPSG:4326",
        "bbox": f"{south:.8f},{west:.8f},{north:.8f},{east:.8f}",
        "width": str(TILE),
        "height": str(WMS_SRC_HEIGHT),
        "format": "image/png",
        "transparent": "true",
        "elevation": "0.0",
        **({"time": time if "T" in time else f"{time}T12:00:00Z"} if time else {}),
    }


async def fill_tile(z: int, x: int, y: int) -> Image.Image:
    """Blue Marble imagery for one tile. Above zoom 8 the ancestor tile is cropped and scaled up."""
    dz = max(0, z - C.FILL_MAX_ZOOM)
    pz, px, py = z - dz, x >> dz, y >> dz
    url = C.FILL_TILE_TEMPLATE.format(z=pz, y=py, x=px)

    async def fetch() -> tuple[bytes, str]:
        return await _fetch(url)

    content, _, _ = await cached_bytes("tiles-fill", (url,), C.TTL_FILL, fetch)
    img = Image.open(io.BytesIO(content)).convert("RGB")
    if dz:
        size = TILE / 2**dz
        ox, oy = (x - (px << dz)) * size, (y - (py << dz)) * size
        img = img.resize((TILE, TILE), Image.Resampling.BICUBIC, box=(ox, oy, ox + size, oy + size))
    return img


def blank_mask(img: Image.Image, white: bool) -> Image.Image | None:
    """Mask of no-data pixels (pure black, transparent, and pure white when white=True), or None.

    An opening removes small features such as white roofs or surf, then the mask grows by 3 px
    to cover the JPEG fringe at the edge of a no-data area.
    """
    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()
    low = ImageChops.darker(ImageChops.darker(r, g), b)
    high = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mask = ImageChops.lighter(high.point(lambda v: 255 if v <= 4 else 0), a.point(lambda v: 255 if v < 16 else 0))
    if white:
        mask = ImageChops.lighter(mask, low.point(lambda v: 255 if v >= 240 else 0))
    mask = mask.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MaxFilter(7))
    return mask if mask.getbbox() else None


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


async def fill_blanks(content: bytes, z: int, x: int, y: int, white: bool) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(content))
    mask = blank_mask(img, white)
    if mask is None:
        return content, Image.MIME.get(img.format or "", "image/jpeg")
    filled = Image.composite(await fill_tile(z, x, y), img.convert("RGB"), mask)
    return _jpeg(filled), "image/jpeg"


def _check_zxy(z: int, x: int, y: int) -> None:
    if not (0 <= z <= 19 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(status_code=400, detail="Bad tile coordinates")


async def _fetch(url: str, params: dict | None = None) -> tuple[bytes, str]:
    resp = await client().get(url, params=params)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "image/png").split(";")[0]


async def tile(provider: str, z: int, x: int, y: int, date: str | None = None) -> Response:
    _check_zxy(z, x, y)
    params: dict | None = None
    fetch: Callable[[], Awaitable[tuple[bytes, str]]]
    if provider == "base":
        try:
            content = _jpeg(await fill_tile(z, x, y))
        except Exception:  # noqa: BLE001 - offline miss or upstream error
            return Response(EMPTY_PNG, media_type="image/png", headers={"X-WaterCheck-Cache": "error"})
        return Response(content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})
    if provider == "ortho":
        if z > C.ORTHO_MAX_ZOOM:
            raise HTTPException(status_code=400, detail=f"ortho tiles exist up to z{C.ORTHO_MAX_ZOOM}")
        url = C.ORTHO_TILE_TEMPLATE.format(z=z, y=y, x=x)
    elif provider == "gibs":
        if not date or not _DATE_RE.match(date) or z > C.GIBS_MAX_ZOOM:
            raise HTTPException(status_code=400, detail=f"gibs tiles need ?date=YYYY-MM-DD and z <= {C.GIBS_MAX_ZOOM}")
        url = C.GIBS_TILE_TEMPLATE.format(date=date, z=z, y=y, x=x)
    elif provider == "chl":
        if date and not _TIME_RE.match(date):
            raise HTTPException(status_code=400, detail="Bad time")
        url = f"{C.ERDDAP_BASE}/wms/{C.CHL_DATASET.dataset_id}/request"
        params = wms_params(f"{C.CHL_DATASET.dataset_id}:{C.CHL_DATASET.variable}", z, x, y, date)
    else:
        raise HTTPException(status_code=404, detail="Unknown tile provider")

    if provider == "chl":

        async def fetch() -> tuple[bytes, str]:
            content, _ = await _fetch(url, params)
            return reproject_to_mercator(content, z, y), "image/png"

    elif provider in ("ortho", "gibs"):

        async def fetch() -> tuple[bytes, str]:
            content, _ = await _fetch(url, params)
            # gibs: white is cloud, which is real, so only black no-data is filled
            return await fill_blanks(content, z, x, y, white=provider == "ortho")

    else:

        async def fetch() -> tuple[bytes, str]:
            return await _fetch(url, params)

    try:
        content, media_type, cached = await cached_bytes(
            f"tiles-{provider}", (url, sorted((params or {}).items()), "v3"), C.TTL_TILES, fetch
        )
    except Exception as exc:  # noqa: BLE001 - a missing tile should not break the map
        status = "miss" if isinstance(exc, OfflineMiss) else "error"
        if provider in ("ortho", "gibs"):
            try:
                fallback = _jpeg(await fill_tile(z, x, y))
                return Response(fallback, media_type="image/jpeg", headers={"X-WaterCheck-Cache": f"{status}-fill"})
            except Exception:  # noqa: BLE001
                pass
        return Response(EMPTY_PNG, media_type="image/png", headers={"X-WaterCheck-Cache": status})
    return Response(
        content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600", "X-WaterCheck-Cache": "hit" if cached else "live"},
    )
