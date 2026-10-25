"""Official water-quality status.

1. San Diego County Beach & Bay Program (live; the public sdbeachinfo app's
   OutSystems endpoints, with version tokens discovered at runtime).
2. California SWRCB BeachWatch on data.ca.gov (statewide; San Diego records in
   it can lag by months, so it is used for station matching and is shown as
   "Unverified" unless it is recent).
Gemma never sets this status.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..cache import cached_call
from ..config import (
    ADVISORY_MATCH_RADIUS_KM,
    BEACHWATCH_ADVISORIES_RESOURCE,
    BEACHWATCH_MAX_AGE_DAYS,
    BEACHWATCH_PAGE,
    BEACHWATCH_STATIONS_RESOURCE,
    SD_COUNTY_BASE,
    SD_COUNTY_PAGE,
    TTL_ADVISORY,
    TTL_METADATA,
    TTL_STATIONS,
)
from ..models import OfficialEvent, OfficialStatus, Receipt, Station
from ..net import client, get_json, haversine_km

# Event type ids from the county app's static EventType entity (moduleinfo).
COUNTY_EVENT_TYPES = {1: "advisory", 2: "closure", 3: "warning"}
STATUS_PRIORITY = {"closure": 3, "warning": 2, "advisory": 1}
STATUS_LABELS = {
    "closure": "Closed (official)",
    "warning": "Warning (official)",
    "advisory": "Advisory (official)",
    "no_advisory_found": "No advisory found",
    "unverified": "Unverified",
    "unavailable": "Unavailable",
}
NO_ADVISORY_NOTE = "No advisory found is not the same as confirmed safe."
_NULL_DATE = "1900-01-01"
_ANON_CSRF_RE = re.compile(r'"(T6C\+9iB49TLra4jEsMeSckDMNhQ=)"')


def clean_text(value: Any, limit: int = 280) -> str:
    """Strip markup from untrusted source text and cap its length."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


# ---------------- San Diego County ----------------


@dataclass
class CountyTokens:
    module_version: str
    csrf: str
    api: dict[str, str]


COUNTY_ENDPOINTS = {
    "HomeBlockNew": [
        "ScreenDataSetGetRegionsNort",
        "ScreenDataSetGetRegionsCentral",
        "ScreenDataSetGetRegionsSouth",
        "ActionGetSitesByTypeNotification",
        "DataActionGetLastDateTime",
    ],
    "BlockMarkup": ["ScreenDataSetGetEventsList"],
}


def extract_api_tokens(module: str, js: str, names: list[str]) -> dict[str, str]:
    tokens = {}
    for name in names:
        marker = f'"screenservices/CoSD_Beach_Water_CW/MainFlow/{module}/{name}", "'
        idx = js.find(marker)
        if idx < 0:
            raise RuntimeError(f"County app endpoint {name} not found")
        start = idx + len(marker)
        tokens[name] = js[start : js.index('"', start)]
    return tokens


async def _discover_tokens() -> dict:
    http = client()
    version = (await http.get(f"{SD_COUNTY_BASE}/moduleservices/moduleversioninfo")).json()["versionToken"]
    os_js = (await http.get(f"{SD_COUNTY_BASE}/scripts/OutSystems.js")).text
    csrf_match = _ANON_CSRF_RE.search(os_js)
    if not csrf_match:
        raise RuntimeError("County app anonymous CSRF token not found")
    api: dict[str, str] = {}
    for module, names in COUNTY_ENDPOINTS.items():
        js = (await http.get(f"{SD_COUNTY_BASE}/scripts/CoSD_Beach_Water_CW.MainFlow.{module}.mvc.js")).text
        api.update(extract_api_tokens(module, js, names))
    return {"module_version": version, "csrf": csrf_match.group(1), "api": api}


async def county_tokens(refresh: bool = False) -> CountyTokens:
    ttl = 0 if refresh else TTL_METADATA
    result = await cached_call("sdcounty-tokens", ("v1",), ttl, _discover_tokens)
    return CountyTokens(**result.data)


async def _county_post(module: str, name: str, body: dict) -> dict:
    for attempt in range(2):
        tokens = await county_tokens(refresh=attempt > 0)
        payload = {
            "versionInfo": {"moduleVersion": tokens.module_version, "apiVersion": tokens.api[name]},
            "viewName": "MainFlow.Home",
            **body,
        }
        resp = await client().post(
            f"{SD_COUNTY_BASE}/screenservices/CoSD_Beach_Water_CW/MainFlow/{module}/{name}",
            json=payload,
            headers={"X-CSRFToken": tokens.csrf},
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        changed = data.get("versionInfo", {}).get("hasApiVersionChanged")
        if resp.status_code == 200 and "exception" not in data and not changed:
            return data["data"]
    raise RuntimeError(f"County endpoint {name} failed (HTTP {resp.status_code})")


def _aggregate_body(variables: dict | None = None, max_records: int = 2000) -> dict:
    return {
        "screenData": {"variables": variables or {}},
        "inputParameters": {"StartIndex": 0, "MaxRecords": max_records},
        "clientVariables": {},
    }


async def _fetch_county_snapshot() -> dict:
    sites: list[dict] = []
    for region in ("ScreenDataSetGetRegionsNort", "ScreenDataSetGetRegionsCentral", "ScreenDataSetGetRegionsSouth"):
        data = await _county_post("HomeBlockNew", region, _aggregate_body())
        for row in data["List"]["List"]:
            site = row["Site"]
            sites.append(
                {"id": site["Id"], "name": site["LocationName"], "lat": float(site["Latitude"]), "lon": float(site["Longitude"])}
            )
    active: dict[str, list[str]] = {}
    for type_id, status in COUNTY_EVENT_TYPES.items():
        data = await _county_post(
            "HomeBlockNew", "ActionGetSitesByTypeNotification", {"inputParameters": {"EventTypeIdentifier": type_id}}
        )
        for point in data["Out1"]["List"]:
            lat, lon = float(point["Latitude"]), float(point["Longitude"])
            for site in sites:
                if abs(site["lat"] - lat) < 1e-4 and abs(site["lon"] - lon) < 1e-4:
                    active.setdefault(site["id"], [])
                    if status not in active[site["id"]]:
                        active[site["id"]].append(status)
    last = await _county_post("HomeBlockNew", "DataActionGetLastDateTime", {"screenData": {"variables": {}}})
    return {"sites": sites, "active": active, "last_update": last.get("LastUpdate")}


async def county_snapshot():
    return await cached_call("sdcounty-snapshot", ("v1",), TTL_ADVISORY, _fetch_county_snapshot, SD_COUNTY_PAGE)


async def county_site_events(site_id: str) -> list[dict]:
    async def fetch() -> list[dict]:
        data = await _county_post(
            "BlockMarkup",
            "ScreenDataSetGetEventsList",
            _aggregate_body({"SiteId": site_id, "_siteIdInDataFetchStatus": 1}, 50),
        )
        events = []
        for row in data["List"]["List"]:
            event = row["Event"]
            if not str(event.get("LiftedDateTime", "")).startswith(_NULL_DATE):
                continue
            events.append(
                {
                    "type": COUNTY_EVENT_TYPES.get(row["EventType"]["Id"], "notice"),
                    "issued_at": event.get("IssueDateTime"),
                    "description": clean_text(event.get("DescriptionIssue")),
                    "station_id": row["Site"].get("StationID") or None,
                }
            )
        return events

    result = await cached_call("sdcounty-events", (site_id,), TTL_ADVISORY, fetch, SD_COUNTY_PAGE)
    return result.data


def nearest(items: list[dict], lat: float, lon: float) -> tuple[dict | None, float]:
    best, best_d = None, float("inf")
    for item in items:
        d = haversine_km(lat, lon, item["lat"], item["lon"])
        if d < best_d:
            best, best_d = item, d
    return best, best_d


def status_from_county(site: dict | None, distance_km: float, active: list[str], events: list[dict]) -> tuple[str, str]:
    if site is None or distance_km > ADVISORY_MATCH_RADIUS_KM:
        return "unverified", f"No county monitoring station within {ADVISORY_MATCH_RADIUS_KM:g} km."
    types = set(active) | {e["type"] for e in events if e["type"] in STATUS_PRIORITY}
    if not types:
        return "no_advisory_found", f"No active advisory, warning, or closure at {site['name']}. {NO_ADVISORY_NOTE}"
    top = max(types, key=lambda t: STATUS_PRIORITY.get(t, 0))
    return top, f"County lists an active {top} at {site['name']}."


# ---------------- BeachWatch (data.ca.gov) ----------------


def _sql_url(sql: str) -> tuple[str, dict]:
    return "https://data.ca.gov/api/3/action/datastore_search_sql", {"sql": sql}


async def _sql(sql: str) -> list[dict]:
    url, params = _sql_url(sql)
    data = await get_json(url, params=params, timeout=45.0)
    if not data.get("success"):
        raise RuntimeError("BeachWatch query failed")
    return data["result"]["records"]


async def beachwatch_stations():
    sql = (
        'SELECT "Station_id","Station_Name","Station_Description","Beach_Name","Station_UpperLat",'
        f'"Station_UpperLon","CountyName","Status" FROM "{BEACHWATCH_STATIONS_RESOURCE}"'
    )

    async def fetch() -> list[dict]:
        rows = await _sql(sql)
        out = []
        for r in rows:
            try:
                lat, lon = float(r["Station_UpperLat"]), float(r["Station_UpperLon"])
            except (TypeError, ValueError):
                continue
            out.append(
                {
                    "id": str(r["Station_id"]),
                    "code": r["Station_Name"],
                    "name": clean_text(r["Station_Description"] or r["Beach_Name"], 120),
                    "beach": clean_text(r["Beach_Name"], 120),
                    "county": r["CountyName"],
                    "lat": lat,
                    "lon": lon,
                }
            )
        return out

    return await cached_call("beachwatch-stations", (sql,), TTL_STATIONS, fetch, BEACHWATCH_PAGE)


async def beachwatch_latest(station_id: str, county: str) -> dict:
    safe_id = int(float(station_id))
    safe_county = county.replace("'", "''")
    sql_records = (
        'SELECT "AdvisoryType","AdvisoryCause","DateofAdvisory","DateOpened" '
        f'FROM "{BEACHWATCH_ADVISORIES_RESOURCE}" WHERE "Station_id" = {safe_id} '
        'ORDER BY "DateofAdvisory" DESC LIMIT 3'
    )
    sql_fresh = (
        f'SELECT max("DateofAdvisory") AS latest FROM "{BEACHWATCH_ADVISORIES_RESOURCE}" WHERE "CountyName" = \'{safe_county}\''
    )

    async def fetch() -> dict:
        return {"records": await _sql(sql_records), "county_latest": (await _sql(sql_fresh))[0]["latest"]}

    result = await cached_call("beachwatch-latest", (sql_records,), TTL_ADVISORY, fetch, BEACHWATCH_PAGE)
    return {**result.data, "fetched_at": result.fetched_at, "cached": result.cached}


def status_from_beachwatch(latest: dict, today: datetime | None = None) -> tuple[str, str]:
    today = today or datetime.now(UTC)
    county_latest = latest.get("county_latest")
    records = latest.get("records") or []
    if not county_latest:
        return "unverified", "State BeachWatch has no records for this county."
    age = (today.date() - datetime.fromisoformat(county_latest[:10]).date()).days
    if age > BEACHWATCH_MAX_AGE_DAYS:
        last = records[0] if records else None
        last_txt = f" Last state record for this station: {last['AdvisoryType']} issued {last['DateofAdvisory']}." if last else ""
        return "unverified", f"State BeachWatch records for this county end {county_latest[:10]}.{last_txt}"
    for r in records:
        if r.get("DateOpened") is None:
            kind = "closure" if r.get("AdvisoryType") == "Closure" else "advisory"
            return (
                kind,
                f"State BeachWatch lists an open {r.get('AdvisoryType', 'advisory').lower()} issued {r['DateofAdvisory']}.",
            )
    return "no_advisory_found", f"No open state BeachWatch posting for this station. {NO_ADVISORY_NOTE}"


# ---------------- Combined ----------------


async def official_status(lat: float, lon: float) -> tuple[OfficialStatus, list[str]]:
    warnings: list[str] = []
    try:
        snap = await county_snapshot()
        site, dist = nearest(snap.data["sites"], lat, lon)
        if site is not None and dist <= ADVISORY_MATCH_RADIUS_KM:
            events = await county_site_events(site["id"])
            status, detail = status_from_county(site, dist, snap.data["active"].get(site["id"], []), events)
            station_code = next((e["station_id"] for e in events if e.get("station_id")), None)
            return (
                OfficialStatus(
                    status=status,
                    label=STATUS_LABELS[status],
                    detail=detail,
                    station=Station(id=station_code or f"site {site['id']}", name=site["name"], distance_km=round(dist, 2)),
                    events=[
                        OfficialEvent(type=e["type"], issued_at=e["issued_at"], description=e["description"] or None)
                        for e in events
                    ],
                    receipt=Receipt(
                        source="San Diego County Beach & Bay Program",
                        dataset="sdbeachinfo live site status",
                        observed_at=snap.data.get("last_update"),
                        fetched_at=snap.fetched_at,
                        url=SD_COUNTY_PAGE,
                        cached=snap.cached,
                        note=f"Matched to the nearest county station, {dist:.2f} km away.",
                    ),
                ),
                warnings,
            )
    except Exception as exc:  # noqa: BLE001 - one provider must not fail the report
        warnings.append(f"San Diego County beach status unavailable ({type(exc).__name__}).")

    try:
        stations = await beachwatch_stations()
        station, dist = nearest(stations.data, lat, lon)
        if station is None or dist > ADVISORY_MATCH_RADIUS_KM:
            return (
                OfficialStatus(
                    status="unverified",
                    label=STATUS_LABELS["unverified"],
                    detail=f"No official monitoring station within {ADVISORY_MATCH_RADIUS_KM:g} km of this spot.",
                    receipt=Receipt(
                        source="California SWRCB BeachWatch",
                        dataset="Beach Water Quality Monitoring Stations",
                        fetched_at=stations.fetched_at,
                        url=BEACHWATCH_PAGE,
                        cached=stations.cached,
                    ),
                ),
                warnings,
            )
        latest = await beachwatch_latest(station["id"], station["county"])
        status, detail = status_from_beachwatch(latest)
        return (
            OfficialStatus(
                status=status,
                label=STATUS_LABELS[status],
                detail=detail,
                station=Station(id=station["code"], name=station["name"], distance_km=round(dist, 2)),
                receipt=Receipt(
                    source="California SWRCB BeachWatch",
                    dataset="Beach Advisories (Postings and Closures)",
                    observed_at=latest.get("county_latest"),
                    fetched_at=latest["fetched_at"],
                    url=BEACHWATCH_PAGE,
                    cached=latest["cached"],
                    note=f"Matched to station {station['code']}, {dist:.2f} km away.",
                ),
            ),
            warnings,
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"State BeachWatch status unavailable ({type(exc).__name__}).")
        return (
            OfficialStatus(
                status="unavailable",
                label=STATUS_LABELS["unavailable"],
                detail="Official status could not be loaded. Check the posted signs at the beach.",
                receipt=Receipt(source="Official water-quality services", url=SD_COUNTY_PAGE),
            ),
            warnings,
        )


async def status_lookup_bulk() -> dict:
    """County snapshot for many spots at once (Feature 2). Returns {} if unavailable."""
    try:
        snap = await county_snapshot()
        return snap.data
    except Exception:  # noqa: BLE001
        return {}


def quick_status(snapshot: dict, lat: float, lon: float) -> str:
    if not snapshot:
        return "unavailable"
    site, dist = nearest(snapshot["sites"], lat, lon)
    if site is None or dist > ADVISORY_MATCH_RADIUS_KM:
        return "unverified"
    active = snapshot["active"].get(site["id"], [])
    if not active:
        return "no_advisory_found"
    return max(active, key=lambda t: STATUS_PRIORITY.get(t, 0))
