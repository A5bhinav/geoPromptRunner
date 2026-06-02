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

# Negative-framing cues. A brand in a segment carrying one of these is not
# treated as recommended even if a recommendation word is nearby ("avoid X",
# "X is weak"). Full sentiment is a job for the LLM judge; this just stops the
# crudest false positives.
_NEGATION_RE = re.compile(
    r"\b(?:avoid|not|never|no longer|worst|weak|weaker|lacks?|lacking|poor|"
    r"limited|don't|doesn't|isn't|steer clear|stay away|overrated|overpriced)\b",
    re.IGNORECASE,
)

# Segment boundaries: sentence enders plus contrastive conjunctions. We classify
# recommendation at the *segment containing the brand*, not the whole response,
# so "The best CRM is Salesforce, but Acme also exists" does not mark Acme as
# recommended just because "best" appears elsewhere in the answer.
_SEGMENT_RE = re.compile(
    r"[.!?;]|\bbut\b|\bhowever\b|\bwhereas\b|\balthough\b|\bthough\b|\byet\b",
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


def detect_mention(brand: str, response: str) -> MentionType:
    """Classify how ``brand`` appears in ``response``.

    Pure function, case-insensitive. ``RECOMMENDED`` when the brand appears in a
    segment (sentence/clause) that also carries explicit recommendation language
    and no negative framing; ``MENTIONED`` when present otherwise;
    ``NOT_MENTIONED`` when absent.

    Scoping recommendation to the brand's own segment avoids the systematic
    over-counting of pure response-level matching. This is still a heuristic —
    sentiment, accuracy, and rank/prominence are the LLM judge's job.
    """
    brand = brand.strip()
    if not brand or not _mentions_brand(brand, response):
        return MentionType.NOT_MENTIONED

    pattern = _brand_pattern(brand)
    for segment in _SEGMENT_RE.split(response):
        if not pattern.search(segment):
            continue
        if _NEGATION_RE.search(segment):
            continue  # brand present but negatively framed here — not a rec
        if _RECOMMENDATION_RE.search(segment):
            return MentionType.RECOMMENDED
    return MentionType.MENTIONED


def extract_competitors(competitors: list[str], response: str) -> list[str]:
    """Return the competitors that appear in ``response`` (case-insensitive)."""
    return [c for c in competitors if _mentions_brand(c, response)]


def extract_competitor_mentions(competitors: list[str], response: str) -> dict[str, MentionType]:
    """Map each competitor to how it appears in ``response`` (case-insensitive)."""
    return {competitor: detect_mention(competitor, response) for competitor in competitors}


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
