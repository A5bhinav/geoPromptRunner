"""Cat 3/4 — deterministic content primitives (impl guide §3.3).

The measurable half of Categories 3 (structure) and 4 (substance) — the checks
that don't need an LLM. DOM-structural checks (headings, lists/tables, alt text)
run on the rendered HTML via selectolax; text-statistical checks (fact density)
run on trafilatura's extracted main text; freshness uses htmldate plus JSON-LD
``dateModified`` and a visible "last updated" regex.

Each primitive is one named pass/partial/fail/ungradeable verdict per page, so it
flows into the same persistence + roadmap path as the SSR/schema/link checks.
This complements the Cat 3/4 *LLM judge* (the subjective ``[J]`` half), which
stays gated on calibration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from selectolax.parser import HTMLParser

from src.audit.crawl.models import PageRecord

__all__ = [
    "PrimitiveCheck",
    "ContentPrimitivesResult",
    "check_content_primitives",
    "PRIMITIVE_CHECKS",
]

logger = logging.getLogger(__name__)

# A heading is "question-like" if it ends with ? or opens with an interrogative.
_QUESTION_RE = re.compile(
    r"^\s*(who|what|when|where|why|how|which|can|do|does|did|is|are|should|will)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d[\d,.]*")
_VISIBLE_UPDATED_RE = re.compile(r"(last\s+updated|updated\s+on|reviewed\s+on)\b", re.IGNORECASE)

# (check_key, category) for the verdicts this module emits — declared so the
# roadmap synthesizer and callers know the full set.
PRIMITIVE_CHECKS: tuple[tuple[str, int], ...] = (
    ("headings_questions", 3),
    ("scannable_format", 3),
    ("alt_text", 3),
    ("fact_density", 4),
    ("freshness_date", 4),
)


@dataclass
class PrimitiveCheck:
    check_key: str
    category: int
    status: str  # pass | partial | fail | ungradeable
    detail: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentPrimitivesResult:
    page_url: str
    checks: list[PrimitiveCheck]


def _effective_html(page: PageRecord) -> str:
    return page.rendered_html or page.raw_html or ""


# --- individual primitives ---------------------------------------------------


def _headings_questions(tree: HTMLParser) -> PrimitiveCheck:
    headings = [(h.text(deep=True) or "").strip() for h in tree.css("h1, h2, h3, h4")]
    headings = [h for h in headings if h]
    if len(headings) < 2:
        return PrimitiveCheck(
            "headings_questions",
            3,
            "ungradeable",
            "too few headings to assess",
            {"headings": len(headings)},
        )
    questions = sum(1 for h in headings if h.endswith("?") or _QUESTION_RE.match(h))
    ratio = questions / len(headings)
    status = "pass" if ratio >= 0.3 else "partial" if questions else "fail"
    return PrimitiveCheck(
        "headings_questions",
        3,
        status,
        f"{questions}/{len(headings)} headings phrased as questions",
        {"question_headings": questions, "total_headings": len(headings)},
    )


def _scannable_format(tree: HTMLParser) -> PrimitiveCheck:
    list_items = len(tree.css("li"))
    tables = len(tree.css("table"))
    paragraphs = [(p.text(deep=True) or "").split() for p in tree.css("p")]
    long_paras = sum(1 for words in paragraphs if len(words) > 120)
    has_structure = list_items >= 4 or tables >= 1
    some_structure = list_items >= 1
    if has_structure and long_paras == 0:
        status = "pass"
    elif has_structure or some_structure:
        status = "partial"
    else:
        status = "fail"
    return PrimitiveCheck(
        "scannable_format",
        3,
        status,
        f"{list_items} list item(s), {tables} table(s), {long_paras} long paragraph(s)",
        {"list_items": list_items, "tables": tables, "long_paragraphs": long_paras},
    )


def _alt_text(tree: HTMLParser) -> PrimitiveCheck:
    should_have, with_alt = 0, 0
    for img in tree.css("img"):
        attrs = img.attributes
        if (attrs.get("width") == "1") or (attrs.get("height") == "1"):
            continue  # tracking pixel
        alt = attrs.get("alt")
        # selectolax reports both `alt=""` and a missing alt as None, so use key
        # presence to tell them apart: an *explicit* empty alt is decorative (OK).
        if "alt" in attrs and not alt:
            continue
        should_have += 1
        if alt:
            with_alt += 1
    if should_have == 0:
        return PrimitiveCheck("alt_text", 3, "ungradeable", "no content images", {"images": 0})
    coverage = with_alt / should_have
    status = "pass" if coverage >= 0.9 else "partial" if coverage >= 0.5 else "fail"
    return PrimitiveCheck(
        "alt_text",
        3,
        status,
        f"{with_alt}/{should_have} content images have alt text",
        {"with_alt": with_alt, "should_have_alt": should_have},
    )


def _fact_density(text: str) -> PrimitiveCheck:
    words = len(text.split())
    if words < 50:
        return PrimitiveCheck(
            "fact_density", 4, "ungradeable", "too little text to assess", {"words": words}
        )
    numbers = len(_NUMBER_RE.findall(text))
    per_100 = numbers / words * 100
    status = "pass" if per_100 >= 1.5 else "partial" if per_100 >= 0.5 else "fail"
    return PrimitiveCheck(
        "fact_density",
        4,
        status,
        f"{numbers} numeric tokens over {words} words ({per_100:.1f}/100w)",
        {"numbers": numbers, "words": words, "per_100_words": round(per_100, 2)},
    )


def _freshness_date(html: str, text: str, json_ld: list[dict[str, Any]]) -> PrimitiveCheck:
    json_modified = any(node.get("dateModified") for node in json_ld if isinstance(node, dict))
    json_published = any(node.get("datePublished") for node in json_ld if isinstance(node, dict))
    visible_updated = bool(_VISIBLE_UPDATED_RE.search(text))
    try:
        from htmldate import find_date

        updated = find_date(html, original_date=False, extensive_search=False)
        original = find_date(html, original_date=True, extensive_search=False)
    except Exception as exc:  # htmldate can choke on odd HTML — degrade, don't crash
        logger.warning("htmldate failed: %s", type(exc).__name__)
        updated = original = None

    has_freshness = bool(json_modified or visible_updated or updated)
    has_any_date = bool(has_freshness or json_published or original)
    if has_freshness:
        status, detail = "pass", "visible/structured last-updated date present"
    elif has_any_date:
        status, detail = "partial", "a publish date exists but no clear last-updated signal"
    else:
        status, detail = "fail", "no visible or structured date found"
    return PrimitiveCheck(
        "freshness_date",
        4,
        status,
        detail,
        {
            "html_updated": updated,
            "html_original": original,
            "json_ld_modified": json_modified,
            "visible_updated": visible_updated,
        },
    )


def check_content_primitives(page: PageRecord) -> ContentPrimitivesResult:
    """Run every deterministic Cat 3/4 primitive over one crawled page."""
    html = _effective_html(page)
    text = page.extracted_text or ""
    if not html:
        checks = [
            PrimitiveCheck(key, cat, "ungradeable", "no page HTML", {})
            for key, cat in PRIMITIVE_CHECKS
        ]
        return ContentPrimitivesResult(page.url, checks)
    try:
        tree = HTMLParser(html)
    except Exception as exc:
        logger.warning("content-primitives parse failed for %s: %s", page.url, exc)
        tree = HTMLParser("<html></html>")
    return ContentPrimitivesResult(
        page.url,
        [
            _headings_questions(tree),
            _scannable_format(tree),
            _alt_text(tree),
            _fact_density(text),
            _freshness_date(html, text, page.json_ld),
        ],
    )
