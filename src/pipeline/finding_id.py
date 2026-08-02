"""Stable identity for an accuracy finding — the keystone of the recurring report.

``AccuracyFlag`` is what the judge returns; it is anonymous. An anonymous finding
cannot be deduplicated, prioritized, tracked across weeks, evidenced or closed,
which is why 235 flags render as 235 identical cards. This module gives one a
name (``docs/audit-packaging-spec.md`` P0-T1).

**Two layers, deliberately.** A single content hash is brittle by construction:
"Fort is a relatively new *player*" and "…new *entrant*" hash to unrelated values,
so next week's report shows a fixed finding plus a new one when nothing changed.

===============  ==========================================  =======================
layer            what                                        purpose
===============  ==========================================  =======================
``row_hash``     ``sha256(normalize(claim))[:16]``, always    idempotency only —
                 recomputed, never stored                     "did I already ingest
                                                              this exact row?"
``cluster_id``   uuid5 over the component's canonical text,   the stable,
                 attached via a registry lookup when one      client-facing finding
                 exists                                       id; survives weeks
===============  ==========================================  =======================

**Why uuid5 and not uuid4.** The spec calls the cluster id "persisted", and it is
— :class:`FindingRegistry` is what carries a paraphrase from last week onto the
same id. But minting a *random* id for a genuinely new finding would make the
assignment depend on when it ran, and P1-T1's acceptance is that shuffling the
input produces identical cluster ids. Deriving the id from the component's
canonical text gives determinism for free and degrades gracefully: with no
registry at all, identical text still lands on the identical id.

**Deliberately NOT used:** SimHash and MinHash/LSH (document-scale techniques
whose guarantees evaporate on 10–40 word sentences), embeddings/pgvector (BLAS
and hardware float variance break the determinism requirement), HDBSCAN and
``scipy.fcluster`` (both relabel the whole dataset when one item is added, which
is exactly the instability that would make a weekly diff lie). Semantic-only
near-matches — *"There isn't a widely recognized brand called 'Fort'"* vs
*"Fort (assuming you mean Fitbit?)"* — are caught by the **theme** classifier
(:mod:`src.pipeline.themes`), not here. Do not make similarity solve semantic
equivalence.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz

__all__ = [
    "DUP_THRESHOLD",
    "normalize",
    "row_hash",
    "numeric_discriminators",
    "similarity",
    "UnionFind",
    "FindingRegistry",
    "InMemoryRegistry",
    "ClusterAssignment",
    "medoid",
    "mint_cluster_id",
    "assign_clusters",
]

#: Namespace for :func:`mint_cluster_id`. Frozen — changing it renames every
#: finding in every stored report, which is a silent history rewrite.
_CLUSTER_NS = uuid.UUID("6f2b0a54-7c1e-5d9a-9f31-2b8e4c0a71d3")

#: Similarity floor (0–100) above which two claims are the same finding.
#:
#: **Tuned, not guessed, and the measured numbers are below — not aspirational
#: ones.** Swept 60→99 over ``tests/fixtures/labeled_pairs.csv`` (72 hand-labeled
#: pairs; phrasings and paraphrase patterns from the Fort and Albert Nahman runs).
#: With the numeric guard in :func:`similarity`, the precision curve has a clear
#: knee between 86 and 88 — precision jumps 0.73 → 0.80 for 0.08 of recall —  and
#: is flat either side of it:
#:
#: ====  =========  ======
#: t     precision  recall
#: ====  =========  ======
#: 84    0.707      0.806
#: 86    0.730      0.750
#: **88**  **0.800**  **0.667**
#: 90    0.815      0.611
#: 92    0.810      0.472
#: ====  =========  ======
#:
#: The bias is deliberate and is why the knee, not the F1 maximum (which sits
#: near 78), is the right pick: a false *merge* hides a finding inside another and
#: the reader cannot see that it happened, whereas a false *split* merely shows
#: two cards where one would do. Precision first.
#:
#: **Read that precision as a floor, not an estimate.** The fixture's negatives
#: are adversarial by construction — minimal pairs that differ by one token
#: ("iOS-only" vs "Android-only", "Whoop competitor" vs "Garmin competitor").
#: In a real run most non-duplicate pairs are about entirely different subjects
#: and score nowhere near the threshold. The residual errors are all semantic, not
#: lexical, and are out of this layer's scope by design.
#:
#: ``tests/test_finding_id.py`` re-runs the sweep as a regression gate, so growing
#: the fixture re-checks this number rather than silently invalidating it.
DUP_THRESHOLD = 88.0

# Punctuation-to-space, so "Fort's" and "Fort s" collapse the same way and a
# claim ending in "." matches the same claim quoted mid-sentence.
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize(claim: str) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace.

    Pure and total: any string in, a possibly-empty string out. NFKD first so a
    curly apostrophe and a straight one — which the engines mix freely within a
    single answer — cannot produce two findings.
    """
    decomposed = unicodedata.normalize("NFKD", claim)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", stripped.casefold())).strip()


def row_hash(claim: str) -> str:
    """Idempotency key for one claim row. Never a client-facing id.

    Recomputed on every read rather than stored, so it can never disagree with
    the text it names.
    """
    return hashlib.sha256(normalize(claim).encode("utf-8")).hexdigest()[:16]


#: Small number words, so "about seven days" and "roughly 7 days" carry the same
#: discriminator. Stops at twelve deliberately — beyond that the engines write
#: digits, and a longer list starts colliding with ordinary prose ("a hundred").
_NUMBER_WORDS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def numeric_discriminators(claim: str) -> frozenset[str]:
    """Every number in a claim, as a set. The thing two claims must agree on.

    Prices, durations, dates, phone numbers and battery life are where the models
    are wrong in the way a customer acts on, and they are also where lexical
    similarity is at its most misleading: *"The Fort band costs $349"* and
    *"The Fort band costs $289"* share every token but one and score 93 on
    ``token_set_ratio``. Merging them would file two findings — a wrong price and
    a different wrong price — as one, and hide the second from the client.

    Leading zeros are stripped so ``07`` and ``7`` agree; ``0`` survives as ``0``.
    """
    n = normalize(claim)
    found = {_NUMBER_WORDS[t] for t in n.split() if t in _NUMBER_WORDS}
    found |= {(m.lstrip("0") or "0") for m in _NUMBER_RE.findall(n)}
    return frozenset(found)


def similarity(a_normalized: str, b_normalized: str) -> float:
    """Score two *already normalized* claims, 0–100. Deterministic.

    ``token_set_ratio`` because it is robust to reordering and to one claim being
    a subset of the other — exactly the paraphrase shapes the engines produce.
    C++-backed, so 235 flags (~27.6k pairs) is sub-second.

    Gated on :func:`numeric_discriminators`: claims whose numbers disagree score
    ``0.0`` regardless of how alike they read. That guard is worth ~11 points of
    precision on the labeled set and cannot cost recall, because two claims that
    state different numbers are never one finding.
    """
    if numeric_discriminators(a_normalized) != numeric_discriminators(b_normalized):
        return 0.0
    return float(fuzz.token_set_ratio(a_normalized, b_normalized))


class UnionFind:
    """Single-linkage clustering, computed incrementally.

    The incremental part is the point: HDBSCAN and ``scipy.fcluster`` return
    arbitrary integer labels recomputed from the whole dataset, so adding item
    #236 can reshuffle which integer means which real finding. This composes with
    a persisted registry without relabelling anything already assigned.
    """

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Deterministic tie-break: the lower index always becomes the root.
            self.parent[max(ra, rb)] = min(ra, rb)

    def components(self) -> dict[int, list[int]]:
        """Root index -> its members, both in ascending order."""
        out: dict[int, list[int]] = {}
        for i in range(len(self.parent)):
            out.setdefault(self.find(i), []).append(i)
        return out


class FindingRegistry(Protocol):
    """What a previously-seen finding looks up as.

    Implementations may block however they like (``pg_trgm``, a dict, nothing at
    all) as long as ``lookup`` is a *recall-oriented* candidate fetch: the caller
    re-scores every candidate with rapidfuzz and applies :data:`DUP_THRESHOLD`
    itself, so returning a near-miss costs nothing but returning too few is a
    silent split.
    """

    def lookup(self, normalized: str, limit: int = 20) -> list[tuple[str, str]]:
        """Candidate ``(cluster_id, normalized_text)`` pairs for one claim."""
        ...

    def remember(self, cluster_id: str, normalized: str, representative: str) -> None:
        """Record that ``normalized`` belongs to ``cluster_id``."""
        ...


class InMemoryRegistry:
    """The default registry: this process, this run.

    Enough for a single-run report — within-run duplicates still collapse,
    because :func:`assign_clusters` unions them before consulting the registry.
    Cross-week identity needs a durable implementation
    (``src.storage.db.SupabaseFindingRegistry``); this one is what makes the
    module usable and testable without a database.
    """

    def __init__(self, seed: Iterable[tuple[str, str]] = ()) -> None:
        self._rows: list[tuple[str, str]] = list(seed)
        self._exact: dict[str, str] = {n: c for c, n in self._rows}

    def lookup(self, normalized: str, limit: int = 20) -> list[tuple[str, str]]:
        exact = self._exact.get(normalized)
        if exact is not None:
            return [(exact, normalized)]
        return self._rows[:limit] if limit else list(self._rows)

    def remember(self, cluster_id: str, normalized: str, representative: str) -> None:
        if normalized in self._exact:
            return
        self._exact[normalized] = cluster_id
        self._rows.append((cluster_id, normalized))


@dataclass(frozen=True)
class ClusterAssignment:
    """One input claim's identity."""

    index: int  # position in the caller's original list
    claim: str
    row_hash: str
    cluster_id: str
    #: The component's chosen representative (the medoid) — the text a card shows.
    representative: str
    #: True when the id came from the registry rather than being minted here.
    matched_existing: bool


def medoid(members: Sequence[str]) -> str:
    """The member with the least total distance to the others.

    Ties break by shortest, then lexicographically first, so the choice is a
    function of the *set* and not of iteration order. A medoid beats "first seen"
    because the representative is what a client reads: the most central phrasing
    of a finding is the one that describes all of its instances.
    """
    if not members:
        return ""
    if len(members) == 1:
        return members[0]
    normalized = [normalize(m) for m in members]

    def total_distance(i: int) -> float:
        # Raw token_set_ratio, NOT `similarity`: the numeric guard is a merge
        # decision, and zeroing a within-component score would make the medoid
        # depend on which member happens to quote a figure.
        return sum(
            100.0 - fuzz.token_set_ratio(normalized[i], normalized[j])
            for j in range(len(members))
            if j != i
        )

    best = min(range(len(members)), key=lambda i: (total_distance(i), len(members[i]), members[i]))
    return members[best]


def mint_cluster_id(canonical: str) -> str:
    """A new finding's stable id, derived from its canonical (normalized) text."""
    return str(uuid.uuid5(_CLUSTER_NS, canonical))


def assign_clusters(
    claims: Sequence[str],
    registry: FindingRegistry | None = None,
    threshold: float = DUP_THRESHOLD,
) -> list[ClusterAssignment]:
    """Give every claim a ``row_hash`` and a ``cluster_id``. Pure w.r.t. ordering.

    Three steps, in this order:

    1. **Sort by** ``(row_hash, original_index)`` before doing anything pairwise.
       Union-Find on an unsorted list can produce different components near the
       threshold depending on comparison order — the determinism requirement is
       satisfied by the sort, not by the algorithm.
    2. **Union** mutual near-duplicates within this run into components.
    3. **Ask the registry** once per component (not once per claim, which would
       let two members of one component land on two different historical ids).
       A hit attaches the existing id; a miss mints one from the component's
       canonical text and remembers it.

    Returns one assignment per input, in the caller's original order.
    """
    n = len(claims)
    if n == 0:
        return []
    registry = registry if registry is not None else InMemoryRegistry()

    hashes = [row_hash(c) for c in claims]
    normalized = [normalize(c) for c in claims]
    order = sorted(range(n), key=lambda i: (hashes[i], i))

    uf = UnionFind(n)
    for a in range(n):
        for b in range(a + 1, n):
            i, j = order[a], order[b]
            # Identical normalized text is a duplicate by definition; skip the
            # fuzzy call for it (the common case at 200+ flags per run).
            if normalized[i] == normalized[j] or similarity(normalized[i], normalized[j]) >= (
                threshold
            ):
                uf.union(i, j)

    components = uf.components()
    assignments: list[ClusterAssignment | None] = [None] * n
    for root in sorted(components, key=lambda r: (hashes[r], r)):
        members = sorted(components[root], key=lambda i: (hashes[i], i))
        member_claims = [claims[i] for i in members]
        rep = medoid(member_claims)
        canonical = normalize(rep)

        cluster_id, matched = _resolve(registry, normalized, members, canonical, threshold)
        registry.remember(cluster_id, canonical, rep)
        for i in members:
            # Every member's own text is remembered too, so next week's exact
            # repeat of a non-representative phrasing is an O(1) hit.
            registry.remember(cluster_id, normalized[i], rep)
            assignments[i] = ClusterAssignment(
                index=i,
                claim=claims[i],
                row_hash=hashes[i],
                cluster_id=cluster_id,
                representative=rep,
                matched_existing=matched,
            )

    out = [a for a in assignments if a is not None]
    assert len(out) == n, "every claim must receive exactly one assignment"
    return out


def _resolve(
    registry: FindingRegistry,
    normalized: Sequence[str],
    members: Sequence[int],
    canonical: str,
    threshold: float,
) -> tuple[str, bool]:
    """Best registry match for a whole component, or a freshly minted id.

    Scores every member against every candidate and takes the single best pair,
    rather than trusting the representative alone: a component's medoid can be
    the one phrasing the registry has never seen while three of its members are
    verbatim repeats of last week.
    """
    best_id: str | None = None
    best_score = 0.0
    for i in members:
        for cid, cand in registry.lookup(normalized[i]):
            score = 100.0 if cand == normalized[i] else similarity(normalized[i], cand)
            # `>` not `>=`, so the first-encountered best wins a tie and the scan
            # order — which the caller already sorted — decides it deterministically.
            if score >= threshold and score > best_score:
                best_score, best_id = score, cid
    if best_id is not None:
        return best_id, True
    return mint_cluster_id(canonical), False


if __name__ == "__main__":
    sample = [
        "Fort is a relatively new player in the fitness tracking market.",
        "Fort is a relatively new entrant in the fitness tracking space.",
        "There isn't a widely recognized brand called 'Fort'.",
        "The Fort band costs $349.",
        "The Fort band costs $349!",
    ]
    for a in assign_clusters(sample):
        print(f"{a.cluster_id[:8]}  {a.row_hash}  {a.claim}")
