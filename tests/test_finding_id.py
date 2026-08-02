"""Finding identity: the keystone of the recurring report (audit-packaging P0-T1).

Two properties are load-bearing and everything else is detail:

1. **The same finding gets the same id** — across engines, across punctuation and
   casing, and across the paraphrases the engines actually produce. Without it the
   weekly diff invents a fixed finding plus a new one when nothing changed.
2. **Assignment does not depend on input order.** Union-Find near a threshold is
   order-sensitive unless the input is sorted first; a shuffle test is the only
   thing that catches a regression there.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

from src.pipeline.finding_id import (
    DUP_THRESHOLD,
    InMemoryRegistry,
    UnionFind,
    assign_clusters,
    medoid,
    mint_cluster_id,
    normalize,
    numeric_discriminators,
    row_hash,
    similarity,
)

FIXTURE = Path(__file__).parent / "fixtures" / "labeled_pairs.csv"


def _labeled_pairs() -> list[tuple[str, str, int]]:
    """Read the hand-labeled pairs, skipping the `#` provenance comments."""
    rows: list[tuple[str, str, int]] = []
    for line in FIXTURE.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#") or line.startswith("claim_a"):
            continue
        a, b, label = next(csv.reader([line]))
        rows.append((a, b, int(label)))
    return rows


# --- normalization + row_hash -------------------------------------------------


def test_normalize_collapses_the_variants_engines_actually_mix() -> None:
    base = normalize("The Fort band costs $349.")
    assert base == normalize("the  fort band costs $349!")
    assert base == normalize("The Fort band costs $349")
    # A curly apostrophe and a straight one appear in one answer routinely.
    assert normalize("Fort’s band") == normalize("Fort's band")


def test_row_hash_is_stable_and_ignores_cosmetics() -> None:
    assert row_hash("The Fort band costs $349.") == row_hash("the fort band costs $349!")
    assert row_hash("costs $349") != row_hash("costs $289")
    assert len(row_hash("anything")) == 16


def test_normalize_and_row_hash_are_total_on_empty_input() -> None:
    assert normalize("") == ""
    assert row_hash("") == row_hash("   ...   ")


# --- the numeric discriminator guard -----------------------------------------


def test_numeric_discriminators_reads_digits_and_small_number_words() -> None:
    assert numeric_discriminators("about seven days") == numeric_discriminators("roughly 7 days")
    assert numeric_discriminators("costs $349") == frozenset({"349"})
    assert numeric_discriminators("no numbers here") == frozenset()
    assert numeric_discriminators("07 days") == numeric_discriminators("7 days")


def test_disagreeing_numbers_can_never_merge_however_alike_they_read() -> None:
    """The guard's whole point: two wrong prices are two findings, not one."""
    a, b = normalize("The Fort band costs $349."), normalize("The Fort band costs $289.")
    assert similarity(a, b) == 0.0
    ids = {c.cluster_id for c in assign_clusters(["It costs $349.", "It costs $289."])}
    assert len(ids) == 2


# --- clustering ---------------------------------------------------------------


def test_the_same_claim_from_two_engines_is_one_finding() -> None:
    claims = ["There isn't a widely recognized brand called 'Fort'."] * 2
    ids = {c.cluster_id for c in assign_clusters(claims)}
    assert len(ids) == 1


def test_a_paraphrase_above_threshold_joins_the_same_cluster() -> None:
    """The exact failure a pure content hash has: player/entrant, market/space."""
    claims = [
        "Fort is a relatively new player in the fitness tracking market.",
        "Fort is a relatively new entrant in the fitness tracking space.",
    ]
    ids = {c.cluster_id for c in assign_clusters(claims)}
    assert len(ids) == 1


def test_a_materially_different_claim_gets_its_own_cluster() -> None:
    claims = [
        "There isn't a widely recognized brand called 'Fort'.",
        "Fort is a wrist-worn wearable for strength training.",
    ]
    ids = {c.cluster_id for c in assign_clusters(claims)}
    assert len(ids) == 2


def test_punctuation_casing_and_whitespace_variants_collapse() -> None:
    claims = [
        "The Fort band costs $349.",
        "the fort  band costs $349",
        "THE FORT BAND COSTS $349!",
    ]
    result = assign_clusters(claims)
    assert len({c.cluster_id for c in result}) == 1
    assert len({c.row_hash for c in result}) == 1


def test_assignment_is_deterministic_under_input_reordering() -> None:
    """Union-Find on an unsorted list drifts near the threshold. Sorting is the fix."""
    claims = [
        "Fort is a relatively new player in the fitness tracking market.",
        "The Fort band costs $349.",
        "Fort is a relatively new entrant in the fitness tracking space.",
        "There isn't a widely recognized brand called 'Fort'.",
        "the fort band costs $349!",
        "Fort measures blood pressure and ECG.",
        "Fort measures ECG and blood pressure.",
    ]
    baseline = {c.claim: c.cluster_id for c in assign_clusters(claims)}
    rng = random.Random(20260802)
    for _ in range(25):
        shuffled = claims[:]
        rng.shuffle(shuffled)
        assert {c.claim: c.cluster_id for c in assign_clusters(shuffled)} == baseline


def test_every_input_gets_exactly_one_assignment_in_original_order() -> None:
    claims = ["a claim", "another claim entirely", "a claim"]
    result = assign_clusters(claims)
    assert [c.index for c in result] == [0, 1, 2]
    assert [c.claim for c in result] == claims


def test_empty_input_is_not_an_error() -> None:
    assert assign_clusters([]) == []


# --- the registry: what makes an id survive to next week ----------------------


def test_a_registry_hit_reuses_last_weeks_cluster_id() -> None:
    first = assign_clusters(["Fort is a relatively new player in the fitness tracking market."])
    registry = InMemoryRegistry()
    assign_clusters([first[0].claim], registry=registry)

    second = assign_clusters(
        ["Fort is a relatively new entrant in the fitness tracking space."], registry=registry
    )
    assert second[0].cluster_id == first[0].cluster_id
    assert second[0].matched_existing is True


def test_a_genuinely_new_finding_mints_rather_than_attaching() -> None:
    registry = InMemoryRegistry()
    assign_clusters(["The Fort band costs $349."], registry=registry)
    fresh = assign_clusters(["Fort serves the entire Bay Area."], registry=registry)
    assert fresh[0].matched_existing is False


def test_minting_is_content_derived_so_an_identical_finding_recurs_on_the_same_id() -> None:
    """No registry at all still degrades gracefully — the id is not random."""
    claim = "There isn't a widely recognized brand called 'Fort'."
    assert assign_clusters([claim])[0].cluster_id == assign_clusters([claim])[0].cluster_id
    assert mint_cluster_id(normalize(claim)) == assign_clusters([claim])[0].cluster_id


# --- representative -----------------------------------------------------------


def test_medoid_picks_the_central_phrasing_not_the_first_seen() -> None:
    members = [
        "Fort measures blood pressure.",
        "Fort measures blood pressure and ECG.",
        "Fort measures ECG and blood pressure.",
    ]
    chosen = medoid(members)
    assert chosen in members
    # Order-independent: it is a function of the set.
    assert medoid(list(reversed(members))) == chosen


def test_medoid_edge_cases() -> None:
    assert medoid([]) == ""
    assert medoid(["only one"]) == "only one"


# --- union-find ---------------------------------------------------------------


def test_union_find_tie_break_is_deterministic() -> None:
    uf = UnionFind(4)
    uf.union(3, 1)
    uf.union(2, 0)
    assert uf.find(3) == 1
    assert uf.find(2) == 0
    assert uf.components() == {0: [0, 2], 1: [1, 3]}


# --- the tuning gate ----------------------------------------------------------


def test_shipped_threshold_still_beats_its_recorded_precision_and_recall() -> None:
    """Re-runs the sweep the docstring quotes, so growing the fixture re-checks it.

    The floors are the measured values at DUP_THRESHOLD=88 on the 72-pair set.
    Precision is the one that must not slip: a false merge hides a finding inside
    another one and the reader cannot see that it happened.
    """
    rows = _labeled_pairs()
    assert len(rows) >= 60, "the fixture shrank — tuning claims rest on it"
    tp = fp = fn = 0
    for a, b, label in rows:
        predicted = similarity(normalize(a), normalize(b)) >= DUP_THRESHOLD
        if predicted and label:
            tp += 1
        elif predicted and not label:
            fp += 1
        elif label:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    assert precision >= 0.80, f"precision regressed to {precision:.3f}"
    assert recall >= 0.66, f"recall regressed to {recall:.3f}"


def test_the_numeric_guard_is_worth_its_place() -> None:
    """Without it precision collapses — this is why the guard exists, asserted."""
    from rapidfuzz import fuzz

    rows = _labeled_pairs()
    unguarded_fp = sum(
        1
        for a, b, label in rows
        if not label and fuzz.token_set_ratio(normalize(a), normalize(b)) >= DUP_THRESHOLD
    )
    guarded_fp = sum(
        1
        for a, b, label in rows
        if not label and similarity(normalize(a), normalize(b)) >= DUP_THRESHOLD
    )
    assert guarded_fp < unguarded_fp
