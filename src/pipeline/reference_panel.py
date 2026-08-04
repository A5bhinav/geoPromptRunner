"""Market context from brands who are not clients (P5-T4).

Benchmark context normally needs many paying customers. Here it does not: model
outputs to structured prompts are producible for **any** brand, so the same
taxonomy can be run against a fixed panel of well-known brands per vertical on
the same cadence, and a client can be placed against a distribution rather than
against nothing.

Three rules, and each of them is a way this feature could be dishonest:

**Never "peer benchmark".** Famous brands score systematically higher than a
median client — that is what makes them famous. Calling their distribution a peer
benchmark tells a client they are behind their peers when what they are behind is
Nike. The sanctioned words are "reference panel" and "market context", and
:func:`panel_label` is the only place either is produced.

**Percentiles, never a mean.** At n=15–30 a single viral brand drags a mean
somewhere no member of the panel actually sits. P25/P50/P75 describe where the
middle of the panel is, and they survive an outlier.

**Suppress below n=5, prefer n≥10.** A band drawn over four brands is four brands
wearing a distribution's clothes. Suppression happens at the product layer — here
— rather than being left to whoever reads the chart.

Every band renders its own ``n`` and its date range inline. A percentile with no
sample size beside it is the same failure as a rate with no denominator.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

__all__ = [
    "MIN_PANEL_N",
    "PREFERRED_PANEL_N",
    "PanelMember",
    "PanelBand",
    "panel_label",
    "build_band",
    "place_client",
]

#: Below this, no band renders at all. Four brands is not a distribution.
MIN_PANEL_N = 5

#: The size a band should be to carry weight. Between this and MIN_PANEL_N the
#: band renders WITH a stated caution rather than silently looking as solid as a
#: full one.
PREFERRED_PANEL_N = 10


@dataclass(frozen=True)
class PanelMember:
    """One reference brand's measured rate in one vertical, one cycle.

    ``is_client`` exists so a client accidentally present in its own reference
    panel can be excluded — comparing a brand to a distribution it is inside
    flatters or punishes it by its own contribution.
    """

    brand: str
    vertical: str
    successes: int
    n: int
    run_date: str
    is_client: bool = False

    @property
    def rate(self) -> float:
        return self.successes / self.n if self.n else 0.0


class PanelBand(TypedDict):
    """A vertical's distribution, or an explicit refusal to draw one."""

    vertical: str
    available: bool
    n: int
    p25: float
    p50: float
    p75: float
    #: "reference panel" / "market context" wording. NEVER "benchmark".
    label: str
    #: The date range the members were measured over, disclosed inline.
    window: str
    #: Why the band is missing or weak. Empty when the band is full strength.
    caution: str


def panel_label(vertical: str) -> str:
    """The one place panel wording is produced.

    Centralised so "benchmark" cannot creep in through a component: a test
    asserts this module never emits the word, and a component that writes its own
    label would route around that assertion.
    """
    return f"Reference panel — market context for {vertical}"


def _percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, and NOT a mean.

    `statistics.quantiles` needs n≥2 and returns cut points rather than
    arbitrary quantiles, so this does the interpolation directly — the panel is
    small enough that the arithmetic is cheaper than the dependency dance.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def build_band(vertical: str, members: Sequence[PanelMember]) -> PanelBand:
    """The distribution for one vertical, suppressed when too thin.

    A suppressed band is not an empty chart — ``caution`` says how many brands
    were available and why that is not enough, because "we have four" is
    information and a blank space is a rendering bug.
    """
    usable = [m for m in members if m.vertical == vertical and not m.is_client and m.n > 0]
    dates = sorted(m.run_date for m in usable if m.run_date)
    window = f"{dates[0]} to {dates[-1]}" if dates else ""

    if len(usable) < MIN_PANEL_N:
        return PanelBand(
            vertical=vertical,
            available=False,
            n=len(usable),
            p25=0.0,
            p50=0.0,
            p75=0.0,
            label=panel_label(vertical),
            window=window,
            caution=(
                f"Only {len(usable)} reference brand{'s' if len(usable) != 1 else ''} "
                f"have been measured for {vertical}. A range drawn over fewer than "
                f"{MIN_PANEL_N} is not a distribution, so none is shown."
            ),
        )

    rates = [m.rate for m in usable]
    caution = ""
    if len(usable) < PREFERRED_PANEL_N:
        caution = (
            f"Based on {len(usable)} reference brands. Read the range as indicative "
            f"until the panel reaches {PREFERRED_PANEL_N}."
        )
    return PanelBand(
        vertical=vertical,
        available=True,
        n=len(usable),
        # Median via statistics so the p50 is exactly the conventional one, and
        # the quartiles via interpolation. Never a mean: at this n one viral
        # brand drags it somewhere no panel member actually sits.
        p25=_percentile(rates, 0.25),
        p50=statistics.median(rates),
        p75=_percentile(rates, 0.75),
        label=panel_label(vertical),
        window=window,
        caution=caution,
    )


def place_client(band: PanelBand, client_rate: float) -> str:
    """Where the client sits against the band, in words.

    Descriptive, and never a verdict. "Below the panel's middle half" is an
    observation about two measured numbers; "underperforming the market" is a
    judgement, and one that ignores the panel being made of famous brands.
    """
    if not band["available"]:
        return "There is no reference range for this category yet."
    if client_rate < band["p25"]:
        position = "below the middle half of the reference panel"
    elif client_rate > band["p75"]:
        position = "above the middle half of the reference panel"
    else:
        position = "within the middle half of the reference panel"
    return (
        f"At {client_rate:.0%}, this sits {position} "
        f"({band['p25']:.0%}–{band['p75']:.0%}, median {band['p50']:.0%}, "
        f"n={band['n']}{', ' + band['window'] if band['window'] else ''})."
    )


if __name__ == "__main__":
    members = [
        PanelMember(f"Brand {i}", "wearables", successes=i, n=12, run_date="2026-06-13")
        for i in range(1, 13)
    ]
    band = build_band("wearables", members)
    print(band["label"])
    print(place_client(band, 0.25))
    thin = build_band("wearables", members[:4])
    print(thin["caution"])
