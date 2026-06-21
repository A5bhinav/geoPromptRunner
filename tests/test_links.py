from __future__ import annotations

from src.audit.checks.links import LinkGraphClass, analyze_link_graph
from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord

_NAV = (
    "<nav><a href='/'>Home</a><a href='/pricing'>Pricing</a>"
    "<a href='/product'>Product</a><a href='/blog'>Blog</a></nav>"
)


def _page(url: str, category: PageCategory, html: str) -> PageRecord:
    return PageRecord(
        url=url,
        normalized_url=url,
        category=category,
        fetch_meta=FetchMeta(
            status_code=200,
            final_url=url,
            fetched_at="t",
            was_rendered=False,
            request_ua="ua",
            blocked=False,
            headers={},
        ),
        content_sha256="x",
        raw_html=html,
        extracted_text="",
    )


def _site(home_main: str, inner_main: str) -> list[PageRecord]:
    home = f"<html><body>{_NAV}<main>{home_main}</main></body></html>"
    inner = f"<html><body>{_NAV}<main>{inner_main}</main></body></html>"
    return [
        _page("https://x.com/", PageCategory.HOMEPAGE, home),
        _page("https://x.com/pricing", PageCategory.PRICING, inner),
        _page("https://x.com/product", PageCategory.PRODUCT, inner),
        _page("https://x.com/blog", PageCategory.BLOG, inner),
    ]


def test_well_linked_passes() -> None:
    pages = _site(
        "<p>See <a href='/pricing'>detailed pricing plans</a>, "
        "<a href='/product'>product features overview</a>, "
        "<a href='/blog'>latest blog articles</a>.</p>",
        "<p>Back to <a href='/'>the homepage</a>; explore "
        "<a href='/product'>our product features</a>.</p>",
    )
    result = analyze_link_graph(pages, "x.com")
    assert result.classification is LinkGraphClass.PASS
    assert result.orphans == []
    # Homepage carries the most internal authority.
    by_url = {p.url: p for p in result.pages}
    assert by_url["https://x.com/"].click_depth == 0
    assert by_url["https://x.com/pricing"].click_depth == 1


def test_nav_only_orphans_fail() -> None:
    # Every page has only the shared nav — nav links are boilerplate (DOM +
    # cross-page repetition), so there are no in-content edges and inner pages
    # are orphaned.
    pages = _site("<p>Welcome.</p>", "<p>Some text.</p>")
    result = analyze_link_graph(pages, "x.com")
    assert result.classification is LinkGraphClass.FAIL
    assert len(result.orphans) == 3


def test_generic_anchors_partial() -> None:
    pages = _site(
        "<p><a href='/pricing'>click here</a> <a href='/product'>read more</a> "
        "<a href='/blog'>here</a></p>",
        "<p>Back to <a href='/'>the homepage</a>.</p>",
    )
    result = analyze_link_graph(pages, "x.com")
    assert result.classification is LinkGraphClass.PARTIAL
    assert {a.issue for a in result.anchor_issues} == {"generic"}


def test_external_links_excluded() -> None:
    pages = _site(
        "<p>See <a href='/pricing'>pricing details here</a> and "
        "<a href='https://twitter.com/x'>our twitter</a> and "
        "<a href='/product'>product overview page</a> and "
        "<a href='/blog'>blog posts here</a>.</p>",
        "<p>Back to <a href='/'>home page</a>.</p>",
    )
    result = analyze_link_graph(pages, "x.com")
    # The external twitter link is not an internal edge and never an orphan node.
    assert all("twitter.com" not in p.url for p in result.pages)
    assert result.classification is LinkGraphClass.PASS


def test_too_few_pages_ungradeable() -> None:
    pages = _site("<p><a href='/pricing'>pricing</a></p>", "<p>x</p>")[:2]
    assert analyze_link_graph(pages, "x.com").classification is LinkGraphClass.UNGRADEABLE


def test_sitemap_coverage_evidence() -> None:
    pages = _site(
        "<p>See <a href='/pricing'>detailed pricing plans</a>, "
        "<a href='/product'>product features overview</a>, "
        "<a href='/blog'>latest blog articles</a>.</p>",
        "<p>Back to <a href='/'>the homepage</a>.</p>",
    )
    sitemap = [
        "https://x.com/",
        "https://x.com/pricing",
        "https://x.com/product",
        "https://x.com/blog",
        "https://x.com/orphaned-only-in-sitemap",  # never linked in-content
    ]
    result = analyze_link_graph(pages, "x.com", sitemap_urls=sitemap)
    assert result.evidence["sitemap_size"] == 5
    # homepage + pricing/product/blog are all reached by an in-content link.
    assert result.evidence["sitemap_linked_in_content"] == 4
    assert (
        "https://x.com/orphaned-only-in-sitemap" in result.evidence["sitemap_not_internally_linked"]
    )
