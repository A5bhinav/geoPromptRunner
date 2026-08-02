"""Which judged cells a human looks at, and what happens when they disagree.

Two jobs the spec keeps separate and this module keeps together because they
share their sampling logic:

**Building a gold set** (P4-T1). Size it by the RARE class, not the total: at a
~6% Critical/High base rate a random 50 traces gives ~3 minority examples, which
measures nothing. Stratify deliberately across "judge said Critical/High",
"judge said no-flag", and boundary cases — random sampling under-represents
exactly the cases that break judges.

**Routine QA** (P4-T2). Every Critical/High gets reviewed, every finding whose
lifecycle status changed gets reviewed, a stratified slice of everything else,
and — the one people leave out — a random sample of cells where the judge found
NOTHING. Without that last stratum the queue can only ever find false positives,
and the expensive error here is the false negative.

**Reviewer disagreement is recorded, never silently resolved.** Both labels are
kept with the ``prompt_fingerprint`` in force at judge time, which is what turns
"the judge feels off lately" into a queryable regression rather than a feeling.
The documented tie-break for a client-facing product escalates to the MORE severe
label when two reviewers differ — a false Critical is embarrassing and gets
caught in review; a missed one ships as silence.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from src.pipeline.severity import SEVERITY_RANK

__all__ = [
    "SamplingPolicy",
    "DEFAULT_POLICY",
    "ReviewStratum",
    "ReviewCandidate",
    "sample_for_review",
    "stratify_gold_candidates",
    "ReviewOutcome",
    "ReviewRecord",
    "reconcile",
]


class ReviewStratum(StrEnum):
    """Why a cell is in the queue. Recorded so coverage can be audited per stratum."""

    SEVERE = "severe"  # Critical or High — always reviewed
    LIFECYCLE_CHANGED = "lifecycle_changed"  # resolved / regressed — always reviewed
    ROUTINE = "routine"  # a stratified slice of the rest
    NO_FINDING = "no_finding"  # the false-negative probe
    BOUNDARY = "boundary"  # near-threshold; gold-set only


@dataclass(frozen=True)
class SamplingPolicy:
    """The coverage contract. Rates are fractions of their own stratum."""

    routine_rate: float = 0.20
    no_finding_rate: float = 0.05
    #: Ceiling on one cycle's queue. A guarantee nobody can meet is not a
    #: guarantee — but truncation is REPORTED (`SampleResult.dropped`), never
    #: silent, because a silently-capped queue reads as full coverage.
    max_items: int = 200


DEFAULT_POLICY = SamplingPolicy()


@dataclass(frozen=True)
class ReviewCandidate:
    """One judged cell, with everything the sampler needs to place it."""

    cell_id: str  # stable: "{run_id}:{query_id}:{engine}:{run_index}"
    severity: str  # four-level; NO_FLAG-equivalent is "" or "none"
    lifecycle_status: str = ""  # new | persisting | resolved | regressed
    theme: str = ""

    @property
    def is_severe(self) -> bool:
        return self.severity in ("critical", "high")

    @property
    def has_finding(self) -> bool:
        return bool(self.severity) and self.severity != "none"


@dataclass(frozen=True)
class SampleResult:
    """The queue, plus what it did not cover. Both, always."""

    items: list[tuple[str, str]] = field(default_factory=list)  # (cell_id, stratum)
    #: Cells the cap excluded, by stratum. A queue that silently truncates reads
    #: as full coverage, which is the one thing a QA process may not do.
    dropped: dict[str, int] = field(default_factory=dict)

    def of(self, stratum: str) -> list[str]:
        return [cell for cell, s in self.items if s == stratum]


def _deterministic_rank(cell_id: str, salt: str) -> float:
    """A stable pseudo-random score in [0,1) for one cell.

    Hash-based rather than ``random.sample`` so the queue is REPRODUCIBLE: the
    same cycle sampled twice gives the same queue, which is what lets a reviewer
    resume, and what stops "re-roll until it's short" being possible.
    """
    digest = hashlib.sha256(f"{salt}\x1f{cell_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def sample_for_review(
    candidates: Sequence[ReviewCandidate],
    policy: SamplingPolicy = DEFAULT_POLICY,
    salt: str = "",
) -> SampleResult:
    """Build one cycle's review queue. Deterministic for a given ``salt``.

    The two 100% strata are taken first and are never truncated: if the cap would
    cut into them the cap is the wrong number, and dropping a Critical from review
    to make room for a routine sample is exactly backwards.
    """
    severe: list[str] = []
    changed: list[str] = []
    routine: list[str] = []
    no_finding: list[str] = []

    for candidate in candidates:
        if candidate.is_severe:
            severe.append(candidate.cell_id)
        elif candidate.lifecycle_status in ("resolved", "regressed"):
            changed.append(candidate.cell_id)
        elif candidate.has_finding:
            routine.append(candidate.cell_id)
        else:
            no_finding.append(candidate.cell_id)

    picked_routine = _sample(routine, policy.routine_rate, salt + "routine")
    picked_none = _sample(no_finding, policy.no_finding_rate, salt + "none")

    items: list[tuple[str, str]] = []
    dropped: dict[str, int] = {}
    # Mandatory strata first, and exempt from the cap.
    items += [(c, ReviewStratum.SEVERE.value) for c in severe]
    items += [(c, ReviewStratum.LIFECYCLE_CHANGED.value) for c in changed]

    remaining = max(0, policy.max_items - len(items))
    for stratum, picks in (
        (ReviewStratum.ROUTINE.value, picked_routine),
        (ReviewStratum.NO_FINDING.value, picked_none),
    ):
        take = picks[:remaining]
        items += [(c, stratum) for c in take]
        if len(take) < len(picks):
            dropped[stratum] = len(picks) - len(take)
        remaining -= len(take)

    return SampleResult(items=items, dropped=dropped)


def _sample(cells: Sequence[str], rate: float, salt: str) -> list[str]:
    """A deterministic ``rate`` share of ``cells``, at least one if any exist.

    "At least one" matters: a 5% rate over 12 no-finding cells rounds to zero, and
    a stratum that silently samples nothing is a stratum that does not exist. A
    non-empty population always contributes.
    """
    if not cells or rate <= 0:
        return []
    target = max(1, round(len(cells) * rate))
    return sorted(cells, key=lambda c: _deterministic_rank(c, salt))[:target]


def stratify_gold_candidates(
    candidates: Sequence[ReviewCandidate],
    per_stratum: int = 20,
    salt: str = "gold",
) -> dict[str, list[str]]:
    """Pick gold-set items by stratum, oversampling the rare class deliberately.

    Random sampling under-represents exactly the cases that break judges, so this
    takes ``per_stratum`` from each of: what the judge called severe, what it
    called nothing, and the boundary (``med``) cases where its own uncertainty
    concentrates. ``per_stratum=20`` is the spec's target for a class whose recall
    you intend to quote.

    Returns fewer than asked where the population is smaller — and the caller must
    check, because a stratum with 3 items cannot support a recall claim
    (:func:`src.pipeline.agreement.gate_critical_high_recall` refuses it).
    """
    buckets: dict[str, list[str]] = {
        ReviewStratum.SEVERE.value: [],
        ReviewStratum.NO_FINDING.value: [],
        ReviewStratum.BOUNDARY.value: [],
    }
    for candidate in candidates:
        if candidate.is_severe:
            buckets[ReviewStratum.SEVERE.value].append(candidate.cell_id)
        elif not candidate.has_finding:
            buckets[ReviewStratum.NO_FINDING.value].append(candidate.cell_id)
        else:
            buckets[ReviewStratum.BOUNDARY.value].append(candidate.cell_id)

    return {
        stratum: sorted(cells, key=lambda c: _deterministic_rank(c, salt + stratum))[:per_stratum]
        for stratum, cells in buckets.items()
    }


# --- reviewer disagreement ----------------------------------------------------


class ReviewOutcome(StrEnum):
    AGREED = "agreed"  # both reviewers matched the judge
    OVERRIDDEN = "overridden"  # both reviewers agreed, and differed from the judge
    ESCALATED = "escalated"  # the reviewers differed; the harsher label won


@dataclass(frozen=True)
class ReviewRecord:
    """One reviewed cell. Append-only; this is the audit trail, not a scratchpad.

    Both reviewer labels are kept even when they agree. Recording only the
    reconciled answer throws away the disagreement RATE, which is the number that
    says whether the labels themselves are trustworthy — and a gold set built by
    two people who never disagree is usually one where the second anchored on the
    first.
    """

    cell_id: str
    stratum: str
    judge_label: str
    reviewer_a: str
    reviewer_b: str
    final_label: str
    outcome: str
    #: The judge prompt in force WHEN THE CELL WAS JUDGED. Without it, "the judge
    #: feels off lately" cannot become a queryable regression — you cannot tell a
    #: prompt change from a model change from noise.
    prompt_fingerprint: str
    reviewed_at: str
    note: str = ""

    @property
    def reviewers_disagreed(self) -> bool:
        return self.reviewer_a != self.reviewer_b


def reconcile(
    cell_id: str,
    stratum: str,
    judge_label: str,
    reviewer_a: str,
    reviewer_b: str,
    prompt_fingerprint: str,
    reviewed_at: str,
    note: str = "",
) -> ReviewRecord:
    """Resolve two blind labels into one, and record how.

    **Escalate to the more severe label when reviewers differ.** For a
    client-facing product the errors are not symmetric: a false Critical is
    embarrassing and gets caught at the next review, a missed one ships as
    silence. The tie-break is documented rather than left to whoever reconciles.

    Blind labelling before reconciliation is the property that matters and this
    function cannot enforce it — it only sees the two labels. Anchoring on the
    judge's verdict, or on each other, is how a small team's gold set gets quietly
    contaminated.
    """
    if reviewer_a == reviewer_b:
        final = reviewer_a
        outcome = ReviewOutcome.AGREED if final == judge_label else ReviewOutcome.OVERRIDDEN
    else:
        final = min(
            (reviewer_a, reviewer_b),
            key=lambda label: SEVERITY_RANK.get(label, len(SEVERITY_RANK)),
        )
        outcome = ReviewOutcome.ESCALATED
    return ReviewRecord(
        cell_id=cell_id,
        stratum=stratum,
        judge_label=judge_label,
        reviewer_a=reviewer_a,
        reviewer_b=reviewer_b,
        final_label=final,
        outcome=outcome.value,
        prompt_fingerprint=prompt_fingerprint,
        reviewed_at=reviewed_at,
        note=note,
    )


if __name__ == "__main__":
    pool = (
        [ReviewCandidate(f"c{i}", "critical") for i in range(3)]
        + [ReviewCandidate(f"h{i}", "high") for i in range(5)]
        + [ReviewCandidate(f"m{i}", "med", "resolved") for i in range(4)]
        + [ReviewCandidate(f"l{i}", "low") for i in range(40)]
        + [ReviewCandidate(f"n{i}", "") for i in range(200)]
    )
    result = sample_for_review(pool)
    print(f"queue: {len(result.items)} of {len(pool)} cells")
    for stratum in ReviewStratum:
        picked = result.of(stratum.value)
        if picked:
            print(f"  {stratum.value:18s} {len(picked)}")
    print(f"  dropped: {result.dropped or 'none'}")
    print()
    record = reconcile("c0", "severe", "high", "critical", "high", "fp-abc", "2026-08-02")
    print(f"reviewers differed -> {record.final_label} ({record.outcome})")
