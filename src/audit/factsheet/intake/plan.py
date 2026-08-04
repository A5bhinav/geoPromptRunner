"""Registry + prefill + business kind → the ordered plan of cards to ask.

The registry says what CAN be asked. This says what WILL be, for one business,
given what the crawl already found. Two jobs:

1. **Route.** Q-ID-01 picks the branch; a product business is never shown a
   licence card and a plumber is never shown a pricing-tiers card.
2. **Shorten.** The ceiling is eighteen cards and the median is thirteen. Not by
   asking faster — by asking less: a dimension the crawl already found collapses
   into a batch-confirm, and if a plan still runs long, the lowest-value cards
   come off the end rather than the owner being asked to grind through them.

Pure. No storage, no clock.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.audit.factsheet.intake.questions import (
    LOCAL_BRANCH,
    MAX_CARDS,
    PRODUCT_BRANCH,
    TAIL,
    TRUNK,
    IntakeQuestion,
)
from src.audit.factsheet.models import BusinessKind

__all__ = ["Prefill", "build_plan", "branch_for"]

#: ``key -> {"value": str, "source_url": str, "confidence": str}``. Built by the
#: API from the draft sheet's existing claims, so the owner confirms what we
#: found rather than retyping it.
Prefill = Mapping[str, Mapping[str, object]]


def branch_for(kind: BusinessKind) -> tuple[IntakeQuestion, ...]:
    return LOCAL_BRANCH if kind is BusinessKind.LOCAL_SERVICE else PRODUCT_BRANCH


def _condition_met(question: IntakeQuestion, answers: Mapping[str, object]) -> bool:
    if question.show_if is None:
        return True
    other_id, expected = question.show_if
    return str(answers.get(other_id, "")) == expected


def build_plan(
    *,
    business_kind: BusinessKind,
    prefill: Prefill | None = None,
    answers: Mapping[str, object] | None = None,
    forced: frozenset[str] = frozenset(),
) -> list[IntakeQuestion]:
    """The ordered cards for one session.

    ``forced`` are ids that must survive trimming whatever their drop rank —
    the API puts the extractor's recorded disagreements (``sheet.questions``)
    in here. A disagreement between two sources is the single best use of
    thirty seconds of the owner's attention: it is a fact we already know we
    have wrong, and they can settle it live.

    TRIMMING NEVER TOUCHES A NEGATIVE CARD OR AN UNSKIPPABLE ONE. Negatives are
    where the value is — dropping "what don't you do?" to fit a card budget
    would trade the highest-yield question on the sheet for a cosmetic one.
    """
    prefill = prefill or {}
    answers = answers or {}

    plan: list[IntakeQuestion] = []
    for question in (*TRUNK, *branch_for(business_kind), *TAIL):
        if question.branch is not None and question.branch is not business_kind:
            continue
        if not _condition_met(question, answers):
            continue
        plan.append(question)

    if len(plan) <= MAX_CARDS:
        return plan

    # Over budget. Drop highest rank first, and only from the genuinely optional
    # set: rank 0, unskippable, negative-first and forced cards all stay.
    droppable = [
        q
        for q in plan
        if q.drop_rank > 0
        and q.skippable
        and not q.negative_first
        and q.id not in forced
        # A card the crawl could not pre-fill AND that is optional by value is
        # the cheapest thing to lose. One the crawl DID pre-fill costs a tap.
        and not any(key in prefill for key in q.keys)
    ]
    droppable.sort(key=lambda q: q.drop_rank, reverse=True)

    doomed: set[str] = set()
    for question in droppable:
        if len(plan) - len(doomed) <= MAX_CARDS:
            break
        doomed.add(question.id)

    return [q for q in plan if q.id not in doomed]
