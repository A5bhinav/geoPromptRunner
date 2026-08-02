from __future__ import annotations

from collections.abc import Iterable

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
    "estimate_cost_for_cells",
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
    # gpt-5.6-luna + the Responses web_search tool (repinned 2026-08-01 off
    # gpt-5-search-api, which answered nothing against a 6k TPM cap).
    #
    # MEASURED 2026-08-01 on this exact configuration, n=3 (budgeting/plumber/smart-ring):
    # mean 31,098 in / 1,199 out / 3.3 web_search calls per answer. At $0.20/1M in +
    # $1.20/1M out + the $10/1k hosted-tool fee that is $0.0062 + $0.0014 + $0.0333 =
    # ~$0.041. Priced off the PRICING PAGE, not the model page — an OpenAI model page
    # carried a two-day-stale Luna price on 2026-08-01.
    #
    # THE TOOL FEE DOMINATES, at 81% of the cost: OpenAI bills "$10.00 / 1k calls", and one
    # answer makes 2-5 calls, not one. The pre-measurement estimate of $0.014 assumed one
    # call per request and a 16,700/530 token profile carried over from gpt-5-search-api —
    # both wrong, which is why this line is ~3x higher than planned. Retrieved content is
    # already inside the measured input count ("search content tokens billed at model
    # rates"), so it is not double-counted here.
    "openai_search": 0.041,
    # claude-sonnet-5 + the web_search server tool (repinned 2026-08-01 off
    # claude-sonnet-4-5-20250929).
    #
    # MEASURED 2026-08-01, n=3 on the same queries: mean 18,171 in / 1,123 out / 1.7 server
    # web searches. At Sonnet 5's introductory $2/$10 per 1M plus Anthropic's $10/1k web
    # searches that is $0.0363 + $0.0112 + $0.0167 = ~$0.064.
    #
    # This SUPERSEDES the 2026-07-30 n=1 figure (10,928 in / 534 out / 1 search → $0.051 on
    # Sonnet 4.5), which was correctly flagged as a floor and was one: the n=3 mean is 66%
    # higher on input and 2x on output. Repinning to Sonnet 5 cut the per-token rate by a
    # third and the measured token profile more than ate the saving.
    #
    # EXPIRES 2026-09-01, when Sonnet 5's introductory pricing ends ($3/$15). The same
    # measured profile then costs ~$0.088. Raise this line on that date.
    #
    # Still the largest single line on the six-surface set (~48% of engine spend), and
    # still a floor in the sense that search count varies by question. Under-estimates are
    # the failure that hurts — this figure feeds MAX_AUDIT_COST_USD.
    "anthropic_search": 0.064,
    # gemini-3.6-flash (repinned 2026-08-01 off gemini-2.5-flash).
    #
    # MEASURED 2026-08-01, n=3: mean 267 in / 1,171 answer out / 875 thinking / 2.7 search
    # queries executed. Thinking bills as output, so the billable output is ~2,046 tokens.
    # At $1.50/1M in + $7.50/1M out that is ~$0.016 — up from the 0.01 carried over from
    # 2.5-flash, which was an under-estimate. 3.6-flash's output rate is what dominates.
    #
    # TIERED, and a flat figure cannot say so. Grounding is free for the first 5,000 SEARCH
    # QUERIES per month, shared across all Gemini 3.x models; beyond that it is $14 per
    # 1,000. Google's own note: "A customer-submitted request to Gemini may result in one
    # or more queries to Google Search. You will be charged for each individual search
    # query performed." At the measured 2.7 queries/answer, a 75-cell audit burns ~200 of
    # the allowance — i.e. ~25 audits/month before this line becomes ~$0.053/call. 2.5
    # billed per PROMPT with a 1,500/day allowance, so this is a different shape, not just
    # a different number.
    "gemini_grounded": 0.016,
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
#
# Raised 0.003 -> 0.0098 on 2026-08-01: 0.003 was an UNDER-estimate, which is the
# direction that actually hurts, because this feeds MAX_AUDIT_COST_USD. Basis is the
# cached single-Sonnet judge (one forced-tool call per unique answer, with the rubric
# system block cached) plus the flag verifier at the observed flag rate.
#
# NOTE THE SCALE: this multiplies by the FULL cell count, so on a 6-surface x 25-query x
# K=3 = 450-cell run the judge component moves from $1.35 to ~$4.41. That is correct for
# an API-judged run. It is pure phantom spend for a run that will be prejudged on the
# subscription, where the real judge cost is $0 — which is why every caller that isn't
# going to judge over the API must pass judge=False rather than leave it defaulted.
JUDGE_COST_PER_CALL = 0.0098
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


def estimate_cost_for_cells(cells: Iterable[tuple[str, str, int]]) -> tuple[float, int]:
    """Cost of an explicit list of ``(query_id, engine_name, run_index)`` cells.

    For a correction run, where the work-list is "the cells that failed" rather
    than "the query set". Priced PER ENGINE rather than by scaling the full
    estimate proportionally, because failures concentrate on one surface — that is
    the failure mode, not a coincidence — and the per-call rates differ by ~25x
    across the six. Scaling the whole-run estimate by a cell fraction would
    over-charge a run whose only dead surface was `google_ai_mode` and badly
    under-charge one whose dead surface was `anthropic_search`.
    """
    cell_list = list(cells)
    estimated = sum(
        ROUGH_COST_PER_CALL.get(engine, _DEFAULT_PER_CALL) for _, engine, _ in cell_list
    )
    return estimated, len(cell_list)


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
