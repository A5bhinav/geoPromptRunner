from __future__ import annotations

from enum import StrEnum

__all__ = ["IntentBucket", "BUCKET_ALLOCATION"]


class IntentBucket(StrEnum):
    """Funnel-stage intent buckets every query is tagged with.

    Mirrors the methodology's intent framework so results can be read by funnel
    stage ("invisible at the category stage but fine on brand terms") rather than
    as an undifferentiated mention rate.
    """

    PROBLEM_AWARE = "problem_aware"  # pain described, no category named yet
    CATEGORY = "category"  # category/solution-aware: "best X for Y"
    COMPARISON = "comparison"  # head-to-head vs named competitors
    BRAND = "brand"  # bottom-funnel: asked about the client directly
    ADJACENT_AUTHORITY = "adjacent_authority"  # related expert topics


# Target share of a locked set per bucket (from the methodology's example
# distribution). Used to sanity-check a query set's balance, not to enforce it.
BUCKET_ALLOCATION: dict[IntentBucket, float] = {
    IntentBucket.PROBLEM_AWARE: 0.15,
    IntentBucket.CATEGORY: 0.30,
    IntentBucket.COMPARISON: 0.25,
    IntentBucket.BRAND: 0.15,
    IntentBucket.ADJACENT_AUTHORITY: 0.15,
}
