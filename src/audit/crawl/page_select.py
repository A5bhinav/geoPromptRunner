"""Pick the priority page set to crawl from a domain (impl guide §1.4).

We never crawl a whole site — an audit pulls the homepage plus a small,
high-signal set (pricing, comparison, product, docs, blog) discovered from the
sitemap, scored by path pattern, and hard-capped. Per-category caps keep one
section (e.g. a huge blog) from crowding out the pages that actually move the
GEO/AEO verdict.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from src.audit.crawl.models import PageCategory

__all__ = [
    "CATEGORY_PATTERNS",
    "CATEGORY_CAPS",
    "GLOBAL_PAGE_CAP",
    "classify_url",
    "select_pages",
]

logger = logging.getLogger(__name__)

# (regex, priority weight) per category. Higher weight wins when a URL could match
# more than one. Patterns are matched case-insensitively against the URL path.
CATEGORY_PATTERNS: dict[PageCategory, tuple[str, int]] = {
    PageCategory.PRICING: (r"/pricing|/plans?|/cost", 10),
    PageCategory.COMPARISON: (r"/(vs|versus|compare|alternatives?)", 9),
    PageCategory.PRODUCT: (r"/products?|/features?|/solutions?|/platform", 8),
    PageCategory.DOCS: (r"/docs?|/documentation|/guide|/api", 6),
    PageCategory.BLOG: (r"/blog|/articles?|/resources|/news", 4),
}

# Per-category hard caps (newest by lastmod when over). Pricing/comparison are
# few-and-decisive; docs/blog can be large so cap tighter relative to their count.
CATEGORY_CAPS: dict[PageCategory, int] = {
    PageCategory.PRICING: 3,
    PageCategory.COMPARISON: 3,
    PageCategory.PRODUCT: 5,
    PageCategory.DOCS: 5,
    PageCategory.BLOG: 5,
}

# Homepage is always included; this bounds the total pages fetched per domain.
GLOBAL_PAGE_CAP: int = 20

# Compiled once. Ordered high→low weight so the first match is the best category.
_COMPILED_PATTERNS: list[tuple[PageCategory, re.Pattern[str], int]] = sorted(
    [
        (cat, re.compile(pat, re.IGNORECASE), weight)
        for cat, (pat, weight) in CATEGORY_PATTERNS.items()
    ],
    key=lambda item: item[2],
    reverse=True,
)

# Low-value/duplicate path segments dropped before scoring (pagination, taxonomy,
# author archives, locale duplicates of the same content).
_DROP_RE = re.compile(
    r"/(page|tag|tags|author|authors|category|categories)/|/page/\d+|[?&]page=\d+",
    re.IGNORECASE,
)
_LOCALE_SEGMENT_RE = re.compile(r"^/[a-z]{2}(-[a-z]{2})?/", re.IGNORECASE)


def _homepage(domain: str) -> str:
    """Normalize a bare domain (or any URL on it) to its ``https://host/`` homepage."""
    candidate = domain if "://" in domain else f"https://{domain}"
    host = urlsplit(candidate).hostname or domain
    return f"https://{host}/"


def classify_url(url: str) -> PageCategory:
    """Map a URL to its highest-weight matching :class:`PageCategory`.

    Returns :attr:`PageCategory.OTHER` when nothing matches. Pure function of the
    URL path — no network.
    """
    path = urlsplit(url).path or "/"
    for category, pattern, _weight in _COMPILED_PATTERNS:
        if pattern.search(path):
            return category
    return PageCategory.OTHER


def _depth(url: str) -> int:
    return len([seg for seg in (urlsplit(url).path or "/").split("/") if seg])


def select_pages(
    domain: str, sitemap_urls: list[str] | None = None
) -> list[tuple[str, PageCategory]]:
    """Return the capped, prioritized ``(url, category)`` set to crawl for ``domain``.

    Homepage is always first. When ``sitemap_urls`` is ``None`` the sitemap is
    discovered via trafilatura ``sitemap_search``; with no sitemap the set is just
    the homepage (nav-link fallback is a later refinement). Applies
    :data:`CATEGORY_CAPS` then :data:`GLOBAL_PAGE_CAP`, preferring shallow paths
    and dropping pagination/tag/author/locale duplicates.
    """
    home = _homepage(domain)
    selected: list[tuple[str, PageCategory]] = [(home, PageCategory.HOMEPAGE)]
    home_host = urlsplit(home).hostname

    if sitemap_urls is None:
        sitemap_urls = _discover_sitemap_urls(home)

    # Classify candidates, keep only same-host non-homepage non-junk URLs.
    by_category: dict[PageCategory, list[str]] = {}
    seen: set[str] = {home}
    for url in sitemap_urls:
        if urlsplit(url).hostname != home_host:
            continue
        if _DROP_RE.search(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        category = classify_url(_strip_locale(url))
        if category is PageCategory.OTHER:
            continue
        by_category.setdefault(category, []).append(url)

    # Apply per-category caps, preferring shallower paths (closer to the root).
    for category, urls in by_category.items():
        cap = CATEGORY_CAPS.get(category, GLOBAL_PAGE_CAP)
        ranked = sorted(urls, key=_depth)[:cap]
        selected.extend((url, category) for url in ranked)
        if len(selected) >= GLOBAL_PAGE_CAP:
            break

    return selected[:GLOBAL_PAGE_CAP]


def _strip_locale(url: str) -> str:
    """Drop a leading ``/en/`` style locale segment so it doesn't mask the category."""
    parts = urlsplit(url)
    path = parts.path or "/"
    stripped = _LOCALE_SEGMENT_RE.sub("/", path)
    return parts._replace(path=stripped).geturl()


def _discover_sitemap_urls(homepage: str) -> list[str]:
    """Discover URLs from the domain's sitemap(s); empty list on failure (best-effort).

    trafilatura probes several candidate sitemap paths and logs each 404 at
    ERROR — normal for a site without a sitemap, but alarming in an audit log.
    Those loggers are quieted for the duration of the probe only.
    """
    quiet = logging.getLogger("trafilatura")
    previous = quiet.level
    quiet.setLevel(logging.CRITICAL)
    try:
        from trafilatura import sitemaps

        return list(sitemaps.sitemap_search(homepage))
    except Exception as exc:  # network/parse failure → homepage-only crawl
        logger.warning("sitemap discovery failed for %s: %s", homepage, exc)
        return []
    finally:
        quiet.setLevel(previous)
