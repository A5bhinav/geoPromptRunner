"""Emit answers.md for a stored audit run: every raw answer + the judge's read.

Usage:
    python -m scripts.generate_answers_md <run_id> <query_set.json> [output.md]

Pulls the run, its per-query results, and its stored judgments from Supabase,
and writes a reviewable markdown document: one section per query (in query-set
order), the full raw answer from each engine, and the judge's verdict for that
answer. The judge roll-up summary and the rendered audit report are appended at
the end so the deliverable view is in the same file.

The per-answer rendering is shared with the web/API export
(``src.pipeline.answers_export.build_answers_markdown``) so the two never drift.
"""

from __future__ import annotations

import sys

from src.audit.query_report import render_audit_report
from src.pipeline.answers_export import build_answers_markdown
from src.pipeline.judge import summarize_judgments
from src.prompts.query_set import load_query_set
from src.storage import db


def main(run_id: str, query_set_path: str, out_path: str = "answers.md") -> int:
    run = db.get_audit_run(run_id)
    if run is None:
        print(f"run {run_id} not found")
        return 1
    results = db.get_query_results(run_id)
    judgments = db.get_judgments(run_id)
    qs = load_query_set(query_set_path)

    raw_engines = run.get("engines")
    engine_order = [str(e) for e in raw_engines] if isinstance(raw_engines, list) else []
    runs_per_query = int(str(run.get("runs_per_query") or 1))

    # Shared renderer: header + per-query answers + inline judge verdicts.
    # query_order pins sections to the query set (the audit runner emits results
    # concurrently, so result order alone would be scrambled).
    body = build_answers_markdown(
        client=qs.client,
        competitors=qs.competitors,
        results=results,
        judgments=judgments,
        run_id=run_id,
        run_date=str(run.get("created_at", ""))[:10],
        runs_per_query=runs_per_query,
        engine_order=engine_order,
        query_order=[q.query_id for q in qs.queries],
    )

    # Roll-ups appended below the per-answer detail.
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
    lines = [
        body,
        "# Judge Summary (roll-up)",
        "",
        summarize_judgments(judgments, qs.client, qs.competitors),
        "",
        "---",
        "",
        render_audit_report(outcome, judgments=judgments or None, query_set=qs),
        "",
    ]

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {out_path}: {len(results)} answers, {len(judgments)} judgments")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1], sys.argv[2], *sys.argv[3:4]))
