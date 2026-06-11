"""Unit tests for the verification probes (canary, determinism, shuffle).

The live runners are exercised with fake engines: a stateless one (the
behavior the real API path has) and a deliberately stateful one (the chat-app
behavior the probes exist to catch), so both verdict paths are proven.
"""

from __future__ import annotations

import pytest

from src.engines.base import BaseEngine
from src.verification.canary import (
    MARKER,
    CanaryResult,
    evaluate_canary,
    render_canary_results,
    run_canaries,
    run_canary,
)
from src.verification.determinism import (
    agreement_stats,
    measure_determinism,
    normalize_answer,
    render_baseline,
    suggest_runs_per_query,
)
from src.verification.shuffle import (
    compare_passes,
    render_shuffle_results,
    run_order_shuffle,
)


class _Stateless(BaseEngine):
    """Each call sees only its own prompt — like a clean chat-completions API."""

    ENGINE_NAME = "stateless"

    def query(self, prompt: str) -> str | None:
        if "code phrase" in prompt and "previous message" in prompt:
            return "NO PRIOR CONTEXT."
        return f"answer for: {prompt}"


class _Stateful(BaseEngine):
    """Remembers prior calls — the chat-app contamination the canary must catch."""

    ENGINE_NAME = "stateful"

    def __init__(self) -> None:
        self._history: list[str] = []

    def query(self, prompt: str) -> str | None:
        if "previous message" in prompt and self._history:
            return f"You said: {self._history[-1]}"
        self._history.append(prompt)
        return "Acknowledged."


class _Dead(BaseEngine):
    """Always errors (returns None) — the inconclusive path."""

    ENGINE_NAME = "dead"

    def query(self, prompt: str) -> str | None:
        return None


# --- Canary (Test A) -----------------------------------------------------------


def test_evaluate_canary_verdicts() -> None:
    assert evaluate_canary("NO PRIOR CONTEXT.") == "isolated"
    assert evaluate_canary(f'You said "{MARKER}" earlier.') == "leaked"
    assert evaluate_canary(MARKER.upper()) == "leaked"  # case-insensitive
    assert evaluate_canary(None) == "inconclusive"


def test_canary_passes_on_stateless_engine() -> None:
    result = run_canary(_Stateless())
    assert result.verdict == "isolated"
    assert result.engine_name == "stateless"


def test_canary_catches_stateful_engine() -> None:
    result = run_canary(_Stateful())
    assert result.verdict == "leaked"
    assert result.probe_response is not None and MARKER in result.probe_response


def test_canary_inconclusive_when_engine_fails() -> None:
    assert run_canary(_Dead()).verdict == "inconclusive"


def test_canary_inconclusive_when_setup_fails_but_probe_clean() -> None:
    # Marker never planted -> a clean probe proves nothing.
    class _SetupFails(BaseEngine):
        ENGINE_NAME = "setup-fails"

        def query(self, prompt: str) -> str | None:
            if "previous message" in prompt:
                return "NO PRIOR CONTEXT."
            return None

    assert run_canary(_SetupFails()).verdict == "inconclusive"


def test_render_canary_results_flags_leaks() -> None:
    results = run_canaries([_Stateless(), _Stateful()])
    text = render_canary_results(results)
    assert "ISOLATION BROKEN" in text
    assert "stateful" in text
    clean = render_canary_results(
        [CanaryResult("stateless", "isolated", "ok", "NO PRIOR CONTEXT.")]
    )
    assert "clean room" in clean


# --- Determinism baseline (Test D) ----------------------------------------------


def test_normalize_answer_collapses_format_noise() -> None:
    assert normalize_answer("  The Best\n  App ") == normalize_answer("the best app")


def test_agreement_stats_identical() -> None:
    stats = agreement_stats(["Oura wins.", "oura  wins.", "OURA WINS."])
    assert stats.identical is True
    assert stats.unique_answers == 1
    assert stats.modal_agreement == 1.0
    assert stats.answered == 3


def test_agreement_stats_mixed() -> None:
    stats = agreement_stats(["a", "a", "b", None])
    assert stats.k == 4
    assert stats.answered == 3
    assert stats.unique_answers == 2
    assert stats.modal_agreement == pytest.approx(2 / 3)
    assert stats.identical is False


def test_agreement_stats_all_failed() -> None:
    stats = agreement_stats([None, None])
    assert stats.answered == 0
    assert stats.modal_agreement == 0.0
    assert stats.identical is False


def test_suggest_runs_per_query_bands() -> None:
    assert suggest_runs_per_query(agreement_stats(["a"] * 10)) == 3
    assert suggest_runs_per_query(agreement_stats(["a"] * 6 + ["b"] * 4)) == 5
    assert suggest_runs_per_query(agreement_stats(["a", "b", "c", "d", "e"])) == 10
    assert suggest_runs_per_query(agreement_stats([None, None])) == 3


def test_measure_determinism_runs_k_fresh_calls() -> None:
    class _Counting(BaseEngine):
        ENGINE_NAME = "counting"
        calls = 0

        def query(self, prompt: str) -> str | None:
            _Counting.calls += 1
            return "same answer"

    baseline = measure_determinism(_Counting(), "q", k=5)
    assert _Counting.calls == 5
    assert baseline.stats.identical is True
    assert len(baseline.responses) == 5


def test_measure_determinism_rejects_k_below_two() -> None:
    with pytest.raises(ValueError, match="k must be >= 2"):
        measure_determinism(_Stateless(), "q", k=1)


def test_render_baseline_smoke() -> None:
    text = render_baseline([measure_determinism(_Stateless(), "q", k=3)])
    assert "stateless" in text
    assert "modal-agreement=100%" in text


# --- Order-shuffle (Test C) ------------------------------------------------------


def test_compare_passes_marks_matches_and_mismatches() -> None:
    prompts = ["q1", "q2", "q3"]
    forward: list[str | None] = ["a", "b", None]
    backward: list[str | None] = ["A ", "changed", None]
    comparisons = compare_passes(prompts, forward, backward)
    assert [c.match for c in comparisons] == [True, False, True]


def test_compare_passes_none_vs_text_is_mismatch() -> None:
    (c,) = compare_passes(["q"], ["a"], [None])
    assert c.match is False


def test_compare_passes_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        compare_passes(["q"], ["a", "b"], ["a"])


def test_order_shuffle_clean_on_order_independent_engine() -> None:
    result = run_order_shuffle(_Stateless(), ["q1", "q2", "q3"])
    assert result.match_rate == 1.0


def test_order_shuffle_catches_order_dependence() -> None:
    class _OrderSensitive(BaseEngine):
        """Answer depends on how many calls came before — leakage by position."""

        ENGINE_NAME = "order-sensitive"

        def __init__(self) -> None:
            self._calls = 0

        def query(self, prompt: str) -> str | None:
            self._calls += 1
            return f"{prompt} (call #{self._calls})"

    result = run_order_shuffle(_OrderSensitive(), ["q1", "q2", "q3"])
    # The counter never resets, so every query answers differently across the
    # two passes — exactly the shift the probe exists to surface.
    assert result.match_rate == 0.0


def test_render_shuffle_results_lists_differing_queries() -> None:
    result = run_order_shuffle(_Stateless(), ["q1"])
    text = render_shuffle_results([result])
    assert "match rate 100%" in text
