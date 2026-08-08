"""LIC-T6: per-user auth, verified locally against ES256 JWKS, one route at a time.

Real keys throughout — a genuine P-256 keypair is generated per test run and the
JWKS endpoint is stubbed with its public half. Mocking `jwt.decode` would test the
mock; this tests the thing LIC-T0 established we must do, which is verify an
ES256 signature locally without calling the Auth server.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from src.api import app as api_app
from src.api import auth
from src.api import identity as identity_mod
from src.config import settings
from src.storage import db

_KID = "test-key-1"


@pytest.fixture
def keypair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    private = ec.generate_private_key(ec.SECP256R1())
    return private, private.public_key()


@pytest.fixture(autouse=True)
def _clean_jwks() -> None:
    auth.reset_jwks_cache()


@pytest.fixture
def jwks(monkeypatch: pytest.MonkeyPatch, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    """Serve the public half where the verifier looks for it."""
    _, public = keypair
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(public, as_dict=True)
    jwk.update({"kid": _KID, "use": "sig", "alg": "ES256"})

    class _FakeJWKClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def get_signing_key_from_jwt(self, token: str) -> object:
            header = jwt.get_unverified_header(token)
            if header.get("kid") != _KID:
                raise jwt.exceptions.PyJWKClientError("no matching key")
            return jwt.PyJWK(jwk, algorithm="ES256")

    monkeypatch.setattr(auth, "PyJWKClient", _FakeJWKClient)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://project.supabase.co")


def _token(
    private: ec.EllipticCurvePrivateKey,
    *,
    sub: str = "user-1",
    aud: str = "authenticated",
    exp_delta: int = 3600,
    kid: str = _KID,
) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "aud": aud, "email": "a@b.test", "role": "authenticated",
         "iat": now, "exp": now + exp_delta},
        private,
        algorithm="ES256",
        headers={"kid": kid},
    )


# --- the verifier ------------------------------------------------------------


def test_a_valid_token_verifies_locally(jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    private, _ = keypair
    claims = auth.verify_access_token(_token(private))
    assert claims.subject == "user-1"
    assert claims.email == "a@b.test"


def test_an_expired_token_is_refused(jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    private, _ = keypair
    with pytest.raises(auth.AuthError):
        auth.verify_access_token(_token(private, exp_delta=-10))


def test_a_token_for_another_audience_is_refused(jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]) -> None:
    """Stops a token minted for a different project or integration from
    authenticating here."""
    private, _ = keypair
    with pytest.raises(auth.AuthError):
        auth.verify_access_token(_token(private, aud="some-other-service"))


def test_a_token_signed_by_someone_else_is_refused(jwks: None) -> None:
    attacker = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(auth.AuthError):
        auth.verify_access_token(_token(attacker))


def test_an_unsigned_token_is_refused(jwks: None) -> None:
    """`alg: none` — the oldest JWT attack there is. Defeated by pinning the
    accepted algorithms rather than trusting the header's nomination."""
    forged = jwt.encode({"sub": "user-1", "aud": "authenticated"}, key="",
                        algorithm="none", headers={"kid": _KID})
    with pytest.raises(auth.AuthError):
        auth.verify_access_token(forged)


def test_an_hs256_token_signed_with_the_public_key_is_refused(
    jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]
) -> None:
    """The algorithm-confusion attack: the public key is PUBLISHED, so if HS256
    were accepted anyone could mint a valid token using it as the shared secret.

    Hand-assembled, because PyJWT refuses to ENCODE an HMAC token from a PEM key.
    That refusal protects us from writing the bug, not from receiving the attack —
    an attacker assembles the bytes directly, exactly as this does.
    """
    _, public = keypair
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": _KID}).encode())
    payload = b64(
        json.dumps(
            {"sub": "user-1", "aud": "authenticated", "exp": int(time.time()) + 3600}
        ).encode()
    )
    signing_input = header + b"." + payload
    signature = b64(hmac.new(pem, signing_input, hashlib.sha256).digest())
    forged = (signing_input + b"." + signature).decode()

    with pytest.raises(auth.AuthError):
        auth.verify_access_token(forged)


def test_an_empty_token_is_refused() -> None:
    with pytest.raises(auth.AuthError, match="missing"):
        auth.verify_access_token("")


def test_the_failure_message_never_says_which_check_failed(
    jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]
) -> None:
    """Which of expired / bad audience / bad signature happened helps an attacker
    enumerate and helps a real caller not at all — they sign in again either way."""
    private, _ = keypair
    messages = set()
    for bad in (_token(private, exp_delta=-10), _token(private, aud="other"),
                _token(ec.generate_private_key(ec.SECP256R1()))):
        with pytest.raises(auth.AuthError) as exc:
            auth.verify_access_token(bad)
        messages.add(str(exc.value))
    assert len(messages) == 1, f"error messages distinguish failure modes: {messages}"


# --- the per-route flag ------------------------------------------------------


def test_route_migration_is_prefix_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "JWT_MIGRATED_ROUTES", "/projects,/companies")
    assert api_app.is_jwt_route("/projects")
    assert api_app.is_jwt_route("/projects/fort.cx/history")   # subtree migrates too
    assert api_app.is_jwt_route("/companies")
    assert not api_app.is_jwt_route("/audits")
    # A prefix must not match a different route that merely starts with the text.
    assert not api_app.is_jwt_route("/projects-archive")


def test_nothing_is_migrated_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "JWT_MIGRATED_ROUTES", "")
    assert not api_app.is_jwt_route("/projects")


# --- the boundary ------------------------------------------------------------


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "GEO_API_KEY", "the-shared-key")
    monkeypatch.setattr(settings, "JWT_MIGRATED_ROUTES", "/projects")
    monkeypatch.setattr(db, "list_companies", lambda *a, **k: [])
    monkeypatch.setattr(db, "list_all_audit_runs", lambda *a, **k: [])
    monkeypatch.setattr(db, "list_teasers_with_url", lambda *a, **k: [])
    monkeypatch.setattr(
        db,
        "get_user_profile",
        lambda uid: db.UserProfile(user_id=uid, is_platform_admin=False,
                                   deactivated=False, organization_id="org-1"),
    )
    return TestClient(api_app.app, raise_server_exceptions=False)


def test_a_migrated_route_rejects_the_shared_key(client: TestClient) -> None:
    response = client.get("/projects", headers={"X-API-Key": "the-shared-key"})
    assert response.status_code == 401
    assert "bearer" in response.json()["detail"].lower()


def test_a_migrated_route_accepts_a_jwt(
    client: TestClient, jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]
) -> None:
    private, _ = keypair
    response = client.get(
        "/projects", headers={"Authorization": f"Bearer {_token(private)}"}
    )
    assert response.status_code == 200


def test_an_unmigrated_route_rejects_a_jwt(
    client: TestClient, jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]
) -> None:
    private, _ = keypair
    response = client.get("/audits", headers={"Authorization": f"Bearer {_token(private)}"})
    assert response.status_code == 401
    assert "X-API-Key" in response.json()["detail"]


def test_an_unmigrated_route_accepts_the_shared_key(client: TestClient) -> None:
    response = client.get("/audits", headers={"X-API-Key": "the-shared-key"})
    assert response.status_code == 200


def test_no_route_accepts_both_credentials(
    client: TestClient, jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]
) -> None:
    """The property that keeps 'which credential authorised this' answerable."""
    private, _ = keypair
    both = {"X-API-Key": "the-shared-key", "Authorization": f"Bearer {_token(private)}"}
    assert client.get("/projects", headers=both).status_code == 401
    # The unmigrated route ignores the bearer and honours the key — but it is the
    # KEY that authorised it, unambiguously.
    assert client.get("/audits", headers=both).status_code == 200


def test_the_share_link_route_needs_neither_credential(client: TestClient) -> None:
    """`/shared/{token}/report` is mounted on `app`, not `api`, precisely so a
    client with no account can open a report. That must survive LIC-T6."""
    response = client.get("/shared/garbage/report")
    assert response.status_code == 403          # rejected by the TOKEN check...
    assert "not valid" in response.json()["detail"]   # ...not by an auth check


# --- identity resolution -----------------------------------------------------


def test_roles_come_from_the_database_not_the_token(
    client: TestClient, jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token claiming to be an admin gets exactly nothing for it: there is no
    way to force-refresh claims mid-session, so a role in a token outlives its
    own revocation."""
    private, _ = keypair
    seen: list[identity_mod.CallerIdentity] = []

    monkeypatch.setattr(
        db, "get_user_profile",
        lambda uid: db.UserProfile(user_id=uid, is_platform_admin=False,
                                   deactivated=False, organization_id="org-1"),
    )
    original = api_app.projects.list_projects

    def _spy() -> list[object]:
        seen.append(identity_mod.current_identity())
        return original()

    monkeypatch.setattr(api_app.projects, "list_projects", _spy)

    forged = jwt.encode(
        {"sub": "user-1", "aud": "authenticated", "role": "service_role",
         "is_platform_admin": True, "app_metadata": {"admin": True},
         "exp": int(time.time()) + 3600},
        private, algorithm="ES256", headers={"kid": _KID},
    )
    assert client.get("/projects", headers={"Authorization": f"Bearer {forged}"}).status_code == 200
    assert seen and seen[0].is_platform_admin is False
    assert seen[0].organization_id == "org-1"


def test_an_unprovisioned_account_is_refused(
    client: TestClient, jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, _ = keypair
    monkeypatch.setattr(db, "get_user_profile", lambda uid: None)
    response = client.get("/projects", headers={"Authorization": f"Bearer {_token(private)}"})
    assert response.status_code == 403


def test_a_deactivated_account_is_refused(
    client: TestClient, jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revocation has to bite on the next REQUEST, not the next token refresh."""
    private, _ = keypair
    monkeypatch.setattr(
        db, "get_user_profile",
        lambda uid: db.UserProfile(user_id=uid, is_platform_admin=False,
                                   deactivated=True, organization_id="org-1"),
    )
    response = client.get("/projects", headers={"Authorization": f"Bearer {_token(private)}"})
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"]


def test_a_storage_outage_degrades_to_least_privilege_not_to_admin(
    client: TestClient, jwks: None, keypair: tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failing open here would hand founder rights to anyone holding any valid
    token for the duration of an outage."""
    private, _ = keypair
    seen: list[identity_mod.CallerIdentity] = []

    def _down(_uid: str) -> None:
        raise db.StorageError("down")

    monkeypatch.setattr(db, "get_user_profile", _down)
    original = api_app.projects.list_projects
    monkeypatch.setattr(
        api_app.projects, "list_projects",
        lambda: (seen.append(identity_mod.current_identity()), original())[1],
    )
    assert client.get(
        "/projects", headers={"Authorization": f"Bearer {_token(private)}"}
    ).status_code == 200
    assert seen[0].is_platform_admin is False
    assert seen[0].organization_id is None
