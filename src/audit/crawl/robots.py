"""robots.txt policy for the crawler — honor Crawl-delay + Disallow (impl §1.5).

Uses Protego (RFC 9309-correct, the Scrapy default) rather than the stdlib
``robotparser`` (which is non-compliant on longest-match/Allow-precedence and
ignores ``Crawl-delay``). Best-effort: a missing/unreadable robots.txt yields a
permissive policy so the crawl still runs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from protego import Protego

from src.audit.crawl.fetcher import GPTBOT_UA
from src.net_guard import UnsafeUrlError, assert_public_url

__all__ = ["RobotsPolicy", "load_robots", "ROBOTS_UA_TOKEN"]

logger = logging.getLogger(__name__)

# We crawl as GPTBot, so robots decisions are evaluated for GPTBot's rules
# (falling back to ``*`` when there's no GPTBot group).
ROBOTS_UA_TOKEN = "GPTBot"

_ROBOTS_TIMEOUT = httpx.Timeout(connect=8.0, read=10.0, write=10.0, pool=8.0)


@dataclass
class RobotsPolicy:
    """A parsed robots.txt (or ``None`` = no robots / permissive)."""

    parser: Protego | None

    def allowed(self, url: str, user_agent: str = ROBOTS_UA_TOKEN) -> bool:
        return self.parser is None or bool(self.parser.can_fetch(url, user_agent))

    def crawl_delay(self, user_agent: str = ROBOTS_UA_TOKEN) -> float | None:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(user_agent)
        return float(delay) if delay is not None else None


def load_robots(domain: str) -> RobotsPolicy:
    """Fetch and parse ``/robots.txt`` for ``domain``; permissive on any failure."""
    host = urlsplit(domain if "://" in domain else f"https://{domain}").hostname or domain
    url = f"https://{host}/robots.txt"
    try:
        assert_public_url(url)
        response = httpx.get(
            url, timeout=_ROBOTS_TIMEOUT, headers={"User-Agent": GPTBOT_UA}, follow_redirects=True
        )
    except (httpx.HTTPError, UnsafeUrlError) as exc:
        logger.info("robots.txt fetch failed for %s: %s", host, type(exc).__name__)
        return RobotsPolicy(None)
    if response.status_code >= 400 or not response.text.strip():
        return RobotsPolicy(None)  # no robots.txt → not restricted
    try:
        return RobotsPolicy(Protego.parse(response.text))
    except Exception as exc:  # malformed robots.txt — don't block the crawl
        logger.warning("robots.txt parse failed for %s: %s", host, exc)
        return RobotsPolicy(None)
