"""Pydantic models that ARE the API schema.

One definition, three jobs: it generates the schema sent to OpenAI, validates what
comes back, and types the rest of the code.

Written for OpenAI's strict Structured Outputs, which requires every field to be
`required` and every object to set `additionalProperties: false`. Optionality is
therefore expressed as a union with `None`, never as a field with a default — a
default would be silently dropped from the schema and the model would be free to
omit the field entirely.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """One thing the data shows, and what it means for the athlete.

    Split deliberately into three parts. `finding` must be traceable to a number the
    system actually holds; `meaning` is interpretation; `action` is what to do. Fusing
    them is how a plausible-sounding sentence smuggles in an invented figure.
    """

    model_config = {"extra": "forbid"}

    topic: str = Field(description="Short label, e.g. 'Longest continuous run'.")
    finding: str = Field(description="What the data shows. Cite the number given to you.")
    meaning: str = Field(description="What it means for this athlete's goal.")
    action: str | None = Field(description="What to do about it, or null if nothing.")


class Guidance(BaseModel):
    """The coaching read on where the athlete stands."""

    model_config = {"extra": "forbid"}

    headline: str = Field(description="One sentence. The single most important thing right now.")
    doing_well: list[Observation]
    to_improve: list[Observation]
    stamina: str = Field(
        description="Concretely how to build endurance from where this athlete actually is."
    )
    cautions: list[str] = Field(
        description="Risks in the data. Empty list if none — do not invent one."
    )
    confidence: float = Field(ge=0.0, le=1.0)


class RecoveryAdvice(BaseModel):
    model_config = {"extra": "forbid"}

    level: Literal["LOW", "MODERATE", "HIGH"]
    reason: str


class RunAnalysis(BaseModel):
    """One run, interpreted."""

    model_config = {"extra": "forbid"}

    summary: str = Field(description="Two or three sentences on what happened.")
    what_went_well: list[str]
    observations: list[str]
    possible_explanations: list[str] = Field(
        description="Why the numbers may look as they do — heat, terrain, sleep, "
        "sensor error. Not conclusions."
    )
    concerns: list[str] = Field(description="Empty list if none.")
    recovery: RecoveryAdvice
    next_focus: str = Field(description="What to concentrate on in the next session.")
    confidence: float = Field(ge=0.0, le=1.0)


class WeeklyReview(BaseModel):
    model_config = {"extra": "forbid"}

    status: Literal["ON_TRACK", "UNDER_LOADED", "OVER_LOADED", "FATIGUED", "RECOVERING", "ANOMALOUS"]
    summary: str
    progress: list[Observation]
    risks: list[str]
    next_week_focus: str
    confidence: float = Field(ge=0.0, le=1.0)


class JournalFacts(BaseModel):
    """Structured facts extracted from a free-text log entry."""

    model_config = {"extra": "forbid"}

    rpe: int | None = Field(description="Perceived effort 1-10, or null if not mentioned.")
    energy: int | None = Field(description="1-10, or null.")
    leg_fatigue: int | None = Field(description="1-10, or null.")
    sleep_quality: int | None = Field(description="1-10, or null.")
    pain_reported: bool
    pain_location: str | None
    pain_severity: int | None = Field(description="1-5, or null.")
    illness_reported: bool
    notes_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
