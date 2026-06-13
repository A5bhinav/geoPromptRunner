from __future__ import annotations

from src.pipeline.grade_calibration import (
    GradeSituation,
    fit_grade_policy,
    render_grade_calibration,
    score_policy,
)
from src.pipeline.judge_metrics import DEFAULT_GRADE_POLICY, grade_from


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
