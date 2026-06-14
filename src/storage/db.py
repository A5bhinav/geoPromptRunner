from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from supabase import Client, create_client

from src.config import settings
from src.pipeline.metrics import domain_of
from src.storage.models import (
    AnswerJudgment,
    BrandMention,
    Citation,
    PromptResult,
    QueryResult,
    RubricScore,
    brand_from_dict,
    brand_to_dict,
    flag_from_dict,
    flag_to_dict,
)

__all__ = [
    "StorageError",
    "create_run",
    "save_results",
    "save_mentions",
    "save_citations",
    "get_run",
    "get_results",
    "get_mentions",
    "get_citations",
    "create_audit_run",
    "update_audit_run_progress",
    "save_query_results",
    "get_query_results",
    "list_audit_runs",
    "list_all_audit_runs",
    "list_resumable_runs",
    "get_audit_run",
    "save_rubric_scores",
    "get_rubric_scores",
    "save_judgments",
    "get_judgments",
]

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

TABLE_RUNS = "prompt_runs"
TABLE_RESULTS = "prompt_results"
TABLE_MENTIONS = "brand_mentions"
TABLE_CITATIONS = "citations"

# Query-level (intent-aware) audit tables.
TABLE_AUDIT_RUNS = "audit_runs"
TABLE_QUERY_RESULTS = "query_results"
TABLE_QUERY_CITATIONS = "query_citations"
TABLE_RUBRIC_SCORES = "rubric_scores"
TABLE_JUDGMENTS = "judgments"


class StorageError(Exception):
    """Raised when a storage operation fails. Wraps the underlying error."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _as_str_list(value: object) -> list[str]:
    """Coerce a JSON value to list[str] (narrows mypy on dict[str, object] rows)."""
    return [str(v) for v in value] if isinstance(value, list) else []


_cached_client: Client | None = None


def _client() -> Client:
    """Return a cached Supabase client, or raise StorageError if not configured.

    The client (and its underlying HTTP session) is built once and reused for
    every read and write rather than reconstructed per call.
    """
    global _cached_client
    if _cached_client is not None:
        return _cached_client
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise StorageError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY (see .env.example)."
        )
    try:
        _cached_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    except Exception as exc:
        # Log the type only — the message can echo connection details.
        logger.warning("Failed to create Supabase client: %s", type(exc).__name__)
        raise StorageError("Failed to create Supabase client") from exc
    return _cached_client


def _execute(op_label: str, operation: Callable[[Client], _T]) -> _T:
    """Run a Supabase operation against the cached client, normalizing errors.

    Single owner of the storage try/except: on failure it logs only the
    exception **type** (a Supabase/Postgres message can echo back row values or
    connection detail) and raises ``StorageError``; the original exception still
    chains via ``from exc`` for callers that want full detail. ``op_label`` is a
    caller-controlled string (never the exception), safe to log.

    ``_client()`` is called outside the try so a "not configured" ``StorageError``
    propagates unchanged rather than being re-wrapped.
    """
    client = _client()
    try:
        return operation(client)
    except Exception as exc:
        logger.warning("%s failed: %s", op_label, type(exc).__name__)
        raise StorageError(f"{op_label} failed") from exc


def create_run(client_name: str, prompt_count: int) -> str:
    """Insert a new run row and return its generated ``run_id``."""
    run_id = str(uuid.uuid4())
    row: dict[str, Any] = {
        "id": run_id,
        "client_name": client_name,
        "prompt_count": prompt_count,
        "created_at": _now(),
        "archived_at": None,
    }
    _execute(
        f"create_run for client {client_name}", lambda c: c.table(TABLE_RUNS).insert(row).execute()
    )
    return run_id


def save_results(run_id: str, results: list[PromptResult]) -> None:
    """Persist prompt results for a run."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "prompt": r["prompt"],
            "engine_name": r["engine_name"],
            "response": r["response"],
            "timestamp": r["timestamp"],
        }
        for r in results
    ]
    if not rows:
        return
    _execute(
        f"save_results for run {run_id}", lambda c: c.table(TABLE_RESULTS).insert(rows).execute()
    )


def save_mentions(run_id: str, mentions: list[BrandMention]) -> None:
    """Persist brand/competitor mentions for a run."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "brand": m["brand"],
            "engine_name": m["engine_name"],
            "prompt": m["prompt"],
            "mention_type": m["mention_type"],
        }
        for m in mentions
    ]
    if not rows:
        return
    _execute(
        f"save_mentions for run {run_id}", lambda c: c.table(TABLE_MENTIONS).insert(rows).execute()
    )


def save_citations(run_id: str, citations: list[Citation]) -> None:
    """Persist citation URLs for a run."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "url": c["url"],
            "engine_name": c["engine_name"],
            "prompt": c["prompt"],
        }
        for c in citations
    ]
    if not rows:
        return
    _execute(
        f"save_citations for run {run_id}",
        lambda c: c.table(TABLE_CITATIONS).insert(rows).execute(),
    )


def _select_rows(table: str, run_id: str, key: str = "run_id") -> list[dict[str, object]]:
    response = _execute(
        f"read from {table} ({key}={run_id})",
        lambda c: c.table(table).select("*").eq(key, run_id).execute(),
    )
    data = getattr(response, "data", None) or []
    return list(data)


def get_run(run_id: str) -> dict[str, object] | None:
    """Fetch a single run row by id, or None if absent."""
    rows = _select_rows(TABLE_RUNS, run_id, key="id")
    return rows[0] if rows else None


def get_results(run_id: str) -> list[dict[str, object]]:
    """Fetch all stored results for a run."""
    return _select_rows(TABLE_RESULTS, run_id)


def get_mentions(run_id: str) -> list[dict[str, object]]:
    """Fetch all stored mentions for a run."""
    return _select_rows(TABLE_MENTIONS, run_id)


def get_citations(run_id: str) -> list[dict[str, object]]:
    """Fetch all stored citations for a run."""
    return _select_rows(TABLE_CITATIONS, run_id)


# --- Query-level (intent-aware) audit storage --------------------------------


def create_audit_run(
    client_name: str,
    client_domains: list[str],
    competitors: list[str],
    category: str,
    query_set_version: str,
    query_set_locked_at: str,
    runs_per_query: int,
    run_id: str | None = None,
    status: str = "running",
    total_calls: int = 0,
    engines: list[str] | None = None,
    n_queries: int = 0,
    fact_sheet_present: bool = False,
    queries: list[dict[str, Any]] | None = None,
    fact_sheet: str | None = None,
    judge: bool = False,
    engine_models: dict[str, str] | None = None,
) -> str:
    """Insert an audit-run row (client identity + locked query-set version).

    Accepts an explicit ``run_id`` so a caller (the API) can use one id for both
    its in-memory state and the stored row — that single id is what the UI polls,
    so a finished run can be read back from storage after a restart. The
    progress/state columns (``status``/``completed_calls``/``total_calls``/
    ``engines``) let the run survive a process restart as more than a bare row.

    ``engine_models`` records the exact model string each engine sent (e.g.
    ``{"openai": "gpt-4o-2024-08-06"}``) so two cycles are comparable — a
    provider's silent model update shows up as a metadata diff, not a mystery.
    """
    run_id = run_id or str(uuid.uuid4())
    row: dict[str, Any] = {
        "id": run_id,
        "client_name": client_name,
        "client_domains": client_domains,
        "competitors": competitors,
        "category": category,
        "query_set_version": query_set_version,
        "query_set_locked_at": query_set_locked_at,
        "runs_per_query": runs_per_query,
        "status": status,
        "completed_calls": 0,
        "total_calls": total_calls,
        "engines": engines or [],
        "n_queries": n_queries,
        "fact_sheet_present": fact_sheet_present,
        "queries": queries or [],
        "fact_sheet": fact_sheet,
        "judge": judge,
        "engine_models": engine_models or {},
        "created_at": _now(),
        "updated_at": _now(),
        "archived_at": None,
    }
    _execute(
        f"create_audit_run for client {client_name}",
        lambda c: c.table(TABLE_AUDIT_RUNS).insert(row).execute(),
    )
    return run_id


def update_audit_run_progress(
    run_id: str, completed_calls: int, status: str, error: str | None = None
) -> None:
    """Update a run's live progress/state so the UI can read it back from storage.

    Called best-effort as a run advances and on its terminal state; a storage
    failure here never aborts the run (the caller swallows ``StorageError``).
    """
    row: dict[str, Any] = {
        "completed_calls": completed_calls,
        "status": status,
        "updated_at": _now(),
    }
    if error is not None:
        row["error"] = error
    _execute(
        f"update_audit_run_progress for run {run_id}",
        lambda c: c.table(TABLE_AUDIT_RUNS).update(row).eq("id", run_id).execute(),
    )


def save_query_results(run_id: str, results: list[QueryResult]) -> None:
    """Persist a batch of QueryResults (and their citations) for an audit run.

    Safe to call incrementally (e.g. once per query) so a long run is resumable
    and partial progress survives a mid-run failure.
    """
    result_rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "query_id": r["query_id"],
            "intent": r["intent"],
            "prompt": r["prompt"],
            "engine_name": r["engine_name"],
            "run_index": r["run_index"],
            "response": r["response"],
            "timestamp": r["timestamp"],
        }
        for r in results
    ]
    citation_rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "query_id": r["query_id"],
            "engine_name": r["engine_name"],
            "url": url,
            "domain": domain_of(url),
        }
        for r in results
        for url in r["citations"]
    ]
    if result_rows:
        _execute(
            f"save_query_results for run {run_id}",
            lambda c: c.table(TABLE_QUERY_RESULTS).insert(result_rows).execute(),
        )
    if citation_rows:
        _execute(
            f"save_query_citations for run {run_id}",
            lambda c: c.table(TABLE_QUERY_CITATIONS).insert(citation_rows).execute(),
        )


def get_query_results(run_id: str) -> list[QueryResult]:
    """Reconstruct stored QueryResults for a run (citations re-attached per row).

    Archived rows (soft-deleted, e.g. cleaned-up duplicates) are excluded.
    """
    result_rows = [r for r in _select_rows(TABLE_QUERY_RESULTS, run_id) if not r.get("archived_at")]
    citation_rows = [
        c for c in _select_rows(TABLE_QUERY_CITATIONS, run_id) if not c.get("archived_at")
    ]

    cites_by_cell: dict[tuple[str, str], list[str]] = {}
    for c in citation_rows:
        key = (str(c.get("query_id", "")), str(c.get("engine_name", "")))
        cites_by_cell.setdefault(key, []).append(str(c.get("url", "")))

    results: list[QueryResult] = []
    for r in result_rows:
        query_id = str(r.get("query_id", ""))
        engine_name = str(r.get("engine_name", ""))
        run_index = int(str(r.get("run_index") or 0))
        # Citations are stored per (query, engine), not per run; attach to run 0
        # so they aren't duplicated across the run rows of one cell.
        citations = cites_by_cell.get((query_id, engine_name), []) if run_index == 0 else []
        results.append(
            QueryResult(
                query_id=query_id,
                intent=str(r.get("intent", "")),
                prompt=str(r.get("prompt", "")),
                engine_name=engine_name,
                run_index=run_index,
                response=None if r.get("response") is None else str(r.get("response")),
                citations=citations,
                timestamp=str(r.get("timestamp", "")),
            )
        )
    return results


def get_audit_run(run_id: str) -> dict[str, object] | None:
    """Fetch a single audit-run row by id, or None if absent."""
    rows = _select_rows(TABLE_AUDIT_RUNS, run_id, key="id")
    return rows[0] if rows else None


def list_audit_runs(client_name: str) -> list[dict[str, object]]:
    """All audit runs for a client, oldest first — the basis for trend/cadence."""
    rows = _select_rows(TABLE_AUDIT_RUNS, client_name, key="client_name")
    return sorted(rows, key=lambda r: str(r.get("created_at", "")))


def list_all_audit_runs(limit: int = 100) -> list[dict[str, object]]:
    """The most recent audit runs across all clients — the UI's recent list."""
    response = _execute(
        "list_all_audit_runs",
        lambda c: (
            c.table(TABLE_AUDIT_RUNS)
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ),
    )
    data = getattr(response, "data", None) or []
    return list(data)


def list_resumable_runs() -> list[dict[str, object]]:
    """Runs left in a non-terminal state — candidates to resume after a restart."""
    response = _execute(
        "list_resumable_runs",
        lambda c: (
            c.table(TABLE_AUDIT_RUNS).select("*").in_("status", ["running", "queued"]).execute()
        ),
    )
    data = getattr(response, "data", None) or []
    return list(data)


def save_rubric_scores(run_id: str | None, scores: list[RubricScore]) -> None:
    """Persist human rubric Pass/Partial/Fail judgments for a run."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "subject": s["subject"],
            "category": s["category"],
            "check_name": s["check_name"],
            "status": s["status"],
            "weight": s["weight"],
            "note": s["note"],
            "query_ids": s["query_ids"],
        }
        for s in scores
    ]
    if not rows:
        return
    _execute(
        f"save_rubric_scores for run {run_id}",
        lambda c: c.table(TABLE_RUBRIC_SCORES).insert(rows).execute(),
    )


def _judgment_to_row(run_id: str, j: AnswerJudgment) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "run_id": run_id,
        "query_id": j.query_id,
        "engine_name": j.engine_name,
        "intent": j.intent,
        "run_index": j.run_index,
        "assessed": j.assessed,
        "brands": [brand_to_dict(b) for b in j.brands],
        "accuracy_flags": [flag_to_dict(f) for f in j.accuracy_flags],
    }


def _row_to_judgment(row: dict[str, object]) -> AnswerJudgment:
    raw_brands = row.get("brands")
    brands = [
        brand_from_dict(b)
        for b in (raw_brands if isinstance(raw_brands, list) else [])
        if isinstance(b, dict)
    ]
    raw_flags = row.get("accuracy_flags")
    flags = [
        flag_from_dict(f)
        for f in (raw_flags if isinstance(raw_flags, list) else [])
        if isinstance(f, dict)
    ]
    return AnswerJudgment(
        query_id=str(row.get("query_id", "")),
        engine_name=str(row.get("engine_name", "")),
        intent=str(row.get("intent", "")),
        run_index=int(str(row.get("run_index") or 0)),
        assessed=bool(row.get("assessed", False)),
        brands=brands,
        accuracy_flags=flags,
    )


def save_judgments(run_id: str, judgments: list[AnswerJudgment]) -> None:
    """Persist LLM-judge output for a run (one row per judged answer).

    Replaces the run's existing judgments (delete-then-insert) so re-judging the
    same run is idempotent — the judge is explicitly meant to be re-run, and
    appending would accumulate duplicate rows. Expects the full judgment set for
    the run in one call (not incremental).
    """
    rows = [_judgment_to_row(run_id, j) for j in judgments]
    if not rows:
        return
    _execute(
        f"clear_judgments for run {run_id}",
        lambda c: c.table(TABLE_JUDGMENTS).delete().eq("run_id", run_id).execute(),
    )
    _execute(
        f"save_judgments for run {run_id}",
        lambda c: c.table(TABLE_JUDGMENTS).insert(rows).execute(),
    )


def get_judgments(run_id: str) -> list[AnswerJudgment]:
    """Reconstruct stored judge output for a run (no re-judging needed)."""
    return [_row_to_judgment(r) for r in _select_rows(TABLE_JUDGMENTS, run_id)]


def get_rubric_scores(run_id: str) -> list[RubricScore]:
    """Fetch stored rubric scores for a run."""
    rows = _select_rows(TABLE_RUBRIC_SCORES, run_id)
    return [
        RubricScore(
            subject=str(r.get("subject", "")),
            category=str(r.get("category", "")),
            check_name=str(r.get("check_name", "")),
            status=str(r.get("status", "")),
            weight=float(str(r.get("weight") or 1)),
            note=str(r.get("note") or ""),
            query_ids=_as_str_list(r.get("query_ids")),
        )
        for r in rows
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        run_id = create_run("Demo Client", prompt_count=1)
        save_results(
            run_id,
            [
                PromptResult(
                    prompt="What is the best CRM?",
                    engine_name="openai",
                    response="Acme is a strong choice.",
                    timestamp=_now(),
                )
            ],
        )
        save_mentions(
            run_id,
            [
                BrandMention(
                    brand="Acme",
                    engine_name="openai",
                    prompt="What is the best CRM?",
                    mention_type="recommended",
                )
            ],
        )
        save_citations(
            run_id,
            [
                Citation(
                    url="https://example.com/acme",
                    engine_name="perplexity",
                    prompt="What is the best CRM?",
                )
            ],
        )
        stored = get_results(run_id)
        print(f"Created run {run_id} and stored {len(stored)} result row(s) in Supabase.")
    except StorageError as exc:
        print(f"Cannot run storage test: {exc}")
        raise SystemExit(0) from None
