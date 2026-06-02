from __future__ import annotations

import dataclasses
import logging

from src.engines.base import BaseEngine
from src.pipeline.prompt_runner import run_query_set
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet
from src.storage import db
from src.storage.db import StorageError
from src.storage.models import QueryResult

__all__ = ["AuditOutcome", "run_audit", "run_teaser"]

logger = logging.getLogger(__name__)

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
    runs_per_query: int = 3,
    persist: bool = True,
    progress: bool = True,
) -> AuditOutcome:
    """Run a full audit cycle: query set -> engines -> persisted results.

    Synchronous and order-stable. Persists incrementally (one query at a time)
    so a failure mid-run keeps prior progress and the run is resumable. If
    storage isn't configured, the run continues in-memory and ``run_id`` is None.
    """
    client_domains = client_domains or []
    queries = query_set.queries
    total_calls = len(queries) * len(engines) * runs_per_query
    if progress:
        engine_names = ", ".join(e.ENGINE_NAME for e in engines) or "none"
        print(
            f"Audit: {query_set.client} ({query_set.version}) — "
            f"{len(queries)} queries x {len(engines)} engines [{engine_names}] "
            f"x {runs_per_query} runs = {total_calls} calls"
        )

    run_id: str | None = None
    if persist:
        try:
            run_id = db.create_audit_run(
                client_name=query_set.client,
                client_domains=client_domains,
                competitors=query_set.competitors,
                category=query_set.category,
                query_set_version=query_set.version,
                query_set_locked_at=query_set.locked_at,
                runs_per_query=runs_per_query,
            )
        except StorageError as exc:
            logger.warning("Storage unavailable, continuing in-memory: %s", exc)
            run_id = None

    results: list[QueryResult] = []
    for index, query in enumerate(queries, start=1):
        cell = run_query_set([query], engines, runs_per_query)
        results.extend(cell)
        if run_id is not None:
            try:
                db.save_query_results(run_id, cell)
            except StorageError as exc:
                logger.warning("Failed to persist results for %s: %s", query.query_id, exc)
        if progress:
            answered = sum(1 for r in cell if r["response"] is not None)
            print(f"  [{index}/{len(queries)}] {query.query_id}: {answered}/{len(cell)} answered")

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
