"""The template-bank generator and the question-set lint.

Deterministic and free: no bank entry is written by a model and no check calls
one. The two constraints the generator enforces itself — every competitor
covered, at least two comparisons leaving the client unnamed — are tested here
AND re-checked by the lint, because the lint is the backstop for a hand-edited
set and the generator is the guarantee for a fresh one.
"""

from __future__ import annotations

import csv
import io

from src.prompts.csv_loader import parse_csv_files
from src.prompts.generate import generate_query_set
from src.prompts.intent import BUCKET_ALLOCATION, LOCAL_BUCKET_ALLOCATION, IntentBucket
from src.prompts.lint import lint_query_set

CLIENT = "Albert Nahman Plumbing"
CATEGORY = "plumbing contractor"
COMPETITORS = ["Cabrillo Plumbing", "Ace Plumbing", "Bay Area Plumbing"]
SLOTS = {"city": "Berkeley", "region": "California", "year": "2026"}


def _generate(**overrides: object) -> object:
    kwargs: dict[str, object] = {
        "client": CLIENT,
        "category": CATEGORY,
        "competitors": COMPETITORS,
        "slots": SLOTS,
        # No explicit `n`: the default IS the standard size, and a fixture that
        # pinned 30 was asserting the drift this repo just removed — the lint now
        # blocks any set that is not `QUERY_SET_SIZE`.
    }
    kwargs.update(overrides)
    return generate_query_set(**kwargs)  # type: ignore[arg-type]  # literal mapping above


def _csv_of(query_set: object, *, competitors: list[str] | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(("block", "key", "value", "intent", "persona"))
    writer.writerow(("config", "client_name", CLIENT, "", ""))
    writer.writerow(("config", "category", CATEGORY, "", ""))
    writer.writerow(("config", "competitors", ";".join(competitors or COMPETITORS), "", ""))
    writer.writerow(("config", "engines", "openai", "", ""))
    for q in query_set.queries:  # type: ignore[attr-defined]
        writer.writerow(("query", q.query_id, q.text, q.intent.value, q.persona))
    return buffer.getvalue()


# --- the generator ------------------------------------------------------------


def test_generation_is_deterministic() -> None:
    """Same inputs, same set, same ids.

    Not a nicety: a generated set is the measuring instrument, and two cycles
    are comparable only if the instrument did not move between them.
    """
    first = _generate()
    second = _generate()
    assert [q.query_id for q in first.queries] == [q.query_id for q in second.queries]  # type: ignore[attr-defined]
    assert [q.text for q in first.queries] == [q.text for q in second.queries]  # type: ignore[attr-defined]


def test_no_query_ships_with_an_unfilled_slot() -> None:
    """A literal {city} reaching an engine scores as a loss on a question nobody
    asked — worse than a shorter set."""
    generated = _generate(slots={"city": "", "region": "", "year": "2026"})
    for q in generated.queries:  # type: ignore[attr-defined]
        assert "{" not in q.text and "}" not in q.text


def test_every_competitor_gets_a_comparison_question() -> None:
    generated = _generate()
    comparison = [
        q for q in generated.queries if q.intent is IntentBucket.COMPARISON  # type: ignore[attr-defined]
    ]
    for competitor in COMPETITORS:
        assert any(competitor.casefold() in q.text.casefold() for q in comparison), competitor


def test_at_least_two_comparisons_leave_the_client_unnamed() -> None:
    """These test unprompted surfacing, which is the measurement that matters
    most. A set where the client is named everywhere can only measure how well a
    model reads a prompt back."""
    generated = _generate()
    unnamed = [
        q
        for q in generated.queries  # type: ignore[attr-defined]
        if q.intent is IntentBucket.COMPARISON and not q.names_client
    ]
    assert len(unnamed) >= 2


def test_coverage_wins_over_the_allocation_when_they_conflict() -> None:
    """An allocation is a target; the two comparison constraints are not. With
    six competitors and no room, the SET GROWS rather than dropping one."""
    many = [f"Competitor {i}" for i in range(8)]
    generated = _generate(competitors=many, n=20)
    comparison = [
        q for q in generated.queries if q.intent is IntentBucket.COMPARISON  # type: ignore[attr-defined]
    ]
    for competitor in many:
        assert any(competitor.casefold() in q.text.casefold() for q in comparison), competitor


def test_the_local_allocation_produces_local_buckets() -> None:
    """The fallback for a trade with no hand-written template. Same bank, a
    different allocation — which is why the generator takes one."""
    generated = _generate(local=True, allocation=LOCAL_BUCKET_ALLOCATION)
    buckets = {q.intent for q in generated.queries}  # type: ignore[attr-defined]
    assert IntentBucket.LOCAL_INTENT in buckets
    assert IntentBucket.PROBLEM_AWARE not in buckets


def test_the_default_allocation_is_the_consumer_funnel() -> None:
    generated = _generate()
    buckets = {q.intent for q in generated.queries}  # type: ignore[attr-defined]
    assert buckets <= set(BUCKET_ALLOCATION)


# --- the lint -----------------------------------------------------------------


def _lint(query_set: object, **overrides: object) -> list[object]:
    kwargs: dict[str, object] = {
        "csv_text": _csv_of(query_set),
        "client": CLIENT,
        "category": CATEGORY,
        "competitors": COMPETITORS,
        "engines": ["openai"],
        "region": "California",
    }
    kwargs.update(overrides)
    return lint_query_set(query_set, **kwargs)  # type: ignore[arg-type]  # literal mapping above


def _codes(items: list[object], level: str) -> set[str]:
    return {i.code for i in items if i.level == level}  # type: ignore[attr-defined]


def test_a_clean_generated_set_has_no_blocks() -> None:
    """The whole point of generating rather than hand-writing: the output of the
    generator must be approvable without edits."""
    generated = _generate()
    assert _codes(_lint(generated), "block") == set()


def test_a_missing_competitor_blocks() -> None:
    generated = _generate(competitors=["Cabrillo Plumbing"])
    items = _lint(generated, competitors=["Cabrillo Plumbing", "Nobody Plumbing"])
    assert "competitor_uncovered" in _codes(items, "block")


def test_an_abbreviated_region_blocks_with_the_real_reason() -> None:
    """"CA" is not a typo the vendors correct — they return an EMPTY surface,
    which reads downstream as the brand being absent."""
    generated = _generate()
    items = _lint(generated, region="CA")
    assert "abbreviated_region" in _codes(items, "block")
    message = next(i.message for i in items if i.code == "abbreviated_region")  # type: ignore[attr-defined]
    assert "empty surface" in message


def test_a_surviving_placeholder_blocks() -> None:
    generated = _generate()
    broken = type(generated)(  # type: ignore[operator]
        queries=(
            *generated.queries[:-1],  # type: ignore[attr-defined]
            type(generated.queries[0])(  # type: ignore[attr-defined]
                query_id="cat-99",
                text="best {category} in Berkeley",
                intent=IntentBucket.CATEGORY,
            ),
        ),
        allocation=generated.allocation,  # type: ignore[attr-defined]
    )
    assert "unfilled_slot" in _codes(_lint(broken), "block")


def test_an_unknown_surface_blocks() -> None:
    generated = _generate()
    assert "unknown_engine" in _codes(_lint(generated, engines=["chatgpt5"]), "block")


def test_a_missing_required_config_key_blocks() -> None:
    generated = _generate()
    assert "missing_category" in _codes(_lint(generated, category=""), "block")


def test_the_round_trip_is_the_check_that_actually_gates() -> None:
    """Generate, then parse your own output with the exact function POST /audits
    uses. If that does not come back clean, nothing else matters."""
    generated = _generate()
    csv_text = _csv_of(generated)
    parsed = parse_csv_files([("generated.csv", csv_text)])
    assert parsed.ok, [e.message for e in parsed.errors]
    assert parsed.audit is not None
    assert len(parsed.audit.query_set.queries) == len(generated.queries)  # type: ignore[attr-defined]
    # And no fact block: the sheet travels by fact_sheet_id, and a run carrying
    # both is refused.
    assert parsed.audit.fact_sheet is None


def test_a_broken_csv_blocks_even_when_every_other_check_passes() -> None:
    generated = _generate()
    assert "csv_round_trip" in _codes(_lint(generated, csv_text="not,a,valid\ncsv"), "block")


def test_near_duplicates_warn_and_never_block() -> None:
    """Balance and duplication are judgement calls, and a lint that blocks on
    judgement calls gets bypassed."""
    generated = _generate()
    items = _lint(generated)
    assert "near_duplicate" not in _codes(items, "block")
