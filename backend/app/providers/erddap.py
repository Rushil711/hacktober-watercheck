"""NOAA CoastWatch ERDDAP: chlorophyll-a and sea surface temperature grids.

Dataset IDs and variables are checked against the live metadata before any
data query, so a renamed variable or unit change fails loudly instead of
returning wrong numbers.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from ..cache import cached_call
from ..config import ERDDAP_BASE, TTL_GRID, TTL_METADATA, GridDataset
from ..net import get_json, km_to_deg_lat, km_to_deg_lon


class MetadataError(Exception):
    pass


@dataclass
class GridMeta:
    units: str
    lat_descending: bool
    lat_res: float
    lon_res: float
    time_end: str


@dataclass
class Cell:
    time: str
    lat: float
    lon: float
    value: float | None


@dataclass
class Grid:
    dataset: GridDataset
    meta: GridMeta
    cells: list[Cell]
    url: str
    fetched_at: str
    cached: bool


def info_url(ds: GridDataset) -> str:
    return f"{ERDDAP_BASE}/info/{ds.dataset_id}/index.json"


def parse_metadata(ds: GridDataset, info: dict) -> GridMeta:
    rows = info["table"]["rows"]
    variables = {r[1] for r in rows if r[0] == "variable"}
    if ds.variable not in variables:
        raise MetadataError(f"{ds.dataset_id}: variable '{ds.variable}' not found (has {sorted(variables)})")
    units = next((r[4] for r in rows if r[0] == "attribute" and r[1] == ds.variable and r[2] == "units"), None)
    if units != ds.expected_units:
        raise MetadataError(f"{ds.dataset_id}: units are '{units}', expected '{ds.expected_units}'")

    def spacing(dim: str) -> float:
        info_row = next((r for r in rows if r[0] == "dimension" and r[1] == dim), None)
        if info_row is None:
            raise MetadataError(f"{ds.dataset_id}: missing dimension {dim}")
        match = re.search(r"averageSpacing=(-?[\d.eE+-]+)", info_row[4])
        if not match:
            raise MetadataError(f"{ds.dataset_id}: cannot read spacing for {dim}")
        return float(match.group(1))

    time_end = next(
        (r[4] for r in rows if r[0] == "attribute" and r[1] == "NC_GLOBAL" and r[2] == "time_coverage_end"),
        None,
    )
    if not time_end:
        raise MetadataError(f"{ds.dataset_id}: missing time_coverage_end")
    lat_spacing = spacing("latitude")
    return GridMeta(
        units=units,
        lat_descending=lat_spacing < 0,
        lat_res=abs(lat_spacing),
        lon_res=abs(spacing("longitude")),
        time_end=time_end,
    )


async def get_metadata(ds: GridDataset) -> GridMeta:
    url = info_url(ds)
    result = await cached_call("erddap-info", (url,), TTL_METADATA, lambda: get_json(url), url)
    return parse_metadata(ds, result.data)


def build_query_url(
    ds: GridDataset, meta: GridMeta, lat_min: float, lat_max: float, lon_min: float, lon_max: float, days: int
) -> str:
    end = datetime.fromisoformat(meta.time_end.replace("Z", "+00:00"))
    start = end - timedelta(days=days - 1)
    lat_a, lat_b = (lat_max, lat_min) if meta.lat_descending else (lat_min, lat_max)
    altitude = "[(0.0)]" if ds.has_altitude else ""
    constraint = (
        f"{ds.variable}[({start:%Y-%m-%dT00:00:00Z}):1:(last)]{altitude}"
        f"[({lat_a:.4f}):1:({lat_b:.4f})][({lon_min:.4f}):1:({lon_max:.4f})]"
    )
    return f"{ERDDAP_BASE}/griddap/{ds.dataset_id}.json?{quote(constraint, safe='():')}"


def parse_grid_json(ds: GridDataset, payload: dict) -> list[list]:
    table = payload["table"]
    cols = table["columnNames"]
    i_t, i_lat, i_lon, i_v = (cols.index(c) for c in ("time", "latitude", "longitude", ds.variable))
    out = []
    for row in table["rows"]:
        value = row[i_v]
        if isinstance(value, float) and math.isnan(value):
            value = None
        out.append([row[i_t], row[i_lat], row[i_lon], value])
    return out


async def fetch_grid(ds: GridDataset, lat_min: float, lat_max: float, lon_min: float, lon_max: float, days: int) -> Grid:
    meta = await get_metadata(ds)
    url = build_query_url(ds, meta, lat_min, lat_max, lon_min, lon_max, days)

    async def fetch() -> list[list]:
        return parse_grid_json(ds, await get_json(url, timeout=60.0))

    result = await cached_call("erddap-grid", (url,), TTL_GRID, fetch, url)
    cells = [Cell(t, la, lo, v) for t, la, lo, v in result.data]
    return Grid(ds, meta, cells, url, result.fetched_at, result.cached)


def box_bounds(lat: float, lon: float, half_km: float, res_deg: float) -> tuple[float, float, float, float]:
    """Bounds that select every grid cell overlapping the box around (lat, lon)."""
    dlat = km_to_deg_lat(half_km) + res_deg / 2
    dlon = km_to_deg_lon(half_km, lat) + res_deg / 2
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def cells_in_box(grid: Grid, lat: float, lon: float, half_km: float) -> list[Cell]:
    lat_min, lat_max, _, _ = box_bounds(lat, lon, half_km, grid.meta.lat_res)
    _, _, lon_min, lon_max = box_bounds(lat, lon, half_km, grid.meta.lon_res)
    return [c for c in grid.cells if lat_min <= c.lat <= lat_max and lon_min <= c.lon <= lon_max]


@dataclass
class DailyValue:
    date: str
    time: str
    mean: float | None
    valid: int
    total: int


def daily_means(cells: list[Cell]) -> list[DailyValue]:
    by_time: dict[str, list[Cell]] = {}
    for c in cells:
        by_time.setdefault(c.time, []).append(c)
    out = []
    for t in sorted(by_time):
        group = by_time[t]
        valid = [c.value for c in group if c.value is not None]
        mean = sum(valid) / len(valid) if valid else None
        out.append(DailyValue(t[:10], t, mean, len(valid), len(group)))
    return out


def latest_valid(days: list[DailyValue]) -> DailyValue | None:
    for d in reversed(days):
        if d.mean is not None:
            return d
    return None


def age_days(time_iso: str, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    then = datetime.fromisoformat(time_iso.replace("Z", "+00:00"))
    return round((now - then).total_seconds() / 86400, 1)


def dataset_page(ds: GridDataset) -> str:
    return f"{ERDDAP_BASE}/griddap/{ds.dataset_id}.html"
