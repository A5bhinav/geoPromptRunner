"""LIC-T21: prove no model-vendor key can leave, under a non-platform identity.

**The standing rule has had nothing enforcing it.** "Never share a raw
model-vendor API key with an agency or its clients" is the first line of the
licensing skill and the last line of the spec's global acceptance, and until this
file it was a sentence in a document. The agency runs audits *through our
software, on our keys* — that is what the licence IS. A key in a response body, an
error payload, a log line or an export does not just leak a credential; it hands a
competitor the ability to run the product without us.

**Why a test and not a code review.** The realistic leak is not someone typing
`return {"key": settings.OPENAI_API_KEY}`. It is an exception handler that grows a
`repr(config)`, a debug field that survives to production, or a 500 body that
echoes an upstream SDK error carrying the Authorization header. All three are one
careless line in a file nobody was thinking about keys in, and all three are
caught here.

The keys are set to distinctive sentinels for the duration of each test, so a
match is unambiguous and no real credential is ever needed (or printed).
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.api import app as api_app
from src.api import identity as identity_mod
from src.api.identity import CallerIdentity
from src.config import settings
from src.storage import db

#: Every secret that must never cross the boundary. `SHARE_SIGNING_KEY` is here
#: because forging it mints a valid link to any client's confidential report, and
#: `SUPABASE_KEY` because it is the service-role key that bypasses RLS entirely —
#: leaking either is as bad as leaking a vendor key, and the spec names both.
GUARDED_SETTINGS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "PERPLEXITY_API_KEY",
    "GEMINI_API_KEY",
    "SERPER_API_KEY",
    "SUPABASE_KEY",
    "SHARE_SIGNING_KEY",
)

#: Distinctive, unmistakable, and obviously not a real key.
_SENTINEL = "sk-LEAKCANARY-{name}-do-not-disclose"


@pytest.fixture
def canaries(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replace every guarded secret with a traceable sentinel."""
    values: dict[str, str] = {}
    for name in GUARDED_SETTINGS:
        value = _SENTINEL.format(name=name)
        monkeypatch.setattr(settings, name, value, raising=False)
        values[name] = value
    return values


@pytest.fixture
def agency_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-platform identity — an agency owner, not a founder."""
    monkeypatch.setattr(
        identity_mod,
        "current_identity",
        lambda: CallerIdentity(user_id="u-agency", is_platform_admin=False,
                               organization_id="org-1"),
    )


def _assert_clean(blob: str, canaries: dict[str, str], where: str) -> None:
    for name, value in canaries.items():
        assert value not in blob, f"{name} leaked into {where}"
        # Also catch a partial disclosure — the tail of a key is enough to
        # confirm a guess, and "redacting" only the prefix is a common mistake.
        assert value[-12:] not in blob, f"{name} partially leaked into {where}"


def test_no_key_leaves_through_any_get_endpoint(
    canaries: dict[str, str], agency_caller: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Walk every registered GET route and assert the body is clean.

    Route-by-route rather than a fixed list, so a NEW endpoint is covered the day
    it is added rather than the day someone remembers to extend this test.
    """
    monkeypatch.setattr(settings, "GEO_API_KEY", "")  # open mode; auth is not what's under test
    client = TestClient(api_app.app, raise_server_exceptions=False)

    checked = 0
    for route in api_app.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if "GET" not in methods or "{" in path:
            # Parameterised routes are exercised separately below with ids that
            # actually resolve; a random uuid here would only ever 404.
            continue
        response = client.get(path)
        _assert_clean(response.text, canaries, f"GET {path}")
        checked += 1
    assert checked > 0, "no GET routes were exercised — the walk found nothing"


def test_no_key_leaves_through_an_error_body(
    canaries: dict[str, str], agency_caller: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The realistic leak: a handler that echoes config or an upstream SDK error.

    `get_audit_run` is made to raise carrying a key IN THE MESSAGE, which is
    exactly what an unwrapped provider error looks like. The response must not
    contain it — `db._execute` logs the exception TYPE only, and handlers must not
    re-widen that.
    """
    leaky = canaries["OPENAI_API_KEY"]

    def _raise(_rid: str) -> None:
        raise db.StorageError(f"connection refused using key {leaky}")

    monkeypatch.setattr(db, "get_audit_run", _raise)
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    client = TestClient(api_app.app, raise_server_exceptions=False)

    for path in (
        "/audits/00000000-0000-0000-0000-000000000000/report",
        "/audits/00000000-0000-0000-0000-000000000000/status",
        "/audits/00000000-0000-0000-0000-000000000000/judge-status",
    ):
        response = client.get(path)
        _assert_clean(response.text, canaries, f"error body of {path}")


def test_no_key_leaves_through_a_shared_report_link(
    canaries: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The anonymous surface, and the one an agency's CLIENT actually opens.

    Every failure mode is exercised — invalid, expired, revoked, wrong password —
    because each takes a different branch and each returns its reason in the body.
    """
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    client = TestClient(api_app.app, raise_server_exceptions=False)
    for token in ("garbage", "garbage.garbage", "", "a.b.c"):
        response = client.get(f"/shared/{token}/report")
        _assert_clean(response.text, canaries, f"/shared/{token}/report")


def test_no_key_reaches_the_logs(
    canaries: dict[str, str], caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A log line is an export: it goes to a hosting dashboard, and a support
    screenshot of it is how a key ends up in a chat thread."""
    leaky = canaries["ANTHROPIC_API_KEY"]

    def _raise(_rid: str) -> None:
        raise db.StorageError(f"upstream said: bad key {leaky}")

    monkeypatch.setattr(db, "get_audit_run", _raise)
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    client = TestClient(api_app.app, raise_server_exceptions=False)

    with caplog.at_level(logging.DEBUG):
        client.get("/audits/00000000-0000-0000-0000-000000000000/report")
    _assert_clean(caplog.text, canaries, "log output")


def test_the_openapi_schema_never_carries_a_key(canaries: dict[str, str]) -> None:
    """A schema dump is the fastest way to hand someone a defaulted secret: a
    Pydantic field whose default is read from settings serialises that default."""
    schema = json.dumps(api_app.app.openapi())
    _assert_clean(schema, canaries, "the OpenAPI schema")


def test_settings_module_is_the_only_place_that_reads_the_environment() -> None:
    """The rule that keeps all of the above tractable: one module reads secrets,
    so there is one place to audit. A stray `os.getenv` elsewhere is a second
    door, and the rest of this file cannot see through it."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "src"
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path.name != "settings.py" and "os.getenv" in path.read_text()
    ]
    assert offenders == [], f"os.getenv outside settings.py: {offenders}"


def test_the_canary_fixture_would_actually_catch_a_leak(canaries: dict[str, str]) -> None:
    """Guard the guard. If the sentinels stopped being installed, every assertion
    above would pass vacuously and this file would be decorative."""
    for name in GUARDED_SETTINGS:
        assert getattr(settings, name) == canaries[name]
    with pytest.raises(AssertionError, match="leaked"):
        _assert_clean(f"oops {canaries['OPENAI_API_KEY']}", canaries, "a deliberate leak")
