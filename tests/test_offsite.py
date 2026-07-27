from __future__ import annotations

import unittest.mock as mock
from typing import Any

import httpx
import pytest

from src.audit.offsite import agent as agent_mod
from src.audit.offsite import tools as tools_mod
from src.audit.offsite.agent import _deterministic_prepass, _dispatch_tool, _parse_findings
from src.audit.offsite.models import Confidence, FindingType, ToolLogEntry
from src.audit.offsite.tools import ToolResult, wikidata_entity

# --- submit_findings parsing -------------------------------------------------


def test_parse_findings_valid_and_fallback() -> None:
    submitted = {
        "findings": [
            {
                "finding_type": "community",
                "title": "Reddit thread on r/budgeting",
                "url": "https://reddit.com/r/budgeting/x",
                "confidence": "high",
                "summary": "Active discussion.",
            },
            {  # invalid enum values fall back to community/low
                "finding_type": "nonsense",
                "title": "Mystery",
                "confidence": "???",
                "summary": "s",
            },
            "not a dict",  # skipped
        ]
    }
    findings = _parse_findings(submitted)
    assert len(findings) == 2
    assert findings[0].finding_type is FindingType.COMMUNITY
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].url == "https://reddit.com/r/budgeting/x"
    assert findings[1].finding_type is FindingType.COMMUNITY  # fallback
    assert findings[1].confidence is Confidence.LOW  # fallback
    assert findings[1].url is None


# --- dispatcher: cache then quota --------------------------------------------


def test_dispatch_cache_then_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force web_search to a deterministic "unavailable" without hitting network.
    monkeypatch.setattr(
        agent_mod, "serper_search", lambda q: ToolResult(False, "serper", error="no key")
    )
    quotas = {"web_search": 1}
    cache: dict[str, Any] = {}
    log: list[ToolLogEntry] = []

    out1 = _dispatch_tool("web_search", {"query": "a"}, quotas, cache, 0, log)
    out2 = _dispatch_tool("web_search", {"query": "a"}, quotas, cache, 1, log)  # cache hit
    out3 = _dispatch_tool("web_search", {"query": "b"}, quotas, cache, 2, log)  # quota gone

    assert out1 == {"error": "no key"}
    assert out2 == out1  # served from cache
    assert out3 == {"error": "quota exhausted for web_search"}
    assert [e.status for e in log] == ["error", "cache_hit", "quota_exhausted"]
    assert quotas["web_search"] == 0  # consumed once; cache hit didn't consume


# --- tools degrade without keys ----------------------------------------------


def test_tools_unavailable_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_mod.settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(tools_mod.settings, "REDDIT_CLIENT_ID", None)
    monkeypatch.setattr(tools_mod.settings, "REDDIT_CLIENT_SECRET", None)
    monkeypatch.setattr(tools_mod.settings, "DATAFORSEO_LOGIN", None)
    monkeypatch.setattr(tools_mod.settings, "DATAFORSEO_PASSWORD", None)
    assert tools_mod.serper_search("x").available is False
    assert tools_mod.reddit_search("x").available is False
    assert tools_mod.dataforseo_backlinks("x.com").available is False
    assert tools_mod.reviews_presence("x").available is False


# --- Wikidata parsing (mocked transport) -------------------------------------


def _wikidata_handler(p856_url: str | None, p31_qid: str | None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        action = request.url.params.get("action")
        if action == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": "Q42"}]})
        claims: dict[str, Any] = {}
        if p856_url:
            claims["P856"] = [{"mainsnak": {"datavalue": {"value": p856_url}}}]
        if p31_qid:
            claims["P31"] = [{"mainsnak": {"datavalue": {"value": {"id": p31_qid}}}}]
        entity = {
            "labels": {"en": {"value": "Acme"}},
            "descriptions": {"en": {"value": "a company"}},
            "claims": claims,
        }
        return httpx.Response(200, json={"entities": {"Q42": entity}})

    return handler


def _patched_client(handler: Any) -> Any:
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client  # capture before the patch to avoid recursion

    def factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs.pop("transport", None)
        return real_client(transport=transport, **kwargs)

    return factory


def test_wikidata_match_by_official_website() -> None:
    handler = _wikidata_handler(p856_url="https://acme.com", p31_qid=None)
    with mock.patch.object(tools_mod.httpx, "Client", _patched_client(handler)):
        result = wikidata_entity("Acme", "acme.com")
    assert result.available is True
    assert result.data["found"] is True
    assert result.data["matched_by"] == "P856"
    assert result.data["qid"] == "Q42"


def test_wikidata_match_by_instance_of() -> None:
    handler = _wikidata_handler(p856_url=None, p31_qid="Q4830453")  # business
    with mock.patch.object(tools_mod.httpx, "Client", _patched_client(handler)):
        result = wikidata_entity("Acme", "acme.com")
    assert result.data["found"] is True
    assert result.data["matched_by"] == "P31"


def test_wikidata_no_discriminating_claim_is_not_found() -> None:
    # Name matches but neither P856 (wrong domain) nor an org P31 -> not found.
    handler = _wikidata_handler(p856_url="https://someoneelse.com", p31_qid="Q5")  # human
    with mock.patch.object(tools_mod.httpx, "Client", _patched_client(handler)):
        result = wikidata_entity("Acme", "acme.com")
    assert result.data["found"] is False


# --- deterministic pre-pass mapping ------------------------------------------


def test_prepass_maps_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_mod,
        "wikidata_entity",
        lambda b, d: ToolResult(True, "wikidata", {"found": True, "qid": "Q1"}),
    )
    monkeypatch.setattr(
        agent_mod,
        "reviews_presence",
        lambda b, kind="product": ToolResult(
            True, "reviews", {"platforms": {"trustpilot.com": {"present": True}}}
        ),
    )
    monkeypatch.setattr(
        agent_mod,
        "dataforseo_backlinks",
        lambda d: ToolResult(True, "dataforseo", {"referring_domains": 123}),
    )
    findings, log = _deterministic_prepass("Acme", "acme.com")
    types = {f.finding_type for f in findings}
    assert types == {FindingType.WIKIDATA, FindingType.REVIEWS, FindingType.BACKLINKS}
    assert len(log) == 3
    wiki = next(f for f in findings if f.finding_type is FindingType.WIKIDATA)
    assert wiki.url == "https://www.wikidata.org/wiki/Q1"


# --- orchestrator gating -----------------------------------------------------


def test_run_offsite_research_no_search_keys_returns_prepass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.audit.offsite.models import OffsiteFinding

    monkeypatch.setattr(
        agent_mod,
        "_deterministic_prepass",
        lambda b, d, kind="product": (
            [OffsiteFinding(FindingType.WIKIDATA, "found", None, Confidence.HIGH, {})],
            [],
        ),
    )
    monkeypatch.setattr(agent_mod.settings, "SERPER_API_KEY", None)
    monkeypatch.setattr(agent_mod.settings, "REDDIT_CLIENT_ID", None)
    monkeypatch.setattr(agent_mod.settings, "REDDIT_CLIENT_SECRET", None)
    result = agent_mod.run_offsite_research("Acme", "acme.com")
    assert result.status == "partial"
    assert len(result.findings) == 1
    assert "pre-pass only" in result.note


# --- W4.1 / W4.2: local directories and the local research brief -------------------


def test_review_platforms_are_forked_by_business_kind() -> None:
    from src.audit.offsite.tools import (
        LOCAL_REVIEW_PLATFORMS,
        REVIEW_PLATFORMS,
        review_platforms_for,
    )

    assert review_platforms_for() == REVIEW_PLATFORMS
    assert review_platforms_for("product") == REVIEW_PLATFORMS
    assert review_platforms_for("local_service") == LOCAL_REVIEW_PLATFORMS
    assert review_platforms_for("unknown-kind") == REVIEW_PLATFORMS

    # The consumer tuple is unchanged, and the two sets are disjoint — a plumber has
    # no App Store presence, a phone app has no BBB page.
    assert REVIEW_PLATFORMS == ("trustpilot.com", "apps.apple.com", "play.google.com")
    assert not set(REVIEW_PLATFORMS) & set(LOCAL_REVIEW_PLATFORMS)

    # Yelp and GBP are the two that matter most for local.
    assert "yelp.com" in LOCAL_REVIEW_PLATFORMS
    assert "google.com/maps" in LOCAL_REVIEW_PLATFORMS


def test_local_research_brief_is_a_fork_not_a_rewrite() -> None:
    from src.audit.offsite.agent import _SYSTEM, _system_prompt

    consumer = _system_prompt("product")
    local = _system_prompt("local_service")

    # The consumer brief still hunts threads, listicles and press, unchanged.
    assert consumer == _SYSTEM
    assert "listicles" in consumer
    assert _system_prompt() == consumer
    assert _system_prompt("unknown-kind") == consumer

    # The local brief leads with NAP consistency and directory presence instead.
    assert "NAP CONSISTENCY" in local
    assert "DIRECTORY PRESENCE" in local
    assert local != consumer

    # Same-name confusion across metros is the #1 local research error.
    assert "same-name confusion" in local
    assert "confirm the CITY matches" in local


def test_local_brief_carries_the_client_city_when_known() -> None:
    from src.audit.offsite.agent import _system_prompt

    located = _system_prompt("local_service", "Berkeley,California,US")
    assert "Berkeley,California,US" in located
    # Without a location the brief still works — it just can't disambiguate.
    assert "operates in" not in _system_prompt("local_service")
    # A location must never leak onto the consumer brief.
    assert "Berkeley" not in _system_prompt("product", "Berkeley,California,US")
