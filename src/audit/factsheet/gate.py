"""Which accuracy flags a sheet is allowed to put in front of a stranger (plan §8).

The standing rule this enforces: a fact sheet is the reference the judge measures
answers against, so a wrong line in it does not produce a missing finding — it
produces a **false accusation in a document we send a stranger**. An
auto-generated sheet that nobody has confirmed is the highest-risk input the
system has, and the teaser is its highest-risk output.

**Why this gates on the SHEET and not on the claim.** A per-claim gate is the
one the §8 table reads like it wants, and it cannot be built without breaking a
hard invariant. ``csv_loader._build_fact_sheet`` flattens the sheet to
``"{key}: {value}"`` lines, so the judge never sees ``verification``,
``source_url`` or ``claim_id``; it therefore cannot stamp a tier on a flag, and
``AccuracyFlag`` (``storage/models.py``) has nowhere to carry one. Every route to
adding it — a new tool-schema field, or embedding claim ids in the sheet text —
changes the judge prompt or the sheet, both of which are inside the judge cache
key (geo-dev: *"judge cache keys are sacred"*) and would invalidate every stored
verdict. Matching ``flag.reality`` back to a claim by string similarity would
avoid that, but it puts a fuzzy heuristic in charge of what gets sent to a
prospect, which is exactly the wrong place for one.

So permissions are read off the document, as :attr:`FactSheet.verification_tier`
already says they are: the sheet is only as confirmed as its least-confirmed
line. That is coarser than §8's table and it fails SAFE — one unconfirmed claim
restricts the whole sheet's flags, never the reverse.

Nothing here decides whether a flag is *true*; the judge already did. This
decides whether we are entitled to say it yet.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from src.audit.factsheet.models import Verification
from src.storage.models import Severity

__all__ = ["SENDABLE_SEVERITIES", "may_send_flag", "sendable_flags"]

FlagT = TypeVar("FlagT")


def _severity_attr(flag: Any) -> str:
    """Default severity reader: both flag shapes expose a ``.severity`` string."""
    return str(getattr(flag, "severity", ""))

# §8, as a table. The key is the sheet's WEAKEST verification tier; the value is
# the severities a flag may carry and still appear in something we send.
#
# `public_source_only` is one quoted public source and nothing more. §8 allows it
# low/med "and only from the client's own site" — that second condition is
# satisfied structurally rather than checked here, because `extract.build_sheet`
# crawls exactly the client's domain and the lead form they filled in. If an
# off-site layer (F7, L3) ever feeds claims into a sheet, this comment stops
# being true and the condition needs a real check.
#
# HIGH is absent from the unconfirmed tier deliberately, and it is SUPPRESSED
# rather than downgraded: re-labelling a high-severity claim as medium would put
# it in front of a stranger wearing a softer label, which is worse than silence.
SENDABLE_SEVERITIES: dict[Verification, frozenset[Severity]] = {
    Verification.PUBLIC_SOURCE_ONLY: frozenset({Severity.LOW, Severity.MED}),
    Verification.CROSS_CONFIRMED: frozenset({Severity.LOW, Severity.MED, Severity.HIGH}),
    Verification.CLIENT_CONFIRMED: frozenset({Severity.LOW, Severity.MED, Severity.HIGH}),
}


def may_send_flag(tier: Verification, severity: str) -> bool:
    """Whether a flag of ``severity`` may be sent, given the sheet's weakest ``tier``.

    ``severity`` is the raw string off :class:`~src.storage.models.AccuracyFlag`,
    which is a value not an enum — an unrecognised one is refused rather than
    coerced. A severity this code does not understand is not evidence that the
    flag is harmless, and the audit-packaging spec (P0-T2) intends to add a
    CRITICAL tier: until it is in :class:`Severity` and in the table above, a
    flag carrying it must not slip through as "not in the deny list".
    """
    try:
        parsed = Severity(severity)
    except ValueError:
        return False
    return parsed in SENDABLE_SEVERITIES[tier]


def sendable_flags(
    flags: Sequence[FlagT],
    tier: Verification,
    *,
    severity_of: Callable[[FlagT], str] = _severity_attr,
) -> list[FlagT]:
    """The subset of ``flags`` this sheet is entitled to send.

    Generic over the flag type because two shapes exist for the same thing —
    :class:`~src.storage.models.AccuracyFlag` in the pipeline and ``FlagRow`` in
    the report payload — and duplicating the policy for each is how the two would
    drift. ``severity_of`` defaults to reading a ``.severity`` attribute.
    """
    return [f for f in flags if may_send_flag(tier, severity_of(f))]
