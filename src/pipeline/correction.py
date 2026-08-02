"""Re-measure the cells a run failed to answer, without paying for the rest.

A run that FINISHES with dead engines is terminal today: ``list_resumable_runs``
only picks up ``running``/``queued``, and ``done_cells`` cannot tell an
attempted-but-unanswered cell from an answered one. So the only recovery is a
whole new audit. Albert Nahman's 2026-07-28 cycle is what that costs — four full
runs (30, 25, 35, 40 cells) to get one good measurement, because there was no way
to top up the broken one.

A **correction run** is a new immutable run that carries the parent's answered
cells verbatim and re-asks only the ones that failed
(``docs/audit-packaging-implementation.md`` §5.5).

**Why a new run and not an edit.** Filling a stored ``response: NULL`` in place
would mutate a run someone may already have been shown. Storage is create-only
(``CLAUDE.md``) and prior cycles' numbers are immutable (the packaging rules), and
both exist so that "what did we tell the client on the 14th" always has an answer.
The parent row is left exactly as it was; the correction is a separate row that
records what it supersedes.

**Why a correction is not a new cycle.** It is the same cycle measured properly.
The prior-run resolver skips any run that something supersedes, so a corrected
week compares against the previous WEEK — not against its own broken first
attempt, which would report the repair as client progress. That is the same class
of false claim as calling model nondeterminism a fix.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.pipeline.cost import estimate_cost_for_cells
from src.storage.models import QueryResult

__all__ = [
    "Cell",
    "CorrectionPlan",
    "answered_cells",
    "unanswered_cells",
    "plan_correction",
]

#: ``(query_id, engine_name, run_index)`` — the granularity everything resumes at.
Cell = tuple[str, str, int]


def _cell(result: QueryResult) -> Cell:
    return (result["query_id"], result["engine_name"], result["run_index"])


def answered_cells(results: Sequence[QueryResult]) -> set[Cell]:
    """Cells that returned an answer. The ONLY ones a correction may keep.

    Distinct from "cells that have a stored row", which is what ``done_cells``
    means during a resume, and the distinction is the entire bug: a failed call
    still writes a row (``response: None``), so a resume seeded from row existence
    skips exactly the cells a correction exists to retry.
    """
    return {_cell(r) for r in results if r["response"] is not None}


def unanswered_cells(results: Sequence[QueryResult]) -> set[Cell]:
    """Cells that were attempted and produced nothing. The correction's work-list."""
    return {_cell(r) for r in results if r["response"] is None}


@dataclass(frozen=True)
class CorrectionPlan:
    """What a correction would re-ask, and what it would cost. Pure; no calls made.

    Built before anything is spent so the decision is informed: a run that lost
    one cheap surface is worth topping up, and one that lost almost everything is
    usually better re-run from scratch — the plan says which without guessing.
    """

    parent_run_id: str
    #: Answered cells inherited from the parent, free.
    carried: list[QueryResult]
    #: Cells to re-ask.
    missing: list[Cell]
    #: How many missing cells each surface owns. This is the diagnosis: a
    #: correction whose misses are one engine is a dead surface, not bad luck.
    missing_by_engine: dict[str, int] = field(default_factory=dict)
    estimated_usd: float = 0.0

    @property
    def is_worthwhile(self) -> bool:
        """False when there is nothing to fix, or nothing worth keeping.

        With no answered cells to carry, a correction is a full re-run wearing a
        lineage pointer — and it would inherit a `supersedes` edge that suppresses
        the parent from the trend for no benefit. Say so and let the caller start
        a normal run instead.
        """
        return bool(self.missing) and bool(self.carried)

    @property
    def saved_calls(self) -> int:
        """Calls the correction does NOT have to make, versus a fresh run."""
        return len(self.carried)

    def summary(self) -> str:
        """One line for the CLI and the log. Leads with what it costs."""
        if not self.missing:
            return (
                f"Run {self.parent_run_id[:8]} answered every attempted cell — "
                f"nothing to correct."
            )
        if not self.carried:
            return (
                f"Run {self.parent_run_id[:8]} answered NO cells — there is nothing to carry "
                f"forward, so a correction saves nothing. Start a fresh run instead."
            )
        worst = sorted(self.missing_by_engine.items(), key=lambda kv: (-kv[1], kv[0]))
        breakdown = ", ".join(f"{name} {count}" for name, count in worst)
        return (
            f"Correcting run {self.parent_run_id[:8]}: re-asking {len(self.missing)} cells "
            f"(~${self.estimated_usd:.2f}), carrying {self.saved_calls} answered cells forward. "
            f"Missing by surface: {breakdown}."
        )


def plan_correction(parent_run_id: str, parent_results: Sequence[QueryResult]) -> CorrectionPlan:
    """Work out what a correction of ``parent_run_id`` would re-ask and cost.

    Pure — takes the parent's stored results and returns a plan. Nothing is
    created and nothing is spent, so a caller can show the number before
    committing to it.

    The work-list comes from cells the parent ATTEMPTED and failed. Cells it never
    attempted at all (a query added to the set since, an engine that was not in
    the run) are deliberately out of scope: filling those would change what the
    run measured, which makes it a different instrument rather than the same one
    measured properly.
    """
    carried = [r for r in parent_results if r["response"] is not None]
    missing = sorted(unanswered_cells(parent_results))
    estimated, _ = estimate_cost_for_cells(missing)
    return CorrectionPlan(
        parent_run_id=parent_run_id,
        carried=carried,
        missing=missing,
        missing_by_engine=dict(Counter(engine for _, engine, _ in missing)),
        estimated_usd=estimated,
    )


if __name__ == "__main__":

    def _qr(qid: str, engine: str, run: int, resp: str | None) -> QueryResult:
        return QueryResult(
            query_id=qid,
            intent="category",
            prompt="(mock)",
            engine_name=engine,
            run_index=run,
            response=resp,
            citations=[],
            timestamp="2026-07-28T06:26:27Z",
        )

    # The real shape of Albert Nahman's e186c524: one dead surface, not bad luck.
    results = [
        _qr(f"q{q}", engine, run, None if engine == "openai_search" else "answer")
        for q in range(5)
        for engine in ("perplexity", "openai_search", "anthropic_search")
        for run in range(2)
    ]
    plan = plan_correction("e186c524-0217-4348-be24-0e89f0673001", results)
    print(plan.summary())
    print(f"worthwhile={plan.is_worthwhile} saved_calls={plan.saved_calls}")
