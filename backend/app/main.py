"""WaterCheck API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import config as C
from . import voice
from .cache import is_offline, set_offline_request
from .gemma.insights import parse_natural_query, report_insights
from .gemma.schemas import NaturalFilter
from .models import BeachReport, NearbyResult, SearchResult, Spot
from .nearby import nearby, search
from .net import close_client
from .providers.places import geocode
from .report import build_report
from .tiles import tile


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await close_client()


async def offline_flag(request: Request) -> None:
    flag = request.query_params.get("offline") or request.headers.get("x-watercheck-offline") or ""
    set_offline_request(flag.lower() in ("1", "true", "yes"))


app = FastAPI(title="WaterCheck API", version="0.1.0", lifespan=lifespan, dependencies=[Depends(offline_flag)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in C.get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    s = C.get_settings()
    return {
        "ok": True,
        "offline": is_offline(),
        "demo_mode": s.demo_mode,
        "gemma_configured": bool(s.gemini_api_key),
        "gemma_model": s.gemma_model,
        "voice_configured": voice.status()["configured"],
    }


@app.get("/api/config")
async def app_config() -> dict:
    return {
        "demo_beaches": [b.__dict__ for b in C.DEMO_BEACHES],
        "nearby_default_mi": C.NEARBY_DEFAULT_MI,
        "nearby_min_mi": C.NEARBY_MIN_MI,
        "nearby_max_mi": C.NEARBY_MAX_MI,
        "chl_dataset": C.CHL_DATASET.dataset_id,
        "chl_variable": C.CHL_DATASET.variable,
        "gibs_layer": C.GIBS_LAYER,
        "gibs_max_zoom": C.GIBS_MAX_ZOOM,
        "ortho_min_zoom": C.ORTHO_MIN_ZOOM,
        "ortho_max_zoom": C.ORTHO_MAX_ZOOM,
        "ortho_attribution": C.ORTHO_ATTRIBUTION,
        "safety_line": C.JUMP_SAFETY_LINE,
    }


@app.get("/api/beach/report", response_model=BeachReport)
async def beach_report(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    name: Annotated[str, Query(max_length=120)] = "Selected spot",
    kind: Annotated[str, Query(max_length=20)] = "beach",
) -> BeachReport:
    return await build_report(Spot(name=name, lat=lat, lon=lon, kind=kind))


@app.get("/api/search", response_model=SearchResult)
async def search_place(q: Annotated[str, Query(min_length=2, max_length=200)]) -> SearchResult:
    try:
        return await search(q)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Place search failed ({type(exc).__name__}).") from exc


@app.post("/api/beach/insights")
async def beach_insights(report: BeachReport) -> dict:
    outcomes = await report_insights(report)
    return {k: v.model_dump() for k, v in outcomes.items()}


class NaturalSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=200)
    origin: dict[str, float] | None = None


@app.post("/api/gemma/search")
async def gemma_search(req: NaturalSearchRequest) -> dict:
    outcome = await parse_natural_query(req.query)
    warnings: list[str] = []
    if not outcome.ok or not outcome.data:
        return {"filter": outcome.model_dump(), "origin": None, "result": None, "warnings": warnings}
    flt = NaturalFilter.model_validate(outcome.data)
    origin = None
    if flt.near:
        try:
            hits = await geocode(flt.near)
        except Exception:  # noqa: BLE001
            hits = []
        if hits:
            origin = Spot(name=hits[0]["display_name"][:120], lat=hits[0]["lat"], lon=hits[0]["lon"], kind="origin")
        else:
            warnings.append(f"Could not find '{flt.near}'.")
    if origin is None and req.origin and {"lat", "lon"} <= req.origin.keys():
        origin = Spot(name="Your pin", lat=req.origin["lat"], lon=req.origin["lon"], kind="origin")
    if origin is None:
        warnings.append("Drop a pin or name a place so the drive time has a starting point.")
        return {"filter": outcome.model_dump(), "origin": None, "result": None, "warnings": warnings}
    result = await nearby(origin, flt.max_drive_min * C.STRAIGHT_LINE_KM_PER_MIN)
    keep = [
        s
        for s in result.spots
        if (flt.min_temp_f is None or (s.sea_temp_f is not None and s.sea_temp_f >= flt.min_temp_f))
        and (flt.activity == "any" or (flt.activity == "jump") == (s.kind == "cliff"))
    ]
    result = result.model_copy(update={"spots": keep})
    return {"filter": outcome.model_dump(), "origin": origin.model_dump(), "result": result.model_dump(), "warnings": warnings}


@app.get("/api/voice/status")
async def voice_status() -> dict:
    return voice.status()


@app.post("/api/voice/briefing")
async def voice_briefing(req: voice.BriefingRequest):
    return await voice.briefing(req)


@app.get("/api/tiles/{provider}/{z}/{x}/{y}")
async def map_tile(provider: str, z: int, x: int, y: int, date: str | None = None):
    return await tile(provider, z, x, y, date)


@app.get("/api/nearby", response_model=NearbyResult)
async def nearby_water(
    radius_mi: Annotated[float, Query(ge=C.NEARBY_MIN_MI, le=C.NEARBY_MAX_MI)] = C.NEARBY_DEFAULT_MI,
    address: Annotated[str | None, Query(min_length=2, max_length=200)] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> NearbyResult:
    if address:
        try:
            hits = await geocode(address)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Address lookup failed ({type(exc).__name__}).") from exc
        if not hits:
            raise HTTPException(status_code=404, detail="No place found for that address. Try a fuller address.")
        origin = Spot(name=hits[0]["display_name"][:120], lat=hits[0]["lat"], lon=hits[0]["lon"], kind="origin")
    elif lat is not None and lon is not None:
        origin = Spot(name="Search center", lat=lat, lon=lon, kind="origin")
    else:
        raise HTTPException(status_code=422, detail="Give an address, or lat and lon.")
    return await nearby(origin, radius_mi * C.MI_TO_KM)
