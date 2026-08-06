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
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.prompts.intent import (
    BUCKET_ALLOCATION,
    CONSUMER_BUCKETS,
    LOCAL_BUCKET_ALLOCATION,
    LOCAL_BUCKETS,
    IntentBucket,
)
from src.prompts.query_set import QUERY_SET_SIZE

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


#: A shape must anchor to something the sheet knows. A shape with NO slot at all
#: is the same string for every client on earth — it cannot be traced to a line
#: the owner confirmed, which is the contract at the top of this module, and it
#: cannot produce a mention because it has no subject. Three of them shipped:
#: "how do I stop this from happening again", "is this an emergency or can it
#: wait until Monday", "what does it usually cost to fix this myself vs hiring
#: someone". Each was a guaranteed zero in the numerator and a live +1 in the
#: denominator of a rate a client is quoted.
#:
#: This is a STRUCTURAL rule, not an editorial one: it says a template must have
#: a slot, not what the slot should say. A genuine problem-aware question ("why
#: do I wake up exhausted even after a full night's sleep") names no brand and is
#: exactly what the methodology asks for — but it is sourced per category, so in
#: a template bank it carries a slot too.
_ANCHORLESS = re.compile(r"^[^{]*$")


def _anchored(shape: str) -> bool:
    """False for a template with no slot to fill from the sheet."""
    return not _ANCHORLESS.match(shape)


def _usable(shape: Mapping[str, object], local: bool) -> bool:
    """Whether one bank entry may be used for this set at all.

    ``local_only`` MARKS A SHAPE WHOSE LANGUAGE ONLY WORKS FOR A TRADE. The
    shared buckets — problem_aware, category, comparison, brand,
    adjacent_authority — are used by both funnels, and two of their shapes were
    sourced from a buyer whose thing physically breaks: "my {category} keeps
    breaking, what should I do" and "how long should a {category} job take". A
    marketing agency does not break and does not have a job that takes a
    weekend, so those two produced the single worst question in a live set.

    It is a stopgap and it should stay small. The real answer is a bank per
    field (query-generation-plan.md §0.5.2) — this only stops the trade bank
    leaking into a set it was never sourced for, and it cannot make the
    remaining shapes anybody's actual words.
    """
    if not _anchored(str(shape.get("shape", ""))):
        return False
    return local or not shape.get("local_only")


_SLOT_NAMES = re.compile(r"\{([a-z_]+)\}")


def _bindings(shape: str, fan: Mapping[str, Sequence[str]]) -> list[dict[str, str]]:
    """One binding per combination of the fan-out values this shape names.

    A shape naming no fan-out slot gets exactly one empty binding, which is the
    old behaviour: single-valued slots come from ``base_slots`` and a shape makes
    one question.

    BREADTH FIRST, NOT DEPTH FIRST. A bucket almost always truncates — six
    services times three towns is eighteen combinations for a bucket with room
    for six — so the ORDER decides what the set covers. A plain nested product
    takes the first service and walks every town before touching the second:
    measured, that produced "best drain cleaning in Albany / Oakland / El
    Cerrito" then "best water heater install in Albany / Oakland / El Cerrito",
    covering two of six services. Sorting by the largest index in the
    combination walks the diagonal instead, so every service is seen once before
    any is seen twice.

    DETERMINISTIC EITHER WAY, which is the constraint that actually binds: the
    set is the instrument, and two cycles that disagree about which questions
    they contain are two instruments. Ties break on the plain product order, so
    the same inputs always give the same list.

    A shape naming a fan-out slot with NO values yields nothing at all, rather
    than one question with an empty binding that ``_fill`` would drop anyway.
    That is the same rule as an unfillable ``{city}``: never partially filled.
    """
    names = [n for n in dict.fromkeys(_SLOT_NAMES.findall(shape)) if n in fan]
    if not names:
        return [{}]
    indexed: list[tuple[tuple[int, ...], dict[str, str]]] = [((), {})]
    for name in names:
        values = list(fan[name])
        if not values:
            return []
        indexed = [
            ((*idx, i), {**binding, name: value})
            for idx, binding in indexed
            for i, value in enumerate(values)
        ]
    indexed.sort(key=lambda pair: (max(pair[0]), sum(pair[0]), pair[0]))
    return [binding for _, binding in indexed]


def _natural(category: str) -> str:
    """A category as a person types it into a chatbot.

    "best Digital Marketing Agency" is not a question anybody asks; "best digital
    marketing agency" is. The sheet stores the category the way an owner writes
    it on their website — title case, because it is a heading there — and it was
    substituted verbatim into the middle of a sentence.

    ONLY TITLE CASE IS LOWERED. A token that is all-caps or internally
    capitalised is an acronym or a brand — HVAC, PPC, SaaS, B2B — and lowering it
    would be a different kind of wrong.
    """
    out: list[str] = []
    for token in category.split():
        stripped = token.strip(".,")
        looks_titled = stripped[:1].isupper() and stripped[1:].islower()
        out.append(token.lower() if looks_titled else token)
    return " ".join(out)


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
    lists: Mapping[str, Sequence[str]] | None = None,
    n: int = QUERY_SET_SIZE,
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

    ``slots`` ARE SINGLE-VALUED; ``lists`` FAN OUT. That distinction is why the
    bank had a ceiling. One category, one city, one year means a shape like
    "best {category} in {city}" yields exactly ONE question however rich the
    fact sheet is — so the maximum size of a set was the number of lines in
    `query_templates.json`, measured at 31 for a local business and 30 for a
    general one with two competitors. Asking for 50 could not work, whatever
    `QUERY_SET_SIZE` said.

    ``{competitor}`` was already the exception, hardcoded into the comparison
    bucket. It is now the general case: any slot named in ``lists`` fans a shape
    out over its values, so "best {category} for {service}" becomes six real
    questions from six services the owner confirmed. That is methodology §3.2 —
    "every other carries a qualifier drawn from the fact sheet's real segments" —
    which the bank could not express before.

    The fan-out is over CONFIRMED LINES, so it adds specificity rather than
    volume: six services the owner typed produce six questions their buyers
    actually ask, not six paraphrases of one.
    """
    allocation = allocation or (LOCAL_BUCKET_ALLOCATION if local else BUCKET_ALLOCATION)
    bank = _load_bank()
    base_slots: dict[str, str] = {
        "client": client.strip(),
        # Lower-cased where it is title case, because it lands mid-sentence in
        # every shape that uses it.
        "category": _natural(category.strip()),
        **{k: str(v).strip() for k, v in (slots or {}).items()},
    }
    competitors = [c.strip() for c in competitors if c.strip()]
    # Every fan-out slot in one map, competitors included — they are no longer a
    # special case, just the one that was built first.
    fan: dict[str, list[str]] = {
        name: [v.strip() for v in values if str(v).strip()]
        for name, values in (lists or {}).items()
    }
    fan["competitor"] = competitors
    # The funnel this set belongs to. The top-up may reach for another bucket
    # inside it, and never for one outside: a local set filled from the consumer
    # bank stops being a local set, and a consumer set filled from the local bank
    # asks a SaaS company about call-out fees.
    family = LOCAL_BUCKETS if set(allocation) <= set(LOCAL_BUCKETS) else CONSUMER_BUCKETS

    counts = _counts(allocation, n)
    out: list[GeneratedQuery] = []

    for bucket, want in counts.items():
        if want <= 0:
            continue
        shapes = bank.get(bucket.value, [])
        made: list[GeneratedQuery] = []
        index = 0
        for shape in shapes:
            if len(made) >= want:
                break
            if not _usable(shape, local):
                continue
            # One question per combination of the fan-out values this shape
            # actually names. A shape with none gets a single empty binding and
            # behaves exactly as it always did.
            for binding in _bindings(str(shape["shape"]), fan):
                if len(made) >= want:
                    break
                text = _fill(shape["shape"], {**base_slots, **binding})
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

    out = _guarantee_comparison_coverage(
        out,
        client=base_slots["client"],
        competitors=competitors,
        category=base_slots["category"],
    )
    out = _resize(
        out,
        n,
        bank=bank,
        allocation=allocation,
        base_slots=base_slots,
        family=family,
        local=local,
        fan=fan,
    )
    return QuerySet(queries=tuple(out), allocation=allocation)


def _resize(
    queries: list[GeneratedQuery],
    n: int,
    *,
    bank: Mapping[str, list[dict[str, str]]],
    allocation: Mapping[IntentBucket, float],
    base_slots: Mapping[str, str],
    family: Sequence[IntentBucket],
    local: bool,
    fan: Mapping[str, Sequence[str]],
) -> list[GeneratedQuery]:
    """Exactly ``n`` questions out, whatever the buckets managed on the way in.

    ASKING FOR n DID NOT GET YOU n, AND THAT WAS THE BUG. The allocation loop
    stops at the first shape it cannot fill — a `{city}` slot nobody supplied
    makes every local shape unfillable — so a bucket that came up short simply
    came up short and the set shipped undersized. A real session asked for 30 and
    produced ELEVEN. The comparison guarantee then pushes in the other direction
    and can overshoot. Between them the set was whatever fell out, and the run's
    price, its per-cell counts and every "N questions" printed to a client were
    computed from a number nobody chose.

    Short: refill from shapes the buckets did not reach, in allocation order, so
    the top-up lands where the set is most under its target share rather than
    wherever there happened to be spare text.

    Long: drop from the most over-allocated bucket first, and NEVER drop a
    comparison — those carry the two constraints `generate_query_set` enforces
    (every competitor named somewhere, at least two questions that leave the
    client unnamed), and trimming one to hit a round number would quietly delete
    the measurement that matters most.

    Still short after the bank is exhausted: return what exists. A set of 22 is a
    problem the lint reports loudly; a set padded with duplicates is a problem
    nobody sees, and it inflates a denominator a client is quoted.
    """
    if len(queries) > n:
        droppable = [q for q in queries if q.intent is not IntentBucket.COMPARISON]
        held = [q for q in queries if q.intent is IntentBucket.COMPARISON]
        counts = Counter(q.intent for q in queries)
        # Most over its target share goes first, and within a bucket the last
        # shape added goes before the first — the bank is ordered by usefulness.
        droppable.sort(
            key=lambda q: counts[q.intent] / max(len(queries), 1) - allocation.get(q.intent, 0.0)
        )
        while len(droppable) + len(held) > n and droppable:
            droppable.pop()
        keep = {id(q) for q in droppable + held}
        return [q for q in queries if id(q) in keep]

    if len(queries) < n:
        seen = {q.text.casefold() for q in queries}
        # Allocation order, so the shortfall is filled where the set is thinnest
        # relative to what it was supposed to be.
        counts = Counter(q.intent for q in queries)
        order = sorted(
            allocation,
            key=lambda b: counts[b] / max(len(queries), 1) - allocation[b],
        )
        # THEN ANY OTHER BUCKET IN THE SAME FUNNEL, allocation or not — and
        # NEVER ONE OUTSIDE IT. The top-up used to reach into every bucket the
        # bank holds, which is how a local set with no city came back as a
        # mongrel: local and hybrid could not fill a single shape, so 13 of 25
        # questions arrived from the consumer funnel and a B2B agency was asked
        # "my digital marketing agency keeps breaking, what should I do".
        #
        # Crossing the funnel is not a drifted mix, it is a different
        # instrument. Staying inside it means a set that cannot be filled comes
        # back SHORT, which `wrong_size` blocks on and `local_without_city`
        # explains — a reviewer is told what is missing instead of being handed
        # 25 questions that look complete.
        order += [b for b in family if b not in allocation]
        for bucket in order:
            for shape in bank.get(bucket.value, []):
                if len(queries) >= n:
                    break
                if not _usable(shape, local):
                    continue
                # The top-up fans out too, so a shape the allocation only had
                # room for once can contribute the rest of its services here.
                for binding in _bindings(str(shape["shape"]), fan):
                    if len(queries) >= n:
                        break
                    text = _fill(shape["shape"], {**base_slots, **binding})
                    if text is None or text.casefold() in seen:
                        continue
                    seen.add(text.casefold())
                    counts[bucket] += 1
                    queries.append(
                        GeneratedQuery(
                            query_id=f"{_PREFIX[bucket]}-{counts[bucket]:02d}",
                            text=text,
                            intent=bucket,
                            persona=shape.get("persona", ""),
                            provenance=shape.get("provenance", "constructed"),
                            names_client=bool(base_slots["client"])
                            and base_slots["client"].casefold() in text.casefold(),
                        )
                    )
            if len(queries) >= n:
                break
    return queries


def _guarantee_comparison_coverage(
    queries: list[GeneratedQuery],
    *,
    client: str,
    competitors: Sequence[str],
    category: str = "",
) -> list[GeneratedQuery]:
    """Add whatever the allocation could not fit, rather than shipping a gap.

    An allocation is a target and the two comparison constraints are not. When
    25% of the set is not enough room for six competitors plus two unnamed
    shapes, it grows here — a slightly-off allocation is a warning, a missing
    competitor is a block, and growing is the only move that satisfies both.
    `_resize` then brings the total back to `QUERY_SET_SIZE`, and it will not
    drop a comparison to do it.
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

    # TWO UNNAMED, FROM ONE COMPETITOR IF THAT IS ALL THERE IS. This used to walk
    # `competitors` and take one shape from each, so a client who named a single
    # rival got exactly ONE unnamed question — and `no_unnamed_comparison` blocked
    # approve with a message about coverage that no amount of editing the sheet
    # could clear. Two shapes per competitor instead of one, so the pair is
    # reachable whenever there is at least one name to ask about.
    shapes = ("best alternative to {c}", "who competes with {c}")
    have_unnamed = sum(1 for q in comparison + extra if not q.names_client)
    seen = {q.text.casefold() for q in queries + extra}
    # NAMING NOBODY IS A REAL ANSWER, and it used to be a dead end. Q-PROOF-02 is
    # skippable and plenty of businesses genuinely answer "nobody, really" — but
    # with no competitors there was nothing to build a comparison from, the lint
    # blocked on `no_unnamed_comparison`, and no amount of editing the sheet could
    # clear it. These two ask the same question at category level: does the model
    # volunteer this business when it was not told the name?
    pool: Sequence[str] = competitors or [category.strip()]
    if not competitors and category.strip():
        shapes = ("who are the best {c} companies", "top {c} companies to consider")
    for shape in shapes:
        for competitor in pool:
            if have_unnamed >= 2:
                break
            text = shape.format(c=competitor)
            if text.casefold() in seen:
                continue
            seen.add(text.casefold())
            next_index += 1
            have_unnamed += 1
            extra.append(
                GeneratedQuery(
                    query_id=f"cmp-{next_index:02d}",
                    # The client is deliberately absent: this measures whether a
                    # model volunteers them when asked about the alternative.
                    text=text,
                    intent=IntentBucket.COMPARISON,
                    provenance="constructed",
                    names_client=False,
                )
            )

    return queries + extra
