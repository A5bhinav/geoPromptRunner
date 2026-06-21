"""Persist the crawl so every downstream check reads the cache, never the web.

Cache key is ``(normalized_url, crawl_id)``. Small queryable artifacts
(extracted text, JSON-LD as ``jsonb``, fetch meta) live in Postgres/Supabase;
large HTML blobs belong gzipped in Supabase Storage with a ``storage_path`` +
``content_sha256`` pointer rather than bloating table rows (§1.6). Reads going
through the cache — not the live site — are what make a run reproducible.

This module owns the ``PageRecord``↔row mapping (audit-domain knowledge); the
actual Supabase write/read goes through :mod:`src.storage.db`, which wraps it in
try/except raising ``StorageError`` — no audit code touches Supabase directly
(the repo's storage rule).

Implemented: URL normalization, content hashing, and the page-cache round-trip.
The HTML blob upload to Supabase Storage (``storage_path``) is still a scaffold —
it lands with the render path that produces rendered HTML.
"""

from __future__ import annotations

import gzip
import logging
from typing import Any
from urllib.parse import urlsplit

from src.audit.crawl.models import CrawlResult, FetchMeta, PageCategory, PageRecord
from src.audit.crawl.urls import content_hash, normalize_url
from src.storage import db
from src.storage.db import StorageError

__all__ = [
    "normalize_url",
    "content_hash",
    "save_page",
    "load_pages",
]

logger = logging.getLogger(__name__)


def _blob_path(run_id: str, content_sha256: str, *, rendered: bool) -> str:
    """Content-addressed object path for a page's gzipped HTML blob."""
    suffix = "rendered.html.gz" if rendered else "html.gz"
    return f"{run_id}/{content_sha256}.{suffix}"


def _persist_blobs(run_id: str, page: PageRecord) -> str | None:
    """Upload gzipped raw (and rendered) HTML to Storage; set ``page.storage_path``.

    Best-effort: a Storage hiccup is logged but does not block the authoritative
    row write — the queryable artifacts (extracted_text, json_ld) still persist.
    Returns the rendered blob's path (recorded in the row's ``fetch_meta``), or
    ``None`` when the page was not rendered or its upload failed.
    """
    rendered_path: str | None = None
    try:
        if page.raw_html is not None:
            raw_path = _blob_path(run_id, page.content_sha256, rendered=False)
            db.upload_site_audit_html(raw_path, gzip.compress(page.raw_html.encode("utf-8")))
            page.storage_path = raw_path
        if page.rendered_html is not None:
            path = _blob_path(run_id, page.content_sha256, rendered=True)
            db.upload_site_audit_html(path, gzip.compress(page.rendered_html.encode("utf-8")))
            rendered_path = path
    except StorageError as exc:
        logger.warning("HTML blob upload failed for %s: %s", page.normalized_url, exc)
    return rendered_path


def _page_to_row(
    run_id: str, crawl_id: str, page: PageRecord, rendered_storage_path: str | None
) -> dict[str, Any]:
    """Map a :class:`PageRecord` to a ``site_audit_page`` row.

    ``id`` is omitted so the DB default fills it and an upsert leaves the PK
    stable on re-crawl. Raw/rendered HTML are not columns — only the
    ``storage_path`` pointer and ``content_sha256`` are persisted (§1.6); the
    rendered blob's path rides in ``fetch_meta`` so the single ``storage_path``
    column stays the raw view.
    """
    meta = page.fetch_meta
    return {
        "run_id": run_id,
        "crawl_id": crawl_id,
        "url": page.url,
        "normalized_url": page.normalized_url,
        "category": page.category.value,
        "status_code": meta.status_code,
        "final_url": meta.final_url,
        "request_ua": meta.request_ua,
        "was_rendered": meta.was_rendered,
        "render_reason": meta.render_reason,
        "blocked": meta.blocked,
        "content_sha256": page.content_sha256,
        "storage_path": page.storage_path,
        "extracted_text": page.extracted_text,
        "json_ld": page.json_ld,
        "fetch_meta": {"headers": meta.headers, "rendered_storage_path": rendered_storage_path},
        "fetched_at": meta.fetched_at,
    }


def _row_to_page(row: dict[str, object]) -> PageRecord:
    extra = row.get("fetch_meta")
    raw_headers = extra.get("headers", {}) if isinstance(extra, dict) else {}
    headers = (
        {str(k): str(v) for k, v in raw_headers.items()} if isinstance(raw_headers, dict) else {}
    )
    meta = FetchMeta(
        status_code=int(str(row.get("status_code") or 0)),
        final_url=str(row.get("final_url") or ""),
        fetched_at=str(row.get("fetched_at") or ""),
        was_rendered=bool(row.get("was_rendered")),
        request_ua=str(row.get("request_ua") or ""),
        render_reason=str(row["render_reason"]) if row.get("render_reason") else None,
        blocked=bool(row.get("blocked")),
        headers=headers,
    )
    try:
        category = PageCategory(str(row.get("category")))
    except ValueError:
        category = PageCategory.OTHER
    json_ld_val = row.get("json_ld")
    json_ld = json_ld_val if isinstance(json_ld_val, list) else []
    return PageRecord(
        url=str(row.get("url") or ""),
        normalized_url=str(row.get("normalized_url") or ""),
        category=category,
        fetch_meta=meta,
        content_sha256=str(row.get("content_sha256") or ""),
        raw_html=None,  # blob lives in Storage, not loaded here
        rendered_html=None,
        extracted_text=(
            str(row["extracted_text"]) if row.get("extracted_text") is not None else None
        ),
        json_ld=json_ld,
        storage_path=str(row["storage_path"]) if row.get("storage_path") else None,
    )


def save_page(run_id: str, crawl_id: str, page: PageRecord) -> None:
    """Persist one crawled page: gzipped HTML to Storage, queryable row to Postgres.

    Idempotent on ``(run_id, normalized_url)`` via the db upsert, so a retried
    crawl overwrites rather than duplicating. Delegates to :mod:`src.storage.db`,
    which raises ``StorageError`` on the row write; blob upload is best-effort.
    """
    rendered_storage_path = _persist_blobs(run_id, page)
    db.upsert_site_audit_pages(
        run_id, [_page_to_row(run_id, crawl_id, page, rendered_storage_path)]
    )


def load_pages(run_id: str, crawl_id: str) -> CrawlResult:
    """Rehydrate a previously-crawled domain from the cache for downstream checks.

    Domain and ``started_at`` are derived from the earliest page (they aren't
    stored per row); ``errors`` is empty since only successfully-saved pages
    persist.
    """
    rows = [r for r in db.get_site_audit_pages(run_id) if str(r.get("crawl_id")) == crawl_id]
    pages = [_row_to_page(r) for r in rows]
    domain = ""
    started_at = ""
    if pages:
        earliest = min(pages, key=lambda p: p.fetch_meta.fetched_at)
        started_at = earliest.fetch_meta.fetched_at
        domain = urlsplit(earliest.normalized_url).hostname or ""
    return CrawlResult(
        run_id=run_id,
        domain=domain,
        crawl_id=crawl_id,
        started_at=started_at,
        pages=pages,
        errors=[],
    )
