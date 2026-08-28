"""Which session a chat message actually affects.

Reporting a sore knee AFTER this morning's run cannot change this morning's run.
Saying "today's session is dropped" in that case is both wrong and useless — the
training already happened — and it is the kind of wrong that makes an athlete stop
trusting the whole thing.
"""

import datetime as dt

import pytest

from apps.activities.models import Activity
from apps.journal.models import JournalEntry
from apps.journal.services import _target_session, _when
from apps.planning.models import Race


@pytest.fixture
def athlete_with_plan(athlete):
    athlete.available_days = {"0": False, "1": True, "2": False, "3": True,
                              "4": False, "5": True, "6": True}
    athlete.long_run_day = 6
    athlete.save()
    Race.objects.create(
        athlete=athlete, name="Target 10K",
        date=athlete.local_today + dt.timedelta(weeks=14), distance_km=10.0, is_target=True,
    )
    return athlete


def entry_for(athlete, *, completed: bool, day=None) -> JournalEntry:
    day = day or athlete.local_today
    return JournalEntry.objects.create(
        athlete=athlete, text="…", written_on=athlete.local_today, applies_to_date=day,
        extracted={"describes_completed_run": completed}, pain_reported=True,
    )


@pytest.mark.django_db
def test_a_run_already_done_affects_the_next_session_not_todays(athlete_with_plan):
    """The reported bug: 'ran 3k this morning, knee sore' dropped THIS morning."""
    entry = entry_for(athlete_with_plan, completed=True)
    session, label, date = _target_session(athlete_with_plan, entry)

    assert label == "next"
    if session:
        assert date > athlete_with_plan.local_today


@pytest.mark.django_db
def test_how_i_feel_now_affects_that_days_session(athlete_with_plan):
    """'Slept badly, about to head out' is about the session still to come.

    Anchored to a Tuesday rather than to today: today may be a rest day, and a rest
    day correctly falls through to the next session instead.
    """
    tuesday = athlete_with_plan.local_today
    while tuesday.weekday() != 1:
        tuesday += dt.timedelta(days=1)

    entry = entry_for(athlete_with_plan, completed=False, day=tuesday)
    session, label, date = _target_session(athlete_with_plan, entry)

    assert label in ("today", "that day")
    assert date == tuesday
    assert session is not None


@pytest.mark.django_db
def test_an_activity_already_recorded_pushes_it_forward_too(athlete_with_plan):
    """Covers a message that never mentions the run — the data says it happened."""
    Activity.objects.create(
        athlete=athlete_with_plan, source=Activity.Source.GARMIN_SYNC, sport="running",
        started_at=dt.datetime(2026, 8, 28, 2, 0, tzinfo=dt.timezone.utc),
        local_date=athlete_with_plan.local_today, total_distance_m=3000,
    )
    entry = entry_for(athlete_with_plan, completed=False)
    _session, label, _date = _target_session(athlete_with_plan, entry)

    assert label == "next"


@pytest.mark.django_db
def test_the_sentence_names_the_day_it_applies_to(athlete_with_plan):
    """'Your next session' with no date is a promise the athlete cannot check."""
    assert _when("today", athlete_with_plan.local_today) == "Today's session"
    assert "Sat" in _when("next", dt.date(2026, 8, 29))


@pytest.mark.django_db
def test_no_plan_means_nothing_is_claimed_to_change(athlete):
    entry = entry_for(athlete, completed=True)
    session, _label, _date = _target_session(athlete, entry)
    assert session is None


@pytest.mark.django_db
def test_a_rest_day_falls_through_to_the_next_session(athlete_with_plan):
    """Reporting pain on a rest day must not read as "nothing changes".

    There is nothing to ease today, but the report has not stopped mattering — and
    telling someone their pain changed nothing is how they stop reporting it.
    """
    # Monday is unavailable in this athlete's week.
    monday = athlete_with_plan.local_today
    while monday.weekday() != 0:
        monday += dt.timedelta(days=1)

    entry = entry_for(athlete_with_plan, completed=False, day=monday)
    session, label, date = _target_session(athlete_with_plan, entry)

    assert label == "next"
    assert session is not None
    assert date > monday
