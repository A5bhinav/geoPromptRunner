"""Phase 4 — the machinery behind the claims (audit-packaging P4-T1..T6).

Review sampling, engine drift, narrative grounding, and instrument versioning.
Each of these exists because a specific failure would otherwise be invisible:

- a QA queue that only ever finds false positives,
- a trend line that moves because the model changed,
- generated prose that states a number the data does not contain,
- a query set that drifts until the trend means nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.pipeline.drift import (
    DriftVerdict,
    compare_fingerprints,
    fingerprint_engine,
)
from src.pipeline.narrative import (
    Fact,
    Sentence,
    extract_numeric_claims,
    fallback_narrative,
    verify,
)
from src.pipeline.review import (
    ReviewCandidate,
    ReviewOutcome,
    ReviewStratum,
    reconcile,
    sample_for_review,
    stratify_gold_candidates,
)
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet
from src.prompts.versioning import (
    ClientConfig,
    CoreChangeRejected,
    comparability_version,
    config_fingerprint,
    split_tiers,
    validate_core_change,
)
from src.storage.models import QueryResult

# --- P4-T1 / P4-T2: review sampling -------------------------------------------


def _pool(critical: int = 3, high: int = 5, med: int = 4, low: int = 40, none: int = 200):  # type: ignore[no-untyped-def]
    return (
        [ReviewCandidate(f"c{i}", "critical") for i in range(critical)]
        + [ReviewCandidate(f"h{i}", "high") for i in range(high)]
        + [ReviewCandidate(f"m{i}", "med", "resolved") for i in range(med)]
        + [ReviewCandidate(f"l{i}", "low") for i in range(low)]
        + [ReviewCandidate(f"n{i}", "") for i in range(none)]
    )


def test_every_severe_cell_is_reviewed() -> None:
    result = sample_for_review(_pool())
    assert len(result.of(ReviewStratum.SEVERE.value)) == 8  # 3 critical + 5 high


def test_every_lifecycle_change_is_reviewed() -> None:
    """A finding we told a client was fixed is the one to check hardest."""
    result = sample_for_review(_pool())
    assert len(result.of(ReviewStratum.LIFECYCLE_CHANGED.value)) == 4


def test_the_no_finding_stratum_is_sampled_at_all() -> None:
    """The stratum people leave out, and the only one that finds FALSE NEGATIVES.

    Without it the queue can only ever discover over-flagging, and the expensive
    error here is the miss.
    """
    result = sample_for_review(_pool())
    assert result.of(ReviewStratum.NO_FINDING.value)


def test_a_small_population_still_contributes_one_item() -> None:
    """A 5% rate over 12 cells rounds to zero — a stratum that samples nothing
    is a stratum that does not exist."""
    result = sample_for_review([ReviewCandidate(f"n{i}", "") for i in range(12)])
    assert len(result.of(ReviewStratum.NO_FINDING.value)) == 1


def test_the_queue_is_reproducible() -> None:
    """A reviewer must be able to resume, and nobody may re-roll for a shorter list."""
    pool = _pool()
    assert sample_for_review(pool).items == sample_for_review(pool).items
    assert sample_for_review(pool, salt="a").items != sample_for_review(pool, salt="b").items


@pytest.mark.parametrize("seed", range(100))
def test_coverage_guarantees_hold_over_randomized_inputs(seed: int) -> None:
    """The 100% strata are 100% whatever the mix looks like."""
    import random

    rng = random.Random(seed)
    pool = [
        ReviewCandidate(
            f"cell{i}",
            rng.choice(["critical", "high", "med", "low", ""]),
            rng.choice(["", "new", "persisting", "resolved", "regressed"]),
        )
        for i in range(rng.randint(1, 120))
    ]
    result = sample_for_review(pool)
    severe = {c.cell_id for c in pool if c.is_severe}
    changed = {
        c.cell_id
        for c in pool
        if not c.is_severe and c.lifecycle_status in ("resolved", "regressed")
    }
    assert severe <= set(result.of(ReviewStratum.SEVERE.value))
    assert changed <= set(result.of(ReviewStratum.LIFECYCLE_CHANGED.value))


def test_the_cap_never_cuts_into_a_mandatory_stratum() -> None:
    """Dropping a Critical to make room for a routine sample is backwards."""
    from src.pipeline.review import SamplingPolicy

    pool = [ReviewCandidate(f"c{i}", "critical") for i in range(50)]
    pool += [ReviewCandidate(f"n{i}", "") for i in range(500)]
    result = sample_for_review(pool, SamplingPolicy(max_items=10))
    assert len(result.of(ReviewStratum.SEVERE.value)) == 50


def test_truncation_is_reported_never_silent() -> None:
    """A silently-capped queue reads as full coverage."""
    from src.pipeline.review import SamplingPolicy

    pool = [ReviewCandidate(f"n{i}", "") for i in range(500)]
    result = sample_for_review(pool, SamplingPolicy(max_items=5))
    assert result.dropped, "the cap must say what it excluded"


def test_the_gold_set_oversamples_the_rare_class_deliberately() -> None:
    """Random sampling under-represents exactly the cases that break judges."""
    buckets = stratify_gold_candidates(_pool(critical=30, high=30, none=2000), per_stratum=20)
    assert len(buckets[ReviewStratum.SEVERE.value]) == 20
    assert len(buckets[ReviewStratum.NO_FINDING.value]) == 20
    # Under random sampling at this mix, 20 items would contain ~1 severe.


def test_a_thin_stratum_returns_what_exists_rather_than_pretending() -> None:
    buckets = stratify_gold_candidates(_pool(critical=3, high=0, none=50), per_stratum=20)
    assert len(buckets[ReviewStratum.SEVERE.value]) == 3


# --- P4-T1: reviewer disagreement ---------------------------------------------


def test_agreeing_reviewers_who_match_the_judge_are_recorded_as_agreement() -> None:
    record = reconcile("c1", "severe", "high", "high", "high", "fp1", "2026-08-02")
    assert record.outcome == ReviewOutcome.AGREED
    assert not record.reviewers_disagreed


def test_agreeing_reviewers_who_differ_from_the_judge_are_an_override() -> None:
    record = reconcile("c1", "severe", "low", "critical", "critical", "fp1", "2026-08-02")
    assert record.outcome == ReviewOutcome.OVERRIDDEN
    assert record.final_label == "critical"


def test_disagreeing_reviewers_escalate_to_the_harsher_label() -> None:
    """Documented tie-break: a false Critical gets caught, a missed one ships."""
    record = reconcile("c1", "severe", "high", "critical", "high", "fp1", "2026-08-02")
    assert record.outcome == ReviewOutcome.ESCALATED
    assert record.final_label == "critical"
    assert record.reviewers_disagreed


def test_both_labels_survive_even_when_they_agree() -> None:
    """Keeping only the reconciled answer throws away the disagreement RATE."""
    record = reconcile("c1", "severe", "high", "high", "high", "fp1", "2026-08-02")
    assert record.reviewer_a and record.reviewer_b


def test_the_record_carries_the_prompt_fingerprint() -> None:
    """Without it, "the judge feels off lately" cannot become a ticket."""
    record = reconcile("c1", "severe", "high", "high", "high", "fp-abc123", "2026-08-02")
    assert record.prompt_fingerprint == "fp-abc123"


# --- P4-T3: engine drift ------------------------------------------------------


def _results(engine: str, n: int, length: int, citations: int = 0, answered: bool = True):  # type: ignore[no-untyped-def]
    return [
        QueryResult(
            query_id=f"q{i}",
            intent="category",
            prompt="(mock)",
            engine_name=engine,
            run_index=0,
            response=("a" * length) if answered else None,
            citations=["https://x"] * citations,
            timestamp="t",
        )
        for i in range(n)
    ]


def test_a_stable_surface_raises_no_flag() -> None:
    before = fingerprint_engine(_results("perplexity", 10, 900, 3), "perplexity", "sonar")
    after = fingerprint_engine(_results("perplexity", 10, 950, 3), "perplexity", "sonar")
    assert compare_fingerprints(before, after).drifted is False


def test_a_material_length_shift_is_flagged_and_annotated() -> None:
    before = fingerprint_engine(_results("perplexity", 10, 900, 3), "perplexity", "sonar")
    after = fingerprint_engine(_results("perplexity", 10, 2600, 3), "perplexity", "sonar")
    verdict = compare_fingerprints(before, after)
    assert verdict.drifted
    assert "possible engine update" in verdict.annotation()


def test_a_refusal_shift_is_flagged() -> None:
    before = fingerprint_engine(_results("openai_search", 10, 900), "openai_search")
    mixed = _results("openai_search", 5, 900) + _results("openai_search", 5, 0, answered=False)
    after = fingerprint_engine(mixed, "openai_search")
    assert compare_fingerprints(before, after).drifted


def test_a_changed_model_pin_is_certainty_not_inference() -> None:
    """The only signal available on a surface that publishes a dated pin."""
    before = fingerprint_engine(_results("anthropic_search", 10, 900), "anthropic_search", "s4-5")
    after = fingerprint_engine(_results("anthropic_search", 10, 900), "anthropic_search", "s5")
    verdict = compare_fingerprints(before, after)
    assert verdict.model_changed and verdict.drifted
    assert "model answering this surface changed" in verdict.annotation()


def test_a_first_cycle_is_not_drift() -> None:
    """Otherwise every new client's first report warns about an engine update."""
    after = fingerprint_engine(_results("perplexity", 10, 900), "perplexity")
    assert compare_fingerprints(None, after).drifted is False


def test_too_little_data_says_nothing_rather_than_guessing() -> None:
    """A spurious annotation trains people to ignore annotations."""
    before = fingerprint_engine(_results("perplexity", 2, 900), "perplexity")
    after = fingerprint_engine(_results("perplexity", 2, 5000), "perplexity")
    assert compare_fingerprints(before, after).drifted is False


def test_the_annotation_never_claims_anything_about_the_client() -> None:
    before = fingerprint_engine(_results("perplexity", 10, 900), "perplexity", "a")
    after = fingerprint_engine(_results("perplexity", 10, 3000), "perplexity", "b")
    text = compare_fingerprints(before, after).annotation().lower()
    assert "not strictly comparable" in text
    for banned in ("improved", "declined", "visibility", "resolved"):
        assert banned not in text


def test_a_clean_verdict_has_no_annotation_to_render() -> None:
    assert DriftVerdict("perplexity", drifted=False, reasons=[]).annotation() == ""


# --- P4-T4: the narrative verifier --------------------------------------------

FACTS = [
    Fact("F1", "open_findings", Decimal(12), "count"),
    Fact("F2", "critical", Decimal(3), "count"),
    Fact("F3", "mention_delta_pp", Decimal(-8), "pct_delta"),
]


def test_honest_prose_passes() -> None:
    sentences = [
        Sentence("This cycle surfaced 12 findings, 3 of them critical.", ("F1", "F2")),
        Sentence("Mention rate fell 8 percentage points.", ("F3",)),
    ]
    assert verify(sentences, FACTS).ok


def test_an_invented_number_is_rejected() -> None:
    """THE test. Do not weaken it — it is the point of the whole task."""
    result = verify([Sentence("This cycle surfaced 47 findings.", ("F1",))], FACTS)
    assert not result.ok
    assert "47" in result.reasons()


def test_citing_a_real_fact_while_writing_a_different_number_is_caught() -> None:
    """Self-reported citations cannot catch this; extracting from the raw text can."""
    result = verify([Sentence("There are 9 critical findings.", ("F2",))], FACTS)
    assert not result.ok


def test_an_unknown_fact_id_is_rejected() -> None:
    assert not verify([Sentence("Something happened.", ("F99",))], FACTS).ok


def test_direction_reversal_is_caught_even_though_the_number_is_right() -> None:
    """The failure a numeric check cannot see: "rose 8" against a −8 fact."""
    result = verify([Sentence("Mention rate rose 8 percentage points.", ("F3",))], FACTS)
    assert not result.ok
    assert "rise" in result.reasons()


def test_a_severity_word_needs_a_fact_carrying_it() -> None:
    result = verify([Sentence("Three findings regressed.", ("F2",))], FACTS)
    assert not result.ok
    assert "regressed" in result.reasons()


def test_a_ratio_is_not_double_counted_as_two_bare_numbers() -> None:
    """"6 of 12" must not read as the separate claims 6 and 12 — the reason the
    extraction passes consume spans in order."""
    claims = extract_numeric_claims("The client appeared in 6 of 12 runs.")
    raws = [c.raw for c in claims]
    assert "6 of 12" in raws
    assert claims[0].value == Decimal("50.00")


def test_ratios_percentages_and_words_normalize_to_one_scale() -> None:
    for text in ("6 of 12 runs", "50%", "half"):
        values = [c.value for c in extract_numeric_claims(text) if c.kind == "pct"]
        assert any(abs(v - Decimal(50)) < Decimal("0.6") for v in values), text


def test_rounding_is_allowed_but_a_wrong_number_is_not() -> None:
    facts = [Fact("F1", "rate", Decimal("58.33"), "pct")]
    assert verify([Sentence("It appeared in 58% of answers.", ("F1",))], facts).ok
    assert not verify([Sentence("It appeared in 62% of answers.", ("F1",))], facts).ok


def test_a_count_never_satisfies_a_percentage_claim() -> None:
    """12 and 12% are different assertions that share a digit."""
    facts = [Fact("F1", "open_findings", Decimal(12), "count")]
    assert not verify([Sentence("Visibility is 12%.", ("F1",))], facts).ok


def test_prose_with_no_numbers_at_all_passes() -> None:
    assert verify([Sentence("We reviewed every surface.", ())], FACTS).ok


def test_the_fallback_is_wooden_and_correct() -> None:
    """Strictly better than a pretty sentence for a product selling "no invented
    facts". Never silently drop the failing claim — that is data loss."""
    text = fallback_narrative(FACTS)
    assert "12" in text and "3" in text
    assert verify([Sentence(text, tuple(f.id for f in FACTS))], FACTS).ok


def test_the_fallback_handles_having_nothing_to_say() -> None:
    assert "No summary" in fallback_narrative([])


# --- P4-T5 / P4-T6: instrument versioning -------------------------------------


def _qs(version: str, ids: list[str]) -> QuerySet:
    return QuerySet(
        version=version,
        locked_at="2026-06-01",
        category="wearables",
        client="Fort",
        competitors=[],
        queries=[Query(query_id=i, text=f"q {i}", intent=IntentBucket.CATEGORY) for i in ids],
    )


CORE = [f"c{i}" for i in range(9)]


def test_discovery_churn_does_not_break_the_trend() -> None:
    """Rotating the discovery slice every cycle is the POINT of the tiering."""
    week1 = split_tiers(_qs("v1", [*CORE, "d1"]), CORE)
    week2 = split_tiers(_qs("v1", [*CORE, "d2"]), CORE)
    assert comparability_version(week1) == comparability_version(week2)
    validate_core_change(week1, week2)  # must not raise


def test_a_core_change_without_a_bridge_is_refused() -> None:
    """A step in the trend line and a step in the client are indistinguishable."""
    before = split_tiers(_qs("v1", [*CORE, "d1"]), CORE)
    new_core = [*CORE[:-1], "c9"]
    after = split_tiers(_qs("v2", [*new_core, "d1"]), new_core)
    with pytest.raises(CoreChangeRejected, match="bridge cycle"):
        validate_core_change(before, after)


def test_a_bridged_core_change_is_accepted() -> None:
    before = split_tiers(_qs("v1", [*CORE, "d1"]), CORE)
    new_core = [*CORE[:-1], "c9"]
    after = split_tiers(_qs("v2", [*new_core, "d1"]), new_core)
    bridge = [comparability_version(before), comparability_version(after)]
    validate_core_change(before, after, bridge_run_versions=bridge)


def test_an_eroding_core_is_reported() -> None:
    """Nobody decides to stop having a trend; the core erodes one query at a time."""
    thin = split_tiers(_qs("v1", [*CORE, *[f"d{i}" for i in range(9)]]), CORE)
    assert not thin.is_healthy
    assert "below the 75% target" in thin.health_note()


def test_an_unlabelled_set_treats_everything_as_core() -> None:
    """The conservative default: challenge a change rather than shrink the trend."""
    tiered = split_tiers(_qs("v1", [*CORE, "d1"]))
    assert len(tiered.discovery) == 0
    assert tiered.is_healthy


def _config(**overrides: object) -> ClientConfig:
    base = {
        "client_name": "Fort",
        "revision": 1,
        "comparability_version": "abc123",
        "engines": ("perplexity",),
        "competitors": ("Whoop",),
        "fact_sheet_text": "pricing: $289",
        "core_query_ids": tuple(CORE),
        "runs_per_query": 3,
    }
    base.update(overrides)
    return ClientConfig(**base)  # type: ignore[arg-type]


def test_a_fact_sheet_change_changes_the_config_fingerprint() -> None:
    """It decides what counts as an error, and the judge cache already keys on it."""
    assert config_fingerprint(_config()) != config_fingerprint(
        _config(fact_sheet_text="pricing: $319")
    )


def test_prose_and_bookkeeping_do_not_change_the_fingerprint() -> None:
    """Tidying a comment must not force a spurious incomparability."""
    assert config_fingerprint(_config()) == config_fingerprint(
        _config(notes="tidied", revision=7)
    )


def test_the_measurement_inputs_all_change_it() -> None:
    base = config_fingerprint(_config())
    for change in (
        {"engines": ("perplexity", "openai")},
        {"competitors": ("Whoop", "Oura")},
        {"runs_per_query": 5},
        {"core_query_ids": tuple(CORE[:-1])},
    ):
        assert config_fingerprint(_config(**change)) != base, change
