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
