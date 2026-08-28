"""Connect a Garmin account from the UI.

Handling someone's Garmin password deserves stating plainly, because the safe version
and the careless version look identical from the outside:

* The password is used once, to exchange for an OAuth token, and is never written to
  the database, a file, or a log. It exists only as a local variable for the duration
  of one request and is deleted immediately afterwards.
* Only the refreshable token is persisted, in a directory scoped to that one athlete.
* Nothing here echoes the password back, including in error messages — the library's
  exception text is passed through, and Garmin does not include it.
* This is fine over localhost. Behind a real domain it must be HTTPS-only, which is a
  deployment concern rather than something this module can enforce.

MFA needs a second round trip carrying library state that cannot be safely parked
between stateless requests, so an MFA account is told so rather than handed a flow
that silently half-works.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.utils import timezone

from .garmin import GarminAuthError, GarminRateLimited

logger = logging.getLogger(__name__)


class MFARequired(Exception):
    """Account needs a code; this flow cannot carry the state to finish it."""


def connect(athlete, email: str, password: str) -> dict:
    """Exchange credentials for a stored token. Returns a status dict."""
    from garminconnect import Garmin

    token_dir = Path(athlete.token_dir)
    token_dir.mkdir(parents=True, exist_ok=True)

    # return_on_mfa is left at its default of False so the library reaches its own
    # dump() call. garmin-mcp's CLI sets it True, which is precisely why that path
    # logs in successfully and then writes no token at all.
    client = Garmin(email=email, password=password)

    try:
        result = client.login(str(token_dir))
        if isinstance(result, tuple) and result and result[0] == "needs_mfa":
            raise MFARequired(
                "This account uses multi-factor authentication, which needs a second "
                "step this page cannot carry."
            )
    except MFARequired:
        raise
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "429" in message or "TooManyRequests" in message:
            raise GarminRateLimited(
                "Garmin is rate-limiting this network. Wait 15–60 minutes and try again."
            ) from exc
        if "MFA" in message.upper():
            raise MFARequired(
                "This account uses multi-factor authentication, which is not supported yet."
            ) from exc
        raise GarminAuthError(f"Garmin rejected the sign-in: {message}") from exc
    finally:
        # Drop the credential as soon as it has served its purpose.
        del password

    # A login can 'succeed' and still write nothing — that is the bug this whole
    # module exists to avoid — so success is confirmed against the filesystem.
    written = sorted(p.name for p in token_dir.iterdir() if p.is_file())
    if not written:
        raise GarminAuthError(
            "Sign-in returned without error but no session token was written. "
            "Treat this as a failure and try again."
        )

    name = ""
    try:
        name = client.get_full_name() or ""
    except Exception:  # noqa: BLE001 — tokens exist; a failed probe is not fatal
        logger.warning("token written but the profile probe failed")

    athlete.garmin_connected = True
    athlete.save(update_fields=["garmin_connected"])
    return {"connected": True, "name": name, "token_files": len(written)}


def disconnect(athlete) -> dict:
    """Remove the stored token. The password was never held, so there is nothing else."""
    token_dir = Path(athlete.token_dir)
    removed = 0
    if token_dir.is_dir():
        for path in token_dir.iterdir():
            if path.is_file():
                path.unlink()
                removed += 1

    athlete.garmin_connected = False
    athlete.garmin_last_sync = None
    athlete.save(update_fields=["garmin_connected", "garmin_last_sync"])
    return {"connected": False, "removed": removed}
