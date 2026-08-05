"""Crawled claims → seeded cards: every branch, offline, for nothing.

WHY THIS FILE IS ADVERSARIAL RATHER THAN HAPPY-PATH. A prefill is a sentence put
in front of an owner who is about to vouch for it. A blank field costs one
question; a MANGLED field — "The business has operated since Founded 1998." — is
a wrong line the owner confirms with one tap and the judge then grades real
answers against. So the tests that matter here are the ones where the extractor's
phrasing and the control's shape disagree, and the rule they enforce is: when a
pattern does not match exactly, produce NOTHING.

The other half is the wiring. Six builders point at question ids by string, and a
builder keyed to an id the registry renamed is a silent no-op — the crawl runs,
the claims are stored, and the card still opens blank with nobody the wiser. That
is what `test_every_builder_points_at_a_real_card` exists to catch.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.audit.factsheet.intake import (
    PREFILLED_QUESTIONS,
    Answer,
    assertions_for,
    has_prefill,
    prefill_answer,
    question,
)
from src.audit.factsheet.intake.questions import REGISTRY

AS_OF = "2026-08-04"
BUSINESS = "Nahman Plumbing"


def _entry(value: str) -> dict[str, Any]:
    """One prefill row as the session stores it."""
    return {
        "value": value,
        "source_url": "https://example.com/",
        "source_kind": "site_jsonld",
        "confidence": "high",
    }


def _prefill(**values: str) -> dict[str, Any]:
    return {k: _entry(v) for k, v in values.items()}


# --- the wiring ---------------------------------------------------------------


def test_every_builder_points_at_a_real_card() -> None:
    """A builder keyed to an id the registry dropped is a silent no-op: the crawl
    runs, the claims are stored, and the card opens blank anyway."""
    ids = {q.id for q in REGISTRY}
    assert PREFILLED_QUESTIONS <= ids, PREFILLED_QUESTIONS - ids


def test_a_card_with_nothing_crawled_is_not_prefilled() -> None:
    """Blank is the default and it has to stay reachable: ten of the sixteen
    cards can never be prefilled, because nothing in markup says what you don't
    do or who people confuse you with."""
    for q in REGISTRY:
        assert prefill_answer(q, {}) is None
        assert has_prefill(q, {}) is False


def test_the_cards_a_crawl_cannot_speak_to_stay_blank() -> None:
    """The negative cards are where the sheet earns its keep, and no extractor
    may fill them: absence in an open enumeration is "not mentioned", never "does
    not offer" (§4.4)."""
    everything = _prefill(
        identity_name="Nahman Plumbing",
        services_offered="Services offered include drain cleaning and repiping.",
        contact_phone="(510) 555-0100",
        hours_monday="Open 08:00-17:00.",
    )
    for qid in ("Q-WHAT-03", "Q-WHAT-04", "Q-OFFER-02", "Q-COST-01", "Q-AI-01", "Q-AI-02"):
        assert prefill_answer(question(qid), everything) is None


# --- taking the extractor's sentences apart -----------------------------------


def test_the_founding_sentence_becomes_a_year() -> None:
    """`"Founded 1998."` is what the sheet says; `"1998"` is what the card holds.
    Seeding the sentence produced "The business has operated since Founded
    1998." — a line an owner confirms with one tap."""
    built = prefill_answer(question("Q-WHAT-01"), _prefill(identity_founded="Founded 1998-03-01."))
    assert built == {"identity_founded": "1998"}


def test_a_founding_date_we_cannot_parse_is_passed_through_not_guessed() -> None:
    built = prefill_answer(question("Q-WHAT-01"), _prefill(identity_founded="Founded the 1970s."))
    assert built == {"identity_founded": "the 1970s"}


def test_the_category_keeps_its_article() -> None:
    """The assertion template is "It is {v}." — the sheet's line has to read as
    English in front of a client."""
    built = prefill_answer(question("Q-WHAT-01"), _prefill(identity_category="It is a plumber."))
    assert built == {"identity_category": "a plumber"}


def test_a_sentence_that_is_not_the_extractors_yields_nothing() -> None:
    """The patterns are anchored on purpose. A loose match puts a mangled value
    in front of somebody about to vouch for it, and that is on the sheet
    forever."""
    for value in ("Established 1998.", "We were founded in 1998", "1998"):
        assert prefill_answer(question("Q-WHAT-01"), _prefill(identity_founded=value)) is None


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Serves Berkeley.", ["Berkeley"]),
        ("Serves Berkeley and Oakland.", ["Berkeley", "Oakland"]),
        ("Serves Berkeley, Oakland and Albany.", ["Berkeley", "Oakland", "Albany"]),
    ],
)
def test_the_oxford_list_comes_apart_the_way_it_went_together(
    sentence: str, expected: list[str]
) -> None:
    built = prefill_answer(question("Q-REACH-02"), _prefill(service_area_towns=sentence))
    assert built == {"scope": "places", "included": expected}


def test_the_lead_forms_area_is_one_item_because_it_was_never_a_list() -> None:
    built = prefill_answer(question("Q-REACH-02"), _prefill(service_area_primary="East Bay"))
    assert built == {"scope": "places", "included": ["East Bay"]}


def test_marked_up_areas_beat_whatever_a_lead_form_said() -> None:
    built = prefill_answer(
        question("Q-REACH-02"),
        _prefill(
            service_area_towns="Serves Berkeley and Oakland.",
            service_area_primary="East Bay",
        ),
    )
    assert built == {"scope": "places", "included": ["Berkeley", "Oakland"]}


def test_the_service_area_is_never_prefilled_with_an_exclusion() -> None:
    """The excluded half has no other producer anywhere in the system and the
    extractor is forbidden from deriving one — absence in an `areaServed` list
    means "not mentioned"."""
    built = prefill_answer(question("Q-REACH-02"), _prefill(service_area_towns="Serves Berkeley."))
    assert isinstance(built, dict)
    assert "excluded" not in built


def test_the_services_sentence_becomes_chips() -> None:
    built = prefill_answer(
        question("Q-OFFER-01"),
        _prefill(
            services_offered=(
                "Services offered include drain cleaning, repiping and leak detection."
            )
        ),
    )
    assert built == ["drain cleaning", "repiping", "leak detection"]


# --- the hours grid, which was dropping everything the crawler found ----------


def test_the_hours_grid_seeds_from_seven_separate_claims() -> None:
    """THE CARD THIS WHOLE MODULE EXISTS FOR. The extractor emits one
    `hours_{day}` claim per day and the card's grid is a single part called
    `days`, so nothing ever matched and every crawled week was thrown away."""
    built = prefill_answer(
        question("Q-REACH-03"),
        _prefill(
            hours_monday="Open 08:00-17:00.",
            hours_tuesday="Open 08:00-17:00.",
            hours_sunday="Closed Sunday.",
        ),
    )
    assert built == {
        "scope": "set_hours",
        "days": {"monday": "08:00-17:00", "tuesday": "08:00-17:00", "sunday": "closed"},
    }


def test_a_crawled_closure_arrives_as_the_closed_toggle() -> None:
    """"closed", lowercase, is what the grid's toggle and `_availability` both
    test for. Any other spelling renders as text typed into a time field and
    asserts "Open Sunday Closed Sunday."."""
    built = prefill_answer(question("Q-REACH-03"), _prefill(hours_sunday="Closed Sunday."))
    assert built == {"scope": "set_hours", "days": {"sunday": "closed"}}


def test_the_grids_scope_is_set_or_the_grid_never_renders() -> None:
    """`days` is `show_when=("scope", "set_hours")`. Seeding the grid without the
    scope fills a control nobody can see."""
    built = prefill_answer(question("Q-REACH-03"), _prefill(hours_monday="Open 08:00-17:00."))
    assert isinstance(built, dict)
    assert built["scope"] == "set_hours"


def test_after_hours_is_never_guessed_from_opening_hours() -> None:
    """Published hours say nothing about whether there is an on-call number, and
    "No after-hours service." is a claim the judge grades."""
    built = prefill_answer(question("Q-REACH-03"), _prefill(hours_monday="Open 08:00-17:00."))
    assert isinstance(built, dict)
    assert "after_hours" not in built


# --- the round trip, which is the only thing that actually matters ------------


@pytest.mark.parametrize(
    ("qid", "prefill", "expected"),
    [
        (
            "Q-WHAT-01",
            {"identity_founded": "Founded 1998.", "identity_category": "It is a plumber."},
            {"The business has operated since 1998.", "It is a plumber."},
        ),
        (
            "Q-REACH-03",
            {"hours_sunday": "Closed Sunday.", "hours_monday": "Open 08:00-17:00."},
            {"Closed Sunday.", "Open Monday 08:00-17:00."},
        ),
        (
            "Q-REACH-02",
            {"service_area_towns": "Serves Berkeley and Oakland."},
            {"The service area is Berkeley and Oakland."},
        ),
        (
            "Q-OFFER-01",
            {"services_offered": "Services offered include drain cleaning and repiping."},
            {"Services offered: drain cleaning and repiping."},
        ),
        (
            "Q-REACH-01",
            {"contact_phone": "(510) 555-0100"},
            {"The published phone number is (510) 555-0100."},
        ),
    ],
)
def test_a_seeded_card_sent_unchanged_produces_a_clean_sentence(
    qid: str, prefill: dict[str, str], expected: set[str]
) -> None:
    """THE TEST THAT WOULD HAVE CAUGHT THE ORIGINAL BUG. A prefill is a draft
    ANSWER, so submitting it untouched has to yield the same sentence a person
    typing the same thing would get. Anything that reads oddly here reads oddly
    on a document a client signs.

    The date stamps `_stamped` appends to volatile keys are dropped before
    comparing: they are the clock, not the phrasing, and they are pinned by
    `test_volatile_keys_carry_their_date` already.
    """
    q = question(qid)
    built = prefill_answer(q, _prefill(**prefill))
    assert built is not None, f"{qid} produced no prefill from {prefill}"
    assertions = assertions_for(
        q, Answer(question_id=qid, value=built), as_of=AS_OF, business_name=BUSINESS
    )
    sentences = {a.value.split(" (as of ")[0].rstrip(".") + "." for a in assertions}
    assert sentences == expected
