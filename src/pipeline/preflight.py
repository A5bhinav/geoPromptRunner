"""Prove each engine can answer before spending a run's worth of calls on it.

Why this exists: run e186c524 (2026-07-28) spent 30 engine calls and finished
`done 30/30` while one of its three surfaces answered nothing — its pinned model had
been deprecated and returned 404 on every call. The engine behaved correctly
(``None`` on error, never raising), so nothing crashed and nothing warned.

**The probe must be a real invocation.** OpenAI's ``models.list`` still returns the
dead model id, so a listing check would have passed at the exact moment every call
was failing. Only sending a request finds this out. That is the whole design
constraint: one cheap real call per engine, before the fan-out, so a 145-call local
audit cannot discover a broken surface on call 145.

Cost is one call per engine per run — a few cents against a run that costs dollars.
Set ``ENGINE_PREFLIGHT=0`` to skip it (tests and the fast teaser path do).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.engines.base import BaseEngine

__all__ = ["EngineProbe", "PROBE_PROMPT", "probe_engines", "split_by_liveness"]

logger = logging.getLogger(__name__)

# Deliberately generic: no brand, no client category, no locale. A probe answer must
# never be mistakable for a measurement, and it is never persisted — so this string
# must stay unrelated to any query set. Do not "improve" it toward a real query.
PROBE_PROMPT = "In one sentence, what is a good beginner bicycle?"


@dataclass(frozen=True)
class EngineProbe:
    """One engine's liveness result."""

    engine_name: str
    model_id: str
    alive: bool
    chars: int
    citations: int
    # Set when the engine answered only on the retry — a surface that needs two
    # attempts to speak is alive but worth noticing in the run record.
    needed_retry: bool = False

    # The provider's own explanation, when it gave one ("Please verify your account",
    # "insufficient balance"). Far more actionable than our guess, so it wins.
    provider_error: str | None = None

    @property
    def detail(self) -> str:
        """Human-readable reason, suitable for a skipped-engine entry."""
        if self.alive:
            return f"answered {self.chars} chars, {self.citations} citations"
        if self.provider_error:
            return f"liveness probe failed — {self.provider_error}"
        return (
            "liveness probe returned no answer "
            "(model deprecated, key rejected, or provider down)"
        )


def _probe_one(engine: BaseEngine) -> EngineProbe:
    """Probe one engine. Never raises — mirrors the engine contract."""
    for attempt in (0, 1):
        try:
            # BaseEngine.probe, not query: for a SERP-capture surface "returned no text"
            # is normal data rather than a failure, so each engine decides what being
            # reachable means for it. See BaseEngine.probe and the SERP engines' overrides.
            alive, chars, citations = engine.probe(PROBE_PROMPT)
        except Exception as exc:  # engines shouldn't raise; treat a breach as dead
            logger.warning(
                "Engine %s raised during preflight (contract breach): %s",
                engine.ENGINE_NAME,
                type(exc).__name__,
            )
            alive, chars, citations = False, 0, 0
        if alive:
            return EngineProbe(
                engine_name=engine.ENGINE_NAME,
                model_id=engine.MODEL_ID,
                alive=True,
                chars=chars,
                citations=citations,
                needed_retry=attempt == 1,
            )
    # Two attempts, no answer. One retry is deliberate: a transient 429 at t=0 must
    # not condemn a working surface for the whole run, but a second silence is a real
    # signal rather than noise.
    return EngineProbe(
        engine_name=engine.ENGINE_NAME,
        model_id=engine.MODEL_ID,
        alive=False,
        chars=0,
        citations=0,
        provider_error=engine.last_error,
    )


def probe_engines(engines: list[BaseEngine]) -> list[EngineProbe]:
    """Probe every engine concurrently, in the order given.

    Returns one ``EngineProbe`` per engine, positionally aligned with ``engines``.
    Never raises.
    """
    if not engines:
        return []
    with ThreadPoolExecutor(max_workers=len(engines)) as pool:
        return list(pool.map(_probe_one, engines))


def split_by_liveness(
    engines: list[BaseEngine],
) -> tuple[list[BaseEngine], list[tuple[str, str]], dict[str, object]]:
    """Probe ``engines`` and split them into (live, skipped, probe_record).

    ``skipped`` matches the ``(name, reason)`` shape the runner already uses for
    engines that couldn't be built, so a dead surface is reported through the same
    path as a missing API key — a distinction the caller doesn't need to care about.
    ``probe_record`` is JSON-safe, for persisting on the run row.
    """
    probes = probe_engines(engines)
    live: list[BaseEngine] = []
    skipped: list[tuple[str, str]] = []
    record: dict[str, object] = {}
    for engine, probe in zip(engines, probes, strict=True):
        record[probe.engine_name] = {
            "model_id": probe.model_id,
            "alive": probe.alive,
            "chars": probe.chars,
            "citations": probe.citations,
            "needed_retry": probe.needed_retry,
            # Persisted with the run so "why is this surface missing?" is answerable
            # months later, without the log line that produced it.
            "provider_error": probe.provider_error,
        }
        if probe.alive:
            live.append(engine)
            if probe.needed_retry:
                logger.info("Engine %s answered only on retry", probe.engine_name)
        else:
            skipped.append((probe.engine_name, probe.detail))
            logger.warning(
                "Engine %s failed preflight and will not be run (model %s)",
                probe.engine_name,
                probe.model_id or "n/a",
            )
    return live, skipped, record
