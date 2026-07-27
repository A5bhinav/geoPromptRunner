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
    assert by_name["schema.org markup valid and matching visible content (hygiene)"] == "partial"


def test_llms_txt_is_note_only_never_a_roadmap_gap() -> None:
    # llms.txt is deliberately unscored (no engine consumes it) — even a hard
    # fail must not synthesize into a rubric score or roadmap item.
    row = SiteCheckRow(
        check_key="llms_txt", category=1, page_url="https://x.com/", status="fail", detail=""
    )
    assert site_audit_to_rubric_scores("Acme", [row]) == []


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


def test_offsite_presence_findings_graded_by_confidence() -> None:
    # A low/medium-confidence presence finding must NOT score a full pass, or the
    # offsite grade inflates and the gap is wrongly dropped from the roadmap.
    low = OffsiteFinding(FindingType.COMMUNITY, "one stale thread", None, Confidence.LOW, {})
    med = OffsiteFinding(FindingType.LISTICLE, "maybe listed", None, Confidence.MEDIUM, {})
    assert site_audit_to_rubric_scores("A", [], offsite=[low])[0]["status"] == "fail"
    assert site_audit_to_rubric_scores("A", [], offsite=[med])[0]["status"] == "partial"


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


# --- W4.3: local Cat 6 checks -----------------------------------------------------
# Every local check must clear the bar the llms_txt precedent sets: evidence an engine
# consumes the source, or it ships note-only. GBP and the directory layer clear it —
# local AI answers are generated FROM the GBP entity and cite Yelp/BBB/Angi by name.
# LocalBusiness SCHEMA does not, and is deliberately absent from this rubric.


def _reviews_finding(platforms: dict[str, dict[str, bool]]) -> OffsiteFinding:
    return OffsiteFinding(
        FindingType.REVIEWS,
        "directory presence",
        None,
        Confidence.MEDIUM,
        {"platforms": platforms},
    )


def test_local_gbp_is_scored_separately_and_carries_the_top_weight() -> None:
    """GBP is not just another directory: the local pack — and the AI answers built on
    it — are generated FROM the profile. No profile = structurally absent, the local
    equivalent of failing SSR, so it must not be averaged away inside a directory
    tally."""
    finding = _reviews_finding(
        {
            "google.com/maps": {"present": False},
            "yelp.com": {"present": True},
            "bbb.org": {"present": True},
        }
    )
    scores = site_audit_to_rubric_scores(
        "Acme Plumbing", [], offsite=[finding], business_kind="local_service"
    )
    by_name = {s["check_name"]: s for s in scores}

    gbp = by_name["Google Business Profile listing present"]
    assert gbp["status"] == "fail"
    assert gbp["weight"] == 3.0
    assert gbp["category"] == "offsite_authority"

    directories = by_name["listed on the local directories AI cites (Yelp, BBB, Angi)"]
    assert directories["status"] == "pass"  # 2 of 2 non-GBP present
    assert directories["weight"] == 2.5


def test_local_nap_consistency_outweighs_generic_entity_consistency() -> None:
    """An inconsistent NAP splits the entity, so no listing accumulates enough
    authority to be cited at all — a bigger deal locally than generic web entity
    consistency (1.5)."""
    finding = OffsiteFinding(
        FindingType.ENTITY_CONSISTENCY, "phone differs on Yelp", None, Confidence.LOW, {}
    )
    scores = site_audit_to_rubric_scores(
        "Acme Plumbing", [], offsite=[finding], business_kind="local_service"
    )
    (score,) = scores
    assert score["check_name"] == "name/address/phone consistent across directories (NAP)"
    assert score["status"] == "fail"  # low confidence
    assert score["weight"] == 2.5


def test_consumer_offsite_scoring_is_untouched_by_the_local_path() -> None:
    """The consumer ICP is still live: same labels, same weights, no GBP row."""
    finding = _reviews_finding({"trustpilot.com": {"present": True}})
    scores = site_audit_to_rubric_scores("Oura", [], offsite=[finding])
    (score,) = scores
    assert score["check_name"] == "reviews on Trustpilot / consumer platforms"
    assert score["weight"] == 1.5
    assert "Google Business Profile" not in str(scores)


def test_local_business_schema_is_never_a_roadmap_gap() -> None:
    """The llms_txt bar, applied to ourselves.

    A local homepage missing LocalBusiness markup is real, and it feeds the existing
    HYGIENE-framed schema_valid check — but it must NEVER become its own roadmap item.
    Controlled studies show no AI-citation lift from JSON-LD (retrieval reads visible
    HTML), so elevating it would fail the same evidence bar that keeps llms_txt
    note-only. The visible NAP block is what matters; the markup is tidy-up.
    """
    finding = _reviews_finding({"google.com/maps": {"present": True}})
    scores = site_audit_to_rubric_scores(
        "Acme Plumbing", [], offsite=[finding], business_kind="local_service"
    )
    for score in scores:
        assert "schema" not in score["check_name"].lower(), (
            f"local schema became a scored gap: {score['check_name']!r} — it must stay "
            "hygiene-only under the llms_txt evidence bar"
        )
