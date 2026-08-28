"""Garmin Connect sync.

Garmin has no personal API — the Connect Developer Program requires a legal entity,
rejects personal use, and is currently on hold — so this rides the unofficial
`garminconnect` client against a saved OAuth token. Three consequences shape it:

1. Auth can fail at any time (expired token, revoked session, IP rate limit). Every
   failure is classified and surfaced verbatim, because a sync that silently reports
   success is worse than one that visibly fails.
2. Downloads are the ORIGINAL .fit file, not the JSON summary. The summary has no
   per-second series, so it cannot support run/walk segmentation.
3. Garmin rate-limits by IP, and on a hosted multi-athlete deployment every sync
   leaves from one address. A 429 is therefore treated as a stop signal for the whole
   run, not something to retry past — continuing lengthens the block for everyone.
   See docs/HOSTING.md.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.athletes.models import Athlete

from .models import RawFitFile
from .services import DuplicateActivity, ingest_fit

logger = logging.getLogger(__name__)


class GarminAuthError(Exception):
    """Token missing, expired, or rejected. The athlete must connect again."""


class GarminRateLimited(Exception):
    """Garmin returned 429. Back off; retrying immediately makes it worse."""


@dataclass
class SyncResult:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    activity_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "imported": self.imported,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors,
            "activity_ids": self.activity_ids,
        }


def _client(athlete: Athlete):
    from garminconnect import Garmin

    token_dir = Path(athlete.token_dir)
    # garth writes several files here. An empty directory means a login that claimed
    # to succeed actually wrote nothing — a real failure mode, not a hypothetical.
    if not token_dir.is_dir() or not any(token_dir.iterdir()):
        raise GarminAuthError(
            "No Garmin session found. Connect your Garmin account first."
        )

    client = Garmin()
    try:
        client.login(str(token_dir))
    except Exception as exc:  # noqa: BLE001 — classify, then re-raise
        message = str(exc)
        if "429" in message or "TooManyRequests" in message:
            raise GarminRateLimited(f"Garmin rate-limited this network: {message}") from exc
        raise GarminAuthError(f"Garmin rejected the saved session: {message}") from exc
    return client


def _extract_fit(payload: bytes) -> tuple[bytes, str] | None:
    """ORIGINAL downloads arrive as a zip containing one .fit."""
    if payload[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".fit"):
                    return archive.read(name), Path(name).name
        return None
    # Some endpoints hand back the .fit directly.
    if payload[8:12] == b".FIT":
        return payload, "activity.fit"
    return None


def sync_athlete(athlete: Athlete, limit: int = 20) -> SyncResult:
    """Pull recent activities and ingest any that are new.

    Idempotent on two independent levels — Garmin's activity id and the file's content
    hash — so re-running is always safe and never duplicates. Two layers rather than
    one because either can fail alone: a manual upload has no Garmin id, and Garmin
    could in principle renumber.
    """
    from garminconnect import Garmin

    result = SyncResult()
    client = _client(athlete)

    try:
        listing = client.get_activities(0, limit)
    except Exception as exc:  # noqa: BLE001
        if "429" in str(exc):
            raise GarminRateLimited(str(exc)) from exc
        raise

    from apps.activities.models import Activity

    known = set(
        Activity.objects.filter(athlete=athlete, garmin_activity_id__isnull=False)
        .values_list("garmin_activity_id", flat=True)
    )

    for entry in listing:
        activity_id = entry.get("activityId")
        if activity_id is None:
            continue
        if activity_id in known:
            result.skipped += 1
            continue

        try:
            payload = client.download_activity(
                activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
            )
            extracted = _extract_fit(payload)
            if extracted is None:
                result.failed += 1
                result.errors.append(f"{activity_id}: download was not a .fit file")
                continue

            data, filename = extracted
            digest = RawFitFile.hash_bytes(data)
            # Second idempotency layer: the same bytes, however they arrived.
            if RawFitFile.objects.filter(athlete=athlete, sha256=digest).exists():
                result.skipped += 1
                continue

            raw = RawFitFile.objects.create(
                athlete=athlete,
                file=ContentFile(data, name=f"{activity_id}_{filename}"),
                original_name=filename,
                sha256=digest,
                size_bytes=len(data),
            )
            activity = ingest_fit(raw, garmin_activity_id=activity_id)
            result.imported += 1
            result.activity_ids.append(activity.pk)

        except DuplicateActivity:
            result.skipped += 1
        except Exception as exc:  # noqa: BLE001 — one bad activity must not stop the sync
            if "429" in str(exc):
                result.errors.append("Garmin rate-limited the download; stopping early.")
                break
            logger.exception("garmin sync failed for activity %s", activity_id)
            result.failed += 1
            result.errors.append(f"{activity_id}: {exc}")

    athlete.garmin_connected = True
    athlete.garmin_last_sync = timezone.now()
    athlete.save(update_fields=["garmin_connected", "garmin_last_sync"])
    return result


def check_connection(athlete: Athlete) -> dict:
    """Cheap probe for real connection state.

    Deliberately does not trust the stored `garmin_connected` flag — it re-checks,
    because the failure mode here is a token that looks present but no longer works.
    """
    try:
        client = _client(athlete)
        return {
            "connected": True,
            "name": client.get_full_name(),
            "error": "",
            "last_sync": athlete.garmin_last_sync,
        }
    except (GarminAuthError, GarminRateLimited) as exc:
        return {"connected": False, "name": "", "error": str(exc),
                "last_sync": athlete.garmin_last_sync}
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "name": "", "error": str(exc),
                "last_sync": athlete.garmin_last_sync}
