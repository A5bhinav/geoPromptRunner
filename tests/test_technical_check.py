from __future__ import annotations

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
