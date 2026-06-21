"""Typed records produced by the site-audit fetch & cache layer.

Everything the deterministic checkers, the SSR-vs-CSR detector, and the LLM judge
read downstream comes from these structures — no check ever re-fetches the live
web (see docs/site-audit-implementation-guide.md §1.6). A ``PageRecord`` is the
unit of cache: raw bytes plus, only when the raw fetch was insufficient, the
headless-rendered DOM, alongside the extracted text and parsed JSON-LD the
checkers actually consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "PageCategory",
    "FetchMeta",
    "PageRecord",
    "CrawlResult",
]


class PageCategory(StrEnum):
    """How a URL was classified by the sitemap/path scorer (see page_select)."""

    HOMEPAGE = "homepage"
    PRICING = "pricing"
    COMPARISON = "comparison"
    PRODUCT = "product"
    DOCS = "docs"
    BLOG = "blog"
    OTHER = "other"


@dataclass
class FetchMeta:
    """Provenance for one fetched page — what happened, not the content itself."""

    status_code: int
    final_url: str
    fetched_at: str  # ISO-8601 UTC
    was_rendered: bool
    request_ua: str
    render_reason: str | None = None  # why we escalated to Playwright, if we did
    blocked: bool = False  # Cloudflare/anti-bot challenge — recorded, not bypassed (§1.5)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class PageRecord:
    """One crawled page: the cache row + blob pointer the whole audit reads from.

    ``raw_html`` is always the true byte stream (httpx, GPTBot UA). ``rendered_html``
    is populated only when the raw fetch was escalated to a headless render — its
    presence alongside ``raw_html`` is exactly the SSR-vs-CSR signal (§2). Large
    HTML blobs are meant to live in object storage; ``storage_path`` points at them
    while ``content_sha256`` dedups/change-detects.
    """

    url: str
    normalized_url: str
    category: PageCategory
    fetch_meta: FetchMeta
    content_sha256: str
    raw_html: str | None = None
    rendered_html: str | None = None
    extracted_text: str | None = None
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    storage_path: str | None = None


@dataclass
class CrawlResult:
    """The whole fetch phase for one domain — handed to the downstream checkers.

    Best-effort by design (plan §6): ``errors`` collects per-page failures so a
    single bad page never sinks the crawl, and the report renders from whatever
    pages succeeded.
    """

    run_id: str
    domain: str
    crawl_id: str
    started_at: str  # ISO-8601 UTC
    pages: list[PageRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
