"""Every number and status the app shows is computed here, never by Gemma."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from . import config as C
from .models import (
    UNAVAILABLE,
    BestTime,
    ChlorophyllBlock,
    Feel,
    Halo,
    HourPoint,
    Measurement,
    OfficialStatus,
    Receipt,
    SeaTempBlock,
    TimeWindow,
    TrendPoint,
)
from .providers.erddap import DailyValue, age_days, latest_valid

OFFICIAL_BLOCKING = {"closure", "warning", "advisory"}


def c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def chl_level(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= C.CHL_HIGH:
        return "high"
    if value >= C.CHL_ELEVATED:
        return "elevated"
    return "typical"


def trend_direction(points: list[TrendPoint]) -> str:
    valid = [p.value for p in points if p.value is not None]
    if len(valid) < 2:
        return "insufficient data"
    latest, earlier = valid[-1], sum(valid[:-1]) / len(valid[:-1])
    if earlier <= 0:
        return "insufficient data"
    ratio = latest / earlier
    if ratio >= C.CHL_TREND_RATIO:
        return "rising"
    if ratio <= 1 / C.CHL_TREND_RATIO:
        return "falling"
    return "steady"


def build_trend(days: list[DailyValue], end_date: str, n_days: int = C.TREND_DAYS) -> list[TrendPoint]:
    by_date = {d.date: d for d in days}
    end = datetime.fromisoformat(end_date[:10])
    out = []
    for i in range(n_days - 1, -1, -1):
        date = (end - timedelta(days=i)).date().isoformat()
        d = by_date.get(date)
        out.append(
            TrendPoint(date=date, value=round(d.mean, 3) if d and d.mean is not None else None, pixels=d.valid if d else 0)
        )
    return out


def chlorophyll_block(days: list[DailyValue], receipt: Receipt, end_date: str, now: datetime | None = None) -> ChlorophyllBlock:
    latest = latest_valid(days)
    trend = build_trend(days, end_date)
    if latest is None:
        return ChlorophyllBlock(
            current=Measurement(
                label="Chlorophyll-a",
                unit="mg/m³",
                receipt=receipt.model_copy(update={"note": "No cloud-free pixels near this spot in the lookback window."}),
            ),
            trend=trend,
        )
    age = age_days(latest.time, now)
    value = round(latest.mean, 2)
    return ChlorophyllBlock(
        current=Measurement(
            label="Chlorophyll-a",
            value=value,
            unit="mg/m³",
            display=f"{value:.2f}",
            receipt=receipt.model_copy(
                update={
                    "observed_at": latest.time,
                    "note": (
                        f"Mean of {latest.valid} satellite cell(s) overlapping a {C.OFFSHORE_BOX_KM:g} km box around the spot."
                    ),
                }
            ),
        ),
        trend=trend,
        trend_direction=trend_direction(trend),
        level=chl_level(value),
        age_days=age,
        stale=age > C.CHL_STALE_DAYS,
        pixels_used=latest.valid,
    )


def sea_temp_block(days: list[DailyValue], receipt: Receipt, now: datetime | None = None) -> SeaTempBlock:
    latest = latest_valid(days)
    if latest is None:
        return SeaTempBlock(current=Measurement(label="Sea surface temperature", unit="°F", receipt=receipt))
    celsius = round(latest.mean, 2)
    fahrenheit = round(c_to_f(latest.mean), 1)
    age = age_days(latest.time, now)
    return SeaTempBlock(
        current=Measurement(
            label="Sea surface temperature",
            value=fahrenheit,
            unit="°F",
            display=f"{fahrenheit:.0f}",
            receipt=receipt.model_copy(
                update={
                    "observed_at": latest.time,
                    "note": f"Mean of {latest.valid} satellite cell(s); {celsius:.1f} °C. Not shore or swim-depth temperature.",
                }
            ),
        ),
        celsius=celsius,
        age_days=age,
        stale=age > C.SST_STALE_DAYS,
    )


def feel_band(temp_f: float | None) -> tuple[str, str]:
    if temp_f is None:
        return "unknown", UNAVAILABLE
    for lower, level, label in C.FEEL_BANDS:
        if temp_f >= lower:
            return level, label
    return "unknown", UNAVAILABLE


def wetsuit_for(temp_f: float | None) -> str | None:
    if temp_f is None:
        return None
    for lower, suit in C.WETSUIT_BANDS:
        if temp_f >= lower:
            return suit
    return None


def tide_fraction(tide_ft: float | None, day_tides: list[float]) -> float | None:
    if tide_ft is None or not day_tides:
        return None
    lo, hi = min(day_tides), max(day_tides)
    if hi - lo < 1e-6:
        return 0.5
    return (tide_ft - lo) / (hi - lo)


def compute_feel(sst: SeaTempBlock, official: OfficialStatus, tide_now_ft: float | None, day_tides: list[float]) -> Feel:
    temp_f = sst.current.value
    level, label = feel_band(temp_f)
    swim_level, swim_label = level, label
    if official.status == "closure":
        swim_level, swim_label = "closed", "Closed (official)"
    elif official.status in ("warning", "advisory"):
        swim_level, swim_label = "advisory", f"{official.label}"
    jump_level, jump_label = swim_level, swim_label
    gauge = None if temp_f is None else max(0.0, min(1.0, (temp_f - C.GAUGE_MIN_F) / (C.GAUGE_MAX_F - C.GAUGE_MIN_F)))
    frac = tide_fraction(tide_now_ft, day_tides)
    meter = None
    if gauge is not None and frac is not None:
        meter = round(100 * (0.5 * gauge + 0.5 * frac))
    return Feel(
        swim_level=swim_level,
        swim_label=swim_label,
        jump_level=jump_level,
        jump_label=jump_label,
        wetsuit=wetsuit_for(temp_f),
        gauge_position=None if gauge is None else round(gauge, 3),
        jump_meter=meter,
        tide_now_ft=tide_now_ft,
        safety_line=C.JUMP_SAFETY_LINE,
    )


def compute_halo(official_status: str, chl: str, chl_stale: bool, sst_available: bool) -> Halo:
    if official_status in OFFICIAL_BLOCKING:
        names = {"closure": "Official closure", "warning": "Official warning", "advisory": "Official advisory"}
        return Halo(
            color="coral", label=names[official_status], icon="octagon-alert", reasons=[names[official_status] + " in effect"]
        )
    reasons = []
    if official_status in ("unverified", "unavailable"):
        reasons.append("Official status not verified")
    if chl in ("elevated", "high"):
        reasons.append(f"Chlorophyll {chl}")
    if chl == "unknown":
        reasons.append("Chlorophyll unavailable")
    elif chl_stale:
        reasons.append("Chlorophyll data is old")
    if not sst_available:
        reasons.append("Sea temperature unavailable")
    if reasons:
        return Halo(color="amber", label="Check details", icon="triangle-alert", reasons=reasons)
    return Halo(color="green", label="No flags found", icon="circle-check", reasons=["No advisory found", "Chlorophyll typical"])


def sky_score(sky: str | None) -> float:
    s = (sky or "").lower()
    if "sunny" in s or "clear" in s:
        return 1.0
    if "partly" in s or "mostly sunny" in s:
        return 0.7
    if "rain" in s or "shower" in s or "thunder" in s:
        return 0.0
    return 0.4


def best_time(
    tides: list[dict],
    periods: list[dict],
    tz_name: str | None,
    now: datetime | None = None,
) -> BestTime:
    tz = ZoneInfo(tz_name or C.DEFAULT_TIMEZONE)
    now = (now or datetime.now(UTC)).astimezone(tz)
    tide_by_hour = {datetime.fromisoformat(t["time"]).astimezone(tz).replace(minute=0): t["ft"] for t in tides}
    wx_by_hour = {datetime.fromisoformat(p["start"]).astimezone(tz).replace(minute=0, second=0): p for p in periods}
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    current_hour = now.replace(minute=0, second=0, microsecond=0)

    def hours_for(day_start: datetime) -> list[HourPoint]:
        pts = []
        for h in range(24):
            t = day_start + timedelta(hours=h)
            wx = wx_by_hour.get(t)
            pts.append(
                HourPoint(
                    time=t.isoformat(),
                    hour_label=t.strftime("%-I %p"),
                    tide_ft=tide_by_hour.get(t),
                    air_f=wx["temp_f"] if wx else None,
                    is_daytime=wx["is_daytime"] if wx else None,
                    sky=wx["sky"] if wx else None,
                )
            )
        return pts

    day_start, day_label = today, "Today"
    hours = hours_for(today)
    usable = [h for h in hours if h.is_daytime and datetime.fromisoformat(h.time) >= current_hour]
    if len(usable) < C.BEST_WINDOW_HOURS:
        day_start, day_label = today + timedelta(days=1), "Tomorrow"
        hours = hours_for(day_start)
    note = None if day_label == "Today" else "No daylight hours left today, so this shows tomorrow."

    day_tides = [h.tide_ft for h in hours if h.tide_ft is not None]

    def hour_score(h: HourPoint) -> float | None:
        if not h.is_daytime or h.air_f is None or h.tide_ft is None:
            return None
        if datetime.fromisoformat(h.time) < current_hour:
            return None
        air = max(0.0, 1 - abs(h.air_f - C.IDEAL_AIR_F) / 20)
        frac = tide_fraction(h.tide_ft, day_tides) or 0.0
        mid_tide = 1 - abs(frac - 0.5) * 2
        return 0.45 * air + 0.35 * mid_tide + 0.2 * sky_score(h.sky)

    scores = [hour_score(h) for h in hours]
    n = C.BEST_WINDOW_HOURS
    candidates = []
    for i in range(0, 24 - n + 1):
        block = scores[i : i + n]
        if all(s is not None for s in block):
            candidates.append((sum(block) / n, i))
    candidates.sort(key=lambda c: (-c[0], c[1]))
    chosen: list[tuple[float, int]] = []
    for score, i in candidates:
        if any(abs(i - j) < n for _, j in chosen):
            continue
        if chosen and score < 0.8 * chosen[0][0]:
            break
        chosen.append((score, i))
        if len(chosen) == 2:
            break
    windows = []
    for score, i in sorted(chosen, key=lambda c: c[1]):
        block = hours[i : i + n]
        for h in block:
            h.in_window = True
        start = datetime.fromisoformat(block[0].time)
        end = start + timedelta(hours=n)
        airs = [h.air_f for h in block if h.air_f is not None]
        tides_ft = [h.tide_ft for h in block if h.tide_ft is not None]
        facts = [
            f"Air {min(airs):.0f}–{max(airs):.0f} °F" if min(airs) != max(airs) else f"Air {airs[0]:.0f} °F",
            f"Tide {tides_ft[0]:.1f} to {tides_ft[-1]:.1f} ft (MLLW)",
            f"Sky: {block[0].sky}" if block[0].sky else "Sky: unavailable",
        ]
        windows.append(
            TimeWindow(
                start=start.isoformat(),
                end=end.isoformat(),
                label=f"{start.strftime('%-I %p')}–{end.strftime('%-I %p')}",
                score=round(score, 3),
                facts=facts,
            )
        )
    if not windows and note is None:
        note = "Not enough forecast and tide data to pick a window."
    return BestTime(day_label=day_label, hours=hours, windows=windows, note=note)


def tide_now(tides: list[dict], now: datetime | None = None) -> float | None:
    now = now or datetime.now(UTC)
    best, best_dt = None, timedelta(hours=1)
    for t in tides:
        dt = abs(datetime.fromisoformat(t["time"]) - now)
        if dt <= best_dt:
            best, best_dt = t["ft"], dt
    return best


def data_age_summary(*ages: tuple[str, float | None]) -> str:
    known = [(name, a) for name, a in ages if a is not None]
    if not known:
        return UNAVAILABLE
    name, oldest = max(known, key=lambda x: x[1])
    return f"Oldest: {name}, {oldest:.1f} days"
