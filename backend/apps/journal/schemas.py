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
        description="The day this is ABOUT. For a run already done, the day of that "
        "run. For how they are feeling now, today."
    )
    describes_completed_run: bool = Field(
        description="True if they describe a run that has ALREADY happened "
        "('ran 3k this morning', 'yesterday's run felt hard'). False if they are "
        "describing how they feel, asking a question, or talking about a run still "
        "to come. This decides whether the consequences land on today's session or "
        "the next one."
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
