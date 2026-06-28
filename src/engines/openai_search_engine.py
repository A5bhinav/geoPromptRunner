from __future__ import annotations

import logging
from typing import Any

import openai
from openai import OpenAI

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["OpenAISearchEngine"]

logger = logging.getLogger(__name__)

# Search-enabled chat model: live web retrieval + URL citations, i.e. the
# ChatGPT-with-search surface a consumer actually sees, not GPT's training memory.
# Dated snapshot, not the floating alias (isolation plan, L3) — retrieval still
# varies run to run (L5), but the model under it stays fixed across cycles.
MODEL = "gpt-4o-search-preview-2025-03-11"


class OpenAISearchEngine(BaseEngine):
    """OpenAI with live web search (surface: ChatGPT-with-search).

    Distinct from ``OpenAIEngine`` (parametric memory). ``query_with_citations``
    returns the source URLs OpenAI retrieved. Loads ``OPENAI_API_KEY``. Never
    raises from ``query``/``query_with_citations``.
    """

    ENGINE_NAME: str = "openai_search"
    MODEL_ID: str = MODEL

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env (see .env.example).")
        # The search-preview model does not accept a temperature parameter.
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        # One isolated call: exactly one user message, no state params. The
        # search-preview models reject sampling params, so no temperature/seed.
        # The recorded payload is the same dict that is sent.
        payload: dict[str, Any] = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }
        record_payload(self.ENGINE_NAME, payload)
        try:
            response = self._client.chat.completions.create(**payload)
        except openai.RateLimitError:
            logger.warning("OpenAI search rate limit hit for model %s", MODEL)
            return None, []
        except openai.APITimeoutError:
            logger.warning("OpenAI search request timed out for model %s", MODEL)
            return None, []
        except openai.APIError as exc:
            logger.warning("OpenAI search API error: %s", exc)
            return None, []
        except Exception as exc:  # never let an engine crash the pipeline
            logger.warning("OpenAI search unexpected error: %s", exc)
            return None, []

        message = response.choices[0].message
        text = message.content
        urls: list[str] = []
        for annotation in getattr(message, "annotations", None) or []:
            citation = getattr(annotation, "url_citation", None)
            url = getattr(citation, "url", None)
            if url:
                urls.append(str(url))
        return text, urls


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = OpenAISearchEngine()
    except ValueError as exc:
        print(f"Cannot run OpenAI search engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations("What are the best budgeting apps in 2026?")
    print(f"[{OpenAISearchEngine.ENGINE_NAME}] response: {answer}")
    print(f"[{OpenAISearchEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
