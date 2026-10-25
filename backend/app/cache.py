"""JSON file cache with fetch times, plus offline (DEMO_MODE) serving.

Every upstream response is stored in backend/cache/<namespace>/<hash>.json as
{"fetched_at", "source_url", "data"}. In offline mode only the cache is read.
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, get_settings

_offline_request: contextvars.ContextVar[bool] = contextvars.ContextVar("offline_request", default=False)


def set_offline_request(value: bool) -> None:
    _offline_request.set(value)


def is_offline() -> bool:
    return get_settings().demo_mode or _offline_request.get()


class OfflineMiss(Exception):
    """Offline mode is on and nothing is cached for this request."""


@dataclass
class CacheResult:
    data: Any
    fetched_at: str
    cached: bool
    stale_fallback: bool = False


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def cache_key(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _path(namespace: str, key: str) -> Path:
    return CACHE_DIR / namespace / f"{key}.json"


def read_entry(namespace: str, key: str) -> dict | None:
    path = _path(namespace, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write_entry(namespace: str, key: str, data: Any, source_url: str | None = None) -> str:
    fetched_at = now_iso()
    path = _path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fetched_at": fetched_at, "source_url": source_url, "data": data}))
    tmp.replace(path)
    return fetched_at


def _age_seconds(fetched_at: str) -> float:
    then = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    return (datetime.now(UTC) - then).total_seconds()


async def cached_call(
    namespace: str,
    key_parts: tuple,
    ttl_s: float,
    fetch: Callable[[], Awaitable[Any]],
    source_url: str | None = None,
) -> CacheResult:
    """Return fresh cache, else fetch and store; fall back to stale cache on failure."""
    key = cache_key(namespace, *key_parts)
    entry = read_entry(namespace, key)
    if is_offline():
        if entry is None:
            raise OfflineMiss(f"Offline mode: no cached {namespace} data for this spot")
        return CacheResult(entry["data"], entry["fetched_at"], cached=True)
    if entry is not None and _age_seconds(entry["fetched_at"]) < ttl_s:
        return CacheResult(entry["data"], entry["fetched_at"], cached=True)
    try:
        data = await fetch()
    except Exception:
        if entry is not None:
            return CacheResult(entry["data"], entry["fetched_at"], cached=True, stale_fallback=True)
        raise
    fetched_at = write_entry(namespace, key, data, source_url)
    return CacheResult(data, fetched_at, cached=False)


async def cached_bytes(
    namespace: str,
    key_parts: tuple,
    ttl_s: float,
    fetch: Callable[[], Awaitable[tuple[bytes, str]]],
) -> tuple[bytes, str, bool]:
    """Binary variant used for map tiles and audio: returns (content, media_type, cached)."""

    async def fetch_encoded() -> dict:
        content, media_type = await fetch()
        return {"b64": base64.b64encode(content).decode(), "media_type": media_type}

    result = await cached_call(namespace, key_parts, ttl_s, fetch_encoded)
    return base64.b64decode(result.data["b64"]), result.data["media_type"], result.cached
