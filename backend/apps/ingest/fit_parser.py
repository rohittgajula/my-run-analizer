"""FIT decoding.

The FIT file carries far more than the Garmin Connect summary: a 28-minute activity
returns a two-lap summary from the API but contains ~1,670 per-second records in the
file. That per-second series is the only thing that makes run/walk segmentation
possible, so parsing happens from the file and never from the API summary.

This module produces plain data and imports nothing from the rest of the app. It does
not know what segmentation is; segmentation consumes what it returns.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from fitparse import FitFile

# FIT stores coordinates as semicircles: degrees = semicircles * 180 / 2^31.
SEMICIRCLE_TO_DEGREES = 180.0 / 2**31


@dataclass(slots=True)
class ParsedRecord:
    """One per-second sample. Every optional field stays None when unmeasured.

    None and 0.0 must never be conflated — a missing cadence reading is not a cadence
    of zero, and treating it as one turns absent data into a confident false trend.
    """

    offset_s: float
    distance_m: float | None = None
    speed_mps: float | None = None
    cadence_spm: float | None = None
    heart_rate: int | None = None
    altitude_m: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    power_w: float | None = None
    vertical_oscillation_mm: float | None = None
    ground_contact_ms: float | None = None
    stride_length_m: float | None = None
    vertical_ratio: float | None = None
    respiration_rate: float | None = None
    temperature_c: float | None = None


@dataclass
class ParsedActivity:
    sport: str = "running"
    started_at: dt.datetime | None = None
    total_distance_m: float = 0.0
    total_timer_s: float = 0.0
    total_elapsed_s: float = 0.0
    avg_hr: int | None = None
    max_hr: int | None = None
    avg_cadence_spm: float | None = None
    total_ascent_m: float | None = None
    total_descent_m: float | None = None
    calories: int | None = None
    records: list[ParsedRecord] = field(default_factory=list)


def _value(message, name: str) -> Any:
    data = message.get(name)
    return data.value if data else None


def _full_cadence(record: dict) -> float | None:
    """FIT stores running cadence per leg; double it for true steps per minute.

    `fractional_cadence` carries the half step, so 84.5 rpm is 169 spm. Getting this
    wrong halves every cadence in the system, which would put every run below the
    140 spm running threshold and classify the entire activity as walking.
    """
    cadence = record.get("cadence")
    if cadence is None:
        return None
    return (cadence + (record.get("fractional_cadence") or 0.0)) * 2


def _semicircles(raw) -> float | None:
    # `if raw` would drop a legitimate 0, which is the prime meridian / equator.
    return raw * SEMICIRCLE_TO_DEGREES if raw is not None else None


def _mm_to_m(raw) -> float | None:
    return raw / 1000.0 if raw is not None else None


def parse(path_or_fileobj) -> ParsedActivity:
    fit = FitFile(path_or_fileobj)
    parsed = ParsedActivity()

    for session in fit.get_messages("session"):
        parsed.sport = _value(session, "sport") or "running"
        parsed.started_at = _value(session, "start_time")
        parsed.total_distance_m = _value(session, "total_distance") or 0.0
        parsed.total_timer_s = _value(session, "total_timer_time") or 0.0
        parsed.total_elapsed_s = _value(session, "total_elapsed_time") or 0.0
        parsed.avg_hr = _value(session, "avg_heart_rate")
        parsed.max_hr = _value(session, "max_heart_rate")
        parsed.total_ascent_m = _value(session, "total_ascent")
        parsed.total_descent_m = _value(session, "total_descent")
        parsed.calories = _value(session, "total_calories")
        average_cadence = _value(session, "avg_running_cadence")
        if average_cadence is not None:
            parsed.avg_cadence_spm = average_cadence * 2
        break  # one session per file for a normal activity

    raw_records = [{d.name: d.value for d in message} for message in fit.get_messages("record")]
    if not raw_records:
        return parsed

    first_timestamp = raw_records[0].get("timestamp")
    if parsed.started_at is None:
        parsed.started_at = first_timestamp

    for record in raw_records:
        timestamp = record.get("timestamp")
        if timestamp is None or first_timestamp is None:
            continue

        parsed.records.append(
            ParsedRecord(
                offset_s=(timestamp - first_timestamp).total_seconds(),
                distance_m=record.get("distance"),
                speed_mps=record.get("enhanced_speed") or record.get("speed"),
                cadence_spm=_full_cadence(record),
                heart_rate=record.get("heart_rate"),
                altitude_m=record.get("enhanced_altitude") or record.get("altitude"),
                latitude=_semicircles(record.get("position_lat")),
                longitude=_semicircles(record.get("position_long")),
                power_w=record.get("power"),
                vertical_oscillation_mm=record.get("vertical_oscillation"),
                ground_contact_ms=record.get("stance_time"),
                stride_length_m=_mm_to_m(record.get("step_length")),
                vertical_ratio=record.get("vertical_ratio"),
                respiration_rate=(
                    record.get("respiration_rate")
                    or record.get("enhanced_respiration_rate")
                ),
                temperature_c=record.get("temperature"),
            )
        )

    derive_missing_totals(parsed)
    return parsed


def derive_missing_totals(parsed: ParsedActivity) -> ParsedActivity:
    """Fill totals a truncated or session-less file did not provide.

    Split out so it is testable without a real .fit, and because a stored 0.0 reads
    downstream as a genuine measurement of zero rather than as absent data.
    """
    if parsed.total_distance_m == 0.0:
        distances = [r.distance_m for r in parsed.records if r.distance_m is not None]
        if distances:
            parsed.total_distance_m = max(distances)

    if parsed.total_elapsed_s == 0.0 and parsed.records:
        parsed.total_elapsed_s = parsed.records[-1].offset_s

    return parsed
