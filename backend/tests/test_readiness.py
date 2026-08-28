"""Readiness adjustment. The guarantee under test is that it only ever eases."""

import datetime as dt

import pytest

from planning.generator import Session
from planning.readiness import WellnessSnapshot, apply, assess


def session(kind="INTERVALS", run=30.0, walk=10.0) -> Session:
    return Session(
        date=dt.date(2026, 8, 28), kind=kind, run_minutes=run, walk_minutes=walk,
        target_run_m=4000, purpose="", effort="Controlled hard",
    )


# --- the guarantee ------------------------------------------------------------

@pytest.mark.parametrize(
    "snapshot",
    [
        WellnessSnapshot(readiness=95, sleep_hours=9.0, hrv=60, hrv_baseline=[40] * 14),
        WellnessSnapshot(readiness=88, sleep_hours=8.5),
        WellnessSnapshot(),
    ],
)
def test_good_signals_never_make_a_session_harder(snapshot):
    """An automated system must not talk anyone into more training than planned."""
    original = session()
    result = apply(original, assess(snapshot))

    assert result.run_minutes <= original.run_minutes
    assert result.kind == original.kind


@pytest.mark.parametrize(
    "snapshot",
    [
        WellnessSnapshot(readiness=1),
        WellnessSnapshot(sleep_hours=3.0),
        WellnessSnapshot(hrv=28, hrv_baseline=[42] * 14),
        WellnessSnapshot(pain_reported=True),
        WellnessSnapshot(illness_reported=True),
    ],
)
def test_bad_signals_only_ever_reduce(snapshot):
    original = session()
    result = apply(original, assess(snapshot))
    assert result.run_minutes <= original.run_minutes


# --- gates --------------------------------------------------------------------

def test_pain_drops_the_session_outright():
    adjustment = assess(WellnessSnapshot(pain_reported=True, readiness=95, sleep_hours=9))
    assert adjustment.severity == "critical"
    assert adjustment.drop_session
    # Excellent readiness must not outvote a pain report.
    assert apply(session(), adjustment).kind == "WALK"


def test_illness_drops_the_session_outright():
    assert assess(WellnessSnapshot(illness_reported=True)).drop_session


def test_the_athletes_actual_worst_day_drops_the_session():
    """21-25 Aug: readiness of 1/100 on two consecutive days, sleep of 3 h."""
    adjustment = assess(WellnessSnapshot(readiness=1, sleep_hours=3.1, hrv=33, hrv_baseline=[42] * 14))

    assert adjustment.severity == "critical"
    assert apply(session("LONG", run=45), adjustment).kind == "WALK"
    assert len(adjustment.reasons) >= 3


# --- graded response ----------------------------------------------------------

def test_moderate_readiness_shortens_rather_than_drops():
    adjustment = assess(WellnessSnapshot(readiness=40, sleep_hours=7.5))
    result = apply(session(), adjustment)

    assert adjustment.severity == "caution"
    assert not adjustment.drop_session
    assert 0 < result.run_minutes < 30


def test_an_eased_hard_session_stops_being_a_hard_session():
    """Merely shortening intervals leaves them intervals. Easing must change kind."""
    result = apply(session("INTERVALS"), assess(WellnessSnapshot(readiness=40)))
    assert result.kind == "EASY"


def test_a_short_night_shortens_the_session():
    result = apply(session(), assess(WellnessSnapshot(sleep_hours=5.2)))
    assert result.run_minutes < 30


def test_hrv_is_judged_against_the_athletes_own_baseline():
    """40 ms is unremarkable for one athlete and a red flag for another."""
    normal = assess(WellnessSnapshot(hrv=40, hrv_baseline=[41] * 14))
    dropped = assess(WellnessSnapshot(hrv=40, hrv_baseline=[58] * 14))

    assert normal.severity == "none"
    assert dropped.severity == "critical"


def test_a_thin_hrv_baseline_is_not_used_at_all():
    """Three nights cannot establish a baseline, and pretending otherwise would drop
    sessions on noise."""
    assert assess(WellnessSnapshot(hrv=28, hrv_baseline=[45, 44, 46])).severity == "none"


def test_no_signals_changes_nothing():
    adjustment = assess(WellnessSnapshot())
    assert adjustment.severity == "none"
    assert not adjustment.changed
    assert apply(session(), adjustment) == session()


def test_race_day_is_never_adjusted():
    """A race is a fixed commitment; easing it is not the system's call."""
    race = session("RACE", run=0, walk=0)
    assert apply(race, assess(WellnessSnapshot(readiness=1))) == race


def test_an_eased_session_still_accounts_for_all_its_minutes():
    result = apply(session("LONG", run=40, walk=20), assess(WellnessSnapshot(readiness=40)))
    assert result.run_minutes > 0 and result.walk_minutes > 0
