from __future__ import annotations

from datetime import UTC, datetime

from src.engines.base import BaseEngine
from src.pipeline.cost import estimate_cost
from src.pipeline.metrics import competitive_ranking
from src.pipeline.trend import due_for_rerun
from src.storage.models import QueryResult


class _Eng(BaseEngine):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def ENGINE_NAME(self) -> str:  # type: ignore[override]
        return self._name

    def query(self, prompt: str) -> str | None:
        return None


def test_estimate_cost_counts_and_sums() -> None:
    engines = [_Eng("openai"), _Eng("openai_search")]  # 0.01 + 0.03 per query
    estimated, calls = estimate_cost(10, engines, 3)
    assert calls == 60  # 10 x 2 x 3
    assert round(estimated, 3) == round((0.01 + 0.03) * 10 * 3, 3)  # 1.2


def test_due_for_rerun() -> None:
    now = datetime(2026, 6, 1, tzinfo=UTC)
    assert due_for_rerun("2026-04-01T00:00:00+00:00", cadence_days=42, now=now) is True
    assert due_for_rerun("2026-05-25T00:00:00+00:00", cadence_days=42, now=now) is False
    assert due_for_rerun("", now=now) is True  # no prior run -> due
    assert due_for_rerun("not-a-date", now=now) is True


def _qr(qid: str, resp: str | None) -> QueryResult:
    return QueryResult(
        query_id=qid,
        intent="category",
        prompt="(mock)",
        engine_name="openai",
        run_index=0,
        response=resp,
        citations=[],
        timestamp="t",
    )


def test_competitive_ranking_orders_by_mention_rate() -> None:
    results = [
        _qr("q1", "Monarch Money and Acme are options."),
        _qr("q2", "Monarch Money is the leader."),
    ]
    ranking = competitive_ranking(results, ["Acme", "Monarch Money"])
    assert ranking[0][0] == "Monarch Money"  # in 2/2 cells
    assert ranking[1][0] == "Acme"  # in 1/2
