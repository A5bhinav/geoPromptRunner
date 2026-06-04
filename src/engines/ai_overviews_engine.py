from __future__ import annotations

import contextlib
import logging
from typing import Any

import httpx

from src.config import settings
from src.engines.base import BaseEngine

__all__ = ["AIOverviewsEngine"]

logger = logging.getLogger(__name__)

SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"
TIMEOUT_SECONDS = 45.0


class AIOverviewsEngine(BaseEngine):
    """Google AI Overviews surface, captured via SearchApi.io.

    Google exposes no official AI-Overviews API, so this reads the ``ai_overview``
    block from a SearchApi.io Google result. Requires ``SEARCHAPI_API_KEY``;
    without it the engine is skipped like any unconfigured engine.
    ``query_with_citations`` returns the AI-Overview text and its reference
    links. Never raises. (AI Overviews don't appear for every query — those
    return ``None``/``[]``.)
    """

    ENGINE_NAME: str = "google_ai_overviews"

    def __init__(self) -> None:
        if not settings.SEARCHAPI_API_KEY:
            raise ValueError(
                "SEARCHAPI_API_KEY is not set; Google AI Overviews capture is unavailable "
                "(see .env.example)."
            )
        self._api_key = settings.SEARCHAPI_API_KEY
        self._client = httpx.Client(timeout=TIMEOUT_SECONDS)

    def close(self) -> None:
        self._client.close()

    def __del__(self) -> None:
        client = getattr(self, "_client", None)
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        try:
            response = self._client.get(
                SEARCHAPI_URL,
                params={"engine": "google", "q": prompt, "api_key": self._api_key},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SearchApi request error: %s", type(exc).__name__)
            return None, []

        data: dict[str, Any] = response.json()
        overview = data.get("ai_overview")
        if not isinstance(overview, dict):
            return None, []  # no AI Overview surfaced for this query

        text = overview.get("markdown") or _extract_text(overview)
        urls = [
            str(ref["link"])
            for ref in overview.get("reference_links", []) or []
            if isinstance(ref, dict) and ref.get("link")
        ]
        return (text or None), urls


def _extract_text(overview: dict[str, Any]) -> str:
    """Fallback text extraction from text_blocks when ``markdown`` is absent."""
    parts: list[str] = []
    for block in overview.get("text_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("answer"):
            parts.append(str(block["answer"]))
        for item in block.get("list", []) or []:
            if isinstance(item, dict) and item.get("answer"):
                parts.append(str(item["answer"]))
    return " ".join(parts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = AIOverviewsEngine()
    except ValueError as exc:
        print(f"Cannot run AI Overviews engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations("best budgeting app for college students")
    print(f"[{AIOverviewsEngine.ENGINE_NAME}] response: {(answer or '')[:200]}")
    print(f"[{AIOverviewsEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
