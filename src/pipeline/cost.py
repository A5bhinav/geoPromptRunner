from __future__ import annotations

from src.engines.base import BaseEngine
from src.pipeline.engine_routing import routed_totals
from src.prompts.query_set import Query

__all__ = [
    "ROUGH_COST_PER_CALL",
    "JUDGE_COST_PER_CALL",
    "PREFLIGHT_COST_PER_ENGINE",
    "OFFSITE_RUN_COST_USD",
    "estimate_cost",
    "estimate_total_cost",
    "estimate_cost_for_queries",
    "estimate_total_cost_for_queries",
    "CostBudgetExceeded",
]

# Rough USD-per-call estimates for budgeting only — NOT billing-accurate. Search
# / grounded surfaces cost more (extra retrieval + longer context). Tune as real
# usage data comes in.
ROUGH_COST_PER_CALL: dict[str, float] = {
    # gpt-5.6-luna at ~520 tokens for a parametric call (20 in / 500 out). The old value
    # here was 0.01 — roughly 7x the real rate, written for a model since repinned.
    "openai": 0.0015,
    "anthropic": 0.012,
    "gemini": 0.002,
    "perplexity": 0.006,
    "openai_search": 0.03,
    # Measured live 2026-07-30, not estimated: one call reported input=10,928 out=534
    # with 1 server web_search. At Sonnet 4.5 list ($3/$15 per 1M) plus Anthropic's
    # $10/1k web searches that is $0.0508 — 45% above the 0.035 this line used to carry.
    # n=1 and a query that searched once, so treat it as a FLOOR: a question that triggers
    # several searches costs more. Rounded up rather than down, because this figure feeds
    # MAX_AUDIT_COST_USD and an under-estimate is the failure that actually hurts.
    "anthropic_search": 0.051,
    "gemini_grounded": 0.01,
    # The AI Overviews surface has two possible vendors (see api/engine_registry). Priced
    # here at DataForSEO's live-endpoint rate — $0.002/SERP plus the ~$0.0006
    # load_async_ai_overview surcharge, which is refunded when cached data sufficed —
    # because that is the preferred vendor when its credentials exist.
    #
    # Why the vendor changed on 2026-07-28: the previous one billed a **$40/month plan
    # floor**, so a ~80-call audit spent $0.32 of a $40 commitment. DataForSEO has no floor
    # at all. That is the kind of cost a per-call table cannot express — read this for
    # relative engine comparison, never as "what does this surface cost us per month".
    "google_ai_overviews": 0.0026,
    # Google AI Mode via DataForSEO's live endpoint. Live rather than the cheaper queued
    # tiers ($0.0012 standard / $0.0024 priority) because those return a task id to poll
    # and the synchronous BaseEngine.query contract has nowhere to put one.
    "google_ai_mode": 0.004,
    # The local-pack capture (src/engines/local_pack.py), not an engine in the fan-out
    # but real spend. Serper /places at ~$0.001/query (1 credit, 2500 free) — ~20x
    # the cheapest surface in the stack, and the only one with a free tier.
    "google_local_pack": 0.001,
}
_DEFAULT_PER_CALL = 0.02
# Rough USD per judge call (one per answer). Worst case is no dedup, so the judge
# estimate uses the full call count — conservative on purpose.
#
# The comment here used to say "Haiku-tier". It isn't: JUDGE_MODEL is Sonnet 4.5, and
# deliberately so — on the 80-item gold set Haiku matched Sonnet on the structural reads
# but recalled 43% of accuracy flags against Sonnet's 95%, a 52-point gap on the exact
# metric the judge exists to protect. Cheapening this line is not available.
JUDGE_COST_PER_CALL = 0.003
# The liveness probe sends one real query per engine before the fan-out
# (src/pipeline/preflight.py), and a failing engine costs two (it retries once). Priced
# at the default per-call rate: it is a real call against a real surface, and a spend
# guard that ignores it under-reports every run by a few cents.
PREFLIGHT_COST_PER_ENGINE = _DEFAULT_PER_CALL
# The Cat 6 offsite research agent always spends when a client domain is given, and
# `estimate_total_cost` ignored it entirely — so every audit with a domain was
# under-estimated by roughly this much. Derived from the agent's own hard caps rather
# than guessed: MAX_STEPS = 8 (src/audit/offsite/models.py) Sonnet turns at
# _AGENT_MAX_TOKENS = 2048 (src/audit/offsite/agent.py:53), plus its tool quota of 5
# Serper searches (~$0.001 each) + 3 Reddit searches (free) + one DataForSEO backlinks
# call (~$0.02). Tool spend rounds to ~$0.03; the 8 LLM turns dominate. A ceiling, not
# an average: most runs stop early.
OFFSITE_RUN_COST_USD = 0.35


class CostBudgetExceeded(Exception):
    """Raised when an estimated run cost exceeds the caller's budget."""


def estimate_cost(
    num_queries: int, engines: list[BaseEngine], runs_per_query: int
) -> tuple[float, int]:
    """Return (estimated_usd, total_calls) for a run. Rough, for budgeting only."""
    total_calls = num_queries * len(engines) * runs_per_query
    per_query_cost = sum(ROUGH_COST_PER_CALL.get(e.ENGINE_NAME, _DEFAULT_PER_CALL) for e in engines)
    estimated = per_query_cost * num_queries * runs_per_query
    return estimated, total_calls


def estimate_total_cost(
    num_queries: int, engines: list[BaseEngine], runs_per_query: int, judge: bool
) -> tuple[float, int]:
    """Like ``estimate_cost`` but adds the LLM judge (one call per answer, no
    dedup assumed) when judging is on — so a spend guard sees the true ceiling."""
    engine_cost, total_calls = estimate_cost(num_queries, engines, runs_per_query)
    judge_cost = JUDGE_COST_PER_CALL * total_calls if judge else 0.0
    return engine_cost + judge_cost, total_calls


# --- Routing-aware estimates ----------------------------------------------------
#
# The count-based functions above assume every engine is asked every query. Once
# routing skips intents an engine can't answer (engine_routing.py), that over-counts
# both the spend and the progress denominator. These take the actual queries so the
# estimate matches the work-list the runner will build. The count-based versions stay
# for callers that only have a query count, and stay behaviourally identical.


def estimate_cost_for_queries(
    queries: list[Query], engines: list[BaseEngine], runs_per_query: int
) -> tuple[float, int]:
    """Return (estimated_usd, total_calls) for the cells routing will actually run."""
    totals = routed_totals(queries, engines, runs_per_query)
    estimated = sum(
        ROUGH_COST_PER_CALL.get(name, _DEFAULT_PER_CALL) * calls for name, calls in totals.items()
    )
    return estimated, sum(totals.values())


def estimate_total_cost_for_queries(
    queries: list[Query],
    engines: list[BaseEngine],
    runs_per_query: int,
    judge: bool,
    *,
    preflight: bool = False,
    offsite: bool = False,
) -> tuple[float, int]:
    """Routing-aware ceiling: engine calls + judge calls + the liveness probe + Cat 6.

    ``total_calls`` counts only measurement cells — the probe and the offsite agent are
    spend, not measurement, so folding them into the progress denominator would make a
    run look permanently incomplete.
    """
    engine_cost, total_calls = estimate_cost_for_queries(queries, engines, runs_per_query)
    judge_cost = JUDGE_COST_PER_CALL * total_calls if judge else 0.0
    probe_cost = PREFLIGHT_COST_PER_ENGINE * len(engines) if preflight else 0.0
    offsite_cost = OFFSITE_RUN_COST_USD if offsite else 0.0
    return engine_cost + judge_cost + probe_cost + offsite_cost, total_calls
