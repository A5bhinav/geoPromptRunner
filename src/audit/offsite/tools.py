"""Concrete offsite data-source tools (impl guide §5.3).

Each tool is a plain function returning a :class:`ToolResult`. Tools that need a
key degrade to ``available=False`` when it's unset rather than raising, so the
agent runs with whatever sources are configured. Wikidata needs no key and is the
always-on baseline. All tools hit fixed, well-known API hosts (not user-supplied
URLs), so SSRF isn't a concern here — the brand/domain are query parameters only.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx
import tldextract

from src.config import settings

__all__ = [
    "ToolResult",
    "wikidata_entity",
    "serper_search",
    "reddit_search",
    "dataforseo_backlinks",
    "reviews_presence",
    "configured_tools",
    "REVIEW_PLATFORMS",
]

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=8.0, read=15.0, write=15.0, pool=8.0)
_UA = "geo-audit/0.1 (offsite research; +https://fort.cx)"
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())

# Wikidata "instance of" (P31) values that discriminate a real org/brand entity.
_ORG_QIDS = frozenset(
    {"Q4830453", "Q43229", "Q891723", "Q167270", "Q6881511", "Q783794", "Q1058914"}
)

REVIEW_PLATFORMS = (
    "trustpilot.com",
    "g2.com",
    "apps.apple.com",
    "play.google.com",
)


@dataclass
class ToolResult:
    available: bool
    source: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _registered_domain(url_or_host: str) -> str:
    host = urlsplit(url_or_host).hostname or url_or_host
    return _EXTRACT(host).top_domain_under_public_suffix.lower()


def configured_tools() -> dict[str, bool]:
    """Which offsite tools have their credentials set (Wikidata needs none)."""
    return {
        "wikidata": True,
        "serper": bool(settings.SERPER_API_KEY),
        "reddit": bool(settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET),
        "dataforseo": bool(settings.DATAFORSEO_LOGIN and settings.DATAFORSEO_PASSWORD),
    }


# --- Wikidata (no key) -------------------------------------------------------

_WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def wikidata_entity(brand: str, domain: str) -> ToolResult:
    """Resolve a brand to a Wikidata entity (``wbsearchentities`` → ``wbgetentities``).

    A match requires a top label hit AND a discriminating claim — either P856
    (official website) matching the audited domain, or P31 (instance-of) in the
    org/brand set — so a coincidental name match doesn't count (§5.3).
    """
    site_domain = _registered_domain(domain if "://" in domain else f"https://{domain}")
    try:
        with httpx.Client(timeout=_TIMEOUT, headers={"User-Agent": _UA}) as client:
            search = client.get(
                _WIKIDATA_API,
                params={
                    "action": "wbsearchentities",
                    "search": brand,
                    "language": "en",
                    "format": "json",
                    "limit": 5,
                },
            ).json()
            candidates = [c.get("id") for c in search.get("search", []) if c.get("id")]
            if not candidates:
                return ToolResult(True, "wikidata", {"found": False})
            entities = client.get(
                _WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(candidates[:5]),
                    "props": "claims|labels|descriptions",
                    "languages": "en",
                    "format": "json",
                },
            ).json()
    except (httpx.HTTPError, ValueError) as exc:
        return ToolResult(False, "wikidata", error=type(exc).__name__)

    for qid in candidates:
        entity = entities.get("entities", {}).get(qid)
        if not entity:
            continue
        matched_by = _wikidata_match(entity, site_domain)
        if matched_by:
            return ToolResult(
                True,
                "wikidata",
                {
                    "found": True,
                    "qid": qid,
                    "label": _first_value(entity.get("labels", {})),
                    "description": _first_value(entity.get("descriptions", {})),
                    "matched_by": matched_by,
                },
            )
    return ToolResult(True, "wikidata", {"found": False, "candidates": candidates})


def _first_value(localized: dict[str, Any]) -> str:
    entry: Any = localized.get("en") or next(iter(localized.values()), {})
    return str(entry.get("value", "")) if isinstance(entry, dict) else ""


def _wikidata_match(entity: dict[str, Any], site_domain: str) -> str | None:
    claims = entity.get("claims", {})
    for snak in claims.get("P856", []):  # official website
        url = _claim_string(snak)
        if url and _registered_domain(url) == site_domain:
            return "P856"
    for snak in claims.get("P31", []):  # instance of
        qid = _claim_entity_id(snak)
        if qid in _ORG_QIDS:
            return "P31"
    return None


def _claim_string(snak: dict[str, Any]) -> str | None:
    value = snak.get("mainsnak", {}).get("datavalue", {}).get("value")
    return value if isinstance(value, str) else None


def _claim_entity_id(snak: dict[str, Any]) -> str | None:
    value = snak.get("mainsnak", {}).get("datavalue", {}).get("value")
    return value.get("id") if isinstance(value, dict) else None


# --- Serper.dev search (key) -------------------------------------------------

_SERPER_URL = "https://google.serper.dev/search"


def serper_search(query: str, num: int = 10) -> ToolResult:
    """Google SERP via Serper.dev — organic results + knowledge graph + rich snippets."""
    if not settings.SERPER_API_KEY:
        return ToolResult(False, "serper", error="SERPER_API_KEY not set")
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _SERPER_URL,
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": num},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return ToolResult(False, "serper", error=type(exc).__name__)
    organic = [
        {"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in data.get("organic", [])
    ]
    return ToolResult(
        True,
        "serper",
        {"query": query, "organic": organic, "knowledge_graph": data.get("knowledgeGraph", {})},
    )


# --- Reddit Data API (OAuth2 client-credentials) -----------------------------

_REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_REDDIT_SEARCH_URL = "https://oauth.reddit.com/search"


def reddit_search(brand: str, limit: int = 10) -> ToolResult:
    """Search Reddit for brand mentions via the official Data API (OAuth2)."""
    if not (settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET):
        return ToolResult(False, "reddit", error="Reddit credentials not set")
    try:
        with httpx.Client(
            timeout=_TIMEOUT, headers={"User-Agent": settings.REDDIT_USER_AGENT}
        ) as client:
            token_resp = client.post(
                _REDDIT_TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
            )
            token_resp.raise_for_status()
            token = token_resp.json().get("access_token")
            if not token:
                return ToolResult(False, "reddit", error="no access token")
            search = client.get(
                _REDDIT_SEARCH_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={"q": brand, "limit": limit, "sort": "relevance", "type": "link"},
            )
            search.raise_for_status()
            data = search.json()
    except (httpx.HTTPError, ValueError) as exc:
        return ToolResult(False, "reddit", error=type(exc).__name__)
    posts = [
        {
            "title": c.get("data", {}).get("title", ""),
            "subreddit": c.get("data", {}).get("subreddit", ""),
            "score": c.get("data", {}).get("score", 0),
            "permalink": "https://reddit.com" + c.get("data", {}).get("permalink", ""),
        }
        for c in data.get("data", {}).get("children", [])
    ]
    return ToolResult(True, "reddit", {"brand": brand, "posts": posts})


# --- DataForSEO backlinks summary (key) --------------------------------------

_DATAFORSEO_URL = "https://api.dataforseo.com/v3/backlinks/summary/live"


def dataforseo_backlinks(domain: str) -> ToolResult:
    """One-call backlinks headline numbers (referring domains + rank) via DataForSEO."""
    if not (settings.DATAFORSEO_LOGIN and settings.DATAFORSEO_PASSWORD):
        return ToolResult(False, "dataforseo", error="DataForSEO credentials not set")
    target = _registered_domain(domain if "://" in domain else f"https://{domain}")
    auth = base64.b64encode(
        f"{settings.DATAFORSEO_LOGIN}:{settings.DATAFORSEO_PASSWORD}".encode()
    ).decode()
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _DATAFORSEO_URL,
                headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
                json=[{"target": target, "internal_list_limit": 10}],
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return ToolResult(False, "dataforseo", error=type(exc).__name__)
    tasks = data.get("tasks") or []
    result = (tasks[0].get("result") or [{}])[0] if tasks else {}
    return ToolResult(
        True,
        "dataforseo",
        {
            "target": target,
            "referring_domains": result.get("referring_domains"),
            "backlinks": result.get("backlinks"),
            "rank": result.get("rank"),
        },
    )


# --- Reviews presence (SERP-based, lowest-risk) ------------------------------


def reviews_presence(brand: str) -> ToolResult:
    """Detect review-platform presence via SERP ``site:`` queries (no scraping, §5.3)."""
    if not settings.SERPER_API_KEY:
        return ToolResult(False, "reviews", error="SERPER_API_KEY not set")
    platforms: dict[str, dict[str, Any]] = {}
    for host in REVIEW_PLATFORMS:
        result = serper_search(f'site:{host} "{brand}"', num=3)
        if not result.available:
            return ToolResult(False, "reviews", error=result.error)
        organic = result.data.get("organic", [])
        platforms[host] = {
            "present": bool(organic),
            "top_url": organic[0]["link"] if organic else None,
        }
    return ToolResult(True, "reviews", {"brand": brand, "platforms": platforms})
