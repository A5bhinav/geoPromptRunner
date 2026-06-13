"""Backfill the missing Gemini cells into an existing audit run.

The r2 Oura run (204e7854) was captured before the Gemini key had quota, so
Gemini only answered a handful of queries while the other engines answered the
full grid. Plain `audit --resume` can't fix this: resume skips by query_id, and
every query already has non-Gemini rows. This fills exactly the (query_id,
run_index) cells that a reference engine has but Gemini lacks, runs only the
Gemini engine over them, and persists incrementally so a quota stall keeps
progress.

Usage:
    python -m scripts.backfill_gemini <run_id> <query_set.json> [reference_engine]
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from src.engines.gemini_engine import GeminiEngine
from src.prompts.query_set import load_query_set
from src.storage import db
from src.storage.models import QueryResult


def main(run_id: str, query_set_path: str, reference_engine: str = "openai") -> int:
    qs = load_query_set(query_set_path)
    by_id = {q.query_id: q for q in qs.queries}

    existing = db.get_query_results(run_id)
    # The full instrument grid = (query_id, run_index) cells the reference
    # engine ran; Gemini should match it cell-for-cell.
    ref_cells = {
        (r["query_id"], r["run_index"]) for r in existing if r["engine_name"] == reference_engine
    }
    gemini_cells = {
        (r["query_id"], r["run_index"]) for r in existing if r["engine_name"] == "gemini"
    }
    missing = sorted(ref_cells - gemini_cells)

    if not missing:
        print("No missing Gemini cells — backlog already complete.")
        return 0

    print(f"Backfilling {len(missing)} Gemini cells into run {run_id} "
          f"(reference engine: {reference_engine}).")
    engine = GeminiEngine()

    done = 0
    for i, (query_id, run_index) in enumerate(missing, start=1):
        q = by_id.get(query_id)
        if q is None:
            print(f"  [{i}/{len(missing)}] {query_id}: not in query set — skipping")
            continue
        response, citations = engine.query_with_citations(q.text)
        result = QueryResult(
            query_id=query_id,
            intent=q.intent.value,
            prompt=q.text,
            engine_name="gemini",
            run_index=run_index,
            response=response,
            citations=citations,
            timestamp=datetime.now(UTC).isoformat(),
        )
        # Persist one cell at a time: a quota interruption keeps prior progress
        # and a re-run resumes from the gap.
        db.save_query_results(run_id, [result])
        status = "ok" if response is not None else "EMPTY (engine error)"
        done += 1
        print(f"  [{i}/{len(missing)}] {query_id} (run {run_index}): {status}")

    print(f"Done. {done} cells written.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1], sys.argv[2], *sys.argv[3:4]))
