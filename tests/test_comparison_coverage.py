from __future__ import annotations

from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord
from src.audit.site_audit import _run_comparison_coverage


def _page(url: str, category: PageCategory, text: str) -> PageRecord:
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
        extracted_text=text,
    )


def test_no_competitors_returns_none() -> None:
    pages = [_page("https://x.com/", PageCategory.HOMEPAGE, "home")]
    assert _run_comparison_coverage("r", pages, [], []) is None


def test_partial_coverage() -> None:
    pages = [
        _page("https://x.com/compare/x-vs-whoop", PageCategory.COMPARISON, "X vs Whoop"),
        _page("https://x.com/blog", PageCategory.BLOG, "general fitness post"),
    ]
    rows: list[dict[str, object]] = []
    row = _run_comparison_coverage("r", pages, ["Whoop", "Garmin"], rows)
    assert row is not None
    assert row["status"] == "partial"
    assert "Garmin" in row["detail"]
    assert rows[0]["details"]["covered"] == ["Whoop"]


def test_all_covered_passes() -> None:
    pages = [
        _page(
            "https://x.com/whoop-alternative", PageCategory.COMPARISON, "the best Whoop alternative"
        ),
        _page(
            "https://x.com/garmin-comparison", PageCategory.OTHER, "Garmin comparison and review"
        ),
    ]
    row = _run_comparison_coverage("r", pages, ["Whoop", "Garmin"], [])
    assert row is not None
    assert row["status"] == "pass"


def test_none_covered_fails() -> None:
    pages = [_page("https://x.com/", PageCategory.HOMEPAGE, "we are great")]
    row = _run_comparison_coverage("r", pages, ["Whoop"], [])
    assert row is not None
    assert row["status"] == "fail"
