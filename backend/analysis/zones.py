"""Heart-rate zones.

Uses the **heart-rate reserve** (Karvonen) method rather than a plain percentage of
maximum, because it accounts for resting heart rate — and resting heart rate is a real
measurement this system already holds, updated nightly by Garmin. Percentage-of-max
ignores it and puts a fit athlete and an unfit one in the same zones at the same
number.

    HRR = max - resting
    zone bound = resting + HRR x fraction

**No 220-age anywhere.** That formula has a standard deviation of ±10-12 bpm across
individuals, which is wide enough to put someone a full zone out. Where a measured
maximum is unavailable the zones are simply not shown — the same rule the rest of this
project follows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

ZoneName = Literal["Z1", "Z2", "Z3", "Z4", "Z5"]

# Lower and upper bound as a fraction of heart-rate reserve.
ZONE_BOUNDS: dict[ZoneName, tuple[float, float]] = {
    "Z1": (0.50, 0.60),
    "Z2": (0.60, 0.70),
    "Z3": (0.70, 0.80),
    "Z4": (0.80, 0.90),
    "Z5": (0.90, 1.00),
}

ZONE_PURPOSE: dict[ZoneName, str] = {
    "Z1": "Recovery. Easy enough that it costs you nothing.",
    "Z2": "Aerobic base. The zone that builds endurance, and the one most beginners "
          "skip by running everything slightly too hard.",
    "Z3": "Steady. Useful in small amounts, but it is where easy runs drift to when "
          "you are not paying attention.",
    "Z4": "Threshold. Hard, controlled, and sparing.",
    "Z5": "Maximum. Short intervals only.",
}

ZONE_LABEL: dict[ZoneName, str] = {
    "Z1": "Recovery", "Z2": "Aerobic base", "Z3": "Steady",
    "Z4": "Threshold", "Z5": "Maximum",
}


@dataclass(frozen=True)
class Zone:
    name: ZoneName
    label: str
    low: int
    high: int
    purpose: str


@dataclass(frozen=True)
class Zones:
    resting_hr: int
    max_hr: int
    max_source: str        # how the maximum was arrived at — shown, never hidden
    zones: list[Zone]

    def of(self, heart_rate: int | None) -> ZoneName | None:
        if heart_rate is None:
            return None
        if heart_rate < self.zones[0].low:
            return None          # below Z1 is not a training zone, it is sitting down
        for zone in self.zones:
            if heart_rate <= zone.high:
                return zone.name
        return "Z5"

    def band(self, name: ZoneName) -> Zone:
        return next(z for z in self.zones if z.name == name)


def build(resting_hr: int, max_hr: int, max_source: str = "measured") -> Zones | None:
    """None when the inputs cannot support zones, rather than a plausible guess."""
    if not resting_hr or not max_hr or max_hr - resting_hr < 40:
        return None

    reserve = max_hr - resting_hr
    zones = [
        Zone(
            name=name,
            label=ZONE_LABEL[name],
            low=round(resting_hr + reserve * low),
            high=round(resting_hr + reserve * high),
            purpose=ZONE_PURPOSE[name],
        )
        for name, (low, high) in ZONE_BOUNDS.items()
    ]
    return Zones(resting_hr=resting_hr, max_hr=max_hr, max_source=max_source, zones=zones)


def time_in_zones(
    samples: Iterable[tuple[float, int | None]], zones: Zones
) -> dict[str, float]:
    """Seconds spent in each zone, from (offset_s, heart_rate) pairs.

    Weighted by the real gap between samples rather than counting them: Garmin drops
    to smart recording on longer activities, and counting samples would then under-report
    exactly the long steady efforts that matter most for aerobic base.
    """
    ordered = sorted(samples, key=lambda pair: pair[0])
    totals: dict[str, float] = {name: 0.0 for name in ZONE_BOUNDS}
    totals["below"] = 0.0

    for (start, heart_rate), (next_start, _) in zip(ordered, ordered[1:]):
        gap = max(next_start - start, 0.0)
        if gap > 30:
            continue          # a gap this large is a pause, not time in a zone
        key = zones.of(heart_rate) or "below"
        totals[key] += gap

    return {name: round(seconds) for name, seconds in totals.items()}
