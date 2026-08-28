"""Ingestion tests.

Built on synthetic FIT files rather than fixtures downloaded from Garmin: the tests
must run without network, without credentials, and must still exercise the cases that
actually bite — a missing session message, absent heart rate, and the run/walk shape
this whole project exists to measure.
"""

import datetime as dt
from io import BytesIO

import pytest
from django.core.files.base import ContentFile

from apps.activities.models import Activity, ActivityRecord
from apps.ingest.fit_parser import (
    ParsedActivity, ParsedRecord, _full_cadence, derive_missing_totals,
)
from apps.ingest.models import RawFitFile
from apps.ingest.services import DuplicateActivity, ingest_fit


# --- cadence, which everything downstream depends on --------------------------

def test_cadence_is_doubled_from_per_leg():
    """FIT reports one leg. Halving every cadence would push every run below the
    140 spm running threshold and classify entire activities as walking."""
    assert _full_cadence({"cadence": 84, "fractional_cadence": 0.5}) == 169.0
    assert _full_cadence({"cadence": 80}) == 160.0


def test_missing_cadence_is_none_not_zero():
    # 0 spm is 'measured, standing still'. None is 'no sensor'. Collapsing them
    # would make missing data look like a stationary athlete.
    assert _full_cadence({}) is None


# --- the founding case --------------------------------------------------------

def _run_walk_activity() -> ParsedActivity:
    """A 2.5 km activity that is really 1.0 km of running in blocks, plus walking.

    Mirrors the 17 Aug run this project was started over. Segmentation lands in M2;
    this asserts the per-second data needed to see it survives ingestion intact.
    """
    records, distance, offset = [], 0.0, 0.0
    # five run blocks of 200 m at 165 spm, each followed by a 300 m walk at 110 spm
    for _ in range(5):
        for _ in range(90):          # ~90 s running
            distance += 200 / 90
            records.append(ParsedRecord(offset_s=offset, distance_m=distance,
                                        cadence_spm=165.0, heart_rate=158))
            offset += 1
        for _ in range(180):         # ~180 s walking
            distance += 300 / 180
            records.append(ParsedRecord(offset_s=offset, distance_m=distance,
                                        cadence_spm=110.0, heart_rate=132))
            offset += 1

    return ParsedActivity(
        sport="running",
        started_at=dt.datetime(2026, 8, 17, 1, 30, tzinfo=dt.timezone.utc),
        total_distance_m=distance,
        total_timer_s=offset,
        total_elapsed_s=offset,
        avg_hr=143,
        records=records,
    )


@pytest.fixture
def stored_fit(athlete, monkeypatch):
    """A RawFitFile whose parse() is stubbed — fitparse is not what is under test."""
    parsed = _run_walk_activity()
    monkeypatch.setattr("apps.ingest.services.parse", lambda _handle: parsed)

    data = b"\x0e\x10\x00\x00.FIT" + b"\x00" * 64
    return RawFitFile.objects.create(
        athlete=athlete,
        file=ContentFile(data, name="test.fit"),
        original_name="test.fit",
        sha256=RawFitFile.hash_bytes(data),
        size_bytes=len(data),
    ), parsed


@pytest.mark.django_db
def test_ingest_stores_every_per_second_record(stored_fit):
    raw, parsed = stored_fit
    activity = ingest_fit(raw, garmin_activity_id=555)

    # Without these rows segmentation cannot run and the run/walk split stays invisible.
    assert activity.records.count() == len(parsed.records) == 1350
    assert activity.total_distance_m == pytest.approx(2500, abs=1)

    cadences = list(activity.records.values_list("cadence_spm", flat=True))
    running = [c for c in cadences if c >= 140]
    assert len(running) == 450, "the five run blocks must survive ingestion"


@pytest.mark.django_db
def test_ingest_marks_the_file_parsed(stored_fit):
    raw, _ = stored_fit
    ingest_fit(raw, garmin_activity_id=555)
    raw.refresh_from_db()

    assert raw.status == RawFitFile.Status.PARSED
    assert raw.parsed_at is not None


@pytest.mark.django_db
def test_segmentation_version_starts_null(stored_fit):
    """NULL means never processed, which is what makes 'everything before v4' a query."""
    raw, _ = stored_fit
    assert ingest_fit(raw, garmin_activity_id=555).segmentation_version is None


# --- the timezone trap --------------------------------------------------------

@pytest.mark.django_db
def test_local_date_uses_the_athletes_zone(stored_fit):
    """01:30 UTC on 17 Aug is 07:00 IST the same day — but the principle is what
    matters: local_date must never come from django.utils.timezone.localdate()."""
    raw, _ = stored_fit
    activity = ingest_fit(raw, garmin_activity_id=555)
    assert activity.local_date.isoformat() == "2026-08-17"


@pytest.mark.django_db
def test_a_late_night_run_is_filed_under_the_local_day(athlete, monkeypatch):
    """20:00 UTC is 01:30 next morning in Kolkata. UTC would file it a day early."""
    parsed = _run_walk_activity()
    parsed.started_at = dt.datetime(2026, 8, 17, 20, 0, tzinfo=dt.timezone.utc)
    monkeypatch.setattr("apps.ingest.services.parse", lambda _h: parsed)

    data = b"late" * 16
    raw = RawFitFile.objects.create(
        athlete=athlete, file=ContentFile(data, name="late.fit"),
        original_name="late.fit", sha256=RawFitFile.hash_bytes(data), size_bytes=len(data),
    )
    assert ingest_fit(raw).local_date.isoformat() == "2026-08-18"


# --- idempotency, the two independent layers ----------------------------------

@pytest.mark.django_db
def test_the_same_garmin_id_is_refused(stored_fit):
    raw, _ = stored_fit
    ingest_fit(raw, garmin_activity_id=555)
    with pytest.raises(DuplicateActivity):
        ingest_fit(raw, garmin_activity_id=555)


@pytest.mark.django_db
def test_the_same_bytes_cannot_be_stored_twice(athlete):
    """The content-hash layer works independently of the Garmin id, which is what
    covers a manual upload of a run that also arrived via sync."""
    from django.db import IntegrityError

    data = b"identical bytes" * 8
    fields = dict(
        athlete=athlete, original_name="a.fit",
        sha256=RawFitFile.hash_bytes(data), size_bytes=len(data),
    )
    RawFitFile.objects.create(file=ContentFile(data, name="a.fit"), **fields)
    with pytest.raises(IntegrityError):
        RawFitFile.objects.create(file=ContentFile(data, name="b.fit"), **fields)


@pytest.mark.django_db
def test_two_manual_uploads_do_not_collide_on_a_null_garmin_id(athlete, monkeypatch):
    """The unique constraint is conditional for exactly this reason."""
    monkeypatch.setattr("apps.ingest.services.parse", lambda _h: _run_walk_activity())

    for name in ("one", "two"):
        data = name.encode() * 32
        raw = RawFitFile.objects.create(
            athlete=athlete, file=ContentFile(data, name=f"{name}.fit"),
            original_name=f"{name}.fit", sha256=RawFitFile.hash_bytes(data),
            size_bytes=len(data),
        )
        ingest_fit(raw)

    assert Activity.objects.filter(athlete=athlete, garmin_activity_id=None).count() == 2


# --- failure handling ---------------------------------------------------------

@pytest.mark.django_db
def test_a_file_with_no_timestamp_fails_loudly(athlete, monkeypatch):
    monkeypatch.setattr("apps.ingest.services.parse", lambda _h: ParsedActivity())

    data = b"no timestamp" * 8
    raw = RawFitFile.objects.create(
        athlete=athlete, file=ContentFile(data, name="bad.fit"), original_name="bad.fit",
        sha256=RawFitFile.hash_bytes(data), size_bytes=len(data),
    )
    with pytest.raises(ValueError):
        ingest_fit(raw)

    raw.refresh_from_db()
    assert raw.status == RawFitFile.Status.FAILED
    assert raw.error
    # Atomic: nothing half-written. A partial activity looks complete to every
    # query that follows, which is worse than no activity at all.
    assert not Activity.objects.filter(athlete=athlete).exists()
    assert not ActivityRecord.objects.exists()


@pytest.mark.django_db
def test_absent_heart_rate_stays_none(athlete, monkeypatch):
    parsed = ParsedActivity(
        started_at=dt.datetime(2026, 8, 17, 6, 0, tzinfo=dt.timezone.utc),
        records=[ParsedRecord(offset_s=float(i), distance_m=float(i * 3)) for i in range(10)],
    )
    monkeypatch.setattr("apps.ingest.services.parse", lambda _h: parsed)

    data = b"nohr" * 16
    raw = RawFitFile.objects.create(
        athlete=athlete, file=ContentFile(data, name="nohr.fit"), original_name="nohr.fit",
        sha256=RawFitFile.hash_bytes(data), size_bytes=len(data),
    )
    activity = ingest_fit(raw)

    assert activity.avg_hr is None
    assert set(activity.records.values_list("heart_rate", flat=True)) == {None}


def test_totals_are_derived_when_the_session_message_is_missing():
    """A truncated file yields no session totals. Storing the 0.0 would read
    downstream as a genuine measurement rather than as absent data."""
    parsed = ParsedActivity(
        records=[ParsedRecord(offset_s=float(i), distance_m=float(i * 3)) for i in range(10)]
    )
    derive_missing_totals(parsed)

    assert parsed.total_distance_m == pytest.approx(27)
    assert parsed.total_elapsed_s == pytest.approx(9)


def test_derivation_leaves_real_totals_alone():
    parsed = ParsedActivity(
        total_distance_m=5000.0, total_elapsed_s=1800.0,
        records=[ParsedRecord(offset_s=0.0, distance_m=1.0)],
    )
    derive_missing_totals(parsed)
    assert parsed.total_distance_m == 5000.0


@pytest.mark.django_db
def test_a_naive_timestamp_is_treated_as_utc(athlete, monkeypatch):
    """fitparse returns naive datetimes; FIT timestamps are UTC by specification.

    Every fixture above is already timezone-aware, so this branch went unexercised —
    and it was broken: it called django.utils.timezone.utc, removed in Django 5, so
    all 18 real activities failed while the suite stayed green.
    """
    parsed = _run_walk_activity()
    parsed.started_at = dt.datetime(2026, 8, 17, 20, 0)  # naive
    monkeypatch.setattr("apps.ingest.services.parse", lambda _h: parsed)

    data = b"naive" * 16
    raw = RawFitFile.objects.create(
        athlete=athlete, file=ContentFile(data, name="naive.fit"),
        original_name="naive.fit", sha256=RawFitFile.hash_bytes(data), size_bytes=len(data),
    )
    activity = ingest_fit(raw)

    assert activity.started_at.tzinfo is not None
    # 20:00 UTC is 01:30 next day in Kolkata.
    assert activity.local_date.isoformat() == "2026-08-18"
