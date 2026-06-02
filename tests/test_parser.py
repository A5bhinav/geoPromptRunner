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
    assert detect_mention("Acme", "For startups, the best CRM is Acme by far.") is R
    assert detect_mention("Acme", "Acme is one of several tools in this space.") is M
    assert detect_mention("Acme", "We looked at Salesforce and HubSpot only.") is N
    assert detect_mention("Acme", "I recommend Acme for small teams.") is R
    assert detect_mention("acme", "ACME integrates with most stacks.") is M


def test_recommendation_is_scoped_to_the_brands_segment() -> None:
    # "best" binds to Salesforce; Acme is in a contrastive clause -> not recommended.
    assert detect_mention("Acme", "The best CRM is Salesforce, but Acme also exists.") is M
    assert detect_mention("Acme", "The best CRM is Salesforce. Acme also exists.") is M
    # Same segment carries both -> recommended.
    assert detect_mention("Acme", "Acme is the best CRM for startups.") is R


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
    text = "The best option is Salesforce, but HubSpot is also mentioned."
    assert extract_competitors(["Salesforce", "HubSpot", "Pipedrive"], text) == [
        "Salesforce",
        "HubSpot",
    ]
    verdicts = extract_competitor_mentions(["Salesforce", "HubSpot", "Pipedrive"], text)
    assert verdicts == {"Salesforce": R, "HubSpot": M, "Pipedrive": N}
