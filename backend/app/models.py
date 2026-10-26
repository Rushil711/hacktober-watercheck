"""Pydantic models shared by the API, scoring, and the Gemma harness."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

UNAVAILABLE = "Unavailable"

OfficialStatusCode = Literal["closure", "warning", "advisory", "no_advisory_found", "unverified", "unavailable"]
HaloColor = Literal["green", "amber", "coral"]
FeelLevel = Literal["closed", "advisory", "cold", "brisk", "mild", "comfortable", "warm", "unknown"]
ChlLevel = Literal["typical", "elevated", "high", "unknown"]


class Receipt(BaseModel):
    source: str
    dataset: str | None = None
    observed_at: str | None = None
    fetched_at: str | None = None
    url: str | None = None
    cached: bool = False
    note: str | None = None


class Measurement(BaseModel):
    label: str
    value: float | None = None
    unit: str | None = None
    display: str = UNAVAILABLE
    receipt: Receipt


class Spot(BaseModel):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    kind: str = "beach"


class TrendPoint(BaseModel):
    date: str
    value: float | None = None
    pixels: int = 0


class ChlorophyllBlock(BaseModel):
    current: Measurement
    trend: list[TrendPoint] = []
    trend_direction: Literal["rising", "falling", "steady", "insufficient data"] = "insufficient data"
    level: ChlLevel = "unknown"
    age_days: float | None = None
    stale: bool = False
    pixels_used: int = 0
    caveat: str = "High chlorophyll does not prove a harmful bloom. Low chlorophyll does not prove safe water."


class SeaTempBlock(BaseModel):
    current: Measurement
    celsius: float | None = None
    age_days: float | None = None
    stale: bool = False
    caveat: str = (
        "Satellite sea surface temperature is about 5 km wide and near the surface. "
        "It is not the temperature at the shore or at swim depth."
    )


class OfficialEvent(BaseModel):
    type: str
    issued_at: str | None = None
    description: str | None = None


class Station(BaseModel):
    id: str | None = None
    name: str
    distance_km: float


class OfficialStatus(BaseModel):
    status: OfficialStatusCode
    label: str
    detail: str
    station: Station | None = None
    events: list[OfficialEvent] = []
    receipt: Receipt


class Imagery(BaseModel):
    date: str | None = None
    layer: str
    tile_url_template: str | None = None
    max_zoom: int
    fallback_used: bool = False
    receipt: Receipt


class HourPoint(BaseModel):
    time: str
    hour_label: str
    tide_ft: float | None = None
    air_f: float | None = None
    is_daytime: bool | None = None
    sky: str | None = None
    in_window: bool = False


class TimeWindow(BaseModel):
    start: str
    end: str
    label: str
    score: float
    facts: list[str]


class BestTime(BaseModel):
    day_label: str
    hours: list[HourPoint] = []
    windows: list[TimeWindow] = []
    tide_station: Station | None = None
    tide_receipt: Receipt | None = None
    weather_receipt: Receipt | None = None
    note: str | None = None


class Feel(BaseModel):
    swim_level: FeelLevel
    swim_label: str
    jump_level: FeelLevel
    jump_label: str
    wetsuit: str | None = None
    gauge_position: float | None = None
    jump_meter: int | None = None
    tide_now_ft: float | None = None
    safety_line: str


class Halo(BaseModel):
    color: HaloColor
    label: str
    icon: str
    reasons: list[str]


class BeachReport(BaseModel):
    spot: Spot
    generated_at: str
    offline: bool
    chlorophyll: ChlorophyllBlock
    sea_temp: SeaTempBlock
    official: OfficialStatus
    imagery: Imagery
    best_time: BestTime
    feel: Feel
    halo: Halo
    data_age: str
    warnings: list[str] = []


class Candidate(BaseModel):
    name: str
    lat: float
    lon: float
    kind: str
    distance_km: float
    source: str


class SearchResult(BaseModel):
    query: str
    place: Candidate | None
    candidates: list[Candidate]
    attribution: str = "Search by Nominatim. Data © OpenStreetMap contributors (ODbL)."
    warnings: list[str] = []


class WaterBody(BaseModel):
    id: str
    name: str
    kind: str  # beach, bay, river, lake, reservoir, estuary, or lagoon
    lat: float
    lon: float
    distance_km: float  # to the nearest point of the outline
    source: str
    geometry: dict[str, Any]  # GeoJSON, simplified to about 30 m
    report_available: bool = False  # the ocean report covers beaches and bays only
    halo: Halo | None = None
    official_status: OfficialStatusCode | None = None
    sea_temp_f: float | None = None
    chl: float | None = None


class NearbyResult(BaseModel):
    origin: Spot
    radius_km: float
    spots: list[WaterBody]
    attribution: str = (
        "Beaches, bays, and rivers © OpenStreetMap contributors (ODbL), via Nominatim. "
        "Lakes and reservoirs: USGS National Hydrography Dataset (US only)."
    )
    warnings: list[str] = []
