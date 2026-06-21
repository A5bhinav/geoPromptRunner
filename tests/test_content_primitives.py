from __future__ import annotations

from typing import Any

from src.audit.checks.content_primitives import check_content_primitives
from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord


def _page(html: str, text: str, json_ld: list[dict[str, Any]] | None = None) -> PageRecord:
    return PageRecord(
        url="https://x.com/",
        normalized_url="https://x.com/",
        category=PageCategory.BLOG,
        fetch_meta=FetchMeta(
            status_code=200,
            final_url="https://x.com/",
            fetched_at="t",
            was_rendered=True,
            request_ua="ua",
            blocked=False,
            headers={},
        ),
        content_sha256="x",
        raw_html=html,
        rendered_html=html,
        extracted_text=text,
        json_ld=json_ld or [],
    )


def _by_key(page: PageRecord) -> dict[str, str]:
    return {c.check_key: c.status for c in check_content_primitives(page).checks}


def test_strong_page_passes_primitives() -> None:
    html = (
        "<html><body><h2>What is X?</h2><p>X is a tool.</p>"
        "<h2>How much does it cost?</h2>"
        "<ul><li>a</li><li>b</li><li>c</li><li>d</li></ul>"
        "<img src=a.png alt='a product screenshot'>"
        "<p>Last updated on March 2026.</p></body></html>"
    )
    text = (
        "X costs 9 dollars per month and is used by 12000 teams across 40 countries with a "
        "99 percent uptime guarantee. It holds a 4.8 average rating from 500 reviews on 3 "
        "review platforms since 2021. The free plan includes 5 projects and 2 seats, while "
        "the paid plan adds 50 projects, 20 seats, and 100 gigabytes of storage for 19 dollars."
    )
    statuses = _by_key(
        _page(html, text, json_ld=[{"@type": "Article", "dateModified": "2026-03-01"}])
    )
    assert statuses["headings_questions"] == "pass"
    assert statuses["scannable_format"] == "pass"
    assert statuses["alt_text"] == "pass"
    assert statuses["fact_density"] == "pass"
    assert statuses["freshness_date"] == "pass"


def test_weak_page_fails_primitives() -> None:
    html = (
        "<html><body><h1>Welcome</h1><p>"
        + "We are the best amazing solution for you. " * 40
        + "</p><img src=hero.png></body></html>"
    )
    text = "We are the best amazing solution for you. " * 40
    statuses = _by_key(_page(html, text))
    assert statuses["scannable_format"] == "fail"  # no lists/tables, wall of text
    assert statuses["alt_text"] == "fail"  # image missing alt
    assert statuses["fact_density"] == "fail"  # zero numbers
    assert statuses["freshness_date"] == "fail"  # no date
    assert statuses["headings_questions"] == "ungradeable"  # only one heading


def test_decorative_and_pixel_images_excluded_from_alt() -> None:
    # alt="" is intentional decorative; 1px is a tracker — neither counts against us.
    html = "<html><body><img src=a alt=''><img src=p width='1' height='1'></body></html>"
    statuses = _by_key(_page(html, "x"))
    assert statuses["alt_text"] == "ungradeable"  # no *content* images


def test_publish_date_only_is_partial() -> None:
    html = "<html><body><p>hello world</p></body></html>"
    statuses = _by_key(
        _page(html, "hello world", json_ld=[{"@type": "Article", "datePublished": "2020-01-01"}])
    )
    assert statuses["freshness_date"] == "partial"


def test_no_html_is_all_ungradeable() -> None:
    page = _page("", "")
    statuses = {c.check_key: c.status for c in check_content_primitives(page).checks}
    assert set(statuses.values()) == {"ungradeable"}
    assert len(statuses) == 5
