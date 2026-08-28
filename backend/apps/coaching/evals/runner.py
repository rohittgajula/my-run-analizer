"""Run the prompts against the fixtures and report what failed.

Responses are cached to disk by fixture and prompt version, so a re-run after an
unrelated change costs nothing. Bumping PROMPT_VERSION invalidates them, which is the
whole point: a prompt change is exactly when you need to re-measure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from apps.coaching.prompts import GUIDANCE_USER, PROMPT_VERSION, SYSTEM
from apps.coaching.schemas import Guidance
from apps.coaching.validators import prose_of, validate

from .fixtures import FIXTURES, Fixture

CACHE = Path(__file__).parent / "recorded"


@dataclass
class Result:
    fixture: str
    ok: bool
    failures: list[str]
    cached: bool


def _cache_path(fixture: Fixture) -> Path:
    return CACHE / f"{fixture.name}.{PROMPT_VERSION}.json"


def run_one(fixture: Fixture, *, live: bool) -> Result:
    from apps.coaching.client import complete

    path = _cache_path(fixture)
    cached = path.exists()

    if cached and not live:
        result = Guidance.model_validate(json.loads(path.read_text()))
    else:
        result, _stats = complete(
            operation="guidance",
            system=SYSTEM,
            user=GUIDANCE_USER.format(state=json.dumps(fixture.state, indent=2)),
            schema=Guidance,
        )
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.model_dump(mode="json"), indent=2))
        cached = False

    text = prose_of(result)
    failures = [f.detail for f in validate(text, fixture.state, flags_set=fixture.flags_set).findings]

    for phrase in fixture.must_mention:
        if phrase.lower() not in text.lower():
            failures.append(f"never mentions '{phrase}'")

    for pattern in fixture.must_not_match:
        if re.search(pattern, text, re.IGNORECASE):
            failures.append(f"matched forbidden pattern /{pattern}/")

    for check in fixture.extra_checks:
        if problem := check(text):
            failures.append(problem)

    return Result(fixture=fixture.name, ok=not failures, failures=failures, cached=cached)


def run_all(*, live: bool = False, only: str | None = None) -> list[Result]:
    return [
        run_one(fixture, live=live)
        for fixture in FIXTURES
        if only is None or fixture.name == only
    ]
