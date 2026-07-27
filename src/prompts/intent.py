from __future__ import annotations

from enum import StrEnum

__all__ = [
    "IntentBucket",
    "BUCKET_ALLOCATION",
    "LOCAL_BUCKET_ALLOCATION",
    "CONSUMER_BUCKETS",
    "LOCAL_BUCKETS",
]


class IntentBucket(StrEnum):
    """Funnel-stage intent buckets every query is tagged with.

    Mirrors the methodology's intent framework so results can be read by funnel
    stage ("invisible at the category stage but fine on brand terms") rather than
    as an undifferentiated mention rate.

    Two families live here, selected by business kind (the SMB pivot's §0.6 rule):
    the consumer-product funnel, and the local-service intents. ``BRAND`` is shared —
    "is X legit" is the same question whether X is an app or a plumber. Adding
    members is backward-compatible: this is a ``StrEnum`` and ``load_query_set``
    validates against it, so existing consumer sets keep parsing unchanged.
    """

    # --- consumer-product funnel ---
    PROBLEM_AWARE = "problem_aware"  # pain described, no category named yet
    CATEGORY = "category"  # category/solution-aware: "best X for Y"
    COMPARISON = "comparison"  # head-to-head vs named competitors
    ADJACENT_AUTHORITY = "adjacent_authority"  # related expert topics

    # --- local-service intents (SMB pivot) ---
    # "best plumber in Berkeley" — resolves to the local pack / AI local pack.
    # Prefer explicit-city phrasing; "near me" variants are ~2x less stable
    # (SE Ranking) and belong in a separately-tagged, noisier cohort.
    LOCAL_INTENT = "local_intent"
    # "average cost of AC replacement in Berkeley" — commercial question with a
    # geographic qualifier; ~97% of these surface an AI Overview.
    HYBRID = "hybrid"
    # "how often should a furnace be serviced" — no geography, but ~92% AIO, and
    # it is where a shop earns authority before the buying moment.
    INFORMATIONAL = "informational"

    # --- shared ---
    BRAND = "brand"  # bottom-funnel: asked about the client directly


#: Buckets that make up a consumer-product query set.
CONSUMER_BUCKETS: tuple[IntentBucket, ...] = (
    IntentBucket.PROBLEM_AWARE,
    IntentBucket.CATEGORY,
    IntentBucket.COMPARISON,
    IntentBucket.BRAND,
    IntentBucket.ADJACENT_AUTHORITY,
)

#: Buckets that make up a local-service query set.
LOCAL_BUCKETS: tuple[IntentBucket, ...] = (
    IntentBucket.LOCAL_INTENT,
    IntentBucket.HYBRID,
    IntentBucket.INFORMATIONAL,
    IntentBucket.BRAND,
)


# Target share of a locked set per bucket (from the methodology's example
# distribution). Used to sanity-check a query set's balance, not to enforce it.
#
# FORKED, not rebalanced (pivot §0.6): the consumer dict keeps its exact pre-pivot
# values, and local gets its own. Merging local buckets into the consumer dict would
# either break its sum or silently change consumer query-set composition.
BUCKET_ALLOCATION: dict[IntentBucket, float] = {
    IntentBucket.PROBLEM_AWARE: 0.15,
    IntentBucket.CATEGORY: 0.30,
    IntentBucket.COMPARISON: 0.25,
    IntentBucket.BRAND: 0.15,
    IntentBucket.ADJACENT_AUTHORITY: 0.15,
}

# Local weighting follows where the money is: the local pack is the buying moment,
# so local_intent carries the plurality; informational earns the authority that
# feeds it; brand stays small (a shop owner already ranks for their own name).
LOCAL_BUCKET_ALLOCATION: dict[IntentBucket, float] = {
    IntentBucket.LOCAL_INTENT: 0.45,
    IntentBucket.HYBRID: 0.25,
    IntentBucket.INFORMATIONAL: 0.20,
    IntentBucket.BRAND: 0.10,
}
