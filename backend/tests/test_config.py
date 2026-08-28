"""Configuration smoke tests.

These exist because the AI settings block and its compose passthrough were both
silently lost during an edit, and nothing failed until a live call was attempted
several milestones later. Configuration that is only exercised by a paid API call is
configuration that breaks quietly.
"""

from django.conf import settings


def test_every_tier_resolves_to_a_model():
    for operation, tier in settings.AI_MODEL_TIERS.items():
        assert tier in settings.AI_MODELS, f"{operation} names unknown tier '{tier}'"


def test_the_active_provider_has_a_key():
    key = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}[settings.AI_PROVIDER]
    assert hasattr(settings, key), f"provider is {settings.AI_PROVIDER} but {key} is not defined"


def test_no_model_id_is_hardcoded_in_application_code():
    """Model IDs belong in .env. A literal in code is one you will forget to change."""
    import re
    from pathlib import Path

    backend = Path(settings.BASE_DIR)
    pattern = re.compile(r"[\"'](gpt-[0-9]|gemini-[0-9]|claude-[0-9])")
    offenders = []
    for path in list(backend.glob("apps/**/*.py")) + list(backend.glob("config/*.py")):
        text = path.read_text()
        for line_no, line in enumerate(text.splitlines(), 1):
            # client.py holds a pricing table keyed by model id, which is reporting
            # data rather than a model choice.
            if "PRICING" in text[: text.find(line)][-200:]:
                continue
            if pattern.search(line) and "PRICING" not in line:
                offenders.append(f"{path.name}:{line_no}")
    assert not offenders or all("client.py" in o for o in offenders), offenders


def test_training_thresholds_are_all_present():
    required = {
        "MAX_WEEKLY_INCREASE_PCT", "MAX_HARD_SESSIONS_PER_WEEK",
        "MIN_RECOVERY_DAYS_AFTER_HARD", "MAX_LONG_RUN_PCT_OF_WEEK",
        "MIN_BUILD_WEEKS", "CUTBACK_EVERY_N_WEEKS", "CUTBACK_FACTOR",
        "MIN_RUNS_FOR_PREDICTION", "MIN_WEEKS_FOR_PREDICTION",
    }
    assert required <= set(settings.TRAINING)
