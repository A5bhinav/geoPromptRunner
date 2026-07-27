from __future__ import annotations

import pytest

from src.pipeline.trend import RunComparison, is_real_move, render_comparison


def test_is_real_move_threshold() -> None:
    assert is_real_move(0.50, 0.60, 0.05) is True  # 10 pts > 5 pt floor
    assert is_real_move(0.50, 0.53, 0.05) is False  # 3 pts within noise
    assert is_real_move(0.50, 0.45, 0.05) is False  # 5 pts not > 5 (strictly greater)


def _cmp() -> RunComparison:
    return RunComparison(
        brand="Oura",
        mention_rate_before=0.50,
        mention_rate_after=0.53,  # +3 pts — within a 5-pt floor
        mention_rate_by_bucket_before={"category": 0.80},
        mention_rate_by_bucket_after={"category": 0.95},  # +15 pts — real
        share_of_voice_before={"Oura": 0.40},
        share_of_voice_after={"Oura": 0.41},
        queries_won=[],
        queries_lost=[],
    )


def test_render_tags_within_noise_moves() -> None:
    out = render_comparison(_cmp(), "before", "after", noise_floor=0.05)
    assert "Real-move threshold: ±5 pts" in out
    # The +3pt overall move is jitter; the +15pt bucket move is real.
    assert "50% → 53% (▲3 pts) _(within noise)_" in out
    assert "80% → 95% (▲15 pts) |" in out  # not tagged


def test_render_without_floor_is_unchanged() -> None:
    out = render_comparison(_cmp(), "before", "after")
    assert "within noise" not in out
    assert "Real-move threshold" not in out


# --- W5.1: per-trade sampling bands -----------------------------------------------
# The plan is explicit: set K empirically per trade via `geo verify determinism`,
# not by assumption. These tests pin the DISCIPLINE, not a number.


def test_no_trade_band_is_invented() -> None:
    """SAMPLING_BANDS ships empty. A band that LOOKS measured but isn't launders a
    guess into the report as a methodology figure — worse than having none."""
    from src.pipeline.local_sampling import SAMPLING_BANDS

    for trade, band in SAMPLING_BANDS.items():
        assert band.is_measured, (
            f"{trade} has a sampling band with no measured_on date — either run "
            "`geo verify determinism` for it, or remove the entry"
        )
        assert band.measured_note, f"{trade} band has no provenance note"


def test_unmeasured_trade_falls_back_and_says_so() -> None:
    from src.config import settings
    from src.pipeline.local_sampling import band_for, runs_for_trade, sampling_note

    band = band_for("hvac")
    assert band.is_measured is False
    assert runs_for_trade("hvac") == settings.DEFAULT_RUNS_PER_QUERY

    note = sampling_note("hvac")
    assert "not established" in note
    # It must NOT imply a measurement happened.
    assert "measured 20" not in note


def test_runs_are_clamped_to_the_cap_but_the_overflow_stays_visible() -> None:
    """A measured band above MAX_RUNS_PER_QUERY is a real finding — local queries too
    unstable to measure at the current ceiling — not an error to swallow. Raising the
    cap must stay a deliberate, cost-bearing decision."""
    from src.config import settings
    from src.pipeline.local_sampling import TradeSamplingBand

    band = TradeSamplingBand(
        trade="plumbing",
        runs_per_query=settings.MAX_RUNS_PER_QUERY + 5,
        measured_on="2026-07-27",
        measured_note="hypothetical",
    )
    assert band.exceeds_cap is True
    assert band.is_measured is True

    within = TradeSamplingBand(trade="hvac", runs_per_query=3, measured_on="2026-07-27")
    assert within.exceeds_cap is False


def test_near_me_cohort_is_identified_and_its_noise_documented() -> None:
    from src.pipeline.local_sampling import NEAR_ME_NOISE_MULTIPLIER, is_near_me

    assert is_near_me("plumber near me") is True
    assert is_near_me("Plumber Near Me") is True
    assert is_near_me("best plumber in Berkeley") is False
    # SE Ranking measured ~2x less stability on "near me" phrasings.
    assert NEAR_ME_NOISE_MULTIPLIER == 2.0


def test_every_trade_set_prefers_explicit_city_over_near_me() -> None:
    """The trade query sets tag "near me" as a separate, noisier cohort rather than
    leaning on it — at most one such query per trade."""
    from src.pipeline.local_sampling import is_near_me
    from src.prompts.local_templates import TRADES, load_trade_template

    for trade in TRADES:
        qs = load_trade_template(trade)
        near_me = [q for q in qs.queries if is_near_me(q.text)]
        assert len(near_me) <= 1, f"{trade} leans on {len(near_me)} 'near me' queries"


def test_local_cadence_warns_when_there_is_no_noise_floor() -> None:
    """trend.render_comparison(noise_floor=None) tags NOTHING as within-noise, so
    every delta reads as a real move. For local that would report churn as progress."""
    from src.pipeline.local_sampling import local_cadence_warning

    warning = local_cadence_warning("plumbing")
    assert warning is not None
    assert "UNVERIFIED movement" in warning
    assert "verify determinism" in warning


def test_local_cadence_warning_clears_once_a_band_is_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import local_sampling

    monkeypatch.setitem(
        local_sampling.SAMPLING_BANDS,
        "plumbing",
        local_sampling.TradeSamplingBand(
            trade="plumbing",
            runs_per_query=5,
            measured_on="2026-07-27",
            measured_note="modal agreement 0.62 across google_ai_overviews",
        ),
    )
    assert local_sampling.local_cadence_warning("plumbing") is None
    note = local_sampling.sampling_note("plumbing")
    assert "measured 2026-07-27" in note
    assert "not established" not in note
