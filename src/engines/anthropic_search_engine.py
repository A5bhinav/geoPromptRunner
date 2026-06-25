from __future__ import annotations

import logging
from typing import Any

import anthropic
from anthropic import Anthropic

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["AnthropicSearchEngine"]

logger = logging.getLogger(__name__)

# Dated snapshot (Anthropic ids carry their release date) — isolation plan, L3.
MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 1024
WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 3,
}


class AnthropicSearchEngine(BaseEngine):
    """Anthropic Claude with the web-search server tool (surface: Claude-with-search).

    Distinct from ``AnthropicEngine`` (parametric memory). ``query_with_citations``
    returns the URLs Claude cited from its searches. Never raises.
    """

    ENGINE_NAME: str = "anthropic_search"
    MODEL_ID: str = MODEL

    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env (see .env.example)."
            )
        self._client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        # One isolated call: exactly one user message, the web-search server
        # tool, no state params. The recorded payload is the same dict sent.
        payload: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [WEB_SEARCH_TOOL],
        }
        record_payload(self.ENGINE_NAME, payload)
        try:
            response = self._client.messages.create(**payload)
        except anthropic.RateLimitError:
            logger.warning("Anthropic search rate limit hit for model %s", MODEL)
            return None, []
        except anthropic.APITimeoutError:
            logger.warning("Anthropic search request timed out for model %s", MODEL)
            return None, []
        except anthropic.APIError as exc:
            logger.warning("Anthropic search API error: %s", exc)
            return None, []
        except Exception as exc:  # never let an engine crash the pipeline
            logger.warning("Anthropic search unexpected error: %s", exc)
            return None, []

        parts: list[str] = []
        urls: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) != "text":
                continue
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
            for citation in getattr(block, "citations", None) or []:
                url = getattr(citation, "url", None)
                if url:
                    urls.append(str(url))

        if not parts:
            return None, _dedupe(urls)
        return "".join(parts), _dedupe(urls)


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = AnthropicSearchEngine()
    except ValueError as exc:
        print(f"Cannot run Anthropic search engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations("What are the best budgeting apps in 2026?")
    print(f"[{AnthropicSearchEngine.ENGINE_NAME}] response: {answer}")
    print(f"[{AnthropicSearchEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
