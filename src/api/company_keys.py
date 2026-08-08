"""How a run or a teaser is mapped to the company it belongs to.

These four functions were `src/api/projects.py`'s private helpers, and they are
the single definition of what a project key IS. They moved here — unchanged —
when LIC-T1 turned companies from a per-request GROUP BY into real rows, because
the backfill (`scripts/backfill_companies.py`) has to derive exactly the same keys
the UI already shows. Two normalisers would mean the migration silently minting a
second tenant for a client that already has one, which under RLS is a client who
cannot see their own reports.

The key is the registrable domain when we know one, and ``name:<slug>`` when we do
not. That asymmetry is deliberate: a domain identifies a business, a name does
not, so a domain-less run gets its own bucket rather than being merged with
unrelated work on a name match.
"""

from __future__ import annotations

import re

__all__ = ["norm_domain", "slugify", "domains_of", "key_for", "NAME_KEY_PREFIX"]

#: Marks a key derived from a client NAME rather than a domain. Load-bearing:
#: `domain_of_key` reads it back, and a company whose slug starts with this has
#: no verified domain — so nothing may join it to a fact sheet or a crawl.
NAME_KEY_PREFIX = "name:"


def norm_domain(raw: object) -> str:
    """Bare host of a URL or domain string (lowercased, scheme/path/port/www stripped).

    Accepts both ``https://www.fort.cx/pricing`` and a bare ``fort.cx`` so an
    audit's domain and a teaser's prospect_url normalize to the same key.
    """
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)  # drop scheme
    s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    s = s.split("@")[-1]  # drop any userinfo
    s = s.split(":", 1)[0]  # drop port
    return s[4:] if s.startswith("www.") else s


def slugify(raw: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(raw or "").strip().lower()).strip("-")


def domains_of(raw: object) -> list[str]:
    """A row's ``client_domains`` as a clean list of strings. DB row values are
    typed ``object``, so guard the type: a non-list value (e.g. a bare string)
    must yield ``[]`` rather than being iterated character-by-character."""
    if not isinstance(raw, list):
        return []
    return [str(d) for d in raw if d]


def key_for(domain: str, name: object) -> tuple[str, str, str | None]:
    """(key, label, domain) for a domain (preferred) or a client/company name."""
    if domain:
        return domain, domain, domain
    slug = slugify(name) or "untitled"
    return f"{NAME_KEY_PREFIX}{slug}", (str(name).strip() if name else "Untitled"), None
