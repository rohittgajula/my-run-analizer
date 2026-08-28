"""Deriving metrics, on a schedule.

Separate from ingestion on purpose: segmentation is pure CPU and needs no network, so
a Garmin rate limit must never stop it, and re-deriving history after an algorithm
change must not touch Garmin at all.
"""

from __future__ import annotations

import logging

from celery import shared_task

from analysis.segmentation import ALGORITHM_VERSION

from .models import Activity
from .services import derive

logger = logging.getLogger(__name__)


@shared_task(name="activities.derive_one")
def derive_one(activity_id: int) -> dict:
    activity = Activity.objects.filter(pk=activity_id).first()
    if activity is None:
        return {"skipped": "gone"}

    metrics = derive(activity)
    return {"activity": activity_id, "segmented": metrics is not None}


@shared_task(name="activities.derive_stale")
def derive_stale(limit: int = 200) -> dict:
    """Anything not yet seen by the current algorithm version.

    This is why segmentation_version is an integer rather than a boolean: bump the
    version, and history re-derives itself without anyone remembering to run a command.
    """
    stale = Activity.objects.exclude(segmentation_version=ALGORITHM_VERSION)[:limit]
    for activity in stale:
        derive_one.delay(activity.pk)
    return {"queued": len(stale)}
