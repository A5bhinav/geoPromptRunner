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
    python -m scripts.scaffold_gold <run_id> [query_set.json] -o <out.json> \
        [--max N] [--engine NAME] [--fact-sheet PATH]

    The query_set is optional — when omitted, query text comes from the run's
    stored prompts and client/competitors/category from the run record.
"""

from __future__ import annotations

import argparse
import json

from src.prompts.query_set import load_query_set
from src.storage import db


def main() -> int:
    ap = argparse.ArgumentParser(prog="scaffold_gold")
    ap.add_argument("run_id")
    ap.add_argument(
        "query_set",
        nargs="?",
        default=None,
        help="optional query-set JSON for query text; if omitted, the run's stored "
        "prompt text is used (client/competitors/category come from the run record)",
    )
    ap.add_argument("-o", "--out", default="gold_skeleton.json", help="output gold JSON path")
    ap.add_argument("--max", type=int, default=40, help="cap the number of items (sampled evenly)")
    ap.add_argument("--engine", default=None, help="only this engine's answers")
    ap.add_argument("--fact-sheet", default=None, help="path to embed as each item's fact sheet")
    args = ap.parse_args()

    run = db.get_audit_run(args.run_id)
    if run is None:
        print(f"run {args.run_id} not found")
        return 1
    qs = load_query_set(args.query_set) if args.query_set else None
    client = str(run.get("client_name") or (qs.client if qs else ""))
    competitors = [str(c) for c in (run.get("competitors") or (qs.competitors if qs else []))]
    category = str(run.get("category") or (qs.category if qs else ""))
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
    prompt_by_qid: dict[str, str] = {}
    for r in results:
        prompt_by_qid.setdefault(r["query_id"], str(r.get("prompt") or r["query_id"]))
        if r["run_index"] != 0 or r["response"] is None:
            continue
        if args.engine and r["engine_name"] != args.engine:
            continue
        cells[(r["query_id"], r["engine_name"])] = r["response"]

    ordered = sorted(cells.items())
    if len(ordered) > args.max:  # sample evenly across the ordered cells
        stride = len(ordered) / args.max
        ordered = [ordered[int(i * stride)] for i in range(args.max)]

    by_query = {q.query_id: q for q in qs.queries} if qs else {}
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
                "query": q.text if q else prompt_by_qid.get(query_id, query_id),
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
