"""Pick which cells of a stored run to gold-label, stratified (P4-T1).

The gold sets that exist (`data/fort_gold.json`, `data/oura_gold.json`) measure
brand-level agreement well — Fort 94% present / 86% prominence / 93% framing over
240 judgements. What they cannot measure is the **flag-bearing** half: Fort's set
carries 3 gold findings and Oura's 18 against a 20-finding floor, so
`AgreementSummary.flags_are_quotable` is False for both and the methodology
section correctly names the gap instead of quoting a number.

A perfect judge cannot pass `gate_critical_high_recall` on either set. That is the
gate working — it is refusing to certify recall from a sample that cannot support
the claim — and no amount of code fixes it. What fixes it is ~60 more labelled
items, and the Fort `csv-2026-06-13` run alone has 115 flags across 540 judged
cells to draw them from.

This script does the *sampling* half of that, so the remaining work is labelling
rather than deciding what to label:

- **Stratified, not random.** Random sampling under-represents exactly the cases
  that break judges. Twenty each from what the judge called severe, what it
  called nothing, and the boundary (`med`) cases where its uncertainty
  concentrates.
- **Deterministic.** Selection ranks on a hash of the cell id, so re-running
  picks the same cells and two labellers work the same list.
- **It reads the judge's verdicts to STRATIFY, and writes none of them out.**
  Labelling anchored on the judge's own call is how a small team's gold set gets
  quietly contaminated; the output carries the answer text and nothing else.

Usage:
    python -m scripts.stratify_gold <run_id> -o data/fort_gold_candidates.json
        [--per-stratum 20]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pipeline.review import ReviewCandidate, ReviewStratum, stratify_gold_candidates
from src.storage import db


def _cell_id(query_id: str, engine_name: str, run_index: int) -> str:
    return f"{query_id}:{engine_name}:{run_index}"


def main() -> int:
    ap = argparse.ArgumentParser(prog="stratify_gold")
    ap.add_argument("run_id")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument(
        "--per-stratum",
        type=int,
        default=20,
        help="the spec's target for a class whose recall you intend to quote",
    )
    args = ap.parse_args()

    row = db.get_audit_run(args.run_id)
    if row is None:
        print(f"run {args.run_id} not found")
        return 1
    results = db.get_query_results(args.run_id)
    judgments = db.get_judgments(args.run_id)
    if not judgments:
        print("this run has no stored verdicts, so there is nothing to stratify by")
        return 1

    # Stratify on the judge's own severity, which is the only signal available
    # before a human has looked. The verdict itself never reaches the output.
    candidates: list[ReviewCandidate] = []
    for j in judgments:
        if not j.assessed:
            continue
        worst = ""
        for flag in j.accuracy_flags:
            if not worst or flag.severity == "high":
                worst = flag.severity
        candidates.append(
            ReviewCandidate(
                cell_id=_cell_id(j.query_id, j.engine_name, j.run_index),
                severity=worst,
            )
        )

    picked = stratify_gold_candidates(candidates, per_stratum=args.per_stratum)
    wanted = {cell for cells in picked.values() for cell in cells}

    answers = {
        _cell_id(r["query_id"], r["engine_name"], r["run_index"]): r
        for r in results
        if r["response"] is not None
    }

    items = []
    for stratum, cells in picked.items():
        for cell in cells:
            result = answers.get(cell)
            if result is None:
                continue
            items.append(
                {
                    "cell_id": cell,
                    "stratum": stratum,
                    "query_id": result["query_id"],
                    "engine_name": result["engine_name"],
                    "run_index": result["run_index"],
                    "prompt": result["prompt"],
                    "answer": result["response"],
                    # Placeholders for the labeller. Deliberately empty: a
                    # pre-filled label is a label the human will agree with.
                    "expected_flags": [],
                    "labeller": "",
                    "notes": "",
                }
            )

    args.out.write_text(
        json.dumps(
            {
                "run_id": args.run_id,
                "client_name": row.get("client_name", ""),
                "query_set_version": row.get("query_set_version", ""),
                "per_stratum": args.per_stratum,
                "items": items,
            },
            indent=2,
        )
    )

    print(f"wrote {len(items)} candidates to {args.out}")
    for stratum in ReviewStratum:
        got = len(picked.get(stratum.value, []))
        # A stratum smaller than asked for is REPORTED, never silently accepted:
        # `gate_critical_high_recall` refuses to certify recall from one, and
        # discovering that after labelling wastes the labelling.
        short = "" if got >= args.per_stratum else f"  ← short of {args.per_stratum}"
        print(f"  {stratum.value:12s} {got}{short}")
    if len(wanted) > len(items):
        print(f"  {len(wanted) - len(items)} selected cells had no stored answer and were dropped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
