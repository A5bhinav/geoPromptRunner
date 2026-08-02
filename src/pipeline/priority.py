"""Which finding to fix first, and who fixes it.

The report used to end at diagnosis. That is the single largest gap against what
buyers say they want, and a finding with no action is the most-cited driver of
churn in this category — so every theme now carries a channel, an owner, an
effort, and a rank (``docs/audit-packaging-spec.md`` P1-T4).

::

    priority = funnel_weight × reach × magnitude × confidence / effort

Deterministic and free, like every other scoring layer in the report. The numbers
are a **published rubric**, not a black box: a client who disagrees with the
ordering can see exactly which term they disagree with, which is the property the
letter grade never had.

``funnel_weight`` is the first real use of the intent data the pipeline has been
collecting all along. A wrong price on a comparison query reaches someone with a
card in their hand; the same error on an awareness query reaches someone reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.pipeline.severity import SEVERITY_RANK
from src.pipeline.themes import Theme
from src.storage.models import Severity

__all__ = [
    "Owner",
    "FixChannel",
    "Effort",
    "FIX_ROUTING",
    "FixRouting",
    "routing_for",
    "funnel_weight",
    "magnitude",
    "priority_score",
]


class Owner(StrEnum):
    """Who does the work. A finding whose owner is nobody is not an action."""

    MARKETING = "Marketing"
    PR = "PR"
    ENG = "Eng"
    LEGAL = "Legal"


class FixChannel(StrEnum):
    """Where the fix lands — and therefore how hard it is.

    Effort is derived from this rather than guessed per finding, because the
    channel genuinely determines the cost: your own site is a deploy, a
    third-party listing is a form and a wait, and a training-data misconception is
    a months-long campaign with no guaranteed effect.
    """

    OWNED_SITE = "owned_site"  # your pages, your schema — you control it
    THIRD_PARTY_LISTING = "third_party_listing"  # G2, Yelp, app stores, directories
    TRAINING_DATA = "training_data"  # the models' priors; press, forums, time


class Effort(StrEnum):
    SMALL = "S"
    MEDIUM = "M"
    LARGE = "L"


#: Effort follows the channel, always. Never set independently.
_CHANNEL_EFFORT: dict[FixChannel, Effort] = {
    FixChannel.OWNED_SITE: Effort.SMALL,
    FixChannel.THIRD_PARTY_LISTING: Effort.MEDIUM,
    FixChannel.TRAINING_DATA: Effort.LARGE,
}

#: Divisor in the score. Not the literal week-count — a ratio that says a large
#: fix must be worth ~4x a small one to outrank it.
_EFFORT_COST: dict[Effort, float] = {Effort.SMALL: 1.0, Effort.MEDIUM: 2.0, Effort.LARGE: 4.0}


@dataclass(frozen=True)
class FixRouting:
    """Everything about a theme that is not measurement: who, where, how hard.

    ``action`` is a template with one ``{client}`` slot. It is deliberately
    concrete and channel-specific — "publish a pricing page with the current
    figures and a visible last-updated date" is an action; "improve your pricing
    content" is a finding wearing an action's clothes.
    """

    channel: FixChannel
    owner: Owner
    action: str
    #: What to check next cycle to know whether it worked. Stated as an
    #: observation, never as a promised outcome — the FTC pattern against
    #: guaranteed-ranking claims applies to this sentence directly.
    verification: str

    @property
    def effort(self) -> Effort:
        return _CHANNEL_EFFORT[self.channel]


#: Theme -> its fix. A static table, so a theme cannot exist without an action.
FIX_ROUTING: dict[str, FixRouting] = {
    Theme.IDENTITY_DISAMBIGUATION.value: FixRouting(
        channel=FixChannel.TRAINING_DATA,
        owner=Owner.PR,
        action=(
            "Establish {client} as a distinct entity: claim and complete a Wikidata "
            "item, add Organization schema with sameAs links to every owned profile, "
            "and pursue coverage that names {client} alongside its category."
        ),
        verification=(
            "Re-run the brand-intent queries next cycle and compare how many name "
            "{client} without a disambiguation hedge."
        ),
    ),
    Theme.CATEGORY_CONFUSION.value: FixRouting(
        channel=FixChannel.OWNED_SITE,
        owner=Owner.MARKETING,
        action=(
            "State the category in the first sentence of the {client} homepage and "
            "About page, in the same words you want repeated back, and mirror it in "
            "Organization/Product schema."
        ),
        verification="Check whether next cycle's answers use that category phrasing.",
    ),
    Theme.LIFECYCLE_STATUS.value: FixRouting(
        channel=FixChannel.OWNED_SITE,
        owner=Owner.MARKETING,
        action=(
            "Publish the current status — availability, launch window, trading hours — "
            "on a canonical {client} page with a visible last-updated date, and remove "
            "or date-stamp the superseded pages the models are reading."
        ),
        verification="Confirm the stale phrasing no longer appears in next cycle's answers.",
    ),
    Theme.PRICING_OFFER.value: FixRouting(
        channel=FixChannel.OWNED_SITE,
        owner=Owner.MARKETING,
        action=(
            "Publish current {client} pricing as plain text (not an image, not behind "
            "a form) with a visible last-updated date, and add Offer schema so the "
            "figure is machine-readable."
        ),
        verification="Check whether next cycle's answers quote the published figure.",
    ),
    Theme.FEATURE_INVENTED.value: FixRouting(
        channel=FixChannel.OWNED_SITE,
        owner=Owner.MARKETING,
        action=(
            "Publish an explicit scope statement for {client} — what it does and what "
            "it deliberately does not do — so the boundary is stated somewhere the "
            "models can retrieve rather than inferred."
        ),
        verification="Check whether the invented capability still appears next cycle.",
    ),
    Theme.FEATURE_OMITTED.value: FixRouting(
        channel=FixChannel.OWNED_SITE,
        owner=Owner.MARKETING,
        action=(
            "Give the missing capability its own {client} page with an answer-first "
            "opening line, and reference it from the comparison and alternatives pages "
            "the models retrieve most."
        ),
        verification="Check whether next cycle's answers list the capability.",
    ),
    Theme.COMPETITOR_MISCHARACTERIZATION.value: FixRouting(
        channel=FixChannel.OWNED_SITE,
        owner=Owner.MARKETING,
        action=(
            "Publish a {client}-vs-competitor comparison page that states the "
            "difference in the first paragraph, in the terms the models are currently "
            "getting wrong."
        ),
        verification="Check whether next cycle's answers still transfer the rival's attributes.",
    ),
    Theme.COMPANY_FACTS.value: FixRouting(
        channel=FixChannel.THIRD_PARTY_LISTING,
        owner=Owner.MARKETING,
        action=(
            "Make the detail identical everywhere it is published — the {client} site, "
            "Google Business Profile, LinkedIn, Crunchbase and the directories in this "
            "report — since the models are averaging the versions they find."
        ),
        verification="Re-check the directories next cycle and confirm they agree.",
    ),
    Theme.AVAILABILITY_GEOGRAPHY.value: FixRouting(
        channel=FixChannel.THIRD_PARTY_LISTING,
        owner=Owner.MARKETING,
        action=(
            "Correct hours and service area on the {client} Google Business Profile "
            "first, then the site, then the directories — and add areaServed and "
            "openingHours to the site's LocalBusiness schema."
        ),
        verification="Re-run the local-intent queries next cycle and compare the stated coverage.",
    ),
    Theme.SOURCE_CITATION_QUALITY.value: FixRouting(
        channel=FixChannel.TRAINING_DATA,
        owner=Owner.PR,
        action=(
            "Get {client} named in the sources this report shows the models actually "
            "retrieve for the category, rather than adding more pages to a site they "
            "are not reading."
        ),
        verification="Compare next cycle's cited-domain list against this one.",
    ),
    Theme.RISK_REPUTATION.value: FixRouting(
        channel=FixChannel.THIRD_PARTY_LISTING,
        owner=Owner.LEGAL,
        action=(
            "Publish the licence, bonding and insurance numbers for {client} on the "
            "site and on every directory listing, and respond on the record to any "
            "complaint the models are surfacing."
        ),
        verification="Re-check whether the concern still appears in next cycle's answers.",
    ),
    Theme.UNCLASSIFIED.value: FixRouting(
        channel=FixChannel.OWNED_SITE,
        owner=Owner.MARKETING,
        action=(
            "Review this finding manually — the classifier had no rule for it, so it "
            "has no routed action yet."
        ),
        verification="Confirm a rule has been added before the next cycle.",
    ),
}


def routing_for(theme: str) -> FixRouting:
    """The fix for a theme. Falls back to the manual-review routing, never to None.

    A finding with no action is unfinished, and silently dropping one that the
    taxonomy has not caught up with is how a report stops being complete without
    anyone noticing.
    """
    return FIX_ROUTING.get(theme, FIX_ROUTING[Theme.UNCLASSIFIED.value])


#: Intents where the reader is choosing, not learning.
_BOTTOM_FUNNEL = frozenset({"comparison", "brand", "local_intent"})

#: Ratio, not a scale: a bottom-funnel error is worth three of the same error
#: upstream, because the person reading it is about to decide.
_BOTTOM_FUNNEL_WEIGHT = 3.0
_UPPER_FUNNEL_WEIGHT = 1.0


def funnel_weight(intents: list[str]) -> float:
    """Weight for the funnel stages a finding appeared on.

    Uses the MAX rather than the mean: a finding that shows up on one comparison
    query and nine awareness queries is a bottom-funnel problem that also happens
    upstream, not a mostly-harmless one. Averaging would let volume upstream
    dilute the one instance that costs money.
    """
    if not intents:
        return _UPPER_FUNNEL_WEIGHT
    return max(
        _BOTTOM_FUNNEL_WEIGHT if i in _BOTTOM_FUNNEL else _UPPER_FUNNEL_WEIGHT for i in intents
    )


#: Severity as a multiplier. The gaps widen going up so a single Critical
#: outranks a pile of Mediums — which is the ordering a reader expects and the
#: reason the count bar leads with Critical.
_MAGNITUDE: dict[str, float] = {
    Severity.CRITICAL.value: 8.0,
    Severity.HIGH.value: 4.0,
    Severity.MED.value: 2.0,
    Severity.LOW.value: 1.0,
}


def magnitude(severity: str) -> float:
    """Severity as a multiplier. An unknown severity scores as low, never as high."""
    return _MAGNITUDE.get(severity, 1.0)


def priority_score(
    severity: str,
    intents: list[str],
    observed: int,
    total: int,
    engine_count: int,
    total_engines: int,
    channel: FixChannel,
    confidence: float = 1.0,
) -> float:
    """Rank one finding. Deterministic; the same inputs always give the same number.

    ``reach`` is two things multiplied: how reliably the error reproduces
    (``observed / total`` runs) and how much of the measured surface it spans
    (``engine_count / total_engines``). An error on one engine once is not the
    same problem as the same error on five engines every time, and only the
    second term catches breadth.

    ``confidence`` is 1.0 for a direct fact-sheet contradiction and ~0.6 for a
    borderline judge call. It multiplies rather than gates, so a shaky Critical
    can still outrank a certain Low — but not a certain Critical.
    """
    reproducibility = observed / total if total > 0 else 0.0
    breadth = engine_count / total_engines if total_engines > 0 else 0.0
    reach = reproducibility * breadth
    effort_cost = _EFFORT_COST[_CHANNEL_EFFORT[channel]]
    return funnel_weight(intents) * reach * magnitude(severity) * confidence / effort_cost


def sort_key(
    severity: str, score: float, cluster_id: str, regressed: bool = False
) -> tuple[int, int, float, str]:
    """Stable ordering for the actions table.

    Regressed findings sort above everything, then severity, then score. A fix
    that did not hold is worse news than a fresh problem of the same severity —
    it means the recommendation was wrong or the change was reverted, and either
    way the client needs to hear it first.

    ``cluster_id`` is the final tie-break so the order is total: two findings with
    identical scores must not swap places between renders of the same run.
    """
    return (0 if regressed else 1, SEVERITY_RANK.get(severity, 99), -score, cluster_id)


if __name__ == "__main__":
    pricing = priority_score(
        Severity.CRITICAL.value, ["comparison"], 9, 12, 4, 6, FixChannel.OWNED_SITE
    )
    founder = priority_score(
        Severity.CRITICAL.value, ["problem_aware"], 9, 12, 4, 6, FixChannel.OWNED_SITE
    )
    print(f"bottom-funnel pricing error : {pricing:.3f}")
    print(f"awareness founder-bio error : {founder:.3f}")
    print(f"ratio                       : {pricing / founder:.1f}x")
    for theme, routing in list(FIX_ROUTING.items())[:3]:
        print(f"\n{theme}: {routing.owner} / {routing.channel} / effort {routing.effort}")
