"""Turning a runway into weeks, and weeks into sessions.

Runs only for dates `calendar.resolve_mode` returned as `build`. Everything else —
race, recovery, mini_taper, maintenance, off_season — is prescribed by mode, because
the week table has no row that is right for those days.

Two rules shape the whole module:

* **Progress running distance, not logged distance.** Ramping the total when 60% of
  it is walking prescribes a load the athlete is not carrying.
* **The safety cap outranks the target.** If the ideal peak cannot be reached inside
  the runway without exceeding the weekly increase limit, the plan reaches what it
  safely can and says so. Inventing a peak you cannot get to is how a plan becomes
  a thing to fail at.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Literal

Runway = Literal["SHORT", "STANDARD", "EXTENDED"]
Phase = Literal["BASE", "FOUNDATION", "AEROBIC", "SPECIFIC", "PEAK", "TAPER", "RACE"]
SessionKind = Literal["REST", "WALK", "RUN_WALK", "EASY", "LONG", "INTERVALS", "TEMPO", "RACE"]

MIN_SAFE_WEEKS = {5.0: 6, 10.0: 8, 21.1: 12, 42.2: 16}
IDEAL_MAX_WEEKS = {5.0: 12, 10.0: 18, 21.1: 22, 42.2: 24}

# Peak weekly RUNNING distance, as a multiple of the race distance. Conservative for
# a beginner: the aim is finishing, not a time.
PEAK_VOLUME_MULTIPLE = 2.2

# Longest CONTINUOUS run, progressed separately from weekly volume.
#
# For a beginner run/walking a 10K this is the number that actually decides the day.
# Weekly kilometres is the conventional lever, but someone running 12 km a week in
# 90-second blocks and someone running 12 km a week in one 40-minute block are not
# in the same place, and only the second can hold a race together.
#
# Capped two ways, whichever is stricter: continuous running is the demand that
# outruns tendons and connective tissue first, and a percentage alone lets a big
# starting block grow absurdly.
MAX_CONTINUOUS_INCREASE_PCT = 10.0
MAX_CONTINUOUS_INCREASE_MIN = 2.0

# Beyond this there is no benefit to a beginner training for a 10K; the long run
# stops progressing and the volume goes elsewhere.
CONTINUOUS_CEILING_MIN = 75.0

TAPER_WEEKS = {5.0: 1, 10.0: 1, 21.1: 2, 42.2: 3}


@dataclass(frozen=True)
class PlanConfig:
    max_weekly_increase_pct: float = 10.0
    cutback_every_n_weeks: int = 4
    cutback_factor: float = 0.7
    max_hard_sessions_per_week: int = 2
    max_long_run_pct_of_week: float = 40.0


@dataclass(frozen=True)
class Baseline:
    """Derived from actual segmented history, never from a questionnaire.

    People misreport training volume, always upward, and a plan built on the reported
    figure starts above the athlete's real fitness on day one.
    """

    run_km_per_week: float
    longest_run_s: float
    run_pace_s_per_km: float
    walk_pace_s_per_km: float
    available_days: dict          # {"0".."6": bool}
    long_run_day: int


@dataclass
class Session:
    date: dt.date
    kind: SessionKind
    run_minutes: float
    walk_minutes: float
    target_run_m: float
    purpose: str
    effort: str
    optional: bool = False
    # Only set on the long run: the unbroken block to aim for inside it. None
    # elsewhere, because prescribing a continuous target on an interval session
    # would contradict the session.
    continuous_target_s: float | None = None

    @property
    def total_minutes(self) -> float:
        return self.run_minutes + self.walk_minutes


@dataclass
class Week:
    index: int              # 0-based from the plan start
    weeks_out: int          # countdown; 0 is race week
    phase: Phase
    start_date: dt.date
    planned_run_km: float
    # The long run's target unbroken block. Progressed separately from volume,
    # because it is the number that decides whether a 10K holds together.
    continuous_target_s: float
    is_cutback: bool
    sessions: list[Session] = field(default_factory=list)


@dataclass
class Plan:
    runway: Runway
    weeks_available: int
    peak_run_km: float
    ideal_peak_run_km: float
    reached_ideal_peak: bool
    peak_continuous_s: float
    race_needs_continuous_s: float
    warnings: list[str]
    weeks: list[Week]

    @property
    def will_run_continuously(self) -> bool:
        """Whether the plan expects the race to be run unbroken."""
        return self.peak_continuous_s >= self.race_needs_continuous_s


def _distance_key(distance_km: float) -> float:
    return min(MIN_SAFE_WEEKS, key=lambda k: abs(k - distance_km))


def classify_runway(weeks: int, distance_km: float) -> Runway:
    key = _distance_key(distance_km)
    if weeks < MIN_SAFE_WEEKS[key]:
        return "SHORT"
    if weeks > IDEAL_MAX_WEEKS[key]:
        return "EXTENDED"
    return "STANDARD"


def allocate_phases(weeks: int, distance_km: float) -> list[Phase]:
    """Proportional allocation with floors, and a deterministic tie-break.

    Deterministic because it must be testable: the invariant is that the phases sum
    to exactly the weeks available, whatever the runway.
    """
    key = _distance_key(distance_km)
    race = 1
    taper = TAPER_WEEKS[key] if weeks > TAPER_WEEKS[key] + 2 else (1 if weeks > 2 else 0)

    remaining = weeks - race - taper
    if remaining <= 0:
        return (["RACE"] * min(weeks, 1)) + ["TAPER"] * max(weeks - 1, 0)

    peak = max(1, round(0.12 * weeks))
    specific = max(2, round(0.28 * weeks))
    aerobic = max(2, round(0.26 * weeks))
    foundation = remaining - peak - specific - aerobic

    # Shave from the largest discretionary block until foundation reaches its floor.
    while foundation < 2 and (specific > 2 or aerobic > 2 or peak > 1):
        if specific >= aerobic and specific > 2:
            specific -= 1
        elif aerobic > 2:
            aerobic -= 1
        elif peak > 1:
            peak -= 1
        else:
            break
        foundation += 1

    # A short runway can still overflow. Trim from the front — foundation is the most
    # expendable, since the athlete already has whatever base they have.
    overflow = (foundation + aerobic + specific + peak) - remaining
    while overflow > 0:
        if foundation > 0:
            foundation -= 1
        elif aerobic > 2:
            aerobic -= 1
        elif specific > 2:
            specific -= 1
        elif peak > 1:
            peak -= 1
        else:
            break
        overflow -= 1

    phases: list[Phase] = (
        ["FOUNDATION"] * max(foundation, 0)
        + ["AEROBIC"] * aerobic
        + ["SPECIFIC"] * specific
        + ["PEAK"] * peak
        + ["TAPER"] * taper
        + ["RACE"] * race
    )
    return phases[:weeks] if len(phases) > weeks else phases


def _round_down(value: float) -> float:
    """Round DOWN to 0.1 km.

    Rounding to nearest broke the cap at low volumes: 3.5 km x 1.10 is 3.85, which
    rounds to 3.9 — an 11.4% week-on-week rise against a 10% limit. At these volumes
    the rounding is the same size as the increment, so it has to round the safe way.
    """
    return math.floor(value * 10) / 10


def _volume_curve(
    weeks: list[Phase], baseline_km: float, ideal_peak_km: float, config: PlanConfig
) -> tuple[list[float], float, bool]:
    """Weekly running volume, capped by the weekly increase limit.

    Returns (volumes, achieved_peak, reached_ideal). The cap is not negotiable: if
    the ideal peak is unreachable inside the runway, the plan tops out lower.
    """
    growth = 1 + config.max_weekly_increase_pct / 100
    volumes: list[float] = []
    # Rounded at the source: week 0 appends this directly, and an unrounded
    # baseline surfaced as '5.25707 km' in the plan table.
    current = _round_down(max(baseline_km, 1.0))
    build_index = 0

    for index, phase in enumerate(weeks):
        if phase == "RACE":
            volumes.append(_round_down(current * 0.3))
            continue
        if phase == "TAPER":
            # Two taper weeks step 60% then 40%; a single one takes 60%.
            taper_positions = [i for i, p in enumerate(weeks) if p == "TAPER"]
            step = taper_positions.index(index)
            volumes.append(_round_down(current * (0.6 if step == 0 else 0.4)))
            continue

        build_index += 1
        # Cutback weeks are where adaptation actually happens; they are not optional.
        if build_index > 1 and build_index % config.cutback_every_n_weeks == 0:
            volumes.append(_round_down(current * config.cutback_factor))
            continue

        if build_index > 1:
            # Round the TRAJECTORY, not just the displayed figure. Carrying an
            # unrounded current while showing its floor made 3.8 -> 4.2 look like a
            # 10.5% rise against a 10% cap: the displayed step was larger than the
            # real one. Rounding down here means every printed step is genuinely
            # within the limit.
            current = _round_down(min(current * growth, ideal_peak_km))
        volumes.append(current)

    build_volumes = [v for v, p in zip(volumes, weeks) if p not in ("TAPER", "RACE")]
    achieved = max(build_volumes) if build_volumes else baseline_km
    return volumes, achieved, achieved >= ideal_peak_km - 0.05


def _continuous_curve(
    phases: list[Phase], baseline_s: float, config: PlanConfig
) -> tuple[list[float], float]:
    """Per-week target for the long run's unbroken block.

    Progresses on its own schedule rather than riding the volume curve. The two come
    apart badly for a beginner: adding a fourth short session raises weekly volume
    without moving continuous capacity at all, and continuous capacity is what
    decides whether a 10K holds together.

    Returns (per-week targets, peak capability). The peak is the CAPABILITY reached,
    not the highest prescribed value — a cutback week prescribes less without
    unlearning anything.
    """
    growth = 1 + MAX_CONTINUOUS_INCREASE_PCT / 100
    ceiling = CONTINUOUS_CEILING_MIN * 60
    capability = max(baseline_s, 120.0)   # floor: everyone can run two minutes
    targets: list[float] = []
    build_index = 0

    for index, phase in enumerate(phases):
        if phase == "RACE":
            targets.append(0.0)
            continue
        if phase == "TAPER":
            # Hold capability, prescribe less of it. A taper is not detraining.
            targets.append(round(capability * 0.6))
            continue

        build_index += 1
        is_cutback = build_index > 1 and build_index % config.cutback_every_n_weeks == 0

        # Capability advances only on weeks that actually load it. Growing it through
        # a cutback bankrolled an increment nobody trained for, so the week after a
        # down week jumped by two steps at once — 363 s to 439 s, a 21% rise against
        # a 10% cap.
        if build_index > 1 and not is_cutback:
            capability = min(
                capability * growth,
                capability + MAX_CONTINUOUS_INCREASE_MIN * 60,
                ceiling,
            )

        # A cutback prescribes less without unlearning anything: capability is held.
        targets.append(round(capability * 0.7 if is_cutback else capability))

    return targets, capability


# How a week's running volume splits across its sessions, and how much walking rides
# along. Early phases are mostly run/walk; later ones hold more continuous running.
PHASE_SHAPE: dict[Phase, dict] = {
    "BASE":       {"long_share": 0.35, "run_walk_ratio": 0.4, "hard": 0},
    "FOUNDATION": {"long_share": 0.35, "run_walk_ratio": 0.4, "hard": 0},
    "AEROBIC":    {"long_share": 0.38, "run_walk_ratio": 0.55, "hard": 1},
    "SPECIFIC":   {"long_share": 0.40, "run_walk_ratio": 0.7, "hard": 2},
    "PEAK":       {"long_share": 0.42, "run_walk_ratio": 0.8, "hard": 2},
    "TAPER":      {"long_share": 0.35, "run_walk_ratio": 0.8, "hard": 1},
    "RACE":       {"long_share": 1.0, "run_walk_ratio": 0.9, "hard": 0},
}

PURPOSE = {
    "LONG": "Time on feet. The session that grows your longest continuous run.",
    "RUN_WALK": "Aerobic volume at an easy effort, taken in run/walk blocks.",
    "EASY": "Easy aerobic running. Conversational throughout.",
    "INTERVALS": "Controlled faster running, kept short on purpose.",
    "TEMPO": "Sustained comfortably-hard effort.",
    "RACE": "Race day.",
    "WALK": "Optional walk. Movement without load.",
    "REST": "Rest.",
}


def _offset_for(week_start: dt.date, weekday: int) -> int:
    """Days from the week's start date to the next occurrence of `weekday`.

    available_days is keyed by WEEKDAY (0 = Monday), but a plan does not begin on a
    Monday. Adding the weekday index directly to the start date put the long run on
    a Thursday for a plan starting on a Friday, and every other session with it.
    """
    return (weekday - week_start.weekday()) % 7


def _lay_out_week(
    week: Week, baseline: Baseline, config: PlanConfig
) -> list[Session]:
    """Place the week's volume on the athlete's own available days.

    Hard sessions never land on consecutive days, and the long run goes on the day
    they said they have time for it.
    """
    shape = PHASE_SHAPE[week.phase]
    available = [d for d in range(7) if baseline.available_days.get(str(d), False)]
    if not available:
        return []

    if week.phase == "RACE":
        race_day = baseline.long_run_day if baseline.long_run_day in available else available[-1]
        return [
            Session(
                date=week.start_date + dt.timedelta(days=_offset_for(week.start_date, race_day)),
                kind="RACE",
                run_minutes=0.0, walk_minutes=0.0, target_run_m=0.0,
                purpose=PURPOSE["RACE"], effort="Race effort",
            )
        ]

    long_day = baseline.long_run_day if baseline.long_run_day in available else available[-1]
    others = [d for d in available if d != long_day]

    long_km = min(
        week.planned_run_km * shape["long_share"],
        week.planned_run_km * config.max_long_run_pct_of_week / 100,
    )
    remaining_km = max(week.planned_run_km - long_km, 0.0)
    per_session_km = remaining_km / len(others) if others else 0.0

    hard_budget = min(shape["hard"], config.max_hard_sessions_per_week - 1)  # long counts as one
    sessions: list[Session] = []
    last_hard_day: int | None = None

    for day in others:
        kind: SessionKind = "RUN_WALK" if shape["run_walk_ratio"] < 0.6 else "EASY"
        effort = "Easy — conversational"

        consecutive = (
            last_hard_day is not None
            and _offset_for(week.start_date, day) - _offset_for(week.start_date, last_hard_day) <= 1
        )
        if hard_budget > 0 and not consecutive and day != long_day:
            kind = "INTERVALS" if week.phase in ("AEROBIC", "SPECIFIC") else "TEMPO"
            effort = "Controlled hard — you should not be gasping"
            hard_budget -= 1
            last_hard_day = day

        sessions.append(_session(week, day, kind, per_session_km, shape, baseline, effort))

    long_run = _session(week, long_day, "LONG", long_km, shape, baseline, "Easy throughout")
    long_run.continuous_target_s = week.continuous_target_s
    if week.continuous_target_s:
        long_run.purpose = (
            f"Time on feet. Aim for one unbroken block of about "
            f"{week.continuous_target_s / 60:.0f} minutes inside it — that block is "
            "what decides whether race day holds together."
        )
    sessions.append(long_run)

    # Non-training days become an optional walk with real numbers rather than a dash:
    # a rest day that says "optional walk" and shows nothing is not a prescription.
    for day in range(7):
        if day not in available:
            sessions.append(
                Session(
                    date=week.start_date + dt.timedelta(days=_offset_for(week.start_date, day)),
                    kind="WALK",
                    run_minutes=0.0, walk_minutes=25.0,
                    target_run_m=0.0,
                    purpose=PURPOSE["WALK"],
                    effort="Very easy",
                    optional=True,
                )
            )

    return sorted(sessions, key=lambda s: s.date)


def _session(
    week: Week, day: int, kind: SessionKind, run_km: float,
    shape: dict, baseline: Baseline, effort: str,
) -> Session:
    run_minutes = run_km * baseline.run_pace_s_per_km / 60
    ratio = shape["run_walk_ratio"]
    # Every minute is accounted for as running or walking. Leaving walk at zero on a
    # run/walk session is why run-project showed a blank RUN TIME on every long run.
    walk_minutes = run_minutes * (1 - ratio) / ratio if ratio > 0 else 0.0

    return Session(
        date=week.start_date + dt.timedelta(days=_offset_for(week.start_date, day)),
        kind=kind,
        run_minutes=round(run_minutes, 1),
        walk_minutes=round(walk_minutes, 1),
        target_run_m=round(run_km * 1000),
        purpose=PURPOSE[kind],
        effort=effort,
    )


def generate_plan(
    plan_start: dt.date,
    race_date: dt.date,
    race_km: float,
    baseline: Baseline,
    config: PlanConfig | None = None,
) -> Plan:
    config = config or PlanConfig()
    days = (race_date - plan_start).days
    if days < 0:
        raise ValueError("The race is in the past.")

    weeks_available = max((days // 7) + 1, 1)
    runway = classify_runway(weeks_available, race_km)
    warnings: list[str] = []

    phases = allocate_phases(weeks_available, race_km)
    if runway == "EXTENDED":
        key = _distance_key(race_km)
        base_weeks = weeks_available - IDEAL_MAX_WEEKS[key]
        # Prepend maintenance rather than diluting the ramp across the whole runway.
        phases = ["BASE"] * base_weeks + allocate_phases(IDEAL_MAX_WEEKS[key], race_km)
        warnings.append(
            f"{weeks_available} weeks is longer than a {race_km:g} km build needs. "
            f"The first {base_weeks} weeks hold steady before the ramp begins."
        )
    elif runway == "SHORT":
        warnings.append(
            f"{weeks_available} weeks is less than the {MIN_SAFE_WEEKS[_distance_key(race_km)]} "
            "usually wanted for this distance. The plan builds what it safely can — "
            "expect to finish with run/walk rather than to race it."
        )

    ideal_peak = race_km * PEAK_VOLUME_MULTIPLE
    volumes, achieved_peak, reached = _volume_curve(phases, baseline.run_km_per_week, ideal_peak, config)
    continuous, peak_continuous = _continuous_curve(phases, baseline.longest_run_s, config)

    # What running the race unbroken would actually take, at this athlete's own pace.
    race_needs_s = race_km * baseline.run_pace_s_per_km
    if peak_continuous < race_needs_s:
        warnings.append(
            f"Your longest unbroken run is projected to reach "
            f"{peak_continuous / 60:.0f} minutes by race day, against the "
            f"{race_needs_s / 60:.0f} minutes running {race_km:g} km non-stop would take "
            f"at your current pace. Expect to run/walk this one — that is a finish, "
            "not a failure."
        )

    if not reached:
        warnings.append(
            f"Starting from {baseline.run_km_per_week:.1f} km of running a week, the "
            f"{config.max_weekly_increase_pct:g}% weekly cap tops this plan out at "
            f"{achieved_peak:.1f} km rather than the {ideal_peak:.1f} km a "
            f"{race_km:g} km build would ideally reach. Raising it faster is how people "
            "get injured, so the cap wins."
        )

    weeks: list[Week] = []
    for index, (phase, volume) in enumerate(zip(phases, volumes)):
        start = plan_start + dt.timedelta(days=index * 7)
        week = Week(
            index=index,
            weeks_out=weeks_available - index - 1,
            phase=phase,
            start_date=start,
            planned_run_km=volume,
            continuous_target_s=continuous[index],
            is_cutback=index > 0 and volume < volumes[index - 1],
        )
        week.sessions = _lay_out_week(week, baseline, config)
        weeks.append(week)

    return Plan(
        runway=runway,
        weeks_available=weeks_available,
        peak_run_km=achieved_peak,
        ideal_peak_run_km=round(ideal_peak, 1),
        reached_ideal_peak=reached,
        peak_continuous_s=round(peak_continuous),
        race_needs_continuous_s=round(race_needs_s),
        warnings=warnings,
        weeks=weeks,
    )
