"""The instrument is allowed to change, but not quietly (P4-T5 / P4-T6).

Weekly *reporting* frequency is being conflated with weekly *instrument-change*
frequency. Change the query set ad hoc and the trend line stops meaning anything —
which silently invalidates the comparability guard the whole recurring report
rests on.

**Frozen core + rotating discovery slice.** ~75% of the set is a core that cannot
change within a quarter and is the only part the trend is computed from. ~25% is a
discovery slice, refreshed every cycle, which is where new query ideas get tried
without touching the instrument. Churn in the discovery slice does NOT bump the
comparability version; a change to the core does.

**A core change needs a bridge.** Run the old and new sets in parallel for one
full cycle before cutover, so there is a point where both instruments measured the
same week. Without it there is no way to tell a step in the trend line from a step
in the client.

**Per-client config is one versioned record** (P4-T6): fact sheet, query-set
version, engine list, competitor set. The fact sheet already lives on
``audit_runs.fact_sheet`` and is IN THE JUDGE CACHE KEY, so this extends that
pattern rather than inventing a parallel store — a second copy of the sheet is a
second answer to "what was this judged against", and the cache would believe the
wrong one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from src.prompts.query_set import Query, QuerySet

__all__ = [
    "QueryTier",
    "CORE_SHARE_TARGET",
    "TieredQuerySet",
    "CoreChangeRejected",
    "comparability_version",
    "split_tiers",
    "validate_core_change",
    "ClientConfig",
    "config_fingerprint",
]


class QueryTier(StrEnum):
    """Which half of the instrument a query belongs to."""

    #: Frozen for the quarter. The trend is computed from THESE and only these.
    CORE = "core"
    #: Rotates every cycle. Never contributes to the trend, by construction.
    DISCOVERY = "discovery"


#: The intended core share. Advisory, not enforced — a set that drifts below it is
#: reported so the drift is visible, because the failure is gradual: nobody
#: decides to stop having a trend, the core just erodes one query at a time.
CORE_SHARE_TARGET = 0.75


class CoreChangeRejected(RuntimeError):
    """A core change without a bridge cycle. Raised, never warned.

    A warning here would be ignored exactly once and then the trend would be
    silently broken for a quarter.
    """


@dataclass(frozen=True)
class TieredQuerySet:
    """A query set split into its frozen core and its rotating slice."""

    version: str
    core: tuple[Query, ...]
    discovery: tuple[Query, ...]

    @property
    def core_share(self) -> float:
        total = len(self.core) + len(self.discovery)
        return len(self.core) / total if total else 0.0

    @property
    def is_healthy(self) -> bool:
        return self.core_share >= CORE_SHARE_TARGET

    def health_note(self) -> str:
        if self.is_healthy:
            return ""
        return (
            f"Core is {self.core_share:.0%} of the set, below the {CORE_SHARE_TARGET:.0%} "
            f"target — the trend rests on {len(self.core)} queries."
        )


def split_tiers(query_set: QuerySet, core_ids: Sequence[str] | None = None) -> TieredQuerySet:
    """Split a set into core and discovery.

    ``core_ids`` is the frozen list. When it is absent EVERY query is core, which
    is the conservative default: treating an unknown query as discovery would
    silently shrink the trend's basis, and treating it as core merely means a
    change to it is challenged.
    """
    frozen = set(core_ids) if core_ids is not None else {q.query_id for q in query_set.queries}
    core = tuple(q for q in query_set.queries if q.query_id in frozen)
    discovery = tuple(q for q in query_set.queries if q.query_id not in frozen)
    return TieredQuerySet(version=query_set.version, core=core, discovery=discovery)


def comparability_version(tiered: TieredQuerySet) -> str:
    """The version two runs must share to be comparable.

    Derived from the CORE ONLY. That is the whole point of the tiering: rotating
    the discovery slice every cycle is expected and must not break the trend, and
    a version derived from the whole set would break it every single week.

    Computed from the ids rather than declared, so it cannot drift from what was
    actually asked.
    """
    payload = "\x1f".join(sorted(q.query_id for q in tiered.core))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def validate_core_change(
    previous: TieredQuerySet,
    proposed: TieredQuerySet,
    bridge_run_versions: Sequence[str] = (),
) -> None:
    """Refuse a core change that has no bridge cycle behind it.

    A bridge is one full cycle where BOTH cores ran, so there exists a week
    measured by both instruments. Without it, a step in the trend line and a step
    in the client are indistinguishable — and the report would attribute the
    former to the latter.

    Discovery churn is not a core change and passes silently, which is the
    behaviour the tiering exists to permit.
    """
    before, after = comparability_version(previous), comparability_version(proposed)
    if before == after:
        return  # discovery churn only — nothing to bridge
    if before in bridge_run_versions and after in bridge_run_versions:
        return  # both instruments measured the same cycle
    added = {q.query_id for q in proposed.core} - {q.query_id for q in previous.core}
    removed = {q.query_id for q in previous.core} - {q.query_id for q in proposed.core}
    raise CoreChangeRejected(
        f"the frozen core changed ({len(added)} added, {len(removed)} removed) with no "
        f"bridge cycle. Run both cores for one full cycle first, or the trend either "
        f"side of the change cannot be told apart from a change in the client."
    )


@dataclass(frozen=True)
class ClientConfig:
    """Everything that decides what a cycle measured, as one versioned record.

    Any run is reproducible and diffable from this. ``fact_sheet_text`` is stored
    verbatim rather than by reference because it is IN THE JUDGE CACHE KEY — a
    pointer would let the sheet change underneath a stored run and make the
    cache's answer to "what was this judged against" wrong.
    """

    client_name: str
    revision: int
    comparability_version: str
    engines: tuple[str, ...]
    competitors: tuple[str, ...]
    fact_sheet_text: str
    core_query_ids: tuple[str, ...]
    runs_per_query: int
    notes: str = ""
    #: Append-only: a new revision is a new record, never an edit. Storage is
    #: create-only and a cycle's config must stay readable exactly as it was.
    superseded_revision: int | None = field(default=None)


def config_fingerprint(config: ClientConfig) -> str:
    """A stable hash of everything that changes what a run measures.

    Deliberately EXCLUDES ``notes`` and ``revision``: prose and bookkeeping do not
    change the measurement, and making them change the fingerprint would force a
    spurious incomparability every time someone tidied a comment.

    Includes the fact sheet, because it decides what counts as an error — and
    because the judge cache already keys on it, so two configs that differ only
    in the sheet genuinely produce different verdicts.
    """
    payload = "\x1e".join(
        [
            config.client_name,
            config.comparability_version,
            ",".join(sorted(config.engines)),
            ",".join(sorted(config.competitors)),
            ",".join(sorted(config.core_query_ids)),
            str(config.runs_per_query),
            hashlib.sha256(config.fact_sheet_text.encode("utf-8")).hexdigest(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


if __name__ == "__main__":
    from src.prompts.intent import IntentBucket

    def _q(qid: str) -> Query:
        return Query(query_id=qid, text=f"query {qid}", intent=IntentBucket.CATEGORY)

    core_ids = [f"c{i}" for i in range(9)]
    week1 = split_tiers(
        QuerySet("v1", "2026-06-01", "wearables", "Fort", [], [_q(i) for i in core_ids + ["d1"]]),
        core_ids,
    )
    week2 = split_tiers(
        QuerySet("v1", "2026-06-08", "wearables", "Fort", [], [_q(i) for i in core_ids + ["d2"]]),
        core_ids,
    )
    print(f"core share {week1.core_share:.0%}  healthy={week1.is_healthy}")
    same = comparability_version(week1) == comparability_version(week2)
    print(f"discovery churn keeps the version: {same}")
    validate_core_change(week1, week2)
    print("discovery churn accepted")

    changed = split_tiers(
        QuerySet(
            "v2", "2026-07-01", "wearables", "Fort", [], [_q(i) for i in core_ids[:-1] + ["c9"]]
        ),
        core_ids[:-1] + ["c9"],
    )
    try:
        validate_core_change(week2, changed)
    except CoreChangeRejected as exc:
        print(f"core change refused: {str(exc)[:78]}...")
