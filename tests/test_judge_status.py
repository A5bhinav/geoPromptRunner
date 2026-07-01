"""The judge-status endpoint logic: reports notebook warmth (query + content) from
pure cache reads, so the UI can tell whether Judge / the report is free."""

from __future__ import annotations

from src.api import runner
from src.audit.checks.content_judge import (
    CONTENT_CHECKS,
    CheckVerdict,
    ContentClass,
    content_cache_key,
)
from src.audit.checks.content_judge_cache import InMemoryContentJudgeCache
from src.config import settings
from src.storage import db


def test_judge_status_reports_content_warmth(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # No API key → the query judge can't build, so the query block is skipped
    # (total 0) and get_query_results is never hit. We assert the CONTENT warmth.
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(
        db,
        "get_audit_run",
        lambda _r: {"client_name": "Fort", "competitors": [], "fact_sheet": None},
    )
    text = "a crawled page about pricing"
    monkeypatch.setattr(
        db, "get_site_audit_pages", lambda _r: [{"normalized_url": "u", "extracted_text": text}]
    )
    warm = InMemoryContentJudgeCache()
    for c in CONTENT_CHECKS:
        warm.put(
            content_cache_key(settings.JUDGE_MODEL, c, text),
            CheckVerdict(c.check_id, 3, ContentClass.PASS, "ok", [], False),
        )
    monkeypatch.setattr(
        "src.audit.checks.content_judge_cache.make_content_judge_cache", lambda: warm
    )

    st = runner.judge_status("run-1")
    n = len(CONTENT_CHECKS)
    assert st["query"]["total"] == 0  # judge unavailable → query block skipped
    assert st["content"] == {"total": n, "cached": n, "warm": True}


def test_judge_status_content_cold_when_uncached(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(db, "get_audit_run", lambda _r: {})
    monkeypatch.setattr(
        db, "get_site_audit_pages", lambda _r: [{"normalized_url": "u", "extracted_text": "text"}]
    )
    monkeypatch.setattr(
        "src.audit.checks.content_judge_cache.make_content_judge_cache",
        InMemoryContentJudgeCache,  # fresh empty cache
    )
    st = runner.judge_status("run-1")
    content = st["content"]
    assert isinstance(content, dict)
    assert content["total"] == len(CONTENT_CHECKS)
    assert content["cached"] == 0
    assert content["warm"] is False
