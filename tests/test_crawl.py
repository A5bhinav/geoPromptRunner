"""Crawl-phase error accounting: a page that fetched fine but failed to PERSIST is
a storage concern, not a crawl-health signal, and must not inflate ``errors``."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.audit.crawl.fetcher import FetchConfig
from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord


def _page(url: str) -> PageRecord:
    return PageRecord(
        url=url,
        normalized_url=url,
        category=PageCategory.HOMEPAGE,
        fetch_meta=FetchMeta(
            status_code=200, final_url=url, fetched_at="t", was_rendered=False, request_ua="ua"
        ),
        content_sha256="x",
        raw_html="<html>ok</html>",
        extracted_text="ok",
    )


class _DummyRenderer:
    def __init__(self, *a: Any, **k: Any) -> None: ...

    async def __aenter__(self) -> _DummyRenderer:
        return self

    async def __aexit__(self, *a: Any) -> bool:
        return False


def _patch_crawl(monkeypatch: pytest.MonkeyPatch, *, save_raises: bool) -> None:
    """Stub the lazily-imported crawl deps so no network/browser is touched."""
    import src.audit.crawl.cache as cache
    import src.audit.crawl.fetcher as fetcher
    import src.audit.crawl.page_select as page_select

    monkeypatch.setattr(
        page_select,
        "select_pages",
        lambda domain, sitemap_urls, **_: [("https://x.com/", PageCategory.HOMEPAGE)],
    )
    monkeypatch.setattr(page_select, "discover_sitemap_urls", lambda home: [])
    monkeypatch.setattr(fetcher, "PlaywrightRenderer", _DummyRenderer)

    async def fake_fetch_page(
        url: str, category: Any, cfg: Any, renderer: Any, throttle: Any = None
    ) -> PageRecord:
        # `throttle` is the crawl-wide pacer (AdaptiveThrottle). The double tracks
        # the real signature deliberately: it is what caught the arity change.
        return _page(url)

    monkeypatch.setattr(fetcher, "fetch_page", fake_fetch_page)

    def fake_save(run_id: str, crawl_id: str, page: PageRecord) -> None:
        if save_raises:
            raise RuntimeError("boom")

    monkeypatch.setattr(cache, "save_page", fake_save)


def test_page_save_failure_lands_in_save_errors_not_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.audit.crawl.crawl import crawl_domain

    _patch_crawl(monkeypatch, save_raises=True)
    result = asyncio.run(crawl_domain("rid", "x.com", FetchConfig(respect_robots=False)))

    assert len(result.pages) == 1  # the page fetched fine and is kept in memory
    assert result.errors == []  # a persistence failure is NOT a crawl error
    assert len(result.save_errors) == 1  # it's tracked apart
    assert "save RuntimeError" in result.save_errors[0]


def test_successful_save_leaves_both_error_lists_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.audit.crawl.crawl import crawl_domain

    _patch_crawl(monkeypatch, save_raises=False)
    result = asyncio.run(crawl_domain("rid", "x.com", FetchConfig(respect_robots=False)))

    assert len(result.pages) == 1
    assert result.errors == []
    assert result.save_errors == []
