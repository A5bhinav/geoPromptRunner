from __future__ import annotations

import re
from enum import StrEnum

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


def _contains(needle: str, haystack: str) -> bool:
    """Case-insensitive, word-boundary-aware substring test."""
    pattern = r"\b" + re.escape(needle.strip()) + r"\b"
    return re.search(pattern, haystack, flags=re.IGNORECASE) is not None


def detect_mention(brand: str, response: str) -> MentionType:
    """Classify how ``brand`` appears in ``response``.

    Pure function. Case-insensitive. Returns ``RECOMMENDED`` if the brand is
    present and explicit recommendation language is present, ``MENTIONED`` if
    the brand is present without it, otherwise ``NOT_MENTIONED``.
    """
    if not _contains(brand, response):
        return MentionType.NOT_MENTIONED
    if any(_contains(term, response) for term in RECOMMENDATION_TERMS):
        return MentionType.RECOMMENDED
    return MentionType.MENTIONED


def extract_competitors(competitors: list[str], response: str) -> list[str]:
    """Return the competitors that appear in ``response`` (case-insensitive)."""
    return [c for c in competitors if _contains(c, response)]


def extract_competitor_mentions(competitors: list[str], response: str) -> dict[str, MentionType]:
    """Map each competitor to how it appears in ``response`` (case-insensitive)."""
    return {c: detect_mention(c, response) for c in competitors}


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
