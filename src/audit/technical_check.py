from __future__ import annotations

import logging
from typing import Literal, TypedDict
from urllib.robotparser import RobotFileParser

import httpx

__all__ = [
    "CheckResult",
    "check_robots_txt",
    "check_llms_txt",
    "check_sitemap",
    "check_rendering",
]

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0

# AI crawlers that should be allowed to reach a client's content.
AI_USER_AGENTS: tuple[str, ...] = (
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "PerplexityBot",
    "Google-Extended",
    "Bingbot",
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


def _get(url: str) -> httpx.Response | None:
    """GET a URL with a 10s timeout, following redirects. None on transport error."""
    try:
        return httpx.get(url, timeout=TIMEOUT_SECONDS, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.warning("Request to %s failed: %s", url, exc)
        return None


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
    if "<urlset" in body or "<sitemapindex" in body:
        return CheckResult(status="pass", details="XML sitemap present and well-formed.")
    return CheckResult(
        status="partial",
        details="sitemap.xml reachable but no <urlset>/<sitemapindex> root found.",
    )


def check_rendering(domain: str) -> CheckResult:
    """Heuristically check whether core content is server-rendered, not JS-only."""
    base = _base_url(domain)
    response = _get(base + "/")
    if response is None:
        return CheckResult(status="fail", details="Could not fetch homepage (request failed).")
    if response.status_code >= 400:
        return CheckResult(status="fail", details=f"Homepage returned HTTP {response.status_code}.")

    html = response.text
    lowered = html.lower()
    # Strip script/style-heavy markers is overkill; use a coarse text-length heuristic.
    has_paragraphs = "<p" in lowered or "<article" in lowered or "<main" in lowered
    text_len = len(html)

    if text_len > 2000 and has_paragraphs:
        return CheckResult(
            status="pass",
            details="Homepage returns substantial server-rendered HTML content.",
        )
    if text_len > 500:
        return CheckResult(
            status="partial",
            details="Homepage HTML is thin; content may rely on client-side rendering.",
        )
    return CheckResult(
        status="fail",
        details="Homepage returns almost no HTML; likely JS-only rendering.",
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    target = "example.com"
    print(f"Running technical checks against {target}\n")
    checks = {
        "robots.txt": check_robots_txt(target),
        "llms.txt": check_llms_txt(target),
        "sitemap": check_sitemap(target),
        "rendering": check_rendering(target),
    }
    for name, result in checks.items():
        print(f"[{result['status'].upper():7s}] {name}: {result['details']}")
