"""Site-audit phase: crawl the client domain, run the on-site checks, persist.

This is the orchestration glue between the fetch/cache crawler, the deterministic
checkers (SSR §2, schema §3.1), and the report. It runs as a best-effort phase
alongside the engine fan-out (plan §6): a crawl failure degrades to an empty
``SiteAuditPayload`` and never blocks the answer report.

The audit layer owns the mapping from check results → report rows and → persisted
``site_audit_check`` rows; :mod:`src.storage.db` owns the Supabase write.
"""

from __future__ import annotations

import logging
from typing import Any

from src.api.reports import RoadmapRow, SiteAuditPayload, SiteCheckRow, SiteFindingRow
from src.audit.checks import (
    analyze_link_graph,
    check_content_primitives,
    check_schema,
    classify_ssr,
)
from src.audit.checks.links import LinkGraphResult
from src.audit.checks.schema import SchemaResult
from src.audit.checks.ssr import SSRResult
from src.audit.crawl import CrawlResult, PageRecord, run_site_audit_blocking
from src.audit.offsite.models import Confidence, FindingType, OffsiteFinding
from src.audit.synthesize import build_site_audit_roadmap
from src.storage import db

__all__ = [
    "run_site_audit",
    "site_audit_payload_from_rows",
    "SSR_CHECK_KEY",
    "SCHEMA_CHECK_KEY",
    "LINKS_CHECK_KEY",
]

logger = logging.getLogger(__name__)

SSR_CHECK_KEY = "ssr_rendering"
SCHEMA_CHECK_KEY = "schema_valid"
LINKS_CHECK_KEY = "internal_linking"


def _ssr_details(result: SSRResult) -> dict[str, Any]:
    return {
        "reason": result.reason,
        "ratio": result.ratio,
        "raw_words": result.raw_words,
        "inline_credit_words": result.inline_credit_words,
        "rendered_words": result.rendered_words,
        "shell_state": result.shell_state,
    }


def _schema_details(result: SchemaResult) -> dict[str, Any]:
    return {
        "reason": result.reason,
        "types_found": result.types_found,
        "mismatches": [
            {"type": m.type_name, "field": m.field_name, "value": m.schema_value, "note": m.note}
            for m in result.mismatches
        ],
        "incomplete_types": sorted({f.type_name for f in result.findings if not f.satisfied}),
    }


def _links_details(result: LinkGraphResult) -> dict[str, Any]:
    return {
        "reason": result.reason,
        "orphans": result.orphans,
        "anchor_issues": [
            {
                "source": a.source_url,
                "target": a.target_url,
                "anchor": a.anchor_text,
                "issue": a.issue,
            }
            for a in result.anchor_issues[:50]  # cap so the jsonb payload stays small
        ],
        "pages": [
            {
                "url": p.url,
                "in_degree": p.in_degree,
                "out_degree": p.out_degree,
                "pagerank": p.pagerank,
                "click_depth": p.click_depth,
                "is_orphan": p.is_orphan,
            }
            for p in result.pages
        ],
    }


def _check_row(
    run_id: str,
    check_key: str,
    category: int,
    page_url: str,
    status: str,
    details: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    # `id` omitted so the DB default fills it; upsert keeps the PK stable.
    return {
        "run_id": run_id,
        "check_key": check_key,
        "category": category,
        "page_url": page_url,
        "status": status,
        "method": "deterministic",
        "details": details,
        "evidence": evidence,
    }


def _summary(checks: list[SiteCheckRow]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for check in checks:
        key = f"{check['check_key']}.{check['status']}"
        summary[key] = summary.get(key, 0) + 1
    return summary


def run_site_audit(
    run_id: str,
    domain: str,
    *,
    brand: str | None = None,
    competitors: list[str] | None = None,
    persist: bool = True,
) -> SiteAuditPayload:
    """Crawl ``domain``, run the on-site checks, and (if ``brand`` given) Cat 6 offsite.

    Persists per-page verdicts to ``site_audit_check`` when ``persist`` is set
    (best-effort — a storage failure is logged, not raised). The crawl itself is
    already best-effort per page, so a single bad page never sinks the phase. The
    offsite research (Cat 6) runs only when ``brand`` is provided; per-competitor
    on-site comparison coverage runs when ``competitors`` are given.
    """
    crawl = run_site_audit_blocking(run_id, domain)

    checks: list[SiteCheckRow] = []
    rows: list[dict[str, Any]] = []
    for page in crawl.pages:
        checks.append(_run_ssr(run_id, page, rows))
        checks.append(_run_schema(run_id, page, rows))
        checks.extend(_run_primitives(run_id, page, rows))
    if crawl.pages:
        checks.append(_run_links(run_id, crawl, rows))
        coverage = _run_comparison_coverage(run_id, crawl.pages, competitors or [], rows)
        if coverage is not None:
            checks.append(coverage)

    if persist and rows:
        try:
            db.upsert_site_audit_checks(run_id, rows)
        except db.StorageError as exc:
            logger.info("Failed to persist site-audit checks (continuing): %s", exc)

    offsite_rows: list[SiteFindingRow] = []
    offsite_findings: list[OffsiteFinding] = []
    if brand:
        offsite_rows, offsite_findings = _run_offsite(run_id, brand, domain, persist)

    roadmap = _roadmap_rows(brand or domain, checks, offsite_findings)

    return SiteAuditPayload(
        present=bool(crawl.pages),
        domain=domain,
        pages_crawled=len(crawl.pages),
        checks=checks,
        summary=_summary(checks),
        errors=len(crawl.errors),
        offsite=offsite_rows,
        roadmap=roadmap,
    )


def _roadmap_rows(
    subject: str, checks: list[SiteCheckRow], offsite: list[OffsiteFinding]
) -> list[RoadmapRow]:
    """Synthesize the §5 prioritized roadmap from the audit results (plan §5.5)."""
    items = build_site_audit_roadmap(subject, checks, offsite)
    return [
        RoadmapRow(
            category=item.category,
            check_name=item.check_name,
            status=item.status,
            impact_label=item.impact_label,
            effort=item.effort,
            phase=item.phase,
        )
        for item in items
    ]


def _finding_payload_row(finding: OffsiteFinding) -> SiteFindingRow:
    return SiteFindingRow(
        finding_type=finding.finding_type.value,
        title=finding.title,
        url=finding.url,
        confidence=finding.confidence.value,
    )


def _finding_db_row(run_id: str, finding: OffsiteFinding) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "finding_type": finding.finding_type.value,
        "title": finding.title,
        "url": finding.url,
        "confidence": finding.confidence.value,
        "payload": finding.payload,
    }


def _run_offsite(
    run_id: str, brand: str, domain: str, persist: bool
) -> tuple[list[SiteFindingRow], list[OffsiteFinding]]:
    """Cat 6 offsite research (best-effort, never raises). Imported lazily.

    Returns both the thin report rows and the structured findings (the latter feed
    the roadmap synthesizer, which needs the payload dicts).
    """
    try:
        from src.audit.offsite import run_offsite_research

        result = run_offsite_research(brand, domain)
    except Exception as exc:  # phase is additive — never fail the audit
        logger.warning("offsite research failed for %s: %s", brand, type(exc).__name__)
        return [], []
    if persist:
        try:
            db.replace_site_audit_findings(
                run_id, [_finding_db_row(run_id, f) for f in result.findings]
            )
        except db.StorageError as exc:
            logger.info("Failed to persist offsite findings (continuing): %s", exc)
    return [_finding_payload_row(f) for f in result.findings], result.findings


def _run_ssr(run_id: str, page: PageRecord, rows: list[dict[str, Any]]) -> SiteCheckRow:
    result = classify_ssr(page)
    rows.append(
        _check_row(
            run_id,
            SSR_CHECK_KEY,
            1,
            page.url,
            result.classification.value,
            _ssr_details(result),
            result.evidence,
        )
    )
    return SiteCheckRow(
        check_key=SSR_CHECK_KEY,
        category=1,
        page_url=page.url,
        status=result.classification.value,
        detail=result.reason,
    )


def _run_schema(run_id: str, page: PageRecord, rows: list[dict[str, Any]]) -> SiteCheckRow:
    result = check_schema(page)
    rows.append(
        _check_row(
            run_id,
            SCHEMA_CHECK_KEY,
            5,
            page.url,
            result.classification.value,
            _schema_details(result),
            result.evidence,
        )
    )
    return SiteCheckRow(
        check_key=SCHEMA_CHECK_KEY,
        category=5,
        page_url=page.url,
        status=result.classification.value,
        detail=result.reason,
    )


_COMPARISON_CUES = (" vs ", "versus", "alternative", "comparison", "/compare", "compare ")


def _run_comparison_coverage(
    run_id: str, pages: list[PageRecord], competitors: list[str], rows: list[dict[str, Any]]
) -> SiteCheckRow | None:
    """Per-competitor on-site 'X vs {competitor}' / alternatives coverage (Comment 19).

    Site-level check (page_url empty). Returns ``None`` when no competitors are
    given. A competitor is 'covered' if a crawled page mentions it in a comparison
    context (a comparison-category page, or a vs/alternative/compare cue nearby).
    """
    valid = [c for c in competitors if c.strip()]
    if not valid:
        return None
    haystacks = [
        (page.category.value, f"{page.url.lower()} {(page.extracted_text or '').lower()}")
        for page in pages
    ]
    covered = []
    for competitor in valid:
        name = competitor.lower().strip()
        if any(
            name in hay
            and (category == "comparison" or any(cue in hay for cue in _COMPARISON_CUES))
            for category, hay in haystacks
        ):
            covered.append(competitor)
    uncovered = [c for c in valid if c not in covered]
    if not uncovered:
        status = "pass"
        detail = f"on-site comparison content covers all {len(valid)} competitor(s)"
    elif not covered:
        status = "fail"
        detail = f"no on-site 'vs {{competitor}}' / alternatives content for: {', '.join(valid)}"
    else:
        status = "partial"
        detail = f"missing comparison content for: {', '.join(uncovered)}"
    rows.append(
        _check_row(
            run_id,
            "comparison_coverage",
            4,
            "",
            status,
            {"reason": detail, "covered": covered, "uncovered": uncovered},
            {},
        )
    )
    return SiteCheckRow(
        check_key="comparison_coverage", category=4, page_url="", status=status, detail=detail
    )


def _run_primitives(
    run_id: str, page: PageRecord, rows: list[dict[str, Any]]
) -> list[SiteCheckRow]:
    """Deterministic Cat 3/4 content primitives — several verdicts per page."""
    result = check_content_primitives(page)
    out: list[SiteCheckRow] = []
    for check in result.checks:
        rows.append(
            _check_row(
                run_id,
                check.check_key,
                check.category,
                page.url,
                check.status,
                {"reason": check.detail, **check.metrics},
                {},
            )
        )
        out.append(
            SiteCheckRow(
                check_key=check.check_key,
                category=check.category,
                page_url=page.url,
                status=check.status,
                detail=check.detail,
            )
        )
    return out


def _run_links(run_id: str, crawl: CrawlResult, rows: list[dict[str, Any]]) -> SiteCheckRow:
    # Site-level verdict (page_url empty) — built once over the whole crawl.
    result = analyze_link_graph(crawl.pages, crawl.domain, sitemap_urls=crawl.sitemap_urls)
    rows.append(
        _check_row(
            run_id,
            LINKS_CHECK_KEY,
            2,
            "",
            result.classification.value,
            _links_details(result),
            result.evidence,
        )
    )
    return SiteCheckRow(
        check_key=LINKS_CHECK_KEY,
        category=2,
        page_url="",
        status=result.classification.value,
        detail=result.reason,
    )


def _finding_from_row(row: dict[str, object]) -> OffsiteFinding:
    """Reconstruct a structured :class:`OffsiteFinding` from a stored row (with payload)."""
    try:
        ftype = FindingType(str(row.get("finding_type", "")))
    except ValueError:
        ftype = FindingType.COMMUNITY
    try:
        conf = Confidence(str(row.get("confidence", "low")))
    except ValueError:
        conf = Confidence.LOW
    payload = row.get("payload")
    return OffsiteFinding(
        finding_type=ftype,
        title=str(row.get("title", "")),
        url=(str(row["url"]) if row.get("url") else None),
        confidence=conf,
        payload=payload if isinstance(payload, dict) else {},
    )


def site_audit_payload_from_rows(
    domain: str,
    rows: list[dict[str, object]],
    finding_rows: list[dict[str, object]] | None = None,
    brand: str | None = None,
) -> SiteAuditPayload:
    """Rebuild a :class:`SiteAuditPayload` from stored check + offsite-finding rows.

    Used on the report-from-storage path (a run not in this process's memory).
    ``pages_crawled`` is the count of distinct page URLs; per-page crawl errors
    aren't persisted, so ``errors`` is 0 here.
    """
    checks: list[SiteCheckRow] = []
    for row in rows:
        details = row.get("details")
        detail = str(details.get("reason", "")) if isinstance(details, dict) else ""
        checks.append(
            SiteCheckRow(
                check_key=str(row.get("check_key", "")),
                category=int(str(row.get("category") or 0)),
                page_url=str(row.get("page_url", "")),
                status=str(row.get("status", "")),
                detail=detail,
            )
        )
    findings = [_finding_from_row(r) for r in (finding_rows or [])]
    offsite = [_finding_payload_row(f) for f in findings]
    pages = len({c["page_url"] for c in checks if c["page_url"]})
    return SiteAuditPayload(
        present=bool(checks or offsite),
        domain=domain,
        pages_crawled=pages,
        checks=checks,
        summary=_summary(checks),
        errors=0,
        offsite=offsite,
        roadmap=_roadmap_rows(brand or domain, checks, findings),
    )
