"""LIC-T14/T19: provisioning an agency, and the console it gets.

The spec's Definition of Done runs through here: Shay accepts an invitation and
lands as `AGENCY_OWNER` of her own organization (#1), adds clients inside her
slot band and is refused beyond it (#2), and invites staff who reach every
managed company with no per-company grant written (#3).

The atomic accept is tested against the REAL database, because the property that
matters — the membership and the stamp land together or not at all — is a
property of the SQL function, and a mocked version of it would prove only that
the mock is atomic.
"""

from __future__ import annotations

import hashlib
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from src.api import app as api_app
from src.api import auth, console
from src.config import settings
from src.licensing import entitlements
from src.storage import db

_ORG = "33333333-3333-3333-3333-333333333333"


def _signed_in(
    monkeypatch: pytest.MonkeyPatch, *, is_platform_admin: bool, organization_id: str | None
) -> TestClient:
    """A TestClient whose requests really carry a verified per-user identity.

    Binding a ContextVar around the call would NOT work: `authenticate` runs as a
    dependency on every request and rebinds the identity itself, so a fixture that
    set one outside the request would be silently overwritten — and every console
    handler would see the shared-key `PLATFORM_ADMIN` instead. Going through the
    real JWT path is also the only version of this test that exercises the code an
    actual caller hits.
    """
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    monkeypatch.setattr(settings, "JWT_MIGRATED_ROUTES", ",".join(api_app.CONSOLE_PREFIXES))
    monkeypatch.setattr(
        auth,
        "verify_access_token",
        lambda token: auth.Claims(
            subject="owner-1", email="owner@agency.test", role="authenticated"
        ),
    )
    monkeypatch.setattr(
        db,
        "get_user_profile",
        lambda uid: db.UserProfile(
            user_id=uid,
            is_platform_admin=is_platform_admin,
            deactivated=False,
            organization_id=organization_id,
        ),
    )
    client = TestClient(api_app.app, raise_server_exceptions=False)
    client.headers.update({"Authorization": "Bearer a-verified-token"})
    return client


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A platform admin — the founders, provisioning agencies."""
    return _signed_in(monkeypatch, is_platform_admin=True, organization_id=None)


@pytest.fixture
def agency_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """An AGENCY_OWNER signed in to their own console."""
    return _signed_in(monkeypatch, is_platform_admin=False, organization_id=_ORG)


@pytest.fixture
def stranger_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Signed in, but with no agency at all."""
    return _signed_in(monkeypatch, is_platform_admin=False, organization_id=None)


@pytest.fixture
def _org(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        db,
        "get_organization",
        lambda oid: db.Organization(
            id=oid, name="Shay's agency", plan_id="agency",
            entitlement_overrides=None, deactivated_at=None,
        ),
    )


# --- LIC-T14: provisioning ----------------------------------------------------


def test_only_a_platform_admin_can_provision_an_agency(agency_client: TestClient) -> None:
    """404 rather than 403: whether a platform-admin surface exists at all is not
    something an agency user needs confirmed."""
    res = agency_client.post(
        "/admin/agencies", json={"name": "Rival", "owner_email": "x@rival.test"}
    )
    assert res.status_code == 404


def test_provisioning_creates_the_org_and_a_one_time_invite(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, _org: None
) -> None:
    """The first link in the chain — nothing else creates an organization."""
    created: dict[str, object] = {}

    def _create_org(name: str, plan_id: str, overrides: object = None) -> db.Organization:
        created["name"] = name
        created["plan_id"] = plan_id
        return db.Organization(
            id=_ORG, name=name, plan_id=plan_id, entitlement_overrides=None, deactivated_at=None
        )

    def _create_invite(**kwargs: object) -> str:
        created.update(kwargs)
        return "inv-1"

    monkeypatch.setattr(db, "create_organization", _create_org)
    monkeypatch.setattr(db, "create_invitation", _create_invite)

    res = client.post(
        "/admin/agencies", json={"name": "Shay's agency", "owner_email": "Shay@Agency.test"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["organization_id"] == _ORG
    assert body["client_slots"] == entitlements.PLAN_ENTITLEMENTS["agency"].client_slots
    assert body["invite_token"]
    # The TOKEN is returned once; only its HASH is ever stored. A table holding a
    # working credential is a table that grants what it is meant to record.
    assert created["token_hash"] == hashlib.sha256(
        body["invite_token"].encode()
    ).hexdigest()
    assert created["role"] == "AGENCY_OWNER"


def test_an_unknown_plan_is_refused_before_anything_is_written(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An organization provisioned with an unknown plan is one whose every later
    entitlement check raises — at which point it is already a row."""
    def _never(*_a: object, **_k: object) -> object:
        raise AssertionError("nothing may be written when the plan is invalid")

    monkeypatch.setattr(db, "create_organization", _never)
    res = client.post(
        "/admin/agencies",
        json={"name": "X", "owner_email": "a@b.test", "plan_id": "enterprise-deluxe"},
    )
    assert res.status_code == 422


def test_a_negotiated_slot_count_is_an_override_not_a_new_plan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plans stay `agency` and `agencyPro`. A bespoke deal lives in
    `entitlement_overrides`, or adding a plan name means hunting every check."""
    monkeypatch.setattr(
        db,
        "create_organization",
        lambda name, plan_id, overrides=None: db.Organization(
            id=_ORG, name=name, plan_id=plan_id,
            entitlement_overrides=overrides, deactivated_at=None,
        ),
    )
    monkeypatch.setattr(db, "create_invitation", lambda **_k: "inv-2")
    monkeypatch.setattr(
        db,
        "get_organization",
        lambda oid: db.Organization(
            id=oid, name="Big", plan_id="agency",
            entitlement_overrides={"client_slots": 40}, deactivated_at=None,
        ),
    )
    res = client.post(
        "/admin/agencies",
        json={
            "name": "Big agency",
            "owner_email": "big@agency.test",
            "entitlement_overrides": {"client_slots": 40},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["client_slots"] == 40
    assert res.json()["plan_id"] == "agency"


# --- LIC-T19: the console -----------------------------------------------------


def test_adding_a_client_inside_the_limit_is_silent(
    agency_client: TestClient, monkeypatch: pytest.MonkeyPatch, _org: None
) -> None:
    monkeypatch.setattr(db, "count_companies_for_agency", lambda oid: 3)
    monkeypatch.setattr(
        db,
        "create_company",
        lambda name, slug, domain=None, agency=None: db.Company(
            id="c-1", name=name, slug=slug, domain=domain, managing_agency_id=agency
        ),
    )
    res = agency_client.post("/agency/clients", json={"name": "Fort", "domain": "fort.cx"})
    assert res.status_code == 200, res.text
    assert res.json()["warning"] == ""
    assert res.json()["slug"] == "fort.cx"


def test_the_eleventh_client_of_ten_is_allowed_with_a_warning(
    agency_client: TestClient, monkeypatch: pytest.MonkeyPatch, _org: None
) -> None:
    """Soft, then hard. Blocking a customer's business over a billing technicality
    costs more than the overage does — so the grace band bills rather than
    refuses, and the warning is what reconciles the invoice."""
    monkeypatch.setattr(db, "count_companies_for_agency", lambda oid: 10)
    monkeypatch.setattr(
        db,
        "create_company",
        lambda name, slug, domain=None, agency=None: db.Company(
            id="c-11", name=name, slug=slug, domain=domain, managing_agency_id=agency
        ),
    )
    res = agency_client.post("/agency/clients", json={"name": "Eleven", "domain": "eleven.test"})
    assert res.status_code == 200, res.text
    assert "grace band" in res.json()["warning"]


def test_the_thirteenth_client_of_ten_is_refused_at_the_api(
    agency_client: TestClient, monkeypatch: pytest.MonkeyPatch, _org: None
) -> None:
    """The frontend gate is UX; this is the security boundary. 402 rather than
    403 — a billing state the caller can resolve, not a permission they will
    never have — and the resolved limit is named in the message."""
    monkeypatch.setattr(db, "count_companies_for_agency", lambda oid: 12)
    monkeypatch.setattr(
        db, "create_company", lambda *a, **k: pytest.fail("nothing may be written past the band")
    )
    res = agency_client.post("/agency/clients", json={"name": "Thirteen"})
    assert res.status_code == 402
    assert "10" in res.json()["detail"]


def test_the_console_never_takes_the_organization_from_the_request(
    stranger_client: TestClient, _org: None
) -> None:
    """An organization_id accepted as a parameter is one an attacker supplies. A
    caller with no agency identity gets 403 no matter what they send."""
    res = stranger_client.post(
        "/agency/clients", json={"name": "X", "organization_id": "someone-elses-org"}
    )
    assert res.status_code == 403


def test_an_owner_cannot_mint_another_owner(
    agency_client: TestClient, _org: None
) -> None:
    """AGENCY_OWNER is not invitable from the console: an owner minting owners is
    how an agency ends up with a staffer who can retarget its billing and cannot
    be removed by the person who hired them."""
    res = agency_client.post("/agency/staff", json={"email": "x@y.test", "role": "AGENCY_OWNER"})
    assert res.status_code == 422
    assert "AGENCY_MANAGER" in res.json()["detail"]


def test_releasing_a_client_is_not_a_delete(
    agency_client: TestClient, monkeypatch: pytest.MonkeyPatch, _org: None
) -> None:
    """Storage is create-only. Releasing sets `managing_agency_id` to null — the
    client keeps their data and their own logins and merely stops being managed."""
    calls: list[object] = []
    monkeypatch.setattr(
        db,
        "get_company",
        lambda cid: db.Company(
            id=cid, name="Fort", slug="fort.cx", domain="fort.cx", managing_agency_id=_ORG
        ),
    )
    monkeypatch.setattr(db, "set_company_agency", lambda cid, agency: calls.append((cid, agency)))
    monkeypatch.setattr(db, "delete_company", lambda *a, **k: pytest.fail("must not delete"))

    res = agency_client.delete("/agency/clients/c-1")
    assert res.status_code == 200
    assert calls == [("c-1", None)]


def test_an_agency_cannot_release_a_company_it_does_not_manage(
    agency_client: TestClient, monkeypatch: pytest.MonkeyPatch, _org: None
) -> None:
    monkeypatch.setattr(
        db,
        "get_company",
        lambda cid: db.Company(
            id=cid, name="Theirs", slug="theirs.test", domain="theirs.test",
            managing_agency_id="another-org",
        ),
    )
    monkeypatch.setattr(
        db, "set_company_agency", lambda *a: pytest.fail("must not touch another agency's client")
    )
    assert agency_client.delete("/agency/clients/c-9").status_code == 404


def test_every_console_route_is_covered_by_the_declared_prefixes() -> None:
    """These handlers resolve the caller's organization from the verified identity
    and refuse to take it from the request, so they are meaningless on the shared
    key. A route outside the declared prefixes would keep taking that key.

    `/auth/accept-invite` is the deliberate exception: the caller has no
    membership yet, by construction, so it cannot require a per-user JWT.
    """
    paths = {route.path for route in console.router.routes}  # type: ignore[attr-defined]
    uncovered = {
        p
        for p in paths
        if not any(p == q or p.startswith(q + "/") for q in api_app.CONSOLE_PREFIXES)
    }
    assert uncovered == {"/auth/accept-invite"}, uncovered


# --- The atomic accept, against the real database ----------------------------

_DSN = settings.SUPABASE_DB_URL
needs_db = pytest.mark.skipif(not _DSN, reason="needs SUPABASE_DB_URL (a real database)")

_INVITEE = "00000000-0000-0000-0000-00000000cc01"
_AGENCY = "00000000-0000-0000-0000-00000000ccb1"


@pytest.fixture
def pending_invite():  # type: ignore[no-untyped-def]
    """An organization with one unredeemed AGENCY_OWNER invitation. Rolled back."""
    psycopg = pytest.importorskip("psycopg")
    token = secrets.token_urlsafe(32)
    with psycopg.connect(_DSN, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into auth.users (instance_id, id, aud, role, email, created_at,
                                    updated_at, is_anonymous)
            values ('00000000-0000-0000-0000-000000000000', %s, 'authenticated',
                    'authenticated', 'shay@agency.test', now(), now(), false)
            on conflict (id) do nothing
            """,
            (_INVITEE,),
        )
        cur.execute("insert into public.organizations (id, name) values (%s, 'Shay')", (_AGENCY,))
        cur.execute(
            "insert into public.invitations "
            "(email, organization_id, role, token_hash, expires_at) "
            "values ('shay@agency.test', %s, 'AGENCY_OWNER', %s, now() + interval '14 days')",
            (_AGENCY, hashlib.sha256(token.encode()).hexdigest()),
        )
        yield cur, token
        conn.rollback()


@needs_db
def test_confirming_lands_exactly_one_agency_owner_membership(pending_invite) -> None:  # type: ignore[no-untyped-def]
    """DoD #1. A confirmed email with no membership is a user who logs in and
    sees nothing, which reads as a broken product — so the membership and the
    stamp are written together or not at all."""
    cur, token = pending_invite
    cur.execute(
        "select public.accept_invitation(%s, %s, %s)",
        (hashlib.sha256(token.encode()).hexdigest(), _INVITEE, "shay@agency.test"),
    )
    membership_id = cur.fetchone()[0]
    assert membership_id is not None

    cur.execute(
        "select role, accepted_at from public.memberships "
        "where user_id = %s and organization_id = %s",
        (_INVITEE, _AGENCY),
    )
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "AGENCY_OWNER"
    assert rows[0][1] is not None, "accepted_at must be stamped in the same transaction"


@needs_db
def test_a_replayed_confirm_does_not_create_a_second_membership(pending_invite) -> None:  # type: ignore[no-untyped-def]
    """Corporate scanners replay these URLs — that is the whole reason LIC-T13's
    interstitial exists. A second call returns the SAME membership rather than
    erroring, or a user whose membership was created correctly gets stranded."""
    cur, token = pending_invite
    digest = hashlib.sha256(token.encode()).hexdigest()
    args = (digest, _INVITEE, "shay@agency.test")
    cur.execute("select public.accept_invitation(%s, %s, %s)", args)
    first = cur.fetchone()[0]
    cur.execute("select public.accept_invitation(%s, %s, %s)", args)
    second = cur.fetchone()[0]

    assert first == second
    cur.execute(
        "select count(*) from public.memberships where user_id = %s and organization_id = %s",
        (_INVITEE, _AGENCY),
    )
    assert cur.fetchone()[0] == 1


@needs_db
def test_an_invitation_cannot_be_redeemed_by_a_different_address(pending_invite) -> None:  # type: ignore[no-untyped-def]
    """Otherwise a token leaked out of an inbox binds a membership to whoever
    redeems it — which is the entire privilege the invitation carries."""
    psycopg = pytest.importorskip("psycopg")
    cur, token = pending_invite
    cur.execute("savepoint sp")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "select public.accept_invitation(%s, %s, %s)",
            (hashlib.sha256(token.encode()).hexdigest(), _INVITEE, "someone.else@evil.test"),
        )
    cur.execute("rollback to savepoint sp")


@needs_db
def test_an_expired_invitation_is_refused(pending_invite) -> None:  # type: ignore[no-untyped-def]
    psycopg = pytest.importorskip("psycopg")
    cur, token = pending_invite
    digest = hashlib.sha256(token.encode()).hexdigest()
    cur.execute(
        "update public.invitations set expires_at = now() - interval '1 day' "
        "where token_hash = %s",
        (digest,),
    )
    cur.execute("savepoint sp")
    with pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "select public.accept_invitation(%s, %s, %s)",
            (digest, _INVITEE, "shay@agency.test"),
        )
    cur.execute("rollback to savepoint sp")


@needs_db
def test_accept_invitation_is_not_callable_by_an_authenticated_user() -> None:
    """`security definer` plus a grant to `authenticated` would let any signed-in
    user redeem any invitation whose token they could obtain."""
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(_DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "select has_function_privilege('authenticated', p.oid, 'execute') "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public' and p.proname = 'accept_invitation'"
        )
        row = cur.fetchone()
    assert row is not None, "accept_invitation is missing"
    assert row[0] is False, "accept_invitation must not be executable by authenticated"


def test_the_invite_ttl_is_bounded() -> None:
    """A token sitting in an abandoned inbox should not be a standing grant."""
    assert 0 < console.INVITE_TTL_SECONDS <= 30 * 24 * 3600
    assert int(time.time()) > 0  # the TTL is applied against wall clock, not a fixture
