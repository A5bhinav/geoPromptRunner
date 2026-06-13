from __future__ import annotations

import logging
from datetime import UTC, datetime

from src.engines.base import BaseEngine
from src.prompts.query_set import Query
from src.storage.models import PromptResult, QueryResult

__all__ = ["run_prompts", "run_query_set"]

logger = logging.getLogger(__name__)


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
    runs_per_query: int = 3,
    *,
    done_cells: set[tuple[str, str, int]] | None = None,
) -> list[QueryResult]:
    """Run every query against every engine ``runs_per_query`` times.

    Synchronous and order-stable. Each query is run multiple times per cycle to
    average out LLM nondeterminism; every result carries its query id, intent,
    and run index so downstream metrics can aggregate per bucket and per run.
    Citations are captured via ``BaseEngine.query_with_citations`` (empty for
    engines that don't expose them). One failing engine never aborts the run.

    ``done_cells`` — a set of ``(query_id, engine_name, run_index)`` already
    persisted — lets a resumed run skip exactly the cells it has, at engine/run
    granularity. This is what makes resume correct when the engine set changed
    between cycles (e.g. a key was added) or a crash left a query half-finished:
    only the genuinely-missing cells are re-run, never a whole query at once.
    """
    if runs_per_query < 1:
        raise ValueError(f"runs_per_query must be >= 1, got {runs_per_query}")

    skip = done_cells or set()
    results: list[QueryResult] = []
    for query in queries:
        for engine in engines:
            for run_index in range(runs_per_query):
                if (query.query_id, engine.ENGINE_NAME, run_index) in skip:
                    continue
                response, citations = engine.query_with_citations(query.text)
                results.append(
                    QueryResult(
                        query_id=query.query_id,
                        intent=query.intent.value,
                        prompt=query.text,
                        engine_name=engine.ENGINE_NAME,
                        run_index=run_index,
                        response=response,
                        citations=citations,
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                )
    return results


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
