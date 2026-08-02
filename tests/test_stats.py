"""Confidence intervals and significance gating (audit-packaging P2-T3/T4).

Numerical code needs layered tests, because a plausible-looking wrong formula is
the failure mode. Four layers here:

1. **Golden values** hardcoded from the closed-form Wilson derivation, so the
   tests carry no runtime dependency on a reference library.
2. **Properties** — bounds ordered and inside [0,1], symmetry, width shrinking
   with n.
3. **The direction of the design correction** — it must only ever widen.
4. **The claims the report makes off these numbers** — that a 50% rate at n=12
   is not reportable as movement, and that the same swing at n=240 is.
"""

from __future__ import annotations

import pytest

from src.pipeline.stats import (
    DEFAULT_ICC,
    benjamini_hochberg,
    design_effect,
    effective_n,
    format_rate,
    icc_one_way,
    interval,
    minimum_detectable_effect,
    newcombe_diff_interval,
    wilson_interval,
)

# --- golden values ------------------------------------------------------------


def test_wilson_matches_the_closed_form_by_hand() -> None:
    """p=0.5, n=12, 95%, no continuity correction. Derived, not copied from a run."""
    lo, hi = wilson_interval(6, 12, continuity=False)
    assert lo == pytest.approx(0.25378, abs=1e-4)
    assert hi == pytest.approx(0.74622, abs=1e-4)


def test_the_number_that_motivates_the_whole_rule() -> None:
    """A 50% mention rate at n=12 has a CI of roughly 25-75%.

    This is the figure the "no rate without its denominator" rule exists for. If
    it ever narrows, either the formula broke or someone swapped in Wald.
    """
    lo, hi = wilson_interval(6, 12, continuity=False)
    assert lo < 0.30 and hi > 0.70


# --- the edge cases that are normative, not incidental ------------------------


def test_zero_n_is_full_uncertainty_and_never_zero_percent() -> None:
    """The report must say "insufficient data", not "0%" — opposite claims."""
    assert wilson_interval(0, 0) == (0.0, 1.0)
    iv = interval(0, 0)
    assert (iv.lower, iv.upper) == (0.0, 1.0)
    assert iv.is_measured is False
    assert format_rate(0, 0) == "insufficient data"


def test_zero_and_full_successes_give_non_degenerate_intervals_inside_the_unit() -> None:
    lo, hi = wilson_interval(0, 12)
    assert lo == 0.0 and 0.0 < hi < 1.0
    lo, hi = wilson_interval(12, 12)
    assert 0.0 < lo < 1.0 and hi == 1.0


def test_successes_above_n_is_an_error_not_a_clamp() -> None:
    """The bug this catches: deflating n without deflating successes."""
    with pytest.raises(ValueError):
        wilson_interval(10, 5.0)
    with pytest.raises(ValueError):
        wilson_interval(-1, 5.0)


# --- properties ---------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 3, 12, 40, 240])
@pytest.mark.parametrize("frac", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_bounds_are_ordered_and_inside_the_unit_interval(n: int, frac: float) -> None:
    successes = round(n * frac)
    lo, hi = wilson_interval(successes, n)
    assert 0.0 <= lo <= hi <= 1.0


@pytest.mark.parametrize("n", [4, 12, 40])
def test_wilson_is_symmetric_about_a_half(n: int) -> None:
    for x in range(n + 1):
        lo_a, hi_a = wilson_interval(x, n)
        lo_b, hi_b = wilson_interval(n - x, n)
        assert lo_a == pytest.approx(1 - hi_b, abs=1e-9)
        assert hi_a == pytest.approx(1 - lo_b, abs=1e-9)


def test_width_shrinks_as_n_grows_at_a_fixed_rate() -> None:
    widths = [
        wilson_interval(n // 2, n)[1] - wilson_interval(n // 2, n)[0] for n in (12, 40, 120, 400)
    ]
    assert widths == sorted(widths, reverse=True)


# --- the design effect --------------------------------------------------------


def test_deff_is_at_least_one_and_grows_with_k() -> None:
    assert design_effect(1) == 1.0
    assert design_effect(3) == pytest.approx(1 + 2 * DEFAULT_ICC)
    assert design_effect(5) > design_effect(3) > design_effect(1)


def test_the_correction_only_ever_widens() -> None:
    """A strict widening — it can never make an interval falsely narrow."""
    naive = interval(6, 12, runs_per_query=1, icc=0.0)
    corrected = interval(6, 12, runs_per_query=3)
    assert corrected.width > naive.width
    # And the point estimate is untouched: same rate, known less precisely.
    assert corrected.point == naive.point == 0.5


def test_the_point_estimate_survives_the_correction() -> None:
    """The bug that produced "50% is between 47% and 100%": scaling n alone."""
    iv = interval(6, 12, runs_per_query=3)
    assert iv.lower < 0.5 < iv.upper


def test_effective_n_deflates_by_deff() -> None:
    assert effective_n(12, 3, icc=0.68) == pytest.approx(12 / (1 + 2 * 0.68))
    assert effective_n(12, 1, icc=0.68) == 12.0


# --- ICC ----------------------------------------------------------------------


def test_icc_is_high_when_runs_of_one_prompt_agree_and_prompts_differ() -> None:
    """Perfectly consistent within prompt, totally different between: ICC -> 1."""
    groups = {"q1": [1.0, 1.0, 1.0], "q2": [0.0, 0.0, 0.0], "q3": [1.0, 1.0, 1.0]}
    assert icc_one_way(groups) > 0.9


def test_icc_is_low_when_repeat_runs_disagree_as_much_as_prompts_do() -> None:
    groups = {"q1": [1.0, 0.0, 1.0], "q2": [0.0, 1.0, 0.0], "q3": [1.0, 0.0, 1.0]}
    assert icc_one_way(groups) < 0.4


def test_icc_never_returns_negative_which_would_narrow_an_interval() -> None:
    groups = {"q1": [1.0, 0.0], "q2": [1.0, 0.0], "q3": [0.0, 1.0]}
    assert icc_one_way(groups) >= 0.0


def test_icc_falls_back_rather_than_crashing_on_too_little_data() -> None:
    assert icc_one_way({}) == DEFAULT_ICC
    assert icc_one_way({"q1": [1.0]}) == DEFAULT_ICC
    assert icc_one_way({"q1": [1.0], "q2": [0.0]}) == DEFAULT_ICC  # one run each


# --- significance: the claim the report actually makes ------------------------


def test_a_big_swing_at_small_n_is_not_news_but_the_same_swing_at_large_n_is() -> None:
    """The spec's explicit acceptance criterion.

    12% -> 50% is the kind of move a weekly report is most tempted to headline.
    At n=12 it is noise; only the denominator tells you which.
    """
    small = newcombe_diff_interval(6, 12, 1, 12, runs_per_query=3)
    assert small[0] <= 0 <= small[1], "n=12 must not earn an 'Up' label"

    large = newcombe_diff_interval(120, 240, 29, 240, runs_per_query=3)
    assert large[0] > 0, "n=240 must earn one"


def test_an_identical_pair_of_rates_is_never_significant() -> None:
    lo, hi = newcombe_diff_interval(6, 12, 6, 12, runs_per_query=3)
    assert lo <= 0 <= hi


def test_no_comparison_is_possible_without_data() -> None:
    assert newcombe_diff_interval(0, 0, 3, 12) == (-1.0, 1.0)


def test_the_difference_interval_is_not_the_overlap_heuristic() -> None:
    """Overlapping CIs can still be a significant difference — the whole point.

    Constructed so the two per-week Wilson intervals overlap while the Newcombe
    interval for the difference excludes zero. Testing overlap instead would call
    this flat and lose a real move.
    """
    a_lo, a_hi = wilson_interval(120, 240, continuity=False)
    b_lo, b_hi = wilson_interval(150, 240, continuity=False)
    assert a_hi > b_lo, "fixture invalid: the per-week intervals must overlap"
    lo, hi = newcombe_diff_interval(150, 240, 120, 240, runs_per_query=1, icc=0.0)
    assert lo > 0, "the difference is significant despite the overlap"


# --- MDE ----------------------------------------------------------------------


def test_mde_is_stricter_for_a_thin_surface_than_a_well_sampled_one() -> None:
    assert minimum_detectable_effect(5) > minimum_detectable_effect(50)
    assert minimum_detectable_effect(50) > minimum_detectable_effect(500)


def test_mde_with_no_data_demands_a_total_reversal() -> None:
    assert minimum_detectable_effect(0) == 1.0


# --- multiple comparisons -----------------------------------------------------


def test_bh_rejects_more_than_bonferroni_would_at_this_many_tests() -> None:
    p_values = [0.001, 0.008, 0.02, 0.04, 0.2, 0.5, 0.9]
    mask = benjamini_hochberg(p_values, fdr=0.05)
    bonferroni = [p <= 0.05 / len(p_values) for p in p_values]
    assert sum(mask) > sum(bonferroni)


def test_bh_rejects_everything_below_the_largest_passing_rank() -> None:
    """The step-up part: an entry that fails alone is rejected if a later one passes."""
    # 0.04 passes at rank 4 (0.05*4/4 = 0.05); 0.03 fails alone but is below it.
    mask = benjamini_hochberg([0.001, 0.03, 0.035, 0.04], fdr=0.05)
    assert mask == [True, True, True, True]


def test_bh_preserves_caller_order_and_handles_the_empty_case() -> None:
    assert benjamini_hochberg([]) == []
    assert benjamini_hochberg([0.9, 0.001], fdr=0.05) == [False, True]


# --- the house format ---------------------------------------------------------


def test_format_rate_leads_with_the_count_and_never_a_bare_percentage() -> None:
    rendered = format_rate(7, 12)
    assert rendered.startswith("7 of 12 runs")
    assert "(58%)" in rendered
    assert not rendered.startswith("58")
