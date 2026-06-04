from __future__ import annotations

from src.audit.query_report import render_audit_report
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import AnswerJudgment, BrandJudgment, QueryResult


def _outcome() -> AuditOutcome:
    return AuditOutcome(
        run_id="r1",
        client_name="Centsible",
        client_domains=["centsible.com"],
        competitors=["YNAB"],
        query_set_version="v1",
        runs_per_query=1,
        results=[
            QueryResult(
                query_id="cat-01",
                intent="category",
                prompt="best budgeting app?",
                engine_name="openai",
                run_index=0,
                response="YNAB is best; Centsible exists too.",
                citations=["https://www.reddit.com/r/budget"],
                timestamp="t",
            )
        ],
    )


def test_report_falls_back_to_regex_without_judgments() -> None:
    out = render_audit_report(_outcome())
    assert "Detection:** regex" in out
    assert "Share of Voice" in out  # regex section
    assert "Visibility Leaderboard" not in out  # judge-only section absent


def test_report_uses_judge_when_judgments_present() -> None:
    judgments = [
        AnswerJudgment(
            query_id="cat-01",
            engine_name="openai",
            intent="category",
            run_index=0,
            assessed=True,
            brands=[
                BrandJudgment("YNAB", True, "recommended_first", "positive"),
                BrandJudgment("Centsible", False, "absent", "neutral"),
            ],
            accuracy_flags=[],
        )
    ]
    out = render_audit_report(_outcome(), judgments=judgments)
    assert "Detection:** LLM judge" in out
    assert "Visibility Leaderboard" in out  # judge section present
    assert "Client Framing" in out
    assert "Share of Voice" not in out  # regex section not used


def test_unassessed_judgments_fall_back_to_regex() -> None:
    judgments = [
        AnswerJudgment("cat-01", "openai", "category", 0, False, [], [])  # judge failed
    ]
    out = render_audit_report(_outcome(), judgments=judgments)
    assert "Detection:** regex" in out
