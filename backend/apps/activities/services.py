"""Deriving segments and metrics from stored per-second records.

The Django-facing half of the metrics engine. Everything numerical happens in
`analysis`, which imports no Django; this module only loads rows, calls it, and
stores the result.
"""

from __future__ import annotations

import logging

from django.db import transaction

from analysis import heart_rate, load
from analysis.running_truth import summarise
from analysis.segmentation import (
    ALGORITHM_VERSION, NotSegmentable, Sample, check_segmentable, segment_samples,
)

from .models import Activity, ActivityMetrics, Segment

logger = logging.getLogger(__name__)


def load_samples(activity: Activity) -> list[Sample]:
    rows = activity.records.order_by("offset_s").values(
        "offset_s", "distance_m", "speed_mps", "cadence_spm", "heart_rate"
    )
    return [Sample(**row) for row in rows]


@transaction.atomic
def derive(activity: Activity) -> ActivityMetrics | None:
    """Segment an activity and store its metrics. Idempotent — safe to re-run.

    Returns None when the activity cannot be honestly segmented (a cycling session,
    a strength session, anything without a cadence sensor). That is a legitimate
    outcome, not a failure: better no number than a confident wrong one.
    """
    samples = load_samples(activity)

    try:
        check_segmentable(activity.sport, samples)
    except NotSegmentable as reason:
        logger.info("activity %s not segmentable: %s", activity.pk, reason)
        activity.segments.all().delete()
        ActivityMetrics.objects.filter(activity=activity).delete()
        # Still stamp the version: this activity HAS been considered under this
        # algorithm and deliberately left unsegmented, which is different from
        # never having been looked at.
        activity.segmentation_version = ALGORITHM_VERSION
        activity.save(update_fields=["segmentation_version"])
        return None

    threshold = activity.athlete.run_cadence_threshold
    segments = segment_samples(samples, run_cadence_threshold=threshold)
    truth = summarise(segments)

    # Delete-and-recreate rather than update: a partial rewrite would leave stale
    # segments from a previous algorithm version interleaved with new ones.
    activity.segments.all().delete()
    Segment.objects.bulk_create(
        Segment(
            activity=activity,
            index=s.index,
            kind=s.kind,
            start_offset_s=s.start_offset_s,
            duration_s=s.duration_s,
            distance_m=s.distance_m,
            avg_pace_s_per_km=s.avg_pace_s_per_km,
            avg_cadence_spm=s.avg_cadence_spm,
            hr_start=s.hr_start,
            hr_end=s.hr_end,
            hr_avg=s.hr_avg,
            hr_max=s.hr_max,
            hr_recovery_60s=s.hr_recovery_60s,
            hr_overshoot_bpm=s.hr_overshoot_bpm,
        )
        for s in segments
    )

    metrics, _ = ActivityMetrics.objects.update_or_create(
        activity=activity,
        defaults={
            "run_distance_m": truth.run_distance_m,
            "walk_distance_m": truth.walk_distance_m,
            "run_fraction": truth.run_fraction,
            "run_duration_s": truth.run_duration_s,
            "walk_duration_s": truth.walk_duration_s,
            "stop_duration_s": truth.stop_duration_s,
            "run_block_count": truth.run_block_count,
            "longest_run_m": truth.longest_run_m,
            "longest_run_s": truth.longest_run_s,
            "run_pace_s_per_km": truth.run_pace_s_per_km,
            "walk_pace_s_per_km": truth.walk_pace_s_per_km,
            "blended_pace_s_per_km": truth.blended_pace_s_per_km,
            "avg_run_cadence_spm": truth.avg_run_cadence_spm,
            "avg_run_hr": truth.avg_run_hr,
            "hr_drift_percent": heart_rate.hr_drift_percent(samples),
            "custom_load": load.session_load(
                truth.run_duration_s / 60, truth.walk_duration_s / 60
            ),
            "load_formula_version": load.LOAD_FORMULA_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
        },
    )

    activity.segmentation_version = ALGORITHM_VERSION
    activity.save(update_fields=["segmentation_version"])

    logger.info("derived activity %s: %s", activity.pk, truth)
    return metrics
