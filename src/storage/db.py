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
    QueryResult,
    brand_from_dict,
    brand_to_dict,
    flag_from_dict,
    flag_to_dict,
)

__all__ = [
    "StorageError",
    "create_audit_run",
    "update_audit_run_progress",
    "save_query_results",
    "get_query_results",
    "list_audit_runs",
    "list_all_audit_runs",
    "list_resumable_runs",
    "delete_audit_runs",
    "delete_teasers",
    "delete_site_audit_html_for_runs",
    "get_audit_run",
    "save_judgments",
    "get_judgments",
    "upsert_site_audit_pages",
    "get_site_audit_pages",
    "upload_site_audit_html",
    "download_site_audit_html",
    "upsert_site_audit_checks",
    "get_site_audit_checks",
    "replace_site_audit_findings",
    "get_site_audit_findings",
    "save_teaser",
    "get_teaser",
    "list_teasers",
    "list_teasers_with_url",
    "update_teaser_status",
    "save_audit_deliverable",
    "get_audit_deliverable",
    "list_audit_deliverables",
    "update_audit_status",
]

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Query-level (intent-aware) audit tables.
TABLE_AUDIT_RUNS = "audit_runs"
TABLE_QUERY_RESULTS = "query_results"
TABLE_QUERY_CITATIONS = "query_citations"
TABLE_JUDGMENTS = "judgments"

# Content-addressed judge notebooks — shared so the subscription pre-judge and the
# UI/report step read the same verdicts. Query-answer verdicts and on-site content
# verdicts live in SEPARATE tables (different value shapes / keyspaces).
# See data/schema_judge_cache.sql and data/schema_content_judge_cache.sql.
TABLE_JUDGE_CACHE = "judge_cache"
TABLE_CONTENT_JUDGE_CACHE = "content_judge_cache"

# Site-audit pipeline tables (see data/schema_site_audit.sql).
TABLE_SITE_AUDIT_PHASE = "site_audit_phase"
TABLE_SITE_AUDIT_PAGE = "site_audit_page"
TABLE_SITE_AUDIT_CHECK = "site_audit_check"
TABLE_SITE_AUDIT_OFFSITE = "site_audit_offsite_finding"

# Private Storage bucket for gzipped raw/rendered HTML blobs (large, not row data).
BUCKET_SITE_AUDIT_HTML = "site-audit-html"

# Teaser one-pagers + their review lifecycle (see data/schema_teasers.sql).
TABLE_TEASERS = "teasers"

# Audit deliverables (the paid AI Visibility Audit) + review lifecycle
# (see data/schema_audits.sql).
TABLE_AUDIT_DELIVERABLES = "audit_deliverables"


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


def _select_rows(table: str, run_id: str, key: str = "run_id") -> list[dict[str, object]]:
    response = _execute(
        f"read from {table} ({key}={run_id})",
        lambda c: c.table(table).select("*").eq(key, run_id).execute(),
    )
    data = getattr(response, "data", None) or []
    return list(data)


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


# --- Judge cache (the shared "notebook") -------------------------------------
# Content-addressed key→verdict store. Reads/writes are chunked so a run with
# hundreds of answers is a handful of round-trips, not one per answer. Raises
# StorageError on failure like every other db op; SupabaseJudgeCache catches it
# and degrades to a miss/no-op so a Supabase blip never breaks a run.

_JUDGE_CACHE_CHUNK = 200


def _cache_read_chunk(table: str, keys: list[str]) -> list[dict[str, object]]:
    # keys is a parameter (not a loop var), so the lambda closes over it cleanly.
    response = _execute(
        f"{table} read ({len(keys)} keys)",
        lambda c: c.table(table).select("key,value").in_("key", keys).execute(),
    )
    return list(getattr(response, "data", None) or [])


def _cache_write_chunk(table: str, rows: list[dict[str, Any]]) -> None:
    _execute(
        f"{table} write ({len(rows)} rows)",
        lambda c: c.table(table).upsert(rows, on_conflict="key").execute(),
    )


def _cache_get_many(table: str, keys: list[str]) -> list[dict[str, object]]:
    """Rows ``{key, value}`` for the given content-address keys, fetched in chunked
    ``IN`` queries. Keys with no stored verdict are simply absent from the result."""
    out: list[dict[str, object]] = []
    for i in range(0, len(keys), _JUDGE_CACHE_CHUNK):
        out.extend(_cache_read_chunk(table, keys[i : i + _JUDGE_CACHE_CHUNK]))
    return out


def _cache_put_many(table: str, rows: list[dict[str, Any]]) -> None:
    """Upsert ``{key, value}`` rows, idempotent on ``key`` (a repeat write of the
    same content just overwrites), in chunks."""
    for i in range(0, len(rows), _JUDGE_CACHE_CHUNK):
        _cache_write_chunk(table, rows[i : i + _JUDGE_CACHE_CHUNK])


def judge_cache_get_many(keys: list[str]) -> list[dict[str, object]]:
    """Query-judge notebook rows for the given keys (chunked)."""
    return _cache_get_many(TABLE_JUDGE_CACHE, keys)


def judge_cache_put_many(rows: list[dict[str, Any]]) -> None:
    """Upsert query-judge verdict rows (chunked, idempotent on key)."""
    _cache_put_many(TABLE_JUDGE_CACHE, rows)


def content_judge_cache_get_many(keys: list[str]) -> list[dict[str, object]]:
    """Content-judge notebook rows for the given keys (chunked)."""
    return _cache_get_many(TABLE_CONTENT_JUDGE_CACHE, keys)


def content_judge_cache_put_many(rows: list[dict[str, Any]]) -> None:
    """Upsert content-judge verdict rows (chunked, idempotent on key)."""
    _cache_put_many(TABLE_CONTENT_JUDGE_CACHE, rows)


# --- Site-audit page cache ---------------------------------------------------


def upsert_site_audit_pages(run_id: str, rows: list[dict[str, Any]]) -> None:
    """Upsert crawled-page rows, idempotent on ``(run_id, normalized_url)``.

    A retried crawl overwrites the prior row for a URL rather than duplicating it
    (the table's unique constraint is the conflict target). Callers in the audit
    layer build the row dicts (the ``PageRecord``→row mapping is audit-domain
    knowledge); this function owns the Supabase write and its error wrapping so no
    audit code touches Supabase directly.
    """
    if not rows:
        return
    _execute(
        f"upsert_site_audit_pages for run {run_id}",
        lambda c: (
            c.table(TABLE_SITE_AUDIT_PAGE)
            .upsert(rows, on_conflict="run_id,normalized_url")
            .execute()
        ),
    )


def get_site_audit_pages(run_id: str) -> list[dict[str, object]]:
    """Return all cached page rows for a run (raw row dicts; caller rehydrates)."""
    return _select_rows(TABLE_SITE_AUDIT_PAGE, run_id)


def upload_site_audit_html(path: str, data: bytes) -> None:
    """Upload a gzipped HTML blob to the private site-audit bucket (upsert).

    Large HTML lives in object storage, not table rows (§1.6); the
    ``site_audit_page`` row keeps only the ``storage_path`` pointer. ``upsert`` is
    on so a re-crawl overwrites the same content-addressed object.
    """
    _execute(
        f"upload_site_audit_html {path}",
        lambda c: c.storage.from_(BUCKET_SITE_AUDIT_HTML).upload(
            path=path,
            file=data,
            file_options={"content-type": "application/gzip", "upsert": "true"},
        ),
    )


def download_site_audit_html(path: str) -> bytes:
    """Download a gzipped HTML blob from the private site-audit bucket."""
    return _execute(
        f"download_site_audit_html {path}",
        lambda c: c.storage.from_(BUCKET_SITE_AUDIT_HTML).download(path),
    )


def upsert_site_audit_checks(run_id: str, rows: list[dict[str, Any]]) -> None:
    """Upsert per-page check verdicts, idempotent on ``(run_id, check_key, page_url)``.

    A re-run overwrites a page's prior verdict for a given check rather than
    duplicating it. Callers in the audit layer build the rows; this owns the write.
    """
    if not rows:
        return
    _execute(
        f"upsert_site_audit_checks for run {run_id}",
        lambda c: (
            c.table(TABLE_SITE_AUDIT_CHECK)
            .upsert(rows, on_conflict="run_id,check_key,page_url")
            .execute()
        ),
    )


def get_site_audit_checks(run_id: str) -> list[dict[str, object]]:
    """Return all site-audit check verdict rows for a run (raw row dicts)."""
    return _select_rows(TABLE_SITE_AUDIT_CHECK, run_id)


def replace_site_audit_findings(run_id: str, rows: list[dict[str, Any]]) -> None:
    """Replace a run's offsite findings (delete-then-insert — findings aren't keyed).

    Mirrors ``save_judgments``: a re-run swaps the whole set rather than
    accumulating duplicates across runs.
    """
    _execute(
        f"clear site_audit findings for run {run_id}",
        lambda c: c.table(TABLE_SITE_AUDIT_OFFSITE).delete().eq("run_id", run_id).execute(),
    )
    if rows:
        _execute(
            f"insert site_audit findings for run {run_id}",
            lambda c: c.table(TABLE_SITE_AUDIT_OFFSITE).insert(rows).execute(),
        )


def get_site_audit_findings(run_id: str) -> list[dict[str, object]]:
    """Return all offsite finding rows for a run (raw row dicts)."""
    return _select_rows(TABLE_SITE_AUDIT_OFFSITE, run_id)


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


def _deleted_count(response: object) -> int:
    """Number of rows a Supabase delete actually removed (PostgREST returns the
    deleted rows in ``data``), so callers report what was removed, not requested."""
    data = getattr(response, "data", None) or []
    return len(data)


def delete_audit_runs(run_ids: list[str]) -> int:
    """Hard-delete audit-run rows by id, returning how many rows were removed.

    The ``query_results`` / ``query_citations`` / ``judgments`` / ``site_audit_*``
    children all reference ``audit_runs(id) ON DELETE CASCADE``, so this one
    delete also removes every child row. Gzipped HTML blobs in the
    ``site-audit-html`` Storage bucket are *not* cascaded — delete those first via
    ``delete_site_audit_html_for_runs`` (the cascade drops the rows that point to
    them, so they can't be found afterwards).
    """
    if not run_ids:
        return 0
    response = _execute(
        f"delete_audit_runs ({len(run_ids)} run(s))",
        lambda c: c.table(TABLE_AUDIT_RUNS).delete().in_("id", run_ids).execute(),
    )
    return _deleted_count(response)


def delete_teasers(teaser_ids: list[str]) -> int:
    """Hard-delete teaser rows by id, returning how many rows were removed."""
    if not teaser_ids:
        return 0
    response = _execute(
        f"delete_teasers ({len(teaser_ids)} teaser(s))",
        lambda c: c.table(TABLE_TEASERS).delete().in_("id", teaser_ids).execute(),
    )
    return _deleted_count(response)


def delete_site_audit_html_for_runs(run_ids: list[str]) -> int:
    """Remove the gzipped HTML blobs these runs left in the site-audit bucket.

    ``ON DELETE CASCADE`` removes the ``site_audit_page`` *rows* but not the
    Storage *objects* they point to, so collect ``storage_path``s first (while the
    rows still exist) and remove the objects. Fully best-effort: any failure (or a
    run with no crawled pages) returns 0 and never blocks the row deletes.
    """
    if not run_ids:
        return 0
    paths: list[str] = []
    for rid in run_ids:
        try:
            for row in get_site_audit_pages(rid):
                p = row.get("storage_path")
                if p:
                    paths.append(str(p))
        except StorageError:
            continue
    if not paths:
        return 0
    try:
        _execute(
            f"delete_site_audit_html ({len(paths)} blob(s))",
            lambda c: c.storage.from_(BUCKET_SITE_AUDIT_HTML).remove(paths),
        )
    except StorageError:
        return 0
    return len(paths)


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


# --- Teaser persistence + human review --------------------------------------


def save_teaser(draft: dict[str, Any], html: str | None, teaser_id: str | None = None) -> str:
    """Insert a teaser row from a freshly generated draft, returning its id.

    Stores the full ``TeaserDraft`` as jsonb plus a few denormalized columns the
    list/detail views read without unpacking ``draft``. The row starts in
    ``status='draft'``; the review endpoints move it to approved/rejected and/or
    save reviewer copy edits into ``edited_fields``.
    """
    teaser_id = teaser_id or str(uuid.uuid4())
    headline = draft.get("headlineNumber")
    lead = draft.get("lead")
    table = draft.get("table")
    row: dict[str, Any] = {
        "id": teaser_id,
        "prospect_url": draft.get("prospectUrl"),
        "company_name": draft.get("companyName"),
        "category": draft.get("category"),
        "run_date": draft.get("runDate"),
        "hero_engine": draft.get("heroEngine"),
        "headline_number": headline if isinstance(headline, dict) else {},
        "lead": lead if isinstance(lead, dict) else {},
        "table_findings": table if isinstance(table, list) else [],
        "draft": draft,
        "html": html,
        "status": "draft",
        "edited_fields": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    _execute(
        f"save_teaser for {draft.get('companyName') or teaser_id}",
        lambda c: c.table(TABLE_TEASERS).insert(row).execute(),
    )
    return teaser_id


def get_teaser(teaser_id: str) -> dict[str, object] | None:
    """Fetch a single teaser row by id, or None if absent."""
    rows = _select_rows(TABLE_TEASERS, teaser_id, key="id")
    return rows[0] if rows else None


def list_teasers(limit: int = 100) -> list[dict[str, object]]:
    """The most recent teasers — the basis for the "Saved teasers" panel.

    Projects only the columns the list view (TeaserSummary) needs — NOT the large
    ``draft`` jsonb or rendered ``html`` — so the panel stays light as teasers
    accumulate (the detail view fetches the full row via get_teaser).
    """
    response = _execute(
        "list_teasers",
        lambda c: (
            c.table(TABLE_TEASERS)
            .select("id, company_name, status, created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ),
    )
    data = getattr(response, "data", None) or []
    return list(data)


def list_teasers_with_url(limit: int = 200) -> list[dict[str, object]]:
    """Recent teasers including ``prospect_url`` — the basis for grouping teasers
    into projects by domain.

    Like ``list_teasers`` but adds the prospect URL (so a teaser can be bucketed
    under its domain) while still skipping the heavy ``draft``/``html`` blobs.
    """
    response = _execute(
        "list_teasers_with_url",
        lambda c: (
            c.table(TABLE_TEASERS)
            .select("id, company_name, status, created_at, prospect_url")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ),
    )
    data = getattr(response, "data", None) or []
    return list(data)


def update_teaser_status(
    teaser_id: str,
    status: str | None = None,
    edited_fields: dict[str, Any] | None = None,
    reject_reason: str | None = None,
    reviewed_by: str | None = None,
    html: str | None = None,
) -> dict[str, object] | None:
    """Advance a teaser's review state and/or save reviewer copy edits.

    Any argument left as ``None`` is untouched (a partial update). Returns the
    updated row so the API can echo the new state straight back to the UI.
    """
    row: dict[str, Any] = {"updated_at": _now()}
    if status is not None:
        row["status"] = status
    if edited_fields is not None:
        row["edited_fields"] = edited_fields
    if reject_reason is not None:
        row["reject_reason"] = reject_reason
    if reviewed_by is not None:
        row["reviewed_by"] = reviewed_by
    if html is not None:
        row["html"] = html
    _execute(
        f"update_teaser_status for teaser {teaser_id}",
        lambda c: c.table(TABLE_TEASERS).update(row).eq("id", teaser_id).execute(),
    )
    return get_teaser(teaser_id)


# --- Audit deliverable persistence + human review ---------------------------


def save_audit_deliverable(
    draft: dict[str, Any], html: str | None, deliverable_id: str | None = None
) -> str:
    """Insert an audit-deliverable row from a freshly generated draft, returning its id.

    Stores the full ``AuditDraft`` as jsonb plus a few denormalized columns the
    list/detail views read without unpacking ``draft``. The row starts in
    ``status='draft'``; the review endpoints move it to approved/rejected and/or
    save reviewer narrative edits into ``edited_fields``. Mirrors save_teaser.
    """
    deliverable_id = deliverable_id or str(uuid.uuid4())
    grade = draft.get("grade")
    grade_letter = grade.get("letter") if isinstance(grade, dict) else None
    grade_score = grade.get("score") if isinstance(grade, dict) else None
    report = draft.get("report")
    scorecard = report.get("scorecard") if isinstance(report, dict) else None
    domains = draft.get("clientDomains")
    row: dict[str, Any] = {
        "id": deliverable_id,
        "run_id": draft.get("runId"),
        "client_name": draft.get("clientName"),
        "client_domains": domains if isinstance(domains, list) else [],
        "category": draft.get("category"),
        "run_date": draft.get("runDate"),
        "grade_letter": grade_letter,
        "grade_score": grade_score,
        "headline": {"headline": draft.get("headline"), "verdict": draft.get("verdictSentence")},
        "scorecard": scorecard if isinstance(scorecard, dict) else {},
        "draft": draft,
        "html": html,
        "status": "draft",
        "edited_fields": {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    _execute(
        f"save_audit_deliverable for {draft.get('clientName') or deliverable_id}",
        lambda c: c.table(TABLE_AUDIT_DELIVERABLES).insert(row).execute(),
    )
    return deliverable_id


def get_audit_deliverable(deliverable_id: str) -> dict[str, object] | None:
    """Fetch a single audit-deliverable row by id, or None if absent."""
    rows = _select_rows(TABLE_AUDIT_DELIVERABLES, deliverable_id, key="id")
    return rows[0] if rows else None


def list_audit_deliverables(limit: int = 100) -> list[dict[str, object]]:
    """The most recent audit deliverables — the basis for the saved-audits list.

    Projects only the columns the list view needs — NOT the large ``draft`` jsonb
    or rendered ``html`` — so the panel stays light as deliverables accumulate
    (the detail view fetches the full row via get_audit_deliverable).
    """
    response = _execute(
        "list_audit_deliverables",
        lambda c: (
            c.table(TABLE_AUDIT_DELIVERABLES)
            .select("id, client_name, category, grade_letter, status, created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        ),
    )
    data = getattr(response, "data", None) or []
    return list(data)


def update_audit_status(
    deliverable_id: str,
    status: str | None = None,
    edited_fields: dict[str, Any] | None = None,
    reject_reason: str | None = None,
    reviewed_by: str | None = None,
    html: str | None = None,
) -> dict[str, object] | None:
    """Advance an audit deliverable's review state and/or save reviewer edits.

    Any argument left as ``None`` is untouched (a partial update). Returns the
    updated row so the API can echo the new state straight back to the UI.
    Mirrors update_teaser_status.
    """
    row: dict[str, Any] = {"updated_at": _now()}
    if status is not None:
        row["status"] = status
    if edited_fields is not None:
        row["edited_fields"] = edited_fields
    if reject_reason is not None:
        row["reject_reason"] = reject_reason
    if reviewed_by is not None:
        row["reviewed_by"] = reviewed_by
    if html is not None:
        row["html"] = html
    _execute(
        f"update_audit_status for deliverable {deliverable_id}",
        lambda c: c.table(TABLE_AUDIT_DELIVERABLES).update(row).eq("id", deliverable_id).execute(),
    )
    return get_audit_deliverable(deliverable_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        runs = list_all_audit_runs()
        print(f"Storage reachable: {len(runs)} audit run(s) visible.")
    except StorageError as exc:
        print(f"Cannot run storage test: {exc}")
        raise SystemExit(0) from None
