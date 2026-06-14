"""Export a run's raw answers — every query and the exact model response.

Two formats off the same stored data (``QueryResult`` rows + optional judge
verdicts), so the web UI, CLI, and any caller share one renderer:

- ``build_results_csv`` — one row per (query, engine, run): the query text and
  the full model response as columns. Opens in any spreadsheet; best for
  sharing/analysis and spot-checking at scale.
- ``build_answers_markdown`` — grouped by query, full prose response, the
  judge's verdict inline. Best for reading the actual answers.

Neither needs the original query-set file: the query text and intent travel on
the results themselves, so a run is exportable from its id alone.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict

from src.storage.models import AnswerJudgment, QueryResult

__all__ = ["build_results_csv", "build_answers_markdown"]

_CSV_COLUMNS = [
    "query_id",
    "intent",
    "engine",
    "run_index",
    "prompt",
    "response",
    "citations",
    "timestamp",
]


def _ordered(results: list[QueryResult], engine_order: list[str]) -> list[QueryResult]:
    """Stable, readable order: by query (first-seen), then engine, then run.

    Query order follows first appearance in ``results`` (the run's own order),
    not alphabetical, so the export reads in the query-set's intended sequence.
    Engines follow ``engine_order`` (the run's configured engine list) with any
    stragglers appended, mirroring the report's engine ordering.
    """
    query_rank: dict[str, int] = {}
    for r in results:
        query_rank.setdefault(r["query_id"], len(query_rank))
    engine_rank = {name: i for i, name in enumerate(engine_order)}

    def key(r: QueryResult) -> tuple[int, int, str, int]:
        return (
            query_rank[r["query_id"]],
            engine_rank.get(r["engine_name"], len(engine_rank)),
            r["engine_name"],
            r["run_index"],
        )

    return sorted(results, key=key)


def _csv_safe(value: str) -> str:
    """Neutralize spreadsheet formula injection.

    A cell beginning with ``= + - @`` (or a leading tab/CR) is executed as a
    formula by Excel/Sheets. Query text comes from an uploaded CSV and responses
    are model output — both attacker-influenceable — so prefix any such cell with
    a single quote, which spreadsheets treat as "render as literal text".
    """
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def build_results_csv(
    results: list[QueryResult], engine_order: list[str] | None = None
) -> str:
    """Render every answered cell as CSV — query text + full response per row.

    A ``None`` response (an engine error/no-answer) becomes an empty response
    cell, so the row still records that the engine was queried. ``csv`` handles
    quoting, so newlines/commas inside a model response are preserved verbatim;
    ``_csv_safe`` additionally neutralizes formula-injection in text cells.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_COLUMNS)
    for r in _ordered(results, engine_order or []):
        writer.writerow(
            [
                r["query_id"],
                r["intent"],
                r["engine_name"],
                r["run_index"],
                _csv_safe(r["prompt"]),
                _csv_safe(r["response"] or ""),
                _csv_safe("; ".join(r["citations"])),
                r["timestamp"],
            ]
        )
    return buf.getvalue()


def _judgment_lines(j: AnswerJudgment, client: str) -> list[str]:
    if not j.assessed:
        return ["  - judge: **not assessed** (judge call failed)"]
    lines: list[str] = []
    for b in j.brands:
        mark = "**" if b.brand == client else ""
        presence = "present" if b.present else "absent"
        lines.append(
            f"  - {mark}{b.brand}{mark}: {presence} · prominence={b.prominence} · "
            f"framing={b.framing}"
        )
    for f in j.accuracy_flags:
        lines.append(
            f"  - 🚩 **{f.type}** ({f.severity}): claim — “{f.claim}” → reality — “{f.reality}”"
        )
    return lines


def build_answers_markdown(
    *,
    client: str,
    competitors: list[str],
    results: list[QueryResult],
    judgments: list[AnswerJudgment] | None = None,
    run_id: str = "",
    run_date: str = "",
    runs_per_query: int = 1,
    engine_order: list[str] | None = None,
    query_order: list[str] | None = None,
) -> str:
    """Render a readable answers document: each query, every raw response, and
    the judge's verdict for that response inline.

    Grouped by query, then by engine, then by run index. ``client`` drives which
    brand is bolded in the judge verdicts. Works from the stored results alone —
    query text and intent come off each row. ``query_order`` pins the section
    order to the query set when a caller has it (the runner emits results in
    finish order under concurrency, so first-seen order would be scrambled);
    omit it to fall back to first-seen order.
    """
    engine_order = engine_order or []
    judgment_by_cell: dict[tuple[str, str, int], AnswerJudgment] = {
        (j.query_id, j.engine_name, j.run_index): j for j in (judgments or [])
    }

    # Group rows by query; keep the query text and intent from the first row of
    # each group. Section order follows query_order when given, else first-seen.
    by_query: dict[str, list[QueryResult]] = defaultdict(list)
    query_text: dict[str, str] = {}
    query_intent: dict[str, str] = {}
    for r in results:
        by_query[r["query_id"]].append(r)
        query_text.setdefault(r["query_id"], r["prompt"])
        query_intent.setdefault(r["query_id"], r["intent"])
    if query_order:
        ordered_query_ids = [q for q in query_order if q in by_query]
        ordered_query_ids += [q for q in by_query if q not in set(query_order)]
    else:
        ordered_query_ids = list(by_query)

    lines: list[str] = []
    lines.append(f"# {client} — GEO Audit: Raw Answers + Judge Verdicts")
    lines.append("")
    if run_id:
        lines.append(f"- **Run:** `{run_id}`" + (f" · {run_date}" if run_date else ""))
    lines.append(f"- **Client:** {client}")
    if competitors:
        lines.append(f"- **Competitors:** {', '.join(competitors)}")
    lines.append(f"- **Queries:** {len(by_query)} · **Runs per query:** {runs_per_query}")
    if judgments:
        lines.append(f"- **Judge:** {len(judgments)} answers scored by the held-constant judge")
    lines.append("")
    lines.append("---")

    for query_id in ordered_query_ids:
        rows = by_query[query_id]
        lines.append("")
        lines.append(f"## {query_id} · _{query_intent[query_id]}_")
        lines.append("")
        lines.append(f"> **{query_text[query_id]}**")

        by_engine: dict[str, list[QueryResult]] = defaultdict(list)
        for r in rows:
            by_engine[r["engine_name"]].append(r)
        ordered_engines = [e for e in engine_order if e in by_engine] + [
            e for e in by_engine if e not in engine_order
        ]
        for engine in ordered_engines:
            for r in sorted(by_engine[engine], key=lambda x: x["run_index"]):
                run_tag = f" (run {r['run_index'] + 1})" if runs_per_query > 1 else ""
                lines.append("")
                lines.append(f"### {engine}{run_tag}")
                lines.append("")
                if r["response"] is None:
                    lines.append("_(no answer — engine returned an error)_")
                else:
                    lines.append(r["response"].strip())
                if r["citations"]:
                    lines.append("")
                    lines.append("Citations: " + " · ".join(r["citations"]))
                j = judgment_by_cell.get((query_id, engine, r["run_index"]))
                if j is not None:
                    lines.append("")
                    lines.append("**Judge verdict:**")
                    lines.extend(_judgment_lines(j, client))
        lines.append("")
        lines.append("---")

    return "\n".join(lines) + "\n"
