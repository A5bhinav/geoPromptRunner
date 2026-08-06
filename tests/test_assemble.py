"""Assembling a runnable audit CSV from a lead.

The output is not a document — it is an INPUT to a measurement that costs money
and gets sent to a stranger. So the tests care about two things: it must parse
through the real `csv_loader` (a CSV that looks right and fails to parse is worse
than none), and it must refuse rather than guess the inputs that silently
mis-aim a run.
"""

from __future__ import annotations

import pytest

from src.prompts.assemble import DEFAULT_LOCAL_ENGINES, AssembleError, assemble_run_csv
from src.prompts.query_set import QUERY_SET_SIZE
from src.prompts.csv_loader import parse_csv_files


def _csv(**over: object) -> str:
    kwargs: dict[str, object] = {
        "business": "Albert Nahman Plumbing",
        "website": "https://www.albertnahmanplumbing.com/",
        "trade": "plumbing",
        "city": "Berkeley",
        "region": "California",
        "competitors": ["Ace Rooter", "Bay Plumbing"],
    }
    kwargs.update(over)
    return assemble_run_csv(**kwargs)  # type: ignore[arg-type]  # kwargs are the signature


def _parsed(**over: object):  # type: ignore[no-untyped-def]
    result = parse_csv_files([("assembled.csv", _csv(**over))])
    assert result.ok, result.errors
    return result.audit


# --- it must actually be runnable --------------------------------------------


def test_the_assembled_csv_parses_through_the_real_loader() -> None:
    # The whole point. A CSV that looks right and fails validation on upload has
    # moved the manual work rather than removed it.
    audit = _parsed()
    assert audit is not None
    # The standard size, not a literal: 29 was one of four numbers this repo
    # used to think a query set was, and a test asserting the old drift is how
    # the drift comes back.
    assert len(audit.query_set.queries) == QUERY_SET_SIZE


def test_config_comes_from_the_lead() -> None:
    cfg = _parsed().config
    assert cfg.client_name == "Albert Nahman Plumbing"
    assert cfg.client_domains == ["albertnahmanplumbing.com"]  # scheme and www stripped
    assert cfg.competitors == ["Ace Rooter", "Bay Plumbing"]
    assert cfg.location == "Berkeley,California,United States"
    assert cfg.engines == list(DEFAULT_LOCAL_ENGINES)


def test_no_template_slot_survives() -> None:
    """A literal "{city}" reaching an engine measures a question no customer asks
    and scores as a loss."""
    text = _csv()
    assert "{city}" not in text
    assert "{brand}" not in text
    assert "<STATE>" not in text


def test_the_geo_anchored_queries_name_the_real_city() -> None:
    """Not every query names the city, and that is correct — "plumber near me" is a
    real local query whose whole point is the absence of one, and the informational
    bucket ("why is my water pressure suddenly low?") measures problem-aware
    visibility, which carries no geography. What matters is that the ones the
    template DID anchor came out anchored to Berkeley."""
    texts = [q.text for q in _parsed().query_set.queries]
    anchored = [t for t in texts if "Berkeley" in t]
    assert len(anchored) >= 15, "the geo-anchored half of the set should name the city"
    # And nothing anywhere still carries a slot.
    assert not any("{" in t for t in texts)


def test_judging_is_off_by_default() -> None:
    # The prejudge flow makes judging free: run with it off, warm the cache on the
    # subscription, judge for $0.
    assert _parsed().config.judge is False
    assert _parsed(judge=True).config.judge is True


def test_no_fact_block_is_emitted() -> None:
    """The sheet attaches by id. A run carrying both a sheet and CSV fact rows is
    refused, so emitting them here would make every assembled run un-attachable."""
    assert "\\nfact," not in _csv()
    assert _parsed().fact_sheet is None


# --- what it refuses rather than guesses --------------------------------------


def test_an_abbreviated_region_is_refused() -> None:
    """DataForSEO returns zero tasks for an abbreviation and the surface comes back
    empty — which reads as the brand being absent. Verified on two vendors."""
    with pytest.raises(AssembleError, match="abbreviation"):
        _csv(region="CA")
    with pytest.raises(AssembleError, match="abbreviation"):
        _csv(region="Ca.")


def test_a_missing_city_is_refused() -> None:
    with pytest.raises(AssembleError, match="city is required"):
        _csv(city="  ")


def test_a_missing_region_is_refused() -> None:
    with pytest.raises(AssembleError, match="region is required"):
        _csv(region="")


def test_a_missing_business_is_refused() -> None:
    with pytest.raises(AssembleError, match="business name is required"):
        _csv(business=" ")


def test_an_unknown_trade_is_refused() -> None:
    with pytest.raises(AssembleError, match="unknown trade"):
        _csv(trade="landscaping")


# --- competitors --------------------------------------------------------------


def test_an_empty_competitor_list_still_assembles() -> None:
    # It produces a run that measures the client against nobody, which is a real
    # state the caller must be told about — the API returns a warning — but the CSV
    # itself is valid and a human may fill the row in.
    cfg = _parsed(competitors=[]).config
    assert cfg.competitors == []


def test_blank_competitor_entries_are_dropped() -> None:
    cfg = _parsed(competitors=["Ace Rooter", "  ", ""]).config
    assert cfg.competitors == ["Ace Rooter"]
