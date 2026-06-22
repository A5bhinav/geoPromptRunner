"""Fetch-phase orchestrator and the single entrypoint the runner will call.

``run_site_audit_blocking(run_id, domain)`` is the self-contained, synchronous
callable the threaded runner invokes (impl guide §6.1). It owns an ``asyncio.run``
of the async crawler so the browser is launched *and* closed inside one loop in
one place (never shared across loops — the documented hang in
playwright-python #2444). Designed as one callable now so the later lift to a
subprocess-per-crawl (§6.5 Layer 2) is a trivial wrapper, not a refactor.

``crawl_domain`` runs the full select → fetch → cache page loop (best-effort per
page). ``__main__`` prints the resolved crawl plan/config without hitting the
network.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from src.audit.crawl.fetcher import FetchConfig
from src.audit.crawl.models import CrawlResult

__all__ = ["run_site_audit_blocking", "crawl_domain"]

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_crawl_id() -> str:
    return str(uuid.uuid4())


async def crawl_domain(run_id: str, domain: str, config: FetchConfig | None = None) -> CrawlResult:
    """Crawl one domain's priority page set into a :class:`CrawlResult`.

    Selects pages (page_select), fetches each through the two-tier fetcher under a
    bounded concurrency gate, persists every page to the cache, and collects
    per-page failures into ``CrawlResult.errors`` (best-effort, §6.3) so one bad
    page never sinks the phase. The browser is launched and closed within this
    coroutine only; a launch failure degrades to a raw-only crawl rather than
    aborting.
    """
    from contextlib import AsyncExitStack

    from src.audit.crawl import cache
    from src.audit.crawl.fetcher import PlaywrightRenderer, fetch_page
    from src.audit.crawl.models import PageCategory
    from src.audit.crawl.page_select import discover_sitemap_urls, select_pages
    from src.audit.crawl.robots import RobotsPolicy, load_robots

    cfg = config or FetchConfig()
    crawl_id = _new_crawl_id()
    result = CrawlResult(run_id=run_id, domain=domain, crawl_id=crawl_id, started_at=_utcnow_iso())

    # robots.txt: skip Disallow-ed pages and honor Crawl-delay (§1.5). A
    # disallowed page is recorded — being invisible to GPTBot is itself a finding.
    policy = load_robots(domain) if cfg.respect_robots else RobotsPolicy(None)
    home = domain if "://" in domain else f"https://{domain}"
    result.sitemap_urls = discover_sitemap_urls(home)  # full set for orphan-vs-sitemap
    # Pass the discovered list (even when empty) so select_pages doesn't re-probe and
    # falls back to homepage nav-link discovery on a sitemap-less site (§7.5).
    selected = select_pages(domain, sitemap_urls=result.sitemap_urls)
    pages = []
    for url, category in selected:
        if not policy.allowed(url):
            result.errors.append(f"{url}: robots-disallowed")
        else:
            pages.append((url, category))
    delay = policy.crawl_delay()
    logger.info(
        "crawl %s: %d/%d pages allowed (crawl_id=%s, delay=%s)",
        domain,
        len(pages),
        len(selected),
        crawl_id,
        delay,
    )
    # A Crawl-delay means serialize and pause between fetches; otherwise fan out.
    gate = asyncio.Semaphore(1 if delay else cfg.max_render_concurrency)

    async def _crawl_one(url: str, category: PageCategory, renderer: object | None) -> None:
        async with gate:
            try:
                page = await fetch_page(url, category, cfg, renderer)  # type: ignore[arg-type]
            except Exception as exc:  # per-page best-effort — record and move on
                logger.warning("page fetch failed %s: %s", url, type(exc).__name__)
                result.errors.append(f"{url}: fetch {type(exc).__name__}: {exc}")
                return
            finally:
                if delay:
                    await asyncio.sleep(delay)  # politeness pause, inside the gate
            result.pages.append(page)
            try:
                cache.save_page(run_id, crawl_id, page)
            except Exception as exc:  # persistence best-effort — keep page in memory
                logger.warning("page save failed %s: %s", url, type(exc).__name__)
                result.errors.append(f"{url}: save {type(exc).__name__}")

    async with AsyncExitStack() as stack:
        renderer: object | None = None
        try:
            renderer = await stack.enter_async_context(PlaywrightRenderer(cfg))
        except Exception as exc:  # no browser → raw-only, still useful
            logger.warning("browser launch failed; raw-only crawl: %s", type(exc).__name__)
        await asyncio.gather(*(_crawl_one(url, cat, renderer) for url, cat in pages))

    logger.info("crawl %s done: %d pages, %d errors", domain, len(result.pages), len(result.errors))
    return result


def run_site_audit_blocking(
    run_id: str, domain: str, config: FetchConfig | None = None
) -> CrawlResult:
    """Synchronous entrypoint for the threaded runner — wraps the async crawl.

    Safe to call only from a worker thread with no running event loop (never from
    the uvicorn request coroutine, §1.3). Creates a fresh loop via ``asyncio.run``,
    runs :func:`crawl_domain`, and tears it down — so all Chromium memory is
    reclaimed when the call returns.
    """
    cfg = config or FetchConfig()
    logger.info("site-audit crawl starting: run_id=%s domain=%s", run_id, domain)
    return asyncio.run(crawl_domain(run_id, domain, cfg))


if __name__ == "__main__":
    from src.audit.crawl.page_select import CATEGORY_CAPS, CATEGORY_PATTERNS, GLOBAL_PAGE_CAP

    logging.basicConfig(level=logging.INFO)
    cfg = FetchConfig()
    print("Site-audit crawl — resolved plan/config\n")
    print(f"crawl_id (sample): {_new_crawl_id()}")
    print(f"started_at        : {_utcnow_iso()}")
    print(f"request UA        : {cfg.request_ua}")
    print(f"global page cap   : {GLOBAL_PAGE_CAP}")
    print(f"thin-text escalate: < {cfg.thin_text_chars} chars")
    print(f"render concurrency: {cfg.max_render_concurrency}\n")
    print("category          weight  cap  pattern")
    for category, (pattern, weight) in CATEGORY_PATTERNS.items():
        cap = CATEGORY_CAPS.get(category, "-")
        print(f"  {category.value:14s}  {weight:>5}  {str(cap):>3}  {pattern}")
