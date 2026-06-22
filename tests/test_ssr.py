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


def test_classify_url() -> None:
    assert classify_url("https://x.com/pricing") is PageCategory.PRICING
    assert classify_url("https://x.com/compare/a-vs-b") is PageCategory.COMPARISON
    assert classify_url("https://x.com/docs/api") is PageCategory.DOCS
    assert classify_url("https://x.com/about") is PageCategory.OTHER


def test_select_pages_navlink_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    import src.audit.crawl.page_select as ps

    html = (
        "<html><body><nav>"
        "<a href='/pricing'>Pricing</a><a href='/blog/post'>Blog</a>"
        "<a href='https://other.com/y'>External</a><a href='#top'>Top</a>"
        "</nav></body></html>"
    )
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: httpx.Response(200, text=html, request=httpx.Request("GET", url)),
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
