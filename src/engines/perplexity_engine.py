from __future__ import annotations

import contextlib
import logging

import httpx

from src.config import settings
from src.engines.base import BaseEngine

__all__ = ["PerplexityEngine"]

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.perplexity.ai"
ENDPOINT = "/chat/completions"
MODEL = "sonar"


class PerplexityEngine(BaseEngine):
    """Perplexity engine with citation extraction.

    Loads the API key from ``PERPLEXITY_API_KEY``. ``query`` returns the
    response text; ``query_with_citations`` additionally returns the list of
    citation URLs Perplexity used. Both return ``None``/``[]`` on error and
    never raise.
    """

    ENGINE_NAME: str = "perplexity"

    def __init__(self) -> None:
        if not settings.PERPLEXITY_API_KEY:
            raise ValueError(
                "PERPLEXITY_API_KEY is not set. Add it to your .env (see .env.example)."
            )
        # Persistent client: one pooled TCP/TLS connection is reused across
        # every prompt in a run instead of reconnecting on each call. The auth
        # header is set once here and is never logged.
        self._client = httpx.Client(
            base_url=API_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.PERPLEXITY_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
        )

    def close(self) -> None:
        """Close the underlying HTTP client and release pooled connections."""
        self._client.close()

    def __del__(self) -> None:
        # Best-effort cleanup if a caller forgets to call close(): release the
        # pooled connection instead of leaking it until GC finalizes the socket.
        # __del__ must never raise, and the client may not exist if __init__
        # failed before assigning it.
        client = getattr(self, "_client", None)
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response = self._client.post(ENDPOINT, json=payload)
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("Perplexity request timed out for model %s", MODEL)
            return None, []
        except httpx.HTTPStatusError as exc:
            logger.warning("Perplexity HTTP error: %s", exc.response.status_code)
            return None, []
        except httpx.HTTPError as exc:
            logger.warning("Perplexity request error: %s", exc)
            return None, []
        except Exception as exc:  # never let an engine crash the pipeline
            logger.warning("Perplexity unexpected error: %s", exc)
            return None, []

        data = response.json()
        try:
            text: str | None = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("Perplexity response missing content: %s", exc)
            return None, []

        raw_citations = data.get("citations") or []
        citations: list[str] = [str(url) for url in raw_citations]
        return text, citations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = PerplexityEngine()
    except ValueError as exc:
        print(f"Cannot run Perplexity engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations(
        "What are the best CRM tools for early-stage B2B SaaS startups?"
    )
    print(f"[{PerplexityEngine.ENGINE_NAME}] response: {answer}")
    print(f"[{PerplexityEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
