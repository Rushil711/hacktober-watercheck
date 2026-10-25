"""NOAA CO-OPS hourly tide predictions and NWS hourly forecast."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..cache import cached_call
from ..config import DEFAULT_TIDE_STATION, TIDE_STATION_MAX_KM, TTL_STATIONS, TTL_TIDES, TTL_WEATHER
from ..net import get_json, haversine_km

COOPS_STATIONS = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"
COOPS_DATA = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"


async def tide_stations():
    async def fetch() -> list[dict]:
        data = await get_json(COOPS_STATIONS, params={"type": "tidepredictions"}, timeout=45.0)
        # Only reference ("R") stations provide hourly predictions.
        return [
            {"id": s["id"], "name": s["name"], "lat": float(s["lat"]), "lon": float(s["lng"])}
            for s in data["stations"]
            if s.get("type") == "R"
        ]

    return await cached_call("coops-stations", ("R",), TTL_STATIONS, fetch, COOPS_STATIONS)


def pick_station(stations: list[dict], lat: float, lon: float) -> tuple[dict | None, float]:
    best, best_d = None, float("inf")
    for s in stations:
        d = haversine_km(lat, lon, s["lat"], s["lon"])
        if d < best_d:
            best, best_d = s, d
    if best is None or best_d > TIDE_STATION_MAX_KM:
        return None, best_d
    return best, best_d


async def tide_predictions(station_id: str, start_local_date: datetime):
    begin = start_local_date.strftime("%Y%m%d")
    params = {
        "product": "predictions",
        "station": station_id,
        "datum": "MLLW",
        "time_zone": "gmt",
        "units": "english",
        "interval": "h",
        "format": "json",
        "begin_date": begin,
        "range": "72",
        "application": "WaterCheck",
    }

    async def fetch() -> list[dict]:
        data = await get_json(COOPS_DATA, params=params)
        if "predictions" not in data:
            raise RuntimeError(data.get("error", {}).get("message", "No tide predictions"))
        return [
            {"time": datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC).isoformat(), "ft": float(p["v"])}
            for p in data["predictions"]
        ]

    url = f"{COOPS_DATA}?station={station_id}&product=predictions&begin_date={begin}"
    return await cached_call("coops-predictions", (station_id, begin), TTL_TIDES, fetch, url)


def station_page(station_id: str) -> str:
    return f"https://tidesandcurrents.noaa.gov/noaatidepredictions.html?id={station_id}"


async def nws_hourly(lat: float, lon: float):
    key_lat, key_lon = round(lat, 3), round(lon, 3)
    points_url = f"https://api.weather.gov/points/{key_lat},{key_lon}"

    async def fetch() -> dict:
        point = await get_json(points_url)
        props = point["properties"]
        hourly = await get_json(props["forecastHourly"])
        hp = hourly["properties"]
        return {
            "time_zone": props.get("timeZone"),
            "forecast_url": props["forecastHourly"],
            "updated": hp.get("updateTime") or hp.get("generatedAt"),
            "periods": [
                {
                    "start": p["startTime"],
                    "temp_f": p["temperature"] if p.get("temperatureUnit") == "F" else round(p["temperature"] * 9 / 5 + 32),
                    "is_daytime": p["isDaytime"],
                    "sky": p.get("shortForecast"),
                    "wind": p.get("windSpeed"),
                }
                for p in hp["periods"][:96]
            ],
        }

    return await cached_call("nws-hourly", (key_lat, key_lon), TTL_WEATHER, fetch, points_url)


def local_midnight(now_local: datetime) -> datetime:
    return now_local.replace(hour=0, minute=0, second=0, microsecond=0)


def day_hours(day_start_local: datetime) -> list[datetime]:
    return [day_start_local + timedelta(hours=h) for h in range(24)]


__all__ = [
    "DEFAULT_TIDE_STATION",
    "nws_hourly",
    "pick_station",
    "station_page",
    "tide_predictions",
    "tide_stations",
]
