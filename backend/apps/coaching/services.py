"""The coaching service.

The order of operations is the design:

    safety gate  ->  cache  ->  model  ->  validation  ->  store

The gate runs BEFORE the model, not after. A gate that only filters output is one you
have already walked through: by then the model has been asked to justify a harder
session and the answer is on the page.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings

from apps.athletes.models import Athlete
from apps.activities.models import Activity

from .client import AIUnavailable, canonical_hash, complete, model_for
from .context import athlete_state, recent_runs, run_summary, weekly_rollup
from .models import AIAnalysis, AIRequestLog
from .prompts import GUIDANCE_USER, JOURNAL_USER, PROMPT_VERSION, RUN_USER, SYSTEM, WEEKLY_USER
from .schemas import Guidance, JournalFacts, RunAnalysis, WeeklyReview
from .validators import prose_of, validate

logger = logging.getLogger(__name__)

# Per-athlete monthly ceiling. Not a rate limit — a money limit. Every registered
# athlete spends the same prepaid balance, so this is what stops one person's
# enthusiasm emptying it for everyone. See docs/HOSTING.md.
MONTHLY_CALL_BUDGET = 200


class BudgetExceeded(AIUnavailable):
    """This athlete has used their share for the month."""


def _spent_this_month(athlete: Athlete) -> int:
    start = athlete.local_today.replace(day=1)
    return AIRequestLog.objects.filter(
        athlete=athlete, created_at__date__gte=start,
        status__in=[AIRequestLog.Status.OK, AIRequestLog.Status.INVALID],
    ).count()


def _run(
    athlete: Athlete,
    *,
    kind: str,
    operation: str,
    payload: dict,
    user_prompt: str,
    schema,
    activity: Activity | None = None,
):
    """One cached, logged, validated call."""
    model = model_for(operation)
    digest = canonical_hash(payload, PROMPT_VERSION, model)

    cached = AIAnalysis.objects.filter(
        athlete=athlete, kind=kind, input_hash=digest
    ).first()
    if cached:
        # Deliberately not logged as a request: it cost nothing, and counting it
        # would make the cost log lie in the direction of looking worse.
        return schema.model_validate(cached.result), True

    if _spent_this_month(athlete) >= MONTHLY_CALL_BUDGET:
        AIRequestLog.objects.create(
            athlete=athlete, operation=operation, provider=settings.AI_PROVIDER,
            model=model, prompt_version=PROMPT_VERSION,
            status=AIRequestLog.Status.REFUSED,
            error=f"Monthly budget of {MONTHLY_CALL_BUDGET} calls reached.",
        )
        raise BudgetExceeded(
            f"You have used your {MONTHLY_CALL_BUDGET} coaching requests for this month."
        )

    try:
        result, stats = complete(
            operation=operation, system=SYSTEM, user=user_prompt, schema=schema
        )
    except Exception as exc:
        AIRequestLog.objects.create(
            athlete=athlete, operation=operation, provider=settings.AI_PROVIDER,
            model=model, prompt_version=PROMPT_VERSION,
            status=AIRequestLog.Status.ERROR, error=str(exc)[:500],
        )
        raise

    # Validate before storing. Structured Outputs guarantees the shape; nothing
    # guarantees the content, and an invented figure is the one failure that breaks
    # the whole promise of this system.
    flags = payload.get("state", payload).get("reported_by_athlete", {}) if isinstance(payload, dict) else {}
    checked = validate(
        prose_of(result),
        payload,
        flags_set=bool(flags.get("pain") or flags.get("illness")),
    )
    if not checked.ok:
        logger.warning(
            "ai %s produced %d finding(s): %s",
            operation, len(checked.findings),
            "; ".join(f.detail for f in checked.findings),
        )

    AIRequestLog.objects.create(
        athlete=athlete, operation=operation, provider=settings.AI_PROVIDER,
        prompt_version=PROMPT_VERSION,
        # A response with findings is still logged as OK: it was billed and it was
        # returned. INVALID is reserved for one that could not be parsed at all.
        status=AIRequestLog.Status.OK,
        error="; ".join(f.detail for f in checked.findings)[:500],
        **stats,
    )
    AIAnalysis.objects.update_or_create(
        athlete=athlete, kind=kind, input_hash=digest,
        defaults={
            "activity": activity,
            "prompt_version": PROMPT_VERSION,
            "model": stats["model"],
            # mode="json" so dates and enums become primitives. A plain
            # model_dump() puts date objects in a JSONField and the write dies
            # AFTER the paid call has already been made.
            "result": result.model_dump(mode="json"),
            "findings": checked.as_list(),
        },
    )
    return result, False


def guidance_for(athlete: Athlete) -> tuple[Guidance, bool]:
    """Where the athlete stands, and what to do about it."""
    state = athlete_state(athlete)
    return _run(
        athlete,
        kind=AIAnalysis.Kind.GUIDANCE,
        operation="guidance",
        payload=state,
        user_prompt=GUIDANCE_USER.format(state=json.dumps(state, indent=2, default=str)),
        schema=Guidance,
    )


def analyse_run(athlete: Athlete, activity: Activity) -> tuple[RunAnalysis, bool]:
    run = run_summary(activity)
    recent = recent_runs(athlete, limit=8)
    payload = {"run": run, "recent": recent}
    return _run(
        athlete,
        kind=AIAnalysis.Kind.RUN,
        operation="run_analysis",
        payload=payload,
        user_prompt=RUN_USER.format(
            run=json.dumps(run, indent=2, default=str),
            recent=json.dumps(recent, indent=2, default=str),
        ),
        schema=RunAnalysis,
        activity=activity,
    )


def weekly_review(athlete: Athlete) -> tuple[WeeklyReview, bool]:
    weeks = weekly_rollup(athlete)
    state = athlete_state(athlete)
    payload = {"weeks": weeks, "state": state}
    return _run(
        athlete,
        kind=AIAnalysis.Kind.WEEKLY,
        operation="weekly_review",
        payload=payload,
        user_prompt=WEEKLY_USER.format(
            weeks=json.dumps(weeks, indent=2, default=str),
            state=json.dumps(state, indent=2, default=str),
        ),
        schema=WeeklyReview,
    )


def extract_journal(athlete: Athlete, text: str, written_on) -> tuple[JournalFacts, bool]:
    payload = {"text": text, "written_on": str(written_on)}
    return _run(
        athlete,
        kind=AIAnalysis.Kind.JOURNAL,
        operation="journal_extract",
        payload=payload,
        user_prompt=JOURNAL_USER.format(text=text, written_on=written_on),
        schema=JournalFacts,
    )
