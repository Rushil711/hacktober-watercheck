"""Gemma 4 through the Gemini API (the integration from the original server.py)."""

from __future__ import annotations

from ..config import GEMMA_TEMPERATURE, get_settings
from ..net import client

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GemmaNotConfigured(Exception):
    pass


class GemmaError(Exception):
    pass


def model_name() -> str:
    return get_settings().gemma_model


async def generate(system: str, messages: list[dict]) -> str:
    """messages: [{"role": "user" | "model", "text": ...}] -> visible reply text."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GemmaNotConfigured("GEMINI_API_KEY is not set in backend/.env")
    body: dict = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in messages],
        "generationConfig": {
            "temperature": GEMMA_TEMPERATURE,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingLevel": "minimal"},
        },
    }
    url = GEMINI_URL.format(model=settings.gemma_model)
    headers = {"x-goog-api-key": settings.gemini_api_key}
    resp = await client().post(url, json=body, headers=headers, timeout=90.0)
    if resp.status_code == 400 and "hinking" in resp.text:
        body["generationConfig"].pop("thinkingConfig")
        resp = await client().post(url, json=body, headers=headers, timeout=90.0)
    if resp.status_code != 200:
        raise GemmaError(f"Gemini API returned HTTP {resp.status_code}")
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        raise GemmaError("Gemini API reply had no content") from exc
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))
