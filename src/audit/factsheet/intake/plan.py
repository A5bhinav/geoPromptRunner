"""The ordered plan of cards to ask.

Under the branched design this module had two jobs — route to a branch, then
trim the result back under a card budget. **It has neither now.** One spine of
seventeen is asked of every business, in registry order, and seventeen is both
ceiling and the floor. What is left is a seam: `build_plan` stays as the single
place that decides what a session asks, so a future rule (drop a card the crawl
already settled, surface a disagreement first) has somewhere to land that is not
the API.

Why the routing went, in one line: `business_kind` picked a local branch or a
product branch, and the businesses that are neither — an agency, a restaurant, a
clinic, a nonprofit, a marketplace — had no branch at all. It is now the
for-instance line and the query allocation, and nothing structural.

The session still gets SHORTER than seventeen decisions, just not by asking fewer
questions: the two batch-confirm cards carry four facts each, so a crawl that
found JSON-LD collapses eight facts into two taps.

Pure. No storage, no clock.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.audit.factsheet.intake.questions import REGISTRY, IntakeQuestion

__all__ = ["Prefill", "build_plan"]

#: ``key -> {"value": str, "source_url": str, "confidence": str}``. Built by the
#: API from the draft sheet's existing claims, so the owner confirms what we
#: found rather than retyping it.
Prefill = Mapping[str, Mapping[str, object]]


def build_plan(
    *,
    prefill: Prefill | None = None,
    answers: Mapping[str, object] | None = None,
) -> list[IntakeQuestion]:
    """The ordered cards for one session: all seventeen, in registry order.

    ``prefill`` and ``answers`` are accepted and currently unused. They are not
    dead weight — they are the two inputs any future shortening rule would need,
    and every caller already has them to hand. Taking them now means such a rule
    is a change to this function rather than a change to every call site.

    NOTHING IS EVER DROPPED FOR LENGTH. The old trimmer refused to touch
    negative-first or unskippable cards precisely because dropping "what don't
    you do?" to fit a budget trades the highest-yield question in the set for a
    cosmetic one. With one spine there is no budget to fit, so the refusal is
    total rather than conditional.
    """
    _ = prefill, answers
    return list(REGISTRY)
