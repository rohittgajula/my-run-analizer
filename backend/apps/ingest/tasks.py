"""Garmin sync, on a schedule.

Garmin rate-limits by **IP**, and every athlete's sync leaves from this one server.
Three consequences shape everything here, all from docs/HOSTING.md:

* the Garmin queue runs at concurrency 1, so syncs never overlap;
* athletes are staggered rather than all fired at 05:30;
* a 429 stops the whole queue rather than moving to the next athlete, because the
  limit is on the address and continuing lengthens the block for everyone.
"""

from __future__ import annotations

import logging
import random

from celery import shared_task
from django.core.cache import cache

from apps.athletes.models import Athlete

from .garmin import GarminAuthError, GarminRateLimited, sync_athlete

logger = logging.getLogger(__name__)

# Set when Garmin rate-limits us. Shared through Redis so every worker sees it.
BREAKER_KEY = "garmin:blocked_until"
BREAKER_SECONDS = 45 * 60


def garmin_blocked() -> bool:
    return bool(cache.get(BREAKER_KEY))


def trip_breaker(reason: str) -> None:
    logger.warning("garmin circuit breaker tripped: %s", reason)
    cache.set(BREAKER_KEY, reason, BREAKER_SECONDS)


@shared_task(name="ingest.sync_one", bind=True, max_retries=2)
def sync_one(self, athlete_id: int) -> dict:
    """Sync one athlete. Safe to re-run — ingestion is idempotent on two layers."""
    if garmin_blocked():
        logger.info("skipping sync for %s: breaker open", athlete_id)
        return {"skipped": "rate_limited"}

    athlete = Athlete.objects.filter(pk=athlete_id, garmin_connected=True).first()
    if athlete is None:
        return {"skipped": "not_connected"}

    try:
        return sync_athlete(athlete).as_dict()
    except GarminRateLimited as exc:
        trip_breaker(str(exc))
        return {"skipped": "rate_limited"}
    except GarminAuthError as exc:
        # A dead token is not retryable — retrying just burns requests against an
        # address Garmin is already watching. The athlete must reconnect.
        logger.warning("garmin auth failed for %s: %s", athlete_id, exc)
        athlete.garmin_connected = False
        athlete.save(update_fields=["garmin_connected"])
        return {"error": "auth"}


@shared_task(name="ingest.sync_all")
def sync_all() -> dict:
    """Queue every connected athlete, spread across the hour."""
    if garmin_blocked():
        return {"skipped": "rate_limited"}

    ids = list(
        Athlete.objects.filter(garmin_connected=True).values_list("pk", flat=True)
    )
    for index, athlete_id in enumerate(ids):
        # Deterministic spacing plus jitter: ten athletes at 05:30 is ten bursts from
        # one IP inside a minute, which is what the limiter is looking for.
        delay = index * 180 + random.randint(0, 60)
        sync_one.apply_async((athlete_id,), countdown=delay)

    return {"queued": len(ids)}
