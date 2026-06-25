from __future__ import annotations

import contextlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx
from google import genai
from google.genai import types

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload
from src.net_guard import UnsafeUrlError, safe_get

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
        # follow_redirects is off — safe_get follows hops manually so each is
        # SSRF-checked. A cache avoids re-fetching the same redirect across cells
        # (the engine instance is shared by the concurrent runner pool, so guard
        # the cache with a lock).
        self._http = httpx.Client(timeout=_RESOLVE_TIMEOUT, follow_redirects=False)
        self._resolve_cache: dict[str, str] = {}
        self._resolve_lock = threading.Lock()

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

        Only URLs whose host is exactly the Vertex redirector are followed (an
        earlier substring check could be tricked by ``...?x=<host>``). Redirects
        are followed manually with per-hop SSRF validation. Non-redirect URLs,
        unsafe targets, and any failure return the input unchanged, so the
        citation is never lost — at worst it stays the redirect URL. Results are
        cached since the same redirector URL recurs across cells.
        """
        if urlparse(url).hostname != _REDIRECT_HOST:
            return url
        with self._resolve_lock:
            cached = self._resolve_cache.get(url)
        if cached is not None:
            return cached
        try:
            response = safe_get(self._http, url)
            final = str(response.url)
        except (httpx.HTTPError, UnsafeUrlError):
            final = url
        if urlparse(final).hostname == _REDIRECT_HOST:
            final = url  # never resolved past the redirector
        with self._resolve_lock:
            self._resolve_cache[url] = final
        return final

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
        raw_uris: list[str] = []
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            grounding = getattr(candidates[0], "grounding_metadata", None)
            for chunk in getattr(grounding, "grounding_chunks", None) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None)
                if uri:
                    raw_uris.append(str(uri))
        # Resolve the redirect URLs concurrently (each is an independent network
        # hop); order is preserved. Cached hops return immediately.
        if len(raw_uris) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(raw_uris))) as pool:
                urls = list(pool.map(self._resolve, raw_uris))
        else:
            urls = [self._resolve(u) for u in raw_uris]
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

    answer, urls = engine.query_with_citations("What are the best budgeting apps in 2026?")
    print(f"[{GeminiGroundedEngine.ENGINE_NAME}] response: {answer}")
    print(f"[{GeminiGroundedEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
