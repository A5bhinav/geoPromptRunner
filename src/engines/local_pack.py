"""Capture Google's local pack — the surface that actually answers local queries.

Why this is its own module and not an engine: a local pack is a **ranked list of
businesses**, not an answer. Routing it through ``BaseEngine.query`` would put it into
``metrics.detect_mention``, into the judge (which would emit prominence/framing verdicts
about a SERP listing — a category error), and into ``mention_rate``/``share_of_model``
alongside genuine AI answers. It is captured as its own artifact instead.

Why it matters: Google shows a local pack for ~93% of local-intent queries and an AI
Overview for ~15%. ``engine_routing`` stops paying the AIO surface for those queries;
this is what measures them instead.

**Vendor: Serper ``/places``, sole source.** It was probed head-to-head against the
SearchApi capture this module used to fall back to (2026-07-28, same query and market)
and won on every axis — 10 businesses vs 3, street addresses, phone and website (both NAP
inputs) where SearchApi returned neither, at ~$0.001/query against ~$0.004 with a $40
monthly floor. SearchApi has since been removed from the codebase entirely; DataForSEO
covers the AI Overviews surface it used to serve.

**Consequences of being single-vendor**, stated plainly rather than discovered later:

- A Serper outage means no local-pack capture at all. ``fetch_local_pack`` returns
  ``([], SOURCE_NONE)``, the phase writes nothing, and the run reports the pack absent —
  it never fabricates or degrades silently. Serper's free tier is 2,500 queries, so the
  realistic failure is an outage, not exhaustion.
- Serper exposes **no closed-business flag**. SearchApi had ``is_closed``, and the parser
  used it to avoid recommending a shut-down business — the local twin of
  ``DEFUNCT_BRANDS``. That guard is now unenforceable because the field does not exist to
  check. Recorded as a known gap, not papered over. The entities carry ``website``, and a
  dead site is a strong closed signal, but that is a check to build with a measurement
  behind it rather than assume.

Location is required and binds hard: probing "plumber" across Berkeley / Oakland /
Austin returned three disjoint business sets. An unpinned locale names businesses in
the wrong metro, which the W4.2 research brief calls the #1 local research error.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

import httpx

from src.config import settings

__all__ = [
    "SERPER_PLACES_URL",
    "LocalEntity",
    "LocalPackCapture",
    "SOURCE_SERPER",
    "SOURCE_NONE",
    "fetch_local_pack",
    "parse_serper_places",
]


class LocalEntity(TypedDict):
    """One business from Google's local pack.

    This is the ONLY sanctioned source of local competitor candidates. Claude does not
    reliably know the plumbers in a given city, and a fabricated rival printed in a teaser
    emailed to a real shop owner is the unrecoverable failure for this product — so local
    rivals are seeded from captured entities or not at all.

    Lived in ``ai_overviews_engine`` until 2026-07-28, when SearchApi was removed; the
    local pack is Serper's surface now, so the type belongs beside its parser.
    """

    name: str
    address: str
    # Google's own category string ("Plumber", "Barber shop") — the trade as Google
    # classifies it, which is what local queries are actually resolved against.
    category: str
    rating: float | None
    reviews: int | None
    # Google's stable business id. Serper returns it as ``cid``; SearchApi returned the
    # same value as ``ludocid``, so entities captured before the vendor change still join
    # on this field. Kept under the old name for exactly that continuity.
    ludocid: str | None
    position: int | None
    # NAP inputs: a listing whose phone or site disagrees with the client's fact sheet is
    # a Cat 6 finding. None when the vendor didn't supply them.
    phone: str | None
    website: str | None


def _coerce_float(value: Any) -> float | None:
    """Numeric or None — a vendor may send "4.7" or omit the field entirely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

class LocalPackCapture(TypedDict):
    """One query's local pack, with the vendor that produced it.

    Carries ``prompt`` alongside ``query_id`` because the report prints the question a
    customer actually asked ("best plumber in Berkeley"), not an internal id.
    """

    query_id: str
    prompt: str
    source: str
    entities: list[LocalEntity]


logger = logging.getLogger(__name__)

SERPER_PLACES_URL = "https://google.serper.dev/places"
TIMEOUT_SECONDS = 30.0

#: Which vendor produced a capture, persisted with the rows. Only one produces captures
#: today, but the column stays: rows written before 2026-07-28 carry
#: "searchapi_local_results", and a comparison across that boundary must be able to tell
#: a thin 3-business SearchApi pack from a full 10-business Serper one rather than
#: reading the difference as real churn in the client's market.
SOURCE_SERPER = "serper_places"
SOURCE_NONE = "unavailable"


def _optional_str(value: Any) -> str | None:
    """Trimmed string, or None for absent/blank — a blank phone is not a phone."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_serper_places(data: dict[str, Any]) -> list[LocalEntity]:
    """Shape a Serper ``/places`` body into typed entities. Pure, never raises.

    Field names verified against a live response, not docs (the 2026-07-27 location-format
    bug came from trusting docs and unit-testing our own wrong string):
    ``title``/``address``/``category``/``rating``/``ratingCount``/``cid``/``position``/
    ``phoneNumber``/``website``.

    Drops nameless rows. Cannot drop closed businesses —
    see the module docstring; Serper does not return that field.
    """
    entities: list[LocalEntity] = []
    for item in data.get("places", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("title") or "").strip()
        if not name:
            continue
        entities.append(
            LocalEntity(
                name=name,
                address=str(item.get("address") or "").strip(),
                category=str(item.get("category") or "").strip(),
                rating=_coerce_float(item.get("rating")),
                # Serper calls this ratingCount; SearchApi calls it reviews.
                reviews=_coerce_int(item.get("ratingCount")),
                # Serper's `cid` is the same identifier SearchApi returns as `ludocid`
                # (verified on a shared business), so it lands in the same field.
                ludocid=(str(item["cid"]) if item.get("cid") else None),
                position=_coerce_int(item.get("position")),
                phone=_optional_str(item.get("phoneNumber")),
                website=_optional_str(item.get("website")),
            )
        )
    return entities


def _fetch_serper(query: str, location: str) -> list[LocalEntity] | None:
    """One Serper ``/places`` call. ``None`` means unconfigured or the request failed;
    ``[]`` means it answered and there was no local pack. Keeping those distinct is what
    stops an outage reading as "no competitors in this market".

    Never raises, matching the engine contract this sits beside.
    """
    if not settings.SERPER_API_KEY:
        return None
    payload = {"q": query, "location": location}
    try:
        response = httpx.post(
            SERPER_PLACES_URL,
            headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Serper places request error: %s", type(exc).__name__)
        return None
    try:
        data = response.json()
    except ValueError as exc:
        logger.warning("Serper places response parse error: %s", type(exc).__name__)
        return None
    if not isinstance(data, dict):
        return None
    return parse_serper_places(data)


def fetch_local_pack(query: str, location: str) -> tuple[list[LocalEntity], str]:
    """Businesses in Google's local pack for ``query`` at ``location``.

    Returns ``(entities, source)`` — ``([], SOURCE_NONE)`` when Serper is unconfigured or
    the request fails. Never raises.

    ``location`` is required: a pack from an unpinned locale names businesses in the
    wrong metro, which is worse than no data. Blank input returns empty rather than
    quietly measuring a nationwide average.

    Note the distinction the return type preserves: ``([], SOURCE_SERPER)`` means Serper
    answered and this query genuinely has no local pack, while ``([], SOURCE_NONE)``
    means nothing was measured. Collapsing those would let an outage read as "no
    competitors in this market".
    """
    market = location.strip()
    if not market:
        logger.warning("fetch_local_pack called with no location; refusing to capture")
        return [], SOURCE_NONE
    if not query.strip():
        return [], SOURCE_NONE

    entities = _fetch_serper(query, market)
    if entities is None:  # unconfigured or the request failed — measured nothing
        return [], SOURCE_NONE
    return entities, SOURCE_SERPER


if __name__ == "__main__":
    for q in ("best plumber in Berkeley", "emergency plumber in Berkeley"):
        found, src = fetch_local_pack(q, "Berkeley,California,United States")
        print(f"\n{q!r} via {src} -> {len(found)} businesses")
        for e in found[:5]:
            print(f"  {e['position']}. {e['name']} ({e['rating']}, {e['reviews']} reviews)")
            print(f"     {e['address'] or '(no address)'} | {e['phone'] or '(no phone)'}")
