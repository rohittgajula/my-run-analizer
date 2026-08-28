"""What is any given day *for*?

This runs before the plan generator, and it exists because a training plan anchored
to one date works exactly once. Add a second race and a naive plan slides the whole
ramp onto it — `run-project` produced cutback, peak and taper with **peak week landing
eight days after a race**.

Six modes, and only `build` reads the week table. The others exist because the table
has no row that is right for those days.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Literal

Mode = Literal["race", "recovery", "mini_taper", "maintenance", "build", "off_season"]

# Below this many weeks between two races there is nothing to build. Dropping an
# athlete into weeks_out=3 hands them a peak week on a recovering body.
MIN_BUILD_WEEKS = 4

# A B race gets days of taper where the target gets weeks.
MINI_TAPER_DAYS = {5.0: 2, 10.0: 3, 21.1: 5, 42.2: 7}

KM_PER_MILE = 1.609344


@dataclass(frozen=True)
class Race:
    date: dt.date
    distance_km: float
    is_target: bool = False
    name: str = ""


@dataclass(frozen=True)
class ModeResult:
    mode: Mode
    race: Race | None = None          # the race this day relates to
    weeks_out: int | None = None      # only meaningful in `build`
    days_to_race: int | None = None
    note: str = ""


def recovery_days(distance_km: float) -> int:
    """Roughly one day per mile, rounded UP.

    Rounding down puts a 10K's window at six days, which hands straight over to a
    long run with no easing step.
    """
    return math.ceil(distance_km / KM_PER_MILE)


def mini_taper_days(distance_km: float) -> int:
    for limit, days in sorted(MINI_TAPER_DAYS.items()):
        if distance_km <= limit + 0.5:
            return days
    return 7


def _anchor(day: dt.date, races: list[Race]) -> Race | None:
    """The race the ramp counts down to.

    Falls back to the next race once the target is past. Without that fallback a
    passed race leaves weeks_out clamped at 0 and the plan prescribes race week
    forever — a real bug, not a hypothetical.
    """
    upcoming = sorted((r for r in races if r.date >= day), key=lambda r: r.date)
    if not upcoming:
        return None
    for race in upcoming:
        if race.is_target:
            return race
    return upcoming[0]


def resolve_mode(day: dt.date, races: list[Race]) -> ModeResult:
    if not races:
        return ModeResult("off_season", note="No races on the calendar.")

    ordered = sorted(races, key=lambda r: r.date)

    # 1. Race day itself.
    for race in ordered:
        if race.date == day:
            return ModeResult("race", race=race, days_to_race=0)

    # 2. Recovery from the most recent race takes precedence over everything after
    #    it. A build day inside a recovery window is the failure this prevents.
    past = [r for r in ordered if r.date < day]
    if past:
        last = past[-1]
        window = recovery_days(last.distance_km)
        elapsed = (day - last.date).days
        if elapsed <= window:
            return ModeResult(
                "recovery", race=last,
                note=f"Day {elapsed} of {window} after {last.distance_km:g} km.",
            )

    upcoming = [r for r in ordered if r.date > day]
    if not upcoming:
        return ModeResult("off_season", note="No races left on the calendar.")

    next_race = upcoming[0]
    days_to_next = (day - next_race.date).days * -1

    # 3. A B race gets days of taper, and does not move the ramp.
    if not next_race.is_target and days_to_next <= mini_taper_days(next_race.distance_km):
        return ModeResult(
            "mini_taper", race=next_race, days_to_race=days_to_next,
            note=f"Short taper into a {next_race.distance_km:g} km B race.",
        )

    anchor = _anchor(day, races)
    if anchor is None:
        return ModeResult("off_season")

    days_to_anchor = (anchor.date - day).days
    weeks_to_anchor = days_to_anchor / 7

    # 4. Too close to the anchor to build anything. Hold, rather than re-entering a
    #    ramp that would peak on a body still recovering from the last race.
    if weeks_to_anchor < MIN_BUILD_WEEKS:
        # Only "too short to build" when a race already happened; a first race with
        # a short run-up is a compressed build, not maintenance.
        if past:
            return ModeResult(
                "maintenance", race=anchor, days_to_race=days_to_anchor,
                note=(
                    f"{weeks_to_anchor:.1f} weeks to the next race — under "
                    f"{MIN_BUILD_WEEKS}, so holding rather than rebuilding."
                ),
            )

    # 5. Building towards the anchor. weeks_out counts down: 0 is race week.
    return ModeResult(
        "build", race=anchor,
        weeks_out=max(int(weeks_to_anchor), 0),
        days_to_race=days_to_anchor,
        note=f"Building towards {anchor.name or f'{anchor.distance_km:g} km'}.",
    )


def resolve_range(start: dt.date, end: dt.date, races: list[Race]) -> list[tuple[dt.date, ModeResult]]:
    """Every day in [start, end]. Used by the calendar view and by the tests."""
    days = (end - start).days
    return [
        (start + dt.timedelta(days=offset), resolve_mode(start + dt.timedelta(days=offset), races))
        for offset in range(days + 1)
    ]
