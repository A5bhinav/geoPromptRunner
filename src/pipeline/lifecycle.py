"""new / persisting / resolved / regressed — the question that decides renewal.

A recurring report with no comparison is a status update. This module answers
*"did your recommendations do anything"* (``docs/audit-packaging-spec.md`` P2-T2).

**Telling a client something is fixed when an engine timed out is the worst
correctness failure available here**, so two guardrails are normative rather than
optional:

**A — the run-coverage gate.** A run counts as evidence only if it completed, met
a coverage floor, and used the same query set. Failing runs are stored immutably
but skipped ENTIRELY by the state machine — they never trigger ``resolved`` and
never break an absence streak. That is the answer to "not found vs not measured".

**B — the confirmation count.** ``resolved`` requires **two** consecutive
comparable-run absences. A single missed week stays ``persisting``. Tenable and
Qualys both mark Fixed after ONE absent scan; do not copy them. That works for
deterministic scanners, not for an LLM-judged pipeline where an absence may just
mean the model phrased things differently this time. The rule is borrowed from
monitoring flapping-detection instead.

Together these make the cutoff **state-based, not time-based**: a theme absent
three cycles and then returning is ``regressed`` only if it actually reached a
confirmed ``resolved``; otherwise it is continuation.

**Tracked at THEME level.** Cards are themes (see :mod:`src.pipeline.findings`),
and a theme is stable by construction — no registry needed for it to mean the
same thing next week. It is also the more useful claim: *"models still get your
pricing wrong, 3rd cycle running"* is something a client can act on, where *"this
exact sentence recurred"* is not.

Everything here is a pure function of stored data. Same inputs, same outputs,
always — which is what lets a report be re-rendered years later and agree with
what the client was shown.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "LifecycleStatus",
    "RESOLUTION_CONFIRMATION_RUNS",
    "MIN_COVERAGE_RATIO",
    "RunMeta",
    "CycleObservation",
    "LifecycleFact",
    "Accountability",
    "comparable_cycles",
    "compute_lifecycle",
    "accountability",
]


class LifecycleStatus(StrEnum):
    """What happened to a finding since last cycle."""

    NEW = "new"
    PERSISTING = "persisting"
    RESOLVED = "resolved"
    #: Outranks a same-severity NEW in the actions table. A fix that did not hold
    #: is worse news than a fresh problem: it means the recommendation was wrong
    #: or the change was reverted, and either way the client hears it first.
    REGRESSED = "regressed"


#: Consecutive comparable-run absences before a finding is called resolved.
#:
#: TUNABLE, and the one constant here most likely to want changing once a real
#: cadence exists. At 1 a single quiet week reads as a fix; at 3 a genuine fix
#: takes a month to acknowledge. 2 is the spec's recommendation.
RESOLUTION_CONFIRMATION_RUNS = 2

#: A run below this answered-cell ratio measured a different, smaller thing.
#:
#: TUNABLE. The gate exists because Albert Nahman's 2026-07-28 cycle produced
#: runs at 11/30 and 21/35 answered — comparing against one of those would report
#: the shortfall as the client losing visibility.
MIN_COVERAGE_RATIO = 0.95


@dataclass(frozen=True)
class RunMeta:
    """Just enough about a run to decide whether it may serve as evidence."""

    run_id: str
    run_date: str
    status: str
    #: Answered cells / attempted cells.
    coverage_ratio: float
    query_set_version: str

    @property
    def is_evidence(self) -> bool:
        """Whether the state machine may look at this run at all."""
        return self.status == "done" and self.coverage_ratio >= MIN_COVERAGE_RATIO


@dataclass(frozen=True)
class CycleObservation:
    """One cycle's run plus the set of themes that were open in it."""

    run: RunMeta
    themes: frozenset[str]


@dataclass(frozen=True)
class LifecycleFact:
    """A theme's status as of the latest cycle."""

    theme: str
    status: str
    #: The run where this theme was first observed, across every comparable cycle.
    first_seen_run: str
    first_seen_date: str
    #: Comparable cycles this theme has been open, counting the current one.
    #: Resets to 1 exactly on REGRESSED — a new episode, not a continuation.
    cycles_open: int
    #: Consecutive comparable cycles it has been absent without reaching RESOLVED.
    consecutive_absences: int


@dataclass(frozen=True)
class Accountability:
    """The sentence that answers "did your recommendations do anything".

    The arithmetic must close exactly, or a reader can do the subtraction and
    catch a contradiction — after which every number on the page is suspect::

        opening = resolved + still_open
        closing = still_open + new + regressed
    """

    opening: int  # themes open at the end of the prior cycle
    resolved: int
    still_open: int  # open last cycle AND open now
    new: int
    regressed: int
    closing: int  # themes open now
    #: Transitions INTO resolved across every comparable cycle in the window —
    #: counted as transitions, not rows, or a finding that stays resolved for 20
    #: weeks counts 20 times.
    resolved_all_time: int
    #: How many comparable cycles the figures above are drawn from.
    cycles_considered: int

    @property
    def is_closed(self) -> bool:
        return (
            self.opening == self.resolved + self.still_open
            and self.closing == self.still_open + self.new + self.regressed
        )

    def sentence(self) -> str:
        """Plain, countable, no adjectives. Flat is a claim, not a blank."""
        if self.opening == 0 and self.closing == 0:
            return "No findings were open last cycle and none are open now."
        if self.opening == 0:
            plural = "s" if self.closing != 1 else ""
            return (
                f"{self.closing} finding{plural} opened this cycle. Nothing was open "
                f"last cycle to compare against."
            )
        parts = [
            f"{self.resolved} of {self.opening} findings from last cycle "
            f"{'are' if self.resolved != 1 else 'is'} resolved"
        ]
        if self.regressed:
            parts.append(f"{self.regressed} regressed")
        if self.new:
            parts.append(f"{self.new} newly opened")
        parts.append(f"{self.still_open} still open")
        line = ", ".join(parts) + "."
        if self.resolved_all_time:
            line += (
                f" {self.resolved_all_time} resolved across the last "
                f"{self.cycles_considered} cycles."
            )
        return line


def comparable_cycles(
    history: Sequence[CycleObservation], query_set_version: str
) -> list[CycleObservation]:
    """The subsequence the state machine is allowed to see, oldest first.

    Filters on the run-coverage gate AND the query set. Only compare like
    instruments: a run on a different query set measured a different thing, and
    silently comparing across one would report the change of ruler as a change in
    the client.
    """
    return [
        c
        for c in history
        if c.run.is_evidence and c.run.query_set_version == query_set_version
    ]


def compute_lifecycle(cycles: Sequence[CycleObservation]) -> dict[str, LifecycleFact]:
    """Status of every theme as of the LAST cycle in ``cycles``.

    ``cycles`` must already be filtered by :func:`comparable_cycles` and ordered
    oldest-first. Pure: same inputs, same outputs, always.

    Returns a fact for every theme ever seen, including ones that are currently
    resolved — the accountability line needs those, and dropping them is how a
    "resolved" count silently becomes zero.
    """
    if not cycles:
        return {}
    every_theme = sorted({t for c in cycles for t in c.themes})
    return {theme: _walk(theme, cycles) for theme in every_theme}


def _walk(theme: str, cycles: Sequence[CycleObservation]) -> LifecycleFact:
    """Replay one theme's presence across the comparable cycles.

    A direct transcription of the spec's algorithm. The branch that matters most
    is ``seen and was_resolved`` versus ``seen`` while absences are unconfirmed:
    the first is a REGRESSION, the second is continuation of something that was
    never actually fixed. Collapsing them is how a client gets told a fix broke
    when it never landed.
    """
    first_seen_run = ""
    first_seen_date = ""
    status = LifecycleStatus.NEW.value
    age = 0
    absences = 0
    was_open = False
    was_resolved = False

    for cycle in cycles:
        seen = theme in cycle.themes
        if not first_seen_run:
            if not seen:
                continue  # the finding does not exist yet
            first_seen_run, first_seen_date = cycle.run.run_id, cycle.run.run_date
            age, was_open, absences = 1, True, 0
            status = LifecycleStatus.NEW.value
            continue

        if seen and was_open:
            age += 1
            absences = 0
            status = LifecycleStatus.PERSISTING.value
        elif seen and was_resolved:
            # A confirmed fix came back. New episode, so the age restarts.
            age, absences = 1, 0
            was_open, was_resolved = True, False
            status = LifecycleStatus.REGRESSED.value
        elif seen:
            # Reappeared during an UNCONFIRMED absence — it was never resolved,
            # so this is continuation and there is nothing to alarm anyone about.
            age += 1
            absences = 0
            was_open = True
            status = LifecycleStatus.PERSISTING.value
        elif was_open:
            absences += 1
            if absences >= RESOLUTION_CONFIRMATION_RUNS:
                was_open, was_resolved = False, True
                status = LifecycleStatus.RESOLVED.value
            else:
                status = LifecycleStatus.PERSISTING.value  # <- guardrail B
        else:
            absences += 1
            status = LifecycleStatus.RESOLVED.value

    return LifecycleFact(
        theme=theme,
        status=status,
        first_seen_run=first_seen_run,
        first_seen_date=first_seen_date,
        cycles_open=age,
        consecutive_absences=absences,
    )


def accountability(cycles: Sequence[CycleObservation]) -> Accountability:
    """Roll the lifecycle up into the line that determines renewal.

    ``opening`` is what was open at the END of the prior cycle, which is that
    cycle's theme set — not the union of everything ever seen. The arithmetic
    closes by construction; :attr:`Accountability.is_closed` asserts it anyway,
    because "by construction" is a claim that survives exactly until someone
    edits this function.
    """
    if not cycles:
        return Accountability(0, 0, 0, 0, 0, 0, 0, 0)
    current = cycles[-1].themes
    prior = cycles[-2].themes if len(cycles) > 1 else frozenset()
    facts = compute_lifecycle(cycles)

    still_open = len(prior & current)
    resolved = len(prior - current)
    regressed = sum(
        1 for t in current if facts[t].status == LifecycleStatus.REGRESSED.value
    )
    # NEW is everything open now that wasn't open last cycle and isn't a
    # regression — so the three add up to `closing` with nothing double-counted.
    new = len(current - prior) - regressed

    return Accountability(
        opening=len(prior),
        resolved=resolved,
        still_open=still_open,
        new=new,
        regressed=regressed,
        closing=len(current),
        resolved_all_time=_resolution_transitions(cycles),
        cycles_considered=len(cycles),
    )


def _resolution_transitions(cycles: Sequence[CycleObservation]) -> int:
    """How many times a theme has ENTERED resolved across the window.

    Transitions, not rows: a theme that stays resolved for 20 cycles resolved
    once, and counting rows would report it twenty times.
    """
    if len(cycles) < 2:
        return 0
    total = 0
    for theme in {t for c in cycles for t in c.themes}:
        was = ""
        for i in range(1, len(cycles) + 1):
            now = _walk(theme, cycles[:i]).status
            if now == LifecycleStatus.RESOLVED.value and was != LifecycleStatus.RESOLVED.value:
                total += 1
            was = now
    return total


if __name__ == "__main__":

    def _cycle(n: int, themes: set[str], coverage: float = 1.0) -> CycleObservation:
        return CycleObservation(
            run=RunMeta(f"run-{n}", f"2026-06-{n:02d}", "done", coverage, "v1"),
            themes=frozenset(themes),
        )

    history = [
        _cycle(1, {"pricing_offer", "identity_disambiguation"}),
        _cycle(2, {"pricing_offer", "identity_disambiguation"}),
        _cycle(3, {"pricing_offer"}),
        _cycle(4, {"pricing_offer", "feature_invented"}),
    ]
    for theme, fact in sorted(compute_lifecycle(history).items()):
        print(f"  {theme:28s} {fact.status:11s} open {fact.cycles_open} cycles")
    acc = accountability(history)
    print(f"\n{acc.sentence()}")
    print(f"arithmetic closes: {acc.is_closed}")
