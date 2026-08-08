"""LIC-T1: companies are rows, and the projects response did not move.

The load-bearing test here is `test_company_rows_do_not_change_the_response`.
Turning a GROUP BY into a table is the kind of change that "works" while quietly
renaming a key or dropping a bucket, and every one of those is a broken URL in a
UI that already ships. So the assertion is not "the new path returns something
sensible" — it is that the new path and the old derivation return the SAME thing,
proved by running both against one fixture.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.api import projects, runner
from src.api.company_keys import key_for, norm_domain
from src.storage import db
from scripts.backfill_companies import check_collisions, derive


# --- fixture: four shapes that must all survive ------------------------------
#
# fort.cx       runs AND teasers, tenanted        (the ordinary case)
# calai.app     teasers ONLY, tenanted            (spec: "with a teaser-only
#                                                  project in the fixture")
# drafted.ai    a run with NO company_id          (the derivation fallback)
# name:oura     no domain at all, tenanted        (the name-slug key; one real
#                                                  instance exists in production)

_COMPANIES = [
    db.Company(id="c-fort", name="fort.cx", slug="fort.cx", domain="fort.cx",
               managing_agency_id=None),
    db.Company(id="c-calai", name="calai.app", slug="calai.app", domain="calai.app",
               managing_agency_id=None),
    db.Company(id="c-oura", name="Oura", slug="name:oura", domain=None,
               managing_agency_id=None),
]

_RUN_ROWS: list[dict[str, object]] = [
    {"id": "r1", "client_domains": ["https://www.fort.cx/pricing"], "company_id": "c-fort"},
    {"id": "r2", "client_domains": [], "company_id": "c-oura"},
    # Untenanted on purpose: a run created since the last backfill.
    {"id": "r3", "client_domains": ["drafted.ai"], "company_id": None},
]

_TEASER_ROWS: list[dict[str, object]] = [
    {"id": "t1", "company_name": "FORT", "status": "sent", "created_at": "2026-01-02",
     "prospect_url": "https://fort.cx", "company_id": "c-fort"},
    {"id": "t2", "company_name": "Cal AI", "status": "draft", "created_at": "2026-01-03",
     "prospect_url": "https://calai.app/x", "company_id": "c-calai"},
]


@dataclasses.dataclass(frozen=True)
class _Summary:
    """Stand-in for runner.RunSummary — only the fields _collect() reads."""

    run_id: str
    client_name: str
    state: str
    created_at: str
    n_queries: int
    engines: list[str]


_RUN_SUMMARIES = [
    _Summary("r1", "FORT", "done", "2026-01-05", 25, ["openai"]),
    _Summary("r2", "Oura", "done", "2026-01-04", 25, ["openai", "anthropic"]),
    _Summary("r3", "Drafted", "done", "2026-01-06", 10, ["openai"]),
]


def _install(monkeypatch: pytest.MonkeyPatch, *, companies: bool) -> None:
    """Point the module at the fixture. ``companies=False`` simulates both a
    pre-backfill database and an unreachable one — the derivation-only path."""
    if companies:
        monkeypatch.setattr(db, "list_companies", lambda *a, **k: list(_COMPANIES))
    else:
        def _down(*_a: object, **_k: object) -> list[db.Company]:
            raise db.StorageError("storage down")

        monkeypatch.setattr(db, "list_companies", _down)
    monkeypatch.setattr(db, "list_all_audit_runs", lambda *a, **k: list(_RUN_ROWS))
    monkeypatch.setattr(db, "list_teasers_with_url", lambda *a, **k: list(_TEASER_ROWS))
    monkeypatch.setattr(runner, "list_runs", lambda *a, **k: list(_RUN_SUMMARIES))


def test_company_rows_do_not_change_the_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of LIC-T1: same fixture, same answer, rows or no rows.

    With company rows present every run/teaser is bucketed by `company_id`;
    without them every one is bucketed by the derived key. If those two ever
    disagree, a client's URL changes under them or two clients merge — so this
    compares the FULL serialized response, not a count.
    """
    _install(monkeypatch, companies=True)
    with_rows = [dataclasses.asdict(p) for p in projects.list_projects()]

    _install(monkeypatch, companies=False)
    derived_only = [dataclasses.asdict(p) for p in projects.list_projects()]

    assert with_rows == derived_only


def test_the_four_fixture_shapes_all_appear(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, companies=True)
    by_key = {p.key: p for p in projects.list_projects()}

    assert set(by_key) == {"fort.cx", "calai.app", "drafted.ai", "name:oura"}

    # Runs and teasers roll into ONE project, not two.
    assert (by_key["fort.cx"].audit_count, by_key["fort.cx"].teaser_count) == (1, 1)
    # A teaser-only prospect is still a project (it has no audit_runs row at all).
    assert (by_key["calai.app"].audit_count, by_key["calai.app"].teaser_count) == (0, 1)
    # An untenanted run still shows, via the derivation fallback.
    assert by_key["drafted.ai"].audit_count == 1
    # The name-slug key keeps its human label rather than becoming its slug.
    assert by_key["name:oura"].label == "Oura"
    assert by_key["name:oura"].domain is None


def test_a_company_with_no_work_yet_resolves_but_is_not_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An agency that just added a client must be able to click into it.

    It is deliberately absent from `list_projects()` (an empty card reads as a
    bug) but `get_project` resolves it, because landing on "no such project"
    immediately after creating one reads as a broken product.
    """
    empty = db.Company(id="c-new", name="newclient.com", slug="newclient.com",
                       domain="newclient.com", managing_agency_id="org-1")
    monkeypatch.setattr(db, "list_companies", lambda *a, **k: [*_COMPANIES, empty])
    monkeypatch.setattr(db, "list_all_audit_runs", lambda *a, **k: list(_RUN_ROWS))
    monkeypatch.setattr(db, "list_teasers_with_url", lambda *a, **k: list(_TEASER_ROWS))
    monkeypatch.setattr(runner, "list_runs", lambda *a, **k: list(_RUN_SUMMARIES))
    monkeypatch.setattr(db, "get_company_by_slug", lambda slug: empty if slug == "c-new" or slug == "newclient.com" else None)

    assert "newclient.com" not in {p.key for p in projects.list_projects()}

    detail = projects.get_project("newclient.com")
    assert detail is not None
    assert (detail.key, detail.label, detail.audits, detail.teasers) == (
        "newclient.com", "newclient.com", [], [],
    )


def test_unknown_key_is_still_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, companies=True)
    monkeypatch.setattr(db, "get_company_by_slug", lambda slug: None)
    assert projects.get_project("nope.example") is None


# --- the backfill's own guarantees -------------------------------------------


def test_backfill_derives_the_same_keys_the_ui_shows() -> None:
    """`derive()` must bucket exactly as `_collect()` does — it is the same
    functions, and this asserts they were actually wired that way."""
    derived = derive(
        runs=[("r1", "FORT", ["https://www.fort.cx/pricing"]), ("r2", "Oura", [])],
        teasers=[("t1", "Cal AI", "https://calai.app/x")],
    )
    assert set(derived) == {"fort.cx", "name:oura", "calai.app"}
    assert derived["fort.cx"].run_ids == ["r1"]
    assert derived["fort.cx"].domain == "fort.cx"
    assert derived["name:oura"].label == "Oura"
    assert derived["name:oura"].domain is None
    assert derived["calai.app"].teaser_ids == ["t1"]


def test_a_fact_sheet_domain_is_a_company_even_with_no_run_or_teaser() -> None:
    """The gap the live backfill exposed, now a regression test.

    `projects._collect()` has only ever known two identity sources, runs and
    teasers. A business can have a fact sheet and an intake conversation before
    either exists — `blackpropeller.com` was exactly that in production, with 36
    claims and no measurement. Deriving from two sources left its sheet with no
    tenant, and an untenanted row under RLS is a row nobody can read, including
    the client it belongs to.
    """
    derived = derive(
        runs=[("r1", "FORT", ["fort.cx"])],
        teasers=[],
        sheet_domains=[("blackpropeller.com", "Black Propeller")],
    )
    assert set(derived) == {"fort.cx", "blackpropeller.com"}
    sheet_only = derived["blackpropeller.com"]
    assert sheet_only.domain == "blackpropeller.com"
    # It has no work yet, which is precisely why `list_projects()` drops it while
    # `get_project` still resolves it.
    assert sheet_only.run_ids == [] and sheet_only.teaser_ids == []


def test_a_sheet_domain_folds_into_an_existing_company() -> None:
    """A sheet for a domain we already measure must NOT mint a second tenant."""
    derived = derive(
        runs=[("r1", "FORT", ["https://www.fort.cx/"])],
        teasers=[],
        sheet_domains=[("fort.cx", "FORT")],
    )
    assert set(derived) == {"fort.cx"}
    assert derived["fort.cx"].run_ids == ["r1"]


def test_a_sheet_with_no_domain_is_skipped_rather_than_name_keyed() -> None:
    """A name-keyed company from a sheet could never be joined back to by a run,
    so it would be a tenant nothing else can reach."""
    derived = derive(runs=[], teasers=[], sheet_domains=[("", "No Domain Co"), (None, None)])  # type: ignore[list-item]
    assert derived == {}


def test_a_name_slug_collision_is_refused_not_merged() -> None:
    """Two different businesses whose names slugify alike must NOT become one
    tenant. While a project was a GROUP BY this was a cosmetic bug; the moment it
    is a tenant with memberships, it is one client reading another's reports."""
    derived = derive(
        runs=[("r1", "Acme Inc", []), ("r2", "ACME, Inc.", [])],
        teasers=[],
    )
    assert set(derived) == {"name:acme-inc"}  # they DID collide
    collisions = check_collisions(derived)
    assert collisions and "name:acme-inc" in collisions[0]


def test_one_domain_with_several_names_is_not_a_collision() -> None:
    """The mirror case, and it must stay allowed: a domain identifies the
    business, so "FORT" and "Fort Security" on fort.cx are one company."""
    derived = derive(
        runs=[("r1", "FORT", ["fort.cx"]), ("r2", "Fort Security", ["https://fort.cx"])],
        teasers=[],
    )
    assert set(derived) == {"fort.cx"}
    assert check_collisions(derived) == []


def test_a_domain_learned_later_upgrades_the_bucket() -> None:
    """A teaser with a URL and a run without one, same business: the bucket must
    end up domain-keyed, matching `_collect()`'s `ensure()` behaviour."""
    key, label, domain = key_for(norm_domain("https://www.acme.io/"), "Acme")
    assert (key, label, domain) == ("acme.io", "acme.io", "acme.io")
