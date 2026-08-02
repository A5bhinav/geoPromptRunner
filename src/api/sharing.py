"""Signed, expiring, revocable read-only report links (P3-T4).

A login wall is what kills forwardability, and forwardability is the one thing a
PDF has over a dashboard. A CMO forwards the report to a founder who does not
have an account; if that link asks for a password the report stops travelling.

**Signed, not guessed.** The token carries the run id, an expiry and an optional
password hash, and is signed with the API secret. Nothing is stored server-side to
mint one — but revocation IS stored, because a link you cannot withdraw is a link
you should not have issued.

Constant-time comparison throughout: a signature check that leaks timing is a
signature check that can be brute-forced one byte at a time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from src.config import settings

__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ShareToken",
    "ShareError",
    "mint_share_token",
    "verify_share_token",
]

#: 30 days. Long enough to survive a forward-and-forget, short enough that a link
#: leaked into an email thread does not stay live for a year.
DEFAULT_TTL_SECONDS = 30 * 24 * 3600


class ShareError(RuntimeError):
    """A link that may not be honoured. The message is safe to show a visitor."""


@dataclass(frozen=True)
class ShareToken:
    run_id: str
    expires_at: int
    #: sha256 of the password, or "" when the link is not password-protected.
    password_hash: str = ""
    #: Random per-token, so revoking one link does not revoke every link for the
    #: same run. Without it "revoke" would mean "revoke everything".
    token_id: str = ""


def _secret() -> bytes:
    key = settings.GEO_API_KEY or ""
    if not key:
        # Refusing beats minting a link signed with an empty key: that signature
        # is forgeable by anyone who reads this file.
        raise ShareError("GEO_API_KEY is not set — cannot sign a share link")
    return key.encode("utf-8")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes) -> str:
    return _b64(hmac.new(_secret(), payload, hashlib.sha256).digest())


def hash_password(password: str) -> str:
    """Hash of a share password. Never store or transmit the password itself."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest() if password else ""


def mint_share_token(
    run_id: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    password: str = "",
    token_id: str = "",
    now: int | None = None,
) -> str:
    """A signed, expiring token for one run. Stateless — nothing is written."""
    if not run_id:
        raise ShareError("a share link needs a run id")
    issued = int(now if now is not None else time.time())
    token = ShareToken(
        run_id=run_id,
        expires_at=issued + max(1, ttl_seconds),
        password_hash=hash_password(password),
        token_id=token_id or _b64(hashlib.sha256(f"{run_id}{issued}".encode()).digest()[:9]),
    )
    payload = json.dumps(token.__dict__, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{_b64(payload)}.{_sign(payload)}"


def verify_share_token(
    token: str,
    password: str = "",
    revoked_ids: frozenset[str] = frozenset(),
    now: int | None = None,
) -> ShareToken:
    """Validate a token or raise :class:`ShareError`. Order matters.

    Signature FIRST, then revocation, then expiry, then password. Checking expiry
    before the signature would let an attacker learn which forged run ids exist by
    reading the different error messages.
    """
    try:
        encoded, signature = token.split(".", 1)
        payload = _unb64(encoded)
    except (ValueError, TypeError) as exc:
        raise ShareError("this link is not valid") from exc

    if not hmac.compare_digest(signature, _sign(payload)):
        raise ShareError("this link is not valid")

    try:
        data = json.loads(payload)
        parsed = ShareToken(
            run_id=str(data["run_id"]),
            expires_at=int(data["expires_at"]),
            password_hash=str(data.get("password_hash", "")),
            token_id=str(data.get("token_id", "")),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise ShareError("this link is not valid") from exc

    if parsed.token_id and parsed.token_id in revoked_ids:
        raise ShareError("this link has been revoked")
    if parsed.expires_at <= int(now if now is not None else time.time()):
        raise ShareError("this link has expired")
    if parsed.password_hash and not hmac.compare_digest(
        parsed.password_hash, hash_password(password)
    ):
        raise ShareError("this link needs a password")
    return parsed
