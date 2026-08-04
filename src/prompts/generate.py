"""A bucket-allocated query set from a template bank. Pure, deterministic, free.

WHY THIS IS NOT AN LLM. ``docs/query-generation-plan.md`` §1b is explicit that
the methodology FORBIDS LLM-originated queries — the drafter's role is "source →
draft → format, never originate from imagination." Three consequences follow and
all three matter here:

* A generated question set is the instrument. If it is nondeterministic, two
  cycles are not comparable and the whole recurring contract collapses.
* It would cost money on a path that currently costs nothing, on every intake.
* This feeds a screen whose entire job is human review. A reviewer cannot check
  a set they cannot regenerate.

So: a template bank, slots filled ONLY from the sheet's own claims and the
session's run inputs. Every query is traceable to a line the owner confirmed.

This is also the fallback for a local trade with no hand-written template
(``TRADES`` covers hvac, plumbing and barbershop and nothing else). That is why
it takes an allocation rather than assuming the consumer funnel: pass
``LOCAL_BUCKET_ALLOCATION`` and the same bank produces a local set.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.prompts.intent import BUCKET_ALLOCATION, LOCAL_BUCKET_ALLOCATION, IntentBucket

__all__ = [
    "GeneratedQuery",
    "QuerySet",
    "GenerateError",
    "generate_query_set",
    "TEMPLATE_BANK_PATH",
]

TEMPLATE_BANK_PATH = Path(__file__).resolve().parents[2] / "data" / "query_templates.json"


class GenerateError(RuntimeError):
    """The bank cannot satisfy the request — missing slots, or no templates."""


@dataclass(frozen=True, kw_only=True)
class GeneratedQuery:
    """One question, with enough provenance to audit the set that contains it."""

    query_id: str
    text: str
    intent: IntentBucket
    persona: str = ""
    #: verbatim | near_verbatim | constructed. §5's "≥1/3 verbatim" check is
    #: unenforceable without real sourcing, so it is reported and never blocked —
    #: but it has to be RECORDED, or the check can never become enforceable.
    provenance: str = "constructed"
    #: True when the client's own name appears. The lint reads this rather than
    #: re-deriving it, so "named" means the same thing everywhere.
    names_client: bool = False


@dataclass(frozen=True, kw_only=True)
class QuerySet:
    queries: tuple[GeneratedQuery, ...]
    allocation: Mapping[IntentBucket, float]

    def by_bucket(self) -> dict[IntentBucket, list[GeneratedQuery]]:
        out: dict[IntentBucket, list[GeneratedQuery]] = {}
        for q in self.queries:
            out.setdefault(q.intent, []).append(q)
        return out


def _load_bank() -> dict[str, list[dict[str, str]]]:
    if not TEMPLATE_BANK_PATH.exists():
        raise GenerateError(f"no template bank at {TEMPLATE_BANK_PATH}")
    with TEMPLATE_BANK_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise GenerateError("the template bank must be an object keyed by intent bucket")
    return {str(k): list(v) for k, v in data.items()}


def _fill(shape: str, slots: Mapping[str, str]) -> str | None:
    """Fill a shape, or ``None`` when a slot it needs is missing.

    NEVER partially filled. A literal ``{city}`` reaching an engine scores as a
    loss on a question nobody asked, which is worse than a shorter set — so an
    unfillable shape is dropped here and the lint blocks on any that survive.
    """
    out = shape
    start = out.find("{")
    while start != -1:
        end = out.find("}", start)
        if end == -1:
            return None
        name = out[start + 1 : end]
        value = slots.get(name, "").strip()
        if not value:
            return None
        out = f"{out[:start]}{value}{out[end + 1 :]}"
        start = out.find("{", start + len(value))
    return " ".join(out.split())


_PREFIX = {
    IntentBucket.PROBLEM_AWARE: "prb",
    IntentBucket.CATEGORY: "cat",
    IntentBucket.COMPARISON: "cmp",
    IntentBucket.BRAND: "brd",
    IntentBucket.ADJACENT_AUTHORITY: "adj",
    IntentBucket.LOCAL_INTENT: "loc",
    IntentBucket.HYBRID: "hyb",
    IntentBucket.INFORMATIONAL: "inf",
}


def _counts(allocation: Mapping[IntentBucket, float], n: int) -> dict[IntentBucket, int]:
    """Whole-number counts per bucket that sum to exactly ``n``.

    Largest-remainder, not rounding: independent rounding of five shares gives a
    total of n±2 often enough to matter, and a set that is not the size the cost
    estimate was based on is a set whose price is wrong.
    """
    raw = {b: allocation[b] * n for b in allocation}
    base = {b: int(math.floor(v)) for b, v in raw.items()}
    short = n - sum(base.values())
    for bucket in sorted(raw, key=lambda b: raw[b] - base[b], reverse=True):
        if short <= 0:
            break
        base[bucket] += 1
        short -= 1
    return base


def generate_query_set(
    *,
    client: str,
    category: str,
    competitors: Sequence[str],
    slots: Mapping[str, str] | None = None,
    n: int = 30,
    allocation: Mapping[IntentBucket, float] | None = None,
    local: bool = False,
) -> QuerySet:
    """A bucket-allocated set. Deterministic: same inputs, same set, same ids.

    TWO CONSTRAINTS ARE ENFORCED HERE AND NOT LEFT TO THE LINT, because a set
    that violates them is not a set worth reviewing:

    * every competitor appears in at least one comparison question;
    * at least two comparison questions leave the CLIENT UNNAMED. Those are the
      ones that test unprompted surfacing, which is the measurement that matters
      most — a set where the client is named in every question can only ever
      measure how well a model reads a prompt back.

    The lint re-checks both anyway. It is the backstop for a hand-edited set.
    """
    allocation = allocation or (LOCAL_BUCKET_ALLOCATION if local else BUCKET_ALLOCATION)
    bank = _load_bank()
    base_slots: dict[str, str] = {
        "client": client.strip(),
        "category": category.strip(),
        **{k: str(v).strip() for k, v in (slots or {}).items()},
    }
    competitors = [c.strip() for c in competitors if c.strip()]

    counts = _counts(allocation, n)
    out: list[GeneratedQuery] = []

    for bucket, want in counts.items():
        if want <= 0:
            continue
        shapes = bank.get(bucket.value, [])
        made: list[GeneratedQuery] = []
        index = 0
        # Comparison is special: it is the only bucket whose slots vary per
        # query, because each competitor needs its own question.
        pool = competitors or [""]
        for shape in shapes:
            if len(made) >= want:
                break
            for competitor in pool if bucket is IntentBucket.COMPARISON else [""]:
                if len(made) >= want:
                    break
                text = _fill(shape["shape"], {**base_slots, "competitor": competitor})
                if text is None:
                    continue
                index += 1
                made.append(
                    GeneratedQuery(
                        query_id=f"{_PREFIX[bucket]}-{index:02d}",
                        text=text,
                        intent=bucket,
                        persona=shape.get("persona", ""),
                        provenance=shape.get("provenance", "constructed"),
                        names_client=bool(base_slots["client"])
                        and base_slots["client"].casefold() in text.casefold(),
                    )
                )
        out.extend(made)

    out = _guarantee_comparison_coverage(out, client=base_slots["client"], competitors=competitors)
    return QuerySet(queries=tuple(out), allocation=allocation)


def _guarantee_comparison_coverage(
    queries: list[GeneratedQuery],
    *,
    client: str,
    competitors: Sequence[str],
) -> list[GeneratedQuery]:
    """Add whatever the allocation could not fit, rather than shipping a gap.

    An allocation is a target and the two comparison constraints are not. When
    25% of 30 questions is not enough room for six competitors plus two unnamed
    shapes, the set grows — a slightly-off allocation is a warning, a missing
    competitor is a block, and growing is the only move that satisfies both.
    """
    comparison = [q for q in queries if q.intent is IntentBucket.COMPARISON]
    covered = {
        c.casefold()
        for c in competitors
        if any(c.casefold() in q.text.casefold() for q in comparison)
    }
    next_index = len(comparison)
    extra: list[GeneratedQuery] = []

    for competitor in competitors:
        if competitor.casefold() in covered:
            continue
        next_index += 1
        extra.append(
            GeneratedQuery(
                query_id=f"cmp-{next_index:02d}",
                text=f"{client} vs {competitor}",
                intent=IntentBucket.COMPARISON,
                provenance="constructed",
                names_client=True,
            )
        )

    unnamed = [q for q in comparison + extra if not q.names_client]
    for competitor in list(competitors)[: max(0, 2 - len(unnamed))]:
        next_index += 1
        extra.append(
            GeneratedQuery(
                query_id=f"cmp-{next_index:02d}",
                # The client is deliberately absent: this measures whether a
                # model volunteers them when asked about the alternative.
                text=f"best alternative to {competitor}",
                intent=IntentBucket.COMPARISON,
                provenance="constructed",
                names_client=False,
            )
        )

    return queries + extra
