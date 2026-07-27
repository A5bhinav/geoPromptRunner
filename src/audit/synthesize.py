"""Roadmap synthesizer — site-audit results → ``RubricScore`` rows (plan §5.5 / §8.6).

The roadmap machinery in :mod:`src.audit.rubric` already turns ``RubricScore``
rows into the §4 category rollup and the §5 prioritized roadmap (impact × effort ×
phase). Historically those rows were hand-entered by an analyst; this module
generates them from the automated audit instead (plan §6 step 3) so a single CSV
upload drives the whole report.

It maps three sources to the seven rubric categories:
- **Deterministic checks** (SSR→Cat 1, internal-linking→Cat 2, schema→Cat 5):
  per-page verdicts are rolled up to one row per check (fail > partial > pass;
  ``ungradeable`` rows are dropped — an unmeasurable check isn't a gap).
- **Offsite findings** (Cat 6): Wikidata/reviews/community/listicle presence.
- **Content-judge verdicts** (Cat 3/4): only when supplied — they stay out until
  the judge is calibrated (plan §7), so by default the synthesizer omits them.
"""

from __future__ import annotations

from collections import Counter

from src.api.reports import SiteCheckRow
from src.audit.checks.content_judge import CheckVerdict, ContentClass
from src.audit.offsite.models import Confidence, FindingType, OffsiteFinding
from src.audit.rubric import (
    CheckStatus,
    RoadmapItem,
    RubricCategory,
    build_roadmap,
    render_roadmap,
)
from src.storage.models import RubricScore

__all__ = [
    "site_audit_to_rubric_scores",
    "build_site_audit_roadmap",
    "render_site_audit_roadmap",
]

# check_key → (rubric category, human check name, weight). Weight feeds the
# roadmap's impact when a check isn't linked to queries; SSR is the
# highest-value finding so it carries the most weight (§2).
_CHECK_MAP: dict[str, tuple[RubricCategory, str, float]] = {
    "ssr_rendering": (
        RubricCategory.TECHNICAL_ACCESSIBILITY,
        "core content server-rendered (AI-crawler visible)",
        3.0,
    ),
    # Domain-level Cat-1 technical-accessibility probes (technical_check.py). If
    # AI crawlers can't reach the content at all, nothing downstream matters —
    # so robots/WAF/gating carry the heaviest weight.
    "robots_txt": (
        RubricCategory.TECHNICAL_ACCESSIBILITY,
        "robots.txt allows AI crawlers",
        3.0,
    ),
    "crawler_access": (
        RubricCategory.TECHNICAL_ACCESSIBILITY,
        "AI crawler UAs not blocked at the CDN/WAF",
        3.0,
    ),
    "gated_content": (
        RubricCategory.TECHNICAL_ACCESSIBILITY,
        "content reachable, not gated behind a login/paywall",
        2.5,
    ),
    # llms_txt is deliberately unmapped: no engine confirms consuming it and
    # ~300k-domain analyses show zero correlation with AI citations, so a missing
    # llms.txt must never surface as a roadmap gap. The Cat-1 check still runs and
    # appears in the raw check table as an informational note.
    "sitemap": (
        RubricCategory.TECHNICAL_ACCESSIBILITY,
        "XML sitemap present and current",
        1.0,
    ),
    "internal_linking": (
        RubricCategory.CONTENT_COVERAGE,
        "internal linking establishes topical authority",
        1.5,
    ),
    # Schema is scored as hygiene/entity clarity, not a citation driver —
    # controlled studies show no AI-citation lift from JSON-LD (retrieval reads
    # visible HTML), so the check name must not imply visibility impact.
    "schema_valid": (
        RubricCategory.STRUCTURED_DATA,
        "schema.org markup valid and matching visible content (hygiene)",
        1.5,
    ),
    # Deterministic Cat 3/4 content primitives (§3.3).
    "headings_questions": (
        RubricCategory.CONTENT_STRUCTURE,
        "headings written as consumer questions",
        1.0,
    ),
    "scannable_format": (
        RubricCategory.CONTENT_STRUCTURE,
        "scannable formatting (lists/tables)",
        1.0,
    ),
    "alt_text": (RubricCategory.CONTENT_STRUCTURE, "alt text on images", 0.5),
    "fact_density": (RubricCategory.CONTENT_SUBSTANCE, "fact density / statistics", 1.5),
    "freshness_date": (RubricCategory.CONTENT_SUBSTANCE, "visible last-updated date", 1.0),
    "comparison_coverage": (
        RubricCategory.CONTENT_SUBSTANCE,
        "on-site comparison content (X vs competitors)",
        1.5,
    ),
}

# Cat 3 = structure, Cat 4 = substance (E-E-A-T) — the content-judge categories.
_CONTENT_CATEGORY = {3: RubricCategory.CONTENT_STRUCTURE, 4: RubricCategory.CONTENT_SUBSTANCE}

_SITE_LEVEL = ""  # page_url for a whole-site check


def _rollup_status(statuses: list[str]) -> str | None:
    """Roll per-page verdicts into one: fail > partial > pass; all-ungradeable → None."""
    s = set(statuses)
    if "fail" in s:
        return "fail"
    if "partial" in s:
        return "partial"
    if "pass" in s:
        return "pass"
    return None


def _checks_to_scores(subject: str, checks: list[SiteCheckRow]) -> list[RubricScore]:
    by_key: dict[str, list[str]] = {}
    for check in checks:
        if check["check_key"] in _CHECK_MAP:
            by_key.setdefault(check["check_key"], []).append(check["status"])

    scores: list[RubricScore] = []
    for check_key, statuses in by_key.items():
        status = _rollup_status(statuses)
        if status is None:
            continue  # every page ungradeable — not a gap
        category, check_name, weight = _CHECK_MAP[check_key]
        tally = Counter(statuses)
        note = ", ".join(f"{n} {label}" for label, n in sorted(tally.items()))
        scores.append(
            RubricScore(
                subject=subject,
                category=category.value,
                check_name=check_name,
                status=status,
                weight=weight,
                note=f"{len(statuses)} page(s): {note}",
                query_ids=[],
            )
        )
    return scores


def _offsite_to_scores(
    subject: str, findings: list[OffsiteFinding], business_kind: str = "product"
) -> list[RubricScore]:
    scores: list[RubricScore] = []
    for finding in findings:
        for check_name, status, weight in _offsite_scores(finding, business_kind):
            scores.append(
                RubricScore(
                    subject=subject,
                    category=RubricCategory.OFFSITE_AUTHORITY.value,
                    check_name=check_name,
                    status=status,
                    weight=weight,
                    note=finding.title,
                    query_ids=[],
                )
            )
    return scores


def _local_review_scores(finding: OffsiteFinding) -> list[tuple[str, str, float]]:
    """Local directory presence, split into TWO checks (W4.3).

    Google Business Profile is pulled out and weighted separately because it is not
    just another directory: Google's local pack — and the AI local answers built on
    it — are generated FROM the GBP entity. A business with no profile is
    structurally absent from the surface that matters most, the local equivalent of
    failing SSR, so it carries the same 3.0 weight rather than being averaged away
    inside a "3 of 8 directories" pass.

    Both clear the evidence bar the `llms_txt` precedent sets: engines demonstrably
    consume these sources (they are cited by name in local AI answers), unlike
    llms.txt which no engine confirms reading.
    """
    platforms = finding.payload.get("platforms", {})
    if not platforms:
        return []

    gbp = platforms.get("google.com/maps", {})
    out: list[tuple[str, str, float]] = [
        (
            "Google Business Profile listing present",
            "pass" if gbp.get("present") else "fail",
            3.0,
        )
    ]

    others = {host: info for host, info in platforms.items() if host != "google.com/maps"}
    if others:
        present = sum(1 for info in others.values() if info.get("present"))
        total = len(others)
        status = "pass" if present >= total / 2 else "partial" if present else "fail"
        out.append(("listed on the local directories AI cites (Yelp, BBB, Angi)", status, 2.5))
    return out


def _offsite_scores(
    finding: OffsiteFinding, business_kind: str = "product"
) -> list[tuple[str, str, float]]:
    """Map one finding to zero or more (check_name, status, weight) rows."""
    if business_kind == "local_service" and finding.finding_type is FindingType.REVIEWS:
        return _local_review_scores(finding)

    if business_kind == "local_service" and finding.finding_type is FindingType.ENTITY_CONSISTENCY:
        # For a local business this IS the NAP-consistency check, and it matters more
        # than generic web entity consistency: a name/address/phone that disagrees
        # across directories splits the entity, so no single listing accumulates
        # enough authority to be cited at all.
        return [
            (
                "name/address/phone consistent across directories (NAP)",
                _confidence_status(finding.confidence),
                2.5,
            )
        ]

    mapped = _offsite_score(finding)
    return [mapped] if mapped is not None else []


def _offsite_score(finding: OffsiteFinding) -> tuple[str, str, float] | None:
    """Map one structured finding to (check_name, status, weight); None to skip."""
    if finding.finding_type is FindingType.WIKIDATA:
        found = bool(finding.payload.get("found"))
        return ("entity present in Wikidata / Knowledge Graph", "pass" if found else "fail", 2.0)
    if finding.finding_type is FindingType.REVIEWS:
        platforms = finding.payload.get("platforms", {})
        present = sum(1 for info in platforms.values() if info.get("present"))
        total = len(platforms) or 1
        status = "pass" if present >= total / 2 else "partial" if present else "fail"
        return ("reviews on Trustpilot / consumer platforms", status, 1.5)
    # For the presence-style findings the agent reports, the model's confidence is
    # the only signal to how real the presence is — a low-confidence "one stale
    # Reddit thread" must NOT score the same full pass as a strong presence, or the
    # offsite grade inflates and the gap is wrongly dropped from the roadmap.
    if finding.finding_type is FindingType.ENTITY_CONSISTENCY:
        return ("entity consistent across the web", _confidence_status(finding.confidence), 1.5)
    if finding.finding_type is FindingType.COMMUNITY:
        return ("presence on Reddit / consumer forums", _confidence_status(finding.confidence), 2.0)
    if finding.finding_type is FindingType.LISTICLE:
        return (
            "named in 'best [category]' listicles / roundups",
            _confidence_status(finding.confidence),
            1.5,
        )
    if finding.finding_type is FindingType.PRESS:
        return ("third-party citations / press", _confidence_status(finding.confidence), 1.0)
    return None  # BACKLINKS et al. — informational, not a roadmap gap


def _confidence_status(confidence: Confidence) -> str:
    """Grade a presence finding by the agent's confidence: high→pass, medium→partial,
    low→fail. Keeps a weak/uncertain presence from scoring full offsite credit."""
    if confidence is Confidence.HIGH:
        return "pass"
    if confidence is Confidence.MEDIUM:
        return "partial"
    return "fail"


def _content_to_scores(subject: str, verdicts: list[CheckVerdict]) -> list[RubricScore]:
    scores: list[RubricScore] = []
    for verdict in verdicts:
        if verdict.classification is ContentClass.UNKNOWN:
            continue  # abstention / needs review — not a confirmed gap
        category = _CONTENT_CATEGORY.get(verdict.category)
        if category is None:
            continue
        scores.append(
            RubricScore(
                subject=subject,
                category=category.value,
                check_name=verdict.check_id.replace("_", " "),
                status=CheckStatus(verdict.classification.value).value,
                weight=1.0,
                note=verdict.reason,
                query_ids=[],
            )
        )
    return scores


def site_audit_to_rubric_scores(
    subject: str,
    checks: list[SiteCheckRow],
    offsite: list[OffsiteFinding] | None = None,
    content_verdicts: list[CheckVerdict] | None = None,
    business_kind: str = "product",
) -> list[RubricScore]:
    """Convert automated site-audit results into ``RubricScore`` rows for the roadmap.

    ``content_verdicts`` are included only when passed in — the Cat 3/4 judge stays
    out of the roadmap until it's calibrated (plan §7).

    ``business_kind`` selects the Cat 6 offsite checks (W4.3); it defaults to
    ``"product"``, so every existing consumer caller is unchanged.
    """
    scores = _checks_to_scores(subject, checks)
    scores.extend(_offsite_to_scores(subject, offsite or [], business_kind))
    scores.extend(_content_to_scores(subject, content_verdicts or []))
    return scores


def build_site_audit_roadmap(
    subject: str,
    checks: list[SiteCheckRow],
    offsite: list[OffsiteFinding] | None = None,
    content_verdicts: list[CheckVerdict] | None = None,
    query_weights: dict[str, float] | None = None,
    business_kind: str = "product",
) -> list[RoadmapItem]:
    """Synthesize scores → the prioritized, sequenced :class:`RoadmapItem` list."""
    scores = site_audit_to_rubric_scores(subject, checks, offsite, content_verdicts, business_kind)
    return build_roadmap(scores, subject=subject, query_weights=query_weights)


def render_site_audit_roadmap(
    brand: str,
    checks: list[SiteCheckRow],
    offsite: list[OffsiteFinding] | None = None,
    content_verdicts: list[CheckVerdict] | None = None,
    query_weights: dict[str, float] | None = None,
    business_kind: str = "product",
) -> str:
    """Synthesize scores and render the §4 rollup + §5 prioritized roadmap markdown."""
    scores = site_audit_to_rubric_scores(brand, checks, offsite, content_verdicts, business_kind)
    return render_roadmap(scores, brand=brand, subject=brand, query_weights=query_weights)
