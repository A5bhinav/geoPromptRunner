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
the deterministic halves the Workflow sandbox cannot do (no DB, no filesystem),
and is built so the answer text NEVER flows through the Workflow's args or return
— only through this on-disk file — so it scales to runs with hundreds of long
answers (a real run's dump is multiple MB):

    dump   — pull a run's unique (prompt, answer) pairs from the DB, render the
             exact single-judge prompt for each, and compute the cache key for
             each (from the real ``Judge`` identity). Writes one JSON file (the
             "in" file). Pairs already cached are skipped.
    header — print that file's metadata (client, competitors, has_fact_sheet,
             agent output schema, item count) WITHOUT the bulky items — the small
             payload the Workflow needs in its args.
    item   — print ONE item's judging prompt by index. Each Workflow subagent runs
             this to fetch only its own task, so no answer text touches args.
    inject — given the in file + the Workflow's per-item verdicts (aligned to item
             order), write the verdicts into the judge cache under the in file's
             keys. The key comes from the in file by index, so a subagent never
             has to handle (or could garble) it.

This targets the SINGLE-judge config (``Judge()`` with no cascade/verify), which
is the default the CLI/UI use unless ``JUDGE_CASCADE``/``JUDGE_VERIFY`` are set.
Those configs judge with a different method (two passes / per-flag verify) and a
different cache keyspace, so the Workflow — which replicates the single judge —
would write keys that a cascade/verify run never looks up. ``dump`` refuses them
loudly rather than silently producing a cache nobody reads.

Usage:
    python -m scripts.judge_via_workflow dump <run_id> [--fact-sheet PATH] [--out PATH]
    python -m scripts.judge_via_workflow header <in.json>
    python -m scripts.judge_via_workflow item <in.json> <index>
    python -m scripts.judge_via_workflow inject <in.json> <verdicts.json> [--offset N]

These are normally chained by the ``/prejudge`` skill; run by hand for debugging.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline.judge import Judge

# NOTE: the heavy imports (settings, judge, judge_cache, db — they pull in the
# anthropic / supabase SDKs) live INSIDE _dump / _inject / _build_judge, not at
# module top level. That keeps the ``item`` and ``header`` subcommands stdlib-only
# so a Workflow subagent can run them with any python (it need not be the venv) —
# those two only read the on-disk JSON the dump already wrote.


def _build_judge() -> Judge:
    """The single judge whose identity (cache model id + prompt fingerprint) and
    prompt this script reproduces. Refuses cascade/verify: those judge with a
    different method and live in a different cache keyspace, so a Workflow that
    replicates the single judge would write keys they never read (a silent no-op
    at judge time). Fail loudly instead."""
    from src.config import settings
    from src.pipeline.judge import Judge

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
    from src.storage import db

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
    from src.config import settings
    from src.pipeline.judge import _SYSTEM, _judgment_tool
    from src.pipeline.judge_cache import JudgeCache
    from src.storage import db

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
        # The output shape forced on each Workflow subagent (brands + client flags),
        # straight from the judge's own tool so it can't drift.
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


def _load_in(in_path: str) -> dict[str, object]:
    data = json.loads(Path(in_path).read_text())
    return data if isinstance(data, dict) else {}


def _items_of(d: dict[str, object]) -> list[dict[str, str]]:
    """The in file's ``items`` narrowed to a list of dicts (JSON-decoded as
    ``object``), so callers can index it without tripping the type checker."""
    raw = d.get("items")
    return [i for i in raw if isinstance(i, dict)] if isinstance(raw, list) else []


def _header(in_path: str) -> int:
    """The in file's metadata minus the bulky items — the small payload the
    Workflow takes in args (it reads the items themselves off disk via ``item``)."""
    d = _load_in(in_path)
    items = _items_of(d)
    header = {
        "run_id": d.get("run_id"),
        "client": d.get("client"),
        "competitors": d.get("competitors"),
        "has_fact_sheet": d.get("has_fact_sheet"),
        "schema": d.get("schema"),
        "count": len(items),
    }
    print(json.dumps(header))
    return 0


def _item(in_path: str, index: int) -> int:
    """Print ONE item's judging prompt by index (what a single subagent judges).

    Only the prompt is emitted — not the cache key — because ``inject`` re-attaches
    the key from the in file by the same index, so a subagent can't garble it."""
    items = _items_of(_load_in(in_path))
    if index < 0 or index >= len(items):
        print(f"index {index} out of range (0..{len(items) - 1})", file=sys.stderr)
        return 1
    print(json.dumps({"prompt": items[index]["prompt"]}))
    return 0


def _inject(in_path: str, verdicts_path: str, offset: int) -> int:
    """Write the Workflow's verdicts into the judge cache.

    ``verdicts_path`` holds ``{"raws": [...]}`` — one raw ``record_judgment`` object
    (or null for a failed/skipped answer) per item, in item order, covering
    ``items[offset : offset + len(raws)]`` (``--offset`` supports batched runs). Each
    verdict's key comes from the in file at that index, so it always matches what
    the real judge will look up. Only well-formed verdicts are stored; a null/bad
    one is skipped, leaving that answer to be judged normally later."""
    from src.config import settings
    from src.pipeline.judge import _parse_brands, _parse_flags
    from src.pipeline.judge_cache import JudgeCache, Verdict

    d = _load_in(in_path)
    client = str(d.get("client", ""))
    raw_comps = d.get("competitors") or []
    competitors = [str(c) for c in raw_comps] if isinstance(raw_comps, list) else []
    has_fact_sheet = bool(d.get("has_fact_sheet"))
    items = _items_of(d)

    raws = json.loads(Path(verdicts_path).read_text()).get("raws") or []

    cache = JudgeCache(settings.JUDGE_CACHE_PATH)
    stored: list[tuple[str, Verdict]] = []
    skipped = 0
    try:
        for j, raw in enumerate(raws):
            i = offset + j
            if not isinstance(raw, dict) or i >= len(items):
                skipped += 1
                continue
            brands = _parse_brands(raw, client, competitors)
            # Mirror the single judge exactly: flags only count with a fact sheet.
            flags = _parse_flags(raw) if has_fact_sheet else []
            verdict: Verdict = (brands, flags, True)
            stored.append((str(items[i]["key"]), verdict))
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

    p_dump = sub.add_parser("dump", help="emit the Workflow's input file for a run")
    p_dump.add_argument("run_id")
    p_dump.add_argument(
        "--fact-sheet",
        help="override the run's stored fact sheet (default: use audit_runs.fact_sheet)",
    )
    p_dump.add_argument("--out", help="where to write the Workflow input JSON")

    p_header = sub.add_parser("header", help="print the in file's metadata (no items)")
    p_header.add_argument("in_path")

    p_item = sub.add_parser("item", help="print one item's judging prompt by index")
    p_item.add_argument("in_path")
    p_item.add_argument("index", type=int)

    p_inject = sub.add_parser("inject", help="write the Workflow's verdicts into the judge cache")
    p_inject.add_argument("in_path", help="the dump's in.json")
    p_inject.add_argument("verdicts", help="the Workflow's verdicts JSON ({'raws': [...]})")
    p_inject.add_argument(
        "--offset", type=int, default=0, help="index of items[] the first verdict maps to"
    )

    args = parser.parse_args(argv)
    if args.cmd == "dump":
        return _dump(args.run_id, args.fact_sheet, args.out)
    if args.cmd == "header":
        return _header(args.in_path)
    if args.cmd == "item":
        return _item(args.in_path, args.index)
    return _inject(args.in_path, args.verdicts, args.offset)


if __name__ == "__main__":
    raise SystemExit(main())
