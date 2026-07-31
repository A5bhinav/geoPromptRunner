"""L0/L1 extraction: the layer that is structurally incapable of inventing a fact.

`docs/factsheet-autogen-plan.md` §3 (L0, L1) and §4. Every claim this module
emits is a value that was already present in the lead form or in bytes we
fetched, carried out with the source text stapled to it. There is no model call
here and there must never be one — L2's cited LLM extraction (F6) is a separate
module precisely so that this one can be read end to end and shown not to
generate.

The four rules that shape the code, all from §4:

* **A quote or nothing** (§4.1). A claim ships only if its ``verbatim_quote`` is
  a literal substring of the fetched text of its ``source_url``.
  :func:`verify_quotes` is that gate, and it is mechanical.
* **Blank is safe** (§4.2). Every parse below returns nothing on anything it
  does not fully understand. Coverage is not the metric: fourteen quoted lines
  beat forty with six guesses, because a wrong line does not cost us a finding,
  it costs a stranger a false accusation.
* **Disagreement is a question, not a vote** (§4.3). Two sources that differ
  produce no claim at all. A stale footer phone plus a *correct* AI answer would
  otherwise generate a flag saying the model is wrong when it is right.
* **Negatives only from closed enumerations** (§4.4). Hours are declared
  complete; a services list never is.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from selectolax.parser import HTMLParser

from src.audit.checks.schema import flatten_typed_nodes
from src.audit.crawl.models import PageRecord
from src.audit.factsheet.models import (
    BusinessKind,
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SourceKind,
    Verification,
)

__all__ = [
    "MIN_EXTRACTION_TEXT_CHARS",
    "LEAD_FORM_SOURCE_URL",
    "LOCAL_BUSINESS_TYPES",
    "ThinTextError",
    "readable_text_length",
    "assert_sufficient_text",
    "claims_from_lead_form",
    "claims_from_json_ld",
    "claims_from_html",
    "derive_negative_claims",
    "verify_quotes",
    "resolve_conflicts",
    "page_text_index",
    "build_sheet",
]

logger = logging.getLogger(__name__)


# --- C6: the thin-text refusal (§4.6) ----------------------------------------

# Mirrors MIN_PROFILE_TEXT_CHARS in teaser/src/resolver/profileExtraction.ts:48.
# Below this many readable chars across the fetched pages we refuse to extract at
# all. Cloudflare's "Just a moment…" interstitial is served at HTTP 200 and an
# unhydrated SPA shell is a <div id="root"></div>; both yield a few words of
# noise, and a sheet built from noise is a document we would send a stranger
# asserting things no page ever said. The number is deliberately the same as the
# TS floor — one threshold, two languages, so the two paths refuse the same pages.
MIN_EXTRACTION_TEXT_CHARS: int = 200


class ThinTextError(RuntimeError):
    """Raised instead of extracting from a challenge page or an empty SPA shell."""


def readable_text_length(texts: Sequence[str | None]) -> int:
    """Total readable characters across the pages handed to the extractor. Pure."""
    return sum(len((text or "").strip()) for text in texts)


def assert_sufficient_text(
    texts: Sequence[str | None],
    url: str,
    *,
    minimum: int = MIN_EXTRACTION_TEXT_CHARS,
) -> None:
    """Raise :class:`ThinTextError` unless the corpus carries enough text to extract.

    Post-fetch guard, like its TypeScript twin — it cannot tell you the domain
    failed to resolve, only that what came back is not a site. Callers pass the
    per-page extracted text they were about to mine.
    """
    chars = readable_text_length(texts)
    if chars < minimum:
        raise ThinTextError(
            f"insufficient content to extract facts for {url} ({chars} readable chars, "
            f"need {minimum}). The page is likely JS-only or bot-blocked (a challenge "
            "or SPA shell served at 200) — extracting from noise would fabricate a "
            "fact sheet."
        )


# --- shared value plumbing ---------------------------------------------------

# The lead form is not a URL, but every claim needs a source and the §4.1 gate
# needs something to look the source up by. A urn keeps it unmistakably distinct
# from a fetched page — writing the client's own website here would let a
# form-typed value masquerade as something the site said.
LEAD_FORM_SOURCE_URL: str = "urn:geo:lead-form"

_CONFIDENCE_RANK: dict[Confidence, int] = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}


def _one_line(value: Any) -> str:
    """Collapse to a single whitespace-normalized line (``FactClaim`` rejects newlines).

    ``None`` becomes the empty string, not ``"None"``. Every absent field in this
    module flows through here on its way to :func:`_claim`, so the str() of a
    missing address is one keystroke away from being a claim that says "None".
    """
    if value is None:
        return ""
    return " ".join(str(value).split())


def _claim(
    *,
    section: SheetSection,
    key: str,
    value: Any,
    quote: Any,
    source_url: str,
    source_kind: SourceKind,
    as_of: str,
    polarity: Polarity = Polarity.POSITIVE,
    confidence: Confidence = Confidence.HIGH,
) -> FactClaim | None:
    """Build one claim, or ``None`` when the source had nothing to say.

    Returning ``None`` rather than letting ``FactClaim`` raise is the §4.2 rule in
    code: a missing ``telephone`` is the normal state of most pages, not a defect
    worth aborting an extraction over. Every L0/L1 claim is
    ``PUBLIC_SOURCE_ONLY`` — one source, quoted — and nothing here may promote
    itself; cross-confirmation needs a second *independent* source, which two
    pages of one website are not (§8).
    """
    text_value, text_quote = _one_line(value), _one_line(quote)
    if not text_value or not text_quote:
        return None
    return FactClaim(
        section=section,
        key=key,
        value=text_value,
        polarity=polarity,
        verbatim_quote=text_quote,
        source_url=source_url,
        source_kind=source_kind,
        as_of=as_of,
        verification=Verification.PUBLIC_SOURCE_ONLY,
        confidence=confidence,
    )


def _oxford(items: Sequence[str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


# --- L0: the lead form (§3) --------------------------------------------------


def claims_from_lead_form(
    business: str,
    website: str,
    area: str | None,
    description: str | None,
    *,
    as_of: str,
) -> list[FactClaim]:
    """The three facts a ``/free-check`` submission actually contains.

    ``description`` is accepted and deliberately unused: §3 L0 makes it *a hint
    that tells later layers what to look for, never a fact on its own*. It is
    free text a stranger typed about themselves, so "we do emergency callouts"
    would enter the sheet as an assertion the judge then measures answers
    against, with no page behind it.

    ``area`` is kept exactly as typed rather than canonicalized to Google's
    ``City,Region,United States`` form (§3 L0). That normalization exists only in
    TypeScript (``canonicalLocation``), it belongs to the *query config* that
    SearchApi consumes, and a normalized string is no longer the verbatim thing
    the lead wrote — which is the only evidence this claim has.
    """
    _ = description  # a hint for L2/L3's aim, never a claim — see the docstring
    claims = [
        _claim(
            section=SheetSection.IDENTITY,
            key="identity_name",
            value=business,
            quote=business,
            source_url=LEAD_FORM_SOURCE_URL,
            source_kind=SourceKind.LEAD_FORM,
            as_of=as_of,
            # An unauthenticated web form is typo-prone and unattributed: we know
            # someone typed it, not that the owner did. The site overrides it on
            # agreement and blanks it on disagreement (§4.3), which is why medium
            # is the honest floor here and high is reserved for parsed markup.
            confidence=Confidence.MEDIUM,
        ),
        _claim(
            section=SheetSection.IDENTITY,
            key="identity_website",
            value=website,
            quote=website,
            source_url=LEAD_FORM_SOURCE_URL,
            source_kind=SourceKind.LEAD_FORM,
            as_of=as_of,
            confidence=Confidence.MEDIUM,
        ),
        _claim(
            section=SheetSection.SERVICE_AREA,
            key="service_area_primary",
            value=area,
            quote=area,
            source_url=LEAD_FORM_SOURCE_URL,
            source_kind=SourceKind.LEAD_FORM,
            as_of=as_of,
            confidence=Confidence.MEDIUM,
        ),
    ]
    return [c for c in claims if c is not None]


def _lead_form_text(business: str, website: str, area: str | None) -> str:
    """What the lead "said", so L0 claims face the same §4.1 gate as everything else."""
    return "\n".join(part for part in (business, website, area or "") if part)


# --- L1a: JSON-LD (§3 L1) ----------------------------------------------------

# LocalBusiness and the subtypes a trade site actually uses. Curated because the
# schema.org subtype closure is not available offline and extruct's uniform=True
# normalizes the graph without expanding types — so a `Plumber` node never
# announces that it is a LocalBusiness. Adding a type here is safe; the harvest
# below only reads properties LocalBusiness itself defines.
LOCAL_BUSINESS_TYPES: frozenset[str] = frozenset(
    {
        "LocalBusiness",
        "HomeAndConstructionBusiness",
        "Plumber",
        "Electrician",
        "HVACBusiness",
        "RoofingContractor",
        "GeneralContractor",
        "HousePainter",
        "Locksmith",
        "MovingCompany",
        "ProfessionalService",
        "EmergencyService",
        "AutomotiveBusiness",
        "AutoRepair",
        "Dentist",
        "MedicalBusiness",
        "LegalService",
        "Attorney",
        "RealEstateAgent",
        "ChildCare",
        "SelfStorage",
        "DryCleaningOrLaundry",
        "Restaurant",
        "Store",
    }
)

_DAYS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_DAY_CODES: dict[str, str] = {day[:2]: day for day in _DAYS}

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})")
_OPENING_HOURS_RE = re.compile(
    r"^(?P<days>[A-Za-z,\-]+)\s+(?P<opens>\d{1,2}:\d{2})\s*-\s*(?P<closes>\d{1,2}:\d{2})$"
)


def _types_of(node: Mapping[str, Any]) -> set[str]:
    raw = node.get("@type")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {t for t in raw if isinstance(t, str)}
    return set()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _serialize(value: Any) -> str:
    """Deterministic JSON: sorted keys, default separators, no ASCII escaping.

    Used for both sides of the §4.1 gate on schema claims, which is the only
    reason the exact settings matter — see :func:`_pair_quote`.
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _pair_quote(node: Mapping[str, Any], prop: str) -> str:
    """The ``"prop": value`` fragment a schema claim came from.

    A human checking provenance has to be able to find this in the page's
    ``<script type="application/ld+json">``, so the quote is the JSON itself
    rather than a sentence about it. Serializing the *pair* (not the whole node,
    not a bare value) is what makes it both checkable and a literal substring of
    the node as :func:`page_text_index` serializes it: identical settings at
    every nesting depth mean the fragment appears verbatim inside its parent.
    """
    return _serialize({prop: node[prop]})[1:-1].strip()


def _day_name(raw: Any) -> str | None:
    """``"https://schema.org/Monday"``, ``"Monday"``, ``"Mo"`` → ``"monday"``."""
    if not isinstance(raw, str):
        return None
    token = raw.strip().rstrip("/").rsplit("/", 1)[-1].lower()
    if token in _DAYS:
        return token
    return _DAY_CODES.get(token)


def _time_value(raw: Any) -> str | None:
    """``"08:00:00"`` → ``"08:00"``; anything unrecognized → ``None`` (blank is safe)."""
    if not isinstance(raw, str):
        return None
    match = _TIME_RE.match(raw.strip())
    if match is None:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _intervals_from_specification(specs: Sequence[Any]) -> dict[str, list[tuple[str, str]]]:
    """Day → sorted open intervals, from ``openingHoursSpecification`` entries."""
    by_day: dict[str, set[tuple[str, str]]] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        opens, closes = _time_value(spec.get("opens")), _time_value(spec.get("closes"))
        # An interval that opens and closes at the same instant is how several
        # CMS plugins spell "closed". Recording no hours for that day is right
        # either way: it stays out of the positives, and the §4.4 derivation
        # below then reports it closed if the rest of the week is a full week.
        if opens is None or closes is None or opens == closes:
            continue
        for raw_day in _as_list(spec.get("dayOfWeek")):
            day = _day_name(raw_day)
            if day is not None:
                by_day.setdefault(day, set()).add((opens, closes))
    return {day: sorted(intervals) for day, intervals in by_day.items()}


def _intervals_from_opening_hours(values: Sequence[Any]) -> dict[str, list[tuple[str, str]]]:
    """Day → intervals, from the legacy ``openingHours`` microformat ("Mo-Sa 08:00-17:00").

    Strict on purpose. The format has no specification worth the name and sites
    write things like ``"Mo-Fr 08:00-12:00,13:00-17:00"`` or ``"By appointment"``;
    anything the regex does not fully match yields nothing rather than a guess,
    and a partially-parsed week would then feed a wrong "Closed Sunday".
    """
    by_day: dict[str, set[tuple[str, str]]] = {}
    for value in values:
        if not isinstance(value, str):
            continue
        match = _OPENING_HOURS_RE.match(value.strip())
        if match is None:
            continue
        opens, closes = _time_value(match.group("opens")), _time_value(match.group("closes"))
        if opens is None or closes is None or opens == closes:
            continue
        days = _days_from_codes(match.group("days"))
        if days is None:
            continue
        for day in days:
            by_day.setdefault(day, set()).add((opens, closes))
    return {day: sorted(intervals) for day, intervals in by_day.items()}


def _days_from_codes(spec: str) -> list[str] | None:
    """``"Mo-Sa"`` / ``"Mo,We,Fr"`` → day names; ``None`` if any token is unknown."""
    days: list[str] = []
    for token in spec.split(","):
        bounds = token.strip().lower().split("-")
        if len(bounds) == 1:
            day = _DAY_CODES.get(bounds[0])
            if day is None:
                return None
            days.append(day)
        elif len(bounds) == 2:
            start, end = _DAY_CODES.get(bounds[0]), _DAY_CODES.get(bounds[1])
            if start is None or end is None:
                return None
            first, last = _DAYS.index(start), _DAYS.index(end)
            if first > last:  # a wrapping range ("Sa-Mo") is ambiguous — refuse it
                return None
            days.extend(_DAYS[first : last + 1])
        else:
            return None
    return days


def _address_line(raw: Any) -> str | None:
    """A ``PostalAddress`` (or a plain string) as one readable line."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        raw = next((item for item in raw if isinstance(item, str | dict)), None)
    if not isinstance(raw, dict):
        return None
    # "CA 94702", not "CA, 94702" — the region and the ZIP are one field to every
    # reader, and the judge compares this against how an answer says an address.
    region = " ".join(_one_line(raw[k]) for k in ("addressRegion", "postalCode") if raw.get(k))
    parts = [_one_line(raw[k]) if raw.get(k) else "" for k in ("streetAddress", "addressLocality")]
    return ", ".join(part for part in (*parts, region) if part) or None


def _area_names(raw: Any) -> list[str]:
    """``areaServed`` entries that name a place. A ``GeoCircle`` names none — skip it."""
    names: list[str] = []
    for item in _as_list(raw):
        if isinstance(item, str):
            name = _one_line(item)
        elif isinstance(item, dict):
            name = _one_line(item.get("name") or "")
        else:
            continue
        if name and name not in names:
            names.append(name)
    return names


def claims_from_json_ld(
    blocks: Sequence[Mapping[str, Any]],
    source_url: str,
    as_of: str,
) -> list[FactClaim]:
    """Harvest ``LocalBusiness`` markup from one page's ``PageRecord.json_ld``.

    ``blocks`` is exactly what ``fetcher._extract_json_ld`` stores: extruct's
    ``uniform=True`` output, so ``@graph`` nesting is normal and the real node is
    routinely three levels down — :func:`flatten_typed_nodes` is what finds it.

    Two nodes describing two branches produce two sets of claims, which collide
    in :func:`resolve_conflicts` and become a question rather than a coin flip.
    """
    claims: list[FactClaim] = []
    for node in flatten_typed_nodes([dict(block) for block in blocks]):
        if not (_types_of(node) & LOCAL_BUSINESS_TYPES):
            continue
        claims.extend(_claims_from_business_node(node, source_url, as_of))
    return claims


def _claims_from_business_node(
    node: Mapping[str, Any],
    source_url: str,
    as_of: str,
) -> list[FactClaim]:
    def build(section: SheetSection, key: str, value: Any, prop: str) -> FactClaim | None:
        return _claim(
            section=section,
            key=key,
            value=value,
            quote=_pair_quote(node, prop),
            source_url=source_url,
            source_kind=SourceKind.SITE_JSONLD,
            as_of=as_of,
        )

    claims: list[FactClaim | None] = []
    if node.get("name"):
        claims.append(build(SheetSection.IDENTITY, "identity_name", node["name"], "name"))
    if node.get("telephone"):
        claims.append(build(SheetSection.CONTACT, "contact_phone", node["telephone"], "telephone"))
    if node.get("address"):
        address = _address_line(node["address"])
        claims.append(build(SheetSection.CONTACT, "contact_address", address, "address"))
    if node.get("priceRange"):
        claims.append(
            build(SheetSection.SERVICES_PRICING, "pricing_range", node["priceRange"], "priceRange")
        )

    areas = _area_names(node.get("areaServed"))
    if areas:
        # "Serves X" rather than the bare list: the judge measures answers about
        # where the business WORKS, and a bare town list reads equally as where
        # it is located — a distinction `wrong_service_area` turns on.
        claims.append(
            build(
                SheetSection.SERVICE_AREA,
                "service_area_towns",
                f"Serves {_oxford(areas)}.",
                "areaServed",
            )
        )

    same_as = [_one_line(u) for u in _as_list(node.get("sameAs")) if isinstance(u, str)]
    if same_as:
        claims.append(
            build(
                SheetSection.PRESENCE,
                "presence_profiles",
                f"Official profiles: {', '.join(same_as)}.",
                "sameAs",
            )
        )

    claims.extend(_hours_claims(node, source_url, as_of))
    return [c for c in claims if c is not None]


def _hours_claims(node: Mapping[str, Any], source_url: str, as_of: str) -> list[FactClaim]:
    """One positive claim per day the markup declares open.

    The quote is the whole ``openingHoursSpecification`` (or ``openingHours``)
    property, not the single day's entry, for two reasons: it is the closed
    enumeration :func:`derive_negative_claims` reasons over, so every day claim
    from one node carries identical evidence and groups cleanly; and a reader
    checking "Closed Sunday" needs to see the *whole* week to check it.
    """
    if node.get("openingHoursSpecification"):
        prop = "openingHoursSpecification"
        by_day = _intervals_from_specification(_as_list(node[prop]))
    elif node.get("openingHours"):
        prop = "openingHours"
        by_day = _intervals_from_opening_hours(_as_list(node[prop]))
    else:
        return []

    quote = _pair_quote(node, prop)
    claims: list[FactClaim] = []
    for day in _DAYS:
        intervals = by_day.get(day)
        if not intervals:
            continue
        spans = ", ".join(f"{opens}-{closes}" for opens, closes in intervals)
        claim = _claim(
            section=SheetSection.HOURS,
            key=f"hours_{day}",
            value=f"Open {spans}.",
            quote=quote,
            source_url=source_url,
            source_kind=SourceKind.SITE_JSONLD,
            as_of=as_of,
        )
        if claim is not None:
            claims.append(claim)
    return claims


# --- L1b: the HTML fallback (§3 L1) ------------------------------------------

# A US phone as a page displays it, with digit boundaries so a 16-digit order
# number cannot contribute its middle ten.
_PHONE_DISPLAY_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-]*)?\(?\d{3}\)?[\s.\-]*\d{3}[\s.\-]*\d{4}(?!\d)"
)
# "…, CA 94702" — the tail that makes a line an address rather than prose. An
# uppercase state code is required: "Berkeley, Ca 94702" yields nothing, which is
# the right trade when the alternative is matching "Notice, We 12345".
_CITY_STATE_ZIP_RE = re.compile(r",\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")
_STREET_RE = re.compile(r"\b\d{1,6}\s+\S")
_FOOTER_SELECTOR = "footer, .footer, #footer"


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _visible_lines(html: str) -> list[str]:
    """The page's visible text, one line per text node, whitespace collapsed.

    Deliberately not ``PageRecord.extracted_text``: trafilatura extracts *main
    content*, and the footer is exactly what it discards — which is where a
    local business puts its NAP block. Both this extractor and
    :func:`page_text_index` read through here so the §4.1 gate is checking the
    same corpus the claims came out of.
    """
    try:
        tree = HTMLParser(html)
    except Exception as exc:  # malformed markup — extract nothing, never raise
        logger.warning("selectolax parse failed during fact extraction: %s", exc)
        return []
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    root = tree.body or tree.root
    if root is None:
        return []
    raw = root.text(deep=True, separator="\n") or ""
    return [line for line in (_one_line(part) for part in raw.split("\n")) if line]


def _hrefs(tree: HTMLParser, scheme: str) -> list[str]:
    found: list[str] = []
    for node in tree.css("a"):
        href = (node.attributes.get("href") or "").strip()
        if href.lower().startswith(scheme) and href not in found:
            found.append(href)
    return found


def claims_from_html(html: str, source_url: str, as_of: str) -> list[FactClaim]:
    """The fallback for a page with no ``LocalBusiness`` markup: ``tel:``/``mailto:`` + NAP.

    Every claim quotes the literal visible line the value appears on. A ``tel:``
    href whose number appears nowhere a visitor can read produces **nothing** —
    an attribute is not something a human can check on the page, and the number
    a site links is routinely a call-tracking number it never displays.

    Two ``tel:`` links with different numbers (a main line and a 24/7 emergency
    line) are a genuine ambiguity, not a bug: they collide in
    :func:`resolve_conflicts` and become a question.
    """
    try:
        tree = HTMLParser(html)
    except Exception as exc:
        logger.warning("selectolax parse failed during fact extraction: %s", exc)
        return []
    lines = _visible_lines(html)
    return [
        *_phone_claims(tree, lines, source_url, as_of),
        *_email_claims(tree, lines, source_url, as_of),
        *_nap_claims(tree, source_url, as_of),
    ]


def _phone_claims(
    tree: HTMLParser, lines: Sequence[str], source_url: str, as_of: str
) -> list[FactClaim]:
    claims: list[FactClaim] = []
    seen: set[str] = set()
    for href in _hrefs(tree, "tel:"):
        national = _digits(href)[-10:]
        if len(national) < 10 or national in seen:
            continue
        seen.add(national)
        for line in lines:
            match = next(
                (
                    m
                    for m in _PHONE_DISPLAY_RE.finditer(line)
                    if _digits(m.group())[-10:] == national
                ),
                None,
            )
            if match is None:
                continue
            claim = _claim(
                section=SheetSection.CONTACT,
                key="contact_phone",
                value=match.group(),
                quote=line,
                source_url=source_url,
                source_kind=SourceKind.SITE_TEXT,
                as_of=as_of,
            )
            if claim is not None:
                claims.append(claim)
            break
    return claims


def _email_claims(
    tree: HTMLParser, lines: Sequence[str], source_url: str, as_of: str
) -> list[FactClaim]:
    claims: list[FactClaim] = []
    seen: set[str] = set()
    for href in _hrefs(tree, "mailto:"):
        address = href.split(":", 1)[1].split("?")[0].strip()
        if "@" not in address or address.lower() in seen:
            continue
        seen.add(address.lower())
        line = next((ln for ln in lines if address.lower() in ln.lower()), None)
        if line is None:
            continue
        claim = _claim(
            section=SheetSection.CONTACT,
            key="contact_email",
            value=address,
            quote=line,
            source_url=source_url,
            source_kind=SourceKind.SITE_TEXT,
            as_of=as_of,
        )
        if claim is not None:
            claims.append(claim)
    return claims


def _nap_claims(tree: HTMLParser, source_url: str, as_of: str) -> list[FactClaim]:
    """The footer NAP address, when a continuous run of the page's text carries it.

    The claim is the span from the street number to the ZIP, so the value is a
    literal substring of what the footer says — which is also what lets it pass
    §4.1 unchanged. A street on its own line above the city line is joined with a
    single space for the same reason: collapsing whitespace is precisely what the
    gate does, so the joined string really is what the page reads.

    A street split across three ``<span>``s with the city in a fourth is left to
    L2. Joining non-adjacent lines would assert an address no continuous run of
    the page contains, and the quote could then never be checked.
    """
    footer = tree.css_first(_FOOTER_SELECTOR)
    if footer is None:
        return []
    lines = _visible_lines(footer.html or "")
    for index, line in enumerate(lines):
        zip_match = _CITY_STATE_ZIP_RE.search(line)
        if zip_match is None:
            continue
        street = _STREET_RE.search(line[: zip_match.start()])
        if street is not None:
            span = line[street.start() : zip_match.end()]
            value, quote = span, span
        elif index and (previous := _STREET_RE.search(lines[index - 1])):
            head = lines[index - 1][previous.start() :]
            tail = line[: zip_match.end()]
            value, quote = f"{head}, {tail}", f"{head} {tail}"
        else:
            continue
        claim = _claim(
            section=SheetSection.CONTACT,
            key="contact_address",
            value=value,
            quote=quote,
            source_url=source_url,
            source_kind=SourceKind.SITE_TEXT,
            as_of=as_of,
        )
        return [claim] if claim is not None else []
    return []


# --- §4.4: negatives, only from closed enumerations --------------------------

_HOURS_KEY_RE = re.compile(rf"^hours_({'|'.join(_DAYS)})$")

# Below this many declared days we do not treat an hours block as a statement
# about the whole week. A site that marks up only Monday has lazy markup, not a
# six-day closure — and "Closed Tuesday" on a business open Tuesday is the exact
# false accusation this plan exists to prevent.
_MIN_DAYS_FOR_CLOSED_WEEK: int = 5


def derive_negative_claims(claims: Sequence[FactClaim]) -> list[FactClaim]:
    """Derive "Closed Sunday." and nothing else (§4.4).

    Hours are the only enumeration a site publishes as *complete*: an
    ``openingHoursSpecification`` listing Mon–Sat says the week is Mon–Sat.
    A services list, an ``areaServed`` list and a price list are all open —
    absence there means "not mentioned", so no negative is ever derived from
    them, no matter how tempting "does not offer emergency service" is as a
    finding.

    Each negative reuses the evidence of the enumeration it came from, so it
    passes the same §4.1 gate as the positives and a reader can check the whole
    week in one quote. Claims are grouped by (source_url, quote): that pair *is*
    one enumeration, so two conflicting hours blocks stay separate and collide
    later as a question instead of averaging into a wrong week.
    """
    groups: dict[tuple[str, str], list[FactClaim]] = {}
    for claim in claims:
        if (
            claim.section is SheetSection.HOURS
            and claim.polarity is Polarity.POSITIVE
            and _HOURS_KEY_RE.match(claim.key)
        ):
            groups.setdefault((claim.source_url, claim.verbatim_quote), []).append(claim)

    derived: list[FactClaim] = []
    for (source_url, quote), members in groups.items():
        covered = {claim.key.removeprefix("hours_") for claim in members}
        if not _MIN_DAYS_FOR_CLOSED_WEEK <= len(covered) < len(_DAYS):
            continue
        witness = members[0]
        confidence = min((c.confidence for c in members), key=lambda c: _CONFIDENCE_RANK[c])
        for day in _DAYS:
            if day in covered:
                continue
            # Not `claim`: that name is bound to a FactClaim by the loop above,
            # and `_claim` returns FactClaim | None.
            negative = _claim(
                section=SheetSection.HOURS,
                key=f"hours_{day}",
                # A complete assertion, because the judge has to be able to quote
                # a line the answer contradicts (§4.4). "hours_sunday: no" is not
                # something an answer can contradict in words.
                value=f"Closed {day.capitalize()}.",
                quote=quote,
                source_url=source_url,
                source_kind=witness.source_kind,
                as_of=witness.as_of,
                polarity=Polarity.NEGATIVE,
                confidence=confidence,
            )
            if negative is not None:
                derived.append(negative)
    return derived


# --- §4.1: the verbatim-quote gate -------------------------------------------


def _match_key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _url_key(url: str) -> str:
    return url.strip().rstrip("/").casefold()


def page_text_index(pages: Sequence[PageRecord]) -> dict[str, str]:
    """``source_url`` → everything the page said, as the §4.1 gate must see it.

    Three layers, because the extractors read three: trafilatura's main text, the
    *visible* text including the footer trafilatura drops, and each JSON-LD node
    serialized the way :func:`_pair_quote` serializes its fragments. Leaving any
    of them out would make the gate drop true claims — a gate that fails closed
    on real facts gets weakened by the next person, which is how gates die.
    """
    index: dict[str, str] = {}
    for page in pages:
        html = _effective_html(page)
        parts = [page.extracted_text or ""]
        if html:
            parts.extend(_visible_lines(html))
        parts.extend(
            _serialize(node) for node in flatten_typed_nodes([dict(b) for b in page.json_ld])
        )
        index[page.url] = "\n".join(part for part in parts if part)
    return index


def verify_quotes(
    claims: Sequence[FactClaim],
    page_texts: Mapping[str, str],
) -> tuple[list[FactClaim], list[FactClaim]]:
    """Split claims into (kept, dropped) on the §4.1 substring test.

    Whitespace-normalized and case-insensitive, per §4.1 — HTML wraps lines
    wherever it likes and a heading may be upper-cased by CSS. A claim whose
    ``source_url`` is not in ``page_texts`` is dropped too: unverifiable and
    verified are not the same state, and only one of them may ship.

    Both halves are returned so the caller can log the drops. Dropping silently
    is correct — a source that did not say it is not an error condition. Passing
    silently is not: this is the only mechanical check standing between "the
    model said so" and "the page says so", and it must stay the narrowest,
    dumbest function in the module.
    """
    index = {_url_key(url): _match_key(text) for url, text in page_texts.items()}
    kept: list[FactClaim] = []
    dropped: list[FactClaim] = []
    for claim in claims:
        haystack = index.get(_url_key(claim.source_url))
        if haystack is not None and _match_key(claim.verbatim_quote) in haystack:
            kept.append(claim)
        else:
            dropped.append(claim)
            logger.info(
                "fact-sheet claim dropped by the quote gate: key=%s source=%s quote=%r",
                claim.key,
                claim.source_url,
                claim.verbatim_quote[:120],
            )
    return kept, dropped


# --- §4.3: disagreement becomes a question -----------------------------------

_PHONE_KEYS: frozenset[str] = frozenset({"contact_phone"})


def _conflict_value(key: str, value: str) -> str:
    """The comparable form of a value, so formatting alone is never a conflict.

    "(510) 555-0100" and "510-555-0100" are one phone number. Treating them as
    two would raise a question about a fact both sources agree on, and questions
    are the scarce resource — every one of them costs the owner attention we
    would rather spend on the eight things the models actually get wrong (§7).
    """
    if key in _PHONE_KEYS:
        digits = _digits(value)
        return digits[-10:] if len(digits) >= 10 else digits
    return " ".join(value.split()).casefold().rstrip(".")


def resolve_conflicts(claims: Sequence[FactClaim]) -> tuple[list[FactClaim], list[str]]:
    """Collapse agreeing claims, and turn every disagreement into a question (§4.3).

    Agreement keeps the first claim and its evidence, and does **not** upgrade
    verification: two pages of one website are one source, so cross-confirmation
    has to wait for an off-site source (F7, §8).

    Disagreement emits no claim for that key at all. The alternative — picking
    the "better" source — is what produces a flag telling a client their AI
    listing is wrong about a phone number that changed last month, and being
    wrong in that direction costs more than a blank line.
    """
    order: list[str] = []
    by_key: dict[str, dict[str, list[FactClaim]]] = {}
    for claim in claims:
        if claim.key not in by_key:
            by_key[claim.key] = {}
            order.append(claim.key)
        by_key[claim.key].setdefault(_conflict_value(claim.key, claim.value), []).append(claim)

    kept: list[FactClaim] = []
    questions: list[str] = []
    for key in order:
        variants = by_key[key]
        if len(variants) == 1:
            kept.append(next(iter(variants.values()))[0])
            continue
        witnesses = sorted(
            (group[0] for group in variants.values()),
            key=lambda c: (c.value, c.source_url),
        )
        cited = "; ".join(f'{c.source_url} says "{c.value}"' for c in witnesses)
        questions.append(
            f"{key}: sources disagree — {cited}. Which is current? "
            "(no claim emitted, plan §4.3)"
        )
    return kept, questions


# --- putting it together -----------------------------------------------------


def _effective_html(page: PageRecord) -> str | None:
    """The DOM the audit believes: the render when we escalated, else the raw bytes."""
    return page.rendered_html or page.raw_html


def _as_of(page: PageRecord) -> str:
    """The fetch date, per §4.5 — claims decay, so every one carries when it was true."""
    return page.fetch_meta.fetched_at[:10]


def _domain_of(website: str) -> str:
    host = urlsplit(website if "//" in website else f"https://{website}").hostname or website
    return host.removeprefix("www.")


def build_sheet(
    *,
    business: str,
    website: str,
    pages: Sequence[PageRecord],
    generated_at: str,
    area: str | None = None,
    description: str | None = None,
    business_kind: BusinessKind = BusinessKind.LOCAL_SERVICE,
    lead_ref: str | None = None,
) -> FactSheet:
    """L0 + L1 end to end: a lead and a crawl in, a draft :class:`FactSheet` out.

    No model is called and none may be added: F1's acceptance is a sheet produced
    with zero LLM calls where every line traces to JSON-LD or a ``tel:``/NAP
    block (plan §10).

    The order is load-bearing. Blocked pages are excluded *before* the thin-text
    refusal, so a crawl that returned nothing but challenge pages raises rather
    than yielding a sheet from interstitial boilerplate. JSON-LD wins per page
    and the HTML fallback runs only where the page had no ``LocalBusiness``
    markup (§3 L1), so a site with schema never has its own footer argued with.
    Negatives are derived before the gate, so they face it too.
    """
    usable = [page for page in pages if not page.fetch_meta.blocked]
    assert_sufficient_text([page.extracted_text for page in usable], website)

    claims = claims_from_lead_form(business, website, area, description, as_of=generated_at[:10])
    for page in usable:
        from_schema = claims_from_json_ld(page.json_ld, page.url, _as_of(page))
        if from_schema:
            claims.extend(from_schema)
            continue
        html = _effective_html(page)
        if html:
            claims.extend(claims_from_html(html, page.url, _as_of(page)))
    claims.extend(derive_negative_claims(claims))

    texts = page_text_index(usable)
    texts[LEAD_FORM_SOURCE_URL] = _lead_form_text(business, website, area)
    kept, dropped = verify_quotes(claims, texts)
    if dropped:
        logger.info(
            "fact sheet for %s: %d claim(s) dropped by the quote gate", website, len(dropped)
        )

    resolved, questions = resolve_conflicts(kept)
    sheet = FactSheet(
        domain=_domain_of(website),
        business_name=_one_line(business) or _domain_of(website),
        business_kind=business_kind,
        claims=resolved,
        questions=questions,
        generated_at=generated_at,
        lead_ref=lead_ref,
    )
    sheet.assign_claim_ids()
    return sheet
