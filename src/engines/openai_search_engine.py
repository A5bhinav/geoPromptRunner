from __future__ import annotations

import logging
from typing import Any, Literal

import openai
from openai import OpenAI

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["OpenAISearchEngine"]

logger = logging.getLogger(__name__)

# The ChatGPT-with-search surface: a frontier model calling the hosted web_search tool
# via the Responses API — which is how ChatGPT itself now works, rather than the
# dedicated search model this adapter used to call. Arguably a fidelity upgrade as well
# as a throughput one.
#
# UNDATED — see src/engines/model_pins.py. OpenAI publishes no dated snapshot for the
# 5.6 family (verified live 2026-08-01: each model page's Snapshots section lists only
# the bare id).
#
# WHY NOT `gpt-5-search-api-2025-10-14` (the previous pin): capped at 6,000 tokens/min
# on this account while one search answer consumes ~17,230, so a real run lost every
# cell to 429s (0 of 10 answered, verified twice). The Responses web_search tool bills
# against the CALLING MODEL's limits instead — Luna is 500,000 TPM / 500 RPM at Tier 1.
# This is a throughput fix first and a cost fix second.
MODEL = "gpt-5.6-luna"

# type must be "web_search", not the older "web_search_preview". A dated variant
# (`web_search_2025_08_26`) also exists; switching to it would change what the surface
# retrieves, so it is a separate measured decision rather than a drive-by edit — the
# same stance src/engines/anthropic_search_engine.py takes on its tool version.
WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search"}


class OpenAISearchEngine(BaseEngine):
    """OpenAI with live web search (surface: ChatGPT-with-search).

    Distinct from ``OpenAIEngine`` (parametric memory). ``query_with_citations``
    returns the source URLs OpenAI retrieved. Loads ``OPENAI_API_KEY``. Never
    raises from ``query``/``query_with_citations``.
    """

    ENGINE_NAME: str = "openai_search"
    MODEL_ID: str = MODEL
    # gpt-5.6-* reject a non-default temperature and this adapter sends none, so the
    # surface runs at the provider default. Retrieval varies run to run regardless (L5).
    SAMPLING: Literal["pinned", "default", "none"] = "default"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env (see .env.example).")
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        # One isolated call: a single input string, the hosted web_search tool, and an
        # EXPLICIT store=False. The Responses API retains responses by default and the
        # SDK's own type stub documents no default at all — so the guarantee is stated
        # rather than inherited. See tests/test_isolation.py: present-and-False is the
        # isolation rule being asserted, not broken.
        payload: dict[str, Any] = {
            "model": MODEL,
            "input": prompt,
            "tools": [WEB_SEARCH_TOOL],
            "store": False,
        }
        record_payload(self.ENGINE_NAME, payload)
        try:
            response = self._client.responses.create(**payload)
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

        # `output` is a list of items — web_search_call items and message items, only the
        # latter carrying content; a message's content entries hold annotations with
        # type == "url_citation". The defensive getattr chain is deliberate: this shape is
        # newer than the rest of the codebase and an AttributeError inside an engine would
        # violate the never-raises contract.
        text = getattr(response, "output_text", None)
        urls: list[str] = []
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", None) or []:
                for annotation in getattr(content, "annotations", None) or []:
                    if getattr(annotation, "type", None) != "url_citation":
                        continue
                    url = getattr(annotation, "url", None)
                    if url:
                        urls.append(str(url))
        return text, _dedupe(urls)


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
        engine = OpenAISearchEngine()
    except ValueError as exc:
        print(f"Cannot run OpenAI search engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations("What are the best budgeting apps in 2026?")
    print(f"[{OpenAISearchEngine.ENGINE_NAME}] response: {answer}")
    print(f"[{OpenAISearchEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
