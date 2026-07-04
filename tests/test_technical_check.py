from __future__ import annotations

from typing import Any

from src.audit.technical_check import (
    _base_url,
    _classify_crawler_access,
    _classify_rendering,
    _visible_text,
)


def test_base_url_normalization() -> None:
    assert _base_url("example.com") == "https://example.com"
    assert _base_url("example.com/") == "https://example.com"
    assert _base_url("https://example.com/path") == "https://example.com"
    assert _base_url("http://example.com") == "http://example.com"


def test_classify_crawler_access() -> None:
    # Baseline browser failed -> can't assess -> fail.
    assert _classify_crawler_access(False, [], 4)["status"] == "fail"
    # All crawlers reach the site -> pass.
    assert _classify_crawler_access(True, [], 4)["status"] == "pass"
    # Every probed crawler blocked -> fail.
    assert _classify_crawler_access(True, ["GPTBot", "ClaudeBot"], 2)["status"] == "fail"
    # Some blocked -> partial.
    assert _classify_crawler_access(True, ["GPTBot"], 4)["status"] == "partial"


def test_visible_text_strips_scripts_and_tags() -> None:
    html = (
        "<html><head><style>.a{color:red}</style></head>"
        "<body><script>var x = 1234567890;</script>"
        "<p>Hello world</p><!-- comment --></body></html>"
    )
    # Only the human-visible copy survives — the JS bundle and CSS don't inflate it.
    assert _visible_text(html) == "Hello world"


def test_classify_rendering_substantial_text_passes() -> None:
    assert _classify_rendering(2000, spa_shell=False)["status"] == "pass"
    # Substantial text passes even if a framework marker is present (it hydrated).
    assert _classify_rendering(2000, spa_shell=True)["status"] == "pass"


def test_classify_rendering_spa_shell_with_little_text_fails() -> None:
    result = _classify_rendering(120, spa_shell=True)
    assert result["status"] == "fail"
    assert "SPA shell" in result["details"]


def test_classify_rendering_thin_text_is_partial() -> None:
    assert _classify_rendering(400, spa_shell=False)["status"] == "partial"


def test_classify_rendering_almost_empty_fails() -> None:
    assert _classify_rendering(50, spa_shell=False)["status"] == "fail"


def test_parse_sitemap_directives() -> None:
    from src.audit.technical_check import _parse_sitemap_directives

    text = (
        "User-agent: *\n"
        "Sitemap: https://x.com/sm.xml\n"
        "sitemap:   https://x.com/news.xml\n"
        "Sitemap: /relative-ignored.xml\n"
    )
    assert _parse_sitemap_directives(text) == ["https://x.com/sm.xml", "https://x.com/news.xml"]
    assert _parse_sitemap_directives("no directive here") == []


def test_assess_sitemap_verdicts() -> None:
    import httpx

    from src.audit.technical_check import _assess_sitemap

    assert _assess_sitemap(None)["status"] == "fail"
    assert _assess_sitemap(httpx.Response(404))["status"] == "fail"
    good = "<urlset><url><loc>https://x/a</loc></url></urlset>"
    assert _assess_sitemap(httpx.Response(200, text=good))["status"] == "pass"
    shell = httpx.Response(
        200, text="<html><body>app</body></html>", headers={"content-type": "text/html"}
    )
    assert _assess_sitemap(shell)["status"] == "fail"
    assert _assess_sitemap(httpx.Response(200, text="<urlset></urlset>"))["status"] == "partial"


def test_check_sitemap_honors_robots_declared_sitemap(monkeypatch: Any) -> None:
    import httpx

    import src.audit.technical_check as tc

    valid = "<urlset><url><loc>https://x.com/a</loc></url></urlset>"

    def fake_get(url: str, user_agent: str | None = None) -> httpx.Response:
        if url.endswith("/sitemap.xml"):
            return httpx.Response(404)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text="Sitemap: https://x.com/custom.xml")
        if url == "https://x.com/custom.xml":
            return httpx.Response(200, text=valid)
        return httpx.Response(404)

    monkeypatch.setattr(tc, "_get", fake_get)
    assert tc.check_sitemap("x.com")["status"] == "pass"


def test_check_sitemap_fails_when_none_declared(monkeypatch: Any) -> None:
    import httpx

    import src.audit.technical_check as tc

    def fake_get(url: str, user_agent: str | None = None) -> httpx.Response:
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text="User-agent: *")
        return httpx.Response(404)

    monkeypatch.setattr(tc, "_get", fake_get)
    assert tc.check_sitemap("x.com")["status"] == "fail"
