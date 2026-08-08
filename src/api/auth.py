"""Verify a Supabase access token, locally, against the project's JWKS (LIC-T6).

**Why local verification and not `getUser()`.** LIC-T0 checked this project's
`/auth/v1/.well-known/jwks.json` and found one **ES256** key (EC P-256): the
project is on asymmetric JWT signing keys. Supabase's own guidance is that with an
asymmetric key the token is verified locally against the JWKS — the `getClaims()`
path — while `getUser()` always round-trips to the Auth server. On a backend that
authorises every request, a per-request network call to Auth is a latency and
availability dependency bought for nothing: the signature is the proof, and the
public key is published precisely so we can check it ourselves.

**What this does NOT do: it does not carry roles.** The token is proof of
identity, and that is all we take from it. Whether a user reaches a company is
answered by `private.has_company_access` reading `memberships` live, on every
query. That is deliberate — there is no first-party way to force-refresh a user's
JWT claims mid-session, so a role baked into a token outlives its own revocation.
Keeping authorization DB-authoritative means revoking a membership takes effect on
the next query rather than on the next token refresh.

**Failure is a 401 with a generic message.** Which of "expired", "wrong
audience", "bad signature" happened is useful to an attacker enumerating and
useless to a legitimate caller, who needs to sign in again either way. The
specific reason is logged, never returned.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from src.config import settings

__all__ = ["Claims", "AuthError", "verify_access_token", "reset_jwks_cache"]

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """The token may not be trusted. The message is safe to show a caller."""


@dataclass(frozen=True)
class Claims:
    """The parts of a verified token we are willing to act on."""

    #: `auth.users.id`.
    subject: str
    email: str
    #: The raw `role` claim ("authenticated"). Kept for diagnostics only — it is
    #: Postgres's role, not an application permission, and nothing here branches
    #: on it.
    role: str


#: The signing algorithms we accept. Pinned to a list, and pinned to ASYMMETRIC
#: algorithms only. Two attacks live here: `alg: none`, and an HS256 token whose
#: "secret" is the public key we publish — both are defeated by refusing to accept
#: any algorithm the caller nominates that is not on this list.
_ALLOWED_ALGORITHMS = ("ES256", "RS256")

_jwks_client: PyJWKClient | None = None
_jwks_lock = threading.Lock()


def _jwks_url() -> str:
    base = (settings.SUPABASE_URL or "").rstrip("/")
    if not base:
        raise AuthError("authentication is not configured")
    return f"{base}/auth/v1/.well-known/jwks.json"


def _client() -> PyJWKClient:
    """The JWKS client, built once and cached.

    `PyJWKClient` caches the fetched key set itself, so a verified request costs
    no network call. `lifespan` bounds that cache so a ROTATED signing key is
    picked up without a redeploy — which is the entire point of publishing keys at
    a discovery endpoint, and the reason rotation does not require shipping new
    backend config.
    """
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    with _jwks_lock:
        if _jwks_client is None:
            _jwks_client = PyJWKClient(
                _jwks_url(),
                cache_keys=True,
                lifespan=settings.JWKS_CACHE_SECONDS,
            )
    return _jwks_client


def reset_jwks_cache() -> None:
    """Drop the cached JWKS client. For tests, and for a forced key re-fetch."""
    global _jwks_client
    with _jwks_lock:
        _jwks_client = None


def verify_access_token(token: str) -> Claims:
    """Verify a Supabase access token and return its claims, or raise AuthError."""
    if not token:
        raise AuthError("missing bearer token")

    try:
        signing_key = _client().get_signing_key_from_jwt(token)
    except AuthError:
        raise
    except Exception as exc:
        # Covers an unreachable JWKS endpoint and a token whose `kid` is not in
        # the published set. Log the type only — a PyJWT message can echo token
        # content back into the log.
        logger.warning("JWKS lookup failed: %s", type(exc).__name__)
        raise AuthError("could not verify this token") from exc

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=list(_ALLOWED_ALGORITHMS),
            # Supabase issues access tokens with aud "authenticated". Verifying it
            # stops a token minted for a DIFFERENT audience (a third-party
            # integration, another project) from authenticating here.
            audience="authenticated",
            options={"require": ["exp", "sub"], "verify_exp": True, "verify_aud": True},
        )
    except jwt.PyJWTError as exc:
        # Deliberately one generic message for every failure mode. Which of
        # expired / bad audience / bad signature occurred helps an attacker
        # enumerate and helps a real caller not at all.
        logger.info("token rejected: %s", type(exc).__name__)
        raise AuthError("this session is not valid — please sign in again") from exc

    subject = str(payload.get("sub") or "")
    if not subject:
        raise AuthError("this session is not valid — please sign in again")
    return Claims(
        subject=subject,
        email=str(payload.get("email") or ""),
        role=str(payload.get("role") or ""),
    )
