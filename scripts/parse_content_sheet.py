"""Read a filled content-labeling sheet back into the gold JSONL the κ gate consumes.

The companion to ``build_content_sheet.py``. Reads the ``<!-- LABELS url=... -->`` blocks,
validates every label, and writes one JSON object per page in the shape
``content_calibration.load_gold_set`` expects: ``{page_url, text, labels}``.

Refuses to write a partially-valid file. A gold set is the ground truth the judge is
scored against, so a typo silently becoming a label would corrupt the κ that decides
whether the judge ships — the failure would look like a judge problem forever after.
Unfilled labels (``____``) are dropped, which is intended: skipping a page/check pair you
are unsure about is better than guessing, and `score_check` simply scores fewer pairs.

Usage:
    python -m scripts.parse_content_sheet docs/content-labeling-sheet.md data/content_gold.jsonl
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.audit.checks.content_judge import CONTENT_CHECKS


@dataclass(frozen=True)
class GoldRow:
    """One page's human labels, in the shape ``load_gold_set`` reads."""

    page_url: str
    text: str
    labels: dict[str, str]


_VALID_LABELS = {"pass", "partial", "fail"}
_BLOCK_RE = re.compile(
    r"<!--\s*LABELS url=(?P<url>\S+?)\s*-->(?P<body>.*?)<!--\s*/LABELS\s*-->",
    re.DOTALL,
)
_LINE_RE = re.compile(r"^\s*-\s*(?P<check>[a-z_]+)\s*:\s*(?P<label>\S*)\s*$", re.MULTILINE)
# The text block immediately preceding a LABELS marker, so the gold row carries the same
# text the labeler ruled on rather than a re-crawl that may have changed underneath.
_TEXT_RE = re.compile(r"```text\n(?P<text>.*?)\n```", re.DOTALL)


def parse_sheet(markdown: str) -> tuple[list[GoldRow], list[str]]:
    """Return (rows, errors). Rows are gold objects; any error means write nothing."""
    known = {c.check_id for c in CONTENT_CHECKS}
    rows: list[GoldRow] = []
    errors: list[str] = []

    texts = _TEXT_RE.findall(markdown)
    for index, match in enumerate(_BLOCK_RE.finditer(markdown)):
        url = match.group("url")
        labels: dict[str, str] = {}
        for line in _LINE_RE.finditer(match.group("body")):
            check, raw = line.group("check"), line.group("label").strip().lower()
            if check not in known:
                errors.append(f"{url}: unknown check id {check!r}")
                continue
            if raw in ("____", ""):
                continue  # deliberately unlabeled — dropped, not guessed
            if raw not in _VALID_LABELS:
                errors.append(
                    f"{url}: {check} has {raw!r}; expected one of {sorted(_VALID_LABELS)}"
                )
                continue
            labels[check] = raw
        if not labels:
            continue  # page skipped entirely
        text = texts[index] if index < len(texts) else ""
        rows.append(GoldRow(page_url=url, text=text, labels=labels))
    return rows, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sheet", help="the filled Markdown labeling sheet")
    parser.add_argument("out", help="path to write the gold JSONL")
    args = parser.parse_args()

    rows, errors = parse_sheet(Path(args.sheet).read_text(encoding="utf-8"))
    if errors:
        print(f"{len(errors)} problem(s) — nothing written:")
        for err in errors[:20]:
            print(f"  {err}")
        return 1
    if not rows:
        print("no labeled pages found — fill in some labels first")
        return 1

    with Path(args.out).open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dataclasses.asdict(row)) + "\n")
    total = sum(len(row.labels) for row in rows)
    print(f"wrote {args.out}: {len(rows)} pages, {total} labels")
    print("Then run the κ gate: python -m src.audit.checks.content_calibration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
