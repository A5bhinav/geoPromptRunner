from __future__ import annotations

import pytest

from src.engines.base import BaseEngine
from src.pipeline import orchestrator
from src.pipeline.cost import CostBudgetExceeded
from src.pipeline.orchestrator import run_audit, run_teaser
from src.pipeline.prompt_runner import run_query_set
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet


class _Echo(BaseEngine):
    ENGINE_NAME = "echo"

    def query(self, prompt: str) -> str | None:
        return "The best option is YNAB. Centsible also exists."


class _Counter(BaseEngine):
    """Engine that records every prompt it's actually asked (to prove skips)."""

    def __init__(self, name: str) -> None:
        self.ENGINE_NAME = name
        self.calls: list[str] = []

    def query(self, prompt: str) -> str | None:
        self.calls.append(prompt)
        return f"{self.ENGINE_NAME}: answer"


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


def test_run_query_set_skips_done_cells() -> None:
    """done_cells skips exactly the (query, engine, run) cells it names — at
    engine/run granularity, never a whole query at once."""
    qs = _query_set()
    eng = _Counter("gemini")
    # Pretend cat-01 run 0 is already stored, but cat-01 run 1 is not.
    done = {("cat-01", "gemini", 0)}
    results = run_query_set(qs.queries, [eng], runs_per_query=2, done_cells=done)
    produced = {(r["query_id"], r["run_index"]) for r in results}
    assert ("cat-01", 0) not in produced  # skipped
    assert ("cat-01", 1) in produced  # the missing run still runs
    assert ("pa-01", 0) in produced and ("pa-01", 1) in produced
    assert len(eng.calls) == len(results)  # only the un-skipped cells hit the engine


def test_run_audit_resume_fills_only_missing_cells(monkeypatch: pytest.MonkeyPatch) -> None:
    """A resumed run backfills only the cells missing for the new engine set and
    returns prior + new results, and marks the run done."""
    qs = _query_set()  # 3 queries
    # Prior run had only `openai`; `gemini` is newly available on resume.
    prior = [
        {
            "query_id": q.query_id,
            "intent": q.intent.value,
            "prompt": q.text,
            "engine_name": "openai",
            "run_index": 0,
            "response": "openai: prior",
            "citations": [],
            "timestamp": "t",
        }
        for q in qs.queries
    ]
    saved: list[dict[str, object]] = []
    progress_calls: list[tuple[int, str]] = []
    monkeypatch.setattr(orchestrator.db, "get_query_results", lambda rid: prior)
    monkeypatch.setattr(
        orchestrator.db, "save_query_results", lambda rid, cell: saved.extend(cell)
    )
    monkeypatch.setattr(
        orchestrator.db,
        "update_audit_run_progress",
        lambda rid, completed_calls, status: progress_calls.append((completed_calls, status)),
    )

    openai, gemini = _Counter("openai"), _Counter("gemini")
    outcome = run_audit(
        qs, [openai, gemini], runs_per_query=1, progress=False, resume_run_id="run-123"
    )

    # openai already had every cell -> not re-run; gemini is fully backfilled.
    assert openai.calls == []
    assert len(gemini.calls) == 3
    # Outcome carries prior (3 openai) + new (3 gemini).
    assert len(outcome.results) == 6
    engines_in_outcome = {r["engine_name"] for r in outcome.results}
    assert engines_in_outcome == {"openai", "gemini"}
    # Only the new gemini cells were persisted (prior wasn't re-saved).
    assert {r["engine_name"] for r in saved} == {"gemini"}
    # Run was marked terminal.
    assert progress_calls and progress_calls[-1][1] == "done"
