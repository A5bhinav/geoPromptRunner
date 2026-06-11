from __future__ import annotations

import pytest

from src.engines.base import BaseEngine
from src.pipeline.cost import CostBudgetExceeded
from src.pipeline.orchestrator import run_audit, run_teaser
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet


class _Echo(BaseEngine):
    ENGINE_NAME = "echo"

    def query(self, prompt: str) -> str | None:
        return "The best option is YNAB. Centsible also exists."


def _query_set() -> QuerySet:
    return QuerySet(
        version="v1",
        locked_at="2026-06-02",
        category="budgeting app",
        client="Centsible",
        competitors=["YNAB"],
        queries=[
            Query("pa-01", "how do I stop overspending?", IntentBucket.PROBLEM_AWARE),
            Query("cat-01", "best budgeting app", IntentBucket.CATEGORY),
            Query("cmp-01", "YNAB alternatives", IntentBucket.COMPARISON),
        ],
    )


def test_run_audit_collects_one_result_per_query_engine_run() -> None:
    qs = _query_set()
    outcome = run_audit(qs, [_Echo()], runs_per_query=2, persist=False, progress=False)
    # 3 queries x 1 engine x 2 runs.
    assert len(outcome.results) == 6
    assert outcome.run_id is None  # persist off
    assert outcome.client_name == "Centsible"
    assert outcome.query_set_version == "v1"


def test_run_teaser_trims_to_category_comparison_buckets() -> None:
    qs = _query_set()
    outcome = run_teaser(qs, [_Echo()])
    # Only the category + comparison queries, 1 run each — the problem_aware one is dropped.
    assert {r["query_id"] for r in outcome.results} == {"cat-01", "cmp-01"}
    assert all(r["run_index"] == 0 for r in outcome.results)


def test_run_audit_aborts_when_over_budget() -> None:
    qs = _query_set()
    with pytest.raises(CostBudgetExceeded):
        run_audit(qs, [_Echo()], runs_per_query=3, persist=False, progress=False, max_cost=0.0001)
