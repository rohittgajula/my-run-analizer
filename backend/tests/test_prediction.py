"""Finish-time prediction. The gate matters more than the number."""

import datetime as dt

import pytest

from planning.prediction import MIN_RUNS, MIN_SPAN_WEEKS, RunSummary, predict

TODAY = dt.date(2026, 8, 28)
RACE = dt.date(2026, 12, 13)


def run(days_ago: int, *, longest_s=300.0, run_m=1000.0, walk_m=1500.0, pace=450.0):
    return RunSummary(
        date=TODAY - dt.timedelta(days=days_ago),
        run_distance_m=run_m, walk_distance_m=walk_m,
        run_duration_s=run_m / 1000 * pace, walk_duration_s=walk_m / 1000 * 700,
        longest_run_s=longest_s, run_pace_s_per_km=pace, walk_pace_s_per_km=700.0,
    )


def history(count: int, span_days: int, **kwargs):
    step = span_days / max(count - 1, 1)
    return [run(int(span_days - i * step), **kwargs) for i in range(count)]


# --- the gate -----------------------------------------------------------------

def test_no_runs_predicts_nothing():
    result = predict([], RACE, 10.0, TODAY)
    assert result.mode == "INSUFFICIENT_DATA"
    assert result.likely_finish_s is None


def test_too_few_runs_predicts_nothing():
    result = predict(history(5, 40), RACE, 10.0, TODAY)
    assert result.mode == "INSUFFICIENT_DATA"
    assert "more run" in " ".join(result.what_would_change_it)


def test_enough_runs_but_too_short_a_span_predicts_nothing():
    """Eight runs in a week says nothing about a trend."""
    result = predict(history(8, 7), RACE, 10.0, TODAY)
    assert result.mode == "INSUFFICIENT_DATA"
    assert "week" in " ".join(result.what_would_change_it)


def test_the_gate_opens_at_the_threshold():
    result = predict(history(MIN_RUNS, int(MIN_SPAN_WEEKS * 7) + 1), RACE, 10.0, TODAY)
    assert result.mode != "INSUFFICIENT_DATA"
    assert result.likely_finish_s


# --- shape of the answer ------------------------------------------------------

def test_the_range_brackets_the_estimate():
    result = predict(history(12, 40), RACE, 10.0, TODAY)
    low, high = result.range_s
    assert low < result.likely_finish_s < high
    assert low > 0


def test_more_observations_never_widen_the_range():
    """A property, not an example: data should only ever increase certainty."""
    narrow = predict(history(30, 60), RACE, 10.0, TODAY)
    wide = predict(history(9, 60), RACE, 10.0, TODAY)

    def width(p):
        return (p.range_s[1] - p.range_s[0]) / p.likely_finish_s

    assert width(narrow) <= width(wide)


def test_a_beginner_who_walks_most_of_it_gets_a_run_walk_prediction():
    result = predict(history(10, 40, longest_s=300, run_m=900, walk_m=1600), RACE, 10.0, TODAY)
    assert result.mode == "RUN_WALK"
    assert result.projected_run_fraction is not None


def test_someone_who_can_already_run_the_distance_gets_a_continuous_prediction():
    """Capacity must clear the race by CONTINUOUS_MARGIN, not merely reach it.

    75 min at 6:40/km is 11.2 km of capacity for a 10 km race. A 60-minute block
    at the same pace is only 9 km, and predicting a continuous 10 km off that
    would be optimism dressed as arithmetic.
    """
    result = predict(
        history(12, 60, longest_s=4500, run_m=11000, walk_m=200, pace=400),
        RACE, 10.0, TODAY,
    )
    assert result.mode == "CONTINUOUS"


def test_capacity_that_merely_reaches_the_distance_is_still_run_walk():
    result = predict(
        history(12, 60, longest_s=3600, run_m=9000, walk_m=200, pace=400),
        RACE, 10.0, TODAY,
    )
    assert result.mode == "RUN_WALK"


def test_improvement_projects_a_longer_block_than_today():
    improving = [
        run(60 - i * 6, longest_s=200 + i * 40) for i in range(10)
    ]
    result = predict(improving, RACE, 10.0, TODAY)
    assert result.projected_longest_run_s > improving[-1].longest_run_s


def test_projection_saturates_rather_than_extrapolating_forever():
    """An undamped line would extrapolate a beginner to a marathon."""
    improving = [run(60 - i * 6, longest_s=200 + i * 60) for i in range(10)]
    result = predict(improving, dt.date(2028, 1, 1), 10.0, TODAY)

    # 70 weeks of naive extrapolation would be absurd; saturation caps the gain.
    assert result.projected_longest_run_s < 200 + 60 * 10 * 4


def test_a_flat_history_does_not_predict_improvement():
    result = predict(history(12, 60, longest_s=300), RACE, 10.0, TODAY)
    assert result.projected_longest_run_s == pytest.approx(300, abs=30)


def test_pace_is_never_projected_faster_than_a_plausible_ceiling():
    """A fit on a falling series can run away; the floor stops it."""
    quickening = [run(60 - i * 6, pace=600 - i * 25) for i in range(10)]
    result = predict(quickening, dt.date(2027, 12, 1), 10.0, TODAY)
    assert result.likely_finish_s > 0


def test_a_race_today_still_answers():
    result = predict(history(12, 40), TODAY, 10.0, TODAY)
    assert result.likely_finish_s and result.likely_finish_s > 0


# --- credibility bounds -------------------------------------------------------

def test_a_run_walk_finish_is_never_slower_than_walking_it():
    """This failed on real data and produced a four-hour 10K.

    Someone whose running is slower than their walking simply walks, so any model
    output past that bound is arithmetic that has stopped describing reality.
    """
    slow = [
        run(60 - i * 6, longest_s=200, run_m=600, walk_m=1900, pace=640)
        for i in range(10)
    ]
    result = predict(slow, RACE, 10.0, TODAY)

    walk_the_whole_thing = 10.0 * 700.0   # walk_pace in the fixture
    assert result.likely_finish_s <= walk_the_whole_thing + 1


def test_a_finish_is_never_faster_than_the_best_pace_ever_run():
    result = predict(history(12, 40, pace=450), RACE, 10.0, TODAY)
    assert result.likely_finish_s >= 10.0 * 450


def test_deliberately_slowing_down_to_run_longer_is_not_read_as_decline():
    """The real pattern in this athlete's data: pace fell from 8:11 to 10:40/km
    while the longest block went 4.8 -> 13.9 min. A pace trend fit reads that as
    getting worse and projects him slower still."""
    trading_pace_for_duration = [
        run(60 - i * 6, longest_s=250 + i * 60, pace=490 + i * 20) for i in range(10)
    ]
    result = predict(trading_pace_for_duration, RACE, 10.0, TODAY)

    # Capacity improving is what should drive the answer.
    assert result.projected_longest_run_s > trading_pace_for_duration[-1].longest_run_s
    # And the finish must stay inside the walk bound regardless.
    assert result.likely_finish_s <= 10.0 * 700.0 + 1
