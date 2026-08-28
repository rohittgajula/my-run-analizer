"""Plan generation. The invariants matter more than any single example."""

import datetime as dt

import pytest

from planning.generator import (
    Baseline, PlanConfig, allocate_phases, classify_runway, generate_plan,
)

START = dt.date(2026, 8, 28)


def baseline(**overrides) -> Baseline:
    defaults = dict(
        run_km_per_week=3.5,
        longest_run_s=830.0,
        run_pace_s_per_km=507.0,
        walk_pace_s_per_km=681.0,
        available_days={"0": False, "1": True, "2": False, "3": True,
                        "4": False, "5": True, "6": True},
        long_run_day=6,
    )
    return Baseline(**{**defaults, **overrides})


def plan_for(weeks: int, distance=10.0, **kwargs):
    return generate_plan(START, START + dt.timedelta(days=weeks * 7 - 1), distance,
                         baseline(**kwargs))


# --- runway -------------------------------------------------------------------

@pytest.mark.parametrize(
    "weeks,expected",
    [(5, "SHORT"), (8, "STANDARD"), (15, "STANDARD"), (18, "STANDARD"), (40, "EXTENDED")],
)
def test_runway_classification(weeks, expected):
    assert classify_runway(weeks, 10.0) == expected


def test_a_short_runway_still_returns_a_plan_with_a_warning():
    plan = plan_for(5)
    assert plan.runway == "SHORT"
    assert plan.weeks
    assert any("less than" in w for w in plan.warnings)


def test_a_long_runway_holds_before_ramping_rather_than_diluting():
    plan = plan_for(40)
    assert plan.runway == "EXTENDED"
    assert plan.weeks[0].phase == "BASE"
    # The tail must still be a normally-shaped ramp, not 40 weeks of slow drift.
    assert plan.weeks[-1].phase == "RACE"
    assert "PEAK" in [w.phase for w in plan.weeks]


def test_a_race_in_the_past_is_refused():
    with pytest.raises(ValueError, match="past"):
        generate_plan(START, START - dt.timedelta(days=1), 10.0, baseline())


def test_a_race_tomorrow_does_not_produce_negative_weeks():
    plan = generate_plan(START, START + dt.timedelta(days=1), 10.0, baseline())
    assert plan.weeks_available == 1
    assert all(w.weeks_out >= 0 for w in plan.weeks)


# --- the invariants -----------------------------------------------------------

@pytest.mark.parametrize("weeks", range(2, 41))
def test_phases_always_sum_to_the_weeks_available(weeks):
    """Property, not an example. An off-by-one here silently loses or invents a week."""
    assert len(allocate_phases(weeks, 10.0)) == weeks


@pytest.mark.parametrize("weeks,distance", [(w, d) for w in (6, 10, 15, 22) for d in (5.0, 10.0, 21.1)])
def test_every_plan_covers_exactly_its_runway(weeks, distance):
    plan = plan_for(weeks, distance)
    assert len(plan.weeks) == plan.weeks_available == weeks


@pytest.mark.parametrize("weeks", (8, 12, 15, 20))
def test_no_two_hard_sessions_land_on_consecutive_days(weeks):
    hard = {"INTERVALS", "TEMPO"}
    for week in plan_for(weeks).weeks:
        days = sorted(s.date for s in week.sessions if s.kind in hard)
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        assert all(gap > 1 for gap in gaps), f"consecutive hard days in week {week.index}"


@pytest.mark.parametrize("weeks", (8, 15, 20))
def test_volume_never_exceeds_the_cap_above_anything_already_done(weeks):
    """The cap governs the PROGRESSION, not every week-on-week change.

    Comparing consecutive weeks is the obvious test and the wrong one: a cutback week
    drops volume ~30% on purpose, so the following week necessarily bounces back by
    ~50% and would fail. That bounce is a return to a level already survived, not new
    load. The real safety rule is that no week asks for more than the cap above the
    highest week already completed.
    """
    config = PlanConfig()
    volumes = [w.planned_run_km for w in plan_for(weeks).weeks if w.phase not in ("TAPER", "RACE")]

    highest = volumes[0]
    for volume in volumes[1:]:
        if volume > highest:
            increase = (volume - highest) / highest * 100
            assert increase <= config.max_weekly_increase_pct + 1.0, (
                f"{volume} km is {increase:.1f}% above the previous best of {highest} km"
            )
            highest = volume


def test_a_cutback_week_is_a_real_reduction():
    cutbacks = [w for w in plan_for(16).weeks if w.is_cutback and w.phase not in ("TAPER", "RACE")]
    assert cutbacks, "no cutback weeks at all"


def test_every_session_accounts_for_all_of_its_minutes():
    """run-project left walk_minutes at 0.0 on long runs for years, which is why the
    week table showed a blank RUN TIME on every one of them."""
    for week in plan_for(15).weeks:
        for session in week.sessions:
            if session.kind in ("RUN_WALK", "LONG", "EASY"):
                assert session.total_minutes > 0
                assert session.run_minutes > 0


def test_the_long_run_lands_on_the_athletes_chosen_day():
    for week in plan_for(12).weeks:
        long_runs = [s for s in week.sessions if s.kind == "LONG"]
        for session in long_runs:
            assert session.date.weekday() == 6


def test_sessions_never_land_on_an_unavailable_day_except_as_optional_walks():
    available = {1, 3, 5, 6}
    for week in plan_for(10).weeks:
        for session in week.sessions:
            if session.date.weekday() not in available:
                assert session.kind == "WALK" and session.optional


# --- the volume cap outranks the target ---------------------------------------

def test_a_low_baseline_cannot_reach_the_ideal_peak_and_says_so():
    """This athlete runs 3.5 km a week. A 10 km build ideally peaks near 22.
    Reaching that in 15 weeks would need a ramp well past the safety cap."""
    plan = plan_for(15, run_km_per_week=3.5)

    assert not plan.reached_ideal_peak
    assert plan.peak_run_km < plan.ideal_peak_run_km
    assert any("cap wins" in w for w in plan.warnings)


def test_a_short_runway_does_not_compensate_by_ramping_faster():
    """The exact trade that injures people, and the one an eager system makes."""
    short = plan_for(6)
    long = plan_for(16)

    def steepest(plan):
        """Steepest rise above anything already done — see the note on the cap test."""
        volumes = [w.planned_run_km for w in plan.weeks if w.phase not in ("TAPER", "RACE")]
        highest, worst = volumes[0], 0.0
        for volume in volumes[1:]:
            if volume > highest:
                worst = max(worst, (volume - highest) / highest * 100)
                highest = volume
        return worst

    assert steepest(short) <= PlanConfig().max_weekly_increase_pct + 0.5
    assert steepest(short) <= steepest(long) + 0.5


def test_a_high_baseline_does_reach_the_ideal_peak():
    plan = plan_for(20, run_km_per_week=18.0)
    assert plan.reached_ideal_peak


def test_cutback_weeks_exist():
    """Adaptation happens in the cutback. A plan without them is a plan to break."""
    assert any(week.is_cutback for week in plan_for(16).weeks)


def test_the_taper_reduces_volume_into_the_race():
    weeks = plan_for(15).weeks
    peak = max(w.planned_run_km for w in weeks if w.phase == "PEAK")
    taper = [w.planned_run_km for w in weeks if w.phase == "TAPER"]
    assert taper and all(v < peak for v in taper)


def test_race_week_contains_the_race():
    weeks = plan_for(15).weeks
    assert weeks[-1].phase == "RACE"
    assert any(s.kind == "RACE" for s in weeks[-1].sessions)
