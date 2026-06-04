from __future__ import annotations

from src.pipeline.calibration import compare
from src.pipeline.judge import AccuracyFlag, AnswerJudgment, BrandJudgment
from src.pipeline.judge_metrics import (
    collect_accuracy_flags,
    leaderboard,
    losing_cells,
    mention_rate,
    visibility_score,
)


def _bj(brand: str, present: bool, prom: str, framing: str = "neutral") -> BrandJudgment:
    return BrandJudgment(brand=brand, present=present, prominence=prom, framing=framing)


def _aj(
    qid: str, engine: str, brands: list[BrandJudgment], flags: list[AccuracyFlag] | None = None
) -> AnswerJudgment:
    return AnswerJudgment(
        query_id=qid,
        engine_name=engine,
        intent="category",
        run_index=0,
        assessed=True,
        brands=brands,
        accuracy_flags=flags or [],
    )


def _judgments() -> list[AnswerJudgment]:
    return [
        _aj(
            "q1",
            "openai",
            [_bj("YNAB", True, "recommended_first"), _bj("Centsible", False, "absent")],
        ),
        _aj("q2", "openai", [_bj("YNAB", True, "mid_pack"), _bj("Centsible", True, "buried")]),
    ]


def test_mention_and_visibility() -> None:
    js = _judgments()
    assert mention_rate(js, "YNAB") == 1.0  # present in both cells
    assert mention_rate(js, "Centsible") == 0.5  # present in 1 of 2
    # YNAB (recommended_first + mid_pack) outranks Centsible (absent + buried).
    assert visibility_score(js, "YNAB") > visibility_score(js, "Centsible")


def test_leaderboard_orders_by_visibility() -> None:
    board = leaderboard(_judgments(), ["Centsible", "YNAB"])
    assert [row[0] for row in board] == ["YNAB", "Centsible"]


def test_losing_cells_flags_client_absent_competitor_first() -> None:
    losses = losing_cells(_judgments(), client="Centsible", competitors=["YNAB"])
    # q1: Centsible absent, YNAB recommended_first -> a loss. q2: YNAB only mid_pack.
    assert [(c.query_id, c.brand) for c in losses] == [("q1", "YNAB")]


def test_collect_accuracy_flags_dedupes() -> None:
    f = AccuracyFlag("wrong_pricing", "$20/mo", "free + $5/mo", "high")
    js = [
        _aj("q1", "openai", [_bj("Centsible", True, "buried")], [f]),
        _aj("q1", "anthropic", [_bj("Centsible", True, "buried")], [f]),  # same flag, deduped
    ]
    assert len(collect_accuracy_flags(js)) == 1


def test_calibration_compare_counts_matches() -> None:
    brands = [
        _bj("Centsible", True, "buried", "negative"),
        _bj("YNAB", True, "recommended_first", "positive"),
    ]
    labels = {
        "Centsible": {
            "present": True,
            "prominence": "buried",
            "framing": "positive",
        },  # framing mismatch
        "YNAB": {"present": True, "prominence": "recommended_first", "framing": "positive"},
    }
    pm, pt, rm, rt, fm, ft = compare(brands, labels)
    assert (pm, pt) == (2, 2)  # present matches both
    assert (rm, rt) == (2, 2)  # prominence matches both
    assert (fm, ft) == (1, 2)  # framing: YNAB matches, Centsible doesn't
