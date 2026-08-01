"""Competitor candidates for a service-area business, from Google's local pack.

`docs/competitor-set-plan.md` C1. The second artifact a lead needs: the worker
turns a lead into a fact sheet, and a run also needs the brands to measure it
against. Competitors reached a run from exactly one place — a hand-typed
``config,competitors`` row — so the automated path produced something that could
not start an audit.

**Why the local pack and not a model.** ``LocalEntity`` already states the rule:
a model does not reliably know the plumbers in a given city, and a fabricated
rival printed in a teaser emailed to a real shop owner is the unrecoverable
failure for this product. The pack is Google's own answer to "who does this here",
retrieved over plain HTTP with no model in the path, and every candidate carries
the listing it came from.

This is the LOCAL path only. A consumer product's rivals are national brands a
model genuinely knows and a human can check at a glance, and the teaser resolver
already handles those — nothing here changes that.

Nothing in this module decides who the *real* competitor is. It produces a
measured, evidenced list for a human to approve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.engines.local_pack import LocalEntity

__all__ = [
    "AGGREGATOR_HOSTS",
    "DEFAULT_MAX_CANDIDATES",
    "CompetitorCandidate",
    "CompetitorSet",
    "candidates_from_local_pack",
]

# Directories, marketplaces and lead-gen platforms. They outrank every real
# business for local queries, and measuring a shop against Yelp produces a report
# that says it loses to Yelp — true, and useless to the owner.
AGGREGATOR_HOSTS: frozenset[str] = frozenset(
    {
        "yelp.com",
        "angi.com",
        "angieslist.com",
        "thumbtack.com",
        "homeadvisor.com",
        "porch.com",
        "houzz.com",
        "nextdoor.com",
        "bbb.org",
        "yellowpages.com",
        "superpages.com",
        "mapquest.com",
        "tripadvisor.com",
        "facebook.com",
        "google.com",
    }
)

# Words that mark a pack entry as a directory rather than a business, for the
# listings that carry no website to match on.
_AGGREGATOR_NAME_RE = re.compile(
    r"\b(yelp|angi|angie'?s list|thumbtack|homeadvisor|home advisor|porch|houzz"
    r"|yellow ?pages|better business bureau)\b",
    re.IGNORECASE,
)

# Every competitor multiplies judge cost across every answer of every run, so the
# set is capped. 5 is the working ceiling; what the cap drops is RECORDED, because
# a silent truncation reads as "we looked and there were only five".
DEFAULT_MAX_CANDIDATES: int = 5


@dataclass(frozen=True)
class CompetitorCandidate:
    """One evidenced rival. ``evidence`` is what a reviewer checks, not prose."""

    name: str
    source: str  # "local_pack"
    evidence: str  # the listing as Google returned it
    source_query: str
    location: str
    as_of: str
    category: str | None = None
    rating: float | None = None
    reviews: int | None = None
    position: int | None = None
    website: str | None = None


@dataclass
class CompetitorSet:
    """Candidates a human may approve, plus what was left out and why.

    ``exclusions`` is not debug output. A reviewer needs to see that the obvious
    local name was dropped as an aggregator, or lost to the cap, because the
    alternative is a list that looks complete and is not.
    """

    domain: str
    location: str
    source_query: str
    generated_at: str
    candidates: list[CompetitorCandidate] = field(default_factory=list)
    exclusions: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)

    @property
    def names(self) -> list[str]:
        """Just the names — the shape ``config,competitors`` wants."""
        return [c.name for c in self.candidates]


def _host(url: str | None) -> str:
    if not url:
        return ""
    match = re.search(r"^(?:https?://)?(?:www\.)?([^/?#]+)", url.strip(), re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _norm(name: str) -> str:
    """Compare names ignoring case, punctuation and common legal/trade suffixes."""
    text = re.sub(r"[^\w\s]", " ", name or "").lower()
    text = re.sub(
        r"\b(inc|llc|ltd|co|corp|company|the|and|plumbing|heating|cooling|hvac|services?)\b",
        " ",
        text,
    )
    return " ".join(text.split())


def _is_client(entity: LocalEntity, client_name: str, aliases: list[str], client_host: str) -> bool:
    """Whether this listing IS the client.

    Checked on the WEBSITE first, then on the normalised name. A business listed
    under a slightly different trading name would otherwise appear as its own
    competitor — and its share-of-voice would be split between two entries that
    are the same shop.
    """
    host = _host(entity.get("website"))
    if client_host and host and host == client_host:
        return True
    listed = _norm(entity.get("name", ""))
    if not listed:
        return False
    for candidate in [client_name, *aliases]:
        known = _norm(candidate)
        if known and (listed == known or known in listed or listed in known):
            return True
    return False


def _is_aggregator(entity: LocalEntity) -> bool:
    return _host(entity.get("website")) in AGGREGATOR_HOSTS or bool(
        _AGGREGATOR_NAME_RE.search(entity.get("name", ""))
    )


def _evidence(entity: LocalEntity, query: str, location: str) -> str:
    """The listing, as Google returned it — what a reviewer checks the name against."""
    parts = [entity.get("name", "")]
    if entity.get("category"):
        parts.append(str(entity["category"]))
    if entity.get("address"):
        parts.append(str(entity["address"]))
    listing = " — ".join(p for p in parts if p)
    return f'Google local pack for "{query}" in {location}: {listing}'


def candidates_from_local_pack(
    entities: list[LocalEntity],
    *,
    client_name: str,
    client_website: str | None,
    source_query: str,
    location: str,
    as_of: str,
    domain: str = "",
    aliases: list[str] | None = None,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> CompetitorSet:
    """Turn one local-pack capture into an approvable competitor set. Pure.

    Order is Google's — pack position is a real ranking signal and re-sorting it by
    rating would substitute our judgement for the market's, which is the one thing
    this module is not for.

    Every drop is recorded with a reason: the client itself, aggregators, entries
    with no usable name, duplicates, and anything past the cap.
    """
    aliases = aliases or []
    client_host = _host(client_website)
    result = CompetitorSet(
        domain=domain or client_host,
        location=location,
        source_query=source_query,
        generated_at=as_of,
    )
    seen: set[str] = set()

    for entity in entities:
        name = (entity.get("name") or "").strip()
        if not name:
            continue
        if _is_client(entity, client_name, aliases, client_host):
            result.exclusions.append((name, "this is the client"))
            continue
        if _is_aggregator(entity):
            result.exclusions.append((name, "directory or marketplace, not a competing business"))
            continue
        key = _norm(name)
        if key in seen:
            result.exclusions.append((name, "duplicate listing"))
            continue
        if len(result.candidates) >= max_candidates:
            result.exclusions.append((name, f"over the cap of {max_candidates}"))
            continue
        seen.add(key)
        result.candidates.append(
            CompetitorCandidate(
                name=name,
                source="local_pack",
                evidence=_evidence(entity, source_query, location),
                source_query=source_query,
                location=location,
                as_of=as_of,
                category=entity.get("category") or None,
                rating=entity.get("rating"),
                reviews=entity.get("reviews"),
                position=entity.get("position"),
                website=entity.get("website") or None,
            )
        )
    return result
