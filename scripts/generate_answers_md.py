"""Emit answers.md for a stored audit run: every raw answer + the judge's read.

Usage:
    python -m scripts.generate_answers_md <run_id> <query_set.json> [output.md]

Pulls the run, its per-query results, and its stored judgments from Supabase,
and writes a reviewable markdown document: one section per query (in query-set
order), the full raw answer from each engine, and the judge's verdict for that
answer (per-brand presence/prominence/framing + client accuracy flags). The
rendered audit report is appended at the end so the deliverable view is in the
same file.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from src.audit.query_report import render_audit_report
from src.pipeline.judge import summarize_judgments
from src.prompts.query_set import load_query_set
from src.storage import db
from src.storage.models import AnswerJudgment, QueryResult


def _judgment_lines(j: AnswerJudgment) -> list[str]:
    if not j.assessed:
        return ["  - judge: **not assessed** (judge call failed)"]
    lines = []
    for b in j.brands:
        mark = "**" if b.brand == "Oura" else ""
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


def main(run_id: str, query_set_path: str, out_path: str = "answers.md") -> int:
    run = db.get_audit_run(run_id)
    if run is None:
        print(f"run {run_id} not found")
        return 1
    results = db.get_query_results(run_id)
    judgments = db.get_judgments(run_id)
    qs = load_query_set(query_set_path)

    by_query: dict[str, list[QueryResult]] = defaultdict(list)
    for r in results:
        by_query[r["query_id"]].append(r)
    judgment_by_cell: dict[tuple[str, str, int], AnswerJudgment] = {
        (j.query_id, j.engine_name, j.run_index): j for j in judgments
    }

    raw_engines = run.get("engines")
    engine_order = [str(e) for e in raw_engines] if isinstance(raw_engines, list) else []
    engine_models = run.get("engine_models") or {}
    runs_per_query = int(str(run.get("runs_per_query") or 1))

    lines: list[str] = []
    lines.append("# Oura GEO Audit — Raw Answers + Judge Verdicts")
    lines.append("")
    lines.append(f"- **Run:** `{run_id}` · created {str(run.get('created_at', ''))[:19]}Z")
    lines.append(
        f"- **Query set:** {qs.version} ({len(qs.queries)} queries) · client **{qs.client}** · "
        f"category {qs.category}"
    )
    lines.append(f"- **Competitors:** {', '.join(qs.competitors)}")
    lines.append(f"- **Runs per query:** {run.get('runs_per_query')}")
    if isinstance(engine_models, dict) and engine_models:
        pins = " · ".join(f"{k} = `{v}`" for k, v in engine_models.items())
        lines.append(f"- **Engine model pins:** {pins}")
    lines.append(
        f"- **Judge:** every answer scored by one held-constant LLM judge against the "
        f"Oura fact sheet (accuracy flags) — {len(judgments)} judgments stored"
    )
    lines.append("")
    lines.append("---")

    for q in qs.queries:
        cell = by_query.get(q.query_id, [])
        lines.append("")
        lines.append(f"## {q.query_id} · _{q.intent.value}_ (weight {q.weight})")
        lines.append("")
        lines.append(f"> **{q.text}**")
        if not cell:
            lines.append("")
            lines.append("_No stored results for this query._")
            continue
        cell_by_engine: dict[str, list[QueryResult]] = defaultdict(list)
        for r in cell:
            cell_by_engine[r["engine_name"]].append(r)
        ordered = [e for e in engine_order if e in cell_by_engine] + [
            e for e in cell_by_engine if e not in engine_order
        ]
        for engine in ordered:
            for r in sorted(cell_by_engine[engine], key=lambda x: x["run_index"]):
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
                j = judgment_by_cell.get((q.query_id, engine, r["run_index"]))
                if j is not None:
                    lines.append("")
                    lines.append("**Judge verdict:**")
                    lines.extend(_judgment_lines(j))
        lines.append("")
        lines.append("---")

    # The roll-ups: judge summary + the rendered audit report.
    lines.append("")
    lines.append("# Judge Summary (roll-up)")
    lines.append("")
    lines.append(summarize_judgments(judgments, qs.client, qs.competitors))
    lines.append("")
    lines.append("---")
    lines.append("")

    from src.pipeline.orchestrator import AuditOutcome

    outcome = AuditOutcome(
        run_id=run_id,
        client_name=qs.client,
        client_domains=[],
        competitors=qs.competitors,
        query_set_version=qs.version,
        runs_per_query=runs_per_query,
        results=results,
    )
    lines.append(render_audit_report(outcome, judgments=judgments or None, query_set=qs))
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {out_path}: {len(results)} answers, {len(judgments)} judgments")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1], sys.argv[2], *sys.argv[3:4]))
