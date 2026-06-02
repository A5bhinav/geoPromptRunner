from __future__ import annotations

from datetime import UTC, datetime

from src.pipeline import metrics
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import QueryResult

__all__ = ["render_audit_report"]


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _engine_names(results: list[QueryResult]) -> list[str]:
    return sorted({r["engine_name"] for r in results})


def render_audit_report(outcome: AuditOutcome, run_date: str | None = None) -> str:
    """Render the §2/§3 markdown audit report from an orchestrated audit outcome.

    Pure function over the in-memory results + metrics — deterministic for a
    given outcome.
    """
    brand = outcome.client_name
    results = outcome.results
    competitors = outcome.competitors
    engines = _engine_names(results)
    run_date = run_date or datetime.now(UTC).date().isoformat()

    lines: list[str] = []
    lines.append(f"# GEO Audit — {brand}")
    lines.append("")
    lines.append(f"**Run date:** {run_date}")
    lines.append(
        f"**Query set:** {outcome.query_set_version} · {outcome.runs_per_query} run(s) per query"
    )
    lines.append(f"**Engines:** {', '.join(engines) or 'none'}")
    lines.append(f"**Competitors:** {', '.join(competitors) or 'none'}")
    lines.append("")

    # --- Per-engine visibility (§2) ---
    lines.append("## Visibility by Engine")
    lines.append("")
    lines.append("| Engine | Mention rate | Citation rate |")
    lines.append("| --- | --- | --- |")
    for engine in engines:
        eng_results = [r for r in results if r["engine_name"] == engine]
        m = metrics.mention_rate(eng_results, brand)
        c = metrics.citation_rate(eng_results, outcome.client_domains)
        lines.append(f"| {engine} | {_pct(m)} | {_pct(c)} |")
    overall_m = metrics.mention_rate(results, brand)
    overall_c = metrics.citation_rate(results, outcome.client_domains)
    lines.append(f"| **all** | **{_pct(overall_m)}** | **{_pct(overall_c)}** |")
    lines.append("")

    # --- Mention rate by funnel stage ---
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

    # --- Share of voice (§3) ---
    lines.append("## Share of Voice")
    lines.append("")
    sov = metrics.share_of_voice(results, brand, competitors)
    lines.append("| Brand | Share of voice |")
    lines.append("| --- | --- |")
    for name, share in sorted(sov.items(), key=lambda kv: kv[1], reverse=True):
        marker = " (client)" if name == brand else ""
        lines.append(f"| {name}{marker} | {_pct(share)} |")
    lines.append("")

    # --- Losing queries (symptom -> cause connective tissue) ---
    lines.append("## Losing Queries")
    lines.append("")
    losses = metrics.losing_queries(results, brand, competitors)
    if losses:
        lines.append(
            f"{brand} is absent while a competitor shows up in {len(losses)} (query, engine) cells:"
        )
        lines.append("")
        lines.append("| Query | Bucket | Engine | Competitors present |")
        lines.append("| --- | --- | --- | --- |")
        for loss in losses:
            comps = ", ".join(loss.competitors_present)
            lines.append(f"| {loss.query_id} | {loss.intent} | {loss.engine_name} | {comps} |")
    else:
        lines.append(f"_No losing cells: {brand} is present wherever a competitor is._")
    lines.append("")

    # --- Sources behind the category ---
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

    return "\n".join(lines)


if __name__ == "__main__":
    outcome = AuditOutcome(
        run_id=None,
        client_name="Acme",
        client_domains=["acme.com"],
        competitors=["Salesforce", "HubSpot"],
        query_set_version="v1",
        runs_per_query=1,
        results=[
            QueryResult(
                query_id="cat-01",
                intent="category",
                prompt="best CRM?",
                engine_name="openai",
                run_index=0,
                response="The best CRM is Salesforce, though HubSpot is also strong.",
                citations=["https://www.g2.com/crm"],
                timestamp="t",
            ),
            QueryResult(
                query_id="cmp-01",
                intent="comparison",
                prompt="HubSpot alternatives?",
                engine_name="openai",
                run_index=0,
                response="Acme is a great HubSpot alternative.",
                citations=["https://acme.com/vs-hubspot"],
                timestamp="t",
            ),
        ],
    )
    print(render_audit_report(outcome, run_date="2026-06-01"))
