"""Judge the Gemini answers that lack a stored judgment, keep the rest as-is.

After backfilling Gemini cells we need judge verdicts for them, but the run
already has judgments for the other engines. save_judgments is delete-then-
insert (it expects the full set), so this judges only the un-judged Gemini
answers, unions them with the existing judgments, and writes the whole set back.

Usage:
    python -m scripts.judge_new_gemini <run_id> <query_set.json> <fact_sheet.md>
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.pipeline.judge import Judge
from src.prompts.query_set import load_query_set
from src.storage import db


def _key(query_id: str, engine: str, run_index: int) -> tuple[str, str, int]:
    return (query_id, engine, run_index)


def main(run_id: str, query_set_path: str, fact_sheet_path: str) -> int:
    qs = load_query_set(query_set_path)
    fact_sheet = Path(fact_sheet_path).read_text()

    results = db.get_query_results(run_id)
    existing = db.get_judgments(run_id)
    judged_keys = {_key(j.query_id, j.engine_name, j.run_index) for j in existing}

    to_judge = [
        r
        for r in results
        if r["engine_name"] == "gemini"
        and r["response"] is not None
        and _key(r["query_id"], r["engine_name"], r["run_index"]) not in judged_keys
    ]
    if not to_judge:
        print("No un-judged Gemini answers — nothing to do.")
        return 0

    print(f"Judging {len(to_judge)} new Gemini answers (existing judgments: {len(existing)}).")
    judge = Judge()
    new = judge.judge_results(to_judge, qs.client, qs.competitors, fact_sheet)

    combined = existing + new
    db.save_judgments(run_id, combined)
    print(f"Saved {len(combined)} judgments ({len(existing)} kept + {len(new)} new).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
