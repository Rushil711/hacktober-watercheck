"""Output schemas for each Gemma skill. Every reply is validated against these."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Explanation(_Out):
    headline: str = Field(min_length=3, max_length=160)
    environmental_summary: str = Field(min_length=10, max_length=900)
    key_observations: list[str] = Field(max_length=6)
    concerns: list[str] = Field(max_length=6)
    limitations: list[str] = Field(max_length=6)
    recommended_next_steps: list[str] = Field(max_length=6)
    sources_used: list[str] = Field(max_length=8)


class FeelVerdict(_Out):
    level: str
    verdict: str = Field(min_length=2, max_length=60)
    reason: str = Field(min_length=5, max_length=240)


class Verdicts(_Out):
    swim_feel: FeelVerdict
    jump_feel: FeelVerdict


class WindowReason(_Out):
    label: str
    reason: str = Field(min_length=5, max_length=240)


class BestHours(_Out):
    windows: list[WindowReason] = Field(min_length=1, max_length=2)


class NaturalFilter(_Out):
    max_drive_min: Literal[15, 30, 60]
    min_temp_f: float | None = Field(default=None, ge=40, le=90)
    activity: Literal["swim", "jump", "any"] = "any"
    near: str | None = Field(default=None, max_length=120)
