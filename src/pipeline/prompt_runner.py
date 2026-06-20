from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from src.config import settings
from src.engines.base import BaseEngine
from src.prompts.query_set import Query
from src.storage.models import PromptResult, QueryResult

__all__ = ["run_prompts", "run_query_set"]

logger = logging.getLogger(__name__)


class _ProviderGate:
    """Per-provider concurrency limiter.

    Each engine name gets its own bounded semaphore, created on first use, so
    the runner can fan many cells out across providers while never exceeding a
    single provider's in-flight cap (its rate-limit budget). One shared lock
    guards the lazy creation of the per-provider semaphores.
    """

    def __init__(self, limit: int, overrides: Mapping[str, int] | None = None) -> None:
        self._limit = max(1, limit)
        self._overrides = dict(overrides or {})
        self._sems: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> threading.Semaphore:
        with self._lock:
            sem = self._sems.get(name)
            if sem is None:
                sem = threading.Semaphore(self._overrides.get(name, self._limit))
                self._sems[name] = sem
            return sem


def run_prompts(prompts: list[str], engines: list[BaseEngine]) -> list[PromptResult]:
    """Send every prompt to every engine and collect the results.

    Synchronous and order-stable: iterates prompts in order, and within each
    prompt iterates engines in order. Because every engine returns ``None``
    rather than raising on error, one failing engine never aborts the run.
    """
    results: list[PromptResult] = []
    for prompt in prompts:
        for engine in engines:
            response = engine.query(prompt)
            results.append(
                PromptResult(
                    prompt=prompt,
                    engine_name=engine.ENGINE_NAME,
                    response=response,
                    timestamp=datetime.now(UTC).isoformat(),
                )
            )
    return results


def run_query_set(
    queries: list[Query],
    engines: list[BaseEngine],
    runs_per_query: int = settings.DEFAULT_RUNS_PER_QUERY,
    *,
    done_cells: set[tuple[str, str, int]] | None = None,
    max_workers: int | None = None,
    provider_limits: Mapping[str, int] | None = None,
    on_result: Callable[[QueryResult], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[QueryResult]:
    """Run every query against every engine ``runs_per_query`` times.

    Order-stable in its output, but the calls run **concurrently**: every
    ``(query, engine, run)`` cell is an independent, I/O-bound API request, so
    they're fanned out across a thread pool instead of blocking one at a time.
    A per-provider cap (``ENGINE_PROVIDER_CONCURRENCY``) bounds how many calls
    hit any single provider at once, so we parallelize across providers without
    tripping one provider's rate limit. The returned list is sorted back into
    the deterministic ``query → engine → run`` order regardless of finish order.

    Each query is run multiple times per cycle to average out LLM
    nondeterminism; every result carries its query id, intent, and run index so
    downstream metrics can aggregate per bucket and per run. Citations are
    captured via ``BaseEngine.query_with_citations`` (empty for engines that
    don't expose them). One failing engine never aborts the run.

    ``done_cells`` — a set of ``(query_id, engine_name, run_index)`` already
    persisted — lets a resumed run skip exactly the cells it has, at engine/run
    granularity. This is what makes resume correct when the engine set changed
    between cycles (e.g. a key was added) or a crash left a query half-finished:
    only the genuinely-missing cells are re-run, never a whole query at once.

    ``max_workers``/``provider_limits`` override the global concurrency settings
    for a single call; ``max_workers=1`` forces sequential execution.

    ``on_result`` — if given, called once per completed cell, **serialized**
    (never two at once) so a caller can persist/update progress incrementally
    without its own lock. This is what lets a caller fan out the whole query set
    at once yet still stream results to storage as they land. ``should_cancel``
    — polled before each cell starts; once it returns True, queued-but-unstarted
    cells are skipped (in-flight calls still finish), so a cancelled run stops
    issuing new API calls promptly. Skipped cells are simply absent from the
    output (and never persisted), so a resume refills them.
    """
    if runs_per_query < 1:
        raise ValueError(f"runs_per_query must be >= 1, got {runs_per_query}")

    skip = done_cells or set()

    # Build the ordered work-list of cells to run (skipping already-done ones).
    # The index pins each cell's position so the output stays deterministic even
    # though the threads finish in arbitrary order.
    cells: list[tuple[Query, BaseEngine, int]] = []
    for query in queries:
        for engine in engines:
            for run_index in range(runs_per_query):
                if (query.query_id, engine.ENGINE_NAME, run_index) in skip:
                    continue
                cells.append((query, engine, run_index))

    if not cells:
        return []

    workers = max_workers if max_workers is not None else settings.ENGINE_CONCURRENCY
    workers = max(1, min(workers, len(cells)))
    gate = _ProviderGate(settings.ENGINE_PROVIDER_CONCURRENCY, provider_limits)
    cb_lock = threading.Lock()

    def run_cell(cell: tuple[Query, BaseEngine, int]) -> QueryResult | None:
        query, engine, run_index = cell
        # Honor cancellation before spending an API call: queued-but-unstarted
        # cells bail here, returning None (not persisted, refilled on resume).
        if should_cancel is not None and should_cancel():
            return None
        # Bound concurrent calls per provider; the call itself never raises
        # (engine contract), but guard defensively so one unexpected error can't
        # poison the pool — a failed cell becomes a None response, like any
        # engine failure, preserving the cell so resume can refill it.
        try:
            with gate.get(engine.ENGINE_NAME):
                # Re-check after acquiring the gate: a cell can wait here behind
                # the per-provider semaphore while a cancel arrives — bail rather
                # than spend the API call we were queued for.
                if should_cancel is not None and should_cancel():
                    return None
                response, citations = engine.query_with_citations(query.text)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "Cell %s/%s/%d failed: %s",
                query.query_id,
                engine.ENGINE_NAME,
                run_index,
                type(exc).__name__,
            )
            response, citations = None, []
        result = QueryResult(
            query_id=query.query_id,
            intent=query.intent.value,
            prompt=query.text,
            engine_name=engine.ENGINE_NAME,
            run_index=run_index,
            response=response,
            citations=citations,
            timestamp=datetime.now(UTC).isoformat(),
        )
        if on_result is not None:
            with cb_lock:  # serialize callbacks so the caller needs no lock
                on_result(result)
        return result

    if workers == 1:
        return [r for cell in cells if (r := run_cell(cell)) is not None]

    # Fan the cells out, then re-sort the completed ones back into the
    # deterministic query → engine → run order (threads finish out of order).
    indexed: dict[int, QueryResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_cell, cell): i for i, cell in enumerate(cells)}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                indexed[futures[future]] = result
    return [indexed[i] for i in sorted(indexed)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # A keyless echo engine so the runner is demonstrable without API keys.
    class _EchoEngine(BaseEngine):
        ENGINE_NAME = "echo"

        def query(self, prompt: str) -> str | None:
            return f"echo: {prompt}"

    engines: list[BaseEngine] = [_EchoEngine()]

    # Add any real engines whose API keys happen to be configured.
    from src.engines.anthropic_engine import AnthropicEngine
    from src.engines.gemini_engine import GeminiEngine
    from src.engines.openai_engine import OpenAIEngine
    from src.engines.perplexity_engine import PerplexityEngine

    for cls in (OpenAIEngine, AnthropicEngine, PerplexityEngine, GeminiEngine):
        try:
            engines.append(cls())
        except ValueError as exc:
            print(f"Skipping {cls.__name__}: {exc}")

    sample_prompts = [
        "What is the best CRM for early-stage B2B SaaS startups?",
        "Which project management tool do developers recommend?",
        "Name a good analytics platform for product teams.",
    ]

    run_results = run_prompts(sample_prompts, engines)
    print(f"Ran {len(sample_prompts)} prompts across {len(engines)} engine(s).")
    print(f"Collected {len(run_results)} results.")
