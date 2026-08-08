"""LIC-T9: new writes carry a tenant, so NOT NULL is survivable.

The backfill tenanted every row that existed. That is only half the job: nothing
in the write paths set `company_id`, so the very next audit would have inserted an
untenanted row — and once LIC-T9 adds NOT NULL, that insert becomes a failed
audit. These tests are the reason the constraint can be added at all.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.storage import db


class _Table:
    def __init__(self, name: str, log: list[tuple[str, str, Any]]) -> None:
        self.name, self.log = name, log

    def insert(self, rows: Any) -> _Table:
        self.log.append((self.name, "insert", rows))
        return self

    def upsert(self, rows: Any, **_k: Any) -> _Table:
        self.log.append((self.name, "upsert", rows))
        return self

    def update(self, values: Any) -> _Table:
        self.log.append((self.name, "update", values))
        return self

    def delete(self) -> _Table:
        return self

    def select(self, *_a: Any, **_k: Any) -> _Table:
        return self

    def eq(self, *_a: Any) -> _Table:
        return self

    def limit(self, *_a: Any) -> _Table:
        return self

    def order(self, *_a: Any, **_k: Any) -> _Table:
        return self

    def execute(self) -> Any:
        return type("R", (), {"data": []})()


class _Client:
    def __init__(self) -> None:
        self.log: list[tuple[str, str, Any]] = []

    def table(self, name: str) -> _Table:
        return _Table(name, self.log)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> _Client:
    fake = _Client()
    monkeypatch.setattr(db, "_client", lambda **_: fake)
    # A company already exists for every key these tests use, so `ensure_company`
    # takes its get branch. The create branch is covered separately below.
    monkeypatch.setattr(
        db,
        "get_company_by_slug",
        lambda slug: db.Company(id="c-1", name=slug, slug=slug, domain=slug,
                                managing_agency_id=None),
    )
    monkeypatch.setattr(db, "company_id_for_run", lambda rid: "c-1")
    return fake


def _rows_for(log: list[tuple[str, str, Any]], table: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, op, payload in log:
        if name == table and op in ("insert", "upsert"):
            out.extend(payload if isinstance(payload, list) else [payload])
    return out


def test_a_new_audit_run_is_tenanted(client: _Client) -> None:
    db.create_audit_run(
        client_name="FORT",
        client_domains=["https://fort.cx"],
        competitors=[],
        category="security",
        query_set_version="v1",
        query_set_locked_at="2026-08-06",
        runs_per_query=5,
    )
    (row,) = _rows_for(client.log, "audit_runs")
    assert row["company_id"] == "c-1"


def test_a_new_teaser_is_tenanted(client: _Client) -> None:
    db.save_teaser({"prospectUrl": "https://fort.cx", "companyName": "FORT"}, html=None)
    (row,) = _rows_for(client.log, "teasers")
    assert row["company_id"] == "c-1"


def test_run_children_inherit_the_runs_tenant(client: _Client) -> None:
    """The four high-volume children carry `company_id` themselves rather than
    joining `audit_runs` — a denormalised column is only as good as the code that
    writes it."""
    results: list[Any] = [
        {
            "query_id": "q1",
            "intent": "category",
            "prompt": "best x",
            "engine_name": "openai",
            "run_index": 0,
            "response": "an answer",
            "citations": ["https://example.com/a"],
            "timestamp": "2026-08-06T00:00:00Z",
        }
    ]
    db.save_query_results("run-1", results)
    for table in ("query_results", "query_citations"):
        rows = _rows_for(client.log, table)
        assert rows, f"no rows written to {table}"
        assert all(r["company_id"] == "c-1" for r in rows), table


def test_judgments_inherit_the_runs_tenant(client: _Client) -> None:
    from src.pipeline.judge import AnswerJudgment, BrandJudgment

    db.save_judgments(
        "run-1",
        [
            AnswerJudgment(
                query_id="q1", engine_name="openai", intent="category", run_index=0,
                assessed=True, brands=[BrandJudgment("Acme", True, "mid_pack", "neutral")],
                accuracy_flags=[],
            )
        ],
    )
    rows = _rows_for(client.log, "judgments")
    assert rows and all(r["company_id"] == "c-1" for r in rows)


def test_a_fact_sheet_and_its_claims_are_tenanted(
    client: _Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sheet can precede any run or teaser — that is exactly how
    blackpropeller.com ended up untenanted in the first backfill."""
    from src.audit.factsheet.models import BusinessKind, FactSheet

    sheet = FactSheet(domain="newco.com", business_name="NewCo",
                      business_kind=BusinessKind.PRODUCT,
                      generated_at="2026-08-06T00:00:00Z")
    db.save_fact_sheet(sheet)
    for table in ("fact_sheets",):
        rows = _rows_for(client.log, table)
        assert rows and all(r.get("company_id") == "c-1" for r in rows), table


def test_an_intake_session_is_tenanted(client: _Client) -> None:
    """An agency onboarding its own client starts here, before any run exists."""
    db.create_intake_session(domain="newco.com", business_kind="product")
    rows = _rows_for(client.log, "factsheet_intake_sessions")
    assert rows and rows[0]["company_id"] == "c-1"


# --- ensure_company itself ----------------------------------------------------


def test_ensure_company_reuses_an_existing_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run for a domain that already has a project must JOIN it, not mint a
    second tenant for the same business."""
    created: list[str] = []
    monkeypatch.setattr(
        db, "get_company_by_slug",
        lambda slug: db.Company(id="c-existing", name=slug, slug=slug, domain=slug,
                                managing_agency_id=None),
    )
    monkeypatch.setattr(
        db, "create_company",
        lambda *a, **k: created.append("made") or db.Company("x", "x", "x", None, None),
    )
    company = db.ensure_company("https://www.fort.cx/pricing", "FORT")
    assert company is not None and company.id == "c-existing"
    assert created == []


def test_ensure_company_creates_one_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[tuple[str, str, str | None]] = []

    def _create(name: str, slug: str, domain: str | None = None, agency: str | None = None) -> db.Company:
        made.append((name, slug, domain))
        return db.Company(id="c-new", name=name, slug=slug, domain=domain, managing_agency_id=None)

    monkeypatch.setattr(db, "get_company_by_slug", lambda slug: None)
    monkeypatch.setattr(db, "create_company", _create)
    company = db.ensure_company("https://newco.com/x", "NewCo")
    assert company is not None and company.id == "c-new"
    # Keyed by DOMAIN, with the label the UI already shows for it.
    assert made == [("newco.com", "newco.com", "newco.com")]


def test_ensure_company_survives_losing_the_create_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two runs starting for the same client at once is the ordinary case, not an
    error — read back what the winner wrote."""
    calls = {"n": 0}

    def _by_slug(slug: str) -> db.Company | None:
        calls["n"] += 1
        # Absent on the first look, present once the other writer has committed.
        if calls["n"] == 1:
            return None
        return db.Company(id="c-winner", name=slug, slug=slug, domain=slug,
                          managing_agency_id=None)

    def _create(*_a: object, **_k: object) -> db.Company:
        raise db.CompanySlugTaken("taken")

    monkeypatch.setattr(db, "get_company_by_slug", _by_slug)
    monkeypatch.setattr(db, "create_company", _create)
    company = db.ensure_company("fort.cx", "FORT")
    assert company is not None and company.id == "c-winner"


def test_a_storage_failure_leaves_the_write_untenanted_rather_than_losing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before NOT NULL this degrades; after it, the constraint fails the write
    loudly. Both are better than dropping an expensive measurement."""

    def _down(*_a: object, **_k: object) -> None:
        raise db.StorageError("down")

    monkeypatch.setattr(db, "get_company_by_slug", _down)
    assert db.ensure_company("fort.cx", "FORT") is None
