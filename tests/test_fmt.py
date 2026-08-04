"""TR-T2 — percentage points for rates, percent change for counts.

The regression these guard is a category error, not a rounding bug: a rate
moving 2% → 4% reported as "+100%" is the single most common way vendors in
this category overstate movement.
"""

from __future__ import annotations

import pytest

from src.pipeline.fmt import NO_CHANGE, NO_PRIOR, fmt_count_delta, fmt_delta, fmt_pp


def test_rate_delta_is_percentage_points() -> None:
    # The spec's own example. 42% -> 48% is six points, NOT "+14%".
    assert fmt_delta(0.42, 0.48, "rate") == "+6.0 pp"
    assert fmt_delta(0.48, 0.42, "rate") == "-6.0 pp"


def test_count_delta_is_percent_change() -> None:
    assert fmt_delta(120, 150, "count") == "+25%"
    assert fmt_delta(150, 120, "count") == "-20%"


def test_a_small_rate_never_renders_as_a_huge_percent() -> None:
    """The overstatement this module exists to prevent."""
    rendered = fmt_delta(0.02, 0.04, "rate")
    assert rendered == "+2.0 pp"
    assert "%" not in rendered


def test_no_prior_cycle_is_not_zero() -> None:
    # "Nothing was measured before" and "it did not move" are different claims.
    assert fmt_delta(None, 0.48, "rate") == NO_PRIOR
    assert fmt_delta(0.48, None, "rate") == NO_PRIOR
    assert fmt_delta(None, 150, "count") == NO_PRIOR


def test_zero_move_renders_as_words_not_signed_zero() -> None:
    assert fmt_delta(0.42, 0.4201, "rate") == NO_CHANGE
    assert fmt_pp(0.0) == NO_CHANGE
    assert fmt_delta(120, 120, "count") == NO_CHANGE


def test_count_from_zero_base_has_no_percent_change() -> None:
    # (x - 0) / 0 is undefined; "+inf%" is not a number a client can act on.
    assert fmt_count_delta(0, 3) == "new"
    assert fmt_count_delta(0, 0) == NO_CHANGE


@pytest.mark.parametrize("delta_pp", [6.0, -6.0, 0.05, 100.0])
def test_pp_deltas_always_carry_a_sign_and_a_unit(delta_pp: float) -> None:
    rendered = fmt_pp(delta_pp)
    assert rendered.endswith(" pp")
    assert rendered[0] in "+-"
