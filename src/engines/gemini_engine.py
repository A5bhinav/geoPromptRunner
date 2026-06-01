from __future__ import annotations

import logging

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from src.config import settings
from src.engines.base import BaseEngine

__all__ = ["GeminiEngine"]

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


class GeminiEngine(BaseEngine):
    """Google Gemini 1.5 Pro engine.

    Loads the API key from ``GEMINI_API_KEY``. ``query`` returns the response
    text, or ``None`` on any error. Never raises from ``query``.
    """

    ENGINE_NAME: str = "gemini"

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env (see .env.example).")
        # google-generativeai ships incomplete re-exports; these names exist at runtime.
        genai.configure(api_key=settings.GEMINI_API_KEY)  # type: ignore[attr-defined]
        self._model = genai.GenerativeModel(MODEL)  # type: ignore[attr-defined]

    def query(self, prompt: str) -> str | None:
        try:
            response = self._model.generate_content(prompt)
        except google_exceptions.ResourceExhausted:
            logger.warning("Gemini rate limit hit for model %s", MODEL)
            return None
        except google_exceptions.DeadlineExceeded:
            logger.warning("Gemini request timed out for model %s", MODEL)
            return None
        except google_exceptions.GoogleAPIError as exc:
            logger.warning("Gemini API error: %s", exc)
            return None
        except Exception as exc:  # never let an engine crash the pipeline
            logger.warning("Gemini unexpected error: %s", exc)
            return None

        text: str | None = getattr(response, "text", None)
        if not text:
            return None
        return text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = GeminiEngine()
    except ValueError as exc:
        print(f"Cannot run Gemini engine test: {exc}")
        raise SystemExit(0) from None

    result = engine.query("In one sentence, what is the capital of France?")
    print(f"[{GeminiEngine.ENGINE_NAME}] response: {result}")
