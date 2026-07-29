from __future__ import annotations

import logging
from typing import Any, Literal

import openai
from openai import OpenAI

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["OpenAIEngine"]

logger = logging.getLogger(__name__)

# Repinned 2026-07-28 from `gpt-4o-2024-08-06` (sunsetting, and ~3.3x the price:
# $0.0050 vs $0.0015 per parametric call).
#
# This pin BREAKS the isolation plan's L3 rule of "dated snapshot, never a floating
# alias", and that is a real cost, not a technicality:
#
#   1. OpenAI publishes NO dated snapshot for the 5.6 family (checked live: only
#      gpt-5.6-luna / -sol / -terra exist). There is nothing dated to pin.
#   2. The model returns `system_fingerprint: None`, so OpenAI's own backend-change
#      signal is unavailable too.
#   => Silent provider drift on this surface is currently UNDETECTABLE. `engine_models`
#      will keep recording "gpt-5.6-luna" across a model change that moves the baseline.
#      Do not paper over this; if a cycle-over-cycle comparison looks strange on the
#      `openai` surface, an unannounced model update is a live hypothesis.
#
# It also cannot take `temperature` at all — "Unsupported value: 'temperature' does not
# support 0 with this model. Only the default (1)". Measured consequence (5 runs of one
# category query, 2026-07-28): gpt-4o at temperature 0 produced 5/5 *distinct* answers
# while luna at its fixed temperature 1 produced 3/5, and both named a stable brand set.
# So the temperature pin was not buying textual determinism in the first place — the
# real noise control here is RUNS_PER_QUERY plus the majority-vote collapse in
# `metrics._verdicts`, and that is untouched.
MODEL = "gpt-5.6-luna"


class OpenAIEngine(BaseEngine):
    """OpenAI GPT-4o engine.

    Loads the API key from ``OPENAI_API_KEY``. ``query`` returns the response
    text, or ``None`` on any error (rate limit, timeout, API failure). Never
    raises from ``query``.
    """

    ENGINE_NAME: str = "openai"
    MODEL_ID: str = MODEL
    # gpt-5.6-luna REJECTS temperature outright (see the MODEL comment), so this
    # surface samples at the provider default while the temp-0 engines do not.
    SAMPLING: Literal["pinned", "default", "none"] = "default"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env (see .env.example).")
        # Bounded timeout + retries so one slow request can't stall the whole
        # synchronous run (the SDK default timeout is 10 minutes).
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def query(self, prompt: str) -> str | None:
        # One isolated call: exactly one user message, no history, no state params,
        # best-effort seed. The recorded payload is the same dict that is sent. See
        # BaseEngine's statelessness rule.
        #
        # No `temperature`: gpt-5.6-luna rejects any value but its default (see the
        # MODEL comment). Sending settings.ENGINE_TEMPERATURE would 400 every call and
        # silently zero this surface's coverage — the exact failure that cost run
        # e186c524 a whole engine. `seed` IS accepted and is kept.
        payload: dict[str, Any] = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "seed": settings.ENGINE_SEED,
        }
        record_payload(self.ENGINE_NAME, payload)
        try:
            response = self._client.chat.completions.create(**payload)
        except openai.RateLimitError:
            logger.warning("OpenAI rate limit hit for model %s", MODEL)
            return None
        except openai.APITimeoutError:
            logger.warning("OpenAI request timed out for model %s", MODEL)
            return None
        except openai.APIError as exc:
            logger.warning("OpenAI API error: %s", exc)
            return None
        except Exception as exc:  # never let an engine crash the pipeline
            logger.warning("OpenAI unexpected error: %s", exc)
            return None

        content: str | None = response.choices[0].message.content
        return content


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = OpenAIEngine()
    except ValueError as exc:
        print(f"Cannot run OpenAI engine test: {exc}")
        raise SystemExit(0) from None

    result = engine.query("In one sentence, what is the capital of France?")
    print(f"[{OpenAIEngine.ENGINE_NAME}] response: {result}")
