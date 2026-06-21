"""Cat 5 — Structured data / Schema checker (deterministic, impl guide §3.1).

Three deterministic checks over a page's parsed JSON-LD (already extracted with
extruct during the crawl, on the rendered HTML when escalated):

1. **Present & valid** — flatten the ``@graph`` / nested entities, then validate
   each typed node's required / one-of / recommended properties against a
   *curated, versioned* requirements dict. There is no machine-readable source of
   Google's required properties (schema.org marks nothing required; Google's
   per-feature rules live only in human docs), so we maintain the dict in-house
   and skip pySHACL (required-field presence is a one-line set check).
2. **Types implemented** — enumerate the ``@type``s present (so the report can
   diff them against a should-have set; Organization is a near-universal B2C gap).
3. **Schema matches visible content** — catch fabricated ratings / price drift by
   requiring rating values and prices to actually appear in the page's *main
   text* (not the raw HTML, else a value matches itself inside the ``<script>``),
   with fuzzy matching for text fields.

Operates on a crawled :class:`PageRecord` (its ``json_ld`` and ``extracted_text``).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from rapidfuzz import fuzz

from src.audit.crawl.models import PageRecord

__all__ = [
    "SchemaClass",
    "TypeFinding",
    "ContentMismatch",
    "SchemaResult",
    "check_schema",
    "flatten_typed_nodes",
    "GOOGLE_REQUIREMENTS",
    "SCHEMA_REQUIREMENTS_VERSION",
]

logger = logging.getLogger(__name__)

# Bump when GOOGLE_REQUIREMENTS changes — verdicts are only comparable within a
# version (mirrors the rubric/judge versioning discipline).
SCHEMA_REQUIREMENTS_VERSION = "2026-06-google-v1"

# Fuzzy match floor for text fields (token-set ratio); ratings/prices use exact
# numeric matching instead.
_TEXT_MATCH_THRESHOLD = 88

# Curated Google rich-result requirements. `required`: must all be present;
# `one_of`: at least one prop from each group must be present; `recommended`:
# surfaced as improvements, never a failure. Keep ~15-20 high-value types.
GOOGLE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "Organization": {"required": {"name"}, "recommended": {"url", "logo", "sameAs", "description"}},
    "LocalBusiness": {
        "required": {"name", "address"},
        "recommended": {"telephone", "openingHours", "geo", "priceRange", "image"},
    },
    "Product": {
        "required": {"name"},
        "one_of": [{"offers", "review", "aggregateRating"}],
        "recommended": {
            "image",
            "brand",
            "description",
            "sku",
            "gtin",
            "aggregateRating",
            "offers",
        },
    },
    "Offer": {
        "required": {"price", "priceCurrency"},
        "recommended": {"availability", "url", "priceValidUntil"},
    },
    "AggregateRating": {
        "required": {"ratingValue"},
        "one_of": [{"reviewCount", "ratingCount"}],
        "recommended": {"bestRating"},
    },
    "Review": {
        "required": {"reviewRating", "author"},
        "recommended": {"datePublished", "reviewBody"},
    },
    "Article": {
        "required": {"headline"},
        "recommended": {"image", "datePublished", "dateModified", "author"},
    },
    "NewsArticle": {
        "required": {"headline"},
        "recommended": {"image", "datePublished", "dateModified", "author"},
    },
    "BlogPosting": {
        "required": {"headline"},
        "recommended": {"image", "datePublished", "dateModified", "author"},
    },
    "FAQPage": {"required": {"mainEntity"}},
    "QAPage": {"required": {"mainEntity"}},
    "HowTo": {
        "required": {"name", "step"},
        "recommended": {"image", "totalTime", "supply", "tool"},
    },
    "BreadcrumbList": {"required": {"itemListElement"}},
    "WebSite": {"required": {"name", "url"}, "recommended": {"potentialAction"}},
    "SoftwareApplication": {
        "required": {"name"},
        "one_of": [{"offers", "aggregateRating", "review"}],
        "recommended": {"applicationCategory", "operatingSystem", "aggregateRating", "offers"},
    },
    "MobileApplication": {
        "required": {"name"},
        "one_of": [{"offers", "aggregateRating", "review"}],
        "recommended": {"applicationCategory", "operatingSystem", "aggregateRating", "offers"},
    },
    "VideoObject": {
        "required": {"name", "thumbnailUrl", "uploadDate"},
        "recommended": {"description", "duration", "contentUrl"},
    },
    "Event": {
        "required": {"name", "startDate", "location"},
        "recommended": {"endDate", "offers", "performer"},
    },
    "Recipe": {
        "required": {"name", "image"},
        "recommended": {"recipeIngredient", "recipeInstructions", "aggregateRating", "author"},
    },
    "Person": {"required": {"name"}, "recommended": {"url", "sameAs", "jobTitle", "image"}},
}


class SchemaClass(StrEnum):
    PASS = "pass"  # schema present, required props satisfied, no content mismatch
    PARTIAL = "partial"  # present but incomplete, or a content mismatch
    FAIL = "fail"  # no structured data at all
    UNGRADEABLE = "ungradeable"  # page was blocked, so absence isn't meaningful


@dataclass
class TypeFinding:
    type_name: str
    present: list[str]
    missing_required: list[str]
    missing_one_of: list[list[str]]
    missing_recommended: list[str]

    @property
    def satisfied(self) -> bool:
        return not self.missing_required and not self.missing_one_of


@dataclass
class ContentMismatch:
    type_name: str
    field_name: str
    schema_value: str
    note: str


@dataclass
class SchemaResult:
    classification: SchemaClass
    types_found: list[str]
    findings: list[TypeFinding]
    mismatches: list[ContentMismatch]
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


# --- graph flattening --------------------------------------------------------


def _types_of(node: dict[str, Any]) -> set[str]:
    """Coerce a node's ``@type`` to a set (it can be a string or a list)."""
    raw = node.get("@type")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {t for t in raw if isinstance(t, str)}
    return set()


def flatten_typed_nodes(json_ld: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Yield every typed node in the JSON-LD, recursing into ``@graph``/nested values.

    One malformed block never sinks the page — each top-level block is walked in
    its own try/except.
    """
    nodes: list[dict[str, Any]] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            if "@type" in obj:
                nodes.append(obj)
            for value in obj.values():
                _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for block in json_ld:
        try:
            _walk(block)
        except Exception as exc:  # defensive — keep parsing the rest
            logger.warning("JSON-LD block walk failed: %s", exc)
    return nodes


def _present_props(node: dict[str, Any]) -> set[str]:
    """Schema property keys whose value is non-empty (ignores ``@type``/``@id``)."""
    return {
        key
        for key, value in node.items()
        if not key.startswith("@") and value not in (None, "", [], {})
    }


def _validate_node(node: dict[str, Any], type_name: str) -> TypeFinding:
    reqs = GOOGLE_REQUIREMENTS[type_name]
    present = _present_props(node)
    required: set[str] = reqs.get("required", set())
    recommended: set[str] = reqs.get("recommended", set())
    one_of: list[set[str]] = reqs.get("one_of", [])
    missing_one_of = [sorted(group) for group in one_of if not (group & present)]
    return TypeFinding(
        type_name=type_name,
        present=sorted(present),
        missing_required=sorted(required - present),
        missing_one_of=missing_one_of,
        missing_recommended=sorted(recommended - present),
    )


# --- schema-vs-visible-content ----------------------------------------------


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().lower()


_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers_in(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for token in _NUMBER_RE.findall(text):
        try:
            found.add(Decimal(token.replace(",", ".")))
        except InvalidOperation:
            continue
    return found


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _number_matches(value: Any, visible_numbers: set[Decimal]) -> bool:
    target = _to_decimal(value)
    return target is not None and target in visible_numbers


def _text_matches(value: Any, visible_norm: str) -> bool:
    norm = _normalize(str(value))
    if not norm:
        return True  # nothing to verify
    if norm in visible_norm:
        return True
    return fuzz.token_set_ratio(norm, visible_norm) >= _TEXT_MATCH_THRESHOLD


def _check_content(nodes: list[dict[str, Any]], visible_text: str) -> list[ContentMismatch]:
    """Flag schema values that don't appear in the page's visible main text."""
    mismatches: list[ContentMismatch] = []
    visible_norm = _normalize(visible_text)
    visible_numbers = _numbers_in(visible_text)
    for node in nodes:
        types = _types_of(node)
        if "AggregateRating" in types and node.get("ratingValue") is not None:
            value = node["ratingValue"]
            if not _number_matches(value, visible_numbers):
                mismatches.append(
                    ContentMismatch(
                        "AggregateRating",
                        "ratingValue",
                        str(value),
                        "rating value not found in visible text — possible fabricated rating",
                    )
                )
        if "Offer" in types and node.get("price") is not None:
            value = node["price"]
            if not _number_matches(value, visible_numbers):
                mismatches.append(
                    ContentMismatch(
                        "Offer",
                        "price",
                        str(value),
                        "price not found in visible text — possible price drift",
                    )
                )
        if types & {"Product", "Organization"} and node.get("name"):
            if not _text_matches(node["name"], visible_norm):
                mismatches.append(
                    ContentMismatch(
                        next(iter(types & {"Product", "Organization"})),
                        "name",
                        str(node["name"]),
                        "schema name not found in visible text",
                    )
                )
    return mismatches


# --- features → expected types, and sameAs (Comments 11 / 13) ----------------

# Types a page of each category ought to expose, so a missing one is a real gap.
_CATEGORY_EXPECTED: dict[str, set[str]] = {
    "homepage": {"Organization"},
    "pricing": {"Product", "Offer"},
    "product": {"Product"},
    "comparison": {"Product"},
    "blog": {"Article"},
}
_ARTICLE_FAMILY = {"Article", "NewsArticle", "BlogPosting"}
_ENTITY_TYPES = {"Organization", "Person", "Brand", "LocalBusiness"}
_IDENTITY_PLATFORMS = (
    "twitter.com",
    "x.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "github.com",
    "wikipedia.org",
    "wikidata.org",
    "crunchbase.com",
)


def _should_have_types(page: PageRecord, types_found: set[str]) -> list[str]:
    """Infer the rich-result types this page ought to expose, minus what's present."""
    expected = set(_CATEGORY_EXPECTED.get(page.category.value, set()))
    url = page.url.lower()
    text = (page.extracted_text or "").lower()
    if "/faq" in url or "frequently asked question" in text:
        expected.add("FAQPage")
    if any(seg in url for seg in ("/about", "/team", "/leadership", "/founder")):
        expected.add("Person")
    # Any Article-family type satisfies the blog "Article" expectation.
    if "Article" in expected and (types_found & _ARTICLE_FAMILY):
        expected.discard("Article")
    return sorted(t for t in expected if t not in types_found)


def _sameas_analysis(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract entity ``sameAs`` links and classify them by identity platform.

    Resolution to the live profile belongs to the offsite layer (network); here we
    surface what's declared and which known platforms it points at, so a missing or
    implausible identity-link set is visible.
    """
    urls: list[str] = []
    for node in nodes:
        if _types_of(node) & _ENTITY_TYPES:
            same_as = node.get("sameAs")
            if isinstance(same_as, str):
                urls.append(same_as)
            elif isinstance(same_as, list):
                urls.extend(u for u in same_as if isinstance(u, str))
    platforms = sorted({p for url in urls for p in _IDENTITY_PLATFORMS if p in url.lower()})
    return {"count": len(urls), "platforms": platforms, "urls": urls[:10]}


# --- top-level check ---------------------------------------------------------


def check_schema(page: PageRecord) -> SchemaResult:
    """Validate a crawled page's structured data (Cat 5)."""
    nodes = flatten_typed_nodes(page.json_ld)
    types_found = sorted({t for node in nodes for t in _types_of(node)})
    expected_missing = _should_have_types(page, set(types_found))
    same_as = _sameas_analysis(nodes)

    if not nodes:
        if page.fetch_meta.blocked:
            return SchemaResult(
                SchemaClass.UNGRADEABLE,
                [],
                [],
                [],
                "page blocked — schema absence not meaningful",
                _evidence([], [], expected_missing, same_as),
            )
        return SchemaResult(
            SchemaClass.FAIL,
            [],
            [],
            [],
            "no JSON-LD structured data found",
            _evidence([], [], expected_missing, same_as),
        )

    findings = [
        _validate_node(node, type_name)
        for node in nodes
        for type_name in (_types_of(node) & GOOGLE_REQUIREMENTS.keys())
    ]
    mismatches = _check_content(nodes, page.extracted_text or "")

    incomplete = [f for f in findings if not f.satisfied]
    evidence = _evidence(types_found, findings, expected_missing, same_as)

    if mismatches:
        return SchemaResult(
            SchemaClass.PARTIAL,
            types_found,
            findings,
            mismatches,
            f"schema present but {len(mismatches)} value(s) not found in visible content",
            evidence,
        )
    if incomplete:
        names = ", ".join(sorted({f.type_name for f in incomplete}))
        return SchemaResult(
            SchemaClass.PARTIAL,
            types_found,
            findings,
            mismatches,
            f"schema present but missing required props on: {names}",
            evidence,
        )
    if expected_missing:
        return SchemaResult(
            SchemaClass.PARTIAL,
            types_found,
            findings,
            mismatches,
            f"valid schema, but this page should also expose: {', '.join(expected_missing)}",
            evidence,
        )
    return SchemaResult(
        SchemaClass.PASS,
        types_found,
        findings,
        mismatches,
        f"valid structured data: {', '.join(types_found)}",
        evidence,
    )


def _evidence(
    types_found: list[str],
    findings: list[TypeFinding],
    expected_missing: list[str],
    same_as: dict[str, Any],
) -> dict[str, Any]:
    return {
        "requirements_version": SCHEMA_REQUIREMENTS_VERSION,
        "types_found": types_found,
        "recommended_gaps": sorted({prop for f in findings for prop in f.missing_recommended}),
        "organization_present": "Organization" in types_found,
        "missing_expected_types": expected_missing,
        "same_as": same_as,
    }
