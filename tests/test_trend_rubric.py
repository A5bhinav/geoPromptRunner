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
    before = [_qr("q1", "openai", "Salesforce wins."), _qr("q2", "openai", "Acme is good.")]
    after = [_qr("q1", "openai", "Acme is great."), _qr("q2", "openai", "Salesforce now.")]
    cmp = compare_runs(before, after, "Acme", ["Salesforce"])
    assert cmp.queries_won == [("q1", "openai")]
    assert cmp.queries_lost == [("q2", "openai")]
    # mention rate unchanged (1 of 2 before and after), delta 0.
    assert cmp.mention_rate_delta == 0.0


def _score(category: str, check: str, status: str, weight: float = 1.0) -> RubricScore:
    return RubricScore(
        subject="Acme", category=category, check_name=check, status=status, weight=weight, note=""
    )


def test_build_roadmap_drops_passes_and_sequences_by_phase() -> None:
    scores = [
        _score(RubricCategory.OFFSITE_AUTHORITY.value, "G2 reviews", CheckStatus.FAIL.value, 1.0),
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
    assert roadmap[0].impact_label == "High"  # 1.0 severity * 1.5 weight = 1.5
