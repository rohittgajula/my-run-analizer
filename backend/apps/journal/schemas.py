"""Chat schema.

Extraction and reply are one call rather than two: two calls cost twice as much and
let the reply drift from the facts it is supposedly based on.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class ChatFacts(BaseModel):
    model_config = {"extra": "forbid"}

    applies_to_date: dt.date = Field(
        description="Which day's SESSION this bears on. Usually today. "
        "'I slept badly last night' written in the morning is about TODAY."
    )
    rpe: int | None = Field(description="Perceived effort 1-10 if stated, else null.")
    energy: int | None = Field(description="1-10 if stated, else null.")
    leg_fatigue: int | None = Field(description="1-10 if stated, else null.")
    sleep_quality: int | None = Field(description="1-10 if stated, else null.")
    pain_reported: bool = Field(description="Only if pain or injury is actually mentioned.")
    pain_location: str | None
    pain_severity: int | None = Field(description="1-5 if inferable, else null.")
    illness_reported: bool
    distance_mentioned_km: float | None = Field(description="Only if they stated a distance.")
    notes_summary: str = Field(description="One line, in plain English.")
    confidence: float = Field(ge=0.0, le=1.0)


class ChatTurn(BaseModel):
    model_config = {"extra": "forbid"}

    facts: ChatFacts
    reply: str = Field(
        description="Your reply to the athlete. Acknowledge, answer any question, be "
        "specific to their numbers. Do NOT state whether to train, rest or change a "
        "session — that is appended separately."
    )
