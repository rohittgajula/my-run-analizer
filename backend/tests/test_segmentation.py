"""Segmentation and the metrics built on it. No database, no Django."""

import pytest

from analysis.heart_rate import hr_drift_percent
from analysis.load import LOAD_FORMULA_VERSION, session_load
from analysis.running_truth import summarise
from analysis.segmentation import (
    MIN_SEGMENT_S, NotSegmentable, Sample, cadence_coverage, check_segmentable,
    classify, segment_samples,
)


def series(spec, *, hr=None, start=0.0, speed=2.0):
    """Build samples from [(seconds, cadence, metres_per_second), ...]."""
    samples, offset, distance = [], start, 0.0
    for seconds, cadence, mps in spec:
        for _ in range(int(seconds)):
            distance += mps
            samples.append(Sample(offset_s=offset, distance_m=distance,
                                  speed_mps=mps or speed, cadence_spm=cadence,
                                  heart_rate=hr))
            offset += 1
    return samples


# --- classification -----------------------------------------------------------

def test_cadence_separates_a_slow_jog_from_a_brisk_walk():
    """The whole reason this keys on cadence: these two overlap in speed."""
    jog = Sample(offset_s=0, cadence_spm=150, speed_mps=1.9)
    walk = Sample(offset_s=0, cadence_spm=118, speed_mps=1.9)

    assert classify(jog, 140) == "run"
    assert classify(walk, 140) == "walk"


def test_the_threshold_is_per_athlete():
    sample = Sample(offset_s=0, cadence_spm=145, speed_mps=2.0)
    assert classify(sample, 140) == "run"
    assert classify(sample, 150) == "walk"


def test_standing_still_is_a_stop_not_a_walk():
    assert classify(Sample(offset_s=0, cadence_spm=0, speed_mps=0.0), 140) == "stop"


# --- the gate -----------------------------------------------------------------

def test_cycling_is_refused_rather_than_mis_segmented():
    """Cycling cadence is pedal revolutions. Segmenting it would produce a confident
    wrong answer, which is worse than no answer."""
    samples = series([(60, 85, 6.0)])
    with pytest.raises(NotSegmentable, match="not a foot sport"):
        check_segmentable("cycling", samples)


def test_an_activity_without_a_cadence_sensor_is_refused():
    samples = [Sample(offset_s=float(i), speed_mps=2.0) for i in range(200)]
    assert cadence_coverage(samples) == 0.0
    with pytest.raises(NotSegmentable, match="cadence"):
        check_segmentable("running", samples)


def test_a_very_short_activity_is_refused():
    with pytest.raises(NotSegmentable, match="too short"):
        check_segmentable("running", series([(10, 160, 2.5)]))


def test_a_normal_run_passes_the_gate():
    check_segmentable("running", series([(300, 160, 2.5)]))


# --- block detection ----------------------------------------------------------

def test_alternating_run_and_walk_produces_the_right_blocks():
    samples = series([(90, 165, 2.2), (120, 115, 1.4), (90, 165, 2.2), (120, 115, 1.4)])
    segments = segment_samples(samples)

    assert [s.kind for s in segments] == ["run", "walk", "run", "walk"]
    assert [s.index for s in segments] == [0, 1, 2, 3]


def test_a_dropped_reading_does_not_split_one_run_into_three():
    """A single bad sample mid-run would otherwise cut the longest continuous block
    to a third of its real length — the metric a beginner most needs to be right."""
    samples = series([(150, 165, 2.2), (2, 100, 2.2), (150, 165, 2.2)])
    segments = segment_samples(samples)

    assert [s.kind for s in segments] == ["run"]
    assert segments[0].duration_s == pytest.approx(301, abs=2)


def test_a_genuine_walk_break_is_not_merged_away():
    samples = series([(120, 165, 2.2), (30, 115, 1.4), (120, 165, 2.2)])
    assert [s.kind for s in segment_samples(samples)] == ["run", "walk", "run"]


def test_a_short_opening_block_is_folded_forwards():
    """It has no predecessor to be absorbed into, so it needs handling of its own."""
    samples = series([(4, 115, 1.4), (200, 165, 2.2)])
    segments = segment_samples(samples)

    assert len(segments) == 1
    assert segments[0].kind == "run"


def test_empty_input_returns_nothing_rather_than_raising():
    assert segment_samples([]) == []


# --- the founding case --------------------------------------------------------

def test_a_run_walk_session_reports_running_distance_not_the_total():
    """Five 90 s run blocks with walking between: 2.5 km logged, 1.0 km actually run.

    This is the 17 Aug session that started the project, in miniature.
    """
    spec = []
    for _ in range(5):
        spec.append((90, 165, 200 / 90))     # 200 m running
        spec.append((180, 115, 300 / 180))   # 300 m walking
    truth = summarise(segment_samples(series(spec)))

    assert truth.total_distance_m == pytest.approx(2500, abs=30)
    assert truth.run_distance_m == pytest.approx(1000, abs=30)
    assert truth.walk_distance_m == pytest.approx(1500, abs=30)
    assert truth.run_fraction == pytest.approx(0.40, abs=0.02)
    assert truth.run_block_count == 5


def test_run_pace_is_faster_than_the_blended_pace_the_watch_shows():
    """The number that made the athlete look slower than they are."""
    spec = []
    for _ in range(4):
        spec.append((90, 165, 200 / 90))
        spec.append((180, 115, 300 / 180))
    truth = summarise(segment_samples(series(spec)))

    assert truth.run_pace_s_per_km < truth.blended_pace_s_per_km
    assert truth.run_pace_s_per_km == pytest.approx(450, abs=30)   # ~7:30/km


def test_longest_continuous_run_is_the_longest_block_not_the_sum():
    spec = [(60, 165, 2.2), (60, 115, 1.4), (200, 165, 2.2), (60, 115, 1.4), (90, 165, 2.2)]
    truth = summarise(segment_samples(series(spec)))

    assert truth.run_block_count == 3
    assert truth.longest_run_s == pytest.approx(200, abs=5)


def test_a_pure_walk_reports_no_running_rather_than_failing():
    truth = summarise(segment_samples(series([(600, 115, 1.4)])))

    assert truth.run_distance_m == 0
    assert truth.run_block_count == 0
    assert truth.run_fraction == 0.0
    assert truth.run_pace_s_per_km is None   # not 0, which would read as instant


def test_pace_is_none_over_a_distance_too_short_to_measure():
    """Under 50 m the figure is GPS noise wearing a decimal point."""
    truth = summarise(segment_samples(series([(300, 115, 0.1)])))
    assert truth.walk_pace_s_per_km is None


# --- heart rate ---------------------------------------------------------------

def test_hr_drift_is_none_when_coverage_is_too_thin():
    """Otherwise the figure describes which half had data, not the athlete."""
    samples = series([(200, 160, 2.2)])
    for index, sample in enumerate(samples):
        sample.heart_rate = 150 if index < 20 else None

    assert hr_drift_percent(samples) is None


def test_hr_drift_is_positive_when_the_second_half_is_harder():
    samples = series([(200, 160, 2.2)])
    for index, sample in enumerate(samples):
        sample.heart_rate = 140 if index < 100 else 154

    drift = hr_drift_percent(samples)
    assert drift == pytest.approx(10.0, abs=0.5)


def test_hr_drift_is_none_without_any_heart_rate():
    assert hr_drift_percent(series([(200, 160, 2.2)])) is None


# --- load ---------------------------------------------------------------------

def test_load_weights_running_above_walking():
    assert session_load(10, 0) > session_load(0, 10)


def test_load_formula_is_versioned():
    """Unversioned, a load figure silently means two things at two points in the
    same database, and the trend across the change is meaningless."""
    assert LOAD_FORMULA_VERSION


def test_a_rest_day_has_zero_load():
    assert session_load(0, 0) == 0
