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
