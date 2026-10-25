"""Build minimal evidence payloads from a validated report and run the skills."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from ..models import BeachReport
from ..providers.advisories import clean_text
from .harness import SkillOutcome, run_skill
from .schemas import BestHours, Explanation, NaturalFilter, Verdicts


def _date(iso: str | None) -> str | None:
    return iso[:10] if iso else None


def explain_payload(r: BeachReport) -> dict:
    chl, sst, o = r.chlorophyll, r.sea_temp, r.official
    return {
        "spot": clean_text(r.spot.name, 120),
        "kind": r.spot.kind,
        "official": {
            "status": o.status,
            "label": o.label,
            "detail": clean_text(o.detail, 300),
            "station": clean_text(o.station.name, 80) if o.station else None,
            "station_distance_km": o.station.distance_km if o.station else None,
            "events": [
                {"type": e.type, "issued": _date(e.issued_at), "description": clean_text(e.description, 200)}
                for e in o.events[:3]
            ],
            "source": o.receipt.source,
        },
        "sea_temp": {
            "value_f": sst.current.value,
            "value_c": sst.celsius,
            "observed": _date(sst.current.receipt.observed_at),
            "age_days": sst.age_days,
            "stale": sst.stale,
            "caveat": sst.caveat,
        },
        "chlorophyll": {
            "value_mg_m3": chl.current.value,
            "level": chl.level,
            "observed": _date(chl.current.receipt.observed_at),
            "age_days": chl.age_days,
            "stale": chl.stale,
            "trend_direction": chl.trend_direction,
            "caveat": chl.caveat,
        },
        "feel": {"swim": r.feel.swim_label, "wetsuit": r.feel.wetsuit, "jump_meter": r.feel.jump_meter},
        "best_windows": [{"label": w.label, "facts": w.facts} for w in r.best_time.windows],
        "best_day": r.best_time.day_label,
        "halo": {"label": r.halo.label, "reasons": r.halo.reasons},
        "warnings": [clean_text(w, 160) for w in r.warnings],
        "jump_safety_line": r.feel.safety_line,
        "sources": sorted(
            {
                o.receipt.source,
                sst.current.receipt.source,
                chl.current.receipt.source,
                *([r.best_time.tide_receipt.source] if r.best_time.tide_receipt else []),
                *([r.best_time.weather_receipt.source] if r.best_time.weather_receipt else []),
            }
        ),
    }


def verdict_payload(r: BeachReport) -> dict:
    return {
        "official_status": r.official.label,
        "sea_temp_f": r.sea_temp.current.value,
        "swim_level": r.feel.swim_level,
        "jump_level": r.feel.jump_level,
        "wetsuit": r.feel.wetsuit,
        "chlorophyll_level": r.chlorophyll.level,
        "chlorophyll_trend": r.chlorophyll.trend_direction,
        "tide_now_ft": r.feel.tide_now_ft,
        "jump_meter": r.feel.jump_meter,
    }


def best_payload(r: BeachReport) -> dict:
    return {"day": r.best_time.day_label, "windows": [{"label": w.label, "facts": w.facts} for w in r.best_time.windows]}


def check_explain(r: BeachReport):
    def check(out: BaseModel) -> list[str]:
        assert isinstance(out, Explanation)
        text = " ".join([out.headline, out.environmental_summary, *out.key_observations])
        if r.official.label.lower() not in text.lower():
            return [f'State the official status label exactly: "{r.official.label}".']
        return []

    return check


def check_verdicts(r: BeachReport):
    def check(out: BaseModel) -> list[str]:
        assert isinstance(out, Verdicts)
        problems = []
        if out.swim_feel.level != r.feel.swim_level:
            problems.append(f'swim_feel.level must be "{r.feel.swim_level}".')
        if out.jump_feel.level != r.feel.jump_level:
            problems.append(f'jump_feel.level must be "{r.feel.jump_level}".')
        if "local check" not in out.jump_feel.reason.lower():
            problems.append('jump_feel.reason must end with "Depth, rocks, and surge need a local check."')
        return problems

    return check


def check_best(r: BeachReport):
    def check(out: BaseModel) -> list[str]:
        assert isinstance(out, BestHours)
        expected = [w.label for w in r.best_time.windows]
        got = [w.label for w in out.windows]
        return [] if got == expected else [f"Window labels must be exactly {expected} in that order."]

    return check


async def report_insights(r: BeachReport) -> dict[str, SkillOutcome]:
    async def best() -> SkillOutcome:
        if not r.best_time.windows:
            return SkillOutcome(ok=False, error="no time window to explain")
        return await run_skill("best_hours", best_payload(r), BestHours, check_best(r))

    explain, verdicts, best_hours = await asyncio.gather(
        run_skill("explain_report", explain_payload(r), Explanation, check_explain(r)),
        run_skill("water_feel", verdict_payload(r), Verdicts, check_verdicts(r)),
        best(),
    )
    return {"explain": explain, "verdicts": verdicts, "best_hours": best_hours}


async def parse_natural_query(query: str) -> SkillOutcome:
    return await run_skill("natural_search", {"query": clean_text(query, 200)}, NaturalFilter)
