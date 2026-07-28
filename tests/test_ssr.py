from __future__ import annotations

import pytest

from src.audit.checks.ssr import SSRClass, classify_ssr
from src.audit.crawl.dom import spa_shell_state
from src.audit.crawl.fetcher import FetchConfig, should_escalate
from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord
from src.audit.crawl.page_select import classify_url, select_pages
from src.audit.crawl.urls import normalize_url

_PROSE = "This is a real sentence of content that should count as prose. " * 30


def _page(
    raw: str | None,
    rendered: str | None,
    *,
    blocked: bool = False,
    json_ld: list[dict[str, object]] | None = None,
) -> PageRecord:
    return PageRecord(
        url="https://x.com/",
        normalized_url="https://x.com/",
        category=PageCategory.HOMEPAGE,
        fetch_meta=FetchMeta(
            status_code=200,
            final_url="https://x.com/",
            fetched_at="t",
            was_rendered=rendered is not None,
            request_ua="ua",
            blocked=blocked,
            headers={},
        ),
        content_sha256="x",
        raw_html=raw,
        rendered_html=rendered,
        json_ld=json_ld or [],
    )


# --- SSR detector ------------------------------------------------------------


def test_ssr_plain_server_rendered_passes() -> None:
    page = _page(f"<html><body><article><p>{_PROSE}</p></article></body></html>", None)
    assert classify_ssr(page).classification is SSRClass.PASS


def test_ssr_empty_csr_shell_fails() -> None:
    page = _page(
        "<html><body><div id=root></div></body></html>",
        f"<html><body><article><p>{_PROSE}</p></article></body></html>",
    )
    result = classify_ssr(page)
    assert result.classification is SSRClass.FAIL
    assert result.shell_state == "empty"


def test_ssr_next_data_payload_does_not_fail() -> None:
    # Content is inline in __NEXT_DATA__ — AI crawlers ingest it without JS, so a
    # thin rendered-vs-raw text ratio must NOT produce a FAIL (the §2.3 trap).
    raw = (
        "<html><body><div id=__next></div>"
        '<script type="application/json" id="__NEXT_DATA__">'
        '{"props":{"body":"' + _PROSE + '"}}</script></body></html>'
    )
    page = _page(raw, f"<html><body><article><p>{_PROSE}</p></article></body></html>")
    result = classify_ssr(page)
    assert result.classification is SSRClass.PASS
    assert result.inline_credit_words > 0


def test_ssr_filled_shell_vetoes_fail() -> None:
    nav = "<nav>Home Pricing Product Docs Blog About Careers Contact</nav>"
    page = _page(
        f"<html><body><div id=root>{nav}</div></body></html>",
        f"<html><body><div id=root>{nav}<article><p>{_PROSE}</p></article></div></body></html>",
    )
    result = classify_ssr(page)
    assert result.classification is SSRClass.PARTIAL
    assert result.shell_state == "filled"


def test_ssr_blocked_is_ungradeable() -> None:
    page = _page("<html>Just a moment...</html>", None, blocked=True)
    assert classify_ssr(page).classification is SSRClass.UNGRADEABLE


def test_ssr_rendered_empty_is_ungradeable() -> None:
    page = _page("<html><body><div id=root></div></body></html>", "<html><body></body></html>")
    assert classify_ssr(page).classification is SSRClass.UNGRADEABLE


# --- shell state -------------------------------------------------------------


def test_spa_shell_state() -> None:
    assert spa_shell_state("<div id=root></div>") == "empty"
    assert (
        spa_shell_state("<div id=root><p>lots of real words here now please</p></div>") == "filled"
    )
    assert spa_shell_state("<div class=container>hello</div>") == "absent"


# --- escalation decision -----------------------------------------------------


def test_should_escalate() -> None:
    cfg = FetchConfig()
    fat = "<html><body>" + "<p>real content word</p>" * 80 + "</body></html>"
    assert should_escalate(fat, "real content " * 80, cfg)[0] is False
    assert should_escalate("<div id=root></div>", "", cfg)[0] is True
    # __NEXT_DATA__ present -> do not escalate even with thin extracted text.
    nextdata = '<div id=__next></div><script id="__NEXT_DATA__">{"a":1}</script>'
    assert should_escalate(nextdata, "", cfg)[0] is False


# --- url helpers -------------------------------------------------------------


def test_normalize_url() -> None:
    assert normalize_url("HTTPS://Example.com/Path/?b=2&a=1&utm_source=x#f") == (
        "https://example.com/Path/?a=1&b=2"
    )
    assert normalize_url("https://example.com") == "https://example.com/"
    assert normalize_url("https://example.com/a?gclid=1") == "https://example.com/a"
    # Default ports collapse onto the bare host (one cache key / graph node).
    assert normalize_url("https://example.com:443/") == "https://example.com/"
    assert normalize_url("http://example.com:80/a") == normalize_url("http://example.com/a")
    # A non-default port is preserved.
    assert normalize_url("https://example.com:8443/") == "https://example.com:8443/"


def test_classify_url() -> None:
    assert classify_url("https://x.com/pricing") is PageCategory.PRICING
    assert classify_url("https://x.com/compare/a-vs-b") is PageCategory.COMPARISON
    assert classify_url("https://x.com/docs/api") is PageCategory.DOCS
    assert classify_url("https://x.com/about") is PageCategory.OTHER


def test_is_blocked_detects_200_challenge() -> None:
    # A Cloudflare "Just a moment…" interstitial is served at HTTP 200 — it must
    # still be flagged as blocked, not treated as a thin normal page.
    import httpx

    from src.audit.crawl.fetcher import _is_blocked

    challenge = httpx.Response(
        200, headers={"server": "cloudflare"}, text="<html>Just a moment...</html>"
    )
    assert _is_blocked(challenge, challenge.text) is True
    # A normal 200 from a Cloudflare-fronted site (no challenge markers) is not blocked.
    normal = httpx.Response(200, headers={"server": "cloudflare"}, text="<html>real content</html>")
    assert _is_blocked(normal, normal.text) is False


def test_select_pages_prioritizes_high_value_categories_under_the_cap() -> None:
    # Low-value blog pages listed first must not crowd decisive comparison/pricing
    # pages out of the global cap — allocation is by priority weight, not order.
    import src.audit.crawl.page_select as ps

    sitemap = (
        [f"https://x.com/blog/post-{i}" for i in range(10)]
        + [f"https://x.com/compare/x-vs-rival-{i}" for i in range(3)]
        + [f"https://x.com/pricing/tier-{i}" for i in range(3)]
    )
    selected = ps.select_pages("https://x.com/", sitemap_urls=sitemap)
    cats = [c for _u, c in selected]
    # All 3 comparison and 3 pricing pages survive (their per-category caps), even
    # though 10 blog pages appeared first in the sitemap.
    assert cats.count(PageCategory.COMPARISON) == 3
    assert cats.count(PageCategory.PRICING) == 3


def test_select_pages_navlink_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    import src.audit.crawl.page_select as ps
    import src.net_guard as net_guard

    html = (
        "<html><body><nav>"
        "<a href='/pricing'>Pricing</a><a href='/blog/post'>Blog</a>"
        "<a href='https://other.com/y'>External</a><a href='#top'>Top</a>"
        "</nav></body></html>"
    )
    # discover_nav_links fetches through net_guard.safe_get (per-hop SSRF check),
    # so patch that seam rather than httpx.get.
    monkeypatch.setattr(
        net_guard,
        "safe_get",
        lambda client, url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)),
    )
    # Empty sitemap -> homepage nav-link discovery feeds the scorer (§7.5).
    selected = ps.select_pages("x.com", sitemap_urls=[])
    urls = [u for u, _ in selected]
    cats = {c for _, c in selected}
    assert "https://x.com/pricing" in urls
    assert PageCategory.PRICING in cats and PageCategory.BLOG in cats
    assert all("other.com" not in u for u in urls)  # external link excluded


def test_select_pages_caps_and_filters() -> None:
    sitemap = (
        ["https://x.com/pricing"]
        + [f"https://x.com/blog/{i}" for i in range(8)]
        + ["https://x.com/tag/foo", "https://other.com/pricing"]
    )
    selected = select_pages("x.com", sitemap_urls=sitemap)
    cats = [c for _, c in selected]
    assert selected[0] == ("https://x.com/", PageCategory.HOMEPAGE)
    assert cats.count(PageCategory.BLOG) == 5  # capped
    assert all("other.com" not in u for u, _ in selected)  # cross-host dropped
    assert all("/tag/" not in u for u, _ in selected)  # taxonomy dropped


# --- Local-service page selection (the SMB pivot fork) ----------------------------


def test_local_patterns_keep_the_service_pages_the_consumer_set_drops() -> None:
    """The measured failure this fork fixes.

    Across 8 Berkeley plumber sites the consumer patterns classified 210 of 221
    discovered URLs as OTHER and dropped them, leaving ~2 crawlable pages per site — so
    Cat 3/4 judged a homepage and a blog index and called it a site audit. These are the
    real URL shapes from albertnahmanplumbing.com.
    """
    from src.audit.crawl.models import PageCategory
    from src.audit.crawl.page_select import classify_url

    service_urls = [
        "https://x.com/hvac/cooling/ac-repair-maintenance/",
        "https://x.com/hvac/heating/furnace-installation-replacement/",
        "https://x.com/plumbing/drain-cleaning/",
        "https://x.com/services/water-heater-repair/",
        "https://x.com/emergency-plumbing/",
    ]
    for url in service_urls:
        # Dropped entirely on the consumer path...
        assert classify_url(url) is PageCategory.OTHER
        # ...and kept as a service page on the local one.
        assert classify_url(url, "local_service") is PageCategory.SERVICE

    assert classify_url("https://x.com/areas-served/berkeley/", "local_service") is (
        PageCategory.SERVICE_AREA
    )
    assert classify_url("https://x.com/reviews/", "local_service") is PageCategory.COMPARISON


def test_local_selection_fills_the_page_budget_with_service_pages() -> None:
    """A trade site is mostly service pages, and they are what Cat 3/4 must read, so the
    local caps skew toward them rather than spending the budget on a blog.

    The caps set priority, not a ceiling on the total: leftover budget backfills, because
    a real site whose pages are nearly all one category was otherwise getting 6 of 20
    slots while 8 auditable pages sat unused.
    """
    from src.audit.crawl.models import PageCategory
    from src.audit.crawl.page_select import select_pages

    sitemap = (
        [f"https://x.com/services/job-{i}/" for i in range(14)]
        + [f"https://x.com/areas-served/town-{i}/" for i in range(6)]
        + [f"https://x.com/blog/post-{i}/" for i in range(9)]
    )
    selected = select_pages("https://x.com/", sitemap_urls=sitemap, business_kind="local_service")
    kinds = [cat for _url, cat in selected]

    # Homepage always first, then service pages lead — the caps set PRIORITY.
    assert kinds[0] is PageCategory.HOMEPAGE
    assert kinds.count(PageCategory.SERVICE) >= 10  # LOCAL_CATEGORY_CAPS floor
    assert kinds.count(PageCategory.SERVICE_AREA) >= 4
    # Budget is spent, not left on the table: 29 candidates, cap of 20.
    assert len(selected) == 20
    # The same sitemap on the consumer path yields only the homepage + blog: every
    # service and service-area URL is OTHER there.
    consumer = select_pages("https://x.com/", sitemap_urls=sitemap)
    assert {cat for _u, cat in consumer} == {PageCategory.HOMEPAGE, PageCategory.BLOG}


def test_local_backfill_spends_leftover_budget_but_consumer_does_not() -> None:
    """The regression that prompted the backfill, both halves.

    A blog-heavy trade site (one service page, many articles) hit the local BLOG cap of
    3 and stopped at 5 pages while 8 more were available. Backfill fills the budget in
    priority order. The consumer path deliberately does NOT backfill: that would change
    how many pages an existing consumer audit crawls, and therefore its cost.
    """
    from src.audit.crawl.models import PageCategory
    from src.audit.crawl.page_select import select_pages

    sitemap = ["https://x.com/services/plumbing/"] + [
        f"https://x.com/blog/article-{i}/" for i in range(12)
    ]
    local = select_pages("https://x.com/", sitemap_urls=sitemap, business_kind="local_service")
    # 1 homepage + 1 service + 12 blog = 14 candidates, all under the cap of 20.
    assert len(local) == 14
    assert sum(1 for _u, c in local if c is PageCategory.BLOG) == 12

    # Consumer stays capped at BLOG=5 (+ homepage) — unchanged behaviour.
    consumer = select_pages("https://x.com/", sitemap_urls=sitemap)
    assert len(consumer) == 6
