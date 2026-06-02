from __future__ import annotations

import logging

import anthropic
from anthropic import Anthropic
from anthropic.types import TextBlock

from src.config import settings
from src.engines.base import BaseEngine

__all__ = ["AnthropicEngine"]

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 1024


class AnthropicEngine(BaseEngine):
    """Anthropic Claude (Sonnet 4.5) engine.

    Loads the API key from ``ANTHROPIC_API_KEY``. ``query`` returns the
    response text, or ``None`` on any error. Never raises from ``query``.
    """

    ENGINE_NAME: str = "anthropic"

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env (see .env.example)."
            )
        # Bounded timeout + retries so one slow request can't stall the whole
        # synchronous run.
        self._client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def query(self, prompt: str) -> str | None:
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=settings.ENGINE_TEMPERATURE,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError:
            logger.warning("Anthropic rate limit hit for model %s", MODEL)
            return None
        except anthropic.APITimeoutError:
            logger.warning("Anthropic request timed out for model %s", MODEL)
            return None
        except anthropic.APIError as exc:
            logger.warning("Anthropic API error: %s", exc)
            return None
        except Exception as exc:  # never let an engine crash the pipeline
            logger.warning("Anthropic unexpected error: %s", exc)
            return None

        parts = [block.text for block in response.content if isinstance(block, TextBlock)]
        if not parts:
            return None
        return "".join(parts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = AnthropicEngine()
    except ValueError as exc:
        print(f"Cannot run Anthropic engine test: {exc}")
        raise SystemExit(0) from None

    result = engine.query("In one sentence, what is the capital of France?")
    print(f"[{AnthropicEngine.ENGINE_NAME}] response: {result}")
