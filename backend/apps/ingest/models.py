"""Raw activity files, kept permanently.

Two reasons this is non-negotiable, both learned rather than assumed:

1. Garmin has no personal API. The unofficial sync can break at any time, and manual
   export becomes the fallback — but only for activities you still hold.
2. The segmentation algorithm *will* change. When it does, every past activity needs
   reprocessing from source. A lossy summary cannot be re-derived; the original bytes can.
"""

import hashlib

from django.db import models

from apps.athletes.models import OwnedByAthlete


def fit_upload_path(instance, filename: str) -> str:
    return f"fit/athlete_{instance.athlete_id}/{filename}"


class RawFitFile(OwnedByAthlete):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARSED = "parsed", "Parsed"
        FAILED = "failed", "Failed"

    file = models.FileField(upload_to=fit_upload_path)
    original_name = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, db_index=True)
    size_bytes = models.PositiveIntegerField()

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    error = models.TextField(blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)
    parsed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        constraints = [
            # One of the two independent idempotency layers. The other is the Garmin
            # activity id on Activity. Two layers means re-syncing is safe even if
            # Garmin renumbers something, or the same run arrives by manual upload.
            models.UniqueConstraint(
                fields=["athlete", "sha256"], name="uniq_athlete_fit_hash"
            )
        ]

    def __str__(self):
        return f"{self.original_name} ({self.status})"

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


class DailyMetrics(OwnedByAthlete):
    """One day of Garmin wellness data.

    Every field is nullable. Garmin's unofficial endpoints return different shapes by
    device, subscription tier, and whether the watch was worn overnight — a partial
    row is far more useful than no row, and a missing metric must stay distinguishable
    from a measured zero.
    """

    metric_date = models.DateField(db_index=True)

    # Sleep. Garmin dates a night by the MORNING IT ENDS, so this row's sleep is the
    # sleep *before* that day's session. Written notes are the opposite — they come
    # from the evening before. Getting this backwards misattributes both.
    sleep_seconds = models.IntegerField(null=True, blank=True)
    sleep_need_seconds = models.IntegerField(null=True, blank=True)
    sleep_score = models.IntegerField(null=True, blank=True)
    deep_sleep_seconds = models.IntegerField(null=True, blank=True)
    rem_sleep_seconds = models.IntegerField(null=True, blank=True)
    awake_seconds = models.IntegerField(null=True, blank=True)
    sleep_start_local = models.DateTimeField(null=True, blank=True)
    sleep_end_local = models.DateTimeField(null=True, blank=True)

    # Recovery and load
    hrv_overnight_avg = models.IntegerField(null=True, blank=True)
    hrv_status = models.CharField(max_length=24, blank=True)
    training_readiness = models.IntegerField(null=True, blank=True)
    training_readiness_level = models.CharField(max_length=32, blank=True)
    training_status = models.CharField(max_length=40, blank=True)
    acute_load = models.FloatField(null=True, blank=True)
    chronic_load = models.FloatField(null=True, blank=True)

    # Daily totals
    resting_hr = models.IntegerField(null=True, blank=True)
    steps = models.IntegerField(null=True, blank=True)
    stress_avg = models.IntegerField(null=True, blank=True)
    body_battery_high = models.IntegerField(null=True, blank=True)
    body_battery_low = models.IntegerField(null=True, blank=True)
    floors_climbed = models.IntegerField(null=True, blank=True)
    intensity_minutes = models.IntegerField(null=True, blank=True)
    spo2_avg = models.IntegerField(null=True, blank=True)
    respiration_avg = models.FloatField(null=True, blank=True)
    vo2max = models.FloatField(null=True, blank=True)

    # Verbatim payloads, so a field nobody thought to map can be backfilled from
    # history later without re-fetching from Garmin.
    raw = models.JSONField(default=dict, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-metric_date"]
        verbose_name_plural = "daily metrics"
        constraints = [
            models.UniqueConstraint(
                fields=["athlete", "metric_date"], name="uniq_athlete_metric_date"
            )
        ]

    def __str__(self):
        return f"{self.metric_date} · sleep {self.sleep_score} · HRV {self.hrv_overnight_avg}"

    @property
    def acwr(self) -> float | None:
        """Acute:chronic workload ratio. Above ~1.5 is the classic spike warning."""
        if self.acute_load and self.chronic_load:
            return round(self.acute_load / self.chronic_load, 2)
        return None
