"""The question-set lint — ``docs/query-generation-plan.md`` §5, automated.

Two levels and they mean different things:

* ``block`` — approve is DISABLED and the reason is stated. These are the checks
  where shipping anyway produces a wrong measurement, not a scruffy one.
* ``warn`` — shown, never blocking. Balance, near-duplicates and sourcing are
  judgement calls, and a lint that blocks on judgement calls gets bypassed.

THE LAST CHECK IS THE ONLY ONE THAT MATTERS. Everything above it exists to
produce a better message; ``round_trips`` generates the CSV and then parses it
with the exact function ``POST /audits`` will use. If that does not come back
clean, nothing else about the set is worth discussing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.prompts.csv_loader import KNOWN_ENGINES, REQUIRED_CONFIG_KEYS, parse_csv_files
from src.prompts.generate import GeneratedQuery, QuerySet
from src.prompts.intent import IntentBucket
from src.prompts.query_set import QUERY_SET_SIZE

__all__ = ["LintItem", "lint_query_set", "ABBREVIATED_REGION_RE"]

#: Same shape `assemble.py` refuses on, restated here because the lint runs on
#: hand-edited sets that never went through the assembler.
ABBREVIATED_REGION_RE = re.compile(r"^[A-Za-z]{2}\.?$")

_UNFILLED_SLOT = re.compile(r"\{[a-z_]+\}")

#: How far a bucket may drift from its target share before it is worth saying.
_ALLOCATION_TOLERANCE = 0.20


@dataclass(frozen=True, kw_only=True)
class LintItem:
    level: str  # "block" | "warn"
    message: str
    #: The check's stable name, so a UI can suppress or link one without
    #: string-matching the prose.
    code: str


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.casefold()).split())


def _near_duplicates(queries: Sequence[GeneratedQuery]) -> list[tuple[str, str]]:
    """Pairs that differ by less than a fifth of their length.

    A token-set ratio rather than an edit distance: "best plumber in Berkeley"
    and "best plumber Berkeley California" are the same question and a
    character-level distance says otherwise.
    """
    pairs: list[tuple[str, str]] = []
    tokens = {q.query_id: set(_normalize(q.text).split()) for q in queries}
    ids = [q.query_id for q in queries]
    for i, left in enumerate(ids):
        for right in ids[i + 1 :]:
            a, b = tokens[left], tokens[right]
            if not a or not b:
                continue
            overlap = len(a & b) / len(a | b)
            if overlap >= 0.8:
                pairs.append((left, right))
    return pairs


def lint_query_set(
    query_set: QuerySet,
    *,
    csv_text: str,
    client: str,
    category: str,
    competitors: Sequence[str],
    engines: Sequence[str],
    region: str = "",
    allocation: Mapping[IntentBucket, float] | None = None,
    local: bool = False,
    city: str = "",
) -> list[LintItem]:
    """Every check, most severe first. An empty list means approve is allowed."""
    out: list[LintItem] = []
    queries = list(query_set.queries)
    allocation = allocation or query_set.allocation

    # --- blocks ---------------------------------------------------------------

    if not queries:
        out.append(
            LintItem(
                level="block",
                code="empty_set",
                message="The question set is empty. A run with no questions measures nothing.",
            )
        )
    elif len(queries) != QUERY_SET_SIZE:
        # A BLOCK, NOT A WARNING. Every audit asks the same number of questions,
        # because that number is the denominator under every rate in the report
        # and the multiplier in the price quoted for the run. A set of 22 sold
        # against a cost estimate for 25 is a wrong invoice; a set of 29 compared
        # against a set of 25 is two different instruments reported as one trend.
        #
        # It reads as a warning-shaped problem and is not: the generator can hit
        # the size on every path it has, so a set that misses it was hand-edited
        # or came from a template nobody resized, and both need a person.
        out.append(
            LintItem(
                level="block",
                code="wrong_size",
                message=(
                    f"The set has {len(queries)} questions; every audit asks "
                    f"{QUERY_SET_SIZE}. Add or remove {abs(len(queries) - QUERY_SET_SIZE)} "
                    "— the cost estimate and every rate in the report are computed "
                    "from that number."
                ),
            )
        )

    seen: set[str] = set()
    duplicates: set[str] = set()
    for q in queries:
        if q.query_id in seen:
            duplicates.add(q.query_id)
        seen.add(q.query_id)
    duplicate_ids = sorted(duplicates)
    if duplicate_ids:
        out.append(
            LintItem(
                level="block",
                code="duplicate_ids",
                message=(
                    f"Duplicate question ids: {', '.join(duplicate_ids)}. "
                    "The parser rejects the file, and results would collide on the id."
                ),
            )
        )

    bad_intent = [q.query_id for q in queries if q.intent not in set(IntentBucket)]
    if bad_intent:
        out.append(
            LintItem(
                level="block",
                code="invalid_intent",
                message=(
                    f"{len(bad_intent)} question(s) carry an intent the parser does not "
                    "recognise. Every question needs exactly one valid intent."
                ),
            )
        )

    unfilled = [q.query_id for q in queries if _UNFILLED_SLOT.search(q.text)]
    if unfilled:
        out.append(
            LintItem(
                level="block",
                code="unfilled_slot",
                message=(
                    f"{len(unfilled)} question(s) still contain an unfilled placeholder "
                    f"({', '.join(unfilled[:3])}). A literal {{city}} reaching an engine "
                    "scores as a loss on a question nobody asked."
                ),
            )
        )

    comparison = [q for q in queries if q.intent is IntentBucket.COMPARISON]
    missing = [
        c
        for c in competitors
        if c.strip() and not any(c.casefold() in q.text.casefold() for q in comparison)
    ]
    if missing:
        out.append(
            LintItem(
                level="block",
                code="competitor_uncovered",
                message=(
                    f"No comparison question mentions {', '.join(missing)}. "
                    "Every competitor you named needs at least one."
                ),
            )
        )

    unnamed = [q for q in comparison if not q.names_client]
    if len(unnamed) < 2:
        out.append(
            LintItem(
                level="block",
                code="no_unnamed_comparison",
                message=(
                    f"Only {len(unnamed)} comparison question leaves {client or 'the client'} "
                    "unnamed; two are needed. These are the ones that test whether a model "
                    "volunteers you unprompted, which is the measurement that matters most."
                ),
            )
        )

    # SEVERAL NAMES IN ONE FIELD IS NOT ONE COMPETITOR. The chip control does
    # not split on commas — "Berkeley, Albany" is one service area — so six
    # agencies typed into one chip arrived as a single name and produced
    # "{client} vs A, B, C, D, E, F" as one question. `_as_names` splits this at
    # the intake boundary; this is the backstop for a hand-edited CSV, where
    # nothing has.
    joined = [c for c in competitors if re.search(r"[,;]", c)]
    if joined:
        out.append(
            LintItem(
                level="block",
                code="competitor_list_in_one_field",
                message=(
                    f"{joined[0]!r} looks like several competitors in one field. Each name "
                    "needs its own entry — a comma-joined string becomes one question no "
                    "buyer would ask, and it costs you a head-to-head for every name in it."
                ),
            )
        )

    # A LOCAL SET IS BUILT AROUND A CITY. Without one, every geo shape in the
    # bank is unfillable, the local and hybrid buckets collapse, and the set
    # gets topped up from whatever else the bank holds. That is how a set
    # allocated 45% local intent shipped with one local question in it.
    if local and not city.strip():
        out.append(
            LintItem(
                level="block",
                code="local_without_city",
                message=(
                    "This is a local business but no city was given. Local questions are "
                    "built around one — without it the set cannot ask the questions that "
                    "decide a local audit. Answer the service-area card, or say the "
                    "business is not location-dependent."
                ),
            )
        )

    if region and ABBREVIATED_REGION_RE.match(region.strip()):
        out.append(
            LintItem(
                level="block",
                code="abbreviated_region",
                message=(
                    f"The state is {region!r}. Use the full name ('California', not 'CA') — "
                    "the SERP vendors reject the short form and return an empty surface, "
                    "which reads downstream as the brand being absent."
                ),
            )
        )

    for key, value in (("client_name", client), ("category", category)):
        if key in REQUIRED_CONFIG_KEYS and not value.strip():
            out.append(
                LintItem(
                    level="block",
                    code=f"missing_{key}",
                    message=f"The run config has no {key}. The parser refuses the file without it.",
                )
            )

    unknown_engines = sorted({e for e in engines if e not in KNOWN_ENGINES})
    if unknown_engines:
        out.append(
            LintItem(
                level="block",
                code="unknown_engine",
                message=(
                    f"Unknown surface(s): {', '.join(unknown_engines)}. "
                    "The run would be refused before it started."
                ),
            )
        )

    # THE CHECK THAT ACTUALLY GATES. Generate, then parse your own output with
    # the exact function POST /audits uses.
    parsed = parse_csv_files([("generated.csv", csv_text)])
    if not parsed.ok:
        detail = "; ".join(e.message for e in parsed.errors[:3])
        out.append(
            LintItem(
                level="block",
                code="csv_round_trip",
                message=f"The generated CSV does not parse: {detail}",
            )
        )

    # --- warnings -------------------------------------------------------------

    total = len(queries)
    if total:
        by_bucket = query_set.by_bucket()
        for bucket, share in allocation.items():
            actual = len(by_bucket.get(bucket, [])) / total
            if abs(actual - share) > _ALLOCATION_TOLERANCE:
                out.append(
                    LintItem(
                        level="warn",
                        code="allocation_drift",
                        message=(
                            f"{bucket.value.replace('_', ' ')} is {actual:.0%} of the set, "
                            f"against a target of {share:.0%}."
                        ),
                    )
                )

        named_outside = [
            q
            for q in queries
            if q.names_client and q.intent not in {IntentBucket.BRAND, IntentBucket.COMPARISON}
        ]
        if named_outside:
            out.append(
                LintItem(
                    level="warn",
                    code="client_named_too_widely",
                    message=(
                        f"{len(named_outside)} question(s) outside the brand and comparison "
                        "stages name the client. Those can only measure how well a model "
                        "reads a prompt back."
                    ),
                )
            )

        # A QUESTION THAT NAMES NEITHER YOU NOR YOUR CATEGORY CAN ONLY MEASURE A
        # VOLUNTEERED MENTION. That is a legitimate test — §3.1's problem-aware
        # questions are meant to describe a pain and name nothing — but it is
        # only a test if the pain is specific. "how do I stop this from
        # happening again" names nothing and describes nothing: no answer to it
        # could mention the client, so it scores a guaranteed zero and still
        # counts in the denominator of every rate the client is shown. Warned,
        # not blocked, because the honest version of this question is one of the
        # most valuable in the set.
        anchors = [a.casefold() for a in (client, category) if a.strip()]
        floating = [
            q.query_id for q in queries if not any(a in q.text.casefold() for a in anchors)
        ]
        if floating:
            out.append(
                LintItem(
                    level="warn",
                    code="unanchored_query",
                    message=(
                        f"{len(floating)} question(s) name neither {client or 'the client'} nor "
                        f"the category ({', '.join(floating[:3])}). Those only score if a model "
                        "volunteers the brand — check each one describes a real, specific "
                        "problem rather than a pronoun with no antecedent."
                    ),
                )
            )

        sourced = sum(1 for q in queries if q.provenance in {"verbatim", "near_verbatim"})
        if sourced / total < 1 / 3:
            out.append(
                LintItem(
                    level="warn",
                    code="thin_sourcing",
                    message=(
                        f"Only {sourced} of {total} questions come from real buyer language. "
                        "The methodology asks for at least a third."
                    ),
                )
            )

    for left, right in _near_duplicates(queries):
        out.append(
            LintItem(
                level="warn",
                code="near_duplicate",
                message=(
                    f"{left} and {right} are near-duplicates. Merge them, or leave them "
                    "and spend the extra calls."
                ),
            )
        )

    return sorted(out, key=lambda i: 0 if i.level == "block" else 1)
