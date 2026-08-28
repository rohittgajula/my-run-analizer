"""Checking what the model said before the athlete reads it.

A schema-valid response can still be wrong in ways that matter. Structured Outputs
guarantees the *shape*; nothing guarantees the content. The three failures worth
catching are:

1. **Invented numbers.** The classic hallucination, and the most damaging here because
   the whole product promise is "every figure traces to your own data". A confident
   "your longest run was 22 minutes" when it was 13.9 destroys that in one sentence.
2. **Unsafe progression.** The system prompt forbids recommending harder training, but
   a prompt is a request, not a constraint.
3. **Medical claims.** Naming a condition is not this system's job and not something a
   prompt reliably prevents.

None of these are enforceable by the schema, so they are enforced here. Findings do
not silently rewrite the answer — they are attached to it, logged, and surfaced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Numbers this small are ordinal or structural ("2 blocks", "3 days") and appear in
# ordinary prose regardless of the data. Checking them produces noise, not signal.
IGNORE_BELOW = 11

# How close a cited number must be to a real one. Rounding is legitimate: 13.9 minutes
# reported as 14 is correct, not invented.
TOLERANCE = 0.06

# Words that reverse the sense of what follows. Without these the validator flags the
# *correct* advice: "do not add distance", "it does not diagnose a problem" and
# "rather than trying to run faster" were all caught as violations by the first
# version, which is precisely backwards — the model was warning against them.
NEGATORS = (
    r"do(?:es)?\s+not|don'?t|doesn'?t|never|avoid|rather\s+than|instead\s+of|"
    r"without|no\s+need\s+to|should\s+not|shouldn'?t|refrain\s+from|"
    r"resist|stop\s+short\s+of|\bnot\b"
)

# How far back to look for one. Long enough to catch "do not add pace work, extra
# sessions, or distance", short enough that a negation two sentences earlier does not
# excuse a genuine recommendation.
NEGATION_WINDOW = 60


def _negated(text: str, at: int) -> bool:
    """Whether a negator sits shortly before position `at`, in the SAME sentence.

    Stopping at the sentence boundary matters: "Do not add distance this week. On
    Saturday, go harder than planned." has a negator within sixty characters of "go
    harder", and letting it reach across the full stop would excuse a genuine
    recommendation.
    """
    window = text[max(0, at - NEGATION_WINDOW) : at]
    # Keep only what follows the last sentence break inside the window.
    if breaks := list(re.finditer(r"[.!?;\n]", window)):
        window = window[breaks[-1].end():]
    return re.search(NEGATORS, window) is not None


PROGRESSION_PHRASES = [
    r"\b(?:push|increase|add|extend|ramp)\s+(?:the\s+)?(?:pace|distance|volume|mileage|intensity)",
    r"\brun\s+(?:faster|harder|longer than planned)\b",
    r"\bstep\s+it\s+up\b",
    r"\bgo\s+harder\b",
]

MEDICAL_PHRASES = [
    r"\b(?:you\s+(?:have|likely\s+have)|this\s+is)\s+(?:a\s+)?"
    r"(?:tendinitis|tendonitis|shin\s+splints?|stress\s+fracture|itbs?|"
    r"plantar\s+fasciitis|runner'?s\s+knee)\b",
    r"\bdiagnos(?:e|is|ed)\b",
    r"\bprescrib(?:e|ed)\s+(?:you\s+)?(?:medication|ibuprofen|painkillers)\b",
]


@dataclass
class Finding:
    rule: str
    detail: str


@dataclass
class Validation:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def add(self, rule: str, detail: str) -> None:
        self.findings.append(Finding(rule=rule, detail=detail))

    def as_list(self) -> list[dict]:
        return [{"rule": f.rule, "detail": f.detail} for f in self.findings]


def _numbers_in(value, into: set[float]) -> None:
    """Every number reachable in the context, plus the forms a writer would use."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        into.add(float(value))
        into.add(round(float(value)))
        into.add(round(float(value), 1))
        # Seconds are routinely quoted as minutes, and fractions as percentages.
        into.add(round(float(value) / 60, 1))
        into.add(round(float(value) / 60))
        into.add(round(float(value) * 100))
        into.add(round(float(value) / 1000, 2))
        return
    if isinstance(value, dict):
        for item in value.values():
            _numbers_in(item, into)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _numbers_in(item, into)
        return
    if isinstance(value, str):
        # Numbers embedded in strings are still grounded — "7:05/km" is data.
        for match in re.findall(r"\d+(?:\.\d+)?", value):
            into.add(float(match))
    return


def grounded_numbers(context: dict) -> set[float]:
    found: set[float] = set()
    _numbers_in(context, found)
    return found


def _cited_numbers(text: str) -> list[float]:
    """Numbers a reader would take as claims.

    Dates, times of day and paces are excluded: "2026-08-17" and "7:05/km" are
    formats, and splitting them into components invents claims nobody made.
    """
    without_dates = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text)
    without_clock = re.sub(r"\b\d{1,3}:\d{2}\b", " ", without_dates)
    return [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", without_clock)]


def check_numbers(text: str, context: dict) -> Validation:
    """Every figure in the output must trace to one in the input."""
    validation = Validation()
    allowed = grounded_numbers(context)

    for number in _cited_numbers(text):
        if number < IGNORE_BELOW:
            continue
        if any(
            abs(number - candidate) <= max(TOLERANCE * max(abs(candidate), 1), 0.5)
            for candidate in allowed
        ):
            continue
        validation.add(
            "ungrounded_number",
            f"'{number:g}' does not appear in the data the model was given.",
        )
    return validation


def check_safety(text: str, *, flags_set: bool) -> Validation:
    """No recommending harder training, and never when a flag is raised."""
    validation = Validation()
    lowered = text.lower()

    for pattern in PROGRESSION_PHRASES:
        for match in re.finditer(pattern, lowered):
            if _negated(lowered, match.start()):
                continue
            validation.add(
                "unsafe_progression",
                f"suggests progressing: '{match.group(0)}'"
                + (" while pain or illness is reported" if flags_set else ""),
            )

    for pattern in MEDICAL_PHRASES:
        for match in re.finditer(pattern, lowered):
            if _negated(lowered, match.start()):
                continue
            validation.add(
                "medical_claim", f"names or diagnoses a condition: '{match.group(0)}'"
            )

    return validation


def validate(text: str, context: dict, *, flags_set: bool = False) -> Validation:
    """The full pass over one response's prose."""
    combined = Validation()
    combined.findings.extend(check_numbers(text, context).findings)
    combined.findings.extend(check_safety(text, flags_set=flags_set).findings)
    return combined


def prose_of(result) -> str:
    """Every human-readable string in a response, concatenated for checking.

    Walks the model rather than naming fields, so a schema gaining a field does not
    silently gain an unchecked one.
    """
    parts: list[str] = []

    def walk(value):
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(result.model_dump(mode="json") if hasattr(result, "model_dump") else result)
    return "\n".join(parts)
