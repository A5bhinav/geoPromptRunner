from __future__ import annotations

import httpx
import pytest
from protego import Protego

from src.audit.crawl import robots as robots_mod
from src.audit.crawl.robots import RobotsPolicy, load_robots


def test_policy_allowed_and_crawl_delay() -> None:
    policy = RobotsPolicy(
        Protego.parse("User-agent: GPTBot\nDisallow: /private/\nCrawl-delay: 2\n")
    )
    assert policy.allowed("https://x.com/pricing") is True
    assert policy.allowed("https://x.com/private/secret") is False
    assert policy.crawl_delay() == 2.0


def test_permissive_policy_allows_everything() -> None:
    policy = RobotsPolicy(None)
    assert policy.allowed("https://x.com/anything") is True
    assert policy.crawl_delay() is None


def test_load_robots_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        robots_mod.httpx,
        "get",
        lambda *a, **k: httpx.Response(200, text="User-agent: *\nDisallow: /admin/\n"),
    )
    policy = load_robots("x.com")
    assert policy.allowed("https://x.com/admin/x") is False
    assert policy.allowed("https://x.com/blog") is True


def test_load_robots_missing_is_permissive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(robots_mod.httpx, "get", lambda *a, **k: httpx.Response(404, text=""))
    assert load_robots("x.com").allowed("https://x.com/anything") is True


def test_load_robots_transport_error_is_permissive(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: object, **k: object) -> httpx.Response:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(robots_mod.httpx, "get", boom)
    assert load_robots("x.com").allowed("https://x.com/anything") is True
