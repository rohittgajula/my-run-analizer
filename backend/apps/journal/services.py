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
from apps.planning.plan_services import snapshot_for, today_session

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

`applies_to_date` is which day's SESSION this bears on, not which day the words \
describe. "I slept badly last night", written in the morning, is about TODAY's session.

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


def _consequence(athlete: Athlete) -> str:
    """What actually changed, in deterministic words.

    Assembled after the facts land, from the same code path that prescribes the
    session — so the sentence the athlete reads and the session they are given can
    never disagree.
    """
    session, adjustment, mode = today_session(athlete)

    if adjustment and adjustment.drop_session:
        return (
            "Based on that, today's session is dropped — walk if you want to move. "
            + " ".join(adjustment.reasons)
        )
    if adjustment and adjustment.changed:
        return (
            f"Based on that, today has been eased to {session.run_minutes:.0f} minutes "
            f"of running. " + " ".join(adjustment.reasons)
        )
    if session:
        return (
            f"Today's session is unchanged: {session.run_minutes:.0f} minutes running, "
            f"{session.walk_minutes:.0f} walking."
        )
    return f"Nothing in the plan changes — today is a {mode.replace('_', ' ')} day."


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
    entry.reply = f"{model_reply}\n\n{_consequence(athlete)}"
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
