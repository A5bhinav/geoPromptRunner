from __future__ import annotations

from src.pipeline.judge import AccuracyFlag, AnswerJudgment, BrandJudgment
from src.storage.db import _judgment_to_row, _row_to_judgment


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
