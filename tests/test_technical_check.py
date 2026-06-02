from __future__ import annotations

from src.audit.technical_check import _base_url, _classify_crawler_access


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
