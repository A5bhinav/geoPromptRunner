"""The F4 review gate: /fact-sheets, and the one thing it must refuse.

Approving a sheet is the moment a generated document becomes the reference every
accuracy finding for that domain is measured against. These tests are about the
boundaries of that: what a reviewer is shown, and what the gate will not do.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.audit.factsheet import (
    BusinessKind,
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SourceKind,
    Verification,
)
from src.storage import db


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _sheet() -> FactSheet:
    sheet = FactSheet(
        domain="fortplumbing.example",
        business_name="Fort Plumbing",
        business_kind=BusinessKind.LOCAL_SERVICE,
        generated_at="2026-07-31T00:00:00+00:00",
        questions=["Footer phone and GBP phone disagree — which is live?"],
        claims=[
            FactClaim(
                section=SheetSection.HOURS,
                key="hours_sunday",
                value="Closed Sunday.",
                polarity=Polarity.NEGATIVE,
                verbatim_quote="Sunday: Closed",
                source_url="https://fortplumbing.example/contact",
                source_kind=SourceKind.SITE_TEXT,
                as_of="2026-07-31",
                verification=Verification.PUBLIC_SOURCE_ONLY,
                confidence=Confidence.HIGH,
            )
        ],
    )
    sheet.assign_claim_ids()
    return sheet


# --- what a reviewer is shown -------------------------------------------------


def test_the_detail_view_carries_the_evidence_for_every_claim(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reviewer who cannot check a claim cannot approve it."""
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())
    body = client.get("/fact-sheets/sheet-1").json()
    claim = body["claims"][0]
    # The assertion AND the source line it came from — never one without the other.
    assert claim["value"] == "Closed Sunday."
    assert claim["verbatim_quote"] == "Sunday: Closed"
    assert claim["source_url"] == "https://fortplumbing.example/contact"
    assert claim["as_of"] == "2026-07-31"
    assert claim["verification"] == "public_source_only"


def test_the_detail_view_lists_the_open_questions(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The §4.3 disagreements are the call list — the reason a human is here.
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())
    body = client.get("/fact-sheets/sheet-1").json()
    assert body["questions"] == ["Footer phone and GBP phone disagree — which is live?"]


def test_the_weakest_tier_is_surfaced(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())
    body = client.get("/fact-sheets/sheet-1").json()
    assert body["verification_tier"] == "public_source_only"


def test_a_missing_sheet_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: None)
    assert client.get("/fact-sheets/nope").status_code == 404


# --- the queue ----------------------------------------------------------------


def test_an_unknown_state_is_422_not_an_empty_queue(client: TestClient) -> None:
    # Silently returning [] for a typo'd filter reads as "no sheets need review",
    # which is the wrong answer to show a reviewer.
    res = client.get("/fact-sheets?state=pending")
    assert res.status_code == 422
    assert "draft" in res.json()["detail"]


def test_the_queue_filters_by_state(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        db,
        "list_fact_sheets",
        lambda state=None, domain=None: seen.update({"state": state, "domain": domain}) or [],
    )
    client.get("/fact-sheets?state=draft")
    assert seen["state"] is db.FactSheetState.DRAFT


# --- approve / reject ---------------------------------------------------------


def test_approve_promotes_through_the_demote_aware_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())
    called: list[str] = []
    monkeypatch.setattr(db, "activate_fact_sheet", lambda sid: called.append(sid))
    res = client.post("/fact-sheets/sheet-1/approve")
    assert res.status_code == 200
    assert res.json()["state"] == "active"
    # Never a bare state write: uq_fact_sheets_active_domain requires the incumbent
    # be demoted in the same operation.
    assert called == ["sheet-1"]


def test_rejecting_an_active_sheet_is_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live runs are judged against the active sheet; pulling it leaves their
    accuracy claims referencing a document that no longer exists."""
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())

    def _refuse(sheet_id: str, reason: str | None = None) -> None:
        raise db.StorageError(f"reject_fact_sheet: {sheet_id} is ACTIVE — activate a replacement")

    monkeypatch.setattr(db, "reject_fact_sheet", _refuse)
    res = client.post("/fact-sheets/sheet-1/reject", json={"reason": "wrong hours"})
    assert res.status_code == 409


def test_reject_records_the_reason(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        db,
        "reject_fact_sheet",
        lambda sheet_id, reason=None: seen.update({"id": sheet_id, "reason": reason}),
    )
    res = client.post("/fact-sheets/sheet-1/reject", json={"reason": "hours are wrong"})
    assert res.status_code == 200
    assert res.json()["state"] == "rejected"
    # The verdict is kept, not deleted — it is the signal that tunes L1.
    assert seen == {"id": "sheet-1", "reason": "hours are wrong"}


def test_reject_without_a_reason_still_works(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())
    monkeypatch.setattr(db, "reject_fact_sheet", lambda sheet_id, reason=None: None)
    assert client.post("/fact-sheets/sheet-1/reject", json={}).status_code == 200


def test_approving_a_rejected_sheet_is_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reviewer already said no; one mis-click must not undo the only human
    judgment in the pipeline. The queue renders an Approve button on the rejected
    tab, so the guard lives next to the write, not only in the screen."""
    monkeypatch.setattr(db, "get_fact_sheet", lambda sid: _sheet())

    def _refuse(sheet_id: str) -> None:
        raise db.StorageError(f"activate_fact_sheet: {sheet_id} was REJECTED — regenerate")

    monkeypatch.setattr(db, "activate_fact_sheet", _refuse)
    res = client.post("/fact-sheets/sheet-1/approve")
    assert res.status_code == 409
    assert "REJECTED" in res.json()["detail"]
