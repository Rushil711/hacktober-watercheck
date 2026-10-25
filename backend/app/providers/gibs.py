"""NASA GIBS true-color imagery: pick the newest date that has pixels here."""

from __future__ import annotations

import io
import math
from datetime import UTC, datetime, timedelta

from PIL import Image

from ..cache import OfflineMiss, cached_call
from ..config import (
    GIBS_EMPTY_DARK_FRACTION,
    GIBS_LAYER,
    GIBS_MAX_DAYS_BACK,
    GIBS_MAX_ZOOM,
    GIBS_TILE_TEMPLATE,
    TTL_GIBS,
)
from ..models import Imagery, Receipt
from ..net import client


def tile_for(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def dark_fraction(jpeg: bytes) -> float:
    img = Image.open(io.BytesIO(jpeg)).convert("L")
    hist = img.histogram()
    return sum(hist[:8]) / max(sum(hist), 1)


async def _tile_has_data(date: str, x: int, y: int) -> dict:
    url = GIBS_TILE_TEMPLATE.format(date=date, z=GIBS_MAX_ZOOM, y=y, x=x)

    async def fetch() -> dict:
        resp = await client().get(url)
        if resp.status_code == 404:
            return {"has_data": False, "dark": 1.0}
        resp.raise_for_status()
        dark = dark_fraction(resp.content)
        return {"has_data": dark < GIBS_EMPTY_DARK_FRACTION, "dark": round(dark, 3)}

    result = await cached_call("gibs-check", (url,), TTL_GIBS, fetch, url)
    return {**result.data, "url": url, "fetched_at": result.fetched_at, "cached": result.cached}


async def imagery_for(lat: float, lon: float) -> Imagery:
    x, y = tile_for(lat, lon, GIBS_MAX_ZOOM)
    today = datetime.now(UTC).date()
    last_check: dict | None = None
    for back in range(GIBS_MAX_DAYS_BACK + 1):
        date = (today - timedelta(days=back)).isoformat()
        try:
            check = await _tile_has_data(date, x, y)
        except OfflineMiss:
            continue
        last_check = check
        if check["has_data"]:
            return Imagery(
                date=date,
                layer=GIBS_LAYER,
                tile_url_template=GIBS_TILE_TEMPLATE.replace("{date}", date),
                max_zoom=GIBS_MAX_ZOOM,
                fallback_used=back > 0,
                receipt=Receipt(
                    source="NASA GIBS (Worldview)",
                    dataset=f"{GIBS_LAYER} (NOAA-20 VIIRS true color)",
                    observed_at=date,
                    fetched_at=check["fetched_at"],
                    url=f"https://worldview.earthdata.nasa.gov/?l={GIBS_LAYER}&t={date}",
                    cached=check["cached"],
                    note=(
                        f"No imagery yet for {today.isoformat()} here; showing {date}."
                        if back > 0
                        else "Daily NOAA-20 pass, UTC date."
                    ),
                ),
            )
    return Imagery(
        date=None,
        layer=GIBS_LAYER,
        tile_url_template=None,
        max_zoom=GIBS_MAX_ZOOM,
        receipt=Receipt(
            source="NASA GIBS (Worldview)",
            dataset=GIBS_LAYER,
            fetched_at=last_check["fetched_at"] if last_check else None,
            cached=bool(last_check and last_check["cached"]),
            note=f"No usable imagery in the last {GIBS_MAX_DAYS_BACK + 1} days for this tile.",
        ),
    )
