from __future__ import annotations

from src.engines.base import BaseEngine

__all__ = ["ROUGH_COST_PER_CALL", "estimate_cost", "CostBudgetExceeded"]

# Rough USD-per-call estimates for budgeting only — NOT billing-accurate. Search
# / grounded surfaces cost more (extra retrieval + longer context). Tune as real
# usage data comes in.
ROUGH_COST_PER_CALL: dict[str, float] = {
    "openai": 0.01,
    "anthropic": 0.012,
    "gemini": 0.002,
    "perplexity": 0.006,
    "openai_search": 0.03,
    "anthropic_search": 0.035,
    "gemini_grounded": 0.01,
    "google_ai_overviews": 0.02,  # SerpApi search credit
}
_DEFAULT_PER_CALL = 0.02


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
