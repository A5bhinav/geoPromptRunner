from __future__ import annotations

from src.pipeline.calibration import compare
from src.pipeline.judge import AccuracyFlag, AnswerJudgment, BrandJudgment
from src.pipeline.judge_metrics import (
    DEFAULT_GRADE_POLICY,
    collect_accuracy_flags,
    grade_penalty_flags,
    leaderboard,
    losing_cells,
    mention_rate,
    visibility_grade,
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


def test_visibility_grade_rewards_prominence() -> None:
    # YNAB is recommended_first / mid_pack -> high visibility -> top grade.
    strong = visibility_grade(_judgments(), "YNAB")
    # Centsible is absent / buried -> low visibility -> low grade.
    weak = visibility_grade(_judgments(), "Centsible")
    assert strong.score > weak.score
    assert strong.letter == "A"
    assert weak.letter in {"C", "D", "F"}


def test_visibility_grade_penalized_by_accuracy_flags() -> None:
    flag = AccuracyFlag("wrong_pricing", "$20/mo", "free", "high")
    clean = [_aj("q1", "openai", [_bj("Centsible", True, "recommended_first")])]
    flagged = [_aj("q1", "openai", [_bj("Centsible", True, "recommended_first")], [flag])]
    # Same visibility, but the high-severity flag drags the graded score down.
    assert visibility_grade(flagged, "Centsible").score < visibility_grade(clean, "Centsible").score
    assert visibility_grade(flagged, "Centsible").n_flags == 1


def test_collect_accuracy_flags_dedupes() -> None:
    f = AccuracyFlag("wrong_pricing", "$20/mo", "free + $5/mo", "high")
    js = [
        _aj("q1", "openai", [_bj("Centsible", True, "buried")], [f]),
        _aj("q1", "anthropic", [_bj("Centsible", True, "buried")], [f]),  # same flag, deduped
    ]
    assert len(collect_accuracy_flags(js)) == 1


def test_grade_dedupes_repeated_error_within_answer() -> None:
    # One answer flags the SAME error type twice (different claim text, as an
    # over-flagging judge does). It must count once toward the grade penalty —
    # repetition of one mistake cannot compound the score — and keep the worst
    # severity. (collect_accuracy_flags still lists both for display.)
    f_hi = AccuracyFlag("stale", "Ring 4 is the newest", "Ring 5 is current", "high")
    f_lo = AccuracyFlag("stale", "compare Ring 4 vs RingConn", "Ring 5 is current", "low")
    twice = [_aj("q1", "gemini", [_bj("Centsible", True, "recommended_first")], [f_hi, f_lo])]
    once = [_aj("q1", "gemini", [_bj("Centsible", True, "recommended_first")], [f_hi])]

    assert len(grade_penalty_flags(twice)) == 1  # collapsed to one stale problem
    assert len(collect_accuracy_flags(twice)) == 2  # but both still shown in the report
    g_twice, g_once = visibility_grade(twice, "Centsible"), visibility_grade(once, "Centsible")
    assert g_twice.n_flags == 1
    assert g_twice.score == g_once.score  # repetition did not compound the penalty
    assert g_twice.accuracy_penalty == DEFAULT_GRADE_POLICY.penalty["high"]  # worst severity kept


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
