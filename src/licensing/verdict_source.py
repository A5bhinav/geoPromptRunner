"""Which judge produced a verdict, and who may be sold the result (LIC-T20).

**The problem this closes.** The prejudge flow writes verdicts into the
PRODUCTION cache keyspace — that is what makes "prejudge on the subscription,
then judge for $0" work at all. The consequence is that a subscription-judged
verdict and an API-judged verdict are byte-identical downstream: same table, same
shape, same report. Until this module existed, `verdict_source` appeared nowhere
in `src/` or `data/`, so nothing could tell them apart.

That is tolerable while the only readers are the two founders, who know what they
warmed. It stops being tolerable the moment an agency triggers a run: the agency
is paying for API-judged output, on the held-constant temp-0 model that
calibration was measured against, and has no way to check it got that.

**The rule.** Every verdict is tagged at write time. A report containing any
verdict that is not `api` may not be rendered for, or shared with, a non-platform
organization. Prejudge and Opus verdicts stay dev-only, and never feed calibration
or gold labels.

**Why UNKNOWN is refused too.** Verdicts written before this column existed carry
no source. They are not "probably fine" — the prejudge loop is the *normal* dev
workflow here, so an untagged verdict is more likely than not to be a
subscription verdict. For something a client pays for and an audit report
asserts, "cannot prove it was API-judged" has to mean "not deliverable". The
remedy is cheap and non-destructive: re-judge the run on the API, which retags
it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "API",
    "PREJUDGE",
    "OPUS_DEV",
    "UNKNOWN",
    "ALL_SOURCES",
    "DELIVERABLE_SOURCES",
    "DeliveryVerdict",
    "normalize_source",
    "check_delivery",
]

#: The held-constant API judge (`settings.JUDGE_MODEL`, temp 0). The only source
#: a paying client may receive, and the only one calibration may measure.
API: Final = "api"
#: Warmed on the Claude subscription via `scripts/judge_via_workflow.py`
#: (the `prejudge` skill). Free, a different model, dev iteration only.
PREJUDGE: Final = "prejudge"
#: Judged by Opus in a dev session. Same standing as PREJUDGE.
OPUS_DEV: Final = "opus_dev"
#: Written before verdicts were tagged. Refused — see the module docstring.
UNKNOWN: Final = "unknown"

ALL_SOURCES: Final = frozenset({API, PREJUDGE, OPUS_DEV, UNKNOWN})

#: The allow-list, deliberately a set of ONE. Written as a set so a future
#: second sanctioned source is a one-line change rather than a rewritten
#: predicate — but adding to it is a commercial decision, not a refactor.
DELIVERABLE_SOURCES: Final = frozenset({API})


def normalize_source(raw: object) -> str:
    """Coerce a stored value to a known source, defaulting to UNKNOWN.

    Anything unrecognised — NULL from a pre-LIC-T20 row, an empty string, a
    typo'd tag — becomes UNKNOWN rather than being trusted or dropped. Defaulting
    an unreadable tag to API would defeat the entire mechanism.
    """
    if not isinstance(raw, str):
        return UNKNOWN
    value = raw.strip().lower()
    return value if value in ALL_SOURCES else UNKNOWN


@dataclass(frozen=True)
class DeliveryVerdict:
    """Whether this run's verdicts may be delivered to this caller."""

    allowed: bool
    #: Empty when allowed. Otherwise a sentence naming WHICH sources blocked it —
    #: an operator seeing "refused" with no reason will assume the gate is broken
    #: and look for a way around it.
    reason: str
    #: Every distinct source found on the run, sorted. Reported either way, so a
    #: platform admin rendering a mixed run can see what they are looking at.
    sources: tuple[str, ...]


def check_delivery(sources: object, *, is_platform: bool) -> DeliveryVerdict:
    """Gate a render/share of a run whose verdicts came from ``sources``.

    ``sources`` is whatever was stored on the run (a list, a set, None on a run
    judged before tagging); it is normalised here so no caller has to.

    ``is_platform`` — the caller is a platform admin (a founder). They may render
    anything, because they are the ones who warmed it and the dev loop depends on
    it. Everyone else gets the gate. This is a capability check on the CALLER, not
    on a plan name.

    A run with NO verdicts at all is allowed through: an unjudged run is a
    perfectly ordinary thing to render (the report degrades to the measured
    numbers), and refusing it would break the mention-rate-only report.
    """
    found: set[str]
    if sources is None:
        found = set()
    elif isinstance(sources, str):
        found = {normalize_source(sources)}
    elif isinstance(sources, (list, tuple, set, frozenset)):
        found = {normalize_source(s) for s in sources}
    else:
        found = {UNKNOWN}

    ordered = tuple(sorted(found))
    if not found or is_platform:
        return DeliveryVerdict(True, "", ordered)

    disallowed = sorted(found - DELIVERABLE_SOURCES)
    if not disallowed:
        return DeliveryVerdict(True, "", ordered)

    detail = ", ".join(disallowed)
    return DeliveryVerdict(
        False,
        f"this report contains verdicts that were not produced by the API judge "
        f"({detail}), so it cannot be delivered to a client. Re-judge the run on "
        f"the API to retag it.",
        ordered,
    )
