from __future__ import annotations

from typing import Any

from src.audit.checks.content_calibration import (
    KAPPA_SHIP_THRESHOLD,
    GoldExample,
    flag_disagreements,
    load_gold_set,
    meets_ship_bar,
    quadratic_weighted_kappa,
    score_against_gold,
    score_check,
)
from src.audit.checks.content_judge import (
    CONTENT_CHECKS,
    CheckVerdict,
    ContentClass,
    ContentJudgeResult,
    evidence_supported,
    finalize_check,
    verdict_from_answers,
)

_ANSWER_FIRST = CONTENT_CHECKS[0]  # 3 sub-questions: direct, before_preamble, concise


# --- truth table -------------------------------------------------------------


def test_verdict_truth_table() -> None:
    assert verdict_from_answers(["yes", "yes", "yes"]) is ContentClass.PASS
    assert verdict_from_answers(["no", "no"]) is ContentClass.FAIL
    assert verdict_from_answers(["yes", "no"]) is ContentClass.PARTIAL
    assert verdict_from_answers(["yes", "unknown"]) is ContentClass.UNKNOWN
    assert verdict_from_answers([]) is ContentClass.UNKNOWN


# --- evidence enforcement ----------------------------------------------------


def test_evidence_supported() -> None:
    source = "Oura is a smart ring that tracks your sleep and recovery each night."
    assert evidence_supported("smart ring that tracks your sleep", source) is True
    assert evidence_supported("SMART  RING   that tracks your SLEEP", source) is True  # normalized
    assert evidence_supported("tracks your blood pressure continuously", source) is False
    assert evidence_supported("", source) is False


def _raw(key: str, answer: str, quote: str) -> dict[str, Any]:
    return {"key": key, "answer": answer, "evidence_quote": quote, "reasoning": "r"}


def test_finalize_downgrades_unsupported_affirmative() -> None:
    source = "The direct answer is here. It comes first. It is a short paragraph."
    raws = [
        _raw("direct", "yes", "The direct answer is here"),  # supported
        _raw("before_preamble", "yes", "this phrase is NOT in the page"),  # unsupported
        _raw("concise", "yes", "It is a short paragraph"),  # supported
    ]
    verdict = finalize_check(_ANSWER_FIRST, raws, source)
    # The unsupported 'yes' is downgraded to unknown -> whole check unknown + review.
    assert verdict.classification is ContentClass.UNKNOWN
    assert verdict.needs_review is True
    downgraded = next(s for s in verdict.sub_answers if s.key == "before_preamble")
    assert downgraded.answer == "unknown"
    assert downgraded.evidence_valid is False


def test_finalize_all_supported_yes_passes() -> None:
    source = "The direct answer is here. It comes first. It is a short paragraph."
    raws = [
        _raw("direct", "yes", "The direct answer is here"),
        _raw("before_preamble", "yes", "It comes first"),
        _raw("concise", "yes", "It is a short paragraph"),
    ]
    verdict = finalize_check(_ANSWER_FIRST, raws, source)
    assert verdict.classification is ContentClass.PASS
    assert verdict.needs_review is False


def test_finalize_all_no_fails() -> None:
    raws = [
        _raw("direct", "no", ""),
        _raw("before_preamble", "no", ""),
        _raw("concise", "no", ""),
    ]
    verdict = finalize_check(_ANSWER_FIRST, raws, "irrelevant text")
    assert verdict.classification is ContentClass.FAIL


def test_finalize_missing_subanswer_is_unknown() -> None:
    verdict = finalize_check(_ANSWER_FIRST, [_raw("direct", "yes", "x")], "x")
    # Two sub-questions had no answer -> unknown -> whole check unknown.
    assert verdict.classification is ContentClass.UNKNOWN


# --- calibration: kappa ------------------------------------------------------


def test_kappa_perfect_and_undefined() -> None:
    labels = ["pass", "fail", "partial", "pass", "fail"]
    assert quadratic_weighted_kappa(labels, labels) == 1.0
    # Single class on both sides -> undefined.
    assert quadratic_weighted_kappa(["pass", "pass"], ["pass", "pass"]) is None
    assert quadratic_weighted_kappa([], []) is None


def test_kappa_disagreement_below_perfect() -> None:
    human = ["pass", "pass", "fail", "fail"]
    judge = ["fail", "fail", "pass", "pass"]  # total swap
    kappa = quadratic_weighted_kappa(human, judge)
    assert kappa is not None and kappa < 0.5


def test_score_check_excludes_unknown() -> None:
    human = ["pass", "fail", "partial"]
    judge = ["pass", "fail", "unknown"]  # last is an abstention
    cal = score_check("answer_first_lead", human, judge)
    assert cal.n == 2  # the unknown pair is excluded
    assert cal.n_unknown == 1
    assert cal.kappa == 1.0  # the two scored pairs agree perfectly
    assert cal.ship_ok is True


def test_meets_ship_bar() -> None:
    good = score_check(
        "c", ["pass", "fail", "partial", "pass"], ["pass", "fail", "partial", "pass"]
    )
    assert good.kappa is not None and good.kappa >= KAPPA_SHIP_THRESHOLD
    assert meets_ship_bar({"c": good}) is True


# --- calibration: gold set + scoring against judge results -------------------


def _result(url: str, labels: dict[str, str]) -> ContentJudgeResult:
    verdicts = [
        CheckVerdict(cid, 3, ContentClass(val), "r", [], False) for cid, val in labels.items()
    ]
    return ContentJudgeResult(page_url=url, verdicts=verdicts, assessed=True)


def test_score_against_gold_and_disagreements() -> None:
    gold = [
        GoldExample("https://a/", "t", {"answer_first_lead": "pass", "original_data": "fail"}),
        GoldExample("https://b/", "t", {"answer_first_lead": "fail", "original_data": "fail"}),
    ]
    judged = {
        "https://a/": _result("https://a/", {"answer_first_lead": "pass", "original_data": "pass"}),
        "https://b/": _result("https://b/", {"answer_first_lead": "fail", "original_data": "fail"}),
    }
    scores = score_against_gold(gold, judged)
    assert scores["answer_first_lead"].n == 2
    disagreements = flag_disagreements(gold, judged)
    # Only original_data on page a disagrees (human fail, judge pass).
    assert disagreements == [
        {"page_url": "https://a/", "check_id": "original_data", "human": "fail", "judge": "pass"}
    ]


def test_load_gold_set(tmp_path: Any) -> None:
    path = tmp_path / "gold.jsonl"
    path.write_text(
        '{"page_url": "https://a/", "text": "hi", "labels": {"answer_first_lead": "pass"}}\n'
        "\n"  # blank line tolerated
        "{bad json}\n",  # malformed line skipped
        encoding="utf-8",
    )
    gold = load_gold_set(str(path))
    assert len(gold) == 1
    assert gold[0].labels == {"answer_first_lead": "pass"}
