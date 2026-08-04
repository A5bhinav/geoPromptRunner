from __future__ import annotations

from src.pipeline.calibration import compare
from src.pipeline.judge import AccuracyFlag, AnswerJudgment, BrandJudgment
from src.pipeline.judge_metrics import (
    brand_cells_map,
    collect_accuracy_flags,
    leaderboard,
    losing_cells,
    median_prominence,
    mention_rate,
    prominence_distribution,
    split_cells,
    stability,
    stability_by_engine,
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


def test_mention_rate_counts_presence() -> None:
    js = _judgments()
    assert mention_rate(js, "YNAB") == 1.0  # present in both cells
    assert mention_rate(js, "Centsible") == 0.5  # present in 1 of 2


def test_prominence_is_a_distribution_not_a_score() -> None:
    """TR-T0: prominence reports counts across five levels, never a decimal."""
    js = _judgments()
    dist = prominence_distribution(brand_cells_map(js, ["YNAB"])["YNAB"])
    # Every level present even at zero, and the counts add back to the denominator.
    assert dist == {
        "recommended_first": 1,
        "mid_pack": 1,
        "buried": 0,
        "also_ran": 0,
        "absent": 0,
    }
    assert sum(dist.values()) == 2


def test_median_prominence_reads_only_cells_where_present() -> None:
    cm = brand_cells_map(_judgments(), ["YNAB", "Centsible"])
    # YNAB: recommended_first + mid_pack. Even count -> the WORSE of the two
    # middles, so a tie never rounds a client's position up.
    assert median_prominence(cm["YNAB"]) == "mid_pack"
    # Centsible: absent in q1, buried in q2. The absent cell is not a position.
    assert median_prominence(cm["Centsible"]) == "buried"


def test_median_prominence_is_none_when_never_present() -> None:
    # "No typical position" is a different statement from "typically absent",
    # and the tile renders an em dash rather than the worst level.
    js = [_aj("q1", "openai", [_bj("Ghost", False, "absent")])]
    assert median_prominence(brand_cells_map(js, ["Ghost"])["Ghost"]) is None


def test_leaderboard_orders_by_mention_rate_not_prominence() -> None:
    """The spec's own TR-T0 test: where the two disagree, mention rate wins.

    `Wide` appears everywhere but always mid-pack; `Narrow` is recommended first
    in the one cell it appears in. The old composite ranked Narrow above Wide —
    a client-facing ranking ordered by an invented weighting.
    """
    js = [
        _aj("q1", "openai", [_bj("Wide", True, "mid_pack"), _bj("Narrow", False, "absent")]),
        _aj("q2", "openai", [_bj("Wide", True, "mid_pack"), _bj("Narrow", False, "absent")]),
        _aj(
            "q3",
            "openai",
            [_bj("Wide", True, "mid_pack"), _bj("Narrow", True, "recommended_first")],
        ),
    ]
    board = leaderboard(js, ["Narrow", "Wide"])
    assert [r.brand for r in board] == ["Wide", "Narrow"]
    assert board[0].mention_rate > board[1].mention_rate
    # Prominence rides along as a label, and it is not the sort key.
    assert board[0].prominence == "mid_pack"
    assert board[1].prominence == "recommended_first"


def test_leaderboard_ties_break_on_brand_name() -> None:
    # A leaderboard that reshuffles when nothing moved reads as movement.
    js = [_aj("q1", "openai", [_bj("Zeta", True, "mid_pack"), _bj("Alpha", True, "buried")])]
    assert [r.brand for r in leaderboard(js, ["Zeta", "Alpha"])] == ["Alpha", "Zeta"]
    assert [r.brand for r in leaderboard(js, ["Alpha", "Zeta"])] == ["Alpha", "Zeta"]


def test_leaderboard_carries_the_denominator() -> None:
    board = leaderboard(_judgments(), ["Centsible", "YNAB"])
    row = next(r for r in board if r.brand == "Centsible")
    assert (row.present_cells, row.cells) == (1, 2)


def test_losing_cells_flags_client_absent_competitor_first() -> None:
    losses = losing_cells(_judgments(), client="Centsible", competitors=["YNAB"])
    # q1: Centsible absent, YNAB recommended_first -> a loss. q2: YNAB only mid_pack.
    assert [(c.query_id, c.brand) for c in losses] == [("q1", "YNAB")]


def test_losing_cells_collapses_multiple_rivals_in_one_cell() -> None:
    # Both rivals read recommended_first for the SAME cell (a cross-run best-seen
    # artifact); the losing cell must be counted once, not once per rival.
    js = [
        _aj(
            "q1",
            "openai",
            [
                _bj("YNAB", True, "recommended_first"),
                _bj("Monarch", True, "recommended_first"),
                _bj("Centsible", False, "absent"),
            ],
        )
    ]
    losses = losing_cells(js, client="Centsible", competitors=["YNAB", "Monarch"])
    assert len(losses) == 1
    assert (losses[0].query_id, losses[0].engine_name) == ("q1", "openai")
    assert losses[0].brand == "Monarch"  # deterministic representative (brand-sorted)


def test_collect_accuracy_flags_dedupes() -> None:
    f = AccuracyFlag("wrong_pricing", "$20/mo", "free + $5/mo", "high")
    js = [
        _aj("q1", "openai", [_bj("Centsible", True, "buried")], [f]),
        _aj("q1", "anthropic", [_bj("Centsible", True, "buried")], [f]),  # same flag, deduped
    ]
    assert len(collect_accuracy_flags(js)) == 1


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


# --- Stability of the judge read across repeat runs ----------------------------


def _run(qid: str, engine: str, run: int, brands: list[BrandJudgment]) -> AnswerJudgment:
    return AnswerJudgment(
        query_id=qid,
        engine_name=engine,
        intent="category",
        run_index=run,
        assessed=True,
        brands=brands,
        accuracy_flags=[],
    )


def test_stability_counts_a_prominence_wobble_as_a_split() -> None:
    # Present in all 3 runs, but recommended_first twice and buried once. Presence is
    # stable; the READ is not — and the report shows prominence, so this is a split.
    js = [
        _run("q1", "openai", 0, [_bj("Acme", True, "recommended_first")]),
        _run("q1", "openai", 1, [_bj("Acme", True, "recommended_first")]),
        _run("q1", "openai", 2, [_bj("Acme", True, "buried")]),
    ]
    cells = brand_cells_map(js, ["Acme"])["Acme"]
    assert len(cells) == 1
    assert cells[0].runs == 3
    assert cells[0].agree_runs == 2
    s = stability(cells)
    assert s.split_cells == 1
    assert s.mean_agreement == 2 / 3


def test_stability_per_engine_and_split_listing() -> None:
    js = [
        # openai wobbles, anthropic reproduces exactly.
        _run("q1", "openai", 0, [_bj("Acme", True, "recommended_first")]),
        _run("q1", "openai", 1, [_bj("Acme", False, "absent")]),
        _run("q1", "anthropic", 0, [_bj("Acme", True, "mid_pack")]),
        _run("q1", "anthropic", 1, [_bj("Acme", True, "mid_pack")]),
    ]
    cells = brand_cells_map(js, ["Acme"])["Acme"]
    per_engine = stability_by_engine(cells)
    assert per_engine["openai"].split_cells == 1
    assert per_engine["anthropic"].split_cells == 0
    assert [c.engine_name for c in split_cells(cells)] == ["openai"]


def test_unrepeated_cells_carry_no_stability_evidence() -> None:
    cells = brand_cells_map(_judgments(), ["YNAB"])["YNAB"]
    assert all(c.runs == 1 for c in cells)
    assert stability(cells).is_measured is False
    assert split_cells(cells) == []


def test_collapsed_verdict_is_unchanged_by_the_run_counts() -> None:
    # The added fields must be pure bookkeeping — presence/prominence/framing and the
    # rates built on them stay exactly what they were.
    js = _judgments()
    assert mention_rate(js, "YNAB") == 1.0
    assert mention_rate(js, "Centsible") == 0.5
    cells = {c.query_id: c for c in brand_cells_map(js, ["YNAB"])["YNAB"]}
    assert cells["q1"].prominence == "recommended_first"
    assert cells["q2"].prominence == "mid_pack"
