"""How often the judge agrees with a careful human — and the gate that follows.

"The judge said so" cannot be the evidentiary standard for a Critical finding
shown to a CMO, so the report publishes an agreement rate
(``docs/audit-packaging-spec.md`` P4-T1). This module computes it.

**Gwet's AC1 is the headline, not Cohen's kappa.** This is the single most
important metric decision here and it is counterintuitive.

Kappa penalises agreement in proportion to class imbalance. Most answers carry no
flags, so expected chance agreement is already very high and kappa reads as
mediocre at near-perfect real agreement — the *kappa paradox*. A documented case
has two reviewers at **97.5% raw agreement** scoring **kappa 0.747** and
**AC1 0.972**. Reporting the kappa would say the judge is unreliable when it
agrees with a human almost every time, and the natural response to that number is
to "fix" a judge that is not broken.

**Report AC1 alongside raw agreement, kappa, and the full confusion matrix.**
Never one number alone: AC1 on its own hides *where* the disagreements are, and
the confusion matrix is what turns "88%" into "it systematically calls Critical
things High".

**But the production gate is per-class recall on Critical/High, not any of the
above.** A judge that answers "no flag" to everything scores 95%+ aggregate
accuracy against a 5%-prevalence set with **zero recall on the class that
matters**. Aggregate accuracy cannot see that; :func:`gate_critical_high_recall`
can.

Hand-rolled rather than importing ``irrCAC``: both formulas are a dozen lines of
closed-form arithmetic, and this way the module is fully typed and exhaustively
testable — the same trade already made in :mod:`src.pipeline.stats`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "CRITICAL_HIGH_RECALL_FLOOR",
    "NO_FLAG",
    "AgreementReport",
    "agreement",
    "gate_critical_high_recall",
    "required_items_for_minority",
]

#: The label for "this answer carries no client accuracy error". A real class,
#: not an absence — the confusion matrix needs it to show over-flagging.
NO_FLAG = "none"

#: Per-class recall floor for the two tiers a client acts on.
#:
#: TUNABLE. 0.90 is the spec's figure. It is a floor on RECALL specifically
#: because the expensive error is a missed Critical, not a spurious one: a false
#: Critical is embarrassing and gets caught in review, a missed one ships as
#: silence.
CRITICAL_HIGH_RECALL_FLOOR = 0.90


@dataclass(frozen=True)
class AgreementReport:
    """Judge-vs-human agreement. Read every field; no single number is honest."""

    n: int
    #: Categories observed, in a stable order.
    labels: tuple[str, ...]
    #: ``(human_label, judge_label) -> count``. The thing that shows *where* the
    #: judge is wrong, which a scalar never can.
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)
    raw_agreement: float = 0.0
    gwet_ac1: float = 0.0
    cohens_kappa: float = 0.0
    per_class_recall: dict[str, float] = field(default_factory=dict)
    per_class_precision: dict[str, float] = field(default_factory=dict)
    #: How many gold items carry each label. The denominator behind every recall
    #: above, and the number that says whether a recall figure means anything —
    #: one Critical in the set makes its recall move in 100-point steps.
    support: dict[str, int] = field(default_factory=dict)

    def headline(self) -> str:
        """One line for the methodology section. AC1 first, denominator always."""
        if self.n == 0:
            return "Judge agreement has not been measured against a gold set."
        return (
            f"Across {self.n} hand-labeled answers the judge agreed with the human "
            f"reviewer on {self.raw_agreement:.0%} (Gwet's AC1 {self.gwet_ac1:.2f})."
        )

    def is_underpowered(self, label: str, minimum: int = 20) -> bool:
        """Whether a class has too few examples for its recall to mean anything.

        At 3 gold flags one item moves recall by 33 points. Two identical runs of
        the real Fort set returned precision 29% then 43% on the same inputs —
        that is not judge instability, it is a sample too small to measure with.
        """
        return self.support.get(label, 0) < minimum


def agreement(pairs: Sequence[tuple[str, str]]) -> AgreementReport:
    """Chance-corrected agreement over ``(human_label, judge_label)`` pairs. Pure.

    One label per item, so every metric here is well defined. For accuracy flags
    that label is the item's WORST severity (or :data:`NO_FLAG`) — an answer with
    a Critical and a Low is a Critical, because that is what a reader acts on.
    """
    n = len(pairs)
    if n == 0:
        return AgreementReport(n=0, labels=())

    labels = tuple(sorted({label for pair in pairs for label in pair}))
    confusion = Counter(pairs)
    observed = sum(count for (human, judge), count in confusion.items() if human == judge)
    raw = observed / n

    human_marginal = Counter(human for human, _ in pairs)
    judge_marginal = Counter(judge for _, judge in pairs)

    return AgreementReport(
        n=n,
        labels=labels,
        confusion=dict(confusion),
        raw_agreement=raw,
        gwet_ac1=_gwet_ac1(raw, labels, human_marginal, judge_marginal, n),
        cohens_kappa=_cohens_kappa(raw, labels, human_marginal, judge_marginal, n),
        per_class_recall={
            label: _rate(confusion.get((label, label), 0), human_marginal.get(label, 0))
            for label in labels
        },
        per_class_precision={
            label: _rate(confusion.get((label, label), 0), judge_marginal.get(label, 0))
            for label in labels
        },
        support=dict(human_marginal),
    )


def _rate(numerator: int, denominator: int) -> float:
    """A rate with no denominator is 0.0, not 1.0.

    The opposite convention flatters exactly the case that matters: a class with
    no gold examples would score perfect recall, and a gold set missing Criticals
    would report the judge as flawless on Criticals.
    """
    return numerator / denominator if denominator else 0.0


def _gwet_ac1(
    raw: float,
    labels: Sequence[str],
    human: Counter[str],
    judge: Counter[str],
    n: int,
) -> float:
    """AC1 = (p_a − p_e) / (1 − p_e), with Gwet's chance term.

    The difference from kappa is entirely in ``p_e``. Gwet estimates the chance of
    agreement as the probability that at least one rater was guessing, which does
    NOT explode as one category comes to dominate — so a 95%-prevalence "no flag"
    class stops making genuine agreement look accidental.
    """
    categories = len(labels)
    if categories < 2:
        return 1.0  # everything in one class: no disagreement is possible
    chance = sum(
        _pi(label, human, judge, n) * (1 - _pi(label, human, judge, n)) for label in labels
    ) / (categories - 1)
    return (raw - chance) / (1 - chance) if chance < 1 else 1.0


def _cohens_kappa(
    raw: float,
    labels: Sequence[str],
    human: Counter[str],
    judge: Counter[str],
    n: int,
) -> float:
    """Reported ALONGSIDE AC1, never instead of it — see the module docstring."""
    chance = sum((human.get(label, 0) / n) * (judge.get(label, 0) / n) for label in labels)
    return (raw - chance) / (1 - chance) if chance < 1 else 1.0


def _pi(label: str, human: Counter[str], judge: Counter[str], n: int) -> float:
    """Gwet's π: a label's share averaged across both raters."""
    return (human.get(label, 0) + judge.get(label, 0)) / (2 * n)


def gate_critical_high_recall(
    report: AgreementReport,
    floor: float = CRITICAL_HIGH_RECALL_FLOOR,
    tiers: Sequence[str] = ("critical", "high"),
) -> list[str]:
    """Reasons the judge is not fit to ship. Empty list means it passes.

    Recall, not accuracy: an all-negative judge scores 95%+ aggregate against a
    5%-prevalence set with zero recall on the tiers a client acts on.

    An UNDER-POWERED tier fails too, and that is deliberate. A tier with three
    gold examples cannot demonstrate 0.90 recall no matter what it scores, and
    "we could not measure it" must not read the same as "it passed". The current
    Fort set carries three gold flags; two identical runs returned recall 67% then
    100% on the same inputs.
    """
    failures: list[str] = []
    for tier in tiers:
        support = report.support.get(tier, 0)
        if support == 0:
            failures.append(f"{tier}: no gold examples — recall is unmeasured, not passing")
            continue
        if report.is_underpowered(tier):
            failures.append(
                f"{tier}: only {support} gold examples — too few to demonstrate "
                f"{floor:.0%} recall (one item moves it {1 / support:.0%})"
            )
        recall = report.per_class_recall.get(tier, 0.0)
        if recall < floor:
            failures.append(f"{tier}: recall {recall:.2f} is below the {floor:.2f} floor")
    return failures


def required_items_for_minority(
    target_minority: int, base_rate: float, *, oversampled: bool = False
) -> int:
    """How many labeled items you need for ``target_minority`` rare-class examples.

    **Size the gold set by the rare class, not the total.** At a ~6% Critical/High
    base rate, 50 traces gives ~3 minority examples, which is useless; 200 gives
    ~12. The knob is not "how many traces can we label" but "how many Criticals do
    we need to see".

    ``oversampled=True`` returns the target itself: if sampling is stratified to
    pull minority items deliberately — which it should be, since random sampling
    under-represents exactly the cases that break judges — the total is whatever
    you choose, and this function has nothing to say.
    """
    if oversampled:
        return target_minority
    if base_rate <= 0:
        raise ValueError("base_rate must be positive to size a random sample")
    return int(-(-target_minority // base_rate))  # ceil


if __name__ == "__main__":
    # The kappa paradox, reproduced: near-perfect agreement on a rare class.
    pairs = (
        [("none", "none")] * 190
        + [("critical", "critical")] * 5
        + [("none", "critical")] * 2
        + [("critical", "none")] * 3
    )
    report = agreement(pairs)
    print(report.headline())
    print(
        f"  raw {report.raw_agreement:.3f}  AC1 {report.gwet_ac1:.3f}  "
        f"kappa {report.cohens_kappa:.3f}"
    )
    print(f"  critical recall {report.per_class_recall['critical']:.2f} "
          f"(support {report.support['critical']})")
    for reason in gate_critical_high_recall(report):
        print(f"  GATE FAIL: {reason}")
    print(f"\nFor 20 Criticals at a 6% base rate: {required_items_for_minority(20, 0.06)} items")
