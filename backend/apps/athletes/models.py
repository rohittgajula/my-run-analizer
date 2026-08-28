"""The tenancy root and everything hanging off it.

`Athlete` is the tenant. Every piece of data in this system belongs to exactly one,
from the first model onwards — retrofitting multi-tenancy is a bad week, and on a
publicly hosted app a missed filter is a breach rather than a bug.
"""

from django.contrib.auth.models import User
from django.db import models


def default_available_days() -> dict:
    """Which weekdays this athlete can train. Keys are "0" (Monday) .. "6" (Sunday).

    Availability only — deliberately NOT what each day is for. The plan generator
    decides that from the phase, the runway and last week's data. If the profile also
    declared "Tuesday is intervals" the two would disagree and one would silently win.

    Monday rest by default: new runners are injured by frequency far more often than
    by distance.
    """
    return {"0": False, "1": True, "2": False, "3": True,
            "4": False, "5": True, "6": True}


class Athlete(models.Model):
    """Tenancy root. Every piece of data in the system hangs off an Athlete."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="athlete")
    display_name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="UTC")

    date_of_birth = models.DateField(null=True, blank=True)
    weight_kg = models.FloatField(
        null=True, blank=True, help_text="Scales hydration and fuelling figures later."
    )
    resting_hr = models.PositiveSmallIntegerField(null=True, blank=True)
    max_hr = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Observed max, not a 220-age formula estimate."
    )

    # Standing defaults, in seconds per km. NOT what today's session prescribes:
    # anything describing today reads from the session object, which is what these
    # became after the plan, the day type and the readiness adjustment. Reading the
    # profile instead skips all three.
    easy_pace_min = models.PositiveSmallIntegerField(
        default=600, help_text="Fast edge of the easy band, sec/km. 600 = 10:00/km."
    )
    easy_pace_max = models.PositiveSmallIntegerField(
        default=645, help_text="Slow edge of the easy band, sec/km. 645 = 10:45/km."
    )
    hr_easy_min = models.PositiveSmallIntegerField(default=130)
    hr_easy_max = models.PositiveSmallIntegerField(default=145)
    hr_ceiling = models.PositiveSmallIntegerField(
        default=155, help_text="Cross this during a run block and the athlete should walk."
    )

    run_cadence_threshold = models.PositiveSmallIntegerField(
        default=140, help_text="Cadence at or above this counts as running, not walking."
    )

    available_days = models.JSONField(default=default_available_days)
    long_run_day = models.PositiveSmallIntegerField(
        default=6, help_text="0 = Monday. The one day with time for a long session."
    )

    # Whether the athlete has been through onboarding. Needed as an explicit flag
    # rather than inferred: the router has to decide where a freshly-registered
    # athlete lands, and racing a redirect against a state update silently skipped
    # onboarding entirely.
    onboarding_complete = models.BooleanField(default=False)

    # System-managed. Never writable through the API — a client that could set
    # garmin_connected=True could make the UI lie about whether sync works.
    garmin_connected = models.BooleanField(default=False)
    garmin_last_sync = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.display_name or self.user.username

    @property
    def local_now(self):
        """Now, in the athlete's own timezone.

        Django's TIME_ZONE is UTC, so timezone.localdate() answers a question nobody
        asked: at 00:48 in Kolkata it is still yesterday in UTC, and the whole app
        would show yesterday's session. Every 'today' must come from here.
        """
        from zoneinfo import ZoneInfo

        from django.utils import timezone

        try:
            zone = ZoneInfo(self.timezone or "UTC")
        except Exception:  # noqa: BLE001 — a bad zone must not break every page
            zone = ZoneInfo("UTC")
        return timezone.now().astimezone(zone)

    @property
    def local_today(self):
        return self.local_now.date()

    @property
    def training_days_per_week(self) -> int:
        return sum(1 for v in (self.available_days or {}).values() if v)

    def is_available(self, weekday: int) -> bool:
        """weekday: 0 = Monday."""
        return bool((self.available_days or {}).get(str(weekday), False))

    def zones(self):
        """Heart-rate zones, or None when the data cannot support them.

        Resting HR comes from Garmin's nightly measurement in preference to the
        profile field, because it is measured rather than remembered. Max HR falls
        back to the highest value ever *observed* in this athlete's own activities —
        a real measurement, and a conservative one: a true maximum is likely higher,
        which makes the derived zones slightly easier rather than harder.

        There is deliberately no 220-age fallback. That formula has a ±10-12 bpm
        spread, wide enough to put someone a full zone out, and a wrong zone is worse
        than no zone.
        """
        from django.db.models import Max

        from analysis.zones import build

        from apps.activities.models import Activity
        from apps.ingest.models import DailyMetrics

        resting = self.resting_hr
        source = "profile"
        if not resting:
            recent = [
                row.resting_hr
                for row in DailyMetrics.objects.filter(athlete=self).order_by("-metric_date")[:28]
                if row.resting_hr
            ]
            resting = sorted(recent)[len(recent) // 2] if recent else None

        maximum = self.max_hr
        if not maximum:
            maximum = Activity.objects.filter(athlete=self).aggregate(
                peak=Max("max_hr")
            )["peak"]
            source = "observed"

        if not resting or not maximum:
            return None
        return build(resting, maximum, max_source=source)

    @property
    def token_dir(self) -> str:
        """Per-athlete Garmin token directory. Never shared between athletes."""
        from django.conf import settings

        return f"{settings.GARMIN_TOKEN_DIR}/athlete_{self.pk}"


class OwnedByAthlete(models.Model):
    """Base for every tenant-scoped model."""

    athlete = models.ForeignKey(
        Athlete, on_delete=models.CASCADE, related_name="%(class)ss"
    )

    class Meta:
        abstract = True
