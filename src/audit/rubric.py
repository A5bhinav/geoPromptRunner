from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from src.storage.models import RubricScore

__all__ = [
    "CheckStatus",
    "RubricCategory",
    "DEFAULT_CHECKLIST",
    "RoadmapItem",
    "load_rubric_scores",
    "build_roadmap",
    "render_roadmap",
]


class CheckStatus(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class RubricCategory(StrEnum):
    TECHNICAL_ACCESSIBILITY = "technical_accessibility"
    CONTENT_COVERAGE = "content_coverage"
    CONTENT_STRUCTURE = "content_structure"
    CONTENT_SUBSTANCE = "content_substance"  # E-E-A-T
    STRUCTURED_DATA = "structured_data"
    OFFSITE_AUTHORITY = "offsite_authority"
    BASELINE_MEASUREMENT = "baseline_measurement"


# Representative checks per category (from the 7-category rubric) — the scorecard
# a human fills. Not exhaustive; enough to drive a roadmap.
DEFAULT_CHECKLIST: dict[RubricCategory, tuple[str, ...]] = {
    RubricCategory.TECHNICAL_ACCESSIBILITY: (
        "robots.txt allows AI crawlers",
        "not blocked at CDN/WAF",
        "core content server-rendered",
        "llms.txt present",
        "sitemap present and current",
        "target content not gated",
    ),
    RubricCategory.CONTENT_COVERAGE: (
        "topic clusters map consumer question space",
        "internal linking establishes topical authority",
    ),
    RubricCategory.CONTENT_STRUCTURE: (
        "answer-first direct answers",
        "headings written as consumer questions",
        "scannable formatting (lists/tables)",
    ),
    RubricCategory.CONTENT_SUBSTANCE: (
        "fact density / statistics",
        "citations to authoritative sources",
        "named authors with bios",
        "comparison content (X vs Y, alternatives)",
    ),
    RubricCategory.STRUCTURED_DATA: (
        "schema.org markup present and valid",
        "relevant types (Organization/Product/FAQ)",
    ),
    RubricCategory.OFFSITE_AUTHORITY: (
        # B2C consumer channels (Berkeley/SV consumer-startup niche): the sources
        # that actually drive AI answers for consumer brands.
        "entity consistent across the web",
        "presence on Reddit / consumer forums",
        "App Store / Play Store ratings & reviews",
        "YouTube / TikTok / influencer coverage",
        "reviews on Trustpilot",
        "named in 'best [category] app' listicles / roundups",
    ),
    RubricCategory.BASELINE_MEASUREMENT: (
        "consumer-query set built for category",
        "mention/citation rate recorded across engines",
    ),
}

# Sequencing: accessibility before content before off-site (Step 6).
_PHASE: dict[RubricCategory, int] = {
    RubricCategory.TECHNICAL_ACCESSIBILITY: 1,
    RubricCategory.CONTENT_COVERAGE: 2,
    RubricCategory.CONTENT_STRUCTURE: 2,
    RubricCategory.CONTENT_SUBSTANCE: 2,
    RubricCategory.STRUCTURED_DATA: 2,
    RubricCategory.OFFSITE_AUTHORITY: 3,
    RubricCategory.BASELINE_MEASUREMENT: 4,
}
_PHASE_LABEL = {1: "Accessibility", 2: "Content", 3: "Off-site authority", 4: "Measurement"}

# Rough default effort per category (analyst can override per item later).
_EFFORT: dict[RubricCategory, str] = {
    RubricCategory.TECHNICAL_ACCESSIBILITY: "low",
    RubricCategory.CONTENT_COVERAGE: "high",
    RubricCategory.CONTENT_STRUCTURE: "medium",
    RubricCategory.CONTENT_SUBSTANCE: "high",
    RubricCategory.STRUCTURED_DATA: "low",
    RubricCategory.OFFSITE_AUTHORITY: "high",
    RubricCategory.BASELINE_MEASUREMENT: "low",
}

_SEVERITY = {CheckStatus.FAIL: 1.0, CheckStatus.PARTIAL: 0.5, CheckStatus.PASS: 0.0}

# Fixability is the inverse of effort — easy fixes are higher-leverage (Step 6).
_FIXABILITY = {"low": 1.0, "medium": 0.6, "high": 0.3}


@dataclass(frozen=True)
class RoadmapItem:
    """A prioritized gap: a non-passing rubric check, scored and sequenced.

    impact = queries_touched_value x severity x fixability (Step-6 formula),
    where queries_touched_value sums the commercial-value weights of the queries
    the gap touches (falls back to the check's own weight when no queries are
    linked).
    """

    category: str
    check_name: str
    status: str
    impact: float
    impact_label: str
    effort: str
    phase: int
    queries_touched: int
    note: str


def load_rubric_scores(path: str | Path) -> list[RubricScore]:
    """Load human rubric scores from JSON, validating category/status values."""
    raw = json.loads(Path(path).read_text())
    scores: list[RubricScore] = []
    for item in raw["scores"]:
        category = RubricCategory(item["category"])  # raises ValueError if invalid
        status = CheckStatus(item["status"])  # raises ValueError if invalid
        scores.append(
            RubricScore(
                subject=str(item.get("subject", raw.get("subject", ""))),
                category=category.value,
                check_name=str(item["check_name"]),
                status=status.value,
                weight=float(item.get("weight", 1)),
                note=str(item.get("note", "")),
                query_ids=[str(q) for q in item.get("query_ids", [])],
            )
        )
    return scores


def _impact_label(impact: float) -> str:
    if impact >= 1.0:
        return "High"
    if impact >= 0.4:
        return "Medium"
    return "Low"


def build_roadmap(
    scores: list[RubricScore],
    subject: str | None = None,
    query_weights: dict[str, float] | None = None,
) -> list[RoadmapItem]:
    """Turn non-passing rubric checks into a prioritized, sequenced roadmap.

    Step-6 impact = queries_touched_value x severity x fixability, where
    queries_touched_value sums the commercial-value weights (``query_weights``)
    of the queries each gap is linked to (falls back to the check's own weight
    when no queries are linked). Sequenced accessibility -> content -> off-site,
    then by impact within a phase. Passing checks aren't gaps.
    """
    query_weights = query_weights or {}
    items: list[RoadmapItem] = []
    for s in scores:
        if subject is not None and s["subject"] != subject:
            continue
        status = CheckStatus(s["status"])
        severity = _SEVERITY[status]
        if severity == 0.0:
            continue
        category = RubricCategory(s["category"])
        effort = _EFFORT[category]
        linked = s["query_ids"]
        touched_value = (
            sum(query_weights.get(qid, 1.0) for qid in linked) if linked else s["weight"]
        )
        impact = touched_value * severity * _FIXABILITY[effort]
        items.append(
            RoadmapItem(
                category=category.value,
                check_name=s["check_name"],
                status=status.value,
                impact=impact,
                impact_label=_impact_label(impact),
                effort=effort,
                phase=_PHASE[category],
                queries_touched=len(linked),
                note=s["note"],
            )
        )
    return sorted(items, key=lambda i: (i.phase, -i.impact, i.category))


def render_roadmap(
    scores: list[RubricScore],
    brand: str,
    subject: str | None = None,
    query_weights: dict[str, float] | None = None,
) -> str:
    """Render report §4 (category rollup) and §5 (prioritized roadmap)."""
    subj_scores = [s for s in scores if subject is None or s["subject"] == subject]
    lines: list[str] = [f"# Diagnosis & Roadmap — {brand}", ""]

    # §4 — category rollup
    lines.append("## §4 Rubric Rollup")
    lines.append("")
    lines.append("| Category | Pass | Partial | Fail |")
    lines.append("| --- | --- | --- | --- |")
    by_cat: dict[str, Counter[str]] = {}
    for s in subj_scores:
        by_cat.setdefault(s["category"], Counter())[s["status"]] += 1
    for category in RubricCategory:
        tally = by_cat.get(category.value, Counter())
        lines.append(
            f"| {category.value} | {tally.get('pass', 0)} | "
            f"{tally.get('partial', 0)} | {tally.get('fail', 0)} |"
        )
    lines.append("")

    # §5 — prioritized roadmap
    lines.append("## §5 Prioritized Roadmap")
    lines.append("")
    roadmap = build_roadmap(subj_scores, subject, query_weights)
    if not roadmap:
        lines.append("_No gaps — every scored check passes._")
        return "\n".join(lines) + "\n"
    current_phase = 0
    for item in roadmap:
        if item.phase != current_phase:
            current_phase = item.phase
            lines.append(f"### Phase {item.phase} — {_PHASE_LABEL[item.phase]}")
            lines.append("")
            lines.append("| Gap | Status | Impact | Effort | Queries touched |")
            lines.append("| --- | --- | --- | --- | --- |")
        lines.append(
            f"| {item.check_name} | {item.status} | {item.impact_label} | "
            f"{item.effort} | {item.queries_touched} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sample = Path(__file__).resolve().parents[2] / "data" / "sample_rubric.json"
    scores = load_rubric_scores(sample)
    print(render_roadmap(scores, brand="Acme"))
