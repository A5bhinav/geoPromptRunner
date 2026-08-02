"""The lifecycle state machine (audit-packaging P2-T2).

Telling a client something is fixed when an engine timed out is the worst
correctness failure this product can make, so the two guardrails get the most
tests: a failing run is not evidence, and one quiet cycle is not a fix.

**Exhaustive, not property-based.** The spec asks for Hypothesis properties.
Hypothesis is not a dependency here, and for a state machine over boolean
sequences it would be strictly weaker than what replaces it: every presence
sequence up to length 12 is 4,096 cases and runs instantly, so the invariants
below are checked over ALL of them rather than a sample. Add Hypothesis if the
state space ever stops being enumerable.
"""

from __future__ import annotations

from itertools import product

import pytest

from src.pipeline.lifecycle import (
    MIN_COVERAGE_RATIO,
    RESOLUTION_CONFIRMATION_RUNS,
    Accountability,
    CycleObservation,
    LifecycleStatus,
    RunMeta,
    accountability,
    comparable_cycles,
    compute_lifecycle,
)

THEME = "pricing_offer"


def _cycles(
    presence: str,
    *,
    coverage: float = 1.0,
    status: str = "done",
    version: str = "v1",
) -> list[CycleObservation]:
    """Build a history from a presence string: 'T' present, 'F' absent."""
    return [
        CycleObservation(
            run=RunMeta(f"run-{i}", f"2026-06-{i + 1:02d}", status, coverage, version),
            themes=frozenset({THEME}) if flag == "T" else frozenset(),
        )
        for i, flag in enumerate(presence)
    ]


def _status(presence: str) -> str:
    facts = compute_lifecycle(_cycles(presence))
    return facts[THEME].status if THEME in facts else ""


# --- the spec's table ---------------------------------------------------------


@pytest.mark.parametrize(
    ("presence", "expected"),
    [
        ("T", LifecycleStatus.NEW.value),
        ("TT", LifecycleStatus.PERSISTING.value),
        # Guardrail B: one absence is NOT a fix.
        ("TF", LifecycleStatus.PERSISTING.value),
        ("TFT", LifecycleStatus.PERSISTING.value),
        # Two consecutive absences confirm it.
        ("TFF", LifecycleStatus.RESOLVED.value),
        # ...and a return after a CONFIRMED resolve is a regression.
        ("TFFT", LifecycleStatus.REGRESSED.value),
        ("TFFTT", LifecycleStatus.PERSISTING.value),
        # A four-cycle regression needing a three-cycle look-back.
        ("TTFFT", LifecycleStatus.REGRESSED.value),
        # Never seen at all.
        ("FFF", ""),
        # Appears late — NEW on its first appearance, whenever that is.
        ("FFT", LifecycleStatus.NEW.value),
    ],
)
def test_presence_sequences(presence: str, expected: str) -> None:
    assert _status(presence) == expected


def test_the_difference_between_a_lapse_and_a_fix() -> None:
    """`TFT` and `TFFT` differ by ONE cycle and mean opposite things.

    The first never actually resolved, so its return is continuation and there is
    nothing to alarm anyone about. The second reached a confirmed fix that then
    broke. Collapsing them tells a client a fix failed when it never landed.
    """
    assert _status("TFT") == LifecycleStatus.PERSISTING.value
    assert _status("TFFT") == LifecycleStatus.REGRESSED.value


# --- guardrail A: a failing run is not evidence -------------------------------


def test_a_partial_run_can_never_produce_a_resolve() -> None:
    """Absence in a run that measured half the cells is not absence.

    Without the gate this history reads `TFF` — a confirmed fix. With it, the two
    thin runs are not evidence at all and the finding is simply still NEW, which
    is the only honest reading: nothing has been measured since.
    """
    history = [
        CycleObservation(RunMeta("full", "2026-06-01", "done", 1.0, "v1"), frozenset({THEME})),
        CycleObservation(RunMeta("thin1", "2026-06-08", "done", 0.5, "v1"), frozenset()),
        CycleObservation(RunMeta("thin2", "2026-06-15", "done", 0.5, "v1"), frozenset()),
    ]
    ungated = compute_lifecycle(history)
    assert ungated[THEME].status == LifecycleStatus.RESOLVED.value, "fixture must be a fix ungated"

    gated = comparable_cycles(history, "v1")
    assert [c.run.run_id for c in gated] == ["full"]
    assert compute_lifecycle(gated)[THEME].status == LifecycleStatus.NEW.value


def test_a_failed_run_is_skipped_entirely() -> None:
    failed = _cycles("TFF", status="failed")
    assert comparable_cycles(failed, "v1") == []


def test_a_different_query_set_is_not_a_comparable_cycle() -> None:
    """Only compare like instruments — a different set measured a different thing."""
    other = _cycles("TT", version="v2")
    assert comparable_cycles(other, "v1") == []


def test_the_coverage_gate_is_at_the_documented_floor() -> None:
    assert MIN_COVERAGE_RATIO == 0.95
    assert RunMeta("r", "d", "done", 0.95, "v1").is_evidence
    assert not RunMeta("r", "d", "done", 0.94, "v1").is_evidence
    assert not RunMeta("r", "d", "running", 1.0, "v1").is_evidence


def test_a_broken_run_between_two_good_ones_does_not_break_the_streak() -> None:
    """The real Albert Nahman shape: good, broken, good.

    The broken run is skipped entirely, so the theme persists across it rather
    than appearing to lapse — which is the whole point of filtering BEFORE the
    state machine rather than inside it.
    """
    history = [
        CycleObservation(RunMeta("a", "2026-06-01", "done", 1.0, "v1"), frozenset({THEME})),
        CycleObservation(RunMeta("b", "2026-06-08", "done", 0.37, "v1"), frozenset()),
        CycleObservation(RunMeta("c", "2026-06-15", "done", 1.0, "v1"), frozenset({THEME})),
    ]
    facts = compute_lifecycle(comparable_cycles(history, "v1"))
    assert facts[THEME].status == LifecycleStatus.PERSISTING.value
    assert facts[THEME].cycles_open == 2


# --- invariants, over every sequence up to length 12 --------------------------

_ALL_SEQUENCES = [
    "".join(bits) for n in range(1, 13) for bits in product("TF", repeat=n)
]


def test_exactly_one_status_per_theme_per_history() -> None:
    for presence in _ALL_SEQUENCES:
        facts = compute_lifecycle(_cycles(presence))
        assert len(facts) <= 1
        for fact in facts.values():
            assert fact.status in {s.value for s in LifecycleStatus}


def test_the_first_fact_is_always_new() -> None:
    for presence in _ALL_SEQUENCES:
        if "T" not in presence:
            continue
        first = presence.index("T")
        assert _status(presence[: first + 1]) == LifecycleStatus.NEW.value


def test_resolved_only_ever_follows_enough_absences() -> None:
    for presence in _ALL_SEQUENCES:
        if _status(presence) != LifecycleStatus.RESOLVED.value:
            continue
        trailing = len(presence) - len(presence.rstrip("F"))
        assert trailing >= RESOLUTION_CONFIRMATION_RUNS, presence


def test_regressed_only_ever_follows_a_confirmed_resolve() -> None:
    for presence in _ALL_SEQUENCES:
        if _status(presence) != LifecycleStatus.REGRESSED.value:
            continue
        assert presence.endswith("T")
        assert _status(presence[:-1]) == LifecycleStatus.RESOLVED.value, presence


def test_cycles_open_resets_to_one_exactly_on_a_regression() -> None:
    for presence in _ALL_SEQUENCES:
        facts = compute_lifecycle(_cycles(presence))
        fact = facts.get(THEME)
        if fact and fact.status == LifecycleStatus.REGRESSED.value:
            assert fact.cycles_open == 1, presence


def test_first_seen_never_moves_once_set() -> None:
    """NEW is assigned once, on the cycle the theme first appeared, forever."""
    for presence in _ALL_SEQUENCES:
        if "T" not in presence:
            continue
        expected = f"run-{presence.index('T')}"
        assert compute_lifecycle(_cycles(presence))[THEME].first_seen_run == expected


def test_the_machine_is_deterministic() -> None:
    for presence in _ALL_SEQUENCES[:200]:
        assert compute_lifecycle(_cycles(presence)) == compute_lifecycle(_cycles(presence))


# --- the accountability arithmetic --------------------------------------------


def _multi(*cycle_themes: set[str]) -> list[CycleObservation]:
    return [
        CycleObservation(
            RunMeta(f"run-{i}", f"2026-06-{i + 1:02d}", "done", 1.0, "v1"), frozenset(themes)
        )
        for i, themes in enumerate(cycle_themes)
    ]


def test_the_arithmetic_closes_exactly() -> None:
    """opening = resolved + still_open, closing = still_open + new + regressed.

    A reader who does the subtraction and finds it wrong stops trusting every
    number on the page, so this is asserted rather than assumed.
    """
    acc = accountability(_multi({"a", "b", "c"}, {"b", "c", "d"}))
    assert acc.is_closed
    assert (acc.opening, acc.resolved, acc.still_open) == (3, 1, 2)
    assert (acc.closing, acc.new, acc.regressed) == (3, 1, 0)


def test_the_arithmetic_closes_over_every_generated_history() -> None:
    themes = ["a", "b", "c"]
    for bits in product([0, 1], repeat=6):
        cycles = _multi(
            {t for t, on in zip(themes, bits[:3], strict=True) if on},
            {t for t, on in zip(themes, bits[3:], strict=True) if on},
        )
        assert accountability(cycles).is_closed, bits


def test_a_regression_is_counted_as_a_regression_not_as_new() -> None:
    """Otherwise `closing` double-counts and the arithmetic stops closing."""
    acc = accountability(_multi({"a"}, set(), set(), {"a"}))
    assert acc.regressed == 1
    assert acc.new == 0
    assert acc.is_closed


def test_resolved_all_time_counts_transitions_not_rows() -> None:
    """A theme resolved for 20 cycles resolved ONCE."""
    acc = accountability(_multi({"a"}, set(), set(), set(), set(), set()))
    assert acc.resolved_all_time == 1


def test_a_first_cycle_has_nothing_to_compare_and_says_so() -> None:
    acc = accountability(_multi({"a", "b"}))
    assert acc.opening == 0 and acc.closing == 2
    assert "Nothing was open last cycle" in acc.sentence()
    assert acc.is_closed


def test_a_flat_cycle_is_a_claim_not_a_blank() -> None:
    acc = accountability(_multi({"a", "b"}, {"a", "b"}))
    sentence = acc.sentence()
    assert "still open" in sentence
    assert sentence.strip() != ""


def test_a_clean_cycle_reads_cleanly() -> None:
    assert "none are open now" in accountability(_multi(set(), set())).sentence()


def test_an_empty_history_does_not_divide_by_zero() -> None:
    acc = accountability([])
    assert acc == Accountability(0, 0, 0, 0, 0, 0, 0, 0)
    assert acc.is_closed
    assert compute_lifecycle([]) == {}
