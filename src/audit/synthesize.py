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
from src.audit.offsite.models import FindingType, OffsiteFinding
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
    "internal_linking": (
        RubricCategory.CONTENT_COVERAGE,
        "internal linking establishes topical authority",
        1.5,
    ),
    "schema_valid": (
        RubricCategory.STRUCTURED_DATA,
        "schema.org markup present and valid",
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


def _offsite_to_scores(subject: str, findings: list[OffsiteFinding]) -> list[RubricScore]:
    scores: list[RubricScore] = []
    for finding in findings:
        mapped = _offsite_score(finding)
        if mapped is None:
            continue
        check_name, status, weight = mapped
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
    if finding.finding_type is FindingType.ENTITY_CONSISTENCY:
        return ("entity consistent across the web", "pass", 1.5)
    if finding.finding_type is FindingType.COMMUNITY:
        return ("presence on Reddit / consumer forums", "pass", 2.0)
    if finding.finding_type is FindingType.LISTICLE:
        return ("named in 'best [category]' listicles / roundups", "pass", 1.5)
    if finding.finding_type is FindingType.PRESS:
        return ("third-party citations / press", "pass", 1.0)
    return None  # BACKLINKS et al. — informational, not a roadmap gap


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
) -> list[RubricScore]:
    """Convert automated site-audit results into ``RubricScore`` rows for the roadmap.

    ``content_verdicts`` are included only when passed in — the Cat 3/4 judge stays
    out of the roadmap until it's calibrated (plan §7).
    """
    scores = _checks_to_scores(subject, checks)
    scores.extend(_offsite_to_scores(subject, offsite or []))
    scores.extend(_content_to_scores(subject, content_verdicts or []))
    return scores


def build_site_audit_roadmap(
    subject: str,
    checks: list[SiteCheckRow],
    offsite: list[OffsiteFinding] | None = None,
    content_verdicts: list[CheckVerdict] | None = None,
    query_weights: dict[str, float] | None = None,
) -> list[RoadmapItem]:
    """Synthesize scores → the prioritized, sequenced :class:`RoadmapItem` list."""
    scores = site_audit_to_rubric_scores(subject, checks, offsite, content_verdicts)
    return build_roadmap(scores, subject=subject, query_weights=query_weights)


def render_site_audit_roadmap(
    brand: str,
    checks: list[SiteCheckRow],
    offsite: list[OffsiteFinding] | None = None,
    content_verdicts: list[CheckVerdict] | None = None,
    query_weights: dict[str, float] | None = None,
) -> str:
    """Synthesize scores and render the §4 rollup + §5 prioritized roadmap markdown."""
    scores = site_audit_to_rubric_scores(brand, checks, offsite, content_verdicts)
    return render_roadmap(scores, brand=brand, subject=brand, query_weights=query_weights)
