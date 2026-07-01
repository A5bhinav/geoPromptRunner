"""Judge notebook (cache) backends: round-trip, batching, backend selection, and
the 'never raises into a run' contract for the Supabase backend."""

from __future__ import annotations

from src.pipeline.judge_cache import (
    InMemoryJudgeCache,
    NoOpJudgeCache,
    SupabaseJudgeCache,
    Verdict,
    _from_value,
    _to_value,
    make_judge_cache,
)
from src.storage import db
from src.storage.models import AccuracyFlag, BrandJudgment

_VERDICT: Verdict = (
    [BrandJudgment(brand="Fort", present=True, prominence="mid_pack", framing="neutral")],
    [AccuracyFlag(type="wrong_pricing", claim="$349", reality="$289", severity="high")],
    True,
)


def test_value_roundtrip_preserves_verdict() -> None:
    assert _from_value(_to_value(_VERDICT)) == _VERDICT


def test_inmemory_put_get_and_batch() -> None:
    c = InMemoryJudgeCache()
    c.put_many([("k1", _VERDICT), ("k2", ([], [], False))])
    assert c.get("k1") == _VERDICT
    assert c.get("missing") is None
    # get_many returns only the present keys, decoded.
    got = c.get_many(["k1", "k2", "missing"])
    assert set(got) == {"k1", "k2"}
    assert got["k1"] == _VERDICT


def test_noop_always_misses() -> None:
    c = NoOpJudgeCache()
    c.put_many([("k1", _VERDICT)])
    assert c.get("k1") is None
    assert c.get_many(["k1"]) == {}


def test_make_judge_cache_selects_backend(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src.config import settings

    monkeypatch.setattr(settings, "JUDGE_CACHE_BACKEND", "memory")
    assert isinstance(make_judge_cache(), InMemoryJudgeCache)
    monkeypatch.setattr(settings, "JUDGE_CACHE_BACKEND", "supabase")
    assert isinstance(make_judge_cache(), SupabaseJudgeCache)
    monkeypatch.setattr(settings, "JUDGE_CACHE_BACKEND", "none")
    assert isinstance(make_judge_cache(), NoOpJudgeCache)
    # An unknown backend disables rather than crashing.
    monkeypatch.setattr(settings, "JUDGE_CACHE_BACKEND", "bogus")
    assert isinstance(make_judge_cache(), NoOpJudgeCache)


def test_supabase_put_and_get_via_db(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """SupabaseJudgeCache writes {key,value} rows through db.judge_cache_put_many and
    decodes rows from db.judge_cache_get_many — without touching a real Supabase."""
    store: dict[str, object] = {}

    def fake_put(rows: list[dict[str, object]]) -> None:
        for r in rows:
            store[str(r["key"])] = r["value"]

    def fake_get(keys: list[str]) -> list[dict[str, object]]:
        return [{"key": k, "value": store[k]} for k in keys if k in store]

    monkeypatch.setattr(db, "judge_cache_put_many", fake_put)
    monkeypatch.setattr(db, "judge_cache_get_many", fake_get)

    c = SupabaseJudgeCache()
    c.put_many([("k1", _VERDICT)])
    assert store["k1"] == _to_value(_VERDICT)  # the JSON-safe stored form
    assert c.get("k1") == _VERDICT
    assert c.get_many(["k1", "nope"]) == {"k1": _VERDICT}


def test_supabase_read_error_degrades_to_miss(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A Supabase failure on read must degrade to a cache MISS, never raise into a run."""

    def boom(_keys: list[str]) -> list[dict[str, object]]:
        raise db.StorageError("supabase down")

    monkeypatch.setattr(db, "judge_cache_get_many", boom)
    c = SupabaseJudgeCache()
    assert c.get_many(["k1"]) == {}  # no exception
    assert c.get("k1") is None


def test_supabase_write_error_is_swallowed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A Supabase failure on write must be swallowed (the run continues; the answer
    is simply re-judged later), never raised."""

    def boom(_rows: list[dict[str, object]]) -> None:
        raise db.StorageError("supabase down")

    monkeypatch.setattr(db, "judge_cache_put_many", boom)
    c = SupabaseJudgeCache()
    c.put_many([("k1", _VERDICT)])  # must not raise


def test_supabase_skips_corrupt_row(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A malformed stored row is skipped (treated as a miss for that key), not fatal."""

    def fake_get(keys: list[str]) -> list[dict[str, object]]:
        return [{"key": "good", "value": _to_value(_VERDICT)}, {"key": "bad", "value": {"nope": 1}}]

    monkeypatch.setattr(db, "judge_cache_get_many", fake_get)
    c = SupabaseJudgeCache()
    got = c.get_many(["good", "bad"])
    assert got == {"good": _VERDICT}
