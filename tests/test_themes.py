"""Root-cause theme classification (audit-packaging P0-T3).

Two acceptance criteria from the spec, both asserted here: **every**
``AccuracyFlagType`` maps to at least one theme, and **no** flag can produce
``None``. Plus the split that motivates the whole taxonomy — ``feature_invented``
vs ``feature_omitted``, whose fixes are opposite.

Claim strings are the phrasings the Fort and Albert Nahman runs produce
(``docs/fort-labeling-sheet.md``, ``docs/local-labeling-sheet.md``), not invented
prose, so a rule that only works on tidy sentences fails here.
"""

from __future__ import annotations

import pytest

from src.pipeline.themes import (
    RULES,
    THEME_LABELS,
    TYPE_DEFAULTS,
    Theme,
    classify,
    coverage,
    theme_label,
)
from src.storage.models import AccuracyFlagType

# (flag_type, claim, expected theme) — at least three per theme that a rule owns.
CASES: list[tuple[str, str, str]] = [
    # identity_disambiguation
    ("identity", "There isn't a widely recognized brand called 'Fort'.", "identity_disambiguation"),
    (
        "identity",
        "Fort (assuming you mean Fitbit?) makes fitness trackers.",
        "identity_disambiguation",
    ),
    (
        "identity",
        "I don't have specific information about a company called Fort.",
        "identity_disambiguation",
    ),
    ("identity", "Fort appears to be a fictional product.", "identity_disambiguation"),
    # lifecycle_status
    ("stale", "The Fort band is already shipping to customers.", "lifecycle_status"),
    (
        "stale",
        "Fort is a relatively new entrant in the fitness tracking space.",
        "lifecycle_status",
    ),
    ("stale", "Albert Nahman Plumbing appears to be permanently closed.", "lifecycle_status"),
    # pricing_offer
    ("wrong_pricing", "The Fort band costs $349.", "pricing_offer"),
    ("wrong_pricing", "The subscription is 79.99 dollars per year.", "pricing_offer"),
    ("wrong_pricing", "There is a free tier for basic tracking.", "pricing_offer"),
    # feature_invented
    ("missing_or_invented_feature", "Fort measures blood pressure and ECG.", "feature_invented"),
    (
        "missing_or_invented_feature",
        "It includes built-in GPS for outdoor runs.",
        "feature_invented",
    ),
    ("missing_or_invented_feature", "Fort supports automatic sleep staging.", "feature_invented"),
    # feature_omitted — the opposite fix, and it must not collapse into the above
    ("missing_or_invented_feature", "Fort does not track heart rate.", "feature_omitted"),
    ("missing_or_invented_feature", "There is no Android app for Fort.", "feature_omitted"),
    ("missing_or_invented_feature", "The app is only available on iOS.", "feature_omitted"),
    # competitor_mischaracterization
    (
        "competitor_confusion",
        "It's just a heart-rate band like Whoop.",
        "competitor_mischaracterization",
    ),
    (
        "competitor_confusion",
        "Fort is a Vitruve-class VBT encoder.",
        "competitor_mischaracterization",
    ),
    ("competitor_confusion", "It is essentially an Oura clone.", "competitor_mischaracterization"),
    # availability_geography
    ("wrong_service_area", "They serve the entire Bay Area.", "availability_geography"),
    ("wrong_hours", "Albert Nahman is open 24/7 for emergencies.", "availability_geography"),
    ("wrong_hours", "They are closed on weekends.", "availability_geography"),
    # risk_reputation
    ("licensing", "It is unclear whether they are licensed and bonded.", "risk_reputation"),
    ("licensing", "They hold a valid C-36 certification.", "risk_reputation"),
    ("licensing", "There are complaints filed with the Better Business Bureau.", "risk_reputation"),
    # company_facts
    ("wrong_contact", "Their phone number is 510-234-9981.", "company_facts"),
    ("wrong_contact", "The mailing address is in San Jose.", "company_facts"),
    ("identity", "Fort's founder previously worked at Google.", "company_facts"),
]


@pytest.mark.parametrize(("flag_type", "claim", "expected"), CASES)
def test_classification_matrix(flag_type: str, claim: str, expected: str) -> None:
    assert classify(flag_type, claim).theme == expected


def test_the_invented_omitted_split_is_real() -> None:
    """One judge type, two themes, opposite fixes — the reason the taxonomy exists."""
    invented = classify("missing_or_invented_feature", "Fort measures blood pressure.")
    omitted = classify("missing_or_invented_feature", "Fort does not track heart rate.")
    assert invented.theme == Theme.FEATURE_INVENTED.value
    assert omitted.theme == Theme.FEATURE_OMITTED.value
    assert invented.theme != omitted.theme


def test_every_flag_type_maps_to_a_theme() -> None:
    """Spec acceptance: full coverage of AccuracyFlagType."""
    for t in AccuracyFlagType:
        assert t.value in TYPE_DEFAULTS, f"{t.value} has no default theme"
        assert TYPE_DEFAULTS[t.value] in Theme


def test_no_flag_can_produce_none_even_with_empty_text() -> None:
    """Spec acceptance: classification is total."""
    for t in AccuracyFlagType:
        result = classify(t.value, "")
        assert result.theme
        assert result.theme != Theme.UNCLASSIFIED.value
        assert result.title


def test_an_unknown_flag_type_with_no_matching_rule_is_unclassified_not_guessed() -> None:
    result = classify("some_future_flag_type", "")
    assert result.theme == Theme.UNCLASSIFIED.value
    assert result.classified_by == "none"


def test_classification_is_deterministic() -> None:
    claim = "Fort measures blood pressure and ECG."
    assert classify("missing_or_invented_feature", claim) == classify(
        "missing_or_invented_feature", claim
    )


def test_reality_text_breaks_ties_for_claims_too_terse_to_match() -> None:
    """A one-word claim carries no signal; the correction names the dimension."""
    terse = classify("some_future_flag_type", "No.", reality="Open 24/7 for emergency calls.")
    assert terse.theme == Theme.AVAILABILITY_GEOGRAPHY.value


def test_coverage_is_reported_not_averaged_away() -> None:
    classifications = [
        classify("identity", "There isn't a widely recognized brand called 'Fort'."),
        classify("missing_or_invented_feature", "zzz"),  # falls through to the type default
        classify("some_future_flag_type", "zzz"),  # nothing matches
    ]
    cov = coverage(classifications)
    assert (cov.total, cov.by_rule, cov.by_type_default, cov.unclassified) == (3, 1, 1, 1)
    assert cov.unclassified_rate == pytest.approx(1 / 3)
    assert cov.type_default_rate == pytest.approx(1 / 3)


def test_coverage_of_an_empty_run_does_not_divide_by_zero() -> None:
    cov = coverage([])
    assert cov.unclassified_rate == 0.0 and cov.type_default_rate == 0.0


def test_every_theme_has_a_client_facing_label_with_no_internal_id() -> None:
    for t in Theme:
        label = theme_label(t.value)
        assert label and label != t.value
        assert "_" not in label
    assert set(THEME_LABELS) == {t.value for t in Theme}


def test_titles_are_templates_keyed_off_the_rule_not_scraped_from_model_prose() -> None:
    """A title built from the claim would inherit the phrasing under audit."""
    for rule in RULES:
        assert "{client}" in rule.title or rule.title.startswith("Models")
    title = classify("wrong_pricing", "The Fort band costs $349.").title
    assert "349" not in title
    assert title.format(client="Fort") == "Fort's pricing is stated wrongly"


def test_rule_ids_are_unique_so_a_classification_is_traceable() -> None:
    ids = [r.rule_id for r in RULES]
    assert len(ids) == len(set(ids))


# --- regressions found on the real Fort run (ff231808) -------------------------


@pytest.mark.parametrize(
    "claim",
    [
        "expected to ship in Q3 2026",
        "shipping starting June 2026 according to Fort's YC launch page",
        "expected to begin shipping in Q3 2026. Some sources indicate June 2026",
        "Batch 1 ships Q3 2026",
        "deliveries are scheduled for the third quarter of 2026",
    ],
)
def test_ship_date_phrasing_is_a_lifecycle_finding(claim: str) -> None:
    """The most common lifecycle error the engines make about a pre-launch product.

    None of the original patterns caught it, so 94 real observations fell through
    to whichever general rule matched the surrounding prose — two of them landing
    in `source_citation_quality` purely because the sentence said "according to".
    """
    assert classify("stale", claim).theme == Theme.LIFECYCLE_STATUS.value


def test_incidental_attribution_language_does_not_make_it_a_source_finding() -> None:
    """Source quality is the LAST rule because it is the most general.

    "According to" and "some sources" appear inside claims whose real error is
    something else; a stale ship date cited to a launch page is a lifecycle
    finding, and its fix is a dated status page, not a PR campaign.
    """
    assert RULES[-1].rule_id == "source.citation_quality"
    themed = classify("stale", "According to several sources it ships in Q3 2026.")
    assert themed.theme == Theme.LIFECYCLE_STATUS.value


def test_the_reality_tiebreaker_only_fires_for_a_claim_too_terse_to_read() -> None:
    """The correction describes the FIX, not the error.

    Reading it as the error is wrong whenever the claim can speak for itself —
    which is how a shipping-date error got filed under "weak sources" because the
    fact-sheet line it contradicted happened to mention the press.
    """
    # Terse claim: the correction is the only signal available.
    assert (
        classify("some_future_flag_type", "No.", reality="Open 24/7 for emergency calls.").theme
        == Theme.AVAILABILITY_GEOGRAPHY.value
    )
    # A claim that states a fact is themed on ITSELF, whatever the correction says.
    stated = classify(
        "stale",
        "It is expected to ship in Q3 2026.",
        reality="Live order page says Ships Q2 2027 (press's Q3 2026 is stale).",
    )
    assert stated.theme == Theme.LIFECYCLE_STATUS.value


def test_the_rules_fingerprint_is_pinned() -> None:
    """A theme-rule change must be a DELIBERATE act with a visible diff.

    Cards are keyed on theme and the lifecycle asks "was this theme open last
    cycle", so moving findings between themes is a change to what a client is
    told. Adding the ship-date pattern moved ~90 real Fort observations between
    two themes — a strict improvement, and exactly the kind of edit that should
    never happen by accident.

    If this fails and the change was intended, update the constant in the same
    commit as the rule. Same discipline as the judge prompt fingerprint.
    """
    from src.pipeline.themes import rules_fingerprint

    assert rules_fingerprint() == "8d6bfe3d15aaa6fc", (
        "theme rules changed — update this pin in the same commit, and note that "
        "both cycles are re-classified with the current rules on every render, so "
        "the comparison stays valid"
    )


def test_the_fingerprint_moves_when_a_rule_moves() -> None:
    """Otherwise the pin above is decoration."""
    import src.pipeline.themes as themes_mod
    from src.pipeline.themes import Theme, rules_fingerprint

    before = rules_fingerprint()
    original = themes_mod.RULES
    try:
        themes_mod.RULES = (*original, themes_mod.Rule("x.test", Theme.COMPANY_FACTS, "t", ()))
        assert rules_fingerprint() != before
    finally:
        themes_mod.RULES = original
    assert rules_fingerprint() == before
