from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Literal, TypedDict
from urllib.parse import urlsplit

import httpx
from protego import Protego

from src.net_guard import UnsafeUrlError, safe_get

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
    "OAI-SearchBot": "Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
    "ClaudeBot": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "PerplexityBot": "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Google-Extended": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}

# We fetch the standalone Cat-1 checks AS GPTBot so they measure what GPTBot
# actually receives (the recipes specify -A "GPTBot"). The deep crawler already
# does this; this constant brings the lightweight checks in line.
GPTBOT_UA = AI_CRAWLER_UAS["GPTBot"]

# A Cloudflare/anti-bot interstitial can be served at HTTP 200, so a status check
# alone misses it. Mirrors crawl/fetcher.py's challenge detection.
_CF_CHALLENGE_MARKERS: tuple[str, ...] = (
    "just a moment",
    "cf-browser-verification",
    "challenge-platform",
    "cf_chl_opt",
    "attention required",
)

# Redirect targets / paths that mean the real content sits behind auth.
_AUTH_PATH_MARKERS: tuple[str, ...] = (
    "/login",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/auth",
    "/account",
    "/subscribe",
)

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


# Pooled client reused across checks; redirects are followed by safe_get (which
# SSRF-validates every hop), so the client itself must not auto-follow.
_HTTP = httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False)


def _get(url: str, user_agent: str | None = None) -> httpx.Response | None:
    """GET a URL with a 10s timeout, following redirects. None on transport error.

    User-supplied domains are fetched here, so every hop is SSRF-checked
    (``safe_get`` rejects non-http(s) and private/loopback/metadata targets).
    Pass ``user_agent`` to probe how the site responds to a specific crawler UA.
    """
    headers = {"User-Agent": user_agent} if user_agent else None
    try:
        return safe_get(_HTTP, url, headers=headers)
    except (httpx.HTTPError, UnsafeUrlError) as exc:
        logger.warning("Request to %s failed: %s", url, type(exc).__name__)
        return None


def _content_type(response: httpx.Response) -> str:
    """The bare content-type (no charset), lowercased."""
    return str(response.headers.get("content-type", "")).split(";")[0].strip().lower()


def _is_challenge(response: httpx.Response) -> bool:
    """True if this is an anti-bot challenge — including one served at HTTP 200.

    A status check alone misses a Cloudflare "Just a moment…" interstitial that
    returns 200; mirrors crawl/fetcher.py's detection.
    """
    if "cf-mitigated" in response.headers:
        return True
    server = response.headers.get("server", "").lower()
    if "cloudflare" in server:
        low = response.text.lower()
        return any(marker in low for marker in _CF_CHALLENGE_MARKERS)
    return False


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

    # Protego is RFC 9309-compliant (longest-match + Allow-precedence); the stdlib
    # RobotFileParser uses source-order first-match and wrongly blocks e.g.
    # /admin/public/ when an Allow should win (CPython #138907). (plan §9.3)
    parser = Protego.parse(response.text)
    blocked = [agent for agent in AI_USER_AGENTS if not parser.can_fetch(base + "/", agent)]

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
    """Check whether a valid llms.txt is present (fetched as GPTBot).

    Guards the app-shell trap: an SPA that serves ``index.html`` (HTTP 200,
    ``text/html``) for any unknown path makes a missing llms.txt *look* present.
    A real llms.txt is plain text / markdown, so an HTML body at 200 is treated as
    absent.
    """
    base = _base_url(domain)
    response = _get(f"{base}/llms.txt", user_agent=GPTBOT_UA)
    if response is None:
        return CheckResult(status="fail", details="Could not fetch llms.txt (request failed).")
    if response.status_code == 404:
        return CheckResult(status="fail", details="No llms.txt found (HTTP 404).")
    if response.status_code >= 400:
        return CheckResult(status="fail", details=f"llms.txt returned HTTP {response.status_code}.")
    body = response.text
    if not body.strip():
        return CheckResult(status="partial", details="llms.txt present but empty.")
    ctype = _content_type(response)
    if ctype == "text/html" or "<html" in body[:1000].lower():
        return CheckResult(
            status="fail",
            details=(
                "llms.txt returns an HTML page (likely the SPA app-shell served for "
                "unknown paths); treat as absent."
            ),
        )
    return CheckResult(
        status="pass",
        details=f"llms.txt present and non-empty (content-type {ctype or 'unknown'}).",
    )


def check_sitemap(domain: str) -> CheckResult:
    """Check whether an XML sitemap is present, well-formed, and current (as GPTBot).

    Guards the same app-shell trap as llms.txt (an SPA serving ``index.html`` at
    200) and reports the ``<loc>`` count so an empty/near-empty sitemap is visible.
    """
    base = _base_url(domain)
    response = _get(f"{base}/sitemap.xml", user_agent=GPTBOT_UA)
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
        ctype = _content_type(response)
        if ctype == "text/html" or "<html" in body[:1000].lower():
            return CheckResult(
                status="fail",
                details="sitemap.xml returns an HTML page (app shell), not a real sitemap.",
            )
        return CheckResult(
            status="partial",
            details="sitemap.xml reachable but no <urlset>/<sitemapindex> root found.",
        )

    loc_count = len(_LOC_RE.findall(body))
    if loc_count == 0:
        return CheckResult(
            status="partial", details="Sitemap root present but contains no <loc> entries."
        )
    suffix = f" ({loc_count} <loc> entries)"
    lastmods = _LASTMOD_RE.findall(body)
    if not lastmods:
        return CheckResult(
            status="pass",
            details=f"XML sitemap present and well-formed{suffix}; no <lastmod> dates to assess.",
        )
    try:
        newest = max(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=UTC) for d in lastmods)
    except ValueError:
        return CheckResult(status="pass", details=f"XML sitemap present and well-formed{suffix}.")
    age_days = (datetime.now(UTC) - newest).days
    if age_days > 180:
        return CheckResult(
            status="partial",
            details=f"XML sitemap present but stale (newest <lastmod> {age_days}d old){suffix}.",
        )
    return CheckResult(
        status="pass",
        details=f"XML sitemap present and current (newest <lastmod> {age_days} days old){suffix}.",
    )


_LASTMOD_RE = re.compile(r"<lastmod>\s*(\d{4}-\d{2}-\d{2})")
_LOC_RE = re.compile(r"<loc>", re.IGNORECASE)
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
    response = _get(base + "/", user_agent=GPTBOT_UA)
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
        # A 200 can still be an anti-bot challenge body — flag those too.
        if resp is None or resp.status_code >= 400 or _is_challenge(resp):
            blocked.append(name)
    return _classify_crawler_access(baseline_ok, blocked, len(AI_CRAWLER_UAS))


def _gating_target_pages(domain: str) -> list[tuple[str, bool]]:
    """Homepage + a few priority pages (pricing/docs/blog) to test for gating.

    Uses the same sitemap-derived page-priority selection as the deep crawler; on
    any discovery failure it falls back to the homepage alone.
    """
    base = _base_url(domain)
    try:
        from src.audit.crawl.page_select import select_pages

        selected = select_pages(domain)[:5]
    except Exception as exc:  # discovery is best-effort
        logger.info("gating page selection failed for %s: %s", domain, type(exc).__name__)
        selected = []
    if not selected:
        return [(base + "/", True)]
    return [(url, i == 0) for i, (url, _category) in enumerate(selected)]


def _page_gating(response: httpx.Response) -> tuple[bool, str]:
    """Is this page gated behind auth? Returns (gated, reason).

    Detects an explicit 401/403, a redirect that landed on a login/auth path
    (``safe_get`` already followed it, so we read the final URL), and a thin
    login/paywall stub (gating markers with little real content).
    """
    if response.status_code in (401, 403):
        return True, f"HTTP {response.status_code}"
    final_path = (urlsplit(str(response.url)).path or "/").lower()
    if any(marker in final_path for marker in _AUTH_PATH_MARKERS):
        return True, f"redirects to {final_path}"
    low = response.text.lower()
    markers = [marker for marker in _GATING_MARKERS if marker in low]
    # A real page has substantial visible text; a login stub is short + gated.
    if markers and len(_visible_text(response.text)) < 500:
        return True, f"login/paywall stub ({', '.join(markers[:2])})"
    return False, ""


def check_gated_content(domain: str) -> CheckResult:
    """Check whether target content is reachable by GPTBot, not behind a login/paywall.

    Walks the homepage + priority pages **as GPTBot**, and for each detects an
    auth redirect / 401-403 / login stub (Comment 6). A page that returns real
    content is the pass signal; a gated homepage is a hard fail.
    """
    gated: list[str] = []
    assessed = 0
    home_gated = False
    for url, is_home in _gating_target_pages(domain):
        response = _get(url, user_agent=GPTBOT_UA)
        if response is None:
            continue
        if response.status_code >= 400 and response.status_code not in (401, 403):
            continue  # other errors aren't a gating signal
        assessed += 1
        is_gated, reason = _page_gating(response)
        if is_gated:
            gated.append(f"{urlsplit(url).path or '/'} ({reason})")
            home_gated = home_gated or is_home

    if assessed == 0:
        return CheckResult(status="fail", details="Could not reach any page to assess gating.")
    if not gated:
        return CheckResult(
            status="pass",
            details=f"GPTBot reaches real content on {assessed} page(s); no login/paywall gating.",
        )
    if home_gated:
        return CheckResult(
            status="fail",
            details=f"Homepage is gated for GPTBot: {gated[0]}.",
        )
    return CheckResult(
        status="partial",
        details=f"{len(gated)}/{assessed} priority pages gated for GPTBot: {'; '.join(gated)}.",
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
