from __future__ import annotations

import dataclasses
import logging

from src.config import settings
from src.engines.base import BaseEngine
from src.pipeline.cost import CostBudgetExceeded, estimate_cost
from src.pipeline.prompt_runner import run_query_set
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet
from src.storage import db
from src.storage.db import StorageError
from src.storage.models import QueryResult

__all__ = ["AuditOutcome", "engine_models", "run_audit", "run_teaser"]

logger = logging.getLogger(__name__)


def engine_models(engines: list[BaseEngine]) -> dict[str, str]:
    """Exact model string per engine, recorded in run metadata (isolation L3).

    Engines with no model parameter (SERP capture) are omitted rather than
    recorded as empty strings.
    """
    return {e.ENGINE_NAME: e.MODEL_ID for e in engines if e.MODEL_ID}


# Buckets used for the fast teaser demo — the category/comparison answers are the
# visceral "here's what ChatGPT recommends instead of you" moment.
_TEASER_BUCKETS = (IntentBucket.CATEGORY, IntentBucket.COMPARISON)


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


def run_audit(
    query_set: QuerySet,
    engines: list[BaseEngine],
    client_domains: list[str] | None = None,
    runs_per_query: int = settings.DEFAULT_RUNS_PER_QUERY,
    persist: bool = True,
    progress: bool = True,
    max_cost: float | None = None,
    resume_run_id: str | None = None,
) -> AuditOutcome:
    """Run a full audit cycle: query set -> engines -> persisted results.

    Synchronous and order-stable. Persists incrementally (one query at a time)
    so a failure mid-run keeps prior progress. Pass ``resume_run_id`` to continue
    an interrupted run — queries already stored are skipped. ``max_cost`` aborts
    before any calls if the rough estimate exceeds the budget. If storage isn't
    configured, the run continues in-memory and ``run_id`` is None.
    """
    client_domains = client_domains or []
    queries = query_set.queries
    estimated, total_calls = estimate_cost(len(queries), engines, runs_per_query)
    if progress:
        engine_names = ", ".join(e.ENGINE_NAME for e in engines) or "none"
        print(
            f"Audit: {query_set.client} ({query_set.version}) — "
            f"{len(queries)} queries x {len(engines)} engines [{engine_names}] "
            f"x {runs_per_query} runs = {total_calls} calls (~${estimated:.2f} est.)"
        )
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
            )
        except StorageError as exc:
            logger.warning("Storage unavailable, continuing in-memory: %s", exc)
            run_id = None

    # The outcome carries prior + new results so a resumed run renders/judges the
    # whole run, not just the cells it happened to fill this pass.
    results: list[QueryResult] = list(prior_results)
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
            print(f"  [{index}/{len(queries)}] {query.query_id}: {answered}/{len(cell)} answered")

    # Mark the run terminal so a finished CLI run isn't later mistaken for an
    # interrupted one (the API resumes anything left in a non-terminal state).
    if run_id is not None:
        try:
            db.update_audit_run_progress(run_id, completed_calls=len(results), status="done")
        except StorageError as exc:
            logger.warning("Could not mark run %s done: %s", run_id, exc)

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
    )


def run_teaser(
    query_set: QuerySet,
    engines: list[BaseEngine],
    client_domains: list[str] | None = None,
    max_queries: int = 5,
) -> AuditOutcome:
    """Fast meeting-booking demo: a few category/comparison queries, 1 run, no persist.

    The shallow Steps 1+5 path the method leans on to book the meeting — runs the
    same instrument, just trimmed and fast.
    """
    teaser_queries: list[Query] = [q for q in query_set.queries if q.intent in _TEASER_BUCKETS][
        :max_queries
    ]
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
            return f"The best option is Salesforce. {qs.client} also exists."

    outcome = run_teaser(qs, [_EchoEngine()], client_domains=["acme.com"])
    print(f"teaser collected {len(outcome.results)} results (persist off)")
