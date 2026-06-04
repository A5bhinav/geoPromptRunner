from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.prompts.intent import IntentBucket

__all__ = ["Query", "QuerySet", "load_query_set", "bucket_counts"]


@dataclass(frozen=True)
class Query:
    """One buyer query, tagged with its funnel-stage intent.

    ``weight`` is the query's commercial value (a high-intent decision query is
    worth more than an awareness one) — an input to the Step-6 impact formula.
    Defaults to 1.0 so existing query sets load unchanged.

    ``persona`` is the optional buyer modifier the query is phrased for (e.g.
    "college student", "couple") — the deliverable §6.1 Persona/modifier column.
    Defaults to None so existing query sets load unchanged.
    """

    query_id: str
    text: str
    intent: IntentBucket
    weight: float = 1.0
    persona: str | None = None


@dataclass(frozen=True)
class QuerySet:
    """A locked, versioned set of queries for one measurement cycle.

    Held constant across all engines and competitors so time-series comparisons
    are valid (the instrument stays fixed).
    """

    version: str
    locked_at: str  # ISO date the set was frozen
    category: str
    client: str
    competitors: list[str]
    queries: list[Query]


def load_query_set(path: str | Path) -> QuerySet:
    """Load and validate a query set from JSON.

    Raises ``ValueError`` on a duplicate ``query_id`` or an unknown intent tag —
    a malformed set should fail loudly, not run with bad data.
    """
    raw = json.loads(Path(path).read_text())

    queries: list[Query] = []
    seen: set[str] = set()
    for item in raw["queries"]:
        query_id = str(item["query_id"])
        if query_id in seen:
            raise ValueError(f"duplicate query_id: {query_id}")
        seen.add(query_id)
        try:
            intent = IntentBucket(item["intent"])
        except ValueError:
            valid = ", ".join(b.value for b in IntentBucket)
            raise ValueError(
                f"unknown intent {item['intent']!r} for query {query_id}; expected one of: {valid}"
            ) from None
        queries.append(
            Query(
                query_id=query_id,
                text=str(item["text"]),
                intent=intent,
                weight=float(item.get("weight", 1.0)),
                persona=(str(item["persona"]) if item.get("persona") else None),
            )
        )

    if not queries:
        raise ValueError("query set is empty")

    return QuerySet(
        version=str(raw["version"]),
        locked_at=str(raw["locked_at"]),
        category=str(raw["category"]),
        client=str(raw["client"]),
        competitors=[str(c) for c in raw["competitors"]],
        queries=queries,
    )


def bucket_counts(query_set: QuerySet) -> dict[IntentBucket, int]:
    """Count queries per intent bucket (all buckets present, zero-filled)."""
    counter = Counter(q.intent for q in query_set.queries)
    return {bucket: counter.get(bucket, 0) for bucket in IntentBucket}


if __name__ == "__main__":
    sample = Path(__file__).resolve().parents[2] / "data" / "sample_queries.json"
    qs = load_query_set(sample)
    print(f"Loaded query set {qs.version} (locked {qs.locked_at})")
    print(f"  client={qs.client!r} category={qs.category!r} competitors={qs.competitors}")
    print(f"  {len(qs.queries)} queries across buckets:")
    total = len(qs.queries)
    for bucket, count in bucket_counts(qs).items():
        share = f"{100 * count / total:.0f}%" if total else "n/a"
        print(f"    {bucket.value:20s} {count:2d}  ({share})")
