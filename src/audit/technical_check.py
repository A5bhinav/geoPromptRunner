from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Literal, TypedDict
from urllib.robotparser import RobotFileParser

import httpx

__all__ = [
    "CheckResult",
    "check_robots_txt",
    "check_llms_txt",
    "check_sitemap",
    "check_rendering",
    "check_crawler_access",
    "check_gated_content",
]

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0

# AI crawlers that should be allowed to reach a client's content (robots.txt names).
AI_USER_AGENTS: tuple[str, ...] = (
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "PerplexityBot",
    "Google-Extended",
    "Bingbot",
)

# Realistic User-Agent strings for the AI crawlers, used to detect UA-based
# CDN/WAF blocking (e.g. Cloudflare returning 403 to bot UAs while serving a
# normal browser). robots.txt can say "allowed" while the edge silently blocks.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
AI_CRAWLER_UAS: dict[str, str] = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot",
    "ClaudeBot": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Google-Extended": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}

# Mount-point markers left by client-rendered SPA frameworks. Their presence
# alongside little server-rendered text means the real content is assembled by
# JS in the browser — which AI crawlers that don't execute JS never see.
_SPA_SHELL_MARKERS: tuple[str, ...] = (
    'id="root"',
    "id='root'",
    'id="__next"',
    'id="app"',
    'id="__nuxt"',
    "data-reactroot",
    "ng-app",
    'ng-version="',
)

# Markers that suggest target content is gated behind a login/paywall/form.
_GATING_MARKERS: tuple[str, ...] = (
    "subscribe to read",
    "subscribe to continue",
    "sign in to continue",
    "log in to continue",
    "create a free account",
    "members only",
    "this content is for",
    "paywall",
    'type="password"',
)


class CheckResult(TypedDict):
    status: Literal["pass", "partial", "fail"]
    details: str


def _base_url(domain: str) -> str:
    """Normalize a domain/URL to ``https://host`` (no trailing path)."""
    domain = domain.strip()
    if domain.startswith(("http://", "https://")):
        parsed = httpx.URL(domain)
        return f"{parsed.scheme}://{parsed.host}"
    return f"https://{domain.rstrip('/')}"


def _get(url: str, user_agent: str | None = None) -> httpx.Response | None:
    """GET a URL with a 10s timeout, following redirects. None on transport error.

    Pass ``user_agent`` to probe how the site responds to a specific crawler UA.
    """
    headers = {"User-Agent": user_agent} if user_agent else None
    try:
        return httpx.get(url, timeout=TIMEOUT_SECONDS, follow_redirects=True, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("Request to %s failed: %s", url, exc)
        return None


def _classify_crawler_access(baseline_ok: bool, blocked: list[str], probed: int) -> CheckResult:
    """Pure verdict logic for crawler-access probing (separated for testability)."""
    if not baseline_ok:
        return CheckResult(
            status="fail",
            details="Homepage didn't return 200 for a normal browser; can't assess crawler access.",
        )
    if not blocked:
        return CheckResult(
            status="pass", details="All probed AI crawler UAs reach the site (no UA block)."
        )
    if len(blocked) == probed:
        return CheckResult(
            status="fail",
            details=f"All probed AI crawler UAs blocked at the edge: {', '.join(blocked)}.",
        )
    return CheckResult(
        status="partial",
        details=f"Some AI crawler UAs are blocked at the edge (CDN/WAF): {', '.join(blocked)}.",
    )


def check_robots_txt(domain: str) -> CheckResult:
    """Check whether AI crawlers are allowed by robots.txt."""
    base = _base_url(domain)
    response = _get(f"{base}/robots.txt")
    if response is None:
        return CheckResult(status="fail", details="Could not fetch robots.txt (request failed).")
    if response.status_code == 404:
        return CheckResult(
            status="pass",
            details="No robots.txt present; crawlers are not restricted by default.",
        )
    if response.status_code >= 400:
        return CheckResult(
            status="fail",
            details=f"robots.txt returned HTTP {response.status_code}.",
        )

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    blocked = [agent for agent in AI_USER_AGENTS if not parser.can_fetch(agent, base + "/")]

    if not blocked:
        return CheckResult(status="pass", details="All tracked AI crawlers are allowed.")
    if len(blocked) == len(AI_USER_AGENTS):
        return CheckResult(
            status="fail",
            details=f"All tracked AI crawlers are blocked: {', '.join(blocked)}.",
        )
    return CheckResult(
        status="partial",
        details=f"Some AI crawlers are blocked: {', '.join(blocked)}.",
    )


def check_llms_txt(domain: str) -> CheckResult:
    """Check whether a valid llms.txt is present."""
    base = _base_url(domain)
    response = _get(f"{base}/llms.txt")
    if response is None:
        return CheckResult(status="fail", details="Could not fetch llms.txt (request failed).")
    if response.status_code == 404:
        return CheckResult(status="fail", details="No llms.txt found (HTTP 404).")
    if response.status_code >= 400:
        return CheckResult(status="fail", details=f"llms.txt returned HTTP {response.status_code}.")
    if not response.text.strip():
        return CheckResult(status="partial", details="llms.txt present but empty.")
    return CheckResult(status="pass", details="llms.txt present and non-empty.")


def check_sitemap(domain: str) -> CheckResult:
    """Check whether an XML sitemap is present and well-formed."""
    base = _base_url(domain)
    response = _get(f"{base}/sitemap.xml")
    if response is None:
        return CheckResult(status="fail", details="Could not fetch sitemap.xml (request failed).")
    if response.status_code == 404:
        return CheckResult(status="fail", details="No sitemap.xml found (HTTP 404).")
    if response.status_code >= 400:
        return CheckResult(
            status="fail", details=f"sitemap.xml returned HTTP {response.status_code}."
        )
    body = response.text
    if "<urlset" not in body and "<sitemapindex" not in body:
        return CheckResult(
            status="partial",
            details="sitemap.xml reachable but no <urlset>/<sitemapindex> root found.",
        )

    lastmods = re.findall(r"<lastmod>\s*(\d{4}-\d{2}-\d{2})", body)
    if not lastmods:
        return CheckResult(
            status="pass",
            details="XML sitemap present and well-formed (no <lastmod> dates to assess freshness).",
        )
    try:
        newest = max(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=UTC) for d in lastmods)
    except ValueError:
        return CheckResult(status="pass", details="XML sitemap present and well-formed.")
    age_days = (datetime.now(UTC) - newest).days
    if age_days > 180:
        return CheckResult(
            status="partial",
            details=f"XML sitemap present but stale (newest <lastmod> is {age_days} days old).",
        )
    return CheckResult(
        status="pass",
        details=f"XML sitemap present and current (newest <lastmod> {age_days} days old).",
    )


_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _visible_text(html: str) -> str:
    """Approximate the text a non-JS crawler would see: drop script/style/comments
    and tags, collapse whitespace. Counting raw HTML length over-counts inlined
    JS bundles and misses SPA shells; counting visible text is the real signal.
    """
    stripped = _SCRIPT_STYLE_RE.sub(" ", html)
    stripped = _COMMENT_RE.sub(" ", stripped)
    stripped = _TAG_RE.sub(" ", stripped)
    return _WS_RE.sub(" ", stripped).strip()


def _classify_rendering(visible_chars: int, spa_shell: bool) -> CheckResult:
    """Pure verdict logic for the rendering heuristic (separated for testability)."""
    if visible_chars >= 1500:
        return CheckResult(
            status="pass",
            details=f"Homepage returns substantial server-rendered text (~{visible_chars} chars).",
        )
    if spa_shell and visible_chars < 500:
        return CheckResult(
            status="fail",
            details=(
                f"SPA shell detected (client-render mount point) with only ~{visible_chars} "
                "chars of server-rendered text; AI crawlers that don't run JS will see little."
            ),
        )
    if visible_chars < 200:
        return CheckResult(
            status="fail",
            details=f"Almost no server-rendered text (~{visible_chars} chars); likely JS-only.",
        )
    if visible_chars < 600:
        return CheckResult(
            status="partial",
            details=(
                f"Thin server-rendered text (~{visible_chars} chars); "
                "key content may rely on client-side rendering."
            ),
        )
    return CheckResult(
        status="pass",
        details=f"Homepage returns adequate server-rendered text (~{visible_chars} chars).",
    )


def check_rendering(domain: str) -> CheckResult:
    """Heuristically check whether core content is server-rendered, not JS-only.

    Measures *visible* text (script/style/tags stripped) rather than raw HTML
    length, and flags SPA shells (a framework mount point with little text) — the
    React/Next hydration-only case that a raw-length check misses.
    """
    base = _base_url(domain)
    response = _get(base + "/")
    if response is None:
        return CheckResult(status="fail", details="Could not fetch homepage (request failed).")
    if response.status_code >= 400:
        return CheckResult(status="fail", details=f"Homepage returned HTTP {response.status_code}.")

    html = response.text
    lowered = html.lower()
    visible_chars = len(_visible_text(html))
    spa_shell = any(marker in lowered for marker in _SPA_SHELL_MARKERS)
    return _classify_rendering(visible_chars, spa_shell)


def check_crawler_access(domain: str) -> CheckResult:
    """Probe whether AI crawler UAs are blocked at the CDN/WAF layer.

    robots.txt can permit a crawler while Cloudflare (which defaults to blocking
    AI bots) returns 403 to its UA. We fetch the homepage with a normal browser
    UA as a baseline, then with each AI crawler UA, and flag any that are blocked
    while the browser succeeds — the exact failure mode robots.txt can't reveal.
    """
    base = _base_url(domain)
    baseline = _get(base + "/", user_agent=BROWSER_UA)
    baseline_ok = baseline is not None and baseline.status_code == 200

    blocked: list[str] = []
    for name, ua in AI_CRAWLER_UAS.items():
        resp = _get(base + "/", user_agent=ua)
        if resp is None or resp.status_code >= 400:
            blocked.append(name)
    return _classify_crawler_access(baseline_ok, blocked, len(AI_CRAWLER_UAS))


def check_gated_content(domain: str) -> CheckResult:
    """Heuristically check whether the homepage is gated behind login/paywall/form."""
    base = _base_url(domain)
    response = _get(base + "/")
    if response is None:
        return CheckResult(status="fail", details="Could not fetch homepage (request failed).")
    if response.status_code >= 400:
        return CheckResult(status="fail", details=f"Homepage returned HTTP {response.status_code}.")

    lowered = response.text.lower()
    hits = [marker for marker in _GATING_MARKERS if marker in lowered]
    if not hits:
        return CheckResult(
            status="pass", details="No login/paywall/gating markers on the homepage."
        )
    return CheckResult(
        status="partial",
        details=f"Possible gating markers ({', '.join(hits)}); confirm target content isn't gated.",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    target = "example.com"
    print(f"Running technical checks against {target}\n")
    checks = {
        "robots.txt": check_robots_txt(target),
        "crawler-access (UA/WAF)": check_crawler_access(target),
        "llms.txt": check_llms_txt(target),
        "sitemap": check_sitemap(target),
        "rendering": check_rendering(target),
        "gated-content": check_gated_content(target),
    }
    for name, result in checks.items():
        print(f"[{result['status'].upper():7s}] {name}: {result['details']}")
