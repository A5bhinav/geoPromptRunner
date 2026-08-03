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
        # `error` is passed by the terminal-status write in run_audit's `finally`.
        lambda rid, completed_calls, status, error=None: progress_calls.append(
            (completed_calls, status)
        ),
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


# --- W2.1: kind-keyed teaser bucket selection -------------------------------------
# The consumer pair and the local intents are DISJOINT. Before the fork, a local query
# set intersected _TEASER_BUCKETS in zero queries and the teaser ran empty.


def test_teaser_buckets_are_forked_by_business_kind() -> None:
    from src.pipeline.orchestrator import teaser_buckets
    from src.prompts.intent import IntentBucket

    assert teaser_buckets() == (IntentBucket.CATEGORY, IntentBucket.COMPARISON)
    assert teaser_buckets("product") == (IntentBucket.CATEGORY, IntentBucket.COMPARISON)
    assert teaser_buckets("local_service") == (IntentBucket.LOCAL_INTENT, IntentBucket.HYBRID)
    # Unknown kinds fall back to the pre-pivot consumer pair.
    assert teaser_buckets("something-else") == (IntentBucket.CATEGORY, IntentBucket.COMPARISON)


def test_local_teaser_excludes_informational() -> None:
    """'how often should a furnace be serviced' surfaces an AI Overview but yields
    advice, not a ranked set of shops — it cannot produce the competitor-naming
    moment the teaser exists for."""
    from src.pipeline.orchestrator import teaser_buckets
    from src.prompts.intent import IntentBucket

    assert IntentBucket.INFORMATIONAL not in teaser_buckets("local_service")


def test_run_teaser_raises_rather_than_running_an_empty_query_set() -> None:
    """A zero-query teaser would report 'you appear nowhere' from no measurement at
    all — the exact silent-and-wrong failure the pivot plan guards against."""
    import pytest

    from src.pipeline.orchestrator import run_teaser
    from src.prompts.intent import IntentBucket
    from src.prompts.query_set import Query, QuerySet

    local_set = QuerySet(
        version="v1",
        locked_at="2026-07-27",
        category="plumbing service",
        client="Bay Rooter",
        competitors=[],
        queries=[Query(query_id="l1", text="best plumber in Berkeley", intent=IntentBucket.LOCAL_INTENT)],
    )
    # Running a LOCAL set through the CONSUMER buckets matches nothing.
    with pytest.raises(ValueError, match="no queries match the product teaser buckets"):
        run_teaser(local_set, engines=[], business_kind="product")


# --- P0: a CLI run must always reach a TERMINAL status ----------------------------
# Before this, `status="done"` was written on one line on the happy path only, so a
# Ctrl-C / crash left the row at "running" forever. The API's next startup scan then
# relabelled it "interrupted" — a status that actually means "we could not rebuild
# this at startup", which was never what happened. Worse, a process that died between
# its last result write and that success line left a COMPLETE run stuck at "running",
# and _prior_comparable_run (runner.py, `status == "done"`) then excluded a perfectly
# good cycle from trend comparison permanently.
#
# Both tests fake the db module outright: they must make no engine calls and cost
# nothing.


class _Boom(BaseEngine):
    """Engine that aborts the run partway through the query set.

    It raises KeyboardInterrupt on purpose, not a plain Exception: `run_query_set`
    catches `Exception` and turns a failed cell into a None response (the "engines
    never raise, the pipeline never crashes because one engine failed" invariant),
    so an ordinary engine error does NOT abort the loop and cannot exercise this
    path. KeyboardInterrupt is a BaseException, so it propagates — which is exactly
    the Ctrl-C case this P0 fix exists for.
    """

    ENGINE_NAME = "boom"

    def __init__(self, fail_on: str) -> None:
        self.fail_on = fail_on
        self.seen: list[str] = []

    def query(self, prompt: str) -> str | None:
        self.seen.append(prompt)
        if self.fail_on in prompt:
            raise KeyboardInterrupt("operator pressed Ctrl-C")
        return "answer"


def _fake_storage(
    monkeypatch: pytest.MonkeyPatch, progress_calls: list[tuple[int, str, str | None]]
) -> None:
    monkeypatch.setattr(orchestrator.db, "create_audit_run", lambda **kw: "run-p0")
    monkeypatch.setattr(orchestrator.db, "save_query_results", lambda rid, cell: None)
    monkeypatch.setattr(
        orchestrator.db,
        "update_audit_run_progress",
        lambda rid, completed_calls, status, error=None: progress_calls.append(
            (completed_calls, status, error)
        ),
    )


def test_run_audit_marks_cancelled_when_a_query_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Ctrl-C mid-loop leaves the row terminal as `cancelled` — never `running`.

    "cancelled" rather than "failed": an operator aborting is not an error, and the
    UI, _prior_comparable_run and the engine-state rollup already treat cancelled as
    terminal.
    """
    progress_calls: list[tuple[int, str, str | None]] = []
    _fake_storage(monkeypatch, progress_calls)

    with pytest.raises(KeyboardInterrupt):
        run_audit(
            _query_set(),
            [_Boom(fail_on="best budgeting app")],  # aborts on query 2 of 3
            runs_per_query=1,
            progress=False,
        )

    assert progress_calls, "the terminal-status write must run even when the loop dies"
    completed_calls, status, error = progress_calls[-1]
    assert status == "cancelled"
    assert error == "aborted before all queries ran"
    # Whatever landed before the abort is still counted, not zeroed.
    assert completed_calls == 1


def test_run_audit_marks_done_when_the_loop_finished_then_something_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run whose loop COMPLETED stays `done` even if the process then dies.

    This is the silent one: complete data, but the old code's success line was never
    reached, so the run sat at "running" -> "interrupted" and was dropped from trend
    comparison forever, recoverable only by editing the row by hand.
    """
    progress_calls: list[tuple[int, str, str | None]] = []
    _fake_storage(monkeypatch, progress_calls)

    # engine_models() is called once while creating the run and again after the
    # measurement loop, when the outcome is assembled — i.e. after the terminal-status
    # write. Failing the second call simulates dying just past the finish line.
    real = orchestrator.engine_models
    calls = {"n": 0}

    def _die_after_the_loop(engines: list[BaseEngine]) -> dict[str, str]:
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("process died after the last write")
        return real(engines)

    monkeypatch.setattr(orchestrator, "engine_models", _die_after_the_loop)

    with pytest.raises(RuntimeError):
        run_audit(_query_set(), [_Echo()], runs_per_query=1, progress=False)

    assert progress_calls, "the terminal-status write must run"
    completed_calls, status, error = progress_calls[-1]
    assert status == "done", "a completed loop must never be downgraded"
    assert error is None
    assert completed_calls == 3


def test_run_audit_terminal_write_failure_does_not_mask_the_real_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A storage failure in the `finally` must not replace the original exception."""
    monkeypatch.setattr(orchestrator.db, "create_audit_run", lambda **kw: "run-p0")
    monkeypatch.setattr(orchestrator.db, "save_query_results", lambda rid, cell: None)

    def _storage_down(
        rid: str, completed_calls: int, status: str, error: str | None = None
    ) -> None:
        raise orchestrator.StorageError("supabase unreachable")

    monkeypatch.setattr(orchestrator.db, "update_audit_run_progress", _storage_down)

    # The operator's Ctrl-C must surface, not the StorageError from the finally.
    with pytest.raises(KeyboardInterrupt):
        run_audit(
            _query_set(),
            [_Boom(fail_on="best budgeting app")],
            runs_per_query=1,
            progress=False,
        )
