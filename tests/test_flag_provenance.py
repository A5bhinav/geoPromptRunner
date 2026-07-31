"""Accuracy flags carry the cell they came from (audit-packaging-spec P0-T1).

The trap this guards: ``judge_results`` dedups verdicts by ``(prompt, answer)``,
so ONE flag list is shared by every cell whose answer text matched. Stamping
provenance anywhere but the per-cell join gives them all the first cell's engine
— a report that attributes a Gemini error to ChatGPT, which is exactly the class
of claim the audit is sold on getting right.

The second invariant here is that none of this touched the judge: the cache
payload is still four keys, so no stored verdict is invalidated.
"""

from __future__ import annotations

from src.config import settings
from src.pipeline.judge import Judge
from src.storage.models import (
    AccuracyFlag,
    QueryResult,
    flag_from_dict,
    flag_to_dict,
)


def _result(query_id: str, engine: str, prompt: str, answer: str, run_index: int = 0) -> QueryResult:
    return QueryResult(
        query_id=query_id,
        engine_name=engine,
        intent="category",
        run_index=run_index,
        prompt=prompt,
        response=answer,
        citations=[],
    )


def _judge_with_stub(monkeypatch, flags: list[AccuracyFlag]):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key-never-called")
    judge = Judge()
    # One verdict for any (prompt, answer) — the real dedup path, without a model.
    monkeypatch.setattr(judge, "judge_answer", lambda *a, **k: ([], list(flags), True))
    return judge


# --- the dedup trap -----------------------------------------------------------


def test_identical_answers_on_different_engines_get_their_own_provenance(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The same answer text from two engines must not share one engine label."""
    flag = AccuracyFlag(type="wrong_pricing", claim="$349", reality="$289", severity="high")
    judge = _judge_with_stub(monkeypatch, [flag])
    same_answer = "The Fort band costs $349."
    judgments = judge.judge_results(
        [
            _result("cat-01", "perplexity", "best wearable", same_answer),
            _result("cat-01", "gemini_grounded", "best wearable", same_answer),
        ],
        client="Fort",
        competitors=[],
        fact_sheet="pricing: $289 pre-order.",
    )
    engines = [j.accuracy_flags[0].engine_name for j in judgments]
    assert engines == ["perplexity", "gemini_grounded"]
    # And the shared source flag was not mutated in place.
    assert flag.engine_name == ""


def test_run_index_and_query_id_follow_the_cell(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    flag = AccuracyFlag(type="stale", claim="ships 2026", reality="Ships Q2 2027.", severity="high")
    judge = _judge_with_stub(monkeypatch, [flag])
    answer = "It ships in 2026."
    judgments = judge.judge_results(
        [
            _result("brd-03", "perplexity", "when does it ship", answer, run_index=0),
            _result("brd-03", "perplexity", "when does it ship", answer, run_index=2),
        ],
        client="Fort",
        competitors=[],
        fact_sheet="availability: Ships Q2 2027.",
    )
    assert [j.accuracy_flags[0].run_index for j in judgments] == [0, 2]
    assert all(j.accuracy_flags[0].query_id == "brd-03" for j in judgments)
    assert all(j.accuracy_flags[0].intent == "category" for j in judgments)


def test_stamped_flags_report_having_provenance(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    judge = _judge_with_stub(
        monkeypatch, [AccuracyFlag(type="identity", claim="a", reality="b", severity="low")]
    )
    judgments = judge.judge_results(
        [_result("cat-01", "perplexity", "q", "a")], client="Fort", competitors=[], fact_sheet="x: y"
    )
    assert judgments[0].accuracy_flags[0].has_provenance


# --- the judge cache must not have moved --------------------------------------


def test_the_cache_payload_is_still_four_keys() -> None:
    """Provenance is per-cell; the cache is per-answer. Writing it there would
    serve one cell's engine to a different cell, and would also change every
    stored verdict's bytes."""
    flag = AccuracyFlag(
        type="wrong_pricing",
        claim="$349",
        reality="$289",
        severity="high",
        query_id="cat-01",
        engine_name="perplexity",
        intent="category",
        run_index=3,
    )
    assert set(flag_to_dict(flag)) == {"type", "claim", "reality", "severity"}


def test_a_legacy_flag_dict_still_parses() -> None:
    legacy = {"type": "stale", "claim": "c", "reality": "r", "severity": "med"}
    parsed = flag_from_dict(legacy)
    assert parsed.severity == "med"
    assert parsed.query_id == "" and parsed.engine_name == ""
    assert not parsed.has_provenance


def test_a_stored_flag_round_trips_its_provenance() -> None:
    stored = {
        "type": "stale",
        "claim": "c",
        "reality": "r",
        "severity": "med",
        "query_id": "brd-03",
        "engine_name": "gemini_grounded",
        "intent": "brand",
        "run_index": "2",  # a JSON number can come back as a string
    }
    parsed = flag_from_dict(stored)
    assert parsed.run_index == 2
    assert parsed.engine_name == "gemini_grounded"
    assert parsed.has_provenance


def test_an_unparseable_run_index_does_not_crash_a_read() -> None:
    parsed = flag_from_dict(
        {"type": "t", "claim": "c", "reality": "r", "severity": "low", "run_index": "third"}
    )
    assert parsed.run_index == 0
