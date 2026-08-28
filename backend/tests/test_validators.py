"""Validation of model output.

Structured Outputs guarantees the shape. Nothing guarantees the content, so these are
the checks that stand between a plausible sentence and the athlete reading it.
"""

from apps.coaching.validators import check_numbers, check_safety, prose_of, validate

CONTEXT = {
    "longest_unbroken_run_min_recent": 13.9,
    "best_recent_week_run_km": 5.3,
    "typical_running_pace": "10:09/km",
    "avg_sleep_hours_28d": 5.8,
    "training_readiness_today": 88,
    "plan": {"peak_weekly_run_km": 12.7, "projected_longest_unbroken_min": 32.4},
    "recent": [{"date": "2026-08-20", "minutes": 13.9}],
}


# --- invented numbers ---------------------------------------------------------

def test_a_number_from_the_data_passes():
    assert check_numbers("Your longest block reached 13.9 minutes.", CONTEXT).ok


def test_a_rounded_number_passes():
    """13.9 reported as 14 is correct, not invented."""
    assert check_numbers("Your longest block is about 14 minutes.", CONTEXT).ok


def test_an_invented_number_is_caught():
    """The failure that destroys the whole promise in one sentence."""
    result = check_numbers("Your longest block reached 22 minutes.", CONTEXT)
    assert not result.ok
    assert result.findings[0].rule == "ungrounded_number"


def test_a_number_derived_from_seconds_passes():
    """Durations are given in seconds and quoted in minutes."""
    assert check_numbers("about 32 minutes by race day", CONTEXT).ok


def test_dates_are_not_treated_as_claims():
    assert check_numbers("On 2026-08-20 you ran your longest block.", CONTEXT).ok


def test_paces_are_not_split_into_invented_claims():
    """'10:09/km' is a format. Reading it as 10 and 9 invents two claims."""
    assert check_numbers("Your running pace is 10:09/km.", CONTEXT).ok


def test_small_numbers_are_ignored():
    """'5 blocks', '3 days' — ordinary prose, not data claims."""
    assert check_numbers("You did 5 blocks across 3 days.", CONTEXT).ok


def test_numbers_inside_context_strings_still_count_as_grounded():
    assert check_numbers("at 10:09 per km", CONTEXT).ok


# --- unsafe progression -------------------------------------------------------

def test_recommending_more_is_caught():
    """The system prompt forbids this, but a prompt is a request, not a constraint."""
    result = check_safety("You could increase the distance next week.", flags_set=False)
    assert not result.ok
    assert result.findings[0].rule == "unsafe_progression"


def test_recommending_harder_is_caught():
    assert not check_safety("Try to run faster on Thursday.", flags_set=False).ok


def test_ordinary_encouragement_is_not_flagged():
    assert check_safety(
        "Keep the effort conversational and let the plan progress you.", flags_set=False
    ).ok


def test_the_flag_state_is_named_in_the_finding():
    result = check_safety("Push the pace a little.", flags_set=True)
    assert "pain or illness" in result.findings[0].detail


# --- medical claims -----------------------------------------------------------

def test_naming_a_condition_is_caught():
    result = check_safety("This is runner's knee.", flags_set=False)
    assert not result.ok
    assert result.findings[0].rule == "medical_claim"


def test_advising_a_professional_is_not_a_medical_claim():
    assert check_safety(
        "If the soreness persists, see a qualified professional.", flags_set=False
    ).ok


# --- the whole pass -----------------------------------------------------------

def test_prose_walks_the_model_rather_than_naming_fields():
    """A schema gaining a field must not silently gain an unchecked one."""
    payload = {
        "summary": "first",
        "nested": {"deep": ["second", {"deeper": "third"}]},
        "number": 42,
    }
    text = prose_of(payload)
    assert "first" in text and "second" in text and "third" in text


def test_a_clean_response_passes_everything():
    text = "Your longest block reached 13.9 minutes. Keep the effort easy."
    assert validate(text, CONTEXT, flags_set=False).ok


def test_findings_accumulate_rather_than_stopping_at_the_first():
    text = "Your longest block was 22 minutes, so increase the distance."
    result = validate(text, CONTEXT, flags_set=False)
    assert {f.rule for f in result.findings} == {"ungrounded_number", "unsafe_progression"}


# --- negation, found by the eval harness --------------------------------------

def test_advising_against_progression_is_not_a_violation():
    """The first version flagged all three of these, which is exactly backwards:
    the model was warning against them. Found by running the evals, not by review."""
    assert check_safety(
        "Keep intervals easy enough to repeat, retain the walking breaks, and do not "
        "add distance, pace work, or extra sessions.",
        flags_set=False,
    ).ok


def test_saying_something_is_not_a_diagnosis_is_not_a_diagnosis():
    assert check_safety(
        "Readings can be affected by sleep, fatigue and sensor error, so it does not "
        "diagnose a problem by itself.",
        flags_set=False,
    ).ok


def test_recommending_the_opposite_of_running_faster_is_not_a_violation():
    assert check_safety(
        "Focus on regular run/walk sessions and gradual endurance rather than trying "
        "to run faster or continuously for longer.",
        flags_set=False,
    ).ok


def test_a_genuine_recommendation_after_an_unrelated_negation_still_fails():
    """The window is short on purpose: a negation two sentences back must not
    excuse a real recommendation."""
    text = (
        "Do not worry about your heart rate. Your sleep has been reasonable and your "
        "cadence is steady, so next week you should increase the distance."
    )
    assert not check_safety(text, flags_set=False).ok


def test_every_occurrence_is_checked_not_just_the_first():
    """re.search stops at the first match; a negated one first would mask a real one."""
    text = "Do not add distance this week. On Saturday, go harder than planned."
    result = check_safety(text, flags_set=False)
    assert not result.ok
    assert "go harder" in result.findings[0].detail
