"""P0-T1's durable half: claim identity that survives a cycle boundary.

`assign_clusters` always collapsed within-run duplicates, because it unions
near-matches before consulting the registry. What it could not do is recognise a
re-wording next cycle — "the Fort band costs $349" and "the Fort band costs $349
retail" are one finding, and used to get two `cluster_id`s, one per cycle,
because the id is minted from the text's own hash.

The report never depended on this (its cards are keyed on theme, which is stable
by construction), so these tests are about the sharper claim the registry
unlocks: "this exact wrong statement has been live for five cycles".
"""

from __future__ import annotations

from typing import Any

import pytest

from src.pipeline.finding_id import (
    InMemoryRegistry,
    assign_clusters,
    normalize,
)
from src.storage import db


class _FakeRegistry:
    """A durable registry that lives in a dict — the storage contract without
    the storage. Mirrors `SupabaseFindingRegistry`'s semantics exactly."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str]] = []
        self.remembered: list[tuple[str, str, str]] = []

    def lookup(self, normalized: str, limit: int = 20) -> list[tuple[str, str]]:
        exact = [(c, n) for c, n in self.rows if n == normalized]
        return exact or self.rows[:limit]

    def remember(self, cluster_id: str, normalized: str, representative: str) -> None:
        self.remembered.append((cluster_id, normalized, representative))
        if not any(n == normalized for _, n in self.rows):
            self.rows.append((cluster_id, normalized))


PRICING = "The Fort band costs $349."
# Scores 100 against PRICING under `similarity`, so it is a genuine near-duplicate
# — but its `row_hash` differs, so without a registry it mints a NEW cluster_id.
# That gap is the whole subject of this module.
#
# Deliberately not a looser paraphrase: "The Fort band is priced at $349" scores
# 85 against DUP_THRESHOLD's 88 and correctly does NOT merge. The threshold was
# measured (P=0.800 / R=0.667 over 72 labeled pairs) and a test that quietly
# needed it lowered would be a test arguing with its own calibration.
PRICING_PARAPHRASE = "The Fort band costs $349 retail."


def test_a_paraphrase_next_cycle_keeps_its_cluster_id() -> None:
    """The regression the durable registry exists for."""
    registry = _FakeRegistry()

    week1 = assign_clusters([PRICING], registry=registry)
    week2 = assign_clusters([PRICING_PARAPHRASE], registry=registry)

    assert week1[0].cluster_id == week2[0].cluster_id
    assert week2[0].matched_existing is True


def test_without_a_registry_the_same_paraphrase_splits() -> None:
    """States the cost of NOT having it, so the test above cannot pass vacuously."""
    a = assign_clusters([PRICING], registry=InMemoryRegistry())
    b = assign_clusters([PRICING_PARAPHRASE], registry=InMemoryRegistry())
    assert a[0].cluster_id != b[0].cluster_id


def test_an_unrelated_claim_gets_its_own_id() -> None:
    registry = _FakeRegistry()
    assign_clusters([PRICING], registry=registry)
    other = assign_clusters(["Fort does not track heart rate."], registry=registry)
    assert other[0].matched_existing is False


def test_re_rendering_the_same_report_does_not_grow_the_registry() -> None:
    """`remember` runs once per component on EVERY render. A report re-rendered
    ten times must not leave ten rows behind."""
    registry = _FakeRegistry()
    for _ in range(5):
        assign_clusters([PRICING, "Fort does not track heart rate."], registry=registry)
    assert len(registry.rows) == 2


# --- the Supabase implementation, without Supabase ----------------------------


def test_the_durable_registry_degrades_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This runs on the render path, which is meant to be free and reliable.

    A report that clusters within the run but loses cross-cycle identity is
    degraded; one that raises because Supabase blinked is broken.
    """

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise db.StorageError("unreachable")

    monkeypatch.setattr(db, "findings_registry_lookup", _boom)
    monkeypatch.setattr(db, "findings_registry_remember", _boom)

    registry = db.SupabaseFindingRegistry("Fort")
    assignments = assign_clusters([PRICING, PRICING_PARAPHRASE], registry=registry)

    # The run still clusters correctly — the two paraphrases union before the
    # registry is ever consulted.
    assert len({a.cluster_id for a in assignments}) == 1


def test_the_durable_registry_stops_retrying_after_one_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """200 flags must not become 200 doomed round-trips and 200 warnings."""
    calls = 0

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise db.StorageError("unreachable")

    monkeypatch.setattr(db, "findings_registry_lookup", _boom)
    monkeypatch.setattr(db, "findings_registry_remember", _boom)

    registry = db.SupabaseFindingRegistry("Fort")
    for i in range(20):
        registry.lookup(normalize(f"claim number {i}"))
    assert calls == 1


def test_the_durable_registry_serves_its_own_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Within one render, a cluster remembered a moment ago must be found without
    a round-trip — the row may not have been committed yet, and the component
    that minted it is the authority either way."""
    reads: list[str] = []

    monkeypatch.setattr(
        db,
        "findings_registry_lookup",
        lambda client, normalized, limit=20: (reads.append(normalized), [])[1],
    )
    monkeypatch.setattr(db, "findings_registry_remember", lambda *a, **k: None)

    registry = db.SupabaseFindingRegistry("Fort")
    registry.remember("cluster-1", normalize(PRICING), PRICING)
    assert registry.lookup(normalize(PRICING)) == [("cluster-1", normalize(PRICING))]
    assert reads == [], "a locally-remembered cluster should not need a read"


def test_the_registry_is_scoped_per_client() -> None:
    """Two clients can produce byte-identical claims about unrelated companies.

    A shared keyspace would merge them, which is both wrong and a cross-tenant
    leak of one client's text into another's report.
    """
    registry = db.SupabaseFindingRegistry("Fort")
    assert registry.client_name == "Fort"
    # The schema's unique index is (client_name, normalized), and every read
    # filters on client_name — asserted here so a future "optimization" that
    # drops the filter fails loudly.
    import inspect

    source = inspect.getsource(db.findings_registry_lookup)
    assert source.count('.eq("client_name", client_name)') == 2
