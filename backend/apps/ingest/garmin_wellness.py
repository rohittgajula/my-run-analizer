"""Pull daily wellness metrics from Garmin Connect.

Written defensively on purpose. Garmin's unofficial endpoints return different shapes
depending on device, subscription tier and whether the watch was worn overnight, and
several return `None` or an empty dict rather than erroring. Every read goes through
`_dig`, and one endpoint failing never aborts the day or the run — a partial row is
far more useful than no row.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from apps.athletes.models import Athlete

from .models import DailyMetrics

logger = logging.getLogger(__name__)


def _dig(payload: Any, *path, default=None):
    """Walk nested dict/list keys, returning default at the first miss."""
    current = payload
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            if not current:
                return default
            current = current[key] if isinstance(key, int) else None
        else:
            return default
    return default if current is None else current


def _int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _humanise(phrase: str) -> str:
    """'RECOVERY_1' -> 'Recovery'. Garmin suffixes a variant number per phrase."""
    if not phrase:
        return ""
    tail = phrase.rsplit("_", 1)[-1]
    base = phrase.rsplit("_", 1)[0] if tail.isdigit() else phrase
    return base.replace("_", " ").title()[:40]


def _local_dt(value) -> dt.datetime | None:
    """Garmin's *TimestampLocal fields are epoch-ms ALREADY shifted to local wall
    time, so reading them as UTC gives the clock reading the athlete saw. Applying a
    timezone on top double-counts the offset — which turned a 02:06 bedtime into
    07:36 and made last night's sleep look like a morning nap."""
    try:
        return dt.datetime.utcfromtimestamp(int(value) / 1000)
    except (TypeError, ValueError, OSError):
        return None


def fetch_day(client, day: dt.date) -> dict:
    """Collect one day's metrics. Each endpoint is isolated so one failure is partial."""
    iso = day.isoformat()
    out: dict = {}
    raw: dict = {}

    def attempt(label, fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — a missing metric is not a sync failure
            logger.debug("garmin %s unavailable for %s: %s", label, iso, exc)
            return None

    sleep = attempt("sleep", lambda: client.get_sleep_data(iso))
    if sleep:
        raw["sleep"] = sleep
        daily = _dig(sleep, "dailySleepDTO", default={}) or {}
        out.update(
            sleep_seconds=_int(daily.get("sleepTimeSeconds")),
            sleep_need_seconds=(
                _int(_dig(daily, "sleepNeed", "actual"))
                or _int(daily.get("sleepNeedSeconds"))
                or _int(_dig(daily, "sleepScores", "totalDuration", "optimalStart"))
            ),
            sleep_score=_int(_dig(daily, "sleepScores", "overall", "value")),
            deep_sleep_seconds=_int(daily.get("deepSleepSeconds")),
            rem_sleep_seconds=_int(daily.get("remSleepSeconds")),
            awake_seconds=_int(daily.get("awakeSleepSeconds")),
            sleep_start_local=_local_dt(daily.get("sleepStartTimestampLocal")),
            sleep_end_local=_local_dt(daily.get("sleepEndTimestampLocal")),
            hrv_overnight_avg=_int(_dig(sleep, "avgOvernightHrv")),
        )

    readiness = attempt("training readiness", lambda: client.get_training_readiness(iso))
    if readiness:
        raw["training_readiness"] = readiness
        first = readiness[0] if isinstance(readiness, list) and readiness else readiness
        out.update(
            training_readiness=_int(_dig(first, "score")),
            training_readiness_level=str(_dig(first, "level", default="") or "")[:32],
        )

    status = attempt("training status", lambda: client.get_training_status(iso))
    if status:
        raw["training_status"] = status
        recent = _dig(status, "mostRecentTrainingStatus", "latestTrainingStatusData",
                      default={}) or {}
        device = next(iter(recent.values()), {}) if isinstance(recent, dict) else {}

        # `trainingStatus` is an opaque numeric code; the feedback phrase is the
        # label Garmin itself shows.
        out["training_status"] = _humanise(
            str(device.get("trainingStatusFeedbackPhrase") or "")
        ) or str(device.get("trainingStatus") or "")[:40]

        acwr = _dig(device, "acuteTrainingLoadDTO", default={}) or {}
        acute = _float(acwr.get("dailyTrainingLoadAcute"))
        chronic = _float(acwr.get("dailyTrainingLoadChronic"))
        percent = _float(acwr.get("acwrPercent"))
        if acute is not None:
            out["acute_load"] = acute
        if chronic is not None:
            out["chronic_load"] = chronic
        # Deliberately NOT derived from acwrPercent when Garmin omits chronic.
        # run-project did that, and on this account it produced exactly 100.0 on
        # every single day — the ratio and the acute value are the same number, so
        # the arithmetic is circular. A constant that looks like a measurement is
        # worse than a gap: ACWR computed from it would always read 0.28, 0.42,
        # 1.02 and so on, i.e. just the acute load with a decimal point moved.

    hrv = attempt("hrv", lambda: client.get_hrv_data(iso))
    if hrv:
        raw["hrv"] = hrv
        out["hrv_status"] = str(_dig(hrv, "hrvSummary", "status", default="") or "")[:24]
        out["hrv_overnight_avg"] = out.get("hrv_overnight_avg") or _int(
            _dig(hrv, "hrvSummary", "lastNightAvg")
        )

    rhr = attempt("resting hr", lambda: client.get_rhr_day(iso))
    if rhr:
        values = _dig(rhr, "allMetrics", "metricsMap",
                      "WELLNESS_RESTING_HEART_RATE", default=[]) or []
        if values:
            out["resting_hr"] = _int(_dig(values, 0, "value"))

    stats = attempt("daily stats", lambda: client.get_stats(iso))
    if stats:
        raw["stats"] = stats
        out.update(
            steps=_int(stats.get("totalSteps")),
            stress_avg=_int(stats.get("averageStressLevel")),
            body_battery_high=_int(stats.get("bodyBatteryHighestValue")),
            body_battery_low=_int(stats.get("bodyBatteryLowestValue")),
            floors_climbed=_int(stats.get("floorsAscended")),
            intensity_minutes=_int(stats.get("moderateIntensityMinutes")),
            spo2_avg=_int(stats.get("averageSpo2")),
            respiration_avg=_float(stats.get("avgWakingRespirationValue")),
        )
        out["resting_hr"] = out.get("resting_hr") or _int(stats.get("restingHeartRate"))

    vo2 = attempt("vo2max", lambda: client.get_max_metrics(iso))
    if vo2:
        raw["max_metrics"] = vo2
        first = vo2[0] if isinstance(vo2, list) and vo2 else vo2
        out["vo2max"] = (
            _float(_dig(first, "generic", "vo2MaxPreciseValue"))
            or _float(_dig(first, "generic", "vo2MaxValue"))
        )

    # Drop empties so an existing row is never overwritten with None by a day where
    # one endpoint happened to fail.
    cleaned = {k: v for k, v in out.items() if v not in (None, "")}
    if raw:
        cleaned["raw"] = raw
    return cleaned


def sync_wellness(athlete: Athlete, client, days: int = 28) -> dict:
    """Upsert the last `days` days of wellness metrics."""
    # athlete.local_today, never timezone.localdate() — at 00:48 in Kolkata the
    # latter still says yesterday and the newest day is silently skipped.
    today = athlete.local_today
    written = empty = 0

    for offset in range(days):
        day = today - dt.timedelta(days=offset)
        try:
            payload = fetch_day(client, day)
        except Exception as exc:  # noqa: BLE001
            if "429" in str(exc):
                logger.warning("rate limited during wellness sync, stopping at %s", day)
                break
            logger.exception("wellness fetch failed for %s", day)
            continue

        if not payload:
            empty += 1
            continue

        DailyMetrics.objects.update_or_create(
            athlete=athlete, metric_date=day, defaults=payload
        )
        written += 1

    return {"days_written": written, "days_empty": empty}
