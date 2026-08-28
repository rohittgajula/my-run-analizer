"""Pipeline behaviour.

Celery will retry these at the worst possible moment, so the property under test
throughout is that re-running changes nothing that should not change.
"""

import datetime as dt

import pytest
from django.core.cache import cache
from django.utils import timezone

from analysis.segmentation import ALGORITHM_VERSION
from apps.activities.models import Activity
from apps.activities.tasks import derive_stale
from apps.coaching.tasks import ANALYSIS_GRACE_HOURS, BACKFILL_DAYS
from apps.ingest.tasks import BREAKER_KEY, garmin_blocked, sync_all, sync_one, trip_breaker
from apps.journal.models import JournalEntry


@pytest.fixture(autouse=True)
def _clear_breaker():
    cache.delete(BREAKER_KEY)
    yield
    cache.delete(BREAKER_KEY)


# --- the circuit breaker ------------------------------------------------------

@pytest.mark.django_db
def test_a_rate_limit_stops_every_athlete_not_just_the_one_that_hit_it():
    """Garmin limits by IP. Continuing to the next athlete lengthens the block for
    everyone, so the breaker is global rather than per-athlete."""
    trip_breaker("429")
    assert garmin_blocked()
    assert sync_all()["skipped"] == "rate_limited"
    assert sync_one(1)["skipped"] == "rate_limited"


@pytest.mark.django_db
def test_sync_runs_when_the_breaker_is_open(athlete):
    athlete.garmin_connected = False
    athlete.save()
    assert sync_one(athlete.pk)["skipped"] == "not_connected"


@pytest.mark.django_db
def test_a_missing_athlete_is_skipped_rather_than_crashing():
    assert sync_one(999_999)["skipped"] == "not_connected"


# --- re-derivation ------------------------------------------------------------

@pytest.mark.django_db
def test_nothing_is_queued_when_everything_is_current(athlete):
    Activity.objects.create(
        athlete=athlete, source=Activity.Source.FIT_UPLOAD, sport="running",
        started_at=timezone.now(), local_date=athlete.local_today,
        segmentation_version=ALGORITHM_VERSION,
    )
    assert derive_stale()["queued"] == 0


@pytest.mark.django_db
def test_bumping_the_algorithm_version_makes_history_stale(athlete, settings):
    """This is why segmentation_version is an integer and not a boolean: history
    re-derives itself rather than waiting for someone to remember a command."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    Activity.objects.create(
        athlete=athlete, source=Activity.Source.FIT_UPLOAD, sport="running",
        started_at=timezone.now(), local_date=athlete.local_today,
        segmentation_version=ALGORITHM_VERSION - 1,
    )
    assert derive_stale()["queued"] == 1


@pytest.mark.django_db
def test_never_processed_activities_count_as_stale(athlete):
    Activity.objects.create(
        athlete=athlete, source=Activity.Source.FIT_UPLOAD, sport="running",
        started_at=timezone.now(), local_date=athlete.local_today,
        segmentation_version=None,
    )
    assert derive_stale()["queued"] == 1


# --- the journal gate ---------------------------------------------------------

def _ready(athlete, activity) -> str:
    """Mirrors the decision in analyse_ready, so the rule is asserted directly."""
    cutoff = timezone.now() - dt.timedelta(hours=ANALYSIS_GRACE_HOURS)
    journalled = JournalEntry.objects.filter(
        athlete=athlete, applies_to_date=activity.local_date
    ).exists()
    backfilled = (athlete.local_today - activity.local_date).days > BACKFILL_DAYS
    if journalled:
        return "journalled"
    if activity.created_at < cutoff:
        return "grace_expired"
    if backfilled:
        return "backfilled"
    return "waiting"


@pytest.mark.django_db
def test_a_fresh_run_waits_for_the_athlete_to_say_something(athlete):
    """The subjective read is the only input Garmin cannot supply, and an analysis
    without it presents a partial picture as a complete one."""
    activity = Activity.objects.create(
        athlete=athlete, source=Activity.Source.GARMIN_SYNC, sport="running",
        started_at=timezone.now(), local_date=athlete.local_today,
    )
    assert _ready(athlete, activity) == "waiting"


@pytest.mark.django_db
def test_a_journalled_run_is_analysed(athlete):
    activity = Activity.objects.create(
        athlete=athlete, source=Activity.Source.GARMIN_SYNC, sport="running",
        started_at=timezone.now(), local_date=athlete.local_today,
    )
    JournalEntry.objects.create(
        athlete=athlete, text="felt fine", written_on=athlete.local_today,
        applies_to_date=athlete.local_today,
    )
    assert _ready(athlete, activity) == "journalled"


@pytest.mark.django_db
def test_a_backfilled_run_does_not_wait(athlete):
    """Nobody journals a session from three weeks ago. Without this the whole
    import sits idle for a day and a half waiting for entries never coming."""
    activity = Activity.objects.create(
        athlete=athlete, source=Activity.Source.GARMIN_SYNC, sport="running",
        started_at=timezone.now(),
        local_date=athlete.local_today - dt.timedelta(days=21),
    )
    assert _ready(athlete, activity) == "backfilled"


@pytest.mark.django_db
def test_the_gate_cannot_deadlock(athlete):
    """A forgotten journal must not park a run forever."""
    activity = Activity.objects.create(
        athlete=athlete, source=Activity.Source.GARMIN_SYNC, sport="running",
        started_at=timezone.now(), local_date=athlete.local_today,
    )
    Activity.objects.filter(pk=activity.pk).update(
        created_at=timezone.now() - dt.timedelta(hours=ANALYSIS_GRACE_HOURS + 1)
    )
    activity.refresh_from_db()
    assert _ready(athlete, activity) == "grace_expired"
