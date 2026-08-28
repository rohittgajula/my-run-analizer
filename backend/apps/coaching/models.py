from django.db import models

from apps.athletes.models import OwnedByAthlete


class AIRequestLog(models.Model):
    """Every call, including the failures — failed calls are billed too.

    Token counts come from the API response, never from string length: reasoning
    models bill internal thinking as output and none of it appears in the text you
    read, so estimating from the visible answer can be several times short.
    """

    class Status(models.TextChoices):
        OK = "ok", "OK"
        CACHED = "cached", "Cached"
        INVALID = "invalid", "Failed validation"
        REFUSED = "refused", "Refused by safety gate"
        ERROR = "error", "Error"

    athlete = models.ForeignKey(
        "athletes.Athlete", on_delete=models.CASCADE, related_name="ai_requests"
    )
    operation = models.CharField(max_length=40, db_index=True)
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=60)
    prompt_version = models.CharField(max_length=20)

    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    estimated_cost_usd = models.FloatField(default=0.0)

    status = models.CharField(max_length=10, choices=Status.choices)
    retry_count = models.IntegerField(default=0)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.operation} {self.status} {self.input_tokens}+{self.output_tokens}"


class AIAnalysis(OwnedByAthlete):
    """A stored model response, keyed by what produced it.

    `input_hash` covers the context, the prompt version and the model. Identical
    inputs return the stored result rather than paying for the same answer twice —
    which during development is most of the traffic.

    Storing prompt_version and model separately is what makes it possible to tell a
    model change from a prompt change from a data change later.
    """

    class Kind(models.TextChoices):
        RUN = "run", "Run analysis"
        WEEKLY = "weekly", "Weekly review"
        GUIDANCE = "guidance", "Coaching guidance"
        JOURNAL = "journal", "Journal extraction"

    kind = models.CharField(max_length=12, choices=Kind.choices, db_index=True)
    activity = models.ForeignKey(
        "activities.Activity", on_delete=models.CASCADE,
        null=True, blank=True, related_name="analyses",
    )

    input_hash = models.CharField(max_length=64, db_index=True)
    prompt_version = models.CharField(max_length=20)
    model = models.CharField(max_length=60)

    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "AI analyses"
        constraints = [
            models.UniqueConstraint(
                fields=["athlete", "kind", "input_hash"], name="uniq_athlete_kind_hash"
            )
        ]

    def __str__(self):
        return f"{self.kind} {self.created_at:%Y-%m-%d}"
