"""The grade formula, in its dev-only home.

TR-T0 moved `grade_from` / `GradePolicy` / `grade_penalty_flags` out of
`judge_metrics` and into the calibration harness, which is the only sanctioned
caller. These tests live here for the same reason the code does: the formula is
a research instrument for "can a human gut-grade be reproduced from our
numbers", not a thing the report renders.
"""

from __future__ import annotations

from src.pipeline.grade_calibration import (
    DEFAULT_GRADE_POLICY,
    GradeSituation,
    fit_grade_policy,
    grade_from,
    grade_penalty_flags,
    render_grade_calibration,
    score_policy,
)
from src.pipeline.judge import AccuracyFlag, AnswerJudgment, BrandJudgment


def test_grade_from_floors_at_zero_and_bands() -> None:
    # No flags: visibility maps straight to a band.
    assert grade_from(0.78, []).letter == "A"
    assert grade_from(0.55, []).letter == "B"
    # High-severity flags drive a leading score down; floored at 0 (F).
    g = grade_from(0.55, ["high"] * 5)
    assert g.score == 0.0 and g.letter == "F"


def test_score_policy_counts_exact_and_within_one() -> None:
    sits = [
        GradeSituation("clean", 0.78, [], "A"),  # default → A (exact)
        GradeSituation("absent", 0.03, [], "F"),  # default → F (exact)
        GradeSituation("leader-inaccurate", 0.55, ["high", "high", "high"], "C"),  # default → F
    ]
    fit = score_policy(DEFAULT_GRADE_POLICY, sits)
    assert fit.n == 3
    assert fit.exact == 2  # clean + absent
    # leader-inaccurate (human C) → default predicts F; C=2, F=4 is 2 apart, not within one.
    assert fit.within_one == 2


def test_fit_improves_or_matches_default() -> None:
    # Human consistently grades a leading-but-flagged brand more leniently than v1.
    sits = [
        GradeSituation("clean", 0.78, [], "A"),
        GradeSituation("leader-flags", 0.55, ["high", "high", "med"], "C"),
        GradeSituation("mid-flags", 0.45, ["high", "high"], "C"),
        GradeSituation("absent", 0.03, [], "F"),
    ]
    baseline = score_policy(DEFAULT_GRADE_POLICY, sits)
    fitted, fit = fit_grade_policy(sits)
    # The fit can only match or beat the default's exact-agreement.
    assert fit.exact >= baseline.exact
    # And it stays a valid policy that renders.
    assert "Grade-Formula Calibration" in render_grade_calibration(fitted, fit, baseline)


def test_fit_prefers_default_when_default_is_perfect() -> None:
    # If the v1 default already reproduces every grade, the fit shouldn't drift.
    sits = [
        GradeSituation("a", 0.80, [], "A"),
        GradeSituation("f", 0.02, [], "F"),
    ]
    fitted, fit = fit_grade_policy(sits)
    assert fit.exact == fit.n
    assert fitted.bands == DEFAULT_GRADE_POLICY.bands  # tie-break kept defaults


# --- the flag dedup that keeps an over-flagging judge from compounding a penalty


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


def test_grade_dedupes_repeated_error_within_answer() -> None:
    # One answer flags the SAME error type twice (different claim text, as an
    # over-flagging judge does). It must count once toward the penalty —
    # repetition of one mistake cannot compound it — keeping the worst severity.
    f_hi = AccuracyFlag("stale", "Ring 4 is the newest", "Ring 5 is current", "high")
    f_lo = AccuracyFlag("stale", "compare Ring 4 vs RingConn", "Ring 5 is current", "low")
    brand = [BrandJudgment(brand="Centsible", present=True, prominence="recommended_first",
                           framing="neutral")]
    twice = [_aj("q1", "gemini", brand, [f_hi, f_lo])]
    once = [_aj("q1", "gemini", brand, [f_hi])]

    assert len(grade_penalty_flags(twice)) == 1  # collapsed to one stale problem

    g_twice = grade_from(0.6, [f.severity for f in grade_penalty_flags(twice)])
    g_once = grade_from(0.6, [f.severity for f in grade_penalty_flags(once)])
    assert g_twice.n_flags == 1
    assert g_twice.score == g_once.score  # repetition did not compound the penalty
    assert g_twice.accuracy_penalty == DEFAULT_GRADE_POLICY.penalty["high"]


def test_grade_penalty_ignores_unassessed_answers() -> None:
    unassessed = AnswerJudgment(
        query_id="q1",
        engine_name="openai",
        intent="category",
        run_index=0,
        assessed=False,
        brands=[],
        accuracy_flags=[AccuracyFlag("stale", "old", "new", "high")],
    )
    assert grade_penalty_flags([unassessed]) == []


def test_accuracy_flags_drag_a_leading_score_down() -> None:
    assert grade_from(0.55, ["high"] * 5).score == 0.0
    assert grade_from(0.55, []).score == 0.55
