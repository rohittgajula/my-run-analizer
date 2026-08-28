"""Races. The plan is resolved from these, never from a single stored date."""

from django.db import models

from apps.athletes.models import OwnedByAthlete


class Race(OwnedByAthlete):
    """One race on the calendar.

    `is_target` marks the A race the ramp counts down to. Every other race is
    prescribed at its own distance with its own short taper and recovery window, and
    does not move the plan — which is exactly what a single-date plan gets wrong.
    """

    name = models.CharField(max_length=120)
    date = models.DateField(db_index=True)
    distance_km = models.FloatField()
    is_target = models.BooleanField(
        default=False, help_text="The A race. At most one should be set."
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["athlete", "date"], name="uniq_athlete_race_date")
        ]

    def __str__(self):
        return f"{self.name} ({self.date}, {self.distance_km:g} km)"
