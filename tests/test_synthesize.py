from __future__ import annotations

from src.api.reports import SiteCheckRow
from src.audit.checks.content_judge import CheckVerdict, ContentClass
from src.audit.offsite.models import Confidence, FindingType, OffsiteFinding
from src.audit.synthesize import (
    build_site_audit_roadmap,
    site_audit_to_rubric_scores,
)


def _check(key: str, status: str, page: str = "https://x.com/") -> SiteCheckRow:
    cat = {"ssr_rendering": 1, "internal_linking": 2, "schema_valid": 5}[key]
    return SiteCheckRow(check_key=key, category=cat, page_url=page, status=status, detail="")


def _by_check(scores: list) -> dict[str, str]:
    return {s["check_name"]: s["status"] for s in scores}


# --- deterministic check rollup ----------------------------------------------


def test_check_rollup_fail_beats_partial_beats_pass() -> None:
    checks = [
        _check("ssr_rendering", "pass", "https://x.com/a"),
        _check("ssr_rendering", "fail", "https://x.com/b"),  # any fail -> fail
        _check("schema_valid", "partial", "https://x.com/a"),
        _check("schema_valid", "pass", "https://x.com/b"),  # partial wins over pass
    ]
    scores = site_audit_to_rubric_scores("Acme", checks)
    by_name = _by_check(scores)
    assert by_name["core content server-rendered (AI-crawler visible)"] == "fail"
    assert by_name["schema.org markup present and valid"] == "partial"


def test_all_ungradeable_check_is_dropped() -> None:
    checks = [_check("internal_linking", "ungradeable", "")]
    assert site_audit_to_rubric_scores("Acme", checks) == []


def test_ssr_carries_highest_weight() -> None:
    scores = site_audit_to_rubric_scores("Acme", [_check("ssr_rendering", "fail")])
    assert scores[0]["weight"] == 3.0
    assert scores[0]["category"] == "technical_accessibility"


# --- offsite mapping ---------------------------------------------------------


def _finding(ftype: FindingType, payload: dict) -> OffsiteFinding:
    return OffsiteFinding(ftype, "t", None, Confidence.HIGH, payload)


def test_offsite_wikidata_found_vs_not_found() -> None:
    found = site_audit_to_rubric_scores(
        "Acme", [], offsite=[_finding(FindingType.WIKIDATA, {"found": True})]
    )
    missing = site_audit_to_rubric_scores(
        "Acme", [], offsite=[_finding(FindingType.WIKIDATA, {"found": False})]
    )
    assert found[0]["status"] == "pass"
    assert missing[0]["status"] == "fail"
    assert found[0]["category"] == "offsite_authority"


def test_offsite_reviews_status_from_platform_count() -> None:
    def reviews(present: int, total: int) -> OffsiteFinding:
        platforms = {f"h{i}": {"present": i < present} for i in range(total)}
        return _finding(FindingType.REVIEWS, {"platforms": platforms})

    assert site_audit_to_rubric_scores("A", [], offsite=[reviews(0, 4)])[0]["status"] == "fail"
    assert site_audit_to_rubric_scores("A", [], offsite=[reviews(1, 4)])[0]["status"] == "partial"
    assert site_audit_to_rubric_scores("A", [], offsite=[reviews(3, 4)])[0]["status"] == "pass"


def test_offsite_backlinks_skipped() -> None:
    scores = site_audit_to_rubric_scores(
        "A", [], offsite=[_finding(FindingType.BACKLINKS, {"referring_domains": 99})]
    )
    assert scores == []  # informational, not a roadmap gap


def test_offsite_community_is_present_signal() -> None:
    scores = site_audit_to_rubric_scores("A", [], offsite=[_finding(FindingType.COMMUNITY, {})])
    assert scores[0]["status"] == "pass"
    assert scores[0]["check_name"] == "presence on Reddit / consumer forums"


# --- content-judge verdicts (only when supplied) -----------------------------


def test_content_verdicts_map_and_skip_unknown() -> None:
    verdicts = [
        CheckVerdict("answer_first_lead", 3, ContentClass.FAIL, "r", [], False),
        CheckVerdict("original_data", 4, ContentClass.PARTIAL, "r", [], False),
        CheckVerdict("expert_commentary", 4, ContentClass.UNKNOWN, "r", [], True),  # skipped
    ]
    scores = site_audit_to_rubric_scores("A", [], content_verdicts=verdicts)
    cats = {s["check_name"]: s["category"] for s in scores}
    assert cats["answer first lead"] == "content_structure"
    assert cats["original data"] == "content_substance"
    assert "expert commentary" not in cats  # unknown dropped
    assert len(scores) == 2


# --- roadmap synthesis (sequencing) ------------------------------------------


def test_roadmap_sequences_accessibility_first() -> None:
    checks = [_check("ssr_rendering", "fail"), _check("schema_valid", "fail")]
    offsite = [_finding(FindingType.REVIEWS, {"platforms": {"a": {"present": False}}})]
    items = build_site_audit_roadmap("Acme", checks, offsite)
    phases = [i.phase for i in items]
    assert phases == sorted(phases)  # phases non-decreasing (accessibility → content → offsite)
    assert items[0].category == "technical_accessibility"  # SSR fail leads
    # passing/dropped checks aren't gaps; only the three fails/partials appear.
    assert {i.status for i in items} <= {"fail", "partial"}
