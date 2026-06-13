from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.calibration import (
    GoldFlag,
    GoldItem,
    _Eval,
    _tally,
    compare,
    load_gold_set,
    match_flags,
    render_calibration,
)
from src.storage.models import AccuracyFlag, BrandJudgment


def _flag(t: str, sev: str = "high") -> AccuracyFlag:
    return AccuracyFlag(type=t, claim="c", reality="r", severity=sev)


def test_match_flags_type_multiset() -> None:
    # Judge: 2 pricing + 1 stale. Gold: 1 pricing + 1 feature.
    judge = [_flag("wrong_pricing"), _flag("wrong_pricing"), _flag("stale")]
    gold = [GoldFlag("wrong_pricing", "high"), GoldFlag("missing_or_invented_feature", "med")]
    s = match_flags(judge, gold)
    assert s.tp == 1  # one pricing pair
    assert s.fp == 2  # extra pricing + the stale (over-flagging)
    assert s.fn == 1  # the missed feature flag
    assert round(s.precision, 3) == round(1 / 3, 3)
    assert s.recall == 0.5


def test_match_flags_clean_when_empty() -> None:
    s = match_flags([], [])
    assert s.tp == s.fp == s.fn == 0
    assert s.precision == 1.0 and s.recall == 1.0  # nothing flagged, nothing expected


def test_match_flags_over_flagging_tanks_precision() -> None:
    # The Oura failure: judge invents flags where gold says the answer is accurate.
    s = match_flags([_flag("missing_or_invented_feature"), _flag("stale")], [])
    assert s.tp == 0 and s.fp == 2 and s.fn == 0
    assert s.precision == 0.0  # caught — the binary metric was blind to this
    assert s.recall == 1.0


def test_match_flags_severity_within_one() -> None:
    s = match_flags([_flag("wrong_pricing", "med")], [GoldFlag("wrong_pricing", "high")])
    assert s.tp == 1
    assert s.severity_exact == 0  # med != high
    assert s.severity_within_one == 1  # adjacent bands
    # high vs low is NOT within one
    s2 = match_flags([_flag("stale", "low")], [GoldFlag("stale", "high")])
    assert s2.severity_within_one == 0


def test_compare_counts_only_judged_brands() -> None:
    brands = [
        BrandJudgment("Oura", True, "recommended_first", "positive"),
        BrandJudgment("Whoop", False, "absent", "neutral"),
    ]
    labels = {
        "Oura": {"present": True, "prominence": "recommended_first", "framing": "positive"},
        "Whoop": {"present": False, "prominence": "absent", "framing": "neutral"},
        "Ghost": {"present": True, "prominence": "mid_pack", "framing": "neutral"},  # not judged
    }
    pm, pt, rm, rt, fm, ft = compare(brands, labels)
    assert (pt, rt, ft) == (2, 2, 2)  # Ghost skipped
    assert (pm, rm, fm) == (2, 2, 2)  # both judged brands match


def _gold(engine: str, expected: list[GoldFlag]) -> GoldItem:
    return GoldItem(
        query="q",
        answer="a",
        client="Oura",
        competitors=["Whoop"],
        fact_sheet="Ring 5 is $399.",
        labels={
            "Oura": {"present": True, "prominence": "recommended_first", "framing": "positive"}
        },
        expect_accuracy_flags=len(expected) > 0,
        expected_flags=expected,
        engine=engine,
        category="smart ring",
    )


def test_tally_precision_recall_and_breakdowns() -> None:
    evals = [
        _Eval(
            item=_gold("openai", [GoldFlag("wrong_pricing", "high")]),
            brands=[BrandJudgment("Oura", True, "recommended_first", "positive")],
            flags=[_flag("wrong_pricing")],  # correct
            assessed=True,
        ),
        _Eval(
            item=_gold("gemini", []),  # gold says accurate
            brands=[BrandJudgment("Oura", True, "recommended_first", "positive")],
            flags=[_flag("stale")],  # judge over-flagged
            assessed=True,
        ),
    ]
    report = _tally(evals)
    # 1 TP (pricing), 1 FP (the invented stale), 0 FN.
    assert report.flags.tp == 1 and report.flags.fp == 1 and report.flags.fn == 0
    assert report.flags.precision == 0.5 and report.flags.recall == 1.0
    # Present agreement is perfect over both judged brands.
    assert report.present_agreement == 1.0
    # Per-engine breakdown isolates the over-flagger.
    assert set(report.by_engine) == {"openai", "gemini"}
    assert report.by_engine["openai"].flags.precision == 1.0
    assert report.by_engine["gemini"].flags.precision == 0.0
    assert "smart ring" in report.by_category
    # Renders without error and shows the precision line.
    assert "flag precision" in render_calibration(report)


def test_tally_legacy_binary_flag_detection() -> None:
    # Legacy item: no typed expected_flags -> only the binary metric applies.
    legacy = GoldItem(
        query="q", answer="a", client="Oura", competitors=[],
        fact_sheet="Ring 5 is $399.",
        labels={}, expect_accuracy_flags=True, expected_flags=None,
    )
    ev = _Eval(item=legacy, brands=[], flags=[_flag("wrong_pricing")], assessed=True)
    report = _tally([ev])
    assert report.flag_detection_total == 1 and report.flag_detection_match == 1
    assert report.flags.n_items == 0  # not counted in typed precision/recall


def test_loader_v2_and_legacy(tmp_path: Path) -> None:
    blob = {
        "items": [
            {
                "query": "q1", "answer": "a1", "client": "Oura", "competitors": ["Whoop"],
                "fact_sheet": "f", "category": "smart ring", "engine": "openai",
                "labels": {"Oura": {"present": True, "prominence": "mid_pack"}},
                "expected_flags": [{"type": "stale", "severity": "high", "note": "old model"}],
                "fact_sheet_candidates": ["uncovered claim"],
            },
            {  # legacy
                "query": "q2", "answer": "a2", "client": "Oura", "competitors": [],
                "fact_sheet": None, "labels": {}, "expect_accuracy_flags": True,
            },
        ]
    }
    p = tmp_path / "gold.json"
    p.write_text(json.dumps(blob))
    items = load_gold_set(p)
    assert items[0].has_typed_flags
    assert items[0].expected_flags == [GoldFlag("stale", "high", "old model")]
    assert items[0].expect_accuracy_flags is True
    assert items[0].engine == "openai" and items[0].category == "smart ring"
    assert items[0].fact_sheet_candidates == ["uncovered claim"]
    # Legacy item: not typed-labeled, but binary boolean preserved.
    assert items[1].has_typed_flags is False
    assert items[1].expected_flags is None
    assert items[1].expect_accuracy_flags is True


def test_sample_gold_loads_as_v2() -> None:
    items = load_gold_set("data/sample_gold.json")
    assert len(items) == 3
    assert all(it.has_typed_flags for it in items)  # sample migrated to v2
    assert items[0].expected_flags  # item 1 has real errors
    assert items[2].expected_flags == []  # item 3 accurate
    assert items[2].fact_sheet_candidates  # ...with an uncoverable-claim guard
