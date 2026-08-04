"""What a plan buys, and the one thing it deliberately does not (P5-T5).

**Meter on prompts × engines × competitors. Never on cadence.**

That is the whole design, and the negative half is the load-bearing half:

- Cadence is a **cost-to-you metric masquerading as a value metric**. Running the
  same question set twice this week costs us engine calls; it does not give the
  client twice the value, and charging as though it did is charging for our own
  infrastructure.
- **Every competitor gives daily refresh away.** Metering it prices us out of a
  comparison we would otherwise win on measurement quality.
- It creates the trap where **a flat week reads as wasted money**. A recurring
  product whose value proposition includes "held steady at 8 of 12 for the third
  week" cannot also charge per refresh — the two claims contradict each other in
  front of the customer.

There is a separate, legitimate reason to limit how often a run fires: spend
control for two founders (``MAX_AUDIT_COST_USD`` / ``MAX_TOTAL_SPEND_USD``, in
``src/config/settings.py``). That is an internal budget guard and it must never
become a tier dimension — the same mechanism worn as a plan limit walks straight
into the ruling above. ``tests/test_tiers.py`` asserts no code path here reads a
cadence, an interval or a refresh frequency.

Seats are unlimited at every tier. A team that has to ration logins does not
share the report, and a report nobody reads does not get renewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "Tier",
    "TierLimits",
    "LimitBreach",
    "TIERS",
    "limits_for",
    "check_run",
]


class Tier(StrEnum):
    """The plans. `TRACK` is what ships today; `TRACK_PRO` matches the section
    registry's tier field so the two cannot drift into different vocabularies."""

    FREE = "free"
    TRACK = "track"
    TRACK_PRO = "track_pro"


@dataclass(frozen=True)
class TierLimits:
    """The three metered dimensions, and nothing else.

    Every field here is a property of WHAT IS MEASURED. There is deliberately no
    field for how often it may be measured, and adding one is the change this
    module exists to argue against.
    """

    tier: str
    max_prompts: int
    max_engines: int
    max_competitors: int
    #: Runs per cycle are UNLIMITED at every tier. A client must never be locked
    #: out of recovering from a failed run — the run they cannot repeat is the one
    #: that produced a broken report.
    max_runs_per_query: int
    #: Seats are unlimited everywhere. Present as a documented constant rather
    #: than an absent concept, so "should we meter seats?" has an answer in code.
    unlimited_seats: bool = True


#: The free scan's caps are deliberately tight (P5-T1): 10–15 prompts across the
#: two cheapest, most recognisable surfaces. It exists to show a COUNT, not to be
#: a small paid audit.
TIERS: dict[str, TierLimits] = {
    Tier.FREE.value: TierLimits(
        tier=Tier.FREE.value,
        max_prompts=15,
        max_engines=2,
        max_competitors=1,
        max_runs_per_query=1,
    ),
    Tier.TRACK.value: TierLimits(
        tier=Tier.TRACK.value,
        max_prompts=50,
        max_engines=6,
        max_competitors=5,
        max_runs_per_query=5,
    ),
    Tier.TRACK_PRO.value: TierLimits(
        tier=Tier.TRACK_PRO.value,
        max_prompts=200,
        max_engines=8,
        max_competitors=15,
        max_runs_per_query=5,
    ),
}


@dataclass(frozen=True)
class LimitBreach:
    """One dimension over its cap, phrased for a human.

    Names the dimension, the ask and the cap — never just "limit exceeded". A
    client who cannot see which number was too big cannot fix their own request.
    """

    dimension: str
    requested: int
    allowed: int

    def message(self) -> str:
        return (
            f"{self.dimension}: this run asks for {self.requested}, and the "
            f"{self.dimension} limit on this plan is {self.allowed}."
        )


def limits_for(tier: str) -> TierLimits:
    """The caps for a tier. Unknown tiers get the FREE caps.

    Failing closed, deliberately: an unrecognised tier string is a bug or a
    tampered request, and the safe reading of "we do not know what this customer
    bought" is the smallest thing we sell.
    """
    return TIERS.get(tier, TIERS[Tier.FREE.value])


def check_run(
    tier: str,
    *,
    n_prompts: int,
    n_engines: int,
    n_competitors: int,
    runs_per_query: int = 1,
) -> list[LimitBreach]:
    """Every dimension over its cap, or an empty list.

    Returns ALL breaches rather than the first. A caller who fixes one limit and
    resubmits only to hit the next has been made to guess at the shape of their
    own plan three times.

    Note the signature: there is no ``cadence``, no ``last_run_at`` and no
    ``interval``. That absence is the feature.
    """
    caps = limits_for(tier)
    candidates = (
        ("prompts", n_prompts, caps.max_prompts),
        ("surfaces", n_engines, caps.max_engines),
        ("competitors", n_competitors, caps.max_competitors),
        ("runs per question", runs_per_query, caps.max_runs_per_query),
    )
    return [
        LimitBreach(dimension=name, requested=asked, allowed=cap)
        for name, asked, cap in candidates
        if asked > cap
    ]


if __name__ == "__main__":
    for tier in Tier:
        caps = limits_for(tier.value)
        print(
            f"{tier.value:10s} prompts<={caps.max_prompts:3d} "
            f"surfaces<={caps.max_engines} competitors<={caps.max_competitors}"
        )
    breaches = check_run(Tier.FREE.value, n_prompts=40, n_engines=6, n_competitors=3)
    for breach in breaches:
        print(breach.message())
