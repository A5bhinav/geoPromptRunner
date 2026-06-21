from __future__ import annotations

import httpx
import pytest

from src.audit import technical_check as tc


def _resp(
    status: int, text: str = "", headers: dict[str, str] | None = None, url: str = "https://x.com/"
) -> httpx.Response:
    return httpx.Response(
        status, text=text, headers=headers or {}, request=httpx.Request("GET", url)
    )


# --- challenge detection (WAF at 200) ----------------------------------------


def test_is_challenge_at_200() -> None:
    assert tc._is_challenge(_resp(200, "Just a moment...", {"server": "cloudflare"})) is True
    assert tc._is_challenge(_resp(200, "<html>ok</html>", {"server": "nginx"})) is False
    assert tc._is_challenge(_resp(200, "", {"cf-mitigated": "challenge"})) is True


def test_crawler_access_flags_200_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, user_agent: str | None = None) -> httpx.Response:
        if user_agent == tc.BROWSER_UA:
            return _resp(200, "real homepage content", {"server": "nginx"})
        return _resp(200, "Just a moment...", {"server": "cloudflare"})

    monkeypatch.setattr(tc, "_get", fake_get)
    # Every bot UA gets a challenge body at 200 -> all blocked -> fail.
    assert tc.check_crawler_access("x.com")["status"] == "fail"


def test_oai_searchbot_in_probe() -> None:
    assert "OAI-SearchBot" in tc.AI_CRAWLER_UAS


# --- llms.txt / sitemap content-type traps -----------------------------------


def test_llms_txt_html_app_shell_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tc,
        "_get",
        lambda url, user_agent=None: _resp(200, "<html>app</html>", {"content-type": "text/html"}),
    )
    assert tc.check_llms_txt("x.com")["status"] == "fail"


def test_llms_txt_plain_text_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tc,
        "_get",
        lambda url, user_agent=None: _resp(
            200, "# llms\nDocs: /docs", {"content-type": "text/plain"}
        ),
    )
    assert tc.check_llms_txt("x.com")["status"] == "pass"


def test_sitemap_html_app_shell_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tc,
        "_get",
        lambda url, user_agent=None: _resp(200, "<html>app</html>", {"content-type": "text/html"}),
    )
    assert tc.check_sitemap("x.com")["status"] == "fail"


def test_sitemap_reports_loc_count(monkeypatch: pytest.MonkeyPatch) -> None:
    body = "<urlset><url><loc>https://x.com/a</loc></url><url><loc>https://x.com/b</loc></url></urlset>"
    monkeypatch.setattr(
        tc,
        "_get",
        lambda url, user_agent=None: _resp(200, body, {"content-type": "application/xml"}),
    )
    result = tc.check_sitemap("x.com")
    assert result["status"] == "pass"
    assert "2 <loc> entries" in result["details"]


# --- gated-content recipe (per-page gating) ----------------------------------


def test_page_gating_signals() -> None:
    assert tc._page_gating(_resp(401, "nope"))[0] is True
    assert tc._page_gating(_resp(403, "forbidden"))[0] is True
    assert tc._page_gating(_resp(200, "sign in to continue"))[0] is True  # login stub
    assert tc._page_gating(_resp(200, "<html>" + "real content " * 80 + "</html>"))[0] is False
    # safe_get followed a redirect that landed on /login.
    assert tc._page_gating(_resp(200, "login form", url="https://x.com/login"))[0] is True
