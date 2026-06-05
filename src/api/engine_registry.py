from __future__ import annotations

import hashlib
import importlib
import logging

from src.engines.base import BaseEngine

__all__ = ["ENGINE_SOURCES", "MockEngine", "build_engines"]

logger = logging.getLogger(__name__)

# Maps the engine names a CSV may request -> (module, class). Imported lazily in
# ``build_engines`` so a missing optional SDK (e.g. google-genai not installed)
# drops just that engine instead of crashing the whole API at import time.
# Mirrors the canonical KNOWN_ENGINES set the CSV loader validates against.
ENGINE_SOURCES: dict[str, tuple[str, str]] = {
    "openai": ("src.engines.openai_engine", "OpenAIEngine"),
    "anthropic": ("src.engines.anthropic_engine", "AnthropicEngine"),
    "gemini": ("src.engines.gemini_engine", "GeminiEngine"),
    "perplexity": ("src.engines.perplexity_engine", "PerplexityEngine"),
    "openai_search": ("src.engines.openai_search_engine", "OpenAISearchEngine"),
    "anthropic_search": ("src.engines.anthropic_search_engine", "AnthropicSearchEngine"),
    "gemini_grounded": ("src.engines.gemini_grounded_engine", "GeminiGroundedEngine"),
    "google_ai_overviews": ("src.engines.ai_overviews_engine", "AIOverviewsEngine"),
}


class MockEngine(BaseEngine):
    """A keyless engine that fabricates plausible, deterministic answers.

    Lets the whole UI be exercised end to end — upload, run, report — without
    spending real API calls or configuring keys. Given the client and its
    competitors, it mentions a hash-chosen subset per query (so results vary by
    query but are reproducible) and surfaces a couple of citation URLs so the
    sources panel populates. Never a measured surface — purely for demos/tests.
    """

    ENGINE_NAME = "mock"

    def __init__(self, client: str = "", competitors: list[str] | None = None) -> None:
        self._client = client
        self._competitors = competitors or []

    def _pick(self, prompt: str) -> list[str]:
        brands = [self._client, *self._competitors]
        if not brands:
            return []
        digest = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        # Each brand is included if its bit is set in the prompt hash — stable
        # per (prompt, brand), so re-runs of the same query agree.
        chosen = [b for i, b in enumerate(brands) if b and (digest >> i) & 1]
        return chosen or [brands[0]]

    def query(self, prompt: str) -> str | None:
        chosen = self._pick(prompt)
        if not chosen:
            return "I don't have a specific recommendation for that."
        lead = chosen[0]
        rest = chosen[1:]
        answer = f"For that, the best option is {lead}."
        if rest:
            answer += " Other choices people recommend include " + ", ".join(rest) + "."
        return answer

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        chosen = self._pick(prompt)
        citations = ["https://www.reddit.com/r/recommendations"]
        if chosen:
            slug = chosen[0].lower().replace(" ", "")
            citations.append(f"https://www.{slug}.com")
        return self.query(prompt), citations


def _load_class(name: str) -> type[BaseEngine] | None:
    """Import and return an engine class, or None if its SDK isn't installed."""
    source = ENGINE_SOURCES.get(name)
    if source is None:
        return None
    module_path, class_name = source
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        logger.warning("Engine %s unavailable (SDK not installed): %s", name, exc)
        return None
    cls = getattr(module, class_name, None)
    return cls if isinstance(cls, type) and issubclass(cls, BaseEngine) else None


def build_engines(
    names: list[str], client: str = "", competitors: list[str] | None = None
) -> tuple[list[BaseEngine], list[tuple[str, str]]]:
    """Instantiate the requested engines.

    Returns ``(engines, skipped)`` where ``skipped`` is a list of
    ``(name, reason)`` for engines that couldn't be built — a missing API key,
    or an SDK that isn't installed. Never raises: a bad engine is skipped, not
    fatal, so one unavailable provider can't sink the whole run.
    """
    engines: list[BaseEngine] = []
    skipped: list[tuple[str, str]] = []
    for name in names:
        if name == MockEngine.ENGINE_NAME:
            engines.append(MockEngine(client=client, competitors=competitors))
            continue
        cls = _load_class(name)
        if cls is None:
            skipped.append((name, "engine SDK not installed"))
            continue
        try:
            engines.append(cls())
        except ValueError as exc:
            skipped.append((name, str(exc)))
    return engines, skipped


if __name__ == "__main__":
    mock = MockEngine(client="Oura", competitors=["Whoop", "Ultrahuman"])
    for q in ("best smart ring 2026", "Oura vs Whoop", "is the Oura Ring worth it"):
        resp, cites = mock.query_with_citations(q)
        print(f"{q!r}\n  -> {resp}\n  cites: {cites}")
