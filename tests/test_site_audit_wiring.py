from __future__ import annotations

from typing import Any

import pytest

from src.api.reports import build_report
from src.audit.crawl.models import CrawlResult, FetchMeta, PageCategory, PageRecord
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import QueryResult


def _page(url: str, *, json_ld: list[dict[str, Any]] | None = None) -> PageRecord:
    return PageRecord(
        url=url,
        normalized_url=url,
        category=PageCategory.HOMEPAGE,
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
        raw_html="<html><body><article><p>" + "word " * 80 + "</p></article></body></html>",
        extracted_text="word " * 80,
        json_ld=json_ld or [],
    )


def _outcome() -> AuditOutcome:
    return AuditOutcome(
        run_id=None,
        client_name="Acme",
        client_domains=["acme.com"],
        competitors=["Rival"],
        query_set_version="v1",
        runs_per_query=1,
        results=[
            QueryResult(
                query_id="q1",
                intent="category",
                prompt="(mock)",
                engine_name="mock",
                run_index=0,
                response="Acme is great.",
                citations=[],
                timestamp="t",
            )
        ],
    )


def test_run_site_audit_builds_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.audit.site_audit as site_audit

    pages = [
        _page("https://acme.com/"),
        _page(
            "https://acme.com/product",
            json_ld=[{"@type": "Organization", "name": "Acme", "url": "https://acme.com"}],
        ),
    ]
    crawl = CrawlResult(
        run_id="rid", domain="acme.com", crawl_id="cid", started_at="t", pages=pages, errors=[]
    )
    monkeypatch.setattr(site_audit, "run_site_audit_blocking", lambda run_id, domain: crawl)

    payload = site_audit.run_site_audit("rid", "acme.com", persist=False)
    assert payload["present"] is True
    assert payload["pages_crawled"] == 2
    keys = {c["check_key"] for c in payload["checks"]}
    # Per-page checks (ssr/schema + 5 content primitives) plus the site-level link check.
    assert {"ssr_rendering", "schema_valid", "internal_linking"} <= keys
    assert {"headings_questions", "fact_density", "freshness_date"} <= keys
    # Both pages are server-rendered (no escalation) -> SSR passes.
    assert payload["summary"].get("ssr_rendering.pass") == 2
    # The internal_linking check is site-level (empty page_url).
    assert any(
        c["check_key"] == "internal_linking" and c["page_url"] == "" for c in payload["checks"]
    )


def test_build_report_merges_site_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.audit.site_audit as site_audit

    crawl = CrawlResult(
        run_id="rid",
        domain="acme.com",
        crawl_id="cid",
        started_at="t",
        pages=[_page("https://acme.com/")],
        errors=[],
    )
    monkeypatch.setattr(site_audit, "run_site_audit_blocking", lambda run_id, domain: crawl)
    payload = site_audit.run_site_audit("rid", "acme.com", persist=False)

    report = build_report(_outcome(), site_audit=payload)
    assert report["site_audit"] is not None
    assert report["site_audit"]["domain"] == "acme.com"
    assert report["site_audit"]["pages_crawled"] == 1
    # The synthesized roadmap is part of the payload (empty here — the page passes).
    assert "roadmap" in report["site_audit"]


def test_build_report_without_site_audit_is_none() -> None:
    report = build_report(_outcome())
    assert report["site_audit"] is None


def test_site_audit_payload_from_rows() -> None:
    from src.audit.site_audit import site_audit_payload_from_rows

    rows: list[dict[str, object]] = [
        {
            "check_key": "ssr_rendering",
            "category": 1,
            "page_url": "https://acme.com/",
            "status": "fail",
            "details": {"reason": "content only in rendered DOM"},
        },
        {
            "check_key": "schema_valid",
            "category": 5,
            "page_url": "https://acme.com/",
            "status": "pass",
            "details": {"reason": "valid structured data"},
        },
    ]
    payload = site_audit_payload_from_rows("acme.com", rows)
    assert payload["pages_crawled"] == 1
    assert payload["summary"] == {"ssr_rendering.fail": 1, "schema_valid.pass": 1}
    assert payload["checks"][0]["detail"] == "content only in rendered DOM"
