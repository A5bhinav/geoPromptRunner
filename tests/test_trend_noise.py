from __future__ import annotations

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
