"""Competitor candidates from the local pack (competitor-set-plan C1).

A wrong competitor is subtler than a wrong fact and arguably worse: nobody
reading a report questions why a given shop is in the list. It silently shifts
every share-of-voice number, and stays invisible for as long as the client keeps
paying. So the tests are about what must NOT get in, and about the drops being
recorded rather than silent.
"""

from __future__ import annotations

from typing import Any

from src.audit.competitors import (
    DEFAULT_MAX_CANDIDATES,
    candidates_from_local_pack,
)

_QUERY = "best plumber in Berkeley"
_LOCATION = "Berkeley,California,United States"
_AS_OF = "2026-07-31"


def _entity(name: str, **over: Any) -> Any:
    base: dict[str, Any] = {
        "name": name,
        "address": "1 Main St, Berkeley, CA",
        "category": "Plumber",
        "rating": 4.6,
        "reviews": 120,
        "ludocid": None,
        "position": 1,
        "phone": None,
        "website": None,
    }
    base.update(over)
    return base


def _run(entities: list[Any], **over: Any) -> Any:
    kwargs: dict[str, Any] = {
        "client_name": "Fort Plumbing",
        "client_website": "https://fortplumbing.com",
        "source_query": _QUERY,
        "location": _LOCATION,
        "as_of": _AS_OF,
    }
    kwargs.update(over)
    return candidates_from_local_pack(entities, **kwargs)


# --- what must never get in ---------------------------------------------------


def test_the_client_is_never_its_own_competitor() -> None:
    out = _run([_entity("Fort Plumbing"), _entity("Ace Rooter")])
    assert out.names == ["Ace Rooter"]
    assert ("Fort Plumbing", "this is the client") in out.exclusions


def test_the_client_is_caught_by_website_even_under_a_trading_name() -> None:
    """A shop listed as "Fort Plumbing & Heating Co" is the same shop. Missed, it
    appears as its own rival and its share-of-voice splits across two entries."""
    out = _run([_entity("Fort Plumbing & Heating Co", website="https://www.fortplumbing.com/")])
    assert out.names == []


def test_the_client_is_caught_by_name_when_no_website_is_listed() -> None:
    out = _run([_entity("FORT PLUMBING, INC.")])
    assert out.names == []


def test_an_alias_also_counts_as_the_client() -> None:
    out = _run([_entity("Nahman Plumbing")], aliases=["Nahman Plumbing"])
    assert out.names == []


def test_directories_are_excluded_with_a_reason() -> None:
    """A report saying the client loses to Yelp is true and useless to the owner."""
    out = _run(
        [
            _entity("Yelp", website="https://www.yelp.com/search"),
            _entity("Angi", website="https://www.angi.com/companylist"),
            _entity("Thumbtack Home Services"),
            _entity("Ace Rooter"),
        ]
    )
    assert out.names == ["Ace Rooter"]
    assert len(out.exclusions) == 3
    assert all("directory" in reason for _n, reason in out.exclusions)


def test_a_nameless_listing_is_skipped() -> None:
    assert _run([_entity(""), _entity("   "), _entity("Ace Rooter")]).names == ["Ace Rooter"]


def test_duplicate_listings_collapse() -> None:
    out = _run([_entity("Ace Rooter"), _entity("ACE ROOTER LLC"), _entity("Bay Plumbing")])
    assert out.names == ["Ace Rooter", "Bay Plumbing"]
    assert ("ACE ROOTER LLC", "duplicate listing") in out.exclusions


# --- the cap, and saying what it dropped --------------------------------------


def test_the_cap_holds_and_records_what_it_dropped() -> None:
    # Silent truncation reads as "we looked and there were only five".
    out = _run([_entity(f"Shop {i}") for i in range(9)])
    assert len(out.candidates) == DEFAULT_MAX_CANDIDATES
    over = [n for n, reason in out.exclusions if "over the cap" in reason]
    assert len(over) == 9 - DEFAULT_MAX_CANDIDATES


def test_the_cap_is_configurable() -> None:
    assert len(_run([_entity(f"Shop {i}") for i in range(9)], max_candidates=3).candidates) == 3


# --- evidence, which is the whole point ---------------------------------------


def test_every_candidate_carries_the_listing_it_came_from() -> None:
    out = _run([_entity("Ace Rooter", category="Plumber", address="99 Elm St, Berkeley, CA")])
    candidate = out.candidates[0]
    assert candidate.source == "local_pack"
    # A reviewer checks the NAME against the listing; prose would not let them.
    assert "Ace Rooter" in candidate.evidence
    assert "Plumber" in candidate.evidence
    assert "99 Elm St" in candidate.evidence
    assert _QUERY in candidate.evidence
    assert _LOCATION in candidate.evidence
    assert candidate.as_of == _AS_OF


def test_googles_order_is_preserved() -> None:
    """Pack position is a real ranking signal. Re-sorting by rating would put our
    judgement where the market's belongs."""
    out = _run(
        [
            _entity("First", position=1, rating=3.9),
            _entity("Second", position=2, rating=5.0),
            _entity("Third", position=3, rating=4.4),
        ]
    )
    assert out.names == ["First", "Second", "Third"]


def test_an_empty_pack_yields_an_empty_set_not_a_guess() -> None:
    out = _run([])
    assert out.names == []
    assert out.exclusions == []


def test_the_names_property_is_the_shape_the_csv_wants() -> None:
    out = _run([_entity("Ace Rooter"), _entity("Bay Plumbing")])
    assert ";".join(out.names) == "Ace Rooter;Bay Plumbing"
