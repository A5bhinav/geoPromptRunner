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
    """A judged answer survives storage intact — flag provenance included.

    The flags carry their cell here because that is what `judge_results` produces;
    an un-stamped flag is not a shape a real judgment has. `flag_to_dict` drops
    the provenance on the way out (the judge cache is keyed per ANSWER and must
    stay byte-identical), so `_row_to_judgment` re-derives it from the row's own
    columns. Round-tripping to something LESS than the original is the bug this
    now guards: it left every stored run with anonymous flags, which stripped the
    evidence bundle off every card in the report.
    """
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
        accuracy_flags=[
            AccuracyFlag(
                "wrong_pricing",
                "$20/mo",
                "free + $5/mo",
                "high",
                query_id="cat-01",
                engine_name="openai",
                intent="category",
                run_index=0,
            )
        ],
    )
    row = _judgment_to_row("run-123", original)
    assert row["run_id"] == "run-123"
    # The stored flag dict stays at FOUR keys — widening it would re-key the
    # judge cache and invalidate every cached verdict.
    assert set(row["accuracy_flags"][0]) == {"type", "claim", "reality", "severity"}  # type: ignore[index]  # JSONB list
    # JSONB columns survive a Supabase round-trip as plain lists/dicts.
    restored = _row_to_judgment(row)
    assert restored == original
    assert restored.accuracy_flags[0].has_provenance


def test_row_to_judgment_tolerates_missing_fields() -> None:
    j = _row_to_judgment({"query_id": "q1", "engine_name": "openai"})
    assert j.query_id == "q1"
    assert j.brands == []
    assert j.accuracy_flags == []
    assert j.assessed is False


# --- Judge provenance on the run row --------------------------------------------
#
# JUDGE_MODEL is a choice that has changed and will change again, so verdicts without a
# recorded judge cannot be attributed after the fact — which is how a rendered report
# came to name a judge that had not been in use for months.


class _FakeTable:
    def __init__(self, name: str, log: list[tuple[str, str, object]]) -> None:
        self._name = name
        self._log = log

    def delete(self) -> _FakeTable:
        self._log.append((self._name, "delete", None))
        return self

    def insert(self, rows: object) -> _FakeTable:
        self._log.append((self._name, "insert", rows))
        return self

    def update(self, values: object) -> _FakeTable:
        self._log.append((self._name, "update", values))
        return self

    def eq(self, *_args: object) -> _FakeTable:
        return self

    def execute(self) -> None:
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.log: list[tuple[str, str, object]] = []

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(name, self.log)


def _one_judgment() -> AnswerJudgment:
    return AnswerJudgment(
        query_id="q1",
        engine_name="openai",
        intent="category",
        run_index=0,
        assessed=True,
        brands=[BrandJudgment("Acme", True, "mid_pack", "neutral")],
        accuracy_flags=[],
    )


def _updates(log: list[tuple[str, str, object]]) -> list[object]:
    return [values for table, op, values in log if op == "update" and table == "audit_runs"]


def test_saving_judgments_records_which_judge_produced_them(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src.storage import db

    fake = _FakeClient()
    monkeypatch.setattr(db, "_client", lambda: fake)
    db.save_judgments("run-1", [_one_judgment()], "claude-sonnet-4-5-20250929+verify:x")
    (values,) = _updates(fake.log)
    assert isinstance(values, dict)
    assert values["judge_model"] == "claude-sonnet-4-5-20250929+verify:x"


def test_an_unknown_judge_leaves_the_recorded_one_alone(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # A caller that cannot honestly name the judge (e.g. a mixed re-judge of an
    # already-judged run) must not overwrite good provenance with a guess or a blank.
    from src.storage import db

    fake = _FakeClient()
    monkeypatch.setattr(db, "_client", lambda: fake)
    db.save_judgments("run-1", [_one_judgment()])
    assert _updates(fake.log) == []
    # The verdicts themselves are still written.
    assert any(op == "insert" and table == "judgments" for table, op, _ in fake.log)


def test_failing_to_record_the_judge_does_not_fail_the_save(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # A database predating the judge_model column must lose the provenance, not the
    # verdicts — and must not report a successful save as a failure.
    from src.storage import db

    class _RejectingUpdate(_FakeClient):
        def table(self, name: str) -> _FakeTable:
            table = super().table(name)
            if name == "audit_runs":

                def _boom(_values: object) -> _FakeTable:
                    raise RuntimeError("column audit_runs.judge_model does not exist")

                table.update = _boom  # type: ignore[method-assign]
            return table

    fake = _RejectingUpdate()
    monkeypatch.setattr(db, "_client", lambda: fake)
    db.save_judgments("run-1", [_one_judgment()], "claude-sonnet-4-5-20250929")
    assert any(op == "insert" and table == "judgments" for table, op, _ in fake.log)
