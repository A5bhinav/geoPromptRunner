"""The one formatter that owns "how much did this move".

**Percentage points, never percent change.** A change in a *rate* is stated in
percentage points: 42% → 48% is ``+6.0 pp``, not ``+14%``. Percent change is
reserved for changes in a *count*: 120 → 150 citations is ``+25%``.

Mixing the two is the fastest way to lose a numerate reader, and it is the
single most common way AI-visibility vendors overstate movement — a rate moving
2% → 4% reported as "+100%" is technically arithmetic and practically a lie.
This module exists so that getting it wrong requires deliberately not calling
it: no component, no template and no section builder assembles a delta string
by hand (spec TR-T2).

The rendering rules, once, here:

- A rate delta rounds to one decimal place and carries an explicit sign.
- A delta that rounds to zero renders as words ("no change"), not "+0.0 pp" —
  a signed zero reads as movement to a scanning eye.
- A count delta with a zero base has no percent change; it renders "new".
- ``None`` on either side means there is nothing to compare against, which is a
  first cycle. It renders as the baseline phrase, never as 0.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "Unit",
    "NO_PRIOR",
    "NO_CHANGE",
    "fmt_delta",
    "fmt_pp",
    "fmt_rate_delta",
    "fmt_count_delta",
]

#: What a rate delta and a count delta are measured in. Deliberately not a bare
#: string: the wrong unit is the failure this module exists to prevent, so the
#: caller has to name it and the type checker has to agree.
Unit = Literal["rate", "count"]

#: A first cycle. NOT "0.0 pp" — nothing was measured before, which is a
#: different statement from "it did not move", and the tile must not imply one
#: while meaning the other.
NO_PRIOR = "Baseline — no prior cycle"

#: A move that rounds to zero at this precision. "Flat" is a claim the report
#: makes in words, not a signed zero a reader has to interpret.
NO_CHANGE = "no change"

#: Below this a rate delta is indistinguishable from zero at one decimal place.
_PP_EPSILON = 0.05


def fmt_pp(delta_pp: float | None) -> str:
    """Render an ALREADY-COMPUTED percentage-point delta.

    For callers that hold the pp figure rather than the two rates — the movement
    engine computes ``Movement.delta_pp`` during significance gating, and
    recomputing it from rounded rates here would let the tile and the section
    disagree in the last decimal.
    """
    if delta_pp is None:
        return NO_PRIOR
    if abs(delta_pp) < _PP_EPSILON:
        return NO_CHANGE
    return f"{delta_pp:+.1f} pp"


def fmt_rate_delta(before: float | None, after: float | None) -> str:
    """Two rates in [0, 1] → a percentage-point delta.

    Both sides are rates of the same quantity measured the same way. The caller
    is responsible for having established that (a rate from a different query
    set is not comparable at all — see ``comparison_blocked_reason``); this
    function only formats.
    """
    if before is None or after is None:
        return NO_PRIOR
    return fmt_pp((after - before) * 100)


def fmt_count_delta(before: int | float | None, after: int | float | None) -> str:
    """Two counts → a percent change.

    A zero base has no percent change (the division is undefined, and "+∞%" is
    not a number a client can act on), so it renders "new" when something
    appeared and "no change" when nothing did.
    """
    if before is None or after is None:
        return NO_PRIOR
    if before == 0:
        return "new" if after > 0 else NO_CHANGE
    change = (after - before) / before * 100
    if abs(change) < 0.5:
        return NO_CHANGE
    return f"{change:+.0f}%"


def fmt_delta(
    before: float | int | None,
    after: float | int | None,
    unit: Unit,
) -> str:
    """The single entry point. ``unit="rate"`` → pp; ``unit="count"`` → percent.

    >>> fmt_delta(0.42, 0.48, "rate")
    '+6.0 pp'
    >>> fmt_delta(120, 150, "count")
    '+25%'
    """
    if unit == "rate":
        return fmt_rate_delta(
            None if before is None else float(before),
            None if after is None else float(after),
        )
    return fmt_count_delta(before, after)


if __name__ == "__main__":
    for b, a, u in (
        (0.42, 0.48, "rate"),
        (0.48, 0.42, "rate"),
        (0.42, 0.4201, "rate"),
        (None, 0.48, "rate"),
        (120, 150, "count"),
        (0, 3, "count"),
        (150, 120, "count"),
    ):
        unit: Unit = "rate" if u == "rate" else "count"
        print(f"{b} -> {a} ({unit}): {fmt_delta(b, a, unit)}")
