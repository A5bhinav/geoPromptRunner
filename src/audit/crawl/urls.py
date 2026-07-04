"""Pure URL/content helpers shared by the fetch tier and the cache.

Kept dependency-free (no storage, no network) so any layer can import them
without pulling in Supabase or httpx.
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from w3lib.url import canonicalize_url

__all__ = ["normalize_url", "content_hash"]

# Query params that identify a marketing campaign / click, not page content —
# dropped so the same page reached via different links caches once.
_TRACKING_KEYS = frozenset(
    {"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "igshid", "_hsenc", "_hsmi"}
)


def _strip_tracking_params(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


def normalize_url(url: str) -> str:
    """Canonical cache-key form for a URL.

    Strips tracking params, then ``w3lib.canonicalize_url`` (sorts the query,
    normalizes percent-encoding/IDN, drops the fragment — hand-rolling this is
    where bugs hide, §3.2), then lowercases the host and maps an empty path to
    ``/`` so trailing-slash/case variants collapse to one key.
    """
    canon = canonicalize_url(_strip_tracking_params(url))
    parts = urlsplit(canon)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    # Drop the port when it's the scheme default, so "host" and "host:443" (or
    # "host:80") don't become two cache keys / two link-graph nodes for one page.
    port = parts.port
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        port = None
    netloc = f"{host}:{port}" if port else host
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def content_hash(raw_bytes: bytes) -> str:
    """``sha256`` hex digest of the pre-parse bytes, for dedup/change-detection."""
    return hashlib.sha256(raw_bytes).hexdigest()
