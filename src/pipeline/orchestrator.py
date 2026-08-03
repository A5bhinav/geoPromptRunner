from __future__ import annotations

import dataclasses
import logging
from dataclasses import field

from src.config import settings
from src.engines.base import BaseEngine
from src.pipeline import preflight
from src.pipeline.correction import (
    CorrectionPlan,
    answered_cells,
    plan_correction,
)
from src.pipeline.cost import (
    CostBudgetExceeded,
    estimate_cost_for_cells,
    estimate_cost_for_queries,
)
from src.pipeline.engine_routing import ENGINE_POLICY, routed_totals
from src.pipeline.prompt_runner import run_query_set
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet
from src.storage import db
from src.storage.db import StorageError
from src.storage.models import QueryResult

__all__ = [
    "AuditOutcome",
    "EnginesUnavailable",
    "NothingToCorrect",
    "engine_models",
    "run_audit",
    "run_teaser",
]

logger = logging.getLogger(__name__)


class NothingToCorrect(RuntimeError):
    """A correction of this run would achieve nothing. Carries the reason.

    Raised rather than proceeding, because both cases produce a run that looks
    like a correction and is not one: with no failed cells there is nothing to
    re-ask, and with no answered cells there is nothing to carry, so the "top-up"
    is a full re-run that also suppresses its parent from the trend.
    """


class EnginesUnavailable(RuntimeError):
    """No engine could answer a probe query, so there is nothing to measure with.

    Raised instead of proceeding: a run against zero live surfaces produces a report
    full of honest-looking zeros, which is worse than a loud stop.
    """


def engine_models(engines: list[BaseEngine]) -> dict[str, str]:
    """Exact model string per engine, recorded in run metadata (isolation L3).

    Engines with no model parameter (SERP capture) are omitted rather than
    recorded as empty strings.
    """
    return {e.ENGINE_NAME: e.MODEL_ID for e in engines if e.MODEL_ID}


# Buckets used for the fast teaser demo — the visceral "here's who AI recommends
# instead of you" moment. FORKED by business kind (pivot §0.6), because the two
# families of intent are disjoint: a local query set built from local_intent/hybrid/
# informational intersects the consumer pair in ZERO queries, and the teaser would
# silently run empty rather than fail.
#
# Local picks local_intent + hybrid deliberately: both are buying-moment queries that
# return a RANKED SET of named shops, which is what a teaser needs. `informational`
# is excluded — "how often should a furnace be serviced" yields advice, not rivals,
# so it can't produce the competitor-naming moment even though it surfaces an AIO.
_TEASER_BUCKETS = (IntentBucket.CATEGORY, IntentBucket.COMPARISON)
_LOCAL_TEASER_BUCKETS = (IntentBucket.LOCAL_INTENT, IntentBucket.HYBRID)


def teaser_buckets(business_kind: str = "product") -> tuple[IntentBucket, ...]:
    """The teaser's query-selection buckets for one business kind.

    Unknown kinds fall back to the consumer pair — the pre-pivot behaviour.
    """
    return _LOCAL_TEASER_BUCKETS if business_kind == "local_service" else _TEASER_BUCKETS


@dataclasses.dataclass(frozen=True)
class AuditOutcome:
    """Result of one orchestrated audit run."""

    run_id: str | None  # None if storage was unavailable / disabled
    client_name: str
    client_domains: list[str]
    competitors: list[str]
    query_set_version: str
    runs_per_query: int
    results: list[QueryResult]
    #: engine name -> the exact model string it sent. Carried through to the
    #: report because every client-facing finding names the model that produced
    #: it, and re-deriving the pin at render time would name whatever is pinned
    #: TODAY rather than what answered. Empty for runs stored before it existed;
    #: the report says "model not recorded" rather than inventing one.
    engine_models: dict[str, str] = field(default_factory=dict)


def run_audit(
    query_set: QuerySet,
    engines: list[BaseEngine],
    client_domains: list[str] | None = None,
    runs_per_query: int = settings.DEFAULT_RUNS_PER_QUERY,
    persist: bool = True,
    progress: bool = True,
    max_cost: float | None = None,
    resume_run_id: str | None = None,
    correct_run_id: str | None = None,
) -> AuditOutcome:
    """Run a full audit cycle: query set -> engines -> persisted results.

    Synchronous and order-stable. Persists incrementally (one query at a time)
    so a failure mid-run keeps prior progress. ``max_cost`` aborts before any
    calls if the rough estimate exceeds the budget. If storage isn't configured,
    the run continues in-memory and ``run_id`` is None.

    Two ways to reuse an earlier run's work, and they are NOT the same thing:

    ``resume_run_id``
        Continue a run left unfinished. Skips every cell that has a stored row,
        answered or not — an attempted cell is treated as done so a resume cannot
        start re-paying for a permanently dead surface on each restart.

    ``correct_run_id``
        Re-measure an earlier run's FAILED cells (:mod:`src.pipeline.correction`).
        Creates a NEW run that carries the parent's answered cells forward and
        re-asks only the ones that returned nothing, so the parent stays exactly
        as it was and only the gaps are paid for. This is the one that makes a
        broken run cheap to fix; resume cannot, by design, because it cannot tell
        "attempted" from "answered".

    The two are mutually exclusive.
    """
    if resume_run_id is not None and correct_run_id is not None:
        raise ValueError(
            "pass resume_run_id or correct_run_id, not both — resuming continues a run "
            "in place, correcting creates a new one that supersedes it"
        )
    client_domains = client_domains or []
    queries = query_set.queries

    # Preflight before the estimate, so the printed cost reflects the surfaces that
    # will actually run. This is the path that produced run e186c524 — a full audit
    # against a surface whose model had been deprecated — so the CLI gets the same
    # protection as the API rather than being the one door left unlocked.
    if settings.ENGINE_PREFLIGHT and engines:
        live, dead, _record = preflight.split_by_liveness(engines)
        if dead and progress:
            for name, reason in dead:
                print(f"  (dropping {name}: {reason})")
        engines = live
        if not engines:
            raise EnginesUnavailable(
                "every engine failed its liveness probe — no surface could answer a test "
                "query (check model pins and API keys)"
            )

    # A correction's work-list is "the cells the parent failed", not "the query
    # set", so its plan is built FIRST and its cost estimate replaces the
    # whole-run one below. Otherwise a $1 top-up would be budget-gated as if it
    # were a $10 audit — and refused, which is the opposite of the point.
    plan: CorrectionPlan | None = None
    if correct_run_id is not None:
        # Checked before anything is created, because the lineage write happens
        # AFTER the row insert — discovering the gap then would leave an untracked
        # run behind that reads as an extra cycle.
        if persist and not db.supports_run_lineage():
            raise StorageError(
                "this database has no run_kind / supersedes_run_id columns — apply "
                "data/schema_run_corrections.sql first. Without them a correction is "
                "indistinguishable from a second cycle, and the next report would "
                "compare a client against their own broken run."
            )
        try:
            plan = plan_correction(correct_run_id, db.get_query_results(correct_run_id))
        except StorageError as exc:
            raise StorageError(f"cannot read run {correct_run_id} to correct it") from exc
        if not plan.missing:
            raise NothingToCorrect(plan.summary())
        if not plan.carried:
            # Every cell failed. A "correction" here carries nothing forward, so
            # it is a full re-run that would additionally suppress its parent from
            # the trend. Refuse and say what to do instead.
            raise NothingToCorrect(plan.summary())
        if progress:
            print(plan.summary())

    # Routing-aware: an engine skipped on some intents costs less than queries x
    # engines x runs implies, and printing the un-routed number would overstate both
    # the spend and what the run is about to measure.
    if plan is not None:
        estimated, total_calls = estimate_cost_for_cells(plan.missing)
    else:
        estimated, total_calls = estimate_cost_for_queries(queries, engines, runs_per_query)
    if progress and plan is None:
        engine_names = ", ".join(e.ENGINE_NAME for e in engines) or "none"
        print(
            f"Audit: {query_set.client} ({query_set.version}) — "
            f"{len(queries)} queries x {len(engines)} engines [{engine_names}] "
            f"x {runs_per_query} runs = {total_calls} calls (~${estimated:.2f} est.)"
        )
        for name, calls in sorted(routed_totals(queries, engines, runs_per_query).items()):
            full = len(queries) * runs_per_query
            if calls < full:
                policy = ENGINE_POLICY.get(name)
                skipped = ", ".join(sorted(i.value for i in policy.skip_intents)) if policy else ""
                print(f"  ({name}: {calls} of {full} cells — not asked {skipped})")
    if max_cost is not None and estimated > max_cost:
        raise CostBudgetExceeded(
            f"estimated ~${estimated:.2f} exceeds budget ${max_cost:.2f} "
            f"({total_calls} calls). Lower --runs, trim the query set, or raise the budget."
        )

    run_id: str | None = resume_run_id
    # Cells already persisted, at (query_id, engine, run_index) granularity, plus
    # the prior results themselves. Resuming at the cell level (not the query
    # level) is what lets a newly-added engine be backfilled and a half-finished
    # query be completed — only the genuinely-missing cells re-run.
    done_cells: set[tuple[str, str, int]] = set()
    prior_results: list[QueryResult] = []
    if resume_run_id is not None:
        try:
            prior_results = db.get_query_results(resume_run_id)
            done_cells = {
                (r["query_id"], r["engine_name"], r["run_index"]) for r in prior_results
            }
            if progress:
                done_queries = len({r["query_id"] for r in prior_results})
                print(
                    f"  Resuming run {resume_run_id}: {len(done_cells)} cells across "
                    f"{done_queries} queries already stored"
                )
        except StorageError as exc:
            logger.warning("Could not load run to resume (%s); starting fresh", exc)
            run_id = None
    elif persist:
        try:
            # A correction inherits the PARENT's answered cells as its starting
            # point. `done_cells` is seeded from what actually answered, not from
            # what has a row — that difference is the whole feature, because a
            # failed call still writes a row and a row-based skip would step over
            # exactly the cells being corrected.
            if plan is not None:
                prior_results = list(plan.carried)
                done_cells = answered_cells(prior_results)
            run_id = db.create_audit_run(
                client_name=query_set.client,
                client_domains=client_domains,
                competitors=query_set.competitors,
                category=query_set.category,
                query_set_version=query_set.version,
                query_set_locked_at=query_set.locked_at,
                runs_per_query=runs_per_query,
                engines=[e.ENGINE_NAME for e in engines],
                n_queries=len(queries),
                total_calls=total_calls,
                engine_models=engine_models(engines),
                run_kind="correction" if plan is not None else "baseline",
                supersedes_run_id=correct_run_id,
            )
            # Copy the carried answers onto the new run so it renders standalone.
            # The alternative — storing only the new cells and unioning at read
            # time — would put the join in every reader, and one reader forgetting
            # it is a report that silently loses most of its data.
            if plan is not None and run_id is not None and prior_results:
                db.save_query_results(run_id, prior_results)
        except StorageError as exc:
            logger.warning("Storage unavailable, continuing in-memory: %s", exc)
            run_id = None

    # The outcome carries prior + new results so a resumed run renders/judges the
    # whole run, not just the cells it happened to fill this pass.
    results: list[QueryResult] = list(prior_results)
    # Terminal status is derived from what actually landed, not from reaching the
    # happy path. Two bugs close here:
    #   1. A Ctrl-C / crash used to leave the row at "running", so the API's next
    #      startup scan flipped it to "interrupted" — a status that means "we could
    #      not rebuild this at startup", which was never what happened.
    #   2. A process that died between the last result write and the old success
    #      line left a COMPLETE run stuck at "running", and _prior_comparable_run
    #      (runner.py, `status == "done"`) then excluded a perfectly good cycle from
    #      the trend comparison permanently.
    # "cancelled" rather than "failed": an operator aborting is not an error, and the
    # UI, _prior_comparable_run and the engine-state rollup already treat cancelled
    # as terminal.
    #
    # Deliberately NOT fixed by storing the CLI's query set so its runs auto-resume:
    # resume_interrupted_runs() runs unattended at API startup, so an operator who
    # Ctrl-Cs a 25-query audit because they spotted a bad config would have it
    # silently relaunched — real money on engine calls nobody asked for. An abort is
    # a decision; auto-resume would quietly overrule it.
    completed = False
    try:
        for index, query in enumerate(queries, start=1):
            cell = run_query_set([query], engines, runs_per_query, done_cells=done_cells)
            if not cell:
                if progress:
                    print(f"  [{index}/{len(queries)}] {query.query_id}: skipped (already stored)")
                continue
            results.extend(cell)
            if run_id is not None:
                try:
                    db.save_query_results(run_id, cell)
                except StorageError as exc:
                    logger.warning("Failed to persist results for %s: %s", query.query_id, exc)
            if progress:
                answered = sum(1 for r in cell if r["response"] is not None)
                print(
                    f"  [{index}/{len(queries)}] {query.query_id}: "
                    f"{answered}/{len(cell)} answered"
                )
        # Inside the `try`, after the loop: an exception from the final iteration
        # must not be able to mark the run done.
        completed = True
    finally:
        if run_id is not None:
            try:
                db.update_audit_run_progress(
                    run_id,
                    completed_calls=len(results),
                    status="done" if completed else "cancelled",
                    error=None if completed else "aborted before all queries ran",
                )
            except StorageError as exc:
                # Best-effort, exactly like every other progress write here: a
                # storage failure must not mask the original exception.
                logger.warning("Could not write terminal status for run %s: %s", run_id, exc)

    if progress:
        print(f"Done. {len(results)} results collected" + (f" (run {run_id})." if run_id else "."))
    return AuditOutcome(
        run_id=run_id,
        client_name=query_set.client,
        client_domains=client_domains,
        competitors=query_set.competitors,
        query_set_version=query_set.version,
        runs_per_query=runs_per_query,
        results=results,
        engine_models=engine_models(engines),
    )


def run_teaser(
    query_set: QuerySet,
    engines: list[BaseEngine],
    client_domains: list[str] | None = None,
    max_queries: int = 5,
    business_kind: str = "product",
) -> AuditOutcome:
    """Fast meeting-booking demo: a few buying-moment queries, 1 run, no persist.

    The shallow Steps 1+5 path the method leans on to book the meeting — runs the
    same instrument, just trimmed and fast. ``business_kind`` selects which intents
    count as the buying moment; it defaults to ``"product"``, so every existing
    consumer caller is unchanged.

    Raises ``ValueError`` when no query matches the selected buckets. An empty teaser
    is never a valid outcome — it means the query set and the business kind disagree,
    and running it would report "you appear nowhere" from a zero-query measurement.
    """
    buckets = teaser_buckets(business_kind)
    teaser_queries: list[Query] = [q for q in query_set.queries if q.intent in buckets][
        :max_queries
    ]
    if not teaser_queries:
        present = sorted({q.intent.value for q in query_set.queries})
        raise ValueError(
            f"no queries match the {business_kind} teaser buckets "
            f"({', '.join(b.value for b in buckets)}); the set contains: "
            f"{', '.join(present) or 'nothing'}. A zero-query teaser would report "
            f"'you appear nowhere' from no measurement at all."
        )
    trimmed = dataclasses.replace(query_set, queries=teaser_queries)
    return run_audit(
        trimmed,
        engines,
        client_domains=client_domains,
        runs_per_query=1,
        persist=False,
        progress=True,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from pathlib import Path

    from src.prompts.query_set import load_query_set

    sample = Path(__file__).resolve().parents[2] / "data" / "sample_queries.json"
    qs = load_query_set(sample)

    class _EchoEngine(BaseEngine):
        ENGINE_NAME = "echo"

        def query(self, prompt: str) -> str | None:
            return f"The best option is YNAB. {qs.client} also exists."

    outcome = run_teaser(qs, [_EchoEngine()], client_domains=["acme.com"])
    print(f"teaser collected {len(outcome.results)} results (persist off)")
