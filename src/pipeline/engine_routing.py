"""Which engines are worth asking which intents.

The fan-out is otherwise a uniform ``queries x engines x runs`` cross product, which
assumes every surface can answer every kind of question. One surface can't:
``google_ai_overviews`` measures Google's AI Overview, and Google does not *show* an
AI Overview for a bottom-funnel local query — it shows the local pack instead. Asking
anyway spends a SERP credit to capture nothing.

Two independent measurements agree on this:

- Our own run e186c524 (Berkeley plumbing, 2026-07-28): an AI Overview came back for
  1 of 10 queries — the single ``informational`` one. 0 of 5 ``local_intent``, 0 of 3
  ``brand``.
- Industry data (2026): local-intent SERPs show a Local Pack ~93% of the time and an
  AI Overview ~15% (~7% for "near me" phrasing), against ~92% of ``informational``
  and ~97% of ``hybrid`` queries. Those last two figures were already written into
  ``src/prompts/intent.py`` (see ``HYBRID`` and ``INFORMATIONAL``) — the query-set
  layer knew this; the runner just never acted on it.

That matters because ``LOCAL_BUCKET_ALLOCATION`` gives ``local_intent`` the plurality
(0.45) of a local query set. Un-routed, most of a local audit's AIO credits go to the
one bucket where the surface structurally isn't there.

**Policies are DENYLISTS, deliberately.** ``BRAND`` is shared between the consumer and
local intent families (``intent.py``), so an allowlist of "informational + hybrid"
would also strip AIO from consumer ``CATEGORY``/``COMPARISON`` queries and silently
change the consumer product. A denylist naming ``LOCAL_INTENT`` is inert on the
consumer path by construction, because consumer query sets contain no
``local_intent`` — pinned by ``tests/test_consumer_path_regression.py``.

**What is deliberately NOT encoded:** our run also saw 0 of 3 AIO on local ``brand``
queries, which suggests brand could be skipped too. n=3, no external corroboration —
so it stays a measurement to make, not a guess to ship. Same discipline as
``local_sampling.SAMPLING_BANDS`` shipping empty rather than inventing bands.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.engines.base import BaseEngine
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query

__all__ = [
    "EnginePolicy",
    "ENGINE_POLICY",
    "should_run",
    "routed_cells",
    "routed_cell_count",
    "routed_totals",
    "routed_totals_by_name",
]


@dataclass(frozen=True)
class EnginePolicy:
    """Intents an engine should NOT be asked, plus the evidence for skipping them."""

    skip_intents: frozenset[IntentBucket] = field(default_factory=frozenset)
    rationale: str = ""


#: Engines absent from this dict are asked every intent — the default, and what every
#: engine except one does. Add an entry only with a measurement behind it.
ENGINE_POLICY: dict[str, EnginePolicy] = {
    "google_ai_overviews": EnginePolicy(
        skip_intents=frozenset({IntentBucket.LOCAL_INTENT}),
        rationale=(
            "Google shows the local pack, not an AI Overview, for bottom-funnel local "
            "queries: 0 of 5 local_intent queries returned an Overview in run e186c524, "
            "and industry data puts AI Overview presence at ~15% of local-intent SERPs "
            "(~7% for 'near me') vs ~93% for the local pack. The same surface hits ~92% "
            "of informational and ~97% of hybrid queries, so it stays on for those."
        ),
    ),
}


def should_run(engine_name: str, intent: IntentBucket) -> bool:
    """Whether ``engine_name`` should be asked a query of ``intent``."""
    policy = ENGINE_POLICY.get(engine_name)
    return True if policy is None else intent not in policy.skip_intents


def routed_cells(
    queries: list[Query], engines: list[BaseEngine], runs_per_query: int
) -> list[tuple[Query, BaseEngine, int]]:
    """The (query, engine, run_index) cells that routing actually permits.

    The single source of truth for the routed work-list, so the fan-out, the cost
    estimate and the progress denominators can never disagree about what will run.
    """
    return [
        (query, engine, run_index)
        for query in queries
        for engine in engines
        if should_run(engine.ENGINE_NAME, query.intent)
        for run_index in range(runs_per_query)
    ]


def routed_cell_count(queries: list[Query], engines: list[BaseEngine], runs_per_query: int) -> int:
    """Total calls a routed run will make (the honest denominator for a cost estimate)."""
    return len(routed_cells(queries, engines, runs_per_query))


def routed_totals_by_name(
    queries: list[Query], engine_names: list[str], runs_per_query: int
) -> dict[str, int]:
    """Per-engine call count after routing, keyed by engine name.

    The progress denominator: without this a routed engine reads as "9/145 forever"
    because it is measured against a total it was never going to reach. Name-based so
    a caller holding only names (the API's live run state) doesn't have to
    reconstruct engine instances just to count cells.
    """
    return {
        name: sum(1 for q in queries if should_run(name, q.intent)) * runs_per_query
        for name in engine_names
    }


def routed_totals(
    queries: list[Query], engines: list[BaseEngine], runs_per_query: int
) -> dict[str, int]:
    """Per-engine call count after routing, for callers holding engine instances."""
    return routed_totals_by_name(queries, [e.ENGINE_NAME for e in engines], runs_per_query)
