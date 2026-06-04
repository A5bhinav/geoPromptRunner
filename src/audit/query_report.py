from __future__ import annotations

from datetime import UTC, datetime

from src.pipeline import judge_metrics, metrics
from src.pipeline.orchestrator import AuditOutcome
from src.prompts.query_set import QuerySet
from src.storage.models import AnswerJudgment, QueryResult

__all__ = ["render_audit_report"]


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _delta(before: float, after: float) -> str:
    pts = (after - before) * 100
    arrow = "▲" if pts > 0 else ("▼" if pts < 0 else "—")
    return f"{_pct(before)} → {_pct(after)} ({arrow}{abs(pts):.0f} pts)"


def _engine_names(results: list[QueryResult]) -> list[str]:
    return sorted({r["engine_name"] for r in results})


def _cited_domains_section(lines: list[str], results: list[QueryResult]) -> None:
    lines.append("## Top Cited Domains")
    lines.append("")
    domains = metrics.top_cited_domains(results)
    if domains:
        lines.append("| Domain | Cited in cells |")
        lines.append("| --- | --- |")
        for domain, count in domains:
            lines.append(f"| {domain} | {count} |")
    else:
        lines.append("_No citations captured for this run._")
    lines.append("")


def _judge_body(
    lines: list[str],
    judgments: list[AnswerJudgment],
    brand: str,
    competitors: list[str],
    results: list[QueryResult],
    client_domains: list[str],
    engines: list[str],
) -> None:
    """§2/§3 powered by the judge (prominence/framing/accuracy)."""
    lines.extend(judge_metrics.judge_sections(judgments, brand, competitors))

    # Per-engine client view: mention from the judge, citation from the answers.
    lines.append("## Per-Engine — Client")
    lines.append("")
    lines.append("| Engine | Mention rate | Citation rate |")
    lines.append("| --- | --- | --- |")
    for engine in engines:
        eng_judgments = [j for j in judgments if j.engine_name == engine]
        eng_results = [r for r in results if r["engine_name"] == engine]
        mention = judge_metrics.mention_rate(eng_judgments, brand)
        citation = metrics.citation_rate(eng_results, client_domains)
        lines.append(f"| {engine} | {_pct(mention)} | {_pct(citation)} |")
    lines.append("")


def _regex_body(
    lines: list[str],
    results: list[QueryResult],
    brand: str,
    competitors: list[str],
    engines: list[str],
    client_domains: list[str],
) -> None:
    """Fallback §2/§3 from regex detection — used when no judgments are present.

    Mention/recommendation only; prominence, framing, and accuracy need the judge.
    """
    lines.append("## Visibility by Engine")
    lines.append("")
    lines.append("| Engine | Mention rate | Citation rate |")
    lines.append("| --- | --- | --- |")
    for engine in engines:
        eng_results = [r for r in results if r["engine_name"] == engine]
        m = metrics.mention_rate(eng_results, brand)
        c = metrics.citation_rate(eng_results, client_domains)
        lines.append(f"| {engine} | {_pct(m)} | {_pct(c)} |")
    overall_m = metrics.mention_rate(results, brand)
    overall_c = metrics.citation_rate(results, client_domains)
    lines.append(f"| **all** | **{_pct(overall_m)}** | **{_pct(overall_c)}** |")
    lines.append("")

    lines.append("## Mention Rate by Funnel Stage")
    lines.append("")
    by_bucket = metrics.mention_rate_by_bucket(results, brand)
    if by_bucket:
        lines.append("| Intent bucket | Mention rate |")
        lines.append("| --- | --- |")
        for bucket, rate in sorted(by_bucket.items()):
            lines.append(f"| {bucket} | {_pct(rate)} |")
    else:
        lines.append("_No data._")
    lines.append("")

    lines.append("## Share of Voice")
    lines.append("")
    sov = metrics.share_of_voice(results, brand, competitors)
    lines.append("| Brand | Share of voice |")
    lines.append("| --- | --- |")
    for name, share in sorted(sov.items(), key=lambda kv: kv[1], reverse=True):
        marker = " (client)" if name == brand else ""
        lines.append(f"| {name}{marker} | {_pct(share)} |")
    lines.append("")

    losses = metrics.losing_queries(results, brand, competitors)
    lines.append(f"## Losing Queries ({len(losses)})")
    lines.append("")
    if losses:
        lines.append("| Query | Bucket | Engine | Competitors present |")
        lines.append("| --- | --- | --- | --- |")
        for loss in losses:
            comps = ", ".join(loss.competitors_present)
            lines.append(f"| {loss.query_id} | {loss.intent} | {loss.engine_name} | {comps} |")
    else:
        lines.append(f"_No losing cells: {brand} is present wherever a competitor is._")
    lines.append("")
    lines.append(
        "> Run `geo judge <run_id> --fact-sheet <path>` to upgrade this to "
        "prominence, framing, and accuracy."
    )
    lines.append("")


def _trend_section(
    lines: list[str],
    previous: list[QueryResult],
    current: list[QueryResult],
    brand: str,
    competitors: list[str],
    label: str,
) -> None:
    """§3 movement: per-brand mention-rate delta vs a prior run of the same set.

    Results-based (not judge-based) so it renders on either detection path; valid
    only if the query set was held constant — the caller passes the prior run.
    """
    lines.append(f"## Trend vs {label}")
    lines.append("")
    lines.append("| Brand | Mention rate (before → after) |")
    lines.append("| --- | --- |")
    for name in [brand, *competitors]:
        marker = " (client)" if name == brand else ""
        before = metrics.mention_rate(previous, name)
        after = metrics.mention_rate(current, name)
        lines.append(f"| {name}{marker} | {_delta(before, after)} |")
    lines.append("")


def _query_appendix(lines: list[str], query_set: QuerySet) -> None:
    """§6.1 appendix: the locked query set with the Persona/modifier column."""
    lines.append("## Query Set (Appendix)")
    lines.append("")
    lines.append(f"_Version {query_set.version}, locked {query_set.locked_at}._")
    lines.append("")
    lines.append("| Query | Intent | Persona / modifier | Weight |")
    lines.append("| --- | --- | --- | --- |")
    for q in query_set.queries:
        persona = q.persona or "—"
        lines.append(f"| {q.text} | {q.intent.value} | {persona} | {q.weight:g} |")
    lines.append("")


def render_audit_report(
    outcome: AuditOutcome,
    run_date: str | None = None,
    judgments: list[AnswerJudgment] | None = None,
    previous: list[QueryResult] | None = None,
    previous_label: str = "previous run",
    query_set: QuerySet | None = None,
) -> str:
    """Render the §2/§3 markdown audit report.

    Judge-aware: when ``judgments`` are supplied (and any were assessed) the
    report is powered by the LLM judge — the §1 A-F grade plus the
    visibility/prominence leaderboard, framing, and accuracy flags. Otherwise it
    falls back to regex detection (mention only). Citations always come from the
    answers.

    Optional: ``previous`` (a prior run's results for the *same* locked set) adds
    the §3 trend column; ``query_set`` adds the §6.1 query appendix with the
    Persona/modifier column. Pure/deterministic.
    """
    brand = outcome.client_name
    results = outcome.results
    competitors = outcome.competitors
    engines = _engine_names(results)
    run_date = run_date or datetime.now(UTC).date().isoformat()
    has_judge = judgments is not None and any(j.assessed for j in judgments)

    lines: list[str] = []
    lines.append(f"# GEO Audit — {brand}")
    lines.append("")
    lines.append(f"**Run date:** {run_date}")
    lines.append(
        f"**Query set:** {outcome.query_set_version} · {outcome.runs_per_query} run(s) per query"
    )
    lines.append(f"**Engines:** {', '.join(engines) or 'none'}")
    lines.append(f"**Competitors:** {', '.join(competitors) or 'none'}")
    lines.append(f"**Detection:** {'LLM judge' if has_judge else 'regex (no judge run)'}")
    lines.append("")

    if has_judge:
        assert judgments is not None
        _judge_body(lines, judgments, brand, competitors, results, outcome.client_domains, engines)
    else:
        _regex_body(lines, results, brand, competitors, engines, outcome.client_domains)

    if previous is not None:
        _trend_section(lines, previous, results, brand, competitors, previous_label)

    _cited_domains_section(lines, results)

    if query_set is not None:
        _query_appendix(lines, query_set)
    return "\n".join(lines)


if __name__ == "__main__":
    outcome = AuditOutcome(
        run_id=None,
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
                response="YNAB is the top pick; Centsible is a newer alternative.",
                citations=["https://www.reddit.com/r/budget"],
                timestamp="t",
            )
        ],
    )
    # No judgments -> regex fallback.
    print(render_audit_report(outcome))
