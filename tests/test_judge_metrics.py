from __future__ import annotations

from src.pipeline.calibration import compare
from src.pipeline.judge import AccuracyFlag, AnswerJudgment, BrandJudgment
from src.pipeline.judge_metrics import (
    DEFAULT_GRADE_POLICY,
    brand_cells_map,
    collect_accuracy_flags,
    grade_penalty_flags,
    leaderboard,
    losing_cells,
    mention_rate,
    split_cells,
    stability,
    stability_by_engine,
    visibility_grade,
    visibility_score,
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


def test_mention_and_visibility() -> None:
    js = _judgments()
    assert mention_rate(js, "YNAB") == 1.0  # present in both cells
    assert mention_rate(js, "Centsible") == 0.5  # present in 1 of 2
    # YNAB (recommended_first + mid_pack) outranks Centsible (absent + buried).
    assert visibility_score(js, "YNAB") > visibility_score(js, "Centsible")


def test_leaderboard_orders_by_visibility() -> None:
    board = leaderboard(_judgments(), ["Centsible", "YNAB"])
    assert [row[0] for row in board] == ["YNAB", "Centsible"]


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


def test_visibility_grade_rewards_prominence() -> None:
    # YNAB is recommended_first / mid_pack -> high visibility -> top grade.
    strong = visibility_grade(_judgments(), "YNAB")
    # Centsible is absent / buried -> low visibility -> low grade.
    weak = visibility_grade(_judgments(), "Centsible")
    assert strong.score > weak.score
    assert strong.letter == "A"
    assert weak.letter in {"C", "D", "F"}


def test_visibility_grade_penalized_by_accuracy_flags() -> None:
    flag = AccuracyFlag("wrong_pricing", "$20/mo", "free", "high")
    clean = [_aj("q1", "openai", [_bj("Centsible", True, "recommended_first")])]
    flagged = [_aj("q1", "openai", [_bj("Centsible", True, "recommended_first")], [flag])]
    # Same visibility, but the high-severity flag drags the graded score down.
    assert visibility_grade(flagged, "Centsible").score < visibility_grade(clean, "Centsible").score
    assert visibility_grade(flagged, "Centsible").n_flags == 1


def test_collect_accuracy_flags_dedupes() -> None:
    f = AccuracyFlag("wrong_pricing", "$20/mo", "free + $5/mo", "high")
    js = [
        _aj("q1", "openai", [_bj("Centsible", True, "buried")], [f]),
        _aj("q1", "anthropic", [_bj("Centsible", True, "buried")], [f]),  # same flag, deduped
    ]
    assert len(collect_accuracy_flags(js)) == 1


def test_grade_dedupes_repeated_error_within_answer() -> None:
    # One answer flags the SAME error type twice (different claim text, as an
    # over-flagging judge does). It must count once toward the grade penalty —
    # repetition of one mistake cannot compound the score — and keep the worst
    # severity. (collect_accuracy_flags still lists both for display.)
    f_hi = AccuracyFlag("stale", "Ring 4 is the newest", "Ring 5 is current", "high")
    f_lo = AccuracyFlag("stale", "compare Ring 4 vs RingConn", "Ring 5 is current", "low")
    twice = [_aj("q1", "gemini", [_bj("Centsible", True, "recommended_first")], [f_hi, f_lo])]
    once = [_aj("q1", "gemini", [_bj("Centsible", True, "recommended_first")], [f_hi])]

    assert len(grade_penalty_flags(twice)) == 1  # collapsed to one stale problem
    assert len(collect_accuracy_flags(twice)) == 2  # but both still shown in the report
    g_twice, g_once = visibility_grade(twice, "Centsible"), visibility_grade(once, "Centsible")
    assert g_twice.n_flags == 1
    assert g_twice.score == g_once.score  # repetition did not compound the penalty
    assert g_twice.accuracy_penalty == DEFAULT_GRADE_POLICY.penalty["high"]  # worst severity kept


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
