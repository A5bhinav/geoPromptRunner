from __future__ import annotations

import logging

from google import genai
from google.genai import types

from src.config import settings
from src.engines.base import BaseEngine

__all__ = ["GeminiGroundedEngine"]

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


class GeminiGroundedEngine(BaseEngine):
    """Google Gemini with Google Search grounding (surface: Gemini-with-search).

    Uses the current ``google-genai`` SDK (the legacy ``google-generativeai``
    package can't express the google_search tool that 2.5 requires). Distinct
    from ``GeminiEngine`` (parametric memory). ``query_with_citations`` returns
    the grounded source URIs. Never raises.
    """

    ENGINE_NAME: str = "gemini_grounded"

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env (see .env.example).")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=settings.ENGINE_TEMPERATURE,
        )

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        try:
            response = self._client.models.generate_content(
                model=MODEL, contents=prompt, config=self._config
            )
        except Exception as exc:  # google-genai raises a variety of API errors
            logger.warning("Gemini grounded error: %s", type(exc).__name__)
            return None, []

        text = getattr(response, "text", None)
        urls: list[str] = []
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            grounding = getattr(candidates[0], "grounding_metadata", None)
            for chunk in getattr(grounding, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None)
                if uri:
                    urls.append(str(uri))
        if not text:
            return None, urls
        return text, urls


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = GeminiGroundedEngine()
    except ValueError as exc:
        print(f"Cannot run Gemini grounded engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations("What are the best CRM tools for startups in 2026?")
    print(f"[{GeminiGroundedEngine.ENGINE_NAME}] response: {answer}")
    print(f"[{GeminiGroundedEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
