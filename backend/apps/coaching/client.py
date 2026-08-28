"""The provider boundary.

Everything OpenAI-specific lives here. The rest of the app names a TIER and passes a
Pydantic model; it never sees a model id, a token count or a request shape. M6 adds a
second provider behind this same function as a test that the seam holds.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypeVar

from django.conf import settings
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Cached. NEVER construct a client inline: building and using one in a single
# expression lets it be garbage-collected mid-request, closing its connection pool on
# the way out, and the call dies with "client has been closed".
_CLIENTS: dict[str, Any] = {}

# USD per million tokens, for the cost log. Approximate and only used for reporting —
# the authoritative number is the OpenAI dashboard.
PRICING = {
    "gpt-5.6-terra": (2.00, 12.00),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.6-sol": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5-nano": (0.05, 0.40),
}


class AIUnavailable(Exception):
    """The model could not be reached or could not produce a valid answer.

    Callers must degrade rather than surface this: an athlete is never left without a
    session because an API was down.
    """


def get_client(provider: str = "openai"):
    if provider not in _CLIENTS:
        from openai import OpenAI

        key = settings.OPENAI_API_KEY
        if not key:
            raise AIUnavailable("No OPENAI_API_KEY configured.")
        _CLIENTS[provider] = OpenAI(api_key=key, timeout=settings.AI_TIMEOUT_SEC)
    return _CLIENTS[provider]


def model_for(operation: str) -> str:
    tier = settings.AI_MODEL_TIERS.get(operation, "fast")
    model = settings.AI_MODELS.get(tier) or settings.AI_MODELS.get("fast")
    if not model:
        raise AIUnavailable(f"No model configured for tier '{tier}'.")
    return model


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model)
    if not rates:
        return 0.0
    return round(input_tokens / 1e6 * rates[0] + output_tokens / 1e6 * rates[1], 6)


def complete(
    *,
    operation: str,
    system: str,
    user: str,
    schema: type[T],
    max_retries: int | None = None,
) -> tuple[T, dict]:
    """One structured call. Returns (validated result, usage stats).

    Uses strict Structured Outputs rather than asking for JSON in the prompt, so
    malformed JSON stops being a failure mode to handle and becomes one the decoder
    prevents. A schema-valid answer can still be semantically wrong — that is what
    the validators downstream are for.
    """
    client = get_client()
    model = model_for(operation)
    retries = settings.AI_MAX_RETRIES if max_retries is None else max_retries

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        started = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": _strict_schema(schema),
                    },
                },
            )
            latency = int((time.monotonic() - started) * 1000)

            choice = response.choices[0]
            # A 200 can still carry a truncated answer. Treat it as a failure rather
            # than validating half an object.
            if choice.finish_reason == "length":
                raise AIUnavailable("Response was cut off before it finished.")
            if getattr(choice.message, "refusal", None):
                raise AIUnavailable(f"Model refused: {choice.message.refusal}")

            usage = response.usage
            stats = {
                "model": model,
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
                "latency_ms": latency,
                "retry_count": attempt,
            }
            stats["estimated_cost_usd"] = estimate_cost(
                model, stats["input_tokens"], stats["output_tokens"]
            )
            return schema.model_validate_json(choice.message.content), stats

        except ValidationError as exc:
            last_error = exc
            logger.warning("ai %s failed validation (attempt %s): %s", operation, attempt, exc)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            message = str(exc)
            # A rate limit is a wait, not a failure. Back off and let the caller
            # decide; retrying immediately makes it worse.
            if "429" in message or "rate limit" in message.lower():
                logger.warning("ai %s rate limited", operation)
                raise AIUnavailable("Rate limited. Try again shortly.") from exc
            logger.warning("ai %s error (attempt %s): %s", operation, attempt, message)

        if attempt < retries:
            time.sleep(min(2**attempt, 8))

    raise AIUnavailable(f"{operation} failed after {retries + 1} attempts: {last_error}")


def _strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic's JSON schema, adjusted for OpenAI strict mode.

    Strict mode requires every property listed in `required` and
    `additionalProperties: false` on every object, and it does not accept `$defs`
    references at the top level in all cases — so definitions are inlined.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                return resolve(defs[name])
            node = {key: resolve(value) for key, value in node.items()}
            if node.get("type") == "object":
                node["additionalProperties"] = False
                if "properties" in node:
                    node["required"] = list(node["properties"])
            return node
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def canonical_hash(payload: dict, prompt_version: str, model: str) -> str:
    """Stable across dict ordering, so the same context always hits the same cache row."""
    import hashlib

    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(f"{blob}|{prompt_version}|{model}".encode()).hexdigest()
