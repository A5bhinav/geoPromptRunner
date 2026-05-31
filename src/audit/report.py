from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlparse

from src.pipeline.parser import MentionType
from src.storage import db
from src.storage.models import BrandMention, Citation, PromptResult, ReportData

__all__ = ["generate_report", "render_report"]

logger = logging.getLogger(__name__)


def _is_present(mention_type: str) -> bool:
    return mention_type != MentionType.NOT_MENTIONED.value


def _domain_of(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def _pct(part: int, whole: int) -> str:
    if whole == 0:
        return "n/a"
    return f"{(100.0 * part / whole):.0f}%"


def render_report(data: ReportData) -> str:
    """Render a markdown audit report from fully-assembled report data.

    Pure function: no I/O. Deterministic for a given ``ReportData`` input.
    """
    lines: list[str] = []
    lines.append(f"# GEO Audit Report — {data['client_name']}")
    lines.append("")
    lines.append(f"**Run date:** {data['run_date']}")
    lines.append(f"**Client brand:** {data['client_brand']}")
    lines.append(f"**Engines:** {', '.join(data['engine_names']) or 'none'}")
    lines.append("")

    # --- Mention rate per engine ---
    lines.append("## Mention Rate per Engine")
    lines.append("")
    lines.append("| Engine | Prompts | Client mentions | Mention rate |")
    lines.append("| --- | --- | --- | --- |")
    client = data["client_brand"].lower()
    total_client_mentions = 0
    total_prompts = 0
    for engine in data["engine_names"]:
        prompts = sum(1 for r in data["results"] if r["engine_name"] == engine)
        mentions = sum(
            1
            for m in data["mentions"]
            if m["engine_name"] == engine
            and m["brand"].lower() == client
            and _is_present(m["mention_type"])
        )
        total_prompts += prompts
        total_client_mentions += mentions
        lines.append(f"| {engine} | {prompts} | {mentions} | {_pct(mentions, prompts)} |")
    lines.append("")

    # --- Competitor share-of-model ---
    lines.append("## Competitor Share-of-Model")
    lines.append("")
    total_responses = len(data["results"])
    lines.append("| Brand | Appearances | Share of responses |")
    lines.append("| --- | --- | --- |")
    brands = [data["client_brand"], *data["competitors"]]
    share_rows: list[tuple[str, int]] = []
    for brand in brands:
        appearances = sum(
            1
            for m in data["mentions"]
            if m["brand"].lower() == brand.lower() and _is_present(m["mention_type"])
        )
        share_rows.append((brand, appearances))
    ranked = sorted(share_rows, key=lambda x: x[1], reverse=True)
    for brand, appearances in ranked:
        marker = " (client)" if brand.lower() == client else ""
        lines.append(f"| {brand}{marker} | {appearances} | {_pct(appearances, total_responses)} |")
    lines.append("")

    # --- Top cited domains ---
    lines.append("## Top Cited Domains")
    lines.append("")
    domain_counts = Counter(_domain_of(c["url"]) for c in data["citations"] if c["url"])
    if domain_counts:
        lines.append("| Domain | Citations |")
        lines.append("| --- | --- |")
        for domain, count in domain_counts.most_common(10):
            lines.append(f"| {domain} | {count} |")
    else:
        lines.append("_No citations captured for this run._")
    lines.append("")

    # --- Summary of findings ---
    lines.append("## Summary of Findings")
    lines.append("")
    overall = _pct(total_client_mentions, total_prompts)
    lines.append(
        f"- {data['client_brand']} was mentioned in {overall} of responses across "
        f"{len(data['engine_names'])} engine(s)."
    )
    top_competitor = next((b for b, _ in ranked if b.lower() != client), None)
    if top_competitor is not None:
        lines.append(f"- Most-visible competitor: **{top_competitor}**.")
    lines.append(f"- {len(domain_counts)} distinct domain(s) cited across the run.")
    lines.append("")

    return "\n".join(lines)


def generate_report(run_id: str) -> str:
    """Assemble report data for ``run_id`` from storage and render markdown."""
    run = db.get_run(run_id)
    if run is None:
        logger.warning("generate_report: run %s not found", run_id)
        return f"# GEO Audit Report\n\n_Run `{run_id}` not found._\n"

    result_rows = db.get_results(run_id)
    mention_rows = db.get_mentions(run_id)
    citation_rows = db.get_citations(run_id)

    results: list[PromptResult] = [
        PromptResult(
            prompt=str(r.get("prompt", "")),
            engine_name=str(r.get("engine_name", "")),
            response=None if r.get("response") is None else str(r.get("response")),
            timestamp=str(r.get("timestamp", "")),
        )
        for r in result_rows
    ]
    mentions: list[BrandMention] = [
        BrandMention(
            brand=str(m.get("brand", "")),
            engine_name=str(m.get("engine_name", "")),
            prompt=str(m.get("prompt", "")),
            mention_type=str(m.get("mention_type", "")),
        )
        for m in mention_rows
    ]
    citations: list[Citation] = [
        Citation(
            url=str(c.get("url", "")),
            engine_name=str(c.get("engine_name", "")),
            prompt=str(c.get("prompt", "")),
        )
        for c in citation_rows
    ]

    client_name = str(run.get("client_name", "Unknown Client"))
    engine_names = sorted({r["engine_name"] for r in results})
    competitors = sorted(
        {m["brand"] for m in mentions if m["brand"].lower() != client_name.lower()}
    )

    data = ReportData(
        client_name=client_name,
        client_brand=client_name,
        run_date=str(run.get("created_at", datetime.now(UTC).isoformat())),
        engine_names=engine_names,
        results=results,
        mentions=mentions,
        competitors=competitors,
        citations=citations,
    )
    return render_report(data)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    mock = ReportData(
        client_name="Acme Inc.",
        client_brand="Acme",
        run_date=datetime.now(UTC).date().isoformat(),
        engine_names=["openai", "anthropic", "perplexity", "gemini"],
        results=[
            PromptResult(
                prompt="best CRM?", engine_name="openai", response="Acme is great.", timestamp="t"
            ),
            PromptResult(
                prompt="best CRM?", engine_name="anthropic", response="Salesforce.", timestamp="t"
            ),
            PromptResult(
                prompt="best CRM?",
                engine_name="perplexity",
                response="Acme, HubSpot.",
                timestamp="t",
            ),
            PromptResult(
                prompt="best CRM?", engine_name="gemini", response="HubSpot.", timestamp="t"
            ),
        ],
        mentions=[
            BrandMention(
                brand="Acme", engine_name="openai", prompt="best CRM?", mention_type="recommended"
            ),
            BrandMention(
                brand="Acme", engine_name="perplexity", prompt="best CRM?", mention_type="mentioned"
            ),
            BrandMention(
                brand="Salesforce",
                engine_name="anthropic",
                prompt="best CRM?",
                mention_type="mentioned",
            ),
            BrandMention(
                brand="HubSpot",
                engine_name="perplexity",
                prompt="best CRM?",
                mention_type="mentioned",
            ),
            BrandMention(
                brand="HubSpot",
                engine_name="gemini",
                prompt="best CRM?",
                mention_type="recommended",
            ),
        ],
        competitors=["Salesforce", "HubSpot"],
        citations=[
            Citation(url="https://www.g2.com/acme", engine_name="perplexity", prompt="best CRM?"),
            Citation(url="https://reddit.com/r/saas", engine_name="perplexity", prompt="best CRM?"),
            Citation(
                url="https://www.g2.com/hubspot", engine_name="perplexity", prompt="best CRM?"
            ),
        ],
    )
    print(render_report(mock))
