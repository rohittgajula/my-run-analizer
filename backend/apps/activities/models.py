"""Activities and their per-second samples.

`ActivityRecord` is the table that makes this project possible. Garmin's activity
summary has no per-second series, so without it segmentation cannot run — and without
segmentation a 2.5 km logged run stays "2.5 km at 8:27/km" rather than "1.0 km run in
five blocks, 1.5 km walked", which is the number a coach actually needs.
"""

from django.db import models

from apps.athletes.models import OwnedByAthlete


class Activity(OwnedByAthlete):
    """One recorded session. Summary fields mirror the FIT `session` message."""

    class Source(models.TextChoices):
        GARMIN_SYNC = "garmin_sync", "Garmin sync"
        FIT_UPLOAD = "fit_upload", "Manual FIT upload"

    garmin_activity_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    raw_file = models.ForeignKey(
        "ingest.RawFitFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )

    sport = models.CharField(max_length=40, default="running")
    started_at = models.DateTimeField(db_index=True)
    # Denormalised on purpose. Deriving it at query time would force every "which runs
    # were this week" query to know the athlete's timezone. Written once at ingest from
    # athlete.local_today — never django.utils.timezone.localdate().
    local_date = models.DateField(
        db_index=True, help_text="Calendar date in the athlete's own timezone."
    )

    total_distance_m = models.FloatField(default=0)
    total_timer_s = models.FloatField(default=0)
    total_elapsed_s = models.FloatField(default=0)

    avg_hr = models.PositiveSmallIntegerField(null=True, blank=True)
    max_hr = models.PositiveSmallIntegerField(null=True, blank=True)
    avg_cadence_spm = models.FloatField(null=True, blank=True)
    total_ascent_m = models.FloatField(null=True, blank=True)
    total_descent_m = models.FloatField(null=True, blank=True)
    calories = models.PositiveIntegerField(null=True, blank=True)

    # Which segmentation algorithm produced this activity's derived data. NULL means
    # never processed. An integer rather than a "metrics_current" boolean: a flag tells
    # you a row is stale but never how stale, and it relies on someone remembering to
    # flip every row. This makes "everything before v4" a query, and lets you tell
    # which algorithm produced any given number the first time two runs disagree.
    segmentation_version = models.IntegerField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "activities"
        ordering = ["-started_at"]
        constraints = [
            # Conditional on purpose: without the condition, two manual uploads each
            # with a NULL garmin_activity_id would collide.
            models.UniqueConstraint(
                fields=["athlete", "garmin_activity_id"],
                condition=models.Q(garmin_activity_id__isnull=False),
                name="uniq_athlete_garmin_activity",
            )
        ]

    def __str__(self):
        return f"{self.local_date} {self.sport} {self.total_distance_m / 1000:.2f}km"


class ActivityRecord(models.Model):
    """Per-second sample. A 28-minute run is roughly 1,670 rows, written in bulk.

    Every field is nullable, and that matters: running-dynamics fields exist only with
    a compatible sensor, and `None` (not measured) must stay distinguishable from `0`
    (measured as zero). Collapsing the two makes the system report trends in data it
    does not have.
    """

    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="records"
    )
    offset_s = models.FloatField(help_text="Seconds since activity start.")

    distance_m = models.FloatField(null=True)
    speed_mps = models.FloatField(null=True)
    cadence_spm = models.FloatField(null=True, help_text="Full steps/min, both legs.")
    heart_rate = models.PositiveSmallIntegerField(null=True)
    altitude_m = models.FloatField(null=True)
    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)

    # Stored now because the raw file already has them and re-parsing later is free,
    # whereas re-collecting a run is not.
    power_w = models.FloatField(null=True)
    vertical_oscillation_mm = models.FloatField(null=True)
    ground_contact_ms = models.FloatField(null=True)
    stride_length_m = models.FloatField(null=True)
    vertical_ratio = models.FloatField(null=True)
    respiration_rate = models.FloatField(null=True)
    temperature_c = models.FloatField(null=True)

    class Meta:
        ordering = ["offset_s"]
        indexes = [models.Index(fields=["activity", "offset_s"])]

    def __str__(self):
        return f"{self.activity_id}@{self.offset_s:.0f}s"


class Segment(models.Model):
    """A contiguous run / walk / stop block, derived from cadence.

    This is the entity Garmin does not give you: its lap data hides that a "2.65 km
    run" was five short run blocks with walking in between.
    """

    class Kind(models.TextChoices):
        RUN = "run", "Run"
        WALK = "walk", "Walk"
        STOP = "stop", "Stop"

    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="segments"
    )
    index = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=8, choices=Kind.choices, db_index=True)

    start_offset_s = models.FloatField()
    duration_s = models.FloatField()
    distance_m = models.FloatField()

    avg_pace_s_per_km = models.FloatField(null=True, blank=True)
    avg_cadence_spm = models.FloatField(null=True, blank=True)

    hr_start = models.PositiveSmallIntegerField(null=True, blank=True)
    hr_end = models.PositiveSmallIntegerField(null=True, blank=True)
    hr_avg = models.PositiveSmallIntegerField(null=True, blank=True)
    hr_max = models.PositiveSmallIntegerField(null=True, blank=True)

    # Measured from the HR peak, not the block boundary — cardiac lag keeps HR
    # climbing 15-25s after stopping. Should rise over months as fitness improves.
    hr_recovery_60s = models.SmallIntegerField(null=True, blank=True)
    # How much further HR rose AFTER stopping. Large means that block outran the
    # athlete's aerobic system. Should fall towards zero as base fitness improves.
    hr_overshoot_bpm = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["activity", "index"]
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "index"], name="uniq_activity_segment_index"
            )
        ]

    def __str__(self):
        return f"{self.kind} {self.duration_s:.0f}s {self.distance_m:.0f}m"


class ActivityMetrics(models.Model):
    """Derived numbers for one activity. One row per activity, rebuilt on demand.

    Separate from Activity so that re-deriving is a delete-and-recreate rather than a
    partial update, and so the ingested facts stay clearly distinct from the computed
    ones — a distinction that matters the first time a metric looks wrong.
    """

    activity = models.OneToOneField(
        Activity, on_delete=models.CASCADE, related_name="metrics"
    )

    run_distance_m = models.FloatField()
    walk_distance_m = models.FloatField()
    run_fraction = models.FloatField()

    run_duration_s = models.FloatField()
    walk_duration_s = models.FloatField()
    stop_duration_s = models.FloatField()

    run_block_count = models.PositiveSmallIntegerField()
    # The single most useful progress signal a beginner has.
    longest_run_m = models.FloatField()
    longest_run_s = models.FloatField()

    # Over RUN blocks only. The athlete's real running pace, as opposed to the
    # blended figure the watch shows, which is slower than either component.
    run_pace_s_per_km = models.FloatField(null=True, blank=True)
    walk_pace_s_per_km = models.FloatField(null=True, blank=True)
    blended_pace_s_per_km = models.FloatField(null=True, blank=True)

    avg_run_cadence_spm = models.FloatField(null=True, blank=True)
    avg_run_hr = models.PositiveSmallIntegerField(null=True, blank=True)
    hr_drift_percent = models.FloatField(null=True, blank=True)

    custom_load = models.FloatField(null=True, blank=True)
    load_formula_version = models.CharField(max_length=8, blank=True)

    # Seconds per zone, keyed Z1..Z5 plus "below". Empty when the athlete has no
    # usable max HR — an empty dict reads as "not computed", a dict of zeros would
    # read as "measured, and you were never in a zone".
    time_in_zone = models.JSONField(default=dict, blank=True)

    algorithm_version = models.IntegerField()
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "activity metrics"

    def __str__(self):
        return f"{self.run_distance_m:.0f}m run / {self.walk_distance_m:.0f}m walk"
