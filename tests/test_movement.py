"""Which changes are news (audit-packaging P2-T4).

The failure this prevents is a weekly report that headlines noise. It destroys
credibility faster than reporting nothing, and at 3 runs x 6 surfaces most
week-over-week movement IS noise.
"""

from __future__ import annotations

from src.pipeline.movement import (
    PRACTICAL_FLOOR_PP,
    Direction,
    Movement,
    compare_cell,
    gate_movements,
)


def _m(before: int, before_n: int, after: int, after_n: int, k: str = "ChatGPT") -> Movement:
    return compare_cell(k, before, before_n, after, after_n, runs_per_query=3)


# --- the spec's explicit acceptance criterion ---------------------------------


def test_a_big_swing_at_small_n_is_not_news() -> None:
    """12% -> 50% is the move a weekly report is most tempted to headline."""
    assert _m(1, 12, 6, 12).direction == Direction.FLAT.value


def test_the_same_swing_at_large_n_is_news() -> None:
    assert _m(29, 240, 120, 240).direction == Direction.UP.value


def test_only_the_denominator_separates_them() -> None:
    """IDENTICAL rates on both sides, opposite verdicts. The point of gating."""
    small, large = _m(1, 12, 6, 12), _m(20, 240, 120, 240)
    assert small.delta_pp == large.delta_pp, "the fixture must hold the rates equal"
    assert small.direction == Direction.FLAT.value
    assert large.direction == Direction.UP.value


# --- both gates -------------------------------------------------------------


def test_a_statistically_real_but_trivial_move_is_still_flat() -> None:
    """The second gate. A 2pp shift on a huge sample is real and not worth a page."""
    movement = compare_cell("ChatGPT", 1180, 2400, 1220, 2400, runs_per_query=1)
    assert abs(movement.delta_pp) < PRACTICAL_FLOOR_PP
    assert movement.direction == Direction.FLAT.value
    assert "reporting floor" in movement.flat_reason or "includes zero" in movement.flat_reason


def test_direction_follows_the_sign() -> None:
    assert _m(120, 240, 29, 240).direction == Direction.DOWN.value


# --- flat is a claim, not a blank --------------------------------------------


def test_a_flat_cell_states_what_it_held_steady_at() -> None:
    phrase = _m(6, 12, 6, 12).phrase()
    assert "held steady at 6 of 12 runs" in phrase
    assert phrase.strip() != ""


def test_every_flat_cell_explains_itself() -> None:
    """A reader who asks "why isn't this news" gets an answer, not a shrug."""
    movement = _m(1, 12, 6, 12)
    assert movement.flat_reason
    assert "includes zero" in movement.flat_reason


def test_no_data_is_distinct_from_flat() -> None:
    """ "Nothing moved" and "we could not tell" are different claims."""
    unknown = _m(0, 0, 6, 12)
    assert unknown.direction == Direction.UNKNOWN.value
    assert "not enough data" in unknown.phrase()
    assert unknown.direction != Direction.FLAT.value


def test_a_phrase_never_shows_a_bare_percentage() -> None:
    for movement in (_m(6, 12, 6, 12), _m(29, 240, 120, 240), _m(0, 0, 1, 3)):
        assert "%" not in movement.phrase()


# --- multiple comparisons ----------------------------------------------------


def test_the_fdr_correction_demotes_the_weakest_of_many_tests() -> None:
    """~20 tests per report means one gets lucky. BH is what catches it.

    The FLAT cells are load-bearing in this fixture, not padding. The family BH
    corrects over is every comparison PERFORMED — filter to the ones that already
    looked significant and every candidate has p <= 0.05, the step-up finds
    k = m, and the correction rejects all of them. That inert version passed a
    weaker version of this test.
    """
    strong = [_m(29, 240, 120, 240, k=f"strong-{i}") for i in range(2)]
    marginal = [_m(48, 240, 77, 240, k=f"marginal-{i}") for i in range(18)]
    flat = [_m(6, 12, 6, 12, k=f"flat-{i}") for i in range(5)]
    assert all(m.is_significant for m in marginal), "fixture must pass the per-cell gates"

    gated = gate_movements(strong + marginal + flat)
    survivors = {m.key for m in gated if m.is_significant}
    assert survivors == {"strong-0", "strong-1"}, "only the clear moves may survive"
    demoted = [m for m in gated if m.key.startswith("marginal")]
    assert all(not m.is_significant for m in demoted)
    assert all("comparisons in this report" in m.flat_reason for m in demoted)


def test_correcting_over_only_the_significant_cells_would_be_inert() -> None:
    """Pins the failure mode directly, so it cannot quietly come back.

    With ONLY the significant cells in the family every p is <= the FDR, so BH's
    step-up reaches k = m and demotes nothing. The flat cells are what give the
    correction something to correct against.
    """
    strong = [_m(29, 240, 120, 240, k=f"strong-{i}") for i in range(2)]
    marginal = [_m(48, 240, 77, 240, k=f"marginal-{i}") for i in range(18)]

    without_flat = gate_movements(strong + marginal)
    with_flat = gate_movements(
        strong + marginal + [_m(6, 12, 6, 12, k=f"flat-{i}") for i in range(5)]
    )

    assert sum(m.is_significant for m in without_flat) == 20, "the inert case"
    assert sum(m.is_significant for m in with_flat) == 2, "the corrected case"


def test_gating_preserves_order_and_length() -> None:
    movements = [_m(6, 12, 6, 12, k=f"e{i}") for i in range(5)]
    gated = gate_movements(movements)
    assert [m.key for m in gated] == [m.key for m in movements]


def test_gating_a_set_with_nothing_significant_changes_nothing() -> None:
    movements = [_m(6, 12, 6, 12, k=f"e{i}") for i in range(3)]
    assert gate_movements(movements) == movements


def test_gating_an_empty_set_is_not_an_error() -> None:
    assert gate_movements([]) == []
