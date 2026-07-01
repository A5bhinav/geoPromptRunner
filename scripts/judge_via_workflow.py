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

    dump   — pull a run's unique (prompt, answer) pairs from the DB and compute the
             cache key for each (from the real ``Judge`` identity). Splits the judge
             prompt into the shared RUBRIC (stored ONCE as ``preamble``) and a tiny
             per-answer HEAD (stored per item), so a batch never re-sends the rubric.
             Writes one JSON file (the "in" file). Pairs already cached are skipped.
    header — print that file's metadata (client, competitors, has_fact_sheet,
             agent output schema, item count) WITHOUT the bulky items — the small
             payload the Workflow needs in its args.
    batch  — print ONE batch's judging prompt: the shared rubric preamble + the HEADs
             for items [start, start+count), each under an ``===== ITEM i =====``
             header. Each Workflow subagent runs this to fetch its whole batch (many
             answers, one rubric copy), so no answer text touches args.
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
    python -m scripts.judge_via_workflow batch <in.json> <start> <count>
    python -m scripts.judge_via_workflow inject <in.json> <verdicts.json> [--offset N]

These are normally chained by the ``/prejudge`` skill; run by hand for debugging.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from src.pipeline.judge import Judge

# NOTE: the heavy imports (settings, judge, judge_cache, db — they pull in the
# anthropic / supabase SDKs) live INSIDE _dump / _inject / _build_judge, not at
# module top level. That keeps the ``batch`` and ``header`` subcommands stdlib-only
# so a Workflow subagent can run them with any python (it need not be the venv) —
# those two only read the on-disk JSON the dump already wrote.

# Prepended to the shared rubric so a batch subagent judges each answer on its own.
# The rubric that follows it is written for a single answer ("the answer"); this
# frames the multi-answer batch and pins the output to one verdict per ITEM.
_BATCH_FRAMING = (
    "You are judging SEVERAL independent AI answers in one pass (to save tokens). "
    "Each answer is tagged with an ITEM index and delimited by a '===== ITEM N ====='"
    " header below. Apply the SHARED RUBRIC to EVERY item, but judge each item "
    "INDEPENDENTLY and using ONLY that item's own answer text — never let one "
    "answer influence another, and use NO outside knowledge about the brands. "
    "Return exactly ONE verdict per ITEM via the structured output, each carrying "
    "the ITEM's index; do not merge, reorder-drop, or skip any item."
)


def _batch_schema() -> dict[str, object]:
    """The forced output shape for a batch subagent: a ``verdicts`` array, one entry
    per ITEM, each the single judge's ``record_judgment`` shape plus the ITEM
    ``index`` (so verdicts realign to items even if the model reorders them)."""
    from src.pipeline.judge import _judgment_tool

    single = cast("dict[str, object]", _judgment_tool()["input_schema"])
    props = cast("dict[str, object]", single.get("properties", {}))
    required = cast("list[object]", single.get("required", []))
    verdict_props: dict[str, object] = {"index": {"type": "integer"}, **props}
    verdict_item: dict[str, object] = {
        "type": "object",
        "properties": verdict_props,
        "required": ["index", *required],
    }
    return {
        "type": "object",
        "properties": {"verdicts": {"type": "array", "items": verdict_item}},
        "required": ["verdicts"],
    }


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
    from src.pipeline.judge import (
        _ACCURACY_BLOCK,
        _ANSWER_HEAD,
        _NO_ACCURACY_BLOCK,
        _RUBRIC_TAIL,
        _SYSTEM,
        _brand_lines,
    )
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

    # Split the judge prompt into the shared RUBRIC tail (brand list + decision
    # rules + accuracy block + fact sheet — identical for every answer in this run)
    # and the tiny per-answer HEAD (question + answer). The rubric is by far the
    # bulk of the tokens, so we store it ONCE in ``preamble`` and each ``batch``
    # subagent reads it a single time for its whole batch — instead of once per
    # answer, which is what fanning out one-subagent-per-answer used to cost.
    accuracy_instructions = (
        _ACCURACY_BLOCK.format(fact_sheet=fact_sheet) if fact_sheet else _NO_ACCURACY_BLOCK
    )
    rubric = _RUBRIC_TAIL.format(
        brand_lines=_brand_lines(client, competitors),
        accuracy_instructions=accuracy_instructions,
    )
    preamble = (
        f"{_SYSTEM}\n\n{_BATCH_FRAMING}\n\n"
        f"===== SHARED RUBRIC (applies to every ITEM below) =====\n{rubric}\n\n"
        f"===== ANSWERS TO JUDGE ====="
    )

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
            # Only the per-answer HEAD is stored per item; the rubric lives in
            # ``preamble``. ``batch`` stitches ``preamble`` + N heads back together.
            body = _ANSWER_HEAD.format(query=query_text, answer=answer)
            items.append({"key": key, "body": body})
    finally:
        cache.close()

    payload = {
        "run_id": run_id,
        "client": client,
        "competitors": competitors,
        "has_fact_sheet": fact_sheet is not None,
        # The output shape forced on each Workflow subagent: a ``verdicts`` array
        # (one entry per ITEM in the batch), each entry the judge's own tool shape
        # plus the ITEM ``index`` — derived from the tool so it can't drift.
        "schema": _batch_schema(),
        "preamble": preamble,
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


def _batch(in_path: str, start: int, count: int) -> int:
    """Print ONE batch's judging prompt: the shared rubric preamble followed by the
    per-answer HEADs for items ``[start, start+count)``, each under a
    ``===== ITEM i =====`` header. This is what a single subagent judges — several
    answers in one call, sharing one copy of the (large) rubric.

    Emits ``{"prompt": ..., "indices": [...]}``. Only the prompt is emitted — not
    the cache keys — because ``inject`` re-attaches the key from the in file by the
    same global index, so a subagent can't garble it. ``indices`` is the list of
    global item indices in this batch (the numbers in the ITEM headers), so the
    caller knows which items it covers."""
    items = _items_of(_load_in(in_path))
    preamble = str(_load_in(in_path).get("preamble", ""))
    lo = max(0, start)
    hi = min(len(items), start + max(0, count))
    blocks: list[str] = []
    indices: list[int] = []
    for i in range(lo, hi):
        blocks.append(f"===== ITEM {i} =====\n{items[i].get('body', '')}")
        indices.append(i)
    if not indices:
        print(f"no items in range [{start}, {start + count}) of {len(items)}", file=sys.stderr)
        print(json.dumps({"prompt": "", "indices": []}))
        return 1
    print(json.dumps({"prompt": preamble + "\n\n" + "\n\n".join(blocks), "indices": indices}))
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

    p_batch = sub.add_parser("batch", help="print one batch's judging prompt (rubric + N answers)")
    p_batch.add_argument("in_path")
    p_batch.add_argument("start", type=int, help="global index of the first item in the batch")
    p_batch.add_argument("count", type=int, help="how many items this batch covers")

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
    if args.cmd == "batch":
        return _batch(args.in_path, args.start, args.count)
    return _inject(args.in_path, args.verdicts, args.offset)


if __name__ == "__main__":
    raise SystemExit(main())
