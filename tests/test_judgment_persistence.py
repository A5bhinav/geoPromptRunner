from __future__ import annotations

from src.pipeline.judge import AccuracyFlag, AnswerJudgment, BrandJudgment
from src.storage.db import (
    _judgment_to_row,
    _query_citation_rows,
    _query_result_rows,
    _row_to_judgment,
)


def _qr(query_id: str, engine: str, run_index: int, citations: list[str]) -> dict:
    return {
        "query_id": query_id,
        "intent": "category",
        "prompt": "best smart ring",
        "engine_name": engine,
        "run_index": run_index,
        "response": f"answer {run_index}",
        "citations": citations,
        "timestamp": "2026-07-04T00:00:00Z",
    }


def test_query_result_rows_have_unique_deterministic_ids() -> None:
    results = [_qr("q1", "mock", i, []) for i in range(3)]
    rows = _query_result_rows("run-1", results)
    ids = [r["id"] for r in rows]
    assert len(rows) == 3
    assert len(set(ids)) == 3  # one per (query, engine, run_index)
    # Deterministic: rebuilding the same batch yields the same ids (idempotent upsert).
    assert [r["id"] for r in _query_result_rows("run-1", results)] == ids


def test_query_citation_rows_dedupe_repeated_url_across_runs() -> None:
    # The SAME url cited in every run of a cell must collapse to ONE row — else a
    # single upsert targets the same conflict key twice and Postgres rejects it.
    results = [_qr("q1", "mock", i, ["https://reddit.com/r/x"]) for i in range(3)]
    rows = _query_citation_rows("run-1", results)
    assert len(rows) == 1
    assert len({r["id"] for r in rows}) == len(rows)  # no duplicate conflict keys
    # Two distinct urls in one cell -> two rows, still unique ids.
    two = _query_citation_rows("run-1", [_qr("q1", "mock", 0, ["https://a.com", "https://b.com"])])
    assert len(two) == 2
    assert len({r["id"] for r in two}) == 2


def test_judgment_row_round_trip() -> None:
    original = AnswerJudgment(
        query_id="cat-01",
        engine_name="openai",
        intent="category",
        run_index=0,
        assessed=True,
        brands=[
            BrandJudgment("Centsible", True, "buried", "negative"),
            BrandJudgment("YNAB", True, "recommended_first", "positive"),
        ],
        accuracy_flags=[AccuracyFlag("wrong_pricing", "$20/mo", "free + $5/mo", "high")],
    )
    row = _judgment_to_row("run-123", original)
    assert row["run_id"] == "run-123"
    # JSONB columns survive a Supabase round-trip as plain lists/dicts.
    restored = _row_to_judgment(row)
    assert restored == original


def test_row_to_judgment_tolerates_missing_fields() -> None:
    j = _row_to_judgment({"query_id": "q1", "engine_name": "openai"})
    assert j.query_id == "q1"
    assert j.brands == []
    assert j.accuracy_flags == []
    assert j.assessed is False
