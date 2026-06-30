"""Pre-fill the judge cache with verdicts produced on the Claude subscription.

The judge already does an offline pass over stored answers with a content-
addressed SQLite cache (``data/judge_cache.sqlite``): on a cache hit it never
calls the API (``judge.py`` ``judge_results``). So if we pre-fill that cache with
verdicts produced by *subscription* subagents (a Workflow), a normal
``python -m src.cli judge <run_id>`` — or the UI's judge step, which reads the
same cache — becomes 100% cache hits → $0 API. See
``docs/subscription-judge-plan.md``.

The LLM judging itself cannot happen here (that would spend API credit); it
happens in a Workflow whose subagents run on the subscription. This script owns
the two deterministic halves the Workflow sandbox cannot do (no DB, no
filesystem):

    dump   — pull a run's unique (prompt, answer) pairs from the DB, render the
             exact single-judge prompt for each, and emit the cache key for each
             (computed from the real ``Judge`` identity). Output is the Workflow's
             input. Pairs already in the cache are skipped.
    inject — read the Workflow's output (each item's key + raw verdict) and write
             the verdicts into the judge cache under those keys.

This targets the SINGLE-judge config (``Judge()`` with no cascade/verify), which
is the default the CLI/UI use unless ``JUDGE_CASCADE``/``JUDGE_VERIFY`` are set.
Those configs judge with a different method (two passes / per-flag verify) and a
different cache keyspace, so the Workflow — which replicates the single judge —
would write keys that a cascade/verify run never looks up. ``dump`` refuses them
loudly rather than silently producing a cache nobody reads.

Usage:
    python -m scripts.judge_via_workflow dump <run_id> [--fact-sheet PATH] [--out PATH]
    python -m scripts.judge_via_workflow inject <workflow_output.json>

These are normally chained by the ``/prejudge`` skill; run by hand for debugging.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from src.config import settings
from src.pipeline.judge import (
    _SYSTEM,
    Judge,
    _judgment_tool,
    _parse_brands,
    _parse_flags,
)
from src.pipeline.judge_cache import JudgeCache, Verdict
from src.storage import db


def _build_judge() -> Judge:
    """The single judge whose identity (cache model id + prompt fingerprint) and
    prompt this script reproduces. Refuses cascade/verify: those judge with a
    different method and live in a different cache keyspace, so a Workflow that
    replicates the single judge would write keys they never read (a silent no-op
    at judge time). Fail loudly instead."""
    if settings.JUDGE_CASCADE or settings.JUDGE_VERIFY:
        raise SystemExit(
            "JUDGE_CASCADE / JUDGE_VERIFY are set, but the prejudge Workflow replicates "
            "the SINGLE judge only. A cascade/verify run uses a different cache keyspace, "
            "so the verdicts this writes would never be read. Unset those (the default "
            "single-judge config) and re-run, or extend the Workflow for cascade first."
        )
    return Judge()


def _unique_pairs(run_id: str) -> list[tuple[str, str]]:
    """Distinct (prompt, answer) pairs for a run, in first-seen order — the same
    dedup ``judge_results`` does, so the keys line up one-for-one."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for r in db.get_query_results(run_id):
        answer = r["response"]
        if answer is None:
            continue
        key = (r["prompt"], answer)
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    return pairs


def _dump(run_id: str, fact_sheet_path: str | None, out_path: str | None) -> int:
    run = db.get_audit_run(run_id)
    if run is None:
        print(f"Run {run_id} not found.")
        return 1
    client = str(run.get("client_name", ""))
    raw_comps = run.get("competitors") or []
    competitors = [str(c) for c in raw_comps] if isinstance(raw_comps, list) else []

    # The fact sheet is part of the cache key, and the CLI/UI judge keys off the
    # one STORED ON THE RUN ROW (``audit_runs.fact_sheet``). So default to that —
    # a hand-passed path that differs even slightly would write keys the real
    # judge never looks up. ``--fact-sheet`` overrides only when you deliberately
    # want to judge against a different sheet.
    if fact_sheet_path:
        fact_sheet: str | None = Path(fact_sheet_path).read_text()
        sheet_source = f"override file {fact_sheet_path}"
    else:
        stored = run.get("fact_sheet")
        fact_sheet = str(stored) if stored else None
        sheet_source = "run row" if fact_sheet else "none (structural-only)"

    judge = _build_judge()
    cache = JudgeCache(settings.JUDGE_CACHE_PATH)
    try:
        pairs = _unique_pairs(run_id)
        items: list[dict[str, str]] = []
        cached = 0
        for query_text, answer in pairs:
            key = cache.key(
                model=judge._cache_model_id,
                prompt_fingerprint=judge._prompt_fingerprint,
                client=client,
                competitors=competitors,
                fact_sheet=fact_sheet,
                prompt=query_text,
                answer=answer,
            )
            if cache.get(key) is not None:
                cached += 1
                continue  # already judged under these exact inputs — leave it
            user = judge._build_prompt(query_text, answer, client, competitors, fact_sheet)
            items.append({"key": key, "prompt": f"{_SYSTEM}\n\n{user}"})
    finally:
        cache.close()

    payload = {
        "run_id": run_id,
        "client": client,
        "competitors": competitors,
        "has_fact_sheet": fact_sheet is not None,
        "schema": _judgment_tool()["input_schema"],
        "items": items,
    }
    out = Path(out_path) if out_path else Path(tempfile.gettempdir()) / f"prejudge_{run_id}.in.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload))
    print(
        f"Dumped {len(items)} answer(s) to judge "
        f"({cached} already cached, {len(pairs)} unique total). Fact sheet: {sheet_source}."
    )
    print(f"Workflow input: {out}")
    if not items:
        print("Nothing to judge — the cache is already warm for this run.")
    return 0


def _inject(workflow_output_path: str) -> int:
    data = json.loads(Path(workflow_output_path).read_text())
    client = str(data.get("client", ""))
    raw_comps = data.get("competitors") or []
    competitors = [str(c) for c in raw_comps] if isinstance(raw_comps, list) else []
    has_fact_sheet = bool(data.get("has_fact_sheet"))
    items = data.get("items") or []

    cache = JudgeCache(settings.JUDGE_CACHE_PATH)
    stored: list[tuple[str, Verdict]] = []
    skipped = 0
    try:
        for item in items:
            key = item.get("key")
            raw = item.get("raw")
            if not isinstance(key, str) or not isinstance(raw, dict):
                skipped += 1
                continue
            brands = _parse_brands(raw, client, competitors)
            # Mirror the single judge exactly: flags only count with a fact sheet.
            flags = _parse_flags(raw) if has_fact_sheet else []
            verdict: Verdict = (brands, flags, True)
            stored.append((key, verdict))
        cache.put_many(stored)
    finally:
        cache.close()
    print(f"Injected {len(stored)} verdict(s) into the judge cache ({skipped} skipped).")
    if stored:
        print("Run `python -m src.cli judge <run_id>` (or the UI judge) — now free cache hits.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dump = sub.add_parser("dump", help="emit the Workflow's input for a run")
    p_dump.add_argument("run_id")
    p_dump.add_argument(
        "--fact-sheet",
        help="override the run's stored fact sheet (default: use audit_runs.fact_sheet)",
    )
    p_dump.add_argument("--out", help="where to write the Workflow input JSON")

    p_inject = sub.add_parser("inject", help="write the Workflow's verdicts into the judge cache")
    p_inject.add_argument("workflow_output", help="path to the Workflow's output JSON")

    args = parser.parse_args(argv)
    if args.cmd == "dump":
        return _dump(args.run_id, args.fact_sheet, args.out)
    return _inject(args.workflow_output)


if __name__ == "__main__":
    raise SystemExit(main())
