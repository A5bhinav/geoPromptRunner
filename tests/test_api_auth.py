"""API security boundary: constant-time key check, open-mode warning, and docs
gating (schema hidden once a key is configured)."""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from src.api import app as api_app
from src.config import settings


def test_docs_gated_on_key_configured() -> None:
    # Prod (key set): docs + OpenAPI schema disabled so the surface isn't mappable.
    assert api_app._docs_urls("s3cret") == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }
    # Dev (no key / None): docs open for convenience.
    for open_key in ("", None):
        d = api_app._docs_urls(open_key)
        assert d["docs_url"] == "/docs"
        assert d["openapi_url"] == "/openapi.json"
        assert d["redoc_url"] == "/redoc"


def test_require_api_key_open_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    # Open mode: no header required; anything (even None) passes.
    api_app.require_api_key(None)
    api_app.require_api_key("whatever")


def test_require_api_key_enforced_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GEO_API_KEY", "s3cret-key")
    api_app.require_api_key("s3cret-key")  # correct -> no raise
    for bad in (None, "", "wrong", "s3cret-ke"):  # missing / empty / wrong / truncated
        with pytest.raises(HTTPException) as exc:
            api_app.require_api_key(bad)
        assert exc.value.status_code == 401


def test_warn_if_open_logs_only_when_blank(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    with caplog.at_level(logging.WARNING):
        api_app._warn_if_open()
    assert any("API is OPEN" in r.message for r in caplog.records)

    caplog.clear()
    monkeypatch.setattr(settings, "GEO_API_KEY", "s3cret")
    with caplog.at_level(logging.WARNING):
        api_app._warn_if_open()
    assert not any("API is OPEN" in r.message for r in caplog.records)


# --- W1.6: the /local-entities endpoint's location guard --------------------------


def test_local_entities_requires_a_non_empty_location() -> None:
    """A local pack from an unpinned locale names businesses in the wrong metro. The
    endpoint refuses rather than silently doing a nationwide lookup — 422, not a
    plausible-but-wrong entity list."""
    with pytest.raises(HTTPException) as exc:
        api_app.local_entities(q="best plumber", location="   ")
    assert exc.value.status_code == 422
    assert "location is required" in str(exc.value.detail)


def test_local_entities_requires_a_non_empty_query() -> None:
    with pytest.raises(HTTPException) as exc:
        api_app.local_entities(q="  ", location="Berkeley,California,United States")
    assert exc.value.status_code == 422


def test_local_entities_is_503_when_no_vendor_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No local-pack vendor configured → 503 (the capability is unavailable), not a 200
    with an empty list that reads as "this city has no plumbers".

    Since 2026-07-28 this endpoint goes through ``local_pack.fetch_local_pack`` rather
    than building the google_ai_overviews engine. That coupling broke the moment AI
    Overviews changed vendor — DataForSEO captures Overviews but has no local-pack method
    — and the two surfaces were never the same thing anyway.
    """
    monkeypatch.setattr(settings, "SERPER_API_KEY", "")
    with pytest.raises(HTTPException) as exc:
        api_app.local_entities(q="best plumber", location="Berkeley,California,United States")
    assert exc.value.status_code == 503
    assert "no local-pack vendor is configured" in str(exc.value.detail)
