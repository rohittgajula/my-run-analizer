"""Training load.

A transparent, versioned model. It is NOT Garmin's proprietary training load and must
never be presented as such — call it "Custom Training Load" in every user-facing
string, so a number that disagrees with the watch reads as a different measure rather
than as a bug.

Version the formula. Without that, a load figure silently means two different things
at two points in your own database, and the trend across the change is meaningless.
"""

from __future__ import annotations

LOAD_FORMULA_VERSION = "v1"

# Running costs roughly twice what walking does per minute for a beginner. Crude,
# deliberately: a defensible simple model beats an impressive one nobody can check.
RUN_EFFORT = 2.0
WALK_EFFORT = 1.0


def session_load(run_minutes: float, walk_minutes: float) -> float:
    """Duration × effort factor, split by what was actually run rather than logged."""
    return round(run_minutes * RUN_EFFORT + walk_minutes * WALK_EFFORT, 1)


def rolling_load(daily_loads: dict, end_date, days: int) -> float:
    """Sum of load over the `days` ending at `end_date` inclusive.

    Takes a plain {date: load} mapping so this stays free of Django and testable
    without a database.
    """
    import datetime as dt

    total = 0.0
    for offset in range(days):
        total += daily_loads.get(end_date - dt.timedelta(days=offset), 0.0)
    return round(total, 1)
