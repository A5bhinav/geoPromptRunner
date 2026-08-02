"""Correction runs — re-measure what failed without paying for what worked.

The bug this exists for is specific and was expensive: a run that FINISHES with
dead engines is terminal. ``list_resumable_runs`` only picks up
``running``/``queued``, and ``done_cells`` is built from row existence — but a
failed call still writes a row, so a resume steps over exactly the cells that
need retrying. Albert Nahman's 2026-07-28 cycle cost four full runs (30, 25, 35,
40 cells) to land one good measurement.

Two invariants carry the whole feature and both are asserted below: the parent is
never touched, and a correction is never mistaken for a new cycle.
"""

from __future__ import annotations

import pytest

from src.pipeline.correction import (
    answered_cells,
    plan_correction,
    unanswered_cells,
)
from src.pipeline.cost import ROUGH_COST_PER_CALL, estimate_cost_for_cells
from src.storage.models import QueryResult


def _qr(qid: str, engine: str, run: int, resp: str | None) -> QueryResult:
    return QueryResult(
        query_id=qid,
        intent="category",
        prompt=f"prompt for {qid}",
        engine_name=engine,
        run_index=run,
        response=resp,
        citations=[],
        timestamp="2026-07-28T06:26:27Z",
    )


def _one_dead_surface() -> list[QueryResult]:
    """The real shape of e186c524: one surface answered nothing, the rest worked."""
    return [
        _qr(f"q{q}", engine, run, None if engine == "openai_search" else "an answer")
        for q in range(5)
        for engine in ("perplexity", "openai_search", "anthropic_search")
        for run in range(2)
    ]


# --- the distinction the whole feature rests on -------------------------------


def test_attempted_is_not_answered() -> None:
    """A failed call still writes a row. Conflating the two IS the bug."""
    results = [
        _qr("q1", "perplexity", 0, "an answer"),
        _qr("q1", "openai_search", 0, None),
    ]
    assert answered_cells(results) == {("q1", "perplexity", 0)}
    assert unanswered_cells(results) == {("q1", "openai_search", 0)}
    # Both have rows — a row-existence check cannot tell them apart, which is why
    # `done_cells` skipped the dead cells and made a broken run unrecoverable.
    assert len(results) == 2


def test_a_correction_re_asks_only_what_failed() -> None:
    plan = plan_correction("parent", _one_dead_surface())
    assert len(plan.missing) == 10  # 5 queries x 1 dead engine x 2 runs
    assert plan.saved_calls == 20  # the two working surfaces, carried free
    assert {engine for _, engine, _ in plan.missing} == {"openai_search"}
    assert plan.is_worthwhile


def test_the_plan_names_the_dead_surface() -> None:
    """A correction whose misses are all one engine is a diagnosis, not bad luck."""
    plan = plan_correction("parent", _one_dead_surface())
    assert plan.missing_by_engine == {"openai_search": 10}
    assert "openai_search 10" in plan.summary()


# --- cost ---------------------------------------------------------------------


def test_cost_is_priced_per_engine_not_scaled_from_the_whole_run() -> None:
    """Failures concentrate on one surface, and the surfaces differ ~25x in price.

    Scaling a whole-run estimate by "fraction of cells missing" would badly
    under-charge a correction whose dead surface is the expensive one — and
    `anthropic_search` is ~48% of engine spend on the six-surface set.
    """
    cheap = [("q1", "google_ai_mode", 0)] * 10
    dear = [("q1", "anthropic_search", 0)] * 10
    cheap_usd, cheap_n = estimate_cost_for_cells(cheap)
    dear_usd, dear_n = estimate_cost_for_cells(dear)
    assert cheap_n == dear_n == 10
    assert dear_usd > cheap_usd * 10
    assert dear_usd == pytest.approx(ROUGH_COST_PER_CALL["anthropic_search"] * 10)


def test_an_empty_work_list_costs_nothing() -> None:
    assert estimate_cost_for_cells([]) == (0.0, 0)


def test_an_unknown_engine_still_gets_a_price() -> None:
    """Never free by accident — an unpriced surface must not read as costless."""
    usd, n = estimate_cost_for_cells([("q1", "some_new_surface", 0)])
    assert n == 1 and usd > 0


# --- the cases where a correction is the wrong tool ---------------------------


def test_a_fully_answered_run_has_nothing_to_correct() -> None:
    plan = plan_correction("parent", [_qr("q1", "perplexity", 0, "an answer")])
    assert plan.missing == []
    assert not plan.is_worthwhile
    assert "nothing to correct" in plan.summary()


def test_a_run_that_answered_nothing_is_not_worth_correcting() -> None:
    """It would carry nothing forward — a full re-run wearing a lineage pointer.

    And a harmful one: the `supersedes` edge would suppress the parent from the
    trend for no benefit at all.
    """
    plan = plan_correction("parent", [_qr("q1", e, 0, None) for e in ("perplexity", "openai")])
    assert plan.missing and not plan.carried
    assert not plan.is_worthwhile
    assert "nothing to carry" in plan.summary()


def test_cells_the_parent_never_attempted_are_out_of_scope() -> None:
    """Filling those would change what the run measured.

    A correction re-measures the SAME instrument. Adding cells the parent never
    asked makes it a different one, and then the cycle-over-cycle comparison is
    against something that was never run.
    """
    parent = [_qr("q1", "perplexity", 0, None)]
    plan = plan_correction("parent", parent)
    assert plan.missing == [("q1", "perplexity", 0)]
    assert all(qid == "q1" for qid, _, _ in plan.missing)


def test_the_plan_is_deterministic() -> None:
    results = _one_dead_surface()
    assert plan_correction("p", results).missing == plan_correction("p", results).missing


# --- the orchestrator wiring --------------------------------------------------


def test_resume_and_correct_are_mutually_exclusive() -> None:
    """They mean opposite things about a failed cell, so combining them is a bug.

    Resume treats an attempted cell as done; correction treats it as the work.
    """
    from src.prompts.query_set import QuerySet
    from src.pipeline.orchestrator import run_audit

    qs = QuerySet(
        client="Fort", category="wearables", competitors=[], version="v1", locked_at="", queries=[]
    )
    with pytest.raises(ValueError, match="not both"):
        run_audit(qs, [], resume_run_id="a", correct_run_id="b", persist=False)


def test_correcting_a_clean_run_raises_rather_than_spending(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src.prompts.query_set import QuerySet
    from src.pipeline import orchestrator
    from src.storage import db

    monkeypatch.setattr(db, "supports_run_lineage", lambda: True)
    monkeypatch.setattr(db, "get_query_results", lambda rid: [_qr("q1", "perplexity", 0, "ok")])
    qs = QuerySet(
        client="Fort", category="wearables", competitors=[], version="v1", locked_at="", queries=[]
    )
    with pytest.raises(orchestrator.NothingToCorrect, match="nothing to correct"):
        orchestrator.run_audit(qs, [], correct_run_id="parent", progress=False)


def test_a_database_without_the_lineage_columns_refuses_the_correction(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Better a loud stop than an untracked run that reads as an extra cycle.

    The lineage write happens AFTER the row insert, so discovering the gap then
    would leave a phantom second cycle behind — and the next report would compare
    the client against their own broken run.
    """
    from src.prompts.query_set import QuerySet
    from src.pipeline import orchestrator
    from src.storage import db

    monkeypatch.setattr(db, "supports_run_lineage", lambda: False)
    qs = QuerySet(
        client="Fort", category="wearables", competitors=[], version="v1", locked_at="", queries=[]
    )
    with pytest.raises(db.StorageError, match="schema_run_corrections.sql"):
        orchestrator.run_audit(qs, [], correct_run_id="parent", progress=False)


# --- a correction is not a new cycle ------------------------------------------


def test_the_prior_run_resolver_skips_a_superseded_run(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The corrected week must compare against the previous WEEK.

    Comparing against its own broken first attempt would report the repair of a
    failed measurement as movement in the client's visibility — the same class of
    false claim as calling model nondeterminism a fix.
    """
    from src.api import runner
    from src.storage import db

    runs = [
        {"id": "week1", "created_at": "2026-06-01", "status": "done", "query_set_version": "v1"},
        {"id": "week2-broken", "created_at": "2026-06-08", "status": "done", "query_set_version": "v1"},
        {"id": "week2-fixed", "created_at": "2026-06-08", "status": "done", "query_set_version": "v1"},
    ]
    monkeypatch.setattr(db, "list_audit_runs", lambda client: runs)
    monkeypatch.setattr(db, "superseded_run_ids", lambda client: {"week2-broken"})

    prior = runner._prior_comparable_run("week3", "Fort", "2026-06-15")
    assert prior is not None and prior[0] == "week2-fixed"


def test_without_a_correction_the_resolver_is_unchanged(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src.api import runner
    from src.storage import db

    runs = [
        {"id": "week1", "created_at": "2026-06-01", "status": "done", "query_set_version": "v1"},
    ]
    monkeypatch.setattr(db, "list_audit_runs", lambda client: runs)
    monkeypatch.setattr(db, "superseded_run_ids", lambda client: set())
    assert runner._prior_comparable_run("week2", "Fort", "2026-06-08") == ("week1", "v1")


def test_superseded_lookup_degrades_to_todays_behaviour(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A database without the column must not break the report, only lose the skip."""
    from src.storage import db

    def _boom(table: str, value: str, key: str = "id") -> list[dict[str, object]]:
        raise db.StorageError("column does not exist")

    monkeypatch.setattr(db, "_select_rows", _boom)
    assert db.superseded_run_ids("Fort") == set()
