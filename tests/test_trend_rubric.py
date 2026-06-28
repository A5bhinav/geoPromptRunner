from __future__ import annotations

from src.audit.rubric import CheckStatus, RubricCategory, build_roadmap
from src.pipeline.trend import compare_runs
from src.storage.models import QueryResult, RubricScore


def _qr(qid: str, eng: str, resp: str | None) -> QueryResult:
    return QueryResult(
        query_id=qid,
        intent="category",
        prompt="(mock)",
        engine_name=eng,
        run_index=0,
        response=resp,
        citations=[],
        timestamp="t",
    )


def test_compare_runs_detects_won_and_lost() -> None:
    before = [_qr("q1", "openai", "YNAB wins."), _qr("q2", "openai", "Acme is good.")]
    after = [_qr("q1", "openai", "Acme is great."), _qr("q2", "openai", "YNAB now.")]
    cmp = compare_runs(before, after, "Acme", ["YNAB"])
    assert cmp.queries_won == [("q1", "openai")]
    assert cmp.queries_lost == [("q2", "openai")]
    # mention rate unchanged (1 of 2 before and after), delta 0.
    assert cmp.mention_rate_delta == 0.0


def _score(
    category: str, check: str, status: str, weight: float = 1.0, query_ids: list[str] | None = None
) -> RubricScore:
    return RubricScore(
        subject="Acme",
        category=category,
        check_name=check,
        status=status,
        weight=weight,
        note="",
        query_ids=query_ids or [],
    )


def test_build_roadmap_drops_passes_and_sequences_by_phase() -> None:
    scores = [
        _score(
            RubricCategory.OFFSITE_AUTHORITY.value,
            "Trustpilot reviews",
            CheckStatus.FAIL.value,
            1.0,
        ),
        _score(RubricCategory.TECHNICAL_ACCESSIBILITY.value, "WAF", CheckStatus.FAIL.value, 1.5),
        _score(RubricCategory.STRUCTURED_DATA.value, "schema", CheckStatus.PASS.value, 1.0),
    ]
    roadmap = build_roadmap(scores)
    # Passing check excluded.
    assert all(item.status != "pass" for item in roadmap)
    assert len(roadmap) == 2
    # Accessibility (phase 1) sequenced before off-site (phase 3).
    assert roadmap[0].phase == 1
    assert roadmap[0].category == RubricCategory.TECHNICAL_ACCESSIBILITY.value
    # WAF: weight 1.5 * severity 1.0 * fixability(low=1.0) = 1.5 -> High.
    assert roadmap[0].impact_label == "High"


def test_build_roadmap_uses_query_weights_when_linked() -> None:
    # Same check, but linked to two high-value queries -> impact uses their weights.
    scores = [
        _score(
            RubricCategory.CONTENT_SUBSTANCE.value,
            "comparison pages",
            CheckStatus.FAIL.value,
            weight=1.0,
            query_ids=["q1", "q2"],
        )
    ]
    roadmap = build_roadmap(scores, query_weights={"q1": 2.0, "q2": 3.0})
    item = roadmap[0]
    assert item.queries_touched == 2
    # touched_value 5.0 * severity 1.0 * fixability(high=0.3) = 1.5 -> High.
    assert item.impact_label == "High"
    assert round(item.impact, 2) == 1.5
