"""Chat: free text in, structured facts out, deterministic consequences.

The division of labour is the whole point.

* The **model** reads language. It turns "knee felt off from about 2k" into
  `pain_reported=true, location="knee"`, and it writes a human reply.
* **Python** decides what follows. Whether today's session is dropped, whether the
  plan progresses, what the athlete is actually told to do — none of that is the
  model's call, and the model's reply is never allowed to state it.

So the reply is assembled in two parts: the model's acknowledgement, and a
deterministic sentence describing what actually changed. The model cannot say "so
take it easy today" while `readiness.py` says otherwise, because the model is not the
one who says it.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

from apps.athletes.models import Athlete
from apps.coaching.client import AIUnavailable
from apps.coaching.context import athlete_state
from apps.coaching.models import AIAnalysis
from apps.coaching.services import _run
from apps.planning.plan_services import (
    has_trained_on, next_training_session, session_on, snapshot_for,
)
from planning.readiness import apply as ease
from planning.readiness import assess

from .models import JournalEntry
from .schemas import ChatTurn

logger = logging.getLogger(__name__)

CHAT_USER = """The athlete just wrote this. Read it and do two things.

Their situation:
{state}

What they wrote (today is {today}):
\"\"\"{message}\"\"\"

First, extract only what is actually stated or clearly implied. Do not infer pain from \
tiredness, or illness from a bad night. Where a value is not mentioned, return null \
rather than guessing — a wrong fact here changes what they are told to do tomorrow.

Set `describes_completed_run` carefully. It decides whether the consequences land on \
today's session or the next one, and getting it wrong means telling someone to skip a \
session they have already done.

Second, reply to them. Acknowledge what they said, answer any question they asked, and \
be specific to their numbers. Do NOT tell them whether to train, rest, or change a \
session — that is decided by rules outside this conversation and will be appended to \
your reply. Writing it yourself risks contradicting it."""


def _apply_facts(entry: JournalEntry, facts) -> None:
    """Denormalise the fields the safety gate reads."""
    entry.extracted = facts.model_dump(mode="json")
    entry.pain_reported = facts.pain_reported
    entry.illness_reported = facts.illness_reported
    entry.rpe = facts.rpe
    entry.applies_to_date = facts.applies_to_date


def _target_session(athlete: Athlete, entry: JournalEntry):
    """Which session this actually affects, and how to name it.

    Reporting a sore knee *after* this morning's run cannot change this morning's
    run. Dropping "today's session" in that case is both wrong and useless — the
    training already happened. The consequence belongs to the next one.

    Two independent signals decide it, either being enough:

    * the athlete described a run that has already happened, and
    * an activity is already recorded for that day.

    The first covers the gap before Garmin syncs; the second covers a message that
    never mentions the run at all.
    """
    day = entry.applies_to_date
    already_ran = bool((entry.extracted or {}).get("describes_completed_run")) or has_trained_on(
        athlete, day
    )

    if not already_ran:
        session = session_on(athlete, day)
        if session is not None:
            return session, ("today" if day == athlete.local_today else "that day"), day
        # A rest day has nothing to ease, but the report has not stopped mattering.
        # Saying "nothing changes" here reads as the pain being ignored, so it falls
        # through to the session that IS affected.

    session = next_training_session(athlete, day)
    return session, "next", session.date if session else None


def _when(label: str, date) -> str:
    if label == "today":
        return "Today's session"
    if date is None:
        return "Your next session"
    return f"Your next session ({date:%a %-d %b})"


def _consequence(athlete: Athlete, entry: JournalEntry) -> str:
    """What actually changed, in deterministic words.

    Assembled from the same code that prescribes the session, so the sentence the
    athlete reads and the session they are given can never disagree.
    """
    session, label, date = _target_session(athlete, entry)
    adjustment = assess(snapshot_for(athlete))
    noun = _when(label, date)

    if session is None:
        if adjustment.changed:
            # The flags stand even with nothing scheduled to apply them to; they will
            # be applied to whatever is prescribed next.
            return (
                "There is no session scheduled in the next two weeks to adjust, but "
                "this is recorded and will apply to whatever comes next. "
                + " ".join(adjustment.reasons)
            )
        return "Nothing in the plan changes — no session is scheduled to adjust."

    if adjustment.drop_session:
        return (
            f"{noun} is dropped — walk if you want to move. " + " ".join(adjustment.reasons)
        )
    if adjustment.changed:
        eased = ease(session, adjustment)
        return (
            f"{noun} has been eased to {eased.run_minutes:.0f} minutes of running. "
            + " ".join(adjustment.reasons)
        )
    return (
        f"{noun} is unchanged: {session.run_minutes:.0f} minutes running, "
        f"{session.walk_minutes:.0f} walking."
    )


def chat(athlete: Athlete, message: str) -> JournalEntry:
    """One turn. Always stores the entry, even when extraction fails."""
    today = athlete.local_today
    state = athlete_state(athlete)

    entry = JournalEntry(
        athlete=athlete, text=message.strip(),
        written_on=today, applies_to_date=today,
        source=JournalEntry.Source.CHAT,
    )

    try:
        turn, _cached = _run(
            athlete,
            kind=AIAnalysis.Kind.JOURNAL,
            operation="journal_extract",
            payload={"message": message, "today": str(today), "state": state},
            user_prompt=CHAT_USER.format(
                state=json.dumps(state, indent=2, default=str),
                today=today,
                message=message,
            ),
            schema=ChatTurn,
        )
        _apply_facts(entry, turn.facts)
        model_reply = turn.reply
    except AIUnavailable as exc:
        # The entry is kept regardless. Losing what someone wrote because a model was
        # unavailable is worse than losing the interpretation of it.
        logger.warning("chat extraction unavailable: %s", exc)
        entry.extraction_failed = True
        model_reply = (
            "I have saved what you wrote, but could not read it just now. "
            "It will be picked up again shortly."
        )

    entry.save()

    # The deterministic half, computed AFTER the facts are stored so it reflects them.
    entry.reply = f"{model_reply}\n\n{_consequence(athlete, entry)}"
    entry.save(update_fields=["reply"])
    return entry


def flags_for(athlete: Athlete, day: dt.date, lookback_days: int = 3) -> dict:
    """Pain and illness flags that readiness reads.

    Looks back a few days on purpose: pain reported yesterday has not evaporated
    because nobody mentioned it again this morning. It clears when the athlete says
    it has, or when the window passes without a repeat.
    """
    since = day - dt.timedelta(days=lookback_days)
    recent = JournalEntry.objects.filter(
        athlete=athlete, applies_to_date__gte=since, applies_to_date__lte=day
    )
    return {
        "pain_reported": recent.filter(pain_reported=True).exists(),
        "illness_reported": recent.filter(illness_reported=True).exists(),
    }
