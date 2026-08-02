"""Confidence intervals for the rates the report sells.

At 3 runs × 6 surfaces over a 42-query set, per-engine weekly n is small enough
that a 50% mention rate has a Wilson 95% CI of roughly 25–75%. The report used to
present that as "50%". The standing rule is now the opposite: **no rate without
its denominator** — "7 of 12 runs", percentage secondary
(``.claude/skills/audit-packaging/SKILL.md``).

**Hand-rolled, zero new dependencies, deliberately.**
``statistics.NormalDist().inv_cdf()`` has been stdlib since 3.8 and every formula
here is a dozen lines of closed-form arithmetic. That buys a module that is fully
typed and exhaustively property-tested, which is worth more than importing
statsmodels (heavyweight — pulls pandas + scipy + patsy — and no official stubs)
for two functions.

Four things this module refuses to do, each for a reason:

- **Never Wald.** Unreliable near 0 and 1 at small n, which is precisely where
  this data lives.
- **Never CI overlap as a significance test.** Two 95% CIs can overlap while the
  difference is significant; the heuristic effectively tests against an interval
  ~√2 too wide. :func:`newcombe_diff_interval` computes the CI of the
  *difference* instead.
- **Never raw n.** Repeat runs of one prompt are correlated (published LLM-eval
  work reports ICC 0.48–0.86, mean 0.68), so pooling them as independent badly
  understates uncertainty. :func:`effective_n` is a strict widening — it can
  never make an interval falsely narrow.
- **Never a fixed threshold.** The old 15pp noise floor treated a well-sampled
  engine and a thin one identically. :func:`minimum_detectable_effect` computes
  the floor per cell.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist

__all__ = [
    "DEFAULT_ICC",
    "Interval",
    "wilson_interval",
    "newcombe_diff_interval",
    "design_effect",
    "effective_n",
    "icc_one_way",
    "minimum_detectable_effect",
    "benjamini_hochberg",
    "format_rate",
]

#: Fallback ICC when a run has too few prompts to estimate one from its own data.
#:
#: 0.68 is the mean of the 0.48–0.86 range reported in *Do Repetitions Matter?
#: Strengthening Reliability in LLM Evaluations* across repeated-run eval slices.
#: It is a placeholder for a measured value, not a constant of nature — compute
#: your own with :func:`icc_one_way` whenever there are ≥2 prompts, which there
#: always are on a real run. Being roughly right here is much better than
#: assuming independence, which is exactly wrong.
DEFAULT_ICC = 0.68


@dataclass(frozen=True)
class Interval:
    """A rate with everything needed to render it honestly.

    ``n`` is the REAL denominator read off the payload — never ``RUNS_PER_QUERY``,
    which defaults to 5 while stored runs vary. ``n_eff`` is what the interval was
    actually computed on.
    """

    successes: int
    n: int
    n_eff: float
    lower: float
    upper: float

    @property
    def point(self) -> float:
        """The observed rate. Meaningless without ``n``; never render it alone."""
        return self.successes / self.n if self.n else 0.0

    @property
    def is_measured(self) -> bool:
        """False when nothing was observed — render "insufficient data", not 0%."""
        return self.n > 0

    @property
    def width(self) -> float:
        return self.upper - self.lower


def wilson_interval(
    successes: float, n: float, confidence: float = 0.95, continuity: bool = True
) -> tuple[float, float]:
    """Wilson score CI for a proportion. Never degenerate at p=0 or p=1.

    ``n == 0`` returns ``(0.0, 1.0)`` — full uncertainty. That is deliberate and
    normative: it signals the report layer to say *"insufficient data"* rather
    than *"0%"*, which are opposite claims about a client.

    Both arguments are floats so a design-corrected sample can be passed in.
    **Scale both together** — ``interval`` does, and getting this wrong is not a
    subtle error: deflating ``n`` alone drives ``p_hat`` above 1 and produces an
    interval that says a 50% rate is somewhere between 47% and 100%.
    """
    if n <= 0:
        return (0.0, 1.0)
    if successes < 0:
        raise ValueError(f"successes={successes} is negative")
    if successes > n:
        raise ValueError(f"successes={successes} exceeds n={n}")

    p_hat = min(max(successes / n, 0.0), 1.0)
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    z2 = z * z

    def bound(p: float) -> tuple[float, float]:
        denom = 1 + z2 / n
        center = (p + z2 / (2 * n)) / denom
        margin = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
        return center - margin, center + margin

    if continuity:
        lo, _ = bound(max(p_hat - 1 / (2 * n), 0.0))
        _, hi = bound(min(p_hat + 1 / (2 * n), 1.0))
    else:
        lo, hi = bound(p_hat)
    return max(0.0, lo), min(1.0, hi)


def design_effect(runs_per_query: int, icc: float = DEFAULT_ICC) -> float:
    """Kish's ``DEFF = 1 + (m − 1)·ICC``. Always ≥ 1.

    ``m`` is runs-per-query, the cluster size: the K repeat runs of one prompt are
    the correlated cluster, not the queries.
    """
    m = max(1, runs_per_query)
    return 1.0 + (m - 1) * max(0.0, icc)


def effective_n(n: int, runs_per_query: int, icc: float = DEFAULT_ICC) -> float:
    """``n / DEFF`` — the independent-observation equivalent of ``n`` cells.

    Plug THIS into every interval, never raw n. At K=3 and ICC 0.68 it deflates a
    sample by ~2.4×, which is a large correction and the honest one: three runs of
    the same prompt are not three independent looks at the world.
    """
    return n / design_effect(runs_per_query, icc)


def icc_one_way(groups: Mapping[str, Sequence[float]]) -> float:
    """ICC(1) via one-way random-effects ANOVA, unbalanced-group corrected.

    ``groups`` maps prompt id -> that prompt's per-run 0/1 outcomes. Hand-rolled
    because ``pingouin.intraclass_corr`` pulls pandas + scipy + tabulate for one
    formula.

    Clamped to [0, 1]: a negative ICC is an artifact of small samples, and letting
    it through would *narrow* an interval, which is the one direction this
    correction must never move.
    """
    usable = {k: list(v) for k, v in groups.items() if v}
    k = len(usable)
    if k < 2:
        return DEFAULT_ICC
    all_vals = [v for vals in usable.values() for v in vals]
    n_total = len(all_vals)
    if n_total <= k:  # every group has one observation — nothing to decompose
        return DEFAULT_ICC
    grand = sum(all_vals) / n_total

    ms_b_num = ms_w_num = 0.0
    m_vals: list[int] = []
    for vals in usable.values():
        m = len(vals)
        m_vals.append(m)
        group_mean = sum(vals) / m
        ms_b_num += m * (group_mean - grand) ** 2
        ms_w_num += sum((v - group_mean) ** 2 for v in vals)

    df_b, df_w = k - 1, n_total - k
    ms_b = ms_b_num / df_b
    ms_w = ms_w_num / df_w if df_w > 0 else 0.0
    # Unbalanced correction: the average cluster size that makes the expected
    # mean squares come out right when groups differ in size.
    m0 = (sum(m_vals) - sum(m * m for m in m_vals) / sum(m_vals)) / df_b
    denom = ms_b + (m0 - 1) * ms_w
    if denom <= 0:
        return 0.0
    return min(1.0, max(0.0, (ms_b - ms_w) / denom))


def interval(
    successes: int,
    n: int,
    runs_per_query: int = 1,
    icc: float = DEFAULT_ICC,
    confidence: float = 0.95,
) -> Interval:
    """The whole story for one rate: count, denominator, and a design-corrected CI.

    The design correction scales the numerator and the denominator TOGETHER, so
    the point estimate is untouched and only the interval widens. That is what
    DEFF means — the same observed rate, known less precisely — and it is why the
    correction can never move a bound in the flattering direction.
    """
    if n <= 0:
        return Interval(successes=successes, n=0, n_eff=0.0, lower=0.0, upper=1.0)
    n_eff = effective_n(n, runs_per_query, icc)
    lower, upper = wilson_interval(successes * (n_eff / n), n_eff, confidence)
    return Interval(successes=successes, n=n, n_eff=n_eff, lower=lower, upper=upper)


def newcombe_diff_interval(
    x1: int,
    n1: int,
    x2: int,
    n2: int,
    runs_per_query: int = 1,
    icc: float = DEFAULT_ICC,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """CI for ``p1 − p2`` by Newcombe's hybrid score method.

    This is the significance test — *does the interval exclude zero* — and it
    replaces ``trend.is_real_move``'s single global threshold. The improvement is
    that it self-adjusts to each cell's actual n, so a cell with n=20 gets a more
    sensitive test than one with n=3 instead of both being judged against one
    noise floor.

    Fagerland/Lydersen/Laake rank Agresti–Min exact-unconditional highest for
    n<30 with Newcombe an acceptable alternative that is "relatively
    straightforward to calculate". Agresti–Min needs numerical optimization over a
    nuisance parameter; it is not worth it here.

    Takes RAW counts and applies the design effect itself, rather than asking the
    caller for ``n_eff``. That is deliberate: the version that took ``n_eff``
    invited passing a raw numerator alongside a deflated denominator, which
    silently produces nonsense (see :func:`wilson_interval`).
    """
    if n1 <= 0 or n2 <= 0:
        return (-1.0, 1.0)  # full uncertainty — no comparison is possible
    eff1, eff2 = effective_n(n1, runs_per_query, icc), effective_n(n2, runs_per_query, icc)
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson_interval(p1 * eff1, eff1, confidence, continuity=False)
    l2, u2 = wilson_interval(p2 * eff2, eff2, confidence, continuity=False)
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return max(-1.0, lower), min(1.0, upper)


def minimum_detectable_effect(
    n: float, baseline_p: float = 0.5, alpha: float = 0.05, power: float = 0.80
) -> float:
    """The smallest true difference this cell could reliably detect, as a fraction.

    Replaces the arbitrary 15pp floor. Computed per cell, so a thin surface is
    honestly held to a coarser standard than a well-sampled one rather than both
    being flattered by the same number.

    ``n <= 0`` returns 1.0: nothing short of a total reversal is detectable, which
    is the correct reading of no data.
    """
    if n <= 0:
        return 1.0
    nd = NormalDist()
    p = min(max(baseline_p, 0.0), 1.0)
    return (nd.inv_cdf(1 - alpha / 2) + nd.inv_cdf(power)) * math.sqrt(2 * p * (1 - p) / n)


def benjamini_hochberg(p_values: Sequence[float], fdr: float = 0.05) -> list[bool]:
    """Which of ~20 simultaneous tests survive at a false-DISCOVERY rate of ``fdr``.

    BH, not Bonferroni. A weekly report runs 6 surfaces × several buckets, and for
    an exploratory scan where under-flagging real movement is worse than a false
    positive that self-corrects next week, controlling the false discovery rate is
    the right frame — Bonferroni would suppress nearly everything at this many
    comparisons and this little data.

    Returns a mask in the caller's original order.
    """
    m = len(p_values)
    if m == 0:
        return []
    ordered = sorted(range(m), key=lambda i: p_values[i])
    threshold_rank = -1
    for rank, idx in enumerate(ordered, start=1):
        if p_values[idx] <= fdr * rank / m:
            threshold_rank = rank
    # Everything up to the LARGEST passing rank is rejected, including entries
    # that individually failed — that step is the whole point of the procedure.
    keep = {ordered[i] for i in range(threshold_rank)} if threshold_rank > 0 else set()
    return [i in keep for i in range(m)]


def format_rate(successes: int, n: int, unit: str = "runs") -> str:
    """The house format for a rate. **The only sanctioned way to render one.**

    "7 of 12 runs (58%)" — count first, percentage secondary and parenthetical. A
    bare percentage off a sample this size is the single most misleading thing the
    report could print, and this function exists so that rendering one requires
    deliberately not calling it.

    ``n == 0`` renders "insufficient data", never "0%".
    """
    if n <= 0:
        return "insufficient data"
    return f"{successes} of {n} {unit} ({successes / n:.0%})"


if __name__ == "__main__":
    for successes, n in ((6, 12), (0, 12), (12, 12), (1, 3)):
        iv = interval(successes, n, runs_per_query=3)
        print(
            f"{format_rate(successes, n):24s} "
            f"n_eff={iv.n_eff:5.1f}  95% CI [{iv.lower:.0%}, {iv.upper:.0%}]"
        )
    for label, (a, b) in (
        ("6/12 -> 9/12", ((6, 12), (9, 12))),
        ("30/240 -> 150/240", ((30, 240), (150, 240))),
    ):
        (x1, n1), (x2, n2) = b, a
        lo, hi = newcombe_diff_interval(x1, n1, x2, n2, runs_per_query=3)
        verdict = "significant" if lo > 0 or hi < 0 else "flat"
        print(f"\n{label} at K=3:  diff CI [{lo:+.0%}, {hi:+.0%}] -> {verdict}")
        print(
            f"  MDE at n_eff={effective_n(n1, 3):.1f}: "
            f"{minimum_detectable_effect(effective_n(n1, 3)):.0%}"
        )
