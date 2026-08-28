"""Turning wellness signals into a same-day session adjustment.

**These rules only ever make a session easier.** That is not a style preference: an
automated system must not talk someone into more training than the plan already
prescribed, and every rule here is written so the worst case is an unnecessary rest
day rather than an avoidable injury.

Deliberately deterministic, and deliberately Python. The model reads language and
produces facts; what follows from a fact is decided here, where a hallucination
cannot reach it. That is also what keeps the "only ever easier" guarantee real.

Thresholds are conservative choices open to review, not universal laws.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Literal

from .generator import Session

Severity = Literal["none", "caution", "critical"]

# Garmin's own readiness score. Below CRITICAL the athlete is not recovered in any
# useful sense — this athlete hit 1/100 on two consecutive days in August.
READINESS_CRITICAL = 25
READINESS_CAUTION = 45

SLEEP_CRITICAL_H = 4.5
SLEEP_CAUTION_H = 6.0

# A drop against the athlete's own recent baseline, not an absolute number. HRV is
# only meaningful relative to yourself.
HRV_DROP_CAUTION_PCT = 12.0
HRV_DROP_CRITICAL_PCT = 22.0

MIN_HRV_BASELINE_DAYS = 7


@dataclass(frozen=True)
class WellnessSnapshot:
    readiness: int | None = None
    sleep_hours: float | None = None
    hrv: int | None = None
    hrv_baseline: list[int] = field(default_factory=list)
    resting_hr: int | None = None
    resting_hr_baseline: list[int] = field(default_factory=list)
    # Subjective, from the journal. Overrides everything else when present — see M4.
    pain_reported: bool = False
    illness_reported: bool = False


@dataclass
class Adjustment:
    severity: Severity
    scale: float                       # multiplier applied to the session
    reasons: list[str] = field(default_factory=list)
    drop_session: bool = False

    @property
    def changed(self) -> bool:
        return self.drop_session or self.scale < 0.999


def _mean(values: list[int]) -> float | None:
    return statistics.mean(values) if values else None


def assess(snapshot: WellnessSnapshot) -> Adjustment:
    reasons: list[str] = []
    severity: Severity = "none"
    scale = 1.0
    drop = False

    def escalate(level: Severity):
        nonlocal severity
        order = {"none": 0, "caution": 1, "critical": 2}
        if order[level] > order[severity]:
            severity = level

    # Pain and illness are gates, not inputs to a score. Nothing else can outvote them.
    if snapshot.pain_reported:
        reasons.append("You reported pain. Nothing here progresses until that settles.")
        escalate("critical")
        drop = True
    if snapshot.illness_reported:
        reasons.append("You reported feeling unwell. Training through it is not worth it.")
        escalate("critical")
        drop = True

    if snapshot.readiness is not None:
        if snapshot.readiness <= READINESS_CRITICAL:
            reasons.append(
                f"Training readiness {snapshot.readiness}/100 — your body has not recovered. "
                "Rest or walk today."
            )
            escalate("critical")
            scale = min(scale, 0.0)
            drop = True
        elif snapshot.readiness <= READINESS_CAUTION:
            reasons.append(
                f"Training readiness {snapshot.readiness}/100 — enough for something easy, "
                "not for a hard session."
            )
            escalate("caution")
            scale = min(scale, 0.7)

    if snapshot.sleep_hours is not None:
        if snapshot.sleep_hours < SLEEP_CRITICAL_H:
            reasons.append(
                f"{snapshot.sleep_hours:.1f} h of sleep. Short nights raise injury risk more "
                "than a missed session costs you."
            )
            escalate("critical")
            scale = min(scale, 0.5)
        elif snapshot.sleep_hours < SLEEP_CAUTION_H:
            reasons.append(f"{snapshot.sleep_hours:.1f} h of sleep — shorten today rather than push.")
            escalate("caution")
            scale = min(scale, 0.75)

    baseline = _mean(snapshot.hrv_baseline)
    if (
        snapshot.hrv is not None
        and baseline
        and len(snapshot.hrv_baseline) >= MIN_HRV_BASELINE_DAYS
    ):
        drop_pct = (baseline - snapshot.hrv) / baseline * 100
        if drop_pct >= HRV_DROP_CRITICAL_PCT:
            reasons.append(
                f"HRV {snapshot.hrv} ms is {drop_pct:.0f}% below your {len(snapshot.hrv_baseline)}-day "
                "average — a large drop usually means poor sleep, alcohol or accumulated fatigue."
            )
            escalate("critical")
            scale = min(scale, 0.5)
        elif drop_pct >= HRV_DROP_CAUTION_PCT:
            reasons.append(f"HRV {drop_pct:.0f}% below your recent average. Keep today easy.")
            escalate("caution")
            scale = min(scale, 0.8)

    return Adjustment(severity=severity, scale=max(scale, 0.0), reasons=reasons, drop_session=drop)


# What each session becomes when it is eased. A hard session never survives an easing
# as a hard session — it changes kind, rather than merely getting shorter.
_SOFTENED = {"INTERVALS": "EASY", "TEMPO": "EASY", "LONG": "RUN_WALK", "EASY": "RUN_WALK"}


def apply(session: Session, adjustment: Adjustment) -> Session:
    """Return the eased session. Never returns anything harder than the input."""
    if not adjustment.changed or session.kind == "RACE":
        return session

    if adjustment.drop_session or adjustment.scale == 0.0:
        return Session(
            date=session.date, kind="WALK",
            run_minutes=0.0, walk_minutes=min(session.total_minutes, 30.0),
            target_run_m=0.0,
            purpose="Dropped for recovery. Movement only.",
            effort="Very easy",
            optional=False,
        )

    kind = _SOFTENED.get(session.kind, session.kind)
    # Both halves are rescaled, so the session still accounts for all of its minutes.
    return Session(
        date=session.date,
        kind=kind,
        run_minutes=round(session.run_minutes * adjustment.scale, 1),
        walk_minutes=round(session.walk_minutes * adjustment.scale, 1),
        target_run_m=round(session.target_run_m * adjustment.scale),
        purpose=session.purpose,
        effort="Easier than planned — see why below",
        optional=session.optional,
    )
