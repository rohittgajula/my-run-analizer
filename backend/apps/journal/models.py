"""What the athlete tells the system in their own words.

The highest-value input in the project and the only one Garmin cannot supply. A watch
knows your heart rate; it does not know your knee hurt from 2 km, that work is brutal
this week, or that you stopped because of a dog.
"""

from django.db import models

from apps.athletes.models import OwnedByAthlete


class JournalEntry(OwnedByAthlete):
    """One thing the athlete said, plus the facts extracted from it.

    Facts are stored separately from the text so a better extractor can be re-run over
    history, and so a wrong extraction is a visible, correctable *fact* rather than a
    silent change to what the athlete is told to do.
    """

    class Source(models.TextChoices):
        CHAT = "chat", "Chat"
        RUN_LOG = "run_log", "Post-run log"

    text = models.TextField()
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.CHAT)

    written_on = models.DateField(db_index=True)
    # Which day's SESSION this bears on, which is not the same as the day it was
    # typed. "Last night I slept badly", written in the morning, is about TODAY's
    # session: the bad night is what you carry into it. Asked the other way round the
    # model answered "yesterday" — right about the words, wrong for the plan.
    applies_to_date = models.DateField(db_index=True)

    activity = models.ForeignKey(
        "activities.Activity", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="journal_entries",
    )

    # Extracted facts. Nullable because extraction can fail or be pending, and a
    # pending entry must not read as "nothing was wrong".
    extracted = models.JSONField(null=True, blank=True)
    extraction_failed = models.BooleanField(default=False)

    # Denormalised from `extracted` so the safety gate is a database query rather than
    # a JSON walk. These are what readiness reads, and they must be cheap and certain.
    pain_reported = models.BooleanField(default=False, db_index=True)
    illness_reported = models.BooleanField(default=False, db_index=True)
    rpe = models.PositiveSmallIntegerField(null=True, blank=True)

    reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "journal entries"

    def __str__(self):
        return f"{self.applies_to_date}: {self.text[:60]}"
