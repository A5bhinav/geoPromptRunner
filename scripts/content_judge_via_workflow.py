"""Pre-fill the CONTENT notebook (on-site ContentJudge verdicts) on the subscription.

The site-audit sibling of ``scripts/judge_via_workflow.py``. The crawl already
persisted each page's text to Supabase (``site_audit_page``); this judges the 6
subjective Cat 3/4 checks over those pages on the subscription and writes the
verdicts into ``content_judge_cache`` — so a later ``run_site_audit`` (or its
report step) finds them warm and spends no API. See docs/subscription-judge-plan.md.

Unit of work = one PAGE per subagent: the page text is sent once and all of its
not-yet-cached checks are judged together (token-efficient), returning one verdict
per check. Verdicts are keyed by ``content_cache_key`` — identical to what the live
``ContentJudge`` looks up — so parity holds regardless of this batching.

    dump   — pull the run's crawled pages from Supabase, compute the content-address
             key for each (page, check), skip already-cached, and render one combined
             judging prompt per page. Writes one JSON "in" file.
    header — the in file's metadata (no bulky page text/prompts).
    page   — print ONE page's judging prompt (stdlib-only; a subagent runs this).
    inject — given the in file + the Workflow's per-page verdicts, finalize each
             CheckVerdict (evidence validation) and write it into the content cache
             under the in file's key. Keys come from the in file, never the subagent.

Usage:
    python -m scripts.content_judge_via_workflow dump <run_id> [--out PATH]
    python -m scripts.content_judge_via_workflow header <in.json>
    python -m scripts.content_judge_via_workflow page <in.json> <page_index>
    python -m scripts.content_judge_via_workflow inject <in.json> <verdicts.json>
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.audit.checks.content_judge import ContentCheck

# Heavy imports (content_judge / db / settings pull in anthropic / supabase) live
# INSIDE _dump / _inject so ``header`` and ``page`` stay stdlib-only — a subagent can
# run them with any python; they only read the on-disk JSON the dump already wrote.


def _output_schema() -> dict[str, object]:
    """The forced output shape for a page subagent: a ``verdicts`` array, one entry
    per check, each carrying the check id + its yes/no/unknown sub-answers. Mirrors
    the content_prejudge_workflow.js SCHEMA (kept here for the dump's header)."""
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "check_id": {"type": "string"},
                        "sub_answers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "reasoning": {"type": "string"},
                                    "evidence_quote": {"type": "string"},
                                    "answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
                                },
                                "required": ["key", "reasoning", "evidence_quote", "answer"],
                            },
                        },
                    },
                    "required": ["check_id", "sub_answers"],
                },
            }
        },
        "required": ["verdicts"],
    }


def _render_page_prompt(url: str, text: str, checks: list[ContentCheck]) -> str:
    from src.audit.checks.content_judge import _SYSTEM

    blocks = []
    for c in checks:
        qs = "\n".join(f"- [{q.key}] {q.text}" for q in c.sub_questions)
        blocks.append(f"===== CHECK: {c.check_id} — {c.title} =====\nSub-questions:\n{qs}")
    return (
        f"{_SYSTEM}\n\n"
        "You are judging SEVERAL rubric checks against ONE page in a single pass. For "
        "EACH check below, answer its sub-questions yes / no / unknown; for every 'yes' "
        "copy a short VERBATIM quote from the page text (if you cannot quote it, answer "
        "no or unknown). Judge ONLY from the page text, never outside knowledge. Return "
        "exactly one entry per check via the structured output, tagged with the check's "
        f"id.\n\nPage URL: {url}\n\nPage text:\n\"\"\"\n{text}\n\"\"\"\n\n" + "\n\n".join(blocks)
    )


def _dump(run_id: str, out_path: str | None) -> int:
    from src.audit.checks.content_judge import (
        _MAX_TEXT_CHARS,
        CONTENT_CHECKS,
        content_cache_key,
    )
    from src.audit.checks.content_judge_cache import make_content_judge_cache
    from src.config import settings
    from src.storage import db

    model = settings.JUDGE_MODEL
    cache = make_content_judge_cache()

    page_rows = db.get_site_audit_pages(run_id)
    pages: list[dict[str, object]] = []
    total_checks = 0
    cached = 0
    for row in page_rows:
        url = str(row.get("normalized_url") or "")
        raw_text = row.get("extracted_text")
        if not raw_text:
            continue
        text = str(raw_text)[:_MAX_TEXT_CHARS]
        # Which checks for this page are NOT already cached?
        keys = {c.check_id: content_cache_key(model, c, text) for c in CONTENT_CHECKS}
        have = cache.get_many(list(keys.values()))
        todo = []
        item_checks = []
        for c in CONTENT_CHECKS:
            if keys[c.check_id] in have:
                cached += 1
                continue
            todo.append(c)
            item_checks.append({"check_id": c.check_id, "key": keys[c.check_id]})
        if not todo:
            continue
        total_checks += len(todo)
        pages.append(
            {
                "url": url,
                "text": text,
                "checks": item_checks,
                "prompt": _render_page_prompt(url, text, todo),
            }
        )

    payload = {"run_id": run_id, "model": model, "schema": _output_schema(), "pages": pages}
    default_out = Path(tempfile.gettempdir()) / f"content_prejudge_{run_id}.in.json"
    out = Path(out_path) if out_path else default_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload))
    print(
        f"Dumped {len(pages)} page(s) / {total_checks} check(s) to judge "
        f"({cached} already cached, {len(page_rows)} crawled pages total)."
    )
    print(f"Workflow input: {out}")
    if not pages:
        print("Nothing to judge — the content cache is already warm (or no crawled pages).")
    return 0


def _load_in(in_path: str) -> dict[str, object]:
    data = json.loads(Path(in_path).read_text())
    return data if isinstance(data, dict) else {}


def _pages_of(d: dict[str, object]) -> list[dict[str, object]]:
    raw = d.get("pages")
    return [p for p in raw if isinstance(p, dict)] if isinstance(raw, list) else []


def _header(in_path: str) -> int:
    d = _load_in(in_path)
    pages = _pages_of(d)
    print(
        json.dumps(
            {
                "run_id": d.get("run_id"),
                "model": d.get("model"),
                "schema": d.get("schema"),
                "page_count": len(pages),
                "check_count": sum(len(_checks_of(p)) for p in pages),
            }
        )
    )
    return 0


def _checks_of(page: dict[str, object]) -> list[dict[str, str]]:
    raw = page.get("checks")
    return [c for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []


def _page(in_path: str, index: int) -> int:
    """Print ONE page's combined judging prompt + the check ids it covers."""
    pages = _pages_of(_load_in(in_path))
    if index < 0 or index >= len(pages):
        print(f"page index {index} out of range (0..{len(pages) - 1})", file=sys.stderr)
        return 1
    page = pages[index]
    ids = [c.get("check_id") for c in _checks_of(page)]
    print(json.dumps({"prompt": str(page.get("prompt", "")), "check_ids": ids}))
    return 0


def _inject(in_path: str, verdicts_path: str) -> int:
    """Write the Workflow's per-page verdicts into the content cache.

    ``verdicts_path`` holds ``{"pages": [ {page_index, verdicts:[{check_id, sub_answers}]}
    | null ] }``. Each check's verdict is finalized (evidence validation, truth table)
    against the page text and stored under the in file's key for that (page, check).
    A null page / missing verdict / failure reason is skipped."""
    from src.audit.checks.content_judge import (
        _UNCACHEABLE_REASONS,
        CONTENT_CHECKS,
        CheckVerdict,
        finalize_check,
    )
    from src.audit.checks.content_judge_cache import make_content_judge_cache

    d = _load_in(in_path)
    pages = _pages_of(d)
    by_id = {c.check_id: c for c in CONTENT_CHECKS}
    raws = json.loads(Path(verdicts_path).read_text()).get("pages") or []

    cache = make_content_judge_cache()
    stored: list[tuple[str, CheckVerdict]] = []
    skipped = 0
    for entry in raws:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        pi = entry.get("page_index")
        if not isinstance(pi, int) or pi < 0 or pi >= len(pages):
            skipped += 1
            continue
        page = pages[pi]
        text = str(page.get("text", ""))
        key_by_check = {c["check_id"]: c["key"] for c in _checks_of(page)}
        for v in entry.get("verdicts") or []:
            if not isinstance(v, dict):
                skipped += 1
                continue
            cid = str(v.get("check_id", ""))
            check = by_id.get(cid)
            key = key_by_check.get(cid)
            subs = v.get("sub_answers")
            if check is None or key is None or not isinstance(subs, list):
                skipped += 1
                continue
            verdict = finalize_check(check, subs, text)
            if verdict.reason in _UNCACHEABLE_REASONS:  # never cache a failure
                skipped += 1
                continue
            stored.append((str(key), verdict))
    cache.put_many(stored)
    print(f"Injected {len(stored)} content verdict(s) into the cache ({skipped} skipped).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dump = sub.add_parser("dump", help="emit the Workflow's input file for a run")
    p_dump.add_argument("run_id")
    p_dump.add_argument("--out", help="where to write the Workflow input JSON")

    p_header = sub.add_parser("header", help="print the in file's metadata")
    p_header.add_argument("in_path")

    p_page = sub.add_parser("page", help="print one page's judging prompt by index")
    p_page.add_argument("in_path")
    p_page.add_argument("index", type=int)

    p_inject = sub.add_parser("inject", help="write the Workflow's verdicts into the content cache")
    p_inject.add_argument("in_path")
    p_inject.add_argument("verdicts")

    args = parser.parse_args(argv)
    if args.cmd == "dump":
        return _dump(args.run_id, args.out)
    if args.cmd == "header":
        return _header(args.in_path)
    if args.cmd == "page":
        return _page(args.in_path, args.index)
    return _inject(args.in_path, args.verdicts)


if __name__ == "__main__":
    raise SystemExit(main())
