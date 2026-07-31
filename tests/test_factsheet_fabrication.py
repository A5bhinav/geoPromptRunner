"""Two fabrication defects found by code review, and the controls that keep the fixes honest.

Both defects produced a FALSE FACT that passed the §4.1 quote gate, because the
quote was real and the interpretation was not. That is the dangerous shape: the
gate checks that we quoted the page, not that we understood it. Each fabricated
line then becomes the judge's ground truth for a `wrong_contact` / `wrong_hours`
flag, so the sheet accuses an engine of getting wrong something the business never
said — in a document we send a stranger.

Every test here is paired: the fabrication must not come back, AND the real case
the fix could plausibly have broken must still work. A fix that silences both is
not a fix.
"""

from __future__ import annotations

from src.audit.factsheet.extract import (
    claims_from_html,
    claims_from_json_ld,
    derive_negative_claims,
)

_URL = "https://fortplumbing.example/"
_AS_OF = "2026-07-31"


def _footer(*lines: str) -> str:
    body = "".join(f"<p>{line}</p>" for line in lines)
    return f"<html><body><footer>{body}</footer></body></html>"


def _addresses(html: str) -> list[str]:
    return [c.value for c in claims_from_html(html, _URL, _AS_OF) if c.key == "contact_address"]


def _hours(node: dict[str, object]) -> tuple[list[str], list[str]]:
    claims = claims_from_json_ld([node], _URL, _AS_OF)
    positives = [c.value for c in claims if c.key.startswith("hours_")]
    negatives = [c.value for c in derive_negative_claims(claims)]
    return positives, negatives


def _business(**over: object) -> dict[str, object]:
    return {"@type": "LocalBusiness", "name": "Fort Plumbing", **over}


# --- Defect 1: a number followed by anything was treated as a street ----------


def test_open_7_days_above_a_city_line_is_not_an_address() -> None:
    """The reported case. `\\b\\d{1,6}\\s+\\S` matched "7 days" in "Open 7 days"."""
    assert _addresses(_footer("Open 7 days", "Berkeley, CA 94702")) == []


def test_no_prose_line_ending_in_a_number_becomes_a_street() -> None:
    for prose in (
        "Serving Berkeley since 1998",
        "Call 24 hours",
        "Over 30 years experience",
        "Licensed #12345",
    ):
        assert _addresses(_footer(prose, "Berkeley, CA 94702")) == [], prose


def test_a_real_two_line_address_still_extracts() -> None:
    # The control. A fix that also loses this is not a fix.
    assert _addresses(_footer("1234 Shattuck Ave", "Berkeley, CA 94702")) == [
        "1234 Shattuck Ave, Berkeley, CA 94702"
    ]


def test_a_single_line_address_still_extracts() -> None:
    got = _addresses(_footer("1234 Shattuck Ave, Berkeley, CA 94702"))
    assert got == ["1234 Shattuck Ave, Berkeley, CA 94702"]


def test_common_street_types_and_a_suite_tail_survive() -> None:
    for street in (
        "500 N Main St",
        "12 Elm Street",
        "77 Sunset Blvd",
        "9 Oak Road",
        "1234 Shattuck Ave Suite 200",
    ):
        assert _addresses(_footer(street, "Berkeley, CA 94702")), street


def test_prose_ending_in_a_street_type_on_the_SAME_line_is_refused() -> None:
    """The residual of the same class, found by review after the first fix.

    Every prose fixture above puts the text on its own line, so they exercise only
    the two-line branch. The same-line branch searched for something street-shaped
    anywhere before the ZIP, and "road" is a thoroughfare type — so
    "Over 30 years on the road, Berkeley, CA 94702" shipped as the address.
    The fix is capitalisation: street names are proper nouns, prose is not.
    """
    assert _addresses(_footer("Over 30 years on the road, Berkeley, CA 94702")) == []


def test_lowercase_prose_before_a_street_type_never_forms_an_address() -> None:
    for prose in (
        "Serving every street in Berkeley, CA 94702",
        "We have come a long way, Berkeley, CA 94702",
        "Open 7 days a week on the road, Berkeley, CA 94702",
    ):
        assert _addresses(_footer(prose)) == [], prose


def test_a_capitalised_street_still_extracts_on_one_line() -> None:
    # The control for the capitalisation rule, both branches.
    assert _addresses(_footer("1234 Shattuck Ave, Berkeley, CA 94702")) == [
        "1234 Shattuck Ave, Berkeley, CA 94702"
    ]
    assert _addresses(_footer("3333 Martin Luther King Jr. Way", "Berkeley, CA 94703")) == [
        "3333 Martin Luther King Jr. Way, Berkeley, CA 94703"
    ]


def test_a_sentence_that_merely_ends_in_a_street_word_is_refused() -> None:
    # `search` for something street-shaped anywhere in the line is what let the
    # original bug through; the whole line must BE an address.
    assert _addresses(_footer("We serve every home along the way", "Berkeley, CA 94702")) == []


# --- Defect 2: absence conflated "not mentioned" with "could not read" --------


def test_a_declared_but_unreadable_saturday_never_becomes_closed_saturday() -> None:
    """The reported case: five parsed days cleared the threshold and closed the rest."""
    positives, negatives = _hours(
        _business(openingHours=["Mo-Fr 08:00-17:00", "Sa By appointment"])
    )
    assert "Closed Saturday." not in negatives
    # The whole block is refused: absence is only evidence of closure when
    # everything present was legible.
    assert (positives, negatives) == ([], [])


def test_an_unparseable_time_in_a_specification_refuses_the_block() -> None:
    _, negatives = _hours(
        _business(
            openingHoursSpecification=[
                {"dayOfWeek": "Monday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Tuesday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Wednesday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Thursday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Friday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Saturday", "opens": "by appointment", "closes": ""},
            ]
        )
    )
    assert negatives == []


def test_an_entry_with_no_attributable_day_refuses_the_block() -> None:
    # We cannot know WHICH days it covered, so no day is safe to call closed.
    _, negatives = _hours(
        _business(
            openingHoursSpecification=[
                {"dayOfWeek": "Monday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Tuesday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Wednesday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Thursday", "opens": "08:00", "closes": "17:00"},
                {"dayOfWeek": "Friday", "opens": "08:00", "closes": "17:00"},
                {"opens": "09:00", "closes": "13:00"},  # no dayOfWeek
            ]
        )
    )
    assert negatives == []


def test_a_complete_monday_to_saturday_week_still_closes_sunday() -> None:
    # The control: the feature has to survive its own hardening.
    positives, negatives = _hours(_business(openingHours=["Mo-Sa 08:00-17:00"]))
    assert len(positives) == 6
    assert negatives == ["Closed Sunday."]


def test_opens_equals_closes_is_understood_as_closed_not_unreadable() -> None:
    """A CMS spelling of "closed" is legible, so it must not veto the whole week."""
    _, negatives = _hours(
        _business(
            openingHoursSpecification=[
                {"dayOfWeek": d, "opens": "08:00", "closes": "17:00"}
                for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
            ]
            + [{"dayOfWeek": "Sunday", "opens": "00:00", "closes": "00:00"}]
        )
    )
    assert negatives == ["Closed Sunday."]


def test_a_lazily_marked_up_single_day_still_closes_nothing() -> None:
    # Pre-existing guard (_MIN_DAYS_FOR_CLOSED_WEEK), re-asserted: a site that
    # marks up only Monday has lazy markup, not a six-day closure.
    _, negatives = _hours(_business(openingHours=["Mo 08:00-17:00"]))
    assert negatives == []
