"""Race calendar resolution.

The case that matters is two races three weeks apart: `run-project` slid the whole
ramp onto the second and produced peak week eight days after a race.
"""

import datetime as dt

import pytest

from planning.calendar import (
    MIN_BUILD_WEEKS, Race, mini_taper_days, recovery_days, resolve_mode, resolve_range,
)

TARGET = Race(dt.date(2026, 12, 13), 10.0, is_target=True, name="Pune 10K")
SECOND = Race(dt.date(2027, 1, 3), 10.0, name="January 10K")
BOTH = [TARGET, SECOND]


def mode_on(day: dt.date, races=BOTH) -> str:
    return resolve_mode(day, races).mode


# --- the real calendar --------------------------------------------------------

@pytest.mark.parametrize(
    "day,expected",
    [
        (dt.date(2026, 11, 30), "build"),        # counting down to the A race
        (dt.date(2026, 12, 12), "build"),
        (dt.date(2026, 12, 13), "race"),         # Pune
        (dt.date(2026, 12, 14), "recovery"),
        (dt.date(2026, 12, 19), "recovery"),     # 10 km -> 7 days, rounded up
        (dt.date(2026, 12, 20), "recovery"),
        (dt.date(2026, 12, 21), "maintenance"),  # under MIN_BUILD_WEEKS to Jan 3
        (dt.date(2026, 12, 30), "maintenance"),
        (dt.date(2026, 12, 31), "mini_taper"),   # 3 days for a 10 km B race
        (dt.date(2027, 1, 2), "mini_taper"),
        (dt.date(2027, 1, 3), "race"),           # January
        (dt.date(2027, 1, 4), "recovery"),
        (dt.date(2027, 1, 11), "off_season"),    # nothing left
    ],
)
def test_the_dec13_jan3_calendar(day, expected):
    assert mode_on(day) == expected


def test_no_build_day_falls_inside_a_recovery_window():
    """The invariant. A build day inside recovery is the bug this module prevents."""
    for day, result in resolve_range(dt.date(2026, 12, 1), dt.date(2027, 2, 1), BOTH):
        if result.mode == "build":
            for race in BOTH:
                if race.date < day:
                    assert (day - race.date).days > recovery_days(race.distance_km), (
                        f"{day} is building inside recovery from {race.date}"
                    )


def test_peak_week_never_lands_just_after_a_race():
    """weeks_out <= 1 is peak/race week. It must not appear days after a race."""
    for day, result in resolve_range(dt.date(2026, 12, 13), dt.date(2027, 1, 3), BOTH):
        if result.mode == "build" and (result.weeks_out or 99) <= 1:
            days_since_pune = (day - TARGET.date).days
            assert not (0 < days_since_pune < 21), f"peak week on {day}"


# --- the B race does not move the ramp ----------------------------------------

def test_the_second_race_does_not_pull_the_ramp_onto_itself():
    november = dt.date(2026, 11, 15)
    with_second = resolve_mode(november, BOTH)
    without = resolve_mode(november, [TARGET])

    assert with_second.mode == without.mode == "build"
    assert with_second.race == without.race == TARGET
    assert with_second.weeks_out == without.weeks_out


def test_the_gap_between_close_races_holds_rather_than_rebuilding():
    result = resolve_mode(dt.date(2026, 12, 23), BOTH)
    assert result.mode == "maintenance"
    assert str(MIN_BUILD_WEEKS) in result.note


# --- anchor fallback ----------------------------------------------------------

def test_the_anchor_moves_on_once_the_target_is_past():
    """Without this, a passed race leaves weeks_out clamped at 0 and the plan
    prescribes race week forever."""
    far_second = Race(dt.date(2027, 4, 4), 10.0)
    result = resolve_mode(dt.date(2027, 1, 15), [TARGET, far_second])

    assert result.mode == "build"
    assert result.race == far_second
    assert result.weeks_out and result.weeks_out > 0


def test_no_races_is_off_season_not_a_crash():
    assert resolve_mode(dt.date(2026, 9, 1), []).mode == "off_season"


def test_everything_in_the_past_is_off_season():
    assert mode_on(dt.date(2027, 6, 1)) == "off_season"


# --- windows ------------------------------------------------------------------

def test_recovery_rounds_up():
    """6.2 miles rounding down gives a six-day window that hands straight over to a
    long run with no easing step."""
    assert recovery_days(10.0) == 7
    assert recovery_days(21.1) == 14
    assert recovery_days(42.2) == 27


def test_a_b_race_gets_days_of_taper_where_the_target_gets_weeks():
    assert mini_taper_days(5.0) == 2
    assert mini_taper_days(10.0) == 3
    assert mini_taper_days(42.2) == 7


def test_a_first_race_with_a_short_runup_still_builds():
    """Compressed, not maintenance — there is no previous race to recover from."""
    soon = Race(dt.date(2026, 9, 20), 10.0, is_target=True)
    assert resolve_mode(dt.date(2026, 9, 1), [soon]).mode == "build"
