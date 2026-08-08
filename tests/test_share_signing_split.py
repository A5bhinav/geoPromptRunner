"""LIC-T11: share-link signing moved off GEO_API_KEY without breaking live links.

The failure this guards against is not subtle but it is invisible: `GEO_API_KEY`
was both the API credential and the HMAC secret on every share link, so retiring
it as authentication (LIC-T10) would have silently stopped every report link a
client had already been sent from verifying. Nothing would error at deploy time;
the links would just start returning 403.
"""

from __future__ import annotations

import pytest

from src.api import sharing
from src.config import settings


@pytest.fixture(autouse=True)
def _restore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test sets its own key state; none leaks into the next."""
    monkeypatch.setattr(settings, "SHARE_ACCEPT_LEGACY_SIGNATURE", True)


def test_a_link_minted_before_the_split_still_verifies_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The acceptance criterion, and the whole reason for the deprecation window."""
    # Before: one value doing both jobs.
    monkeypatch.setattr(settings, "GEO_API_KEY", "the-old-shared-secret")
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "the-old-shared-secret")
    old_link = sharing.mint_share_token("run-1")

    # After: signing moved to its own, different secret.
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "a-brand-new-signing-secret")
    assert sharing.verify_share_token(old_link).run_id == "run-1"


def test_a_link_minted_after_the_split_verifies_once_the_window_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GEO_API_KEY", "the-old-shared-secret")
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "a-brand-new-signing-secret")
    new_link = sharing.mint_share_token("run-2")

    # Window closed: only the new secret is honoured...
    monkeypatch.setattr(settings, "SHARE_ACCEPT_LEGACY_SIGNATURE", False)
    assert sharing.verify_share_token(new_link).run_id == "run-2"


def test_closing_the_window_stops_honouring_the_old_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """...and that is the point: closing it must actually retire the old key."""
    monkeypatch.setattr(settings, "GEO_API_KEY", "the-old-shared-secret")
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "the-old-shared-secret")
    old_link = sharing.mint_share_token("run-3")

    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "a-brand-new-signing-secret")
    monkeypatch.setattr(settings, "SHARE_ACCEPT_LEGACY_SIGNATURE", False)
    with pytest.raises(sharing.ShareError, match="not valid"):
        sharing.verify_share_token(old_link)


def test_minting_refuses_rather_than_signing_with_an_empty_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching the pre-split behaviour exactly. A signature over an empty key is
    forgeable by anyone who can read this repository."""
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "")
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    with pytest.raises(sharing.ShareError, match="SHARE_SIGNING_KEY"):
        sharing.mint_share_token("run-4")
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", None)
    with pytest.raises(sharing.ShareError):
        sharing.mint_share_token("run-4")


def test_retiring_geo_api_key_alone_does_not_break_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LIC-T10 deletes GEO_API_KEY as an authentication credential. Once
    SHARE_SIGNING_KEY holds its own value, that deletion must be a non-event for
    links — this is the assertion that lets T10 proceed."""
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "an-independent-signing-secret")
    monkeypatch.setattr(settings, "GEO_API_KEY", "still-the-api-credential")
    link = sharing.mint_share_token("run-5")

    monkeypatch.setattr(settings, "GEO_API_KEY", None)  # retired
    assert sharing.verify_share_token(link).run_id == "run-5"


def test_a_forged_signature_is_still_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fallback widens what verifies; it must not widen it to everything."""
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "real-secret")
    monkeypatch.setattr(settings, "GEO_API_KEY", "old-secret")
    link = sharing.mint_share_token("run-6")
    payload, _sig = link.split(".", 1)
    with pytest.raises(sharing.ShareError, match="not valid"):
        sharing.verify_share_token(f"{payload}.obviously-not-a-signature")
    # And a token signed with a THIRD, unrelated secret is not accepted either.
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "attacker-secret")
    forged = sharing.mint_share_token("run-6")
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "real-secret")
    with pytest.raises(sharing.ShareError, match="not valid"):
        sharing.verify_share_token(forged)


def test_password_and_revocation_still_work_across_the_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The split touches the secret, not the token's semantics."""
    monkeypatch.setattr(settings, "GEO_API_KEY", "old-secret")
    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "old-secret")
    link = sharing.mint_share_token("run-7", password="hunter2", token_id="tok-7")

    monkeypatch.setattr(settings, "SHARE_SIGNING_KEY", "new-secret")
    assert sharing.verify_share_token(link, password="hunter2").run_id == "run-7"
    with pytest.raises(sharing.ShareError, match="password"):
        sharing.verify_share_token(link, password="wrong")
    with pytest.raises(sharing.ShareError, match="revoked"):
        sharing.verify_share_token(link, password="hunter2", revoked_ids=frozenset({"tok-7"}))
