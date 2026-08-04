"""Judge-vs-human agreement and the production gate (audit-packaging P4-T1).

Two decisions carry this module, and both are counterintuitive enough that the
tests are the argument:

1. **AC1, not kappa**, because kappa reads as mediocre at near-perfect agreement
   when one class dominates — which it always does here.
2. **The gate is per-class recall on Critical/High**, not aggregate accuracy,
   because a judge that answers "no flag" to everything scores 95%+ aggregate
   with zero recall on the class a client acts on.
"""

from __future__ import annotations

import pytest

from src.pipeline.agreement import (
    CRITICAL_HIGH_RECALL_FLOOR,
    NO_FLAG,
    agreement,
    gate_critical_high_recall,
    required_items_for_minority,
)


def _pairs(**counts: int) -> list[tuple[str, str]]:
    """`_pairs(none__none=190, critical__none=3)` -> (human, judge) pairs."""
    out: list[tuple[str, str]] = []
    for key, n in counts.items():
        human, judge = key.split("__")
        out.extend([(human, judge)] * n)
    return out


# --- the kappa paradox --------------------------------------------------------


def test_kappa_understates_agreement_when_one_class_dominates() -> None:
    """The reason AC1 is the headline.

    97.5% raw agreement on a rare class. Kappa says the judge is unreliable; AC1
    says it agrees with the human almost every time. The second is true, and the
    natural response to the first is to "fix" a judge that is not broken.
    """
    report = agreement(
        _pairs(none__none=190, critical__critical=5, none__critical=2, critical__none=3)
    )
    assert report.raw_agreement == pytest.approx(0.975)
    assert report.gwet_ac1 == pytest.approx(0.973, abs=0.002)
    assert report.cohens_kappa == pytest.approx(0.654, abs=0.002)
    assert report.gwet_ac1 - report.cohens_kappa > 0.3, "the paradox must be visible"


def test_both_are_reported_never_one_alone() -> None:
    report = agreement(_pairs(none__none=90, critical__critical=10))
    for field in ("raw_agreement", "gwet_ac1", "cohens_kappa"):
        assert isinstance(getattr(report, field), float)
    assert report.confusion, "the confusion matrix is what shows WHERE it errs"
    assert report.support, "recall without its denominator is not a number"


def test_perfect_and_total_disagreement_are_bounded() -> None:
    perfect = agreement(_pairs(none__none=50, critical__critical=50))
    assert perfect.raw_agreement == 1.0
    assert perfect.gwet_ac1 == pytest.approx(1.0)
    disagree = agreement(_pairs(none__critical=50, critical__none=50))
    assert disagree.raw_agreement == 0.0
    assert disagree.gwet_ac1 < 0.0


def test_a_single_category_cannot_disagree() -> None:
    report = agreement(_pairs(none__none=20))
    assert report.gwet_ac1 == 1.0 and report.cohens_kappa == 1.0


def test_an_empty_set_is_not_an_error() -> None:
    report = agreement([])
    assert report.n == 0
    assert "not been measured" in report.headline()


# --- the production gate ------------------------------------------------------


def test_an_all_negative_judge_fails_despite_high_accuracy() -> None:
    """The test the gate exists for.

    95% aggregate accuracy, zero recall on the only classes that matter. Any
    metric that reports this judge as fit is measuring the wrong thing.
    """
    report = agreement(_pairs(none__none=190, critical__none=5, high__none=5))
    assert report.raw_agreement == pytest.approx(0.95)
    assert report.per_class_recall["critical"] == 0.0
    assert report.per_class_recall["high"] == 0.0
    failures = gate_critical_high_recall(report)
    assert failures
    assert any("critical" in f for f in failures) and any("high" in f for f in failures)


def test_a_good_judge_with_enough_examples_passes() -> None:
    report = agreement(
        _pairs(
            none__none=150,
            critical__critical=29,
            critical__high=1,
            high__high=28,
            high__med=2,
        )
    )
    assert report.per_class_recall["critical"] >= CRITICAL_HIGH_RECALL_FLOOR
    assert gate_critical_high_recall(report) == []


def test_an_underpowered_tier_fails_rather_than_passing_by_luck() -> None:
    """Three gold flags cannot demonstrate 90% recall, whatever they score.

    "We could not measure it" must not read the same as "it passed". Two
    identical runs of the real Fort set returned recall 67% then 100% on the same
    inputs — that is the sample size talking, not the judge.
    """
    report = agreement(_pairs(none__none=100, critical__critical=3, high__high=25))
    assert report.per_class_recall["critical"] == 1.0, "perfect recall on 3 examples"
    failures = gate_critical_high_recall(report)
    assert any("too few" in f for f in failures)
    assert not any("high" in f for f in failures), "a well-powered tier must still pass"


def test_a_tier_with_no_gold_examples_is_unmeasured_not_passing() -> None:
    report = agreement(_pairs(none__none=100, high__high=25))
    failures = gate_critical_high_recall(report)
    assert any("critical" in f and "no gold examples" in f for f in failures)


def test_recall_with_no_denominator_is_zero_not_one() -> None:
    """The opposite convention flatters exactly the case that matters."""
    report = agreement(_pairs(none__none=10))
    assert report.per_class_recall.get("critical", 0.0) == 0.0


# --- sizing the gold set ------------------------------------------------------


def test_the_gold_set_is_sized_by_the_rare_class() -> None:
    """At a 6% base rate, 50 traces gives ~3 minority examples — useless."""
    assert required_items_for_minority(20, 0.06) == 334
    assert required_items_for_minority(20, 0.06) > required_items_for_minority(20, 0.20)


def test_stratified_sampling_makes_the_total_a_choice() -> None:
    """Random sampling under-represents exactly the cases that break judges."""
    assert required_items_for_minority(20, 0.06, oversampled=True) == 20


def test_a_zero_base_rate_is_an_error_not_an_infinite_sample() -> None:
    with pytest.raises(ValueError):
        required_items_for_minority(20, 0.0)


# --- the label that makes all of the above well defined -----------------------


def test_an_answers_label_is_its_worst_severity() -> None:
    """An answer with a Critical and three Lows is a Critical — that is what a
    reader acts on, and single-label is what AC1/kappa/recall require."""
    from src.pipeline.calibration import severity_label
    from src.storage.models import AccuracyFlag

    flags = [
        AccuracyFlag("missing_or_invented_feature", "invented", "reality", "low"),
        AccuracyFlag("wrong_pricing", "costs $349", "reality", "high"),
    ]
    assert severity_label(flags) == "critical"  # wrong_pricing/high escalates
    assert severity_label([]) == NO_FLAG


# --- publishing what IS measured ----------------------------------------------


def _summary(**overrides: object):  # type: ignore[no-untyped-def]
    from src.pipeline.calibration import AgreementSummary

    base = {
        "client": "Fort",
        "measured_on": "2026-07-31",
        "judge_model": "claude-sonnet-4-5-20250929",
        "n_items": 40,
        "n_brand_judgements": 240,
        "present": 0.94,
        "prominence": 0.86,
        "framing": 0.93,
        "flag_precision": 0.43,
        "flag_recall": 1.0,
        "n_judge_flags": 7,
        "n_gold_flags": 3,
        "severity_exact": 0.67,
        "n_severity_pairs": 3,
    }
    base.update(overrides)
    return AgreementSummary(**base)  # type: ignore[arg-type]


def test_the_measured_dimensions_are_published_with_their_denominator() -> None:
    """Saying "unmeasured" while holding 94% on 240 judgements understates the work."""
    sentence = _summary().sentence()
    assert "94%" in sentence and "240 brand judgements" in sentence
    assert "40 hand-labeled answers" in sentence
    assert "2026-07-31" in sentence


def test_a_thin_flag_sample_is_named_not_quoted() -> None:
    """43% off SEVEN flags is the bare-percentage failure in a different coat."""
    sentence = _summary().sentence()
    assert "43%" not in sentence
    assert "3 findings, too few" in sentence


def test_a_well_powered_flag_sample_would_be_quoted() -> None:
    """The gate is the denominator, not a permanent refusal — this is what
    changes when ~60 stratified items get labeled."""
    sentence = _summary(n_gold_flags=25, n_judge_flags=28, flag_precision=0.8).sentence()
    assert "precision 80% of 28" in sentence
    assert "recall 100% of 25" in sentence


def test_the_quotable_threshold_is_the_documented_one() -> None:
    from src.pipeline.calibration import AgreementSummary

    assert AgreementSummary.MIN_FLAGS_TO_QUOTE == 20
    assert not _summary(n_gold_flags=19, n_judge_flags=50).flags_are_quotable
    assert _summary(n_gold_flags=20, n_judge_flags=20).flags_are_quotable


def test_a_client_with_no_summary_falls_back_to_the_unmeasured_line() -> None:
    from src.pipeline.calibration import load_agreement_summary

    assert load_agreement_summary("A Client Nobody Has Labeled") is None


def test_the_stored_summaries_load_and_match_the_calibration_report() -> None:
    """Pins the transcription: these figures came from docs/calibration/."""
    from src.pipeline.calibration import load_agreement_summary

    fort = load_agreement_summary("Fort")
    assert fort is not None
    assert (fort.present, fort.prominence, fort.framing) == (0.94, 0.86, 0.93)
    assert (fort.n_gold_flags, fort.n_judge_flags) == (3, 7)
    assert not fort.flags_are_quotable

    oura = load_agreement_summary("Oura")
    assert oura is not None
    # 18 gold flags is the best-powered set there is, and it is STILL under the
    # bar — which is the finding, not a gap in the tooling.
    assert oura.n_gold_flags == 18
    assert not oura.flags_are_quotable
