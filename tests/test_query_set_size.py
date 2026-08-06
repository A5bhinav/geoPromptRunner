"""Twenty-five questions, every path, every business. The size invariant.

WHY THIS FILE EXISTS. The repo used to hold four different opinions about how big
a query set is — `DEFAULT_QUERY_COUNT = 30` in the intake API, 29 in the plumbing
and HVAC templates, 28 in the barbershop one — and the set the generator actually
returned was a fifth number again, because a bucket whose shapes it could not
fill simply came up short and nobody checked. One real session asked for 30 and
produced ELEVEN.

That is not a cosmetic inconsistency. The size is the denominator under every
rate in the report, the multiplier in the cost estimate on the review screen, and
the number of cells `docs/engine-repin-spec.md` prices the whole product from.
Four sizes meant four prices for one product and four denominators under one
"mention rate".

So the rule is enforced here rather than trusted: whatever a fact sheet produces,
it produces `QUERY_SET_SIZE` questions — or it produces fewer and says why, which
is the second half of the rule and the subject of the second parametrized test.
A set padded to the right size out of the wrong funnel passes every check in this
file's first test and still measures the wrong thing.
"""

from __future__ import annotations

import collections

import pytest

from src.prompts.generate import generate_query_set
from src.prompts.intent import BUCKET_ALLOCATION, LOCAL_BUCKET_ALLOCATION, IntentBucket
from src.prompts.lint import lint_query_set
from src.prompts.local_templates import TRADES, trade_template_path
from src.prompts.query_set import QUERY_SET_SIZE, load_query_set

CLIENT = "Nahman Plumbing"
CATEGORY = "plumber"


@pytest.mark.parametrize("trade", sorted(TRADES))
def test_every_trade_template_is_the_standard_size(trade: str) -> None:
    assert len(load_query_set(trade_template_path(trade)).queries) == QUERY_SET_SIZE


@pytest.mark.parametrize("trade", sorted(TRADES))
def test_every_trade_template_carries_the_local_mix(trade: str) -> None:
    """The hand-written sets and the generated one measure the same shape of
    thing. A template at the right SIZE but the wrong mix would pass the size
    rule and still make a local audit incomparable to a generated one."""
    queries = load_query_set(trade_template_path(trade)).queries
    mix = collections.Counter(q.intent for q in queries)
    assert dict(mix) == {
        IntentBucket.LOCAL_INTENT: 11,
        IntentBucket.HYBRID: 6,
        IntentBucket.INFORMATIONAL: 5,
        IntentBucket.BRAND: 3,
    }


@pytest.mark.parametrize("trade", sorted(TRADES))
def test_resizing_a_template_bumped_its_version(trade: str) -> None:
    """A run is comparable only to a run with the SAME `query_set_version`
    (audit-packaging: only compare like instruments). Cutting four questions
    changed the instrument, so a stored v1 run must never be silently diffed
    against a v2 one — and the only thing standing between those two is this
    string."""
    assert load_query_set(trade_template_path(trade)).version.endswith("-v2")


@pytest.mark.parametrize(
    ("label", "kwargs"),
    [
        (
            "local, everything supplied",
            {
                "local": True,
                "slots": {"city": "Berkeley", "region": "California", "year": "2026"},
                "competitors": ["Ace Rooter", "Bay Plumbing"],
            },
        ),
        (
            "local, city but no region",
            {"local": True, "slots": {"city": "Berkeley"}, "competitors": []},
        ),
        ("consumer", {"local": False, "slots": {}, "competitors": ["Ace", "Bay", "Cirrus"]}),
        # The other direction: six competitors plus two unnamed shapes overflows
        # the comparison allocation, and the set has to come back DOWN to size.
        (
            "more competitors than the allocation fits",
            {"local": False, "slots": {}, "competitors": list("ABCDEF")},
        ),
    ],
)
def test_a_generated_set_is_always_the_standard_size(
    label: str, kwargs: dict[str, object]
) -> None:
    built = generate_query_set(client=CLIENT, category=CATEGORY, **kwargs)  # type: ignore[arg-type]
    assert len(built.queries) == QUERY_SET_SIZE, label


@pytest.mark.parametrize(
    ("label", "kwargs", "code"),
    [
        # The case that produced 11. Every local and hybrid shape needs `{city}`,
        # so without one the local funnel cannot fill.
        (
            "local, no city",
            {"local": True, "slots": {}, "competitors": ["Ace Rooter"]},
            "local_without_city",
        ),
        # Comparison shapes all need `{competitor}`, so a quarter of the consumer
        # funnel contributes nothing.
        ("no competitors at all", {"local": False, "slots": {}, "competitors": []}, "wrong_size"),
    ],
)
def test_a_set_that_cannot_be_filled_comes_back_short_and_blocked(
    label: str, kwargs: dict[str, object], code: str
) -> None:
    """SHORT AND BLOCKED BEATS FULL AND WRONG, and this is where that trade is
    written down.

    The size rule above used to be absolute, and the top-up honoured it by
    reaching into every bucket the bank holds — including the other funnel's.
    That is how a local set with no city came back as 25 questions of which 13
    were consumer-funnel shapes, and how a B2B agency was asked "my digital
    marketing agency keeps breaking, what should I do". A set at the right SIZE
    built from the wrong INSTRUMENT passes every check and measures the wrong
    thing, which is worse than a set that refuses to build: nobody reviews a
    number that looks right.

    So the invariant is now: `QUERY_SET_SIZE` questions, or fewer with a block
    naming what is missing. It is never padded across funnels, and it is never
    shipped short in silence.
    """
    built = generate_query_set(client=CLIENT, category=CATEGORY, **kwargs)  # type: ignore[arg-type]
    assert len(built.queries) < QUERY_SET_SIZE, label

    lint = lint_query_set(
        built,
        csv_text="",
        client=CLIENT,
        category=CATEGORY,
        competitors=[str(c) for c in (kwargs.get("competitors") or [])],  # type: ignore[union-attr]
        engines=["openai"],
        local=bool(kwargs.get("local")),
        city=str((kwargs.get("slots") or {}).get("city", "")),  # type: ignore[union-attr]
    )
    blocking = [i.code for i in lint if i.level == "block"]
    assert code in blocking, f"{label}: expected a {code} block, got {blocking}"


@pytest.mark.parametrize("allocation", [BUCKET_ALLOCATION, LOCAL_BUCKET_ALLOCATION])
def test_a_generated_set_never_repeats_a_question(allocation: object) -> None:
    """Padding to a target with duplicates would satisfy the size rule and
    corrupt every rate under it: the same question asked twice is one
    measurement counted twice, and the client is quoted for both."""
    built = generate_query_set(
        client=CLIENT,
        category=CATEGORY,
        competitors=["Ace Rooter"],
        slots={"city": "Berkeley", "region": "California"},
        allocation=allocation,  # type: ignore[arg-type]
    )
    texts = [q.text.casefold() for q in built.queries]
    assert len(set(texts)) == len(texts)


def test_resizing_never_drops_a_comparison_question() -> None:
    """The two comparison constraints outrank the size target. Trimming to a
    round number by deleting the questions that leave the client unnamed would
    remove the measurement the product is sold on — whether a model volunteers
    you when it wasn't told your name."""
    built = generate_query_set(
        client=CLIENT,
        category=CATEGORY,
        competitors=list("ABCDEF"),
        slots={},
    )
    comparisons = [q for q in built.queries if q.intent is IntentBucket.COMPARISON]
    uncovered = [
        c for c in "ABCDEF" if not any(c.casefold() in q.text.casefold() for q in comparisons)
    ]
    assert uncovered == []
    assert len([q for q in comparisons if not q.names_client]) >= 2
    assert len(built.queries) == QUERY_SET_SIZE


def test_two_unnamed_comparisons_are_reachable_from_one_competitor() -> None:
    """THE BUG THAT BLOCKED A REAL APPROVE. The unnamed-comparison guarantee used
    to take one shape per competitor, so a client who named a single rival got
    exactly ONE — and `no_unnamed_comparison` disabled Approve with a message no
    amount of editing the sheet could clear."""
    built = generate_query_set(
        client="Black Propeller",
        category="Digital Marketing Agency",
        competitors=["Tinuiti"],
        slots={},
    )
    unnamed = [
        q
        for q in built.queries
        if q.intent is IntentBucket.COMPARISON and not q.names_client
    ]
    assert len(unnamed) >= 2


def test_naming_nobody_still_produces_two_unnamed_comparisons() -> None:
    """Q-PROOF-02 is skippable and "nobody, really" is a real answer. With no
    competitors there was nothing to build a comparison from and approve was a
    dead end; these ask the same question at category level."""
    built = generate_query_set(
        client="Black Propeller",
        category="Digital Marketing Agency",
        competitors=[],
        slots={},
    )
    unnamed = [
        q
        for q in built.queries
        if q.intent is IntentBucket.COMPARISON and not q.names_client
    ]
    assert len(unnamed) >= 2
    assert all("Black Propeller".casefold() not in q.text.casefold() for q in unnamed)


# --- the ceiling, and what lifts it -------------------------------------------

_SERVICES = [
    "drain cleaning",
    "water heater install",
    "repiping",
    "leak detection",
    "sewer inspection",
    "trenchless repair",
]
_AREAS = ["Albany", "Oakland", "El Cerrito"]


def test_without_fanout_lists_the_bank_cannot_reach_fifty() -> None:
    """THE CEILING IS THE NUMBER OF LINES IN THE BANK, and this is where that is
    written down so a future `QUERY_SET_SIZE = 50` fails here rather than in
    production.

    Every slot except the fan-out ones is single-valued — one category, one city,
    one year — so a shape yields exactly ONE question however rich the sheet is.
    The maximum size of a set is therefore the number of usable shapes, plus the
    comparison shapes times the competitor count. Measured at ~30 for a general
    business with two competitors, which is why asking for 50 could not work.
    """
    built = generate_query_set(
        client=CLIENT, category=CATEGORY, competitors=["Ace Rooter", "Bay Plumbing"], n=200
    )
    assert len(built.queries) < 50


def test_fanout_lists_lift_the_ceiling_past_fifty() -> None:
    """One shape times six services is six questions, so the sheet's own lists —
    not the length of the bank — set the size. This is what makes a 50-question
    instrument reachable, and it does it with questions that are MORE specific
    rather than merely more numerous."""
    built = generate_query_set(
        client=CLIENT,
        category=CATEGORY,
        competitors=["Ace Rooter", "Bay Plumbing"],
        slots={"city": "Berkeley", "region": "California", "year": "2026"},
        lists={"service": _SERVICES, "area": _AREAS},
        n=200,
        local=True,
    )
    assert len(built.queries) > 50
    assert any("drain cleaning" in q.text for q in built.queries)


def test_fanout_covers_every_value_before_repeating_one() -> None:
    """Breadth first. A bucket almost always truncates, so the ORDER decides what
    the set covers: a nested product walked every town for the first service
    before touching the second, covering two services out of six. Every service
    must be seen once before any is seen twice."""
    built = generate_query_set(
        client=CLIENT,
        category=CATEGORY,
        competitors=["Ace Rooter"],
        slots={"city": "Berkeley", "region": "California", "year": "2026"},
        lists={"service": _SERVICES, "area": _AREAS},
        n=QUERY_SET_SIZE,
        local=True,
    )
    texts = [q.text for q in built.queries]
    per_service = {s: sum(1 for t in texts if s in t) for s in _SERVICES}
    seen = [s for s, k in per_service.items() if k]
    twice = [s for s, k in per_service.items() if k > 1]
    assert len(seen) > len(twice), f"depth-first coverage: {per_service}"


def test_a_fanout_slot_with_no_values_yields_nothing() -> None:
    """Never partially filled — the same rule as an unfilled `{city}`. A sheet
    with no service list must not produce "best plumber for ." """
    built = generate_query_set(
        client=CLIENT,
        category=CATEGORY,
        competitors=["Ace Rooter"],
        lists={"service": [], "area": []},
        n=QUERY_SET_SIZE,
    )
    assert all("{" not in q.text for q in built.queries)
    assert all(not q.text.endswith(" for") for q in built.queries)


def test_the_same_inputs_always_give_the_same_set() -> None:
    """The set is the instrument. Two cycles that disagree about which questions
    they contain are two instruments, and the fan-out product order is the newest
    way that could have stopped being true."""
    kwargs = dict(
        client=CLIENT,
        category=CATEGORY,
        competitors=["Ace Rooter", "Bay Plumbing"],
        slots={"city": "Berkeley", "region": "California", "year": "2026"},
        lists={"service": _SERVICES, "area": _AREAS},
        n=QUERY_SET_SIZE,
        local=True,
    )
    first = [q.text for q in generate_query_set(**kwargs).queries]  # type: ignore[arg-type]
    second = [q.text for q in generate_query_set(**kwargs).queries]  # type: ignore[arg-type]
    assert first == second
