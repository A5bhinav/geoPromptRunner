"""Site-audit fetch & cache layer (Categories 1–5).

A two-tier crawler (raw httpx → headless Playwright only when needed) that pulls
a domain's priority page set into a reproducible cache. Every downstream
checker — SSR-vs-CSR, schema, link graph, the LLM judge — reads this cache and
never re-fetches the live web. See docs/site-audit-implementation-guide.md §1.

The public entrypoint is :func:`run_site_audit_blocking`, the self-contained
synchronous callable the threaded runner invokes (impl guide §6.1).
"""

from __future__ import annotations

from src.audit.crawl.crawl import crawl_domain, run_site_audit_blocking
from src.audit.crawl.models import CrawlResult, FetchMeta, PageCategory, PageRecord

__all__ = [
    "run_site_audit_blocking",
    "crawl_domain",
    "CrawlResult",
    "PageRecord",
    "PageCategory",
    "FetchMeta",
]
