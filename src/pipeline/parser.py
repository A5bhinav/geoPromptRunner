from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache

__all__ = [
    "MentionType",
    "detect_mention",
    "extract_competitors",
    "extract_competitor_mentions",
]


class MentionType(StrEnum):
    """How a brand appears in a response."""

    RECOMMENDED = "recommended"
    MENTIONED = "mentioned"
    NOT_MENTIONED = "not_mentioned"


# Explicit recommendation language. If any appears in a response that also
# mentions the brand, the brand is treated as RECOMMENDED.
RECOMMENDATION_TERMS: tuple[str, ...] = ("best", "recommend", "suggest", "top choice")

# Compiled once at import: matches any recommendation term on a word boundary.
# Precompiling avoids rebuilding the pattern on every response we parse.
_RECOMMENDATION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in RECOMMENDATION_TERMS) + r")\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=512)
def _brand_pattern(brand: str) -> re.Pattern[str]:
    """Return (and cache) a word-boundary, case-insensitive pattern for ``brand``.

    A run reuses the same handful of brand names across many responses, so
    caching the compiled patterns avoids recompiling per call.
    """
    return re.compile(r"\b" + re.escape(brand) + r"\b", re.IGNORECASE)


def _mentions_brand(brand: str, response: str) -> bool:
    """Case-insensitive, word-boundary brand presence test.

    An empty or whitespace-only brand never matches (guards against an empty
    pattern matching every response).
    """
    brand = brand.strip()
    if not brand:
        return False
    return _brand_pattern(brand).search(response) is not None


def _has_recommendation_language(response: str) -> bool:
    """True if ``response`` contains any explicit recommendation term."""
    return _RECOMMENDATION_RE.search(response) is not None


def _classify(present: bool, recommended: bool) -> MentionType:
    """Map (brand present?, recommendation language present?) to a MentionType.

    Single source of truth for the classification rule, shared by
    ``detect_mention`` and ``extract_competitor_mentions``.
    """
    if not present:
        return MentionType.NOT_MENTIONED
    return MentionType.RECOMMENDED if recommended else MentionType.MENTIONED


def detect_mention(brand: str, response: str) -> MentionType:
    """Classify how ``brand`` appears in ``response``.

    Pure function. Case-insensitive. Returns ``RECOMMENDED`` if the brand is
    present and explicit recommendation language is present, ``MENTIONED`` if
    the brand is present without it, otherwise ``NOT_MENTIONED``.
    """
    present = _mentions_brand(brand, response)
    # `and` short-circuits, so recommendation language is only scanned when the
    # brand is actually present.
    return _classify(present, present and _has_recommendation_language(response))


def extract_competitors(competitors: list[str], response: str) -> list[str]:
    """Return the competitors that appear in ``response`` (case-insensitive)."""
    return [c for c in competitors if _mentions_brand(c, response)]


def extract_competitor_mentions(competitors: list[str], response: str) -> dict[str, MentionType]:
    """Map each competitor to how it appears in ``response`` (case-insensitive)."""
    # Recommendation language is a property of the response, not of any single
    # brand — scan for it once rather than re-running it for every competitor.
    recommended = _has_recommendation_language(response)
    result: dict[str, MentionType] = {}
    for competitor in competitors:
        present = _mentions_brand(competitor, response)
        result[competitor] = _classify(present, present and recommended)
    return result


if __name__ == "__main__":
    samples: list[tuple[str, str, MentionType]] = [
        ("Acme", "For startups, the best CRM is Acme by far.", MentionType.RECOMMENDED),
        ("Acme", "Acme is one of several tools in this space.", MentionType.MENTIONED),
        ("Acme", "We looked at Salesforce and HubSpot only.", MentionType.NOT_MENTIONED),
        ("Acme", "I recommend Acme for small teams.", MentionType.RECOMMENDED),
        ("acme", "ACME integrates with most stacks.", MentionType.MENTIONED),
    ]
    print("=== detect_mention ===")
    all_ok = True
    for brand, text, expected in samples:
        verdict = detect_mention(brand, text)
        ok = verdict is expected
        all_ok = all_ok and ok
        print(f"[{'OK' if ok else 'FAIL'}] {brand!r}: {verdict.value} (expected {expected.value})")

    print("\n=== competitor extraction ===")
    competitors = ["Salesforce", "HubSpot", "Pipedrive"]
    text = "Top picks: Salesforce and HubSpot, though Pipedrive is also solid."
    print("extract_competitors:", extract_competitors(competitors, text))
    print(
        "extract_competitor_mentions:",
        {k: v.value for k, v in extract_competitor_mentions(competitors, text).items()},
    )

    raise SystemExit(0 if all_ok else 1)
