from __future__ import annotations

import hashlib
import importlib
import logging
from typing import Literal

from src.engines.base import BaseEngine

__all__ = ["ENGINE_SOURCES", "MockEngine", "build_engines", "engine_class", "sampling_for"]

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
    # Both Google surfaces come from DataForSEO (pay-as-you-go, no monthly floor). The
    # engine NAME is the surface, not the vendor — everything downstream (routing policy,
    # cost table, teaser labels/colours/credibility, every stored run's engine_name) keys
    # on these strings, and they survived the 2026-07-28 vendor change untouched.
    "google_ai_overviews": (
        "src.engines.dataforseo_ai_overviews",
        "DataForSEOAIOverviewsEngine",
    ),
    # Google's conversational answer surface. Unlike AI Overviews it answers every
    # intent, so it needs no routing skip and covers the local-intent buying moment
    # that AI Overviews structurally cannot.
    "google_ai_mode": ("src.engines.dataforseo_ai_mode", "DataForSEOAIModeEngine"),
}


#: Engines whose constructor takes a market. These are the SERP-capture surfaces — the
#: model APIs have no locale knob, so a location is silently irrelevant to them rather
#: than an error: a local run still wants those surfaces measured, just un-localized.
_LOCATION_AWARE: frozenset[str] = frozenset({"google_ai_overviews", "google_ai_mode"})


class MockEngine(BaseEngine):
    """A keyless engine that fabricates plausible, deterministic answers.

    Lets the whole UI be exercised end to end — upload, run, report — without
    spending real API calls or configuring keys. Given the client and its
    competitors, it mentions a hash-chosen subset per query (so results vary by
    query but are reproducible) and surfaces a couple of citation URLs so the
    sources panel populates. Never a measured surface — purely for demos/tests.
    """

    ENGINE_NAME = "mock"
    # Deterministic by construction (a hash of the prompt) — no sampling to control.
    SAMPLING: Literal["pinned", "default", "none"] = "none"

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


def engine_class(name: str) -> type[BaseEngine] | None:
    """The adapter class for an engine name, without constructing it.

    Public because provenance readers (a report rendering a stored run) need an
    engine's declared MODEL_ID / SAMPLING but have no API keys and must not spend a
    call to find out.
    """
    return _load_class(name)


def sampling_for(name: str, run_model: str | None = None) -> str | None:
    """How ``name``'s sampling was controlled, or None when it cannot be asserted.

    ``run_model`` is the model string the *stored run* recorded for this engine. When it
    differs from the adapter's current pin, the engine has been repinned since — and a
    repin can change the sampling regime (that is exactly what the 2026-07-28 openai
    repin did). The honest answer then is None, "cannot be determined for that run",
    rather than today's label applied retroactively to yesterday's measurement.
    """
    cls = engine_class(name)
    if cls is None:
        return None
    if run_model and cls.MODEL_ID and run_model != cls.MODEL_ID:
        return None
    return cls.SAMPLING


def build_engines(
    names: list[str],
    client: str = "",
    competitors: list[str] | None = None,
    location: str | None = None,
) -> tuple[list[BaseEngine], list[tuple[str, str]]]:
    """Instantiate the requested engines.

    Returns ``(engines, skipped)`` where ``skipped`` is a list of
    ``(name, reason)`` for engines that couldn't be built — a missing API key,
    or an SDK that isn't installed. Never raises: a bad engine is skipped, not
    fatal, so one unavailable provider can't sink the whole run.

    ``location`` is Google's canonical location name ("Berkeley,California,United States")
    for service-area businesses (W1.4). Only the SERP-capture surfaces consume it
    (``_LOCATION_AWARE``); the others are model APIs with no locale knob, so a location is
    silently irrelevant to them rather than an error — a local run still wants those
    surfaces measured, just un-localized. ``None`` (the default) reproduces the pre-pivot
    behaviour exactly.
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
            if location and name in _LOCATION_AWARE:
                engines.append(cls(location=location))  # type: ignore[call-arg]  # only the SERP engines take it
            else:
                engines.append(cls())
        except ValueError as exc:
            skipped.append((name, str(exc)))
    return engines, skipped


if __name__ == "__main__":
    mock = MockEngine(client="Oura", competitors=["Whoop", "Ultrahuman"])
    for q in ("best smart ring 2026", "Oura vs Whoop", "is the Oura Ring worth it"):
        resp, cites = mock.query_with_citations(q)
        print(f"{q!r}\n  -> {resp}\n  cites: {cites}")
