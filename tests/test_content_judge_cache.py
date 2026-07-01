"""Chunk 1: the content notebook — round-trip/backends, and the ContentJudge
wire-in (warm checks reuse the cache; misses judge + store; failures aren't cached)."""

from __future__ import annotations

from src.audit.checks.content_judge import (
    CONTENT_CHECKS,
    CheckVerdict,
    ContentCheck,
    ContentClass,
    ContentJudge,
    SubAnswer,
    _unknown_verdict,
    content_cache_key,
)
from src.audit.checks.content_judge_cache import (
    InMemoryContentJudgeCache,
    NoOpContentJudgeCache,
    SupabaseContentJudgeCache,
    _from_value,
    _to_value,
    make_content_judge_cache,
)
from src.storage import db


def _verdict(check_id: str, cls: ContentClass = ContentClass.PASS) -> CheckVerdict:
    return CheckVerdict(
        check_id=check_id,
        category=3,
        classification=cls,
        reason=f"{check_id} looks good",  # NOT an uncacheable failure reason
        sub_answers=[SubAnswer("direct", "q?", "reasoning", "quote", "yes", True)],
        needs_review=False,
    )


# --- backend round-trip / selection / never-raises ---------------------------


def test_content_value_roundtrip() -> None:
    v = _verdict("answer_first_lead")
    assert _from_value(_to_value(v)) == v


def test_inmemory_and_noop() -> None:
    c = InMemoryContentJudgeCache()
    v = _verdict("definition_first")
    c.put_many([("k1", v)])
    assert c.get("k1") == v
    assert c.get_many(["k1", "miss"]) == {"k1": v}
    n = NoOpContentJudgeCache()
    n.put_many([("k1", v)])
    assert n.get("k1") is None


def test_make_content_judge_cache_backend(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src.config import settings

    monkeypatch.setattr(settings, "JUDGE_CACHE_BACKEND", "memory")
    assert isinstance(make_content_judge_cache(), InMemoryContentJudgeCache)
    monkeypatch.setattr(settings, "JUDGE_CACHE_BACKEND", "supabase")
    assert isinstance(make_content_judge_cache(), SupabaseContentJudgeCache)
    monkeypatch.setattr(settings, "JUDGE_CACHE_BACKEND", "none")
    assert isinstance(make_content_judge_cache(), NoOpContentJudgeCache)


def test_supabase_content_cache_degrades_to_miss(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def boom(_keys: list[str]) -> list[dict[str, object]]:
        raise db.StorageError("down")

    monkeypatch.setattr(db, "content_judge_cache_get_many", boom)
    assert SupabaseContentJudgeCache().get_many(["k"]) == {}  # no raise


# --- the ContentJudge wire-in ------------------------------------------------


def _judge(monkeypatch) -> tuple[ContentJudge, InMemoryContentJudgeCache]:  # type: ignore[no-untyped-def]
    from src.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key-never-called")
    cache = InMemoryContentJudgeCache()
    return ContentJudge(cache=cache), cache


def test_warm_checks_reuse_cache_without_api(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    judge, cache = _judge(monkeypatch)
    text = "A page about pricing and features."
    for c in CONTENT_CHECKS:
        cache.put(content_cache_key(judge._model, c, text), _verdict(c.check_id))

    def boom(*_a: object, **_k: object) -> object:
        raise AssertionError("judge_check called despite a fully warm cache")

    monkeypatch.setattr(judge, "judge_check", boom)
    result = judge.judge_page_text("https://x/pricing", text)
    assert result.assessed
    assert {v.check_id for v in result.verdicts} == {c.check_id for c in CONTENT_CHECKS}


def test_misses_are_judged_then_reused(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    judge, _cache = _judge(monkeypatch)
    text = "Another page."
    calls: list[str] = []

    def fake(check: ContentCheck, url: str, text: str) -> CheckVerdict:
        calls.append(check.check_id)
        return _verdict(check.check_id)

    monkeypatch.setattr(judge, "judge_check", fake)
    judge.judge_page_text("https://x/p", text)
    assert sorted(calls) == sorted(c.check_id for c in CONTENT_CHECKS)  # all judged once
    calls.clear()
    judge.judge_page_text("https://x/p", text)
    assert calls == []  # second pass is 100% cache hits


def test_failed_verdicts_are_not_cached(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    judge, cache = _judge(monkeypatch)
    text = "Yet another page."

    def failing(check: ContentCheck, url: str, text: str) -> CheckVerdict:
        return _unknown_verdict(check, "judge call failed")

    monkeypatch.setattr(judge, "judge_check", failing)
    judge.judge_page_text("https://x/p", text)
    keys = [content_cache_key(judge._model, c, text) for c in CONTENT_CHECKS]
    assert cache.get_many(keys) == {}  # transient failures never poison the notebook
