from __future__ import annotations

import logging

from google import genai
from google.genai import types

from src.config import settings
from src.engines.base import BaseEngine

__all__ = ["GeminiEngine"]

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


class GeminiEngine(BaseEngine):
    """Google Gemini engine (parametric memory, no grounding).

    Uses the current ``google-genai`` SDK. Loads the API key from
    ``GEMINI_API_KEY``. ``query`` returns the response text, or ``None`` on any
    error. Never raises from ``query``. For the live-retrieval surface see
    ``GeminiGroundedEngine``.
    """

    ENGINE_NAME: str = "gemini"

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env (see .env.example).")
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._config = types.GenerateContentConfig(temperature=settings.ENGINE_TEMPERATURE)

    def query(self, prompt: str) -> str | None:
        try:
            response = self._client.models.generate_content(
                model=MODEL, contents=prompt, config=self._config
            )
        except Exception as exc:  # google-genai raises varied API errors; never crash the run
            logger.warning("Gemini error: %s", type(exc).__name__)
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
