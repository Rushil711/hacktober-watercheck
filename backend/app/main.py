"""WaterCheck API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from . import config as C
from .cache import is_offline, set_offline_request
from .models import BeachReport, NearbyResult, SearchResult, Spot
from .nearby import nearby, search
from .net import close_client
from .report import build_report


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
        "voice_configured": bool(s.xai_api_key),
    }


@app.get("/api/config")
async def app_config() -> dict:
    return {
        "demo_beaches": [b.__dict__ for b in C.DEMO_BEACHES],
        "drive_options": list(C.DRIVE_OPTIONS_MIN),
        "chl_dataset": C.CHL_DATASET.dataset_id,
        "chl_variable": C.CHL_DATASET.variable,
        "chl_wms_url": f"{C.ERDDAP_BASE}/wms/{C.CHL_DATASET.dataset_id}/request",
        "chl_wms_layer": f"{C.CHL_DATASET.dataset_id}:{C.CHL_DATASET.variable}",
        "gibs_layer": C.GIBS_LAYER,
        "gibs_max_zoom": C.GIBS_MAX_ZOOM,
        "safety_line": C.JUMP_SAFETY_LINE,
        "max_km_per_min": C.MAX_KM_PER_MIN,
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


@app.get("/api/nearby", response_model=NearbyResult)
async def nearby_spots(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    drive_min: Annotated[int, Query()] = 30,
) -> NearbyResult:
    if drive_min not in C.DRIVE_OPTIONS_MIN:
        raise HTTPException(status_code=422, detail=f"drive_min must be one of {list(C.DRIVE_OPTIONS_MIN)}")
    return await nearby(lat, lon, drive_min)
