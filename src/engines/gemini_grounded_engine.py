from __future__ import annotations

import contextlib
import logging

import httpx
from google import genai
from google.genai import types

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["GeminiGroundedEngine"]

logger = logging.getLogger(__name__)

# Stable GA name — Google offers no dated snapshots (isolation plan, L3).
MODEL = "gemini-2.5-flash"

# Gemini returns grounded sources as opaque redirect URLs on this host rather
# than the real page; we follow the redirect to recover the actual domain so
# citation/domain analytics aren't all bucketed under Google's redirector.
_REDIRECT_HOST = "vertexaisearch.cloud.google.com"
_RESOLVE_TIMEOUT = 10.0


class GeminiGroundedEngine(BaseEngine):
    """Google Gemini with Google Search grounding (surface: Gemini-with-search).

    Uses the current ``google-genai`` SDK (the legacy ``google-generativeai``
    package can't express the google_search tool that 2.5 requires). Distinct
    from ``GeminiEngine`` (parametric memory). ``query_with_citations`` returns
    the grounded source URIs. Never raises.
    """

    ENGINE_NAME: str = "gemini_grounded"
    MODEL_ID: str = MODEL

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env (see .env.example).")
        # Bounded timeout (ms) + retries — Gemini intermittently 503s under load
        # and the SDK doesn't retry unless asked. Long delays ride out the
        # free-tier per-minute 429 windows (see GeminiEngine).
        self._client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=int(settings.ENGINE_TIMEOUT_SECONDS * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=settings.ENGINE_MAX_RETRIES + 1,
                    initial_delay=10,
                    max_delay=45,
                ),
            ),
        )
        self._config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=settings.ENGINE_TEMPERATURE,
        )
        # Persistent client (pooled) for resolving grounding redirect URLs.
        self._http = httpx.Client(timeout=_RESOLVE_TIMEOUT, follow_redirects=True)

    def close(self) -> None:
        """Close the redirect-resolver HTTP client."""
        self._http.close()

    def __del__(self) -> None:
        client = getattr(self, "_http", None)
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    def _resolve(self, url: str) -> str:
        """Follow a Gemini grounding redirect to its real URL; best-effort.

        Non-redirect URLs and any failure return the input unchanged, so the
        citation is never lost — at worst it stays the redirect URL.
        """
        if _REDIRECT_HOST not in url:
            return url
        try:
            # stream so we resolve the redirect chain without downloading the body
            with self._http.stream("GET", url) as response:
                final = str(response.url)
        except httpx.HTTPError:
            return url
        return final if _REDIRECT_HOST not in final else url

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        # One isolated call: contents is the bare query string, config is fixed
        # (google_search tool + temperature). No chat object is ever reused.
        record_payload(
            self.ENGINE_NAME,
            {
                "model": MODEL,
                "contents": prompt,
                "temperature": settings.ENGINE_TEMPERATURE,
                "tools": ["google_search"],
            },
        )
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
                    urls.append(self._resolve(str(uri)))
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
