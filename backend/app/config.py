"""Settings, thresholds, dataset IDs, and demo beaches.

Thresholds and demo beaches are agent-editable but need human approval
(README section 7). Keys live only in backend/.env.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"
CACHE_DIR = BACKEND_DIR / "cache"
SKILLS_DIR = Path(__file__).resolve().parent / "skills"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    gemma_model: str = "gemma-4-26b-a4b-it"
    xai_api_key: str = ""
    xai_voice_id: str = "eve"
    demo_mode: bool = False
    contact_email: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


def get_settings() -> Settings:
    """Read settings fresh so keys added to backend/.env apply without a restart."""
    return Settings()


def user_agent() -> str:
    contact = get_settings().contact_email.strip()
    suffix = f"; {contact}" if contact else ""
    return f"WaterCheck/0.1 (Hacktoberfest demo{suffix})"


# --- Satellite datasets (confirmed against ERDDAP metadata on 2026-10-25) ---
# The README named noaacwNPPN20VIIRSchlociDaily, but its metadata shows coverage
# ended 2021-09-02 and the variable is chl_oci. The current NOAA-20 NRT daily
# product below is the replacement; providers re-check metadata at runtime.


@dataclass(frozen=True)
class GridDataset:
    dataset_id: str
    variable: str
    expected_units: str
    has_altitude: bool
    title: str


ERDDAP_BASE = "https://coastwatch.noaa.gov/erddap"
CHL_DATASET = GridDataset(
    dataset_id="noaacwN20VIIRSchlaDaily",
    variable="chlor_a",
    expected_units="mg m^-3",
    has_altitude=True,
    title="Chlorophyll, NOAA-20 VIIRS, Near Real-Time, Global 4km, Daily",
)
SST_DATASET = GridDataset(
    dataset_id="noaacwBLENDEDsstDNDaily",
    variable="analysed_sst",
    expected_units="degree_C",
    has_altitude=False,
    title="Sea-Surface Temperature, NOAA Geo-polar Blended Analysis Day+Night, Global 5km, Daily",
)

GIBS_LAYER = "VIIRS_NOAA20_CorrectedReflectance_TrueColor"
GIBS_TILE_TEMPLATE = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
    + GIBS_LAYER
    + "/default/{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpeg"
)
GIBS_MAX_ZOOM = 9  # GIBS serves this layer only up to GoogleMapsCompatible_Level9 (~250 m/px)
GIBS_MAX_DAYS_BACK = 3

# Detail imagery for zoom 10-16: USDA/USGS orthoimagery from The National Map (public domain,
# no key, US coverage). The tile cache stops at level 16 (1:9,028); level 17+ returns 404.
ORTHO_TILE_TEMPLATE = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
ORTHO_MIN_ZOOM = 10
ORTHO_MAX_ZOOM = 16
ORTHO_ATTRIBUTION = "USDA, USGS The National Map: Orthoimagery"
GIBS_EMPTY_DARK_FRACTION = 0.95

# --- Measurement box and thresholds ---
OFFSHORE_BOX_KM = 2.0  # half-size of the box around the beach; cells that overlap it are averaged
TREND_DAYS = 7
CHL_LOOKBACK_DAYS = 14
CHL_ELEVATED = 3.0  # mg m^-3
CHL_HIGH = 10.0  # mg m^-3
CHL_TREND_RATIO = 1.3
CHL_STALE_DAYS = 3
SST_STALE_DAYS = 2

# Water feel bands, sea surface temperature in degrees F (lower bound inclusive).
FEEL_BANDS: list[tuple[float, str, str]] = [
    (72.0, "warm", "Warm"),
    (68.0, "comfortable", "Comfortable"),
    (64.0, "mild", "Mild"),
    (60.0, "brisk", "Brisk"),
    (-99.0, "cold", "Brr"),
]
WETSUIT_BANDS: list[tuple[float, str]] = [(68.0, "none"), (60.0, "3/2 mm"), (-99.0, "4/3 mm")]
GAUGE_MIN_F = 50.0
GAUGE_MAX_F = 78.0

JUMP_SAFETY_LINE = "Water feel only. Depth, rocks, and surge need a local check."

# --- Official status matching ---
ADVISORY_MATCH_RADIUS_KM = 1.0
BEACHWATCH_MAX_AGE_DAYS = 14
BEACHWATCH_ADVISORIES_RESOURCE = "d5cd6a23-829c-426d-a63e-689a55a3db9c"
BEACHWATCH_STATIONS_RESOURCE = "98e628ff-d012-4982-ad32-b9f9ad8ab524"
BEACHWATCH_PAGE = "https://data.ca.gov/dataset/beach-water-quality-postings-and-closures"
SD_COUNTY_BASE = "https://cosdapps.sandiegocounty.gov/sdbeachinfo"
SD_COUNTY_PAGE = "https://www.sdbeachinfo.com/"

# --- Tides and weather ---
DEFAULT_TIDE_STATION = "9410230"  # La Jolla (Scripps Institution Wharf)
TIDE_STATION_MAX_KM = 60.0
DEFAULT_TIMEZONE = "America/Los_Angeles"
BEST_WINDOW_HOURS = 2
IDEAL_AIR_F = 75.0

# --- Discovery ---
SEARCH_RADIUS_KM = 3.0  # around a geocoded address
STRAIGHT_LINE_KM_PER_MIN = 0.8  # turns a Gemma drive-time filter into a search radius
MI_TO_KM = 1.609344
NEARBY_DEFAULT_MI = 5.0
NEARBY_MIN_MI = 0.5
NEARBY_MAX_MI = 25.0  # Nominatim returns at most 40 results per category, so keep the area small
MAX_NEARBY_SPOTS = 150
NOMINATIM_MIN_INTERVAL_S = 1.1  # Nominatim usage policy: at most 1 request per second
NOMINATIM_LIMIT = 40
SHAPE_TOLERANCE_DEG = 0.0003  # about 30 m; simplifies water outlines sent to the map

# --- Cache TTLs (seconds) ---
TTL_GRID = 30 * 60
TTL_METADATA = 24 * 3600
TTL_ADVISORY = 15 * 60
TTL_STATIONS = 7 * 24 * 3600
TTL_TIDES = 6 * 3600
TTL_WEATHER = 30 * 60
TTL_PLACES = 7 * 24 * 3600
TTL_GEOCODE = 30 * 24 * 3600
TTL_GIBS = 60 * 60
TTL_GEMMA = 6 * 3600
TTL_TILES = 24 * 3600

GEMMA_TEMPERATURE = 0.2


@dataclass(frozen=True)
class DemoBeach:
    key: str
    name: str
    lat: float
    lon: float
    kind: str


# Coordinates are OpenStreetMap features (Overpass and Nominatim, 2026-10-25).
DEMO_BEACHES: list[DemoBeach] = [
    DemoBeach("la-jolla-shores", "La Jolla Shores Beach", 32.85585, -117.25897, "beach"),
    DemoBeach("blacks-beach", "Blacks Beach", 32.87625, -117.25180, "beach"),
    DemoBeach("sunset-cliffs", "Sunset Cliffs", 32.72582, -117.25700, "cliff"),
]
