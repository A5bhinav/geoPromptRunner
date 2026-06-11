from __future__ import annotations

import logging
from typing import Any

import openai
from openai import OpenAI

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["OpenAIEngine"]

logger = logging.getLogger(__name__)

# Dated snapshot, not the floating `gpt-4o` alias — a silent provider update
# must not move the baseline between measurement cycles (isolation plan, L3).
MODEL = "gpt-4o-2024-08-06"


class OpenAIEngine(BaseEngine):
    """OpenAI GPT-4o engine.

    Loads the API key from ``OPENAI_API_KEY``. ``query`` returns the response
    text, or ``None`` on any error (rate limit, timeout, API failure). Never
    raises from ``query``.
    """

    ENGINE_NAME: str = "openai"
    MODEL_ID: str = MODEL

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
        # One isolated call: exactly one user message, no history, no state
        # params, fixed temperature, best-effort seed. The recorded payload is
        # the same dict that is sent. See BaseEngine's statelessness rule.
        payload: dict[str, Any] = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.ENGINE_TEMPERATURE,
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
