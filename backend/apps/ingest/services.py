"""Turning a raw .fit file into an Activity and its per-second records."""

from __future__ import annotations

import datetime as dt
import logging

from django.db import transaction
from django.utils import timezone

from apps.activities.models import Activity, ActivityRecord

from .fit_parser import parse
from .models import RawFitFile

logger = logging.getLogger(__name__)

# Written in chunks: a long run is tens of thousands of rows, and one giant
# bulk_create builds the whole list in memory before touching the database.
RECORD_BATCH = 2000


class DuplicateActivity(Exception):
    """This activity is already stored. Not an error — the expected result of a re-sync."""


def ingest_fit(raw: RawFitFile, garmin_activity_id: int | None = None) -> Activity:
    """Parse a stored file into an Activity. Safe to call twice; the second raises.

    The failure marking lives OUT here, deliberately. `_ingest` is atomic, so a
    `raw.save(status=FAILED)` written inside it is rolled back along with everything
    else — leaving a file stuck at PENDING with no recorded error, retried forever,
    with nothing anywhere saying why.
    """
    try:
        return _ingest(raw, garmin_activity_id)
    except DuplicateActivity:
        raise  # an expected re-sync, not a failure of the file
    except Exception as exc:
        raw.status = RawFitFile.Status.FAILED
        raw.error = str(exc)
        raw.save(update_fields=["status", "error"])
        raise


@transaction.atomic
def _ingest(raw: RawFitFile, garmin_activity_id: int | None) -> Activity:
    """Atomic on purpose: a half-ingested activity with only some of its records is
    worse than none, because it looks complete to every query that follows."""
    athlete = raw.athlete

    if garmin_activity_id is not None and Activity.objects.filter(
        athlete=athlete, garmin_activity_id=garmin_activity_id
    ).exists():
        raise DuplicateActivity(f"activity {garmin_activity_id} already stored")

    with raw.file.open("rb") as handle:
        parsed = parse(handle)

    if parsed.started_at is None:
        raise ValueError("No timestamp in file; cannot place this activity on a calendar.")

    started_at = parsed.started_at
    if timezone.is_naive(started_at):
        # FIT timestamps are UTC by specification; fitparse hands them back naive.
        # datetime.timezone.utc, not django.utils.timezone.utc — the latter was
        # removed in Django 5 and every real activity failed on it, while the tests
        # passed because their fixtures were already aware.
        started_at = timezone.make_aware(started_at, dt.timezone.utc)

    # local_date comes from the athlete's own zone, never timezone.localdate(). At
    # 00:48 in Kolkata, UTC still says yesterday, which would file the run — and its
    # journal entry — under the wrong day.
    local_date = started_at.astimezone(athlete.local_now.tzinfo).date()

    activity = Activity.objects.create(
        athlete=athlete,
        garmin_activity_id=garmin_activity_id,
        source=(
            Activity.Source.GARMIN_SYNC
            if garmin_activity_id is not None
            else Activity.Source.FIT_UPLOAD
        ),
        raw_file=raw,
        sport=parsed.sport,
        started_at=started_at,
        local_date=local_date,
        total_distance_m=parsed.total_distance_m,
        total_timer_s=parsed.total_timer_s,
        total_elapsed_s=parsed.total_elapsed_s,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        avg_cadence_spm=parsed.avg_cadence_spm,
        total_ascent_m=parsed.total_ascent_m,
        total_descent_m=parsed.total_descent_m,
        calories=parsed.calories,
        # NULL: never segmented. M2 fills this in with its ALGORITHM_VERSION.
        segmentation_version=None,
    )

    rows = [
        ActivityRecord(
            activity=activity,
            offset_s=record.offset_s,
            distance_m=record.distance_m,
            speed_mps=record.speed_mps,
            cadence_spm=record.cadence_spm,
            heart_rate=record.heart_rate,
            altitude_m=record.altitude_m,
            latitude=record.latitude,
            longitude=record.longitude,
            power_w=record.power_w,
            vertical_oscillation_mm=record.vertical_oscillation_mm,
            ground_contact_ms=record.ground_contact_ms,
            stride_length_m=record.stride_length_m,
            vertical_ratio=record.vertical_ratio,
            respiration_rate=record.respiration_rate,
            temperature_c=record.temperature_c,
        )
        for record in parsed.records
    ]
    ActivityRecord.objects.bulk_create(rows, batch_size=RECORD_BATCH)

    raw.status = RawFitFile.Status.PARSED
    raw.parsed_at = timezone.now()
    raw.error = ""
    raw.save(update_fields=["status", "parsed_at", "error"])

    logger.info(
        "ingested activity %s for athlete %s: %.2f km, %d records",
        activity.pk, athlete.pk, activity.total_distance_m / 1000, len(rows),
    )
    return activity
