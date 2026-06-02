from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import settings
from src.engines.base import BaseEngine

__all__ = ["AIOverviewsEngine"]

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
TIMEOUT_SECONDS = 30.0


class AIOverviewsEngine(BaseEngine):
    """Google AI Overviews surface, captured via SerpApi.

    Google exposes no official AI-Overviews API, so this reads the ``ai_overview``
    block from a SerpApi Google Search result. Requires ``SERPAPI_API_KEY``;
    without it the engine is skipped like any unconfigured engine.
    ``query_with_citations`` returns the AI-Overview text and its source links.
    Never raises.

    NOTE: validated against SerpApi's documented response shape; exercise with a
    real key before relying on it (AI Overviews don't appear for every query).
    """

    ENGINE_NAME: str = "google_ai_overviews"

    def __init__(self) -> None:
        if not settings.SERPAPI_API_KEY:
            raise ValueError(
                "SERPAPI_API_KEY is not set; Google AI Overviews capture is unavailable "
                "(see .env.example)."
            )
        self._api_key = settings.SERPAPI_API_KEY
        self._client = httpx.Client(timeout=TIMEOUT_SECONDS)

    def close(self) -> None:
        self._client.close()

    def __del__(self) -> None:
        client = getattr(self, "_client", None)
        if client is not None:
            import contextlib

            with contextlib.suppress(Exception):
                client.close()

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def _get(self, params: dict[str, str]) -> dict[str, Any] | None:
        try:
            response = self._client.get(SERPAPI_URL, params={**params, "api_key": self._api_key})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SerpApi request error: %s", type(exc).__name__)
            return None
        data: dict[str, Any] = response.json()
        return data

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        data = self._get({"engine": "google", "q": prompt})
        if data is None:
            return None, []
        overview = data.get("ai_overview")
        if not isinstance(overview, dict):
            return None, []  # no AI Overview surfaced for this query

        # Some responses defer the overview behind a page_token (second call).
        if "page_token" in overview and "text_blocks" not in overview:
            follow = self._get(
                {"engine": "google_ai_overview", "page_token": overview["page_token"]}
            )
            overview = follow.get("ai_overview", {}) if isinstance(follow, dict) else {}

        text = _extract_text(overview)
        urls = [
            str(ref["link"])
            for ref in overview.get("references", []) or []
            if isinstance(ref, dict) and ref.get("link")
        ]
        return text or None, urls


def _extract_text(overview: dict[str, Any]) -> str:
    snippets: list[str] = []
    for block in overview.get("text_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("snippet"):
            snippets.append(str(block["snippet"]))
        for item in block.get("list", []) or []:
            if isinstance(item, dict) and item.get("snippet"):
                snippets.append(str(item["snippet"]))
    return " ".join(snippets)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = AIOverviewsEngine()
    except ValueError as exc:
        print(f"Cannot run AI Overviews engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations("best CRM for startups")
    print(f"[{AIOverviewsEngine.ENGINE_NAME}] response: {answer}")
    print(f"[{AIOverviewsEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
