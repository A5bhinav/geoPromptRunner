"""Chunk 0: the subjective ContentJudge is wired into the site audit — its verdicts
become llm-method check rows and feed the roadmap; it degrades off cleanly."""

from __future__ import annotations

from src.audit.checks.content_judge import (
    CheckVerdict,
    ContentClass,
    ContentJudgeResult,
    SubAnswer,
)
from src.audit.site_audit import _make_content_judge, _run_content_judge


class _FakePage:
    url = "https://example.com/pricing"


class _FakeJudge:
    """Stands in for ContentJudge — returns canned verdicts, no API call."""

    def __init__(self, verdicts: list[CheckVerdict]) -> None:
        self._verdicts = verdicts

    def judge_page(self, page: object) -> ContentJudgeResult:
        return ContentJudgeResult(
            page_url="https://example.com/pricing", verdicts=self._verdicts, assessed=True
        )


def _verdict(check_id: str, cls: ContentClass) -> CheckVerdict:
    return CheckVerdict(
        check_id=check_id,
        category=3,
        classification=cls,
        reason=f"{check_id} reason",
        sub_answers=[SubAnswer("direct", "q?", "reasoning", "quote", "yes", True)],
        needs_review=False,
    )


def test_run_content_judge_produces_llm_rows_and_returns_verdicts() -> None:
    verdicts = [
        _verdict("answer_first_lead", ContentClass.PASS),
        _verdict("definition_first", ContentClass.FAIL),
    ]
    judge = _FakeJudge(verdicts)
    rows: list[dict[str, object]] = []
    report_rows, returned = _run_content_judge("run-1", _FakePage(), judge, rows)  # type: ignore[arg-type]

    # Two db rows persisted, both method="llm" (not deterministic), keyed by check_id.
    assert len(rows) == 2
    assert all(r["method"] == "llm" for r in rows)
    assert {r["check_key"] for r in rows} == {"answer_first_lead", "definition_first"}
    assert {r["status"] for r in rows} == {"pass", "fail"}
    assert all(r["page_url"] == "https://example.com/pricing" for r in rows)

    # Report rows mirror them, and the raw verdicts are returned for the roadmap.
    assert [r["check_key"] for r in report_rows] == ["answer_first_lead", "definition_first"]
    assert returned is verdicts


def test_make_content_judge_off_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src.config import settings

    # Disabled by flag (conftest also sets this off for the suite).
    monkeypatch.setattr(settings, "RUN_CONTENT_JUDGE", False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-something")
    assert _make_content_judge() is None

    # Enabled but no key → still None (degrades to deterministic-only, never raises).
    monkeypatch.setattr(settings, "RUN_CONTENT_JUDGE", True)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    assert _make_content_judge() is None
