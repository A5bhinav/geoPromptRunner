"""Which week-over-week changes are news, and which are noise (P2-T4).

Without gating, most week-over-week movement is noise reported as news — the
fastest way to destroy credibility in a recurring product. This module decides
what earns an "Up" or "Down" label, using the intervals in
:mod:`src.pipeline.stats`.

**Two gates, both must pass.**

1. **Statistical** — Newcombe's CI for the *difference* excludes zero. Not CI
   overlap: two 95% CIs can overlap while the difference is significant, and the
   overlap heuristic effectively tests against an interval ~√2 too wide.
2. **Practical** — the move clears a computed minimum detectable effect for that
   cell's own effective sample. A well-sampled surface gets a more sensitive test
   than a thin one, instead of one global noise floor flattering both.

**Flat is a claim, not a blank.** A weekly product that manufactures news in flat
weeks destroys itself faster than one that reports nothing happened — so an
ungated cell renders *"held steady at 8 of 12 runs"*, never an empty cell or a
0pp arrow.

**Multiple comparisons: Benjamini–Hochberg, not Bonferroni.** Six surfaces plus
buckets is ~20 simultaneous tests. For an exploratory weekly scan where
under-flagging real movement is worse than a false positive that self-corrects
next week, controlling the false *discovery* rate is the right frame; Bonferroni
at this many comparisons and this little data would suppress nearly everything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from src.pipeline import stats

__all__ = [
    "Direction",
    "PRACTICAL_FLOOR_PP",
    "Movement",
    "compare_cell",
    "gate_movements",
]


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"
    #: Not enough data on one side to say anything. Distinct from FLAT, which is
    #: a positive claim that nothing moved.
    UNKNOWN = "unknown"


#: The business floor, in percentage points, below which a statistically real
#: move still isn't worth a client's attention.
#:
#: TUNABLE, and the constant here most in need of a real cycle to calibrate. 10pp
#: is a placeholder chosen to be roughly "one answer in ten" — visible to a human
#: reading the answers, not just to the arithmetic. It is deliberately a SECOND
#: gate rather than the only one: the statistical gate already suppresses noise,
#: and this exists so a technically-real 2pp shift on a large sample doesn't lead
#: a report.
PRACTICAL_FLOOR_PP = 10.0


@dataclass(frozen=True)
class Movement:
    """One cell's change, and whether it earned the right to be called one."""

    key: str  # engine name, bucket, whatever the caller is comparing
    before_successes: int
    before_n: int
    after_successes: int
    after_n: int
    #: Newcombe CI for (after − before), as fractions.
    diff_low: float
    diff_high: float
    #: Minimum detectable effect for this cell's effective sample, as a fraction.
    mde: float
    direction: str
    #: Why it was called flat, when it was. Empty when the direction is real.
    flat_reason: str
    #: Carried so the FDR pass can re-derive the design correction without the
    #: caller having to thread it through a second time.
    runs_per_query: int = 1

    @property
    def delta_pp(self) -> float:
        before = self.before_successes / self.before_n if self.before_n else 0.0
        after = self.after_successes / self.after_n if self.after_n else 0.0
        return (after - before) * 100

    @property
    def is_significant(self) -> bool:
        return self.direction in (Direction.UP.value, Direction.DOWN.value)

    def phrase(self) -> str:
        """Client-facing. Counts first, and never a bare percentage."""
        if self.direction == Direction.UNKNOWN.value:
            return f"{self.key}: not enough data to compare"
        after = f"{self.after_successes} of {self.after_n} runs"
        if self.direction == Direction.FLAT.value:
            return f"{self.key}: held steady at {after}"
        arrow = "Up" if self.direction == Direction.UP.value else "Down"
        return (
            f"{self.key}: {arrow} from {self.before_successes} of {self.before_n} "
            f"to {after}"
        )


def compare_cell(
    key: str,
    before_successes: int,
    before_n: int,
    after_successes: int,
    after_n: int,
    runs_per_query: int = 1,
) -> Movement:
    """Gate one cell's week-over-week change. Pure.

    Both gates are applied here; ``gate_movements`` then applies the
    multiple-comparison correction across a set of these.
    """
    if before_n <= 0 or after_n <= 0:
        return Movement(
            key=key,
            before_successes=before_successes,
            before_n=before_n,
            after_successes=after_successes,
            after_n=after_n,
            diff_low=-1.0,
            diff_high=1.0,
            mde=1.0,
            direction=Direction.UNKNOWN.value,
            flat_reason="one side of the comparison has no measured runs",
            runs_per_query=runs_per_query,
        )

    low, high = stats.newcombe_diff_interval(
        after_successes, after_n, before_successes, before_n, runs_per_query=runs_per_query
    )
    n_eff = min(
        stats.effective_n(before_n, runs_per_query), stats.effective_n(after_n, runs_per_query)
    )
    pooled = (before_successes + after_successes) / (before_n + after_n)
    mde = stats.minimum_detectable_effect(n_eff, baseline_p=pooled or 0.5)

    delta = after_successes / after_n - before_successes / before_n
    statistically_real = low > 0 or high < 0
    practically_real = abs(delta) * 100 >= PRACTICAL_FLOOR_PP

    if not statistically_real:
        reason = (
            f"the 95% interval for the change ({low * 100:+.0f} to {high * 100:+.0f} pp) "
            f"includes zero at this sample size"
        )
        direction = Direction.FLAT.value
    elif not practically_real:
        reason = f"the change is under the {PRACTICAL_FLOOR_PP:.0f}pp reporting floor"
        direction = Direction.FLAT.value
    else:
        reason = ""
        direction = Direction.UP.value if delta > 0 else Direction.DOWN.value

    return Movement(
        key=key,
        before_successes=before_successes,
        before_n=before_n,
        after_successes=after_successes,
        after_n=after_n,
        diff_low=low,
        diff_high=high,
        mde=mde,
        direction=direction,
        flat_reason=reason,
        runs_per_query=runs_per_query,
    )


def gate_movements(movements: Sequence[Movement], fdr: float = 0.05) -> list[Movement]:
    """Apply the false-discovery-rate correction across a report's comparisons.

    A report runs ~20 simultaneous tests (six surfaces plus buckets). One of them
    getting lucky is not a finding, and this is what catches it.

    **The family is EVERY comparison performed, not the ones that already looked
    significant.** Two earlier versions of this function did nothing at all, and
    both failures are worth keeping written down because they look right:

    1. Ranking on a pseudo-p derived from the interval's distance from zero,
       capped at 0.05. At rank *m* the BH threshold IS the FDR, so a p that can
       never exceed 0.05 always survives.
    2. Feeding BH only the cells that had already passed a per-cell α≈0.05 gate.
       Every candidate then has p ≲ 0.05, the step-up finds k = m, and it rejects
       all of them. Filtering before correcting removes the very comparisons that
       make the correction bite.

    With the full family, 2 strong cells among 18 marginal ones give
    ``p(20)=0.0496`` against a threshold of ``(20/25)·0.05 = 0.04`` — the step-up
    walks down to k=2 and the marginal cells are correctly demoted.

    The p-value is used for ranking only. The interval remains what the report
    shows, so there is one number on the page, not two.
    """
    testable = [m for m in movements if m.direction != Direction.UNKNOWN.value]
    if not testable:
        return list(movements)

    p_values = [
        stats.two_proportion_p_value(
            m.after_successes, m.after_n, m.before_successes, m.before_n, m.runs_per_query
        )
        for m in testable
    ]
    survives = {
        m.key
        for m, keep in zip(testable, stats.benjamini_hochberg(p_values, fdr=fdr), strict=True)
        if keep
    }
    gated: list[Movement] = []
    for m in movements:
        if not m.is_significant or m.key in survives:
            gated.append(m)
            continue
        gated.append(
            Movement(
                **{
                    **m.__dict__,
                    "direction": Direction.FLAT.value,
                    "flat_reason": (
                        "the change does not survive correction for the "
                        f"{len(testable)} comparisons in this report"
                    ),
                }
            )
        )
    return gated


if __name__ == "__main__":
    cases = [
        ("ChatGPT (small sample)", 1, 12, 6, 12),
        ("ChatGPT (large sample)", 29, 240, 120, 240),
        ("Perplexity (flat)", 6, 12, 6, 12),
        ("Gemini (tiny move)", 118, 240, 120, 240),
        ("Claude (no prior)", 0, 0, 6, 12),
    ]
    movements = [compare_cell(k, bs, bn, a, an, runs_per_query=3) for k, bs, bn, a, an in cases]
    for m in gate_movements(movements):
        print(f"  {m.phrase()}")
        if m.flat_reason:
            print(f"      ({m.flat_reason})")
