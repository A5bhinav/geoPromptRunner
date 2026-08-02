from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar

from supabase import Client, create_client

from src.audit.factsheet import (
    BusinessKind,
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SourceKind,
    Verification,
    assigned_claims,
    to_markdown,
)
from src.config import settings
from src.engines.local_pack import LocalPackCapture
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
    "supports_run_lineage",
    "superseded_run_ids",
    "update_audit_run_progress",
    "save_engine_probe",
    "save_local_pack_entities",
    "get_local_pack_entities",
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
    "FactSheetState",
    "FactSheetJobState",
    "factsheet_source_prefix",
    "save_fact_sheet",
    "load_fact_sheet",
    "get_fact_sheet",
    "activate_fact_sheet",
    "reject_fact_sheet",
    "next_fact_sheet_version",
    "list_fact_sheets",
    "delete_fact_sheets",
    "delete_factsheet_sources_for_sheets",
    "enqueue_factsheet_job",
    "claim_factsheet_job",
    "finish_factsheet_job",
    "factsheet_spend_today",
]

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# Query-level (intent-aware) audit tables.
TABLE_AUDIT_RUNS = "audit_runs"
TABLE_QUERY_RESULTS = "query_results"
TABLE_QUERY_CITATIONS = "query_citations"
TABLE_JUDGMENTS = "judgments"
TABLE_LOCAL_PACK = "local_pack_entities"

# Fixed namespaces for deriving deterministic (idempotent) row ids from a row's
# natural key, so a retried save upserts the same row rather than duplicating it.
_QUERY_RESULT_NS = uuid.uuid5(uuid.NAMESPACE_URL, "geo:query_result")
_QUERY_CITATION_NS = uuid.uuid5(uuid.NAMESPACE_URL, "geo:query_citation")

# Content-addressed judge notebooks — shared so the subscription pre-judge and the
# UI/report step read the same verdicts. Query-answer verdicts and on-site content
# verdicts live in SEPARATE tables (different value shapes / keyspaces).
# See data/schema_judge_cache.sql and data/schema_content_judge_cache.sql.
TABLE_JUDGE_CACHE = "judge_cache"
TABLE_CONTENT_JUDGE_CACHE = "content_judge_cache"

# Site-audit pipeline tables (see data/schema_site_audit.sql).
TABLE_SITE_AUDIT_PAGE = "site_audit_page"
TABLE_SITE_AUDIT_CHECK = "site_audit_check"
TABLE_SITE_AUDIT_OFFSITE = "site_audit_offsite_finding"

# Private Storage bucket for gzipped raw/rendered HTML blobs (large, not row data).
BUCKET_SITE_AUDIT_HTML = "site-audit-html"

# The page snapshots backing each fact claim's verbatim quote
# (data/schema_factsheets.sql §Sources). Deliberately the same object shape as the
# bucket above — gzipped HTML at a content-addressed path — which is why the two
# helpers below take a bucket instead of being duplicated per bucket.
BUCKET_FACTSHEET_SOURCES = "factsheet-sources"

# Teaser one-pagers + their review lifecycle (see data/schema_teasers.sql).
TABLE_TEASERS = "teasers"

# Audit deliverables (the paid AI Visibility Audit) + review lifecycle
# (see data/schema_audits.sql).
TABLE_AUDIT_DELIVERABLES = "audit_deliverables"

# Fact sheets, their claims, and the generation queue where the spend limiter
# lives (see data/schema_factsheets.sql).
TABLE_FACT_SHEETS = "fact_sheets"
TABLE_FACT_CLAIMS = "fact_claims"
TABLE_FACTSHEET_JOBS = "factsheet_jobs"
VIEW_FACTSHEET_SPEND_TODAY = "factsheet_spend_today"

# Postgres SQLSTATE for a unique violation. Named because two fact-sheet writes
# treat it as an ordinary outcome rather than an error (see _is_duplicate_key).
_UNIQUE_VIOLATION = "23505"


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
    location: str | None = None,
    engine_probe: dict[str, Any] | None = None,
    fact_sheet_id: str | None = None,
    fact_sheet_version: int | None = None,
    run_kind: str = "baseline",
    supersedes_run_id: str | None = None,
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

    ``fact_sheet`` stays the frozen snapshot of what this run was judged against.
    ``fact_sheet_id``/``fact_sheet_version`` are the pointer BACK to the living
    row in ``fact_sheets``, which the text alone cannot give you: without them
    nothing can answer "which version was this, and what changed since"
    (docs/factsheet-autogen-plan.md §6). They are written separately — see below.
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
        # Persisted so an interrupted LOCAL run resumes with the same market (W1.4);
        # None for nationally-marketed products, the pre-pivot default.
        "location": location,
        # What the liveness probe saw per engine, so a missing surface is explained
        # rather than silently absent (src/pipeline/preflight.py).
        "engine_probe": engine_probe or {},
        "engine_models": engine_models or {},
        "created_at": _now(),
        "updated_at": _now(),
        "archived_at": None,
    }
    _execute(
        f"create_audit_run for client {client_name}",
        lambda c: c.table(TABLE_AUDIT_RUNS).insert(row).execute(),
    )
    if run_kind != "baseline" or supersedes_run_id is not None:
        # Same follow-up-update pattern as the fact-sheet pointer below, and the
        # same reason: these columns arrive with data/schema_run_corrections.sql
        # and a database predating it would reject the whole INSERT.
        #
        # But it RAISES where the fact-sheet write only warns, and the asymmetry
        # is deliberate. Losing fact-sheet provenance loses a trace. Losing a
        # correction's lineage leaves an ordinary-looking extra run for the same
        # client and query set — a phantom second cycle, which the prior-run
        # resolver will happily compare against, reporting the repair of a broken
        # measurement as client progress. Better to fail loudly with a row nobody
        # trusts than to succeed into a false claim.
        #
        # Callers reach this only after `supports_run_lineage()`, so in practice
        # it fires on a race, not on a stale schema.
        _execute(
            f"record correction lineage for run {run_id}",
            lambda c: c.table(TABLE_AUDIT_RUNS)
            .update(
                {
                    "run_kind": run_kind,
                    "supersedes_run_id": supersedes_run_id,
                    "updated_at": _now(),
                }
            )
            .eq("id", run_id)
            .execute(),
        )
    if fact_sheet_id is not None:
        # Deliberately NOT part of the insert above. These two columns arrive with
        # data/schema_run_provenance.sql, and a database that predates it rejects the
        # whole INSERT — trading the run, which is unrecoverable, for its provenance,
        # which is not. Same degrade-don't-raise trade as judge_model in
        # save_judgments, and the same loud log. Skipped entirely when there is no
        # sheet, so an ordinary run still costs exactly one write.
        try:
            _execute(
                f"record fact-sheet provenance for run {run_id}",
                lambda c: c.table(TABLE_AUDIT_RUNS)
                .update(
                    {
                        "fact_sheet_id": fact_sheet_id,
                        "fact_sheet_version": fact_sheet_version,
                        "updated_at": _now(),
                    }
                )
                .eq("id", run_id)
                .execute(),
            )
        except StorageError:
            logger.warning(
                "Run %s was judged against fact sheet %s but the pointer was NOT "
                "recorded. If this database predates the fact_sheet_id / "
                "fact_sheet_version columns, apply data/schema_run_provenance.sql — "
                "until then no stored run can be traced to the sheet version it used.",
                run_id,
                fact_sheet_id,
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


def save_engine_probe(run_id: str, engine_probe: dict[str, Any]) -> None:
    """Record the liveness-probe result for a run.

    A separate update rather than a ``create_audit_run`` argument because the probe
    runs inside the background run thread, after the row already exists — the row is
    inserted first precisely so the UI has something to poll immediately. Best-effort
    like the progress updates: the caller swallows ``StorageError``, since losing the
    probe record must never sink a run that is otherwise fine.
    """
    _execute(
        f"save_engine_probe for run {run_id}",
        lambda c: c.table(TABLE_AUDIT_RUNS)
        .update({"engine_probe": engine_probe, "updated_at": _now()})
        .eq("id", run_id)
        .execute(),
    )


def save_local_pack_entities(run_id: str, captures: list[LocalPackCapture]) -> None:
    """Persist captured local-pack businesses for a run (create-only).

    One row per (query, business). Stored separately from ``query_results`` because a
    local pack is a ranked entity list, not an answer — see ``src/engines/local_pack.py``
    for why routing it through the answer path would be a category error.
    """
    rows: list[dict[str, Any]] = []
    for capture in captures:
        for entity in capture["entities"]:
            rows.append(
                {
                    "run_id": run_id,
                    "query_id": capture["query_id"],
                    "prompt": capture["prompt"],
                    "source": capture["source"],
                    "position": entity["position"],
                    "name": entity["name"],
                    "address": entity["address"] or None,
                    "category": entity["category"] or None,
                    "rating": entity["rating"],
                    "reviews": entity["reviews"],
                    "ludocid": entity["ludocid"],
                    "phone": entity["phone"],
                    "website": entity["website"],
                }
            )
    if not rows:
        return
    _execute(
        f"save_local_pack_entities for run {run_id} ({len(rows)} rows)",
        lambda c: c.table(TABLE_LOCAL_PACK).insert(rows).execute(),
    )


def get_local_pack_entities(run_id: str) -> list[dict[str, Any]]:
    """Stored local-pack rows for a run, in capture order (query, then rank)."""
    rows = _select_rows(TABLE_LOCAL_PACK, run_id)
    return sorted(
        (dict(r) for r in rows),
        key=lambda r: (str(r.get("query_id") or ""), int(r.get("position") or 0)),
    )


def _dedupe_by_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse rows that share a deterministic ``id`` (e.g. one citation url that
    recurs across a cell's runs) to a single row. A single upsert must never target
    the same conflict key twice — Postgres rejects that with "ON CONFLICT DO UPDATE
    command cannot affect row a second time". Last write wins (rows are identical)."""
    return list({row["id"]: row for row in rows}.values())


def _query_result_rows(run_id: str, results: list[QueryResult]) -> list[dict[str, Any]]:
    """Build query_results rows with deterministic ids (not random uuid4) keyed on
    (run, query, engine, run_index), so a retried flush upserts the SAME rows rather
    than inserting duplicates with fresh ids."""
    rows = [
        {
            "id": str(
                uuid.uuid5(
                    _QUERY_RESULT_NS,
                    f"{run_id}:{r['query_id']}:{r['engine_name']}:{r['run_index']}",
                )
            ),
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
    return _dedupe_by_id(rows)


def _query_citation_rows(run_id: str, results: list[QueryResult]) -> list[dict[str, Any]]:
    """Build query_citations rows with deterministic ids keyed on (run, query, engine,
    url). Citations are per-cell, so the SAME url across a cell's runs collapses to one
    row — both making a retry idempotent and keeping one upsert's conflict keys unique."""
    rows = [
        {
            "id": str(
                uuid.uuid5(_QUERY_CITATION_NS, f"{run_id}:{r['query_id']}:{r['engine_name']}:{url}")
            ),
            "run_id": run_id,
            "query_id": r["query_id"],
            "engine_name": r["engine_name"],
            "url": url,
            "domain": domain_of(url),
        }
        for r in results
        for url in r["citations"]
    ]
    return _dedupe_by_id(rows)


def save_query_results(run_id: str, results: list[QueryResult]) -> None:
    """Persist a batch of QueryResults (and their citations) for an audit run.

    Safe to call incrementally (e.g. once per query) so a long run is resumable
    and partial progress survives a mid-run failure. Result/citation rows carry
    deterministic ids and are upserted, so retrying a batch (the caller retries the
    whole pending set on a StorageError) can't create duplicate rows even though the
    two upserts below aren't one transaction.
    """
    result_rows = _query_result_rows(run_id, results)
    citation_rows = _query_citation_rows(run_id, results)
    if result_rows:
        _execute(
            f"save_query_results for run {run_id}",
            lambda c: c.table(TABLE_QUERY_RESULTS).upsert(result_rows, on_conflict="id").execute(),
        )
    if citation_rows:
        _execute(
            f"save_query_citations for run {run_id}",
            lambda c: (
                c.table(TABLE_QUERY_CITATIONS).upsert(citation_rows, on_conflict="id").execute()
            ),
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


def supports_run_lineage() -> bool:
    """Whether ``audit_runs`` carries ``run_kind``/``supersedes_run_id``.

    Checked BEFORE a correction run is created, not after: the lineage write
    happens after the row insert, so discovering the gap then would leave an
    untracked run behind that reads as an extra cycle. One cheap select on the
    correction path only.
    """
    try:
        _execute(
            "probe audit_runs.supersedes_run_id",
            lambda c: c.table(TABLE_AUDIT_RUNS).select("supersedes_run_id").limit(1).execute(),
        )
    except StorageError:
        return False
    return True


def superseded_run_ids(client_name: str) -> set[str]:
    """Runs for this client that a later correction replaces.

    A superseded run is not a cycle — it is the broken first attempt at one — so
    the prior-run resolver must skip it. Comparing against it would report the
    repair of a failed measurement as movement in the client's visibility.

    Degrades to an empty set on a database without the column: every run then
    looks like a cycle, which is exactly today's behaviour and no worse.
    """
    try:
        rows = _select_rows(TABLE_AUDIT_RUNS, client_name, key="client_name")
    except StorageError:
        return set()
    return {str(r["supersedes_run_id"]) for r in rows if r.get("supersedes_run_id")}


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


def upload_site_audit_html(
    path: str, data: bytes, *, bucket: str = BUCKET_SITE_AUDIT_HTML
) -> None:
    """Upload a gzipped HTML blob to a private bucket (upsert).

    Large HTML lives in object storage, not table rows (§1.6); the
    ``site_audit_page`` row keeps only the ``storage_path`` pointer. ``upsert`` is
    on so a re-crawl overwrites the same content-addressed object.

    ``bucket`` is keyword-only and defaults to the site-audit bucket, so every
    existing call site is unchanged. The fact-sheet source snapshots
    (``BUCKET_FACTSHEET_SOURCES``) are the same object — gzipped HTML, one
    content-addressed path — so they pass a bucket rather than getting a second
    near-identical pair of functions that would then have to be kept in step.
    """
    _execute(
        f"upload gzipped html to {bucket}/{path}",
        lambda c: c.storage.from_(bucket).upload(
            path=path,
            file=data,
            file_options={"content-type": "application/gzip", "upsert": "true"},
        ),
    )


def download_site_audit_html(path: str, *, bucket: str = BUCKET_SITE_AUDIT_HTML) -> bytes:
    """Download a gzipped HTML blob from a private bucket (site-audit by default)."""
    return _execute(
        f"download gzipped html from {bucket}/{path}",
        lambda c: c.storage.from_(bucket).download(path),
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
    """Rebuild one judged answer, RE-STAMPING each flag with the row's own cell.

    ``flag_to_dict`` stores four keys deliberately (it is shared with the judge
    cache, which is keyed per answer and must stay byte-identical), so the stored
    flag dicts carry no provenance. The row does — ``query_id``/``engine_name``/
    ``intent``/``run_index`` are columns right here.

    Stamping them back on is not optional. Without it every run READ FROM STORAGE
    has anonymous flags forever, whatever it looked like live: no verbatim prompt,
    no named model, no date, so `findings.build_finding_groups` correctly refuses
    to build an evidence bundle and every card loses its evidence trail. That is
    the whole deliverable, and it looked like a "legacy run" problem until a
    freshly-judged run was read back and had the same gap.

    ``observed_at`` is NOT set here — this table has no per-cell timestamp. It is
    stamped in ``src/api/reports.build_report``, which has the ``query_results``
    rows the timestamps actually live on.
    """
    raw_brands = row.get("brands")
    brands = [
        brand_from_dict(b)
        for b in (raw_brands if isinstance(raw_brands, list) else [])
        if isinstance(b, dict)
    ]
    query_id = str(row.get("query_id", ""))
    engine_name = str(row.get("engine_name", ""))
    intent = str(row.get("intent", ""))
    run_index = int(str(row.get("run_index") or 0))
    raw_flags = row.get("accuracy_flags")
    flags = [
        replace(
            flag_from_dict(f),
            query_id=query_id,
            engine_name=engine_name,
            intent=intent,
            run_index=run_index,
        )
        for f in (raw_flags if isinstance(raw_flags, list) else [])
        if isinstance(f, dict)
    ]
    return AnswerJudgment(
        query_id=query_id,
        engine_name=engine_name,
        intent=intent,
        run_index=run_index,
        assessed=bool(row.get("assessed", False)),
        brands=brands,
        accuracy_flags=flags,
    )


def save_judgments(
    run_id: str, judgments: list[AnswerJudgment], judge_model: str | None = None
) -> None:
    """Persist LLM-judge output for a run (one row per judged answer).

    Replaces the run's existing judgments (delete-then-insert) so re-judging the
    same run is idempotent — the judge is explicitly meant to be re-run, and
    appending would accumulate duplicate rows. Expects the full judgment set for
    the run in one call (not incremental).

    An empty ``judgments`` list is a deliberate no-op (returns without clearing):
    a re-judge that yields nothing is almost always a failed/empty pass, and
    wiping the prior verdicts in that case would lose good data. To truly clear a
    run's judgments, delete the run.

    ``judge_model`` is the identity of the judge that produced these verdicts
    (``Judge.identity`` — model plus any cascade/verifier configuration). Recorded on
    the run because JUDGE_MODEL is a *choice* that has changed and will change again,
    and without it a stored run's verdicts have no provenance: a report rendering that
    run can only guess, and guessing is how docs/report.md came to name a judge model
    that had not been in use for months. Written here rather than at run creation
    because a run is routinely judged later, by a different model than was configured
    when it was created. ``None`` leaves any existing value alone — an unknown judge
    must not erase a known one.
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
    if judge_model:
        # Deliberately non-fatal, and the only place in this module that degrades rather
        # than raising: the verdicts are already committed above, so failing here would
        # report "could not persist judgments" about a save that succeeded. It also
        # fails cleanly on a database that predates the `judge_model` column
        # (data/schema_ui.sql) — losing the provenance of a saved run, which is
        # recoverable, instead of the run itself, which is not. Logged loudly because a
        # silent loss of provenance is exactly the failure this column exists to end.
        try:
            _execute(
                f"record judge_model for run {run_id}",
                lambda c: c.table(TABLE_AUDIT_RUNS)
                .update({"judge_model": judge_model, "updated_at": _now()})
                .eq("id", run_id)
                .execute(),
            )
        except StorageError:
            logger.warning(
                "Judgments saved for run %s but the judge model was NOT recorded. If this "
                "database predates the judge_model column, apply the `alter table "
                "public.audit_runs add column if not exists judge_model text` in "
                "data/schema_ui.sql — until then every report will read 'judge model not "
                "recorded' for new runs.",
                run_id,
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


# --- Fact sheets: the living record behind the judge's reference -------------
#
# data/schema_factsheets.sql. Two closed sets below live in the DATABASE and not
# in src/audit/factsheet/models.py, because they describe a ROW's place in the
# store rather than the document's own lifecycle: which of a domain's versions a
# run may use, and how far a generation job got. ``FactSheet.sheet_status``
# (draft/client_reviewed/signed) is the orthogonal per-document axis and has no
# column here yet — see the note on _fact_sheet_to_row.


class FactSheetState(StrEnum):
    """Which row of a domain's version history a run is allowed to read.

    Only one ``ACTIVE`` row per domain may exist: ``uq_fact_sheets_active_domain``
    is a partial unique index, so promoting a sheet REQUIRES demoting the
    incumbent in the same operation (:func:`activate_fact_sheet`). Older versions
    are kept as ``SUPERSEDED`` on purpose — a sheet is a measurement reference,
    and plan §6 needs two versions present to diff what a regeneration changed.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    # A reviewer looked and said no. A REVIEWED state, not a deleted one: it
    # records that the extractor produced something plausible-but-false on this
    # domain, which is the signal that tunes L1 (F4).
    REJECTED = "rejected"


class FactSheetJobState(StrEnum):
    """How far a generation job got, including the ways it deliberately did not run.

    The three ``SKIPPED_*`` members are most of the reason the table exists: a job
    that is not run is RECORDED, never dropped. The lead-alert work established
    that a silent failure is worse than no channel, because you stop checking.
    """

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_CAP = "skipped_cap"
    SKIPPED_UNUSABLE = "skipped_unusable"


# Deterministic claim-row ids from (sheet, claim_id), so a caller retrying a
# half-written save upserts the same claims instead of duplicating them.
_FACT_CLAIM_NS = uuid.uuid5(uuid.NAMESPACE_URL, "geo:fact_claim")

# The queue screen lists sheets; it must not drag every sheet's full markdown
# across the wire to do it. ``questions`` stays in — it is the column the queue
# exists to surface (schema_factsheets.sql calls it the most valuable one here).
_FACT_SHEET_LIST_COLUMNS = (
    "id, domain, business_name, business_kind, version, state, verification_tier, "
    "lead_ref, questions, reject_reason, source_snapshot_prefix, generated_at, "
    "created_at, updated_at"
)

# How many queued jobs one claim attempt will fight over before giving up. Each
# lost race costs one round trip, and losing twenty in a row means the queue is
# hot enough that returning empty and letting the worker loop is the cheaper move.
_JOB_CLAIM_SCAN = 20


def _is_duplicate_key(exc: StorageError) -> bool:
    """True when a wrapped storage failure was a unique-constraint violation.

    ``_execute`` throws the driver's error away on purpose — a Postgres message
    echoes row values — so the SQLSTATE has to be read back off the chained
    cause. Callers that treat a duplicate as an ordinary outcome (a second lead
    for a domain already in flight) need to tell it apart from a real failure,
    and the alternative — checking before writing — is exactly the race the
    constraint exists to win. Older clients surface the code only in the message,
    so both are checked.
    """
    cause = exc.__cause__
    if getattr(cause, "code", None) == _UNIQUE_VIOLATION:
        return True
    return _UNIQUE_VIOLATION in str(cause)


def factsheet_source_prefix(domain: str, version: int) -> str:
    """Storage prefix for one sheet version's page snapshots: ``<domain>/v<version>``.

    Defined once because two copies drift: the snapshot writer builds object paths
    under it, :func:`save_fact_sheet` records it on the row, and
    :func:`delete_factsheet_sources_for_sheets` lists it to clean up. The shape is
    fixed by data/schema_factsheets.sql §Sources.
    """
    return f"{domain}/v{version}"


def _fact_sheet_to_row(
    sheet: FactSheet,
    sheet_id: str,
    *,
    state: FactSheetState,
    source_snapshot_prefix: str,
) -> dict[str, Any]:
    """Build the ``fact_sheets`` row for a sheet.

    ``rendered_md`` stores renderer 2's output. Renderer 1 (the CSV fact rows) is
    deliberately NOT stored and is derived from ``fact_claims`` at build time —
    two stored representations of the same facts is how they drift.

    ``verification_tier`` is denormalized from the claims so the column can be
    queried ("which sheets are still public_source_only"); it is recomputed, not
    read back, on load. ``FactSheet.sheet_status`` has nowhere to go: the table
    has ``state`` (this row's place in the version history) and nothing for the
    document's draft/client_reviewed/signed axis, which plan §11.5 still owes a
    reconciliation.
    """
    return {
        "id": sheet_id,
        # Already the registrable domain, normalized by the caller. The column's
        # CHECK only catches a careless writer (lowercase, no scheme, no path) —
        # proper PSL normalization needs Python and does not live here.
        "domain": sheet.domain,
        "business_name": sheet.business_name,
        "business_kind": sheet.business_kind.value,
        "lead_ref": sheet.lead_ref,
        "version": sheet.version,
        "rendered_md": to_markdown(sheet),
        "verification_tier": sheet.verification_tier.value,
        "state": state.value,
        "questions": list(sheet.questions),
        "source_snapshot_prefix": source_snapshot_prefix,
        "generated_at": sheet.generated_at,
        "created_at": _now(),
        "updated_at": _now(),
    }


def _fact_claim_to_row(sheet_id: str, claim: FactClaim) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(_FACT_CLAIM_NS, f"{sheet_id}:{claim.claim_id}")),
        "fact_sheet_id": sheet_id,
        "claim_id": claim.claim_id,
        "section": claim.section.value,
        "key": claim.key,
        "value": claim.value,
        "polarity": claim.polarity.value,
        "verbatim_quote": claim.verbatim_quote,
        "source_url": claim.source_url,
        "source_kind": claim.source_kind.value,
        "as_of": claim.as_of,
        "verification": claim.verification.value,
        "confidence": claim.confidence.value,
    }


def _row_to_fact_claim(row: dict[str, object]) -> FactClaim:
    """Rehydrate one claim.

    The enum constructors are strict rather than tolerant, unlike
    ``_row_to_judgment``: every one of these columns is CHECK-constrained to
    exactly its enum's values, so an unrecognized one means the database moved
    ahead of the code. A claim silently coerced to a wrong section or a wrong
    verification tier is the false-accusation failure the whole sheet exists to
    avoid, and refusing to load it is the conservative answer.
    """
    return FactClaim(
        claim_id=str(row.get("claim_id", "")),
        section=SheetSection(str(row.get("section", ""))),
        key=str(row.get("key", "")),
        value=str(row.get("value", "")),
        polarity=Polarity(str(row.get("polarity", ""))),
        verbatim_quote=str(row.get("verbatim_quote", "")),
        source_url=str(row.get("source_url", "")),
        source_kind=SourceKind(str(row.get("source_kind", ""))),
        as_of=str(row.get("as_of", "")),
        verification=Verification(str(row.get("verification", ""))),
        confidence=Confidence(str(row.get("confidence", ""))),
    )


def _row_to_fact_sheet(row: dict[str, object], claim_rows: list[dict[str, object]]) -> FactSheet:
    """Rehydrate a sheet from its row plus its claim rows.

    ``sheet_status`` is not restored — there is no column for it — so a loaded
    sheet reports ``DRAFT``. Anything gating on a signature must read the store's
    own ``state``, not the rehydrated document.
    """
    return FactSheet(
        domain=str(row.get("domain", "")),
        business_name=str(row.get("business_name") or ""),
        business_kind=BusinessKind(str(row.get("business_kind") or BusinessKind.LOCAL_SERVICE)),
        claims=[_row_to_fact_claim(c) for c in claim_rows],
        questions=_as_str_list(row.get("questions")),
        version=int(str(row.get("version") or 1)),
        generated_at=str(row.get("generated_at") or ""),
        lead_ref=None if row.get("lead_ref") is None else str(row.get("lead_ref")),
    )


def _fact_sheet_row(sheet_id: str) -> dict[str, object] | None:
    rows = _select_rows(TABLE_FACT_SHEETS, sheet_id, key="id")
    return rows[0] if rows else None


def _fact_claim_rows(sheet_id: str) -> list[dict[str, object]]:
    """A sheet's claim rows in claim-ID order, so a round trip is order-stable."""
    rows = _select_rows(TABLE_FACT_CLAIMS, sheet_id, key="fact_sheet_id")
    return sorted(rows, key=lambda r: str(r.get("claim_id", "")))


def save_fact_sheet(
    sheet: FactSheet,
    *,
    sheet_id: str | None = None,
    source_snapshot_prefix: str | None = None,
) -> str:
    """Write a fact sheet and its claims, returning the sheet id.

    The sheet lands in ``FactSheetState.DRAFT``. **Writing is not activating**, and
    that is the point: generation is cheap and unreviewed, while
    ``uq_fact_sheets_active_domain`` allows exactly one active row per domain — so
    a generator that wrote ``active`` would either clobber a reviewed incumbent or
    fail outright. The promotion is the human gate (plan F4) and goes through
    :func:`activate_fact_sheet`.

    ``unique (domain, version)`` is what stops one business being stored twice: a
    regeneration must bump ``sheet.version``, and a second save at the same version
    raises rather than silently forking the history.

    Claim ids are stamped here via ``assigned_claims`` (pure — the caller's sheet is
    not mutated), and claim rows carry deterministic ids keyed on
    ``(sheet_id, claim_id)``, so a caller retrying a half-written save with the same
    ``sheet_id`` upserts the same claims. The sheet row itself is a plain insert:
    upserting it on ``id`` would quietly reset an already-activated sheet to draft.
    """
    sheet_id = sheet_id or str(uuid.uuid4())
    claims = assigned_claims(sheet.claims)
    prefix = source_snapshot_prefix or factsheet_source_prefix(sheet.domain, sheet.version)
    row = _fact_sheet_to_row(
        sheet, sheet_id, state=FactSheetState.DRAFT, source_snapshot_prefix=prefix
    )
    _execute(
        f"save_fact_sheet for {sheet.domain} v{sheet.version}",
        lambda c: c.table(TABLE_FACT_SHEETS).insert(row).execute(),
    )
    claim_rows = [_fact_claim_to_row(sheet_id, claim) for claim in claims]
    if claim_rows:
        _execute(
            f"save_fact_claims for {sheet.domain} v{sheet.version} ({len(claim_rows)} rows)",
            lambda c: (
                c.table(TABLE_FACT_CLAIMS)
                .upsert(claim_rows, on_conflict="fact_sheet_id,claim_id")
                .execute()
            ),
        )
    return sheet_id


def get_fact_sheet(sheet_id: str) -> FactSheet | None:
    """Fetch one sheet by row id, claims attached, or None if absent."""
    row = _fact_sheet_row(sheet_id)
    return None if row is None else _row_to_fact_sheet(row, _fact_claim_rows(sheet_id))


def load_fact_sheet(
    domain: str, *, state: FactSheetState = FactSheetState.ACTIVE
) -> FactSheet | None:
    """The highest-version sheet for ``domain`` in ``state``, claims attached.

    ``domain`` is the registrable domain, already normalized — see the note in
    :func:`_fact_sheet_to_row` about why the column's CHECK is not the normalizer.

    Ordering by version is what makes the non-default states usable: ``ACTIVE`` is
    unique per domain by index, but a domain accumulates drafts and superseded
    versions, and the one a caller means is the newest.
    """
    response = _execute(
        f"load_fact_sheet for {domain} ({state.value})",
        lambda c: (
            c.table(TABLE_FACT_SHEETS)
            .select("*")
            .eq("domain", domain)
            .eq("state", state.value)
            .order("version", desc=True)
            .limit(1)
            .execute()
        ),
    )
    rows = list(getattr(response, "data", None) or [])
    if not rows:
        return None
    return _row_to_fact_sheet(rows[0], _fact_claim_rows(str(rows[0].get("id", ""))))


def activate_fact_sheet(sheet_id: str) -> None:
    """Promote one sheet to ``ACTIVE``, demoting the domain's incumbent first.

    Not two independent updates that happen to be adjacent.
    ``uq_fact_sheets_active_domain`` is a partial unique index, so promoting before
    demoting is rejected by Postgres, and PostgREST offers no transaction to do
    both at once. Demote-then-promote leaves a window in which the domain has NO
    active sheet, and that is the safe way to fail: a run that finds nothing uses
    no fact sheet and makes no accuracy claim, whereas a run that finds two has no
    defined reference at all.

    Re-activating the current active sheet is a no-op rather than a self-demotion —
    hence the ``neq`` on the demote.
    """
    row = _fact_sheet_row(sheet_id)
    if row is None:
        raise StorageError(f"activate_fact_sheet: no fact sheet {sheet_id}")
    state = str(row.get("state") or "")
    if state == FactSheetState.REJECTED.value:
        # A reviewer already read this and said no. Promoting it would let one
        # mis-click undo the only human judgment in the pipeline, and the queue UI
        # renders an Approve button on the rejected tab — so the guard belongs
        # here, next to the write, not only in the screen.
        raise StorageError(
            f"activate_fact_sheet: {sheet_id} was REJECTED — regenerate the sheet "
            "rather than promoting one a reviewer already turned down"
        )
    domain = str(row.get("domain", ""))
    _execute(
        f"demote active fact sheet for {domain}",
        lambda c: (
            c.table(TABLE_FACT_SHEETS)
            .update({"state": FactSheetState.SUPERSEDED.value, "updated_at": _now()})
            .eq("domain", domain)
            .eq("state", FactSheetState.ACTIVE.value)
            .neq("id", sheet_id)
            .execute()
        ),
    )
    _execute(
        f"activate_fact_sheet {sheet_id} for {domain}",
        lambda c: (
            c.table(TABLE_FACT_SHEETS)
            .update({"state": FactSheetState.ACTIVE.value, "updated_at": _now()})
            .eq("id", sheet_id)
            .execute()
        ),
    )


def next_fact_sheet_version(domain: str) -> int:
    """The next free version for ``domain`` — 1 when it has no sheets yet.

    ``fact_sheets`` carries ``unique (domain, version)`` and ``FactSheet.version``
    defaults to 1, so without this every regeneration of a known domain collided
    on the second save. The generator had no version allocator at all, which meant
    the failure surfaced as ``FactSheetJobState.FAILED`` with error
    ``"StorageError"`` — a duplicate key reported as a crawler fault, on the exact
    path that runs unattended against real prospects.

    Read-then-write, so two workers racing the same domain can still collide. That
    is acceptable and deliberate: the in-flight unique index
    (``uq_factsheet_jobs_inflight``) already permits only one job per domain, so
    the race needs two workers defeating that first, and losing it is a retryable
    insert rather than a wrong sheet.
    """

    def _query(client: Client) -> Any:
        return (
            client.table(TABLE_FACT_SHEETS)
            .select("version")
            .eq("domain", domain)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )

    response = _execute(f"next_fact_sheet_version for {domain}", _query)
    rows = list(getattr(response, "data", None) or [])
    if not rows:
        return 1
    return int(str(rows[0].get("version") or 0)) + 1


def reject_fact_sheet(sheet_id: str, reason: str | None = None) -> None:
    """Mark a reviewed sheet ``REJECTED``. The row stays; the verdict is recorded.

    Deliberately not a delete. A reviewer saying "these claims are wrong" is the
    most valuable signal the extractor gets — it means L1 produced something
    plausible-but-false on this domain — and a deleted row teaches nothing and
    lets the next regeneration repeat the mistake unobserved.

    Only a sheet nobody is relying on may be rejected: an ``ACTIVE`` sheet is the
    reference live runs judge against, and silently pulling it would leave those
    runs making accuracy claims against a document that no longer exists. Demote
    it by activating its replacement instead.
    """
    row = _fact_sheet_row(sheet_id)
    if row is None:
        raise StorageError(f"reject_fact_sheet: no fact sheet {sheet_id}")
    if str(row.get("state")) == FactSheetState.ACTIVE.value:
        raise StorageError(
            f"reject_fact_sheet: {sheet_id} is ACTIVE — activate a replacement instead "
            "of rejecting the sheet live runs are judged against"
        )
    # NULL, not "", for a rejection with no note: "rejected without a reason" must
    # stay distinguishable from "the reason failed to persist" (/teasers convention).
    update: dict[str, Any] = {
        "state": FactSheetState.REJECTED.value,
        "reject_reason": (reason or "").strip() or None,
        "updated_at": _now(),
    }
    _execute(
        f"reject_fact_sheet {sheet_id}",
        lambda c: c.table(TABLE_FACT_SHEETS).update(update).eq("id", sheet_id).execute(),
    )


def list_fact_sheets(
    state: FactSheetState | None = None,
    domain: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Fact-sheet rows, newest first — the basis for the F4 review queue.

    Raw rows rather than :class:`FactSheet`s, like ``list_teasers``: the list view
    needs a projection (no ``rendered_md``) and a claim count it does not have to
    join for, and rehydrating a document per row to show a domain and a state
    would fetch every claim of every sheet. The detail view loads one sheet via
    :func:`load_fact_sheet`.
    """

    def _query(client: Client) -> Any:
        q = client.table(TABLE_FACT_SHEETS).select(_FACT_SHEET_LIST_COLUMNS)
        if state is not None:
            q = q.eq("state", state.value)
        if domain is not None:
            q = q.eq("domain", domain)
        return q.order("created_at", desc=True).limit(limit).execute()

    response = _execute("list_fact_sheets", _query)
    data = getattr(response, "data", None) or []
    return list(data)


def _snapshot_paths(prefix: str) -> list[str]:
    """Object paths under one sheet's snapshot prefix.

    ``prefix`` is a parameter (not a loop var), so the lambda closes over it
    cleanly. Storage ``list`` returns names relative to the prefix.
    """
    entries = _execute(
        f"list factsheet sources under {prefix}",
        lambda c: c.storage.from_(BUCKET_FACTSHEET_SOURCES).list(prefix),
    )
    return [f"{prefix}/{e['name']}" for e in entries or [] if isinstance(e, dict) and e.get("name")]


def delete_factsheet_sources_for_sheets(sheet_ids: list[str]) -> int:
    """Remove the gzipped page snapshots these sheets left in the sources bucket.

    The second orphan surface the plan warned about (§12.2). Deleting a
    ``fact_sheets`` row cascades to ``fact_claims`` but never to Storage, and the
    row is the only thing that knows the prefix — so collect the prefixes and
    remove the objects FIRST, exactly as ``delete_site_audit_html_for_runs`` does
    for ``site-audit-html``, then delete the rows.

    Best-effort throughout: any failure returns what it managed and never blocks
    the row deletes, because an orphaned blob is recoverable by listing the bucket
    and a half-deleted project is not.
    """
    if not sheet_ids:
        return 0
    paths: list[str] = []
    for sid in sheet_ids:
        try:
            row = _fact_sheet_row(sid)
            if row is None:
                continue
            prefix = row.get("source_snapshot_prefix")
            # A sheet written before the column was populated still has its blobs
            # at the conventional prefix, so rebuild it rather than leak them.
            if not prefix:
                prefix = factsheet_source_prefix(
                    str(row.get("domain", "")), int(str(row.get("version") or 1))
                )
            paths.extend(_snapshot_paths(str(prefix)))
        except StorageError:
            continue
    if not paths:
        return 0
    try:
        _execute(
            f"delete factsheet sources ({len(paths)} blob(s))",
            lambda c: c.storage.from_(BUCKET_FACTSHEET_SOURCES).remove(paths),
        )
    except StorageError:
        return 0
    return len(paths)


def delete_fact_sheets(sheet_ids: list[str]) -> int:
    """Hard-delete fact-sheet rows by id, returning how many rows were removed.

    ``fact_claims`` references ``fact_sheets(id) ON DELETE CASCADE``, so the claims
    go with the sheet; ``factsheet_jobs.fact_sheet_id`` is ``ON DELETE SET NULL``,
    so the record of what was spent producing it survives on purpose. Snapshots in
    the ``factsheet-sources`` bucket are *not* cascaded — delete those first via
    :func:`delete_factsheet_sources_for_sheets`, while the rows that point at them
    still exist.
    """
    if not sheet_ids:
        return 0
    response = _execute(
        f"delete_fact_sheets ({len(sheet_ids)} sheet(s))",
        lambda c: c.table(TABLE_FACT_SHEETS).delete().in_("id", sheet_ids).execute(),
    )
    return _deleted_count(response)


# --- The generation queue, and where the spend limiter sits ------------------


def enqueue_factsheet_job(domain: str, lead_ref: str | None = None, tier: int = 1) -> str | None:
    """Queue a generation job for ``domain``; ``None`` if one is already in flight.

    ``uq_factsheet_jobs_inflight`` (partial unique on ``domain`` where the state is
    queued or running) is the dedup, and this deliberately does NOT look for an
    existing job first. Two leads from the same business in the same minute is the
    ordinary case — an owner submits twice — and a read-then-write check loses that
    race by construction, because only Postgres sees both writers. So: attempt the
    insert, and read the unique violation as the answer.

    ``None`` is a normal outcome, not an error. The caller records it as a
    ``skipped_duplicate`` against the existing job rather than dropping the lead.
    """
    job_id = str(uuid.uuid4())
    row: dict[str, Any] = {
        "id": job_id,
        "domain": domain,
        # The leads row id and nothing else — no email, no phone crosses projects
        # (data/schema_factsheets.sql, "NO PROSPECT PII CROSSES OVER").
        "lead_ref": lead_ref,
        "tier": tier,
        "state": FactSheetJobState.QUEUED.value,
        "attempts": 0,
        "cost_usd": 0,
        "created_at": _now(),
    }
    try:
        _execute(
            f"enqueue_factsheet_job for {domain} (tier {tier})",
            lambda c: c.table(TABLE_FACTSHEET_JOBS).insert(row).execute(),
        )
    except StorageError as exc:
        if _is_duplicate_key(exc):
            return None
        raise
    return job_id


def _claim_one_job(job_id: str, attempts: int) -> dict[str, object] | None:
    """Compare-and-set one queued job to running; None if another worker won it.

    The update is filtered on ``state = 'queued'`` as well as the id, so of two
    workers that read the same row exactly one gets rows back. PostgREST has no
    ``select ... for update skip locked``; this is the same guarantee at the cost
    of one wasted round trip per lost race. ``job_id``/``attempts`` are parameters
    rather than loop variables so the lambda closes over them cleanly.
    """
    response = _execute(
        f"claim_factsheet_job {job_id}",
        lambda c: (
            c.table(TABLE_FACTSHEET_JOBS)
            .update(
                {
                    "state": FactSheetJobState.RUNNING.value,
                    "attempts": attempts + 1,
                    "claimed_at": _now(),
                }
            )
            .eq("id", job_id)
            .eq("state", FactSheetJobState.QUEUED.value)
            .execute()
        ),
    )
    rows = list(getattr(response, "data", None) or [])
    return rows[0] if rows else None


def claim_factsheet_job(tier: int | None = None) -> dict[str, object] | None:
    """Take the oldest queued job, marked running, or None if the queue is empty.

    Oldest-first because a lead that has waited longest is the one whose owner is
    still expecting something. ``attempts`` is incremented at claim time rather
    than on failure: a job that kills its worker mid-run must still count against
    its retries, since the failure that costs money is the one that never gets to
    write its own epitaph.

    Returns the claimed row (not a typed object) — a job is a queue record, not a
    domain value; the sheet it produces is the typed thing.
    """

    def _queued(client: Client) -> Any:
        q = (
            client.table(TABLE_FACTSHEET_JOBS)
            .select("*")
            .eq("state", FactSheetJobState.QUEUED.value)
        )
        if tier is not None:
            q = q.eq("tier", tier)
        return q.order("created_at").limit(_JOB_CLAIM_SCAN).execute()

    response = _execute("claim_factsheet_job (scan)", _queued)
    for row in list(getattr(response, "data", None) or []):
        claimed = _claim_one_job(str(row.get("id", "")), int(str(row.get("attempts") or 0)))
        if claimed is not None:
            return claimed
    return None


def finish_factsheet_job(
    job_id: str,
    state: FactSheetJobState,
    fact_sheet_id: str | None = None,
    cost_usd: float | None = None,
    error: str | None = None,
) -> None:
    """Record a job's terminal state, what it produced, and what it cost.

    Every terminal state goes through here, the ``SKIPPED_*`` ones included: the
    rolling tier-2 cap is computed off these rows (:func:`factsheet_spend_today`),
    so a skip that is not written is a spend decision nobody can audit afterwards.

    Writing a terminal state is also what releases the domain — the in-flight index
    only covers ``queued``/``running``, so until this lands no second job for that
    business can be queued at all.
    """
    row: dict[str, Any] = {"state": state.value, "finished_at": _now()}
    if fact_sheet_id is not None:
        row["fact_sheet_id"] = fact_sheet_id
    if cost_usd is not None:
        row["cost_usd"] = cost_usd
    if error is not None:
        row["error"] = error
    _execute(
        f"finish_factsheet_job {job_id} ({state.value})",
        lambda c: c.table(TABLE_FACTSHEET_JOBS).update(row).eq("id", job_id).execute(),
    )


def factsheet_spend_today() -> dict[str, float]:
    """Rolling 24-hour tier-2 run count and dollar spend — the limiter's input.

    Read from the ``factsheet_spend_today`` view so the window is defined once, in
    SQL, beside the table it aggregates. Unlike the hourly lead-alert cap, the run
    count excludes the ``skipped_*`` rows the limiter itself writes, so a tripped
    cap unwinds as the window slides instead of holding itself down with its own
    bookkeeping. Note the two figures do not have the same filter: the view sums
    ``cost_usd`` over every row in the window while counting only tier-2 rows in
    ``running``/``done``, so a *failed* tier-2 job's spend is charged but not
    counted. Read the dollars, not the count, when the question is money.
    """
    response = _execute(
        "factsheet_spend_today",
        lambda c: c.table(VIEW_FACTSHEET_SPEND_TODAY).select("*").limit(1).execute(),
    )
    rows = list(getattr(response, "data", None) or [])
    row = rows[0] if rows else {}
    return {
        # A count, not a dollar figure — but sharing one dict with the spend keeps
        # the cap check a single read of a single row.
        "tier2_runs": int(str(row.get("tier2_runs") or 0)),
        "spend_usd": float(str(row.get("spend_usd") or 0)),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        runs = list_all_audit_runs()
        print(f"Storage reachable: {len(runs)} audit run(s) visible.")
    except StorageError as exc:
        print(f"Cannot run storage test: {exc}")
        raise SystemExit(0) from None
