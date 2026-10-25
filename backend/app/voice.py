"""Grok Voice briefing via the xAI Text to Speech API.

Activates as soon as XAI_API_KEY is in backend/.env (settings are re-read on
every request). The spoken script is built by code from the report; Gemma's
headline is included only when its card passed validation.
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .cache import OfflineMiss, cached_bytes
from .config import get_settings
from .gemma.schemas import Explanation
from .models import BeachReport
from .net import client

TTS_URL = "https://api.x.ai/v1/tts"
DOCS_URL = "https://docs.x.ai/developers/model-capabilities/audio/text-to-speech"
TTL_VOICE = 24 * 3600


class BriefingRequest(BaseModel):
    report: BeachReport
    explanation: Explanation | None = None


def key_problem(key: str) -> str | None:
    if not key:
        return "Grok Voice is off: add XAI_API_KEY to backend/.env."
    if any(c in key for c in "<>[]{}\"' \t"):
        return "XAI_API_KEY in backend/.env contains brackets, quotes, or spaces. Remove them."
    if not key.startswith("xai-"):
        return "XAI_API_KEY in backend/.env should start with 'xai-'."
    return None


def status() -> dict:
    s = get_settings()
    problem = key_problem(s.xai_api_key.strip())
    return {"configured": problem is None, "problem": problem, "docs_url": DOCS_URL, "voice_id": s.xai_voice_id}


def _num(v: float | None, digits: int = 0) -> str | None:
    if v is None:
        return None
    return f"{v:.{digits}f}"


def build_script(r: BeachReport, explanation: Explanation | None) -> str:
    parts = [f"WaterCheck briefing for {r.spot.name}."]
    parts.append(f"Official status: {r.official.label}. {r.official.detail}")
    sst = _num(r.sea_temp.current.value)
    if sst:
        parts.append(
            f"Satellite sea surface temperature is about {sst} degrees Fahrenheit. "
            "That is not the temperature at the shore or at swim depth."
        )
    else:
        parts.append("Sea temperature is unavailable.")
    chl = _num(r.chlorophyll.current.value, 1)
    if chl:
        age = _num(r.chlorophyll.age_days)
        parts.append(
            f"Chlorophyll is {chl} milligrams per cubic meter, {r.chlorophyll.level}"
            + (f", from a pass {age} days ago." if age else ".")
        )
    if r.best_time.windows:
        w = r.best_time.windows[0]
        parts.append(f"Best window {r.best_time.day_label.lower()}: {w.label.replace('–', ' to ')}.")
    if explanation:
        parts.append(f"Gemma's summary: {explanation.headline}")
    parts.append("For cliff jumping, this is water feel only. Depth, rocks, and surge need a local check.")
    return " ".join(parts)[:1800]


async def briefing(req: BriefingRequest) -> Response:
    s = get_settings()
    key = s.xai_api_key.strip()
    problem = key_problem(key)
    script = build_script(req.report, req.explanation)

    async def fetch() -> tuple[bytes, str]:
        if problem:
            raise HTTPException(status_code=503, detail=problem)
        resp = await client().post(
            TTS_URL,
            json={"text": script, "voice_id": s.xai_voice_id or "eve", "language": "en"},
            headers={"Authorization": f"Bearer {key}"},
            timeout=60.0,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Grok Voice API returned HTTP {resp.status_code}.")
        return resp.content, resp.headers.get("content-type", "audio/mpeg").split(";")[0]

    try:
        audio, media_type, cached = await cached_bytes("voice", (script, s.xai_voice_id), TTL_VOICE, fetch)
    except OfflineMiss as exc:
        raise HTTPException(status_code=503, detail="Offline mode: this briefing is not cached yet.") from exc
    return Response(audio, media_type=media_type, headers={"X-WaterCheck-Cache": "hit" if cached else "live"})
