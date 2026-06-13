"""Scaffold a BLIND gold-set skeleton from a stored run, for human labeling.

Build-order item 3 of the calibration plan. Pulls the run's answers (NOT the
judge's verdicts — independence is the point) and writes a v2 gold file with
empty placeholder labels for a human to fill in. Sourcing from a real run means
the gold set matches the instrument the judge actually sees.

Each (query, engine) cell becomes one gold item with:
- the verbatim answer, client, competitors, category, engine, fact sheet
- placeholder labels (present=false/absent/neutral) for the client + every
  competitor — the labeler corrects these
- expected_flags: [] — the labeler adds the real client errors (typed)

Blindness: the judge's stored verdicts are never read, so a labeler isn't
anchored on (and won't rubber-stamp) the judge's own call.

Usage:
    python -m scripts.scaffold_gold <run_id> <query_set.json> [out.json] \
        [--max N] [--engine NAME] [--fact-sheet PATH]
"""

from __future__ import annotations

import argparse
import json

from src.prompts.query_set import load_query_set
from src.storage import db


def main() -> int:
    ap = argparse.ArgumentParser(prog="scaffold_gold")
    ap.add_argument("run_id")
    ap.add_argument("query_set")
    ap.add_argument("out", nargs="?", default="gold_skeleton.json")
    ap.add_argument("--max", type=int, default=40, help="cap the number of items (sampled evenly)")
    ap.add_argument("--engine", default=None, help="only this engine's answers")
    ap.add_argument("--fact-sheet", default=None, help="path to embed as each item's fact sheet")
    args = ap.parse_args()

    run = db.get_audit_run(args.run_id)
    if run is None:
        print(f"run {args.run_id} not found")
        return 1
    qs = load_query_set(args.query_set)
    client = str(run.get("client_name") or qs.client)
    competitors = [str(c) for c in (run.get("competitors") or qs.competitors)]
    category = str(run.get("category") or qs.category)
    fact_sheet: str | None
    if args.fact_sheet:
        from pathlib import Path

        fact_sheet = Path(args.fact_sheet).read_text()
    else:
        fs = run.get("fact_sheet")
        fact_sheet = str(fs) if fs else None

    results = db.get_query_results(args.run_id)
    # One answer per (query, engine): the run_index 0 draw (blind to judgments).
    cells: dict[tuple[str, str], str] = {}
    for r in results:
        if r["run_index"] != 0 or r["response"] is None:
            continue
        if args.engine and r["engine_name"] != args.engine:
            continue
        cells[(r["query_id"], r["engine_name"])] = r["response"]

    ordered = sorted(cells.items())
    if len(ordered) > args.max:  # sample evenly across the ordered cells
        stride = len(ordered) / args.max
        ordered = [ordered[int(i * stride)] for i in range(args.max)]

    by_query = {q.query_id: q for q in qs.queries}
    placeholder = {"present": False, "prominence": "absent", "framing": "neutral"}
    items = []
    for (query_id, engine), answer in ordered:
        q = by_query.get(query_id)
        items.append(
            {
                "_todo": "LABEL ME: set present/prominence/framing per brand; "
                "list real client errors in expected_flags; note uncovered claims in "
                "fact_sheet_candidates.",
                "query_id": query_id,
                "query": q.text if q else query_id,
                "engine": engine,
                "category": category,
                "answer": answer,
                "client": client,
                "competitors": competitors,
                "fact_sheet": fact_sheet,
                "labels": {b: dict(placeholder) for b in [client, *competitors]},
                "expected_flags": [],
                "fact_sheet_candidates": [],
            }
        )

    blob = {
        "_comment": (
            f"BLIND gold skeleton from run {args.run_id} ({len(items)} items). "
            "Hand-label every item (judge verdicts intentionally omitted). Then split "
            "into tune/held-out and run: python -m src.pipeline.calibration"
        ),
        "items": items,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(blob, fh, indent=2, ensure_ascii=False)
    print(f"wrote {args.out}: {len(items)} blind gold items (client={client}, category={category})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
