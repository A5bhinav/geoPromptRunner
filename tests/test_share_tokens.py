"""LIC-T17: report share links are rows, not only signatures.

What shipped in P3-T4 was the option design §3.6 explicitly REJECTED — a
stateless HMAC — with a deny list bolted on to compensate. The deny list can
answer "is this token dead" and nothing else. It cannot answer "which links
exist for this client", "has anyone opened this report", or "stop this client's
links now that they have been offboarded", because a stateless token carries a
run id and nothing else.

These tests cover the three acceptance criteria in the spec, plus the one
property the whole migration is not allowed to break: a link minted BEFORE this
change, which has no row, must still work.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api import app as api_app
from src.api import runner, sharing
from src.config import settings
from src.storage import db

_RUN = "11111111-1111-1111-1111-111111111111"
_COMPANY = "22222222-2222-2222-2222-222222222222"
_REPORT: dict[str, object] = {"client_name": "Fort", "run_id": _RUN}


@pytest.fixture(autouse=True)
def _signing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "a-signing-secret")
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    monkeypatch.setattr(settings, "SHARE_ACCEPT_LEGACY_SIGNATURE", False)


class _FakeStore:
    """The token table, in memory, with the same shape the real one returns."""

    def __init__(self) -> None:
        self.rows: dict[str, db.ShareTokenRow] = {}
        self.denied: set[str] = set()
        self.live = True

    def create(
        self,
        token_id: str,
        run_id: str,
        company_id: str,
        expires_at: int,
        password_hash: str = "",
        created_by: str | None = None,
    ) -> None:
        self.rows[token_id] = db.ShareTokenRow(
            token_id=token_id,
            run_id=run_id,
            company_id=company_id,
            expires_at=expires_at,
            password_hash=password_hash,
            revoked_at=None,
            first_viewed_at=None,
            view_count=0,
        )

    def get(self, token_id: str) -> db.ShareTokenRow | None:
        return self.rows.get(token_id)

    def revoke_row(self, token_id: str, reason: str = "") -> bool:
        row = self.rows.get(token_id)
        if row is None or row.revoked_at is not None:
            return False
        self.rows[token_id] = db.ShareTokenRow(
            token_id=row.token_id,
            run_id=row.run_id,
            company_id=row.company_id,
            expires_at=row.expires_at,
            password_hash=row.password_hash,
            revoked_at="2026-08-07T00:00:00+00:00",
            first_viewed_at=row.first_viewed_at,
            view_count=row.view_count,
        )
        return True

    def record_view(self, token_id: str, viewed_at: str | None = None) -> None:
        row = self.rows.get(token_id)
        if row is None:
            return
        self.rows[token_id] = db.ShareTokenRow(
            token_id=row.token_id,
            run_id=row.run_id,
            company_id=row.company_id,
            expires_at=row.expires_at,
            password_hash=row.password_hash,
            revoked_at=row.revoked_at,
            first_viewed_at=row.first_viewed_at or "2026-08-07T00:00:00+00:00",
            view_count=row.view_count + 1,
        )


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(db, "create_share_token_row", fake.create)
    monkeypatch.setattr(db, "get_share_token_row", fake.get)
    monkeypatch.setattr(db, "revoke_share_token_row", fake.revoke_row)
    monkeypatch.setattr(db, "record_share_view", fake.record_view)
    monkeypatch.setattr(db, "company_delivery_live", lambda cid: fake.live)
    monkeypatch.setattr(db, "revoke_share_token", lambda *a, **k: None)
    monkeypatch.setattr(db, "revoked_share_ids", lambda: set(fake.denied))
    monkeypatch.setattr(db, "get_audit_run", lambda rid: {"id": rid, "company_id": _COMPANY})
    # The verdict-source gate (LIC-T20) reads the company; keep it out of the way.
    monkeypatch.setattr(
        db,
        "get_company",
        lambda cid: db.Company(id=cid, name="Fort", slug="fort.cx", domain="fort.cx",
                              managing_agency_id=None),
    )
    monkeypatch.setattr(runner, "get_report", lambda rid: dict(_REPORT) if rid == _RUN else None)
    monkeypatch.setattr(runner, "get_status", lambda rid: {"status": "complete"})
    api_app._REVOKED_SHARES.clear()
    return fake


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, store: _FakeStore) -> TestClient:
    monkeypatch.setattr(settings, "GEO_API_KEY", "")  # open mode: no auth header needed
    # https, not http: the share cookie is set `Secure`, so a plain-http client
    # would accept it and then silently never send it back — and the cookie test
    # would be asserting against a browser behaviour we do not actually have.
    return TestClient(api_app.app, base_url="https://testserver", raise_server_exceptions=False)


def _mint(client: TestClient, password: str = "") -> dict[str, object]:
    res = client.post(f"/audits/{_RUN}/share", json={"password": password})
    assert res.status_code == 200, res.text
    body: dict[str, object] = res.json()
    return body


# --- The three acceptance criteria -------------------------------------------


def test_revoking_one_link_leaves_the_others_working_across_a_redeploy(
    client: TestClient, store: _FakeStore
) -> None:
    """The reason the token needed to become a row at all.

    "Across a redeploy" is the load-bearing half: the in-process mirror
    (`_REVOKED_SHARES`) is cleared here to simulate a restart, so the only thing
    that can still be refusing the revoked link is durable state.
    """
    first = _mint(client)
    second = _mint(client)
    assert first["persistent"] is True

    revoked = client.post(f"/shares/{first['token_id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["row_revoked"] is True

    # The redeploy: this process forgets everything it held in memory.
    api_app._REVOKED_SHARES.clear()

    dead = client.get(f"/shared/{first['token']}/report")
    assert dead.status_code == 403
    assert "revoked" in dead.json()["detail"]

    alive = client.get(f"/shared/{second['token']}/report")
    assert alive.status_code == 200, alive.text
    assert alive.json()["client_name"] == "Fort"


def test_deactivating_the_companys_membership_stops_its_links(
    client: TestClient, store: _FakeStore
) -> None:
    """The capability `company_id` on the row exists to provide.

    Note the wording of the refusal: NOT "revoked". Nobody withdrew this link —
    the relationship behind it ended — and the client's support call goes very
    differently depending on which of those they are told.
    """
    link = _mint(client)
    assert client.get(f"/shared/{link['token']}/report").status_code == 200

    store.live = False

    stopped = client.get(f"/shared/{link['token']}/report")
    assert stopped.status_code == 403
    assert "no longer available" in stopped.json()["detail"]
    assert "revoked" not in stopped.json()["detail"]


def test_the_report_route_refuses_to_leak_the_token_through_a_referer(
    client: TestClient, store: _FakeStore
) -> None:
    """The token IS the credential, so the URL must not travel.

    `no-referrer` is what stops the browser attaching it to every asset,
    analytics beacon and outbound link the report page reaches — one of which
    would otherwise write a working credential into a third party's access log.
    """
    link = _mint(client)
    res = client.get(f"/shared/{link['token']}/report")

    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert "noindex" in res.headers["X-Robots-Tag"]
    assert "no-store" in res.headers["Cache-Control"]


# --- The property the migration may not break --------------------------------


def test_a_link_minted_before_this_change_still_works(
    client: TestClient, store: _FakeStore
) -> None:
    """No row, valid signature — every link already in a client's inbox.

    Refusing these would have been a silent outage: nothing errors at deploy
    time, the links just start returning 403. Same failure mode LIC-T11 existed
    to avoid, and the same answer.
    """
    legacy = sharing.mint_share_token(_RUN)
    assert store.get(sharing.verify_share_token(legacy).token_id) is None

    res = client.get(f"/shared/{legacy}/report")
    assert res.status_code == 200, res.text
    assert res.json()["client_name"] == "Fort"


def test_an_untenanted_run_mints_a_working_but_non_persistent_link(
    client: TestClient, store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run with no `company_id` cannot have a row, and the API says so.

    Reporting success and quietly delivering a link with no per-client
    revocation and no access log is the failure this flag exists to prevent.
    """
    monkeypatch.setattr(db, "get_audit_run", lambda rid: {"id": rid, "company_id": None})
    body = _mint(client)
    assert body["persistent"] is False
    assert client.get(f"/shared/{body['token']}/report").status_code == 200


# --- The access log ----------------------------------------------------------


def test_first_viewed_at_is_stamped_once_and_view_count_keeps_counting(
    client: TestClient, store: _FakeStore
) -> None:
    """Two questions, two columns. "When did it land" must not drift into
    "most recently opened" — that is what `view_count` answers."""
    link = _mint(client)
    token_id = str(link["token_id"])
    assert store.get(token_id) is not None

    client.get(f"/shared/{link['token']}/report")
    after_first = store.get(token_id)
    assert after_first is not None
    first_stamp = after_first.first_viewed_at
    assert first_stamp is not None
    assert after_first.view_count == 1

    client.get(f"/shared/{link['token']}/report")
    after_second = store.get(token_id)
    assert after_second is not None
    assert after_second.first_viewed_at == first_stamp
    assert after_second.view_count == 2


def test_the_cookie_exchange_serves_the_report_without_the_token_in_the_url(
    client: TestClient, store: _FakeStore
) -> None:
    """Design §3.6's history/referrer fix: after the first load the URL is no
    longer the credential, so the page can clean it out of the address bar."""
    link = _mint(client)
    first = client.get(f"/shared/{link['token']}/report")
    assert first.status_code == 200
    assert api_app._SHARE_COOKIE in first.cookies

    # The TestClient keeps the cookie jar, exactly as a browser would.
    second = client.get("/shared/report")
    assert second.status_code == 200
    assert second.json()["client_name"] == "Fort"


def test_the_cookie_route_refuses_a_visitor_who_has_no_cookie(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/shared/report").status_code == 403


# --- Storage degradation ------------------------------------------------------


def test_a_storage_outage_does_not_take_every_client_report_down(
    client: TestClient, store: _FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row check only ever NARROWS what the signature already allowed, so
    failing closed on it would trade a real outage for a hypothetical one."""
    link = _mint(client)

    def _boom(_token_id: str) -> db.ShareTokenRow | None:
        raise db.StorageError("supabase is down")

    monkeypatch.setattr(db, "get_share_token_row", _boom)
    monkeypatch.setattr(db, "revoked_share_ids", _raise_storage)

    res = client.get(f"/shared/{link['token']}/report")
    assert res.status_code == 200


def _raise_storage() -> set[str]:
    raise db.StorageError("supabase is down")
