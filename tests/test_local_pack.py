"""Local-pack capture: the surface that actually answers local-intent queries.

Two things are under test. The **parser**, against field names verified from a live
Serper response rather than docs (the 2026-07-27 location-format bug came from trusting
docs and unit-testing our own wrong string). And the **non-goal**: a local pack is a
ranked business list, not an answer, so it must never reach the judge, `mention_rate`,
`share_of_model` or the visibility grade.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.api.reports import build_local_pack_payload, build_report
from src.engines import local_pack as lp
from src.engines.local_pack import (
    LocalEntity,
    LocalPackCapture,
    fetch_local_pack,
    parse_serper_places,
)
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import QueryResult

# A real Serper /places body, trimmed. Field names captured live on 2026-07-28:
# title / address / category / rating / ratingCount / cid / position / phoneNumber /
# website. NOTE the two name mismatches against SearchApi — ratingCount (not reviews)
# and cid (not ludocid) — which are exactly what a docs-written parser gets wrong.
_SERPER_BODY: dict[str, Any] = {
    "searchParameters": {"q": "plumber", "location": "Berkeley,California,United States"},
    "places": [
        {
            "position": 1,
            "title": "Albert Nahman Plumbing, Heating, and Cooling",
            "address": "3333 Martin Luther King Jr Way, Berkeley, CA 94703",
            "rating": 4.7,
            "ratingCount": 3400,
            "category": "Plumber",
            "phoneNumber": "(510) 408-7879",
            "website": "https://albertnahmanplumbing.com/",
            "cid": "4379385316968292002",
        },
        # No address (Serper often omits it), no website — must still parse.
        {
            "position": 2,
            "title": "LemonTree Plumbing",
            "rating": 5,
            "ratingCount": 30,
            "category": "Plumber",
            "phoneNumber": "(510) 502-7843",
            "cid": "7570472887024032851",
        },
        {"position": 3, "title": "   "},  # nameless once trimmed -> dropped
        "not-a-dict",  # malformed row -> dropped, never raises
    ],
}


def test_parses_the_real_serper_field_names() -> None:
    entities = parse_serper_places(_SERPER_BODY)
    assert [e["name"] for e in entities] == [
        "Albert Nahman Plumbing, Heating, and Cooling",
        "LemonTree Plumbing",
    ]
    first = entities[0]
    assert first["rating"] == 4.7
    assert first["reviews"] == 3400  # Serper calls this ratingCount
    assert first["ludocid"] == "4379385316968292002"  # Serper calls this cid
    assert first["phone"] == "(510) 408-7879"
    assert first["website"] == "https://albertnahmanplumbing.com/"
    assert first["category"] == "Plumber"
    # Absent fields become None, not "" or a crash.
    assert entities[1]["address"] == ""
    assert entities[1]["website"] is None


def test_serper_cid_lands_in_the_ludocid_field() -> None:
    """The field keeps its old name on purpose.

    Serper calls Google's stable business id `cid`; the SearchApi capture this replaced
    called the SAME value `ludocid` (verified on a shared business before that vendor was
    removed). Landing it under the original name is what lets a pack captured before
    2026-07-28 join against one captured after — otherwise a vendor change would read as
    the client's entire market turning over.
    """
    entity = parse_serper_places(_SERPER_BODY)[0]
    assert entity["ludocid"] == _SERPER_BODY["places"][0]["cid"]


def test_capture_refuses_an_unpinned_location() -> None:
    # A pack from the wrong metro is worse than no pack (the W4.2 brief's #1 error).
    assert fetch_local_pack("best plumber in Berkeley", "") == ([], lp.SOURCE_NONE)
    assert fetch_local_pack("best plumber in Berkeley", "   ") == ([], lp.SOURCE_NONE)


def test_a_vendor_failure_is_reported_as_measuring_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-vendor since SearchApi was removed, so this distinction carries the weight.

    A Serper failure must surface as SOURCE_NONE — "we measured nothing" — never as an
    empty pack, which a reader would take as "no competitors in this market".
    """
    monkeypatch.setattr(lp, "_fetch_serper", lambda q, loc: None)
    assert fetch_local_pack(
        "best plumber in Berkeley", "Berkeley,California,United States"
    ) == ([], lp.SOURCE_NONE)


def test_an_empty_pack_from_a_working_vendor_is_a_real_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the same distinction: `[]` with SOURCE_SERPER means Serper
    answered and this query genuinely surfaced no local pack."""
    monkeypatch.setattr(lp, "_fetch_serper", lambda q, loc: [])
    assert fetch_local_pack("x", "Berkeley,California,United States") == ([], lp.SOURCE_SERPER)


def _capture(query_id: str, names: list[str]) -> LocalPackCapture:
    return LocalPackCapture(
        query_id=query_id,
        prompt=f"query {query_id}",
        source=lp.SOURCE_SERPER,
        entities=[
            LocalEntity(
                name=n,
                address="",
                category="Plumber",
                rating=None,
                reviews=None,
                ludocid=None,
                position=i + 1,
                phone=None,
                website=None,
            )
            for i, n in enumerate(names)
        ],
    )


def test_client_rank_survives_a_longer_google_listing() -> None:
    """A shop's Google listing is routinely longer than the name on its own site. Exact
    equality would report a present business as absent — the one error this must not
    make, since the whole point is telling an owner where they rank."""
    payload = build_local_pack_payload(
        [_capture("loc-01", ["Rival Rooter", "Albert Nahman Plumbing, Heating, and Cooling"])],
        "Albert Nahman Plumbing",
        "Berkeley,California,United States",
    )
    assert payload is not None
    assert payload["client_positions"] == {"loc-01": 2}
    assert [r["is_client"] for r in payload["entities"]] == [False, True]


def test_an_absent_client_is_recorded_as_none_not_omitted() -> None:
    # "Not in your own city's pack" is the finding. Dropping the key would make it
    # indistinguishable from a query we never captured.
    payload = build_local_pack_payload(
        [_capture("loc-01", ["Rival Rooter", "Other Plumbing"])],
        "Albert Nahman Plumbing",
        "Berkeley,California,United States",
    )
    assert payload is not None
    assert payload["client_positions"] == {"loc-01": None}


def test_no_captures_means_no_payload() -> None:
    assert build_local_pack_payload([], "Acme", "Berkeley,California,United States") is None


def test_the_local_pack_never_moves_a_visibility_metric() -> None:
    """The explicit non-goal. A pack is a ranked business list, not an answer; if it
    leaked into the answer path it would be judged for prominence/framing and averaged
    into mention_rate beside real AI answers."""
    outcome = AuditOutcome(
        run_id="r1",
        client_name="Albert Nahman Plumbing",
        client_domains=["albertnahmanplumbing.com"],
        competitors=["LemonTree Plumbing"],
        query_set_version="v1",
        runs_per_query=1,
        results=[
            QueryResult(
                query_id="loc-01",
                intent="local_intent",
                prompt="best plumber in Berkeley",
                engine_name="perplexity",
                run_index=0,
                response="LemonTree Plumbing is a good option.",
                citations=[],
                timestamp="t",
            )
        ],
    )
    pack = build_local_pack_payload(
        [_capture("loc-01", ["Albert Nahman Plumbing, Heating, and Cooling"])],
        "Albert Nahman Plumbing",
        "Berkeley,California,United States",
    )
    without = build_report(outcome)
    with_pack = build_report(outcome, local_pack=pack)

    # The client tops the local pack but is absent from the AI answer. Those must stay
    # separate numbers: every visibility figure is byte-identical either way.
    assert with_pack["local_pack"] is not None
    assert with_pack["local_pack"]["client_positions"] == {"loc-01": 1}
    assert without["local_pack"] is None
    for key in ("scorecard", "leaderboard", "by_bucket", "engines", "dead_engines"):
        assert with_pack[key] == without[key], f"local pack leaked into {key}"


def test_consumer_runs_have_no_local_pack_block() -> None:
    outcome = AuditOutcome(
        run_id="r1",
        client_name="Acme",
        client_domains=[],
        competitors=[],
        query_set_version="v1",
        runs_per_query=1,
        results=[
            QueryResult(
                query_id="cat-01",
                intent="category",
                prompt="best budgeting app",
                engine_name="openai",
                run_index=0,
                response="Acme is good.",
                citations=[],
                timestamp="t",
            )
        ],
    )
    assert build_report(outcome)["local_pack"] is None
