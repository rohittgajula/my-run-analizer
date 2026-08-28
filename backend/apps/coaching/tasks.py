"""Analysis, on a schedule.

The journal gate lives here. An activity is not analysed until the athlete has said
something about it, because the subjective read is the highest-value input in the
system and the only one Garmin cannot supply — and an analysis written without it
would quietly present a partial picture as a complete one.

An escape hatch stops that becoming a deadlock: after ANALYSIS_GRACE_HOURS the run is
analysed anyway, and the analysis says the subjective data is missing rather than
proceeding as though nothing were absent.
"""

from __future__ import annotations

import datetime as dt
import logging

from celery import shared_task
from django.utils import timezone

from apps.activities.models import Activity
from apps.athletes.models import Athlete

from .client import AIUnavailable
from .models import AIAnalysis
from .services import BudgetExceeded, analyse_run, weekly_review

logger = logging.getLogger(__name__)

# How long to wait for the athlete to write something before analysing anyway.
ANALYSIS_GRACE_HOURS = 36

# A run already this old when it arrives skips the wait entirely. The grace period
# exists so someone can write about a run they just did; nobody journals a session
# from three weeks ago, and a backfill would otherwise sit idle for a day and a half
# waiting for entries that are never coming.
BACKFILL_DAYS = 4


@shared_task(name="coaching.analyse_one", bind=True, max_retries=3)
def analyse_one(self, activity_id: int) -> dict:
    activity = (
        Activity.objects.filter(pk=activity_id).select_related("metrics", "athlete").first()
    )
    if activity is None or getattr(activity, "metrics", None) is None:
        return {"skipped": "not_segmented"}

    try:
        _result, cached = analyse_run(activity.athlete, activity)
    except BudgetExceeded:
        # Not retried. The budget will not clear by trying again, and each attempt
        # writes another refusal to the log.
        return {"skipped": "budget"}
    except AIUnavailable as exc:
        # A rate limit or outage is a wait, not a failure. Back off and try later
        # rather than writing the activity off.
        raise self.retry(exc=exc, countdown=min(300 * (self.request.retries + 1), 3600))

    return {"activity": activity_id, "cached": cached}


@shared_task(name="coaching.analyse_ready")
def analyse_ready(limit: int = 25) -> dict:
    """Segmented runs that have been journalled, or waited long enough."""
    from apps.journal.models import JournalEntry

    cutoff = timezone.now() - dt.timedelta(hours=ANALYSIS_GRACE_HOURS)
    analysed = set(
        AIAnalysis.objects.filter(kind=AIAnalysis.Kind.RUN, activity__isnull=False)
        .values_list("activity_id", flat=True)
    )

    queued = waiting = 0
    candidates = (
        Activity.objects.filter(sport="running", metrics__run_block_count__gt=0)
        .exclude(pk__in=analysed)
        .select_related("athlete")
        .order_by("-started_at")[:limit]
    )

    for activity in candidates:
        journalled = JournalEntry.objects.filter(
            athlete=activity.athlete, applies_to_date=activity.local_date
        ).exists()
        # Measured from IMPORT, not from the run: the athlete can only write about a
        # session once it is in the system.
        waited_long_enough = activity.created_at < cutoff
        was_backfilled = (
            activity.athlete.local_today - activity.local_date
        ).days > BACKFILL_DAYS

        if journalled or waited_long_enough or was_backfilled:
            analyse_one.delay(activity.pk)
            queued += 1
        else:
            waiting += 1

    return {"queued": queued, "waiting_on_journal": waiting}


@shared_task(name="coaching.weekly_reviews")
def weekly_reviews() -> dict:
    """One review per athlete, Sunday evening.

    Deliberately not fanned out to a task each: this is a handful of athletes and a
    handful of calls, and serialising keeps the spend visible in one place.
    """
    done = failed = 0
    for athlete in Athlete.objects.filter(onboarding_complete=True):
        try:
            weekly_review(athlete)
            done += 1
        except AIUnavailable as exc:
            logger.warning("weekly review unavailable for %s: %s", athlete.pk, exc)
            failed += 1
    return {"reviewed": done, "failed": failed}
