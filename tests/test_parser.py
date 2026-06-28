from __future__ import annotations

from src.pipeline.parser import (
    MentionType,
    detect_mention,
    extract_competitor_mentions,
    extract_competitors,
)

R = MentionType.RECOMMENDED
M = MentionType.MENTIONED
N = MentionType.NOT_MENTIONED


def test_original_cases() -> None:
    assert detect_mention("Acme", "For budgeting, the best app is Acme by far.") is R
    assert detect_mention("Acme", "Acme is one of several apps in this space.") is M
    assert detect_mention("Acme", "We looked at YNAB and Monarch Money only.") is N
    assert detect_mention("Acme", "I recommend Acme for first-time budgeters.") is R
    assert detect_mention("acme", "ACME syncs with most banks.") is M


def test_recommendation_is_scoped_to_the_brands_segment() -> None:
    # "best" binds to YNAB; Acme is in a contrastive clause -> not recommended.
    assert detect_mention("Acme", "The best budgeting app is YNAB, but Acme also exists.") is M
    assert detect_mention("Acme", "The best budgeting app is YNAB. Acme also exists.") is M
    # Same segment carries both -> recommended.
    assert detect_mention("Acme", "Acme is the best budgeting app for students.") is R


def test_negative_framing_is_not_recommended() -> None:
    assert detect_mention("Acme", "Avoid Acme, it's weak.") is M
    assert detect_mention("Acme", "Acme is not a good choice.") is M


def test_empty_or_whitespace_brand_never_matches() -> None:
    assert detect_mention("", "anything at all") is N
    assert detect_mention("   ", "anything at all") is N


def test_word_boundaries_and_case() -> None:
    assert detect_mention("Acme", "Acmeism is unrelated.") is N
    assert detect_mention("ACME", "we use acme daily") is M


def test_competitor_extraction() -> None:
    text = "The best option is YNAB, but Monarch Money is also mentioned."
    assert extract_competitors(["YNAB", "Monarch Money", "Rocket Money"], text) == [
        "YNAB",
        "Monarch Money",
    ]
    verdicts = extract_competitor_mentions(["YNAB", "Monarch Money", "Rocket Money"], text)
    assert verdicts == {"YNAB": R, "Monarch Money": M, "Rocket Money": N}
