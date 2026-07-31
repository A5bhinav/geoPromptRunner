"""Render a blind gold-set skeleton into a human-fillable Markdown labeling sheet.

Reads a v2 gold file (e.g. data/local_gold.json) and emits one Markdown section
per item: the verbatim answer beside a pre-filled label table + flag/candidate
blocks. Defaults come straight from the skeleton (absent/neutral), so "losing
query" items need few or no edits.

Each item's editable region is wrapped in `<!-- LABELS item=N -->` ...
`<!-- /LABELS item=N -->` markers so `parse_labeling_sheet.py` can read the filled
sheet back into the gold JSON. The judge's verdicts are never shown — blindness is
the point (a labeler must not rubber-stamp the judge's own call).

Three things here exist to make an hour of labeling survivable, and each is a
deliberate line between HELP and ANSWER:

* **Items are grouped by query**, so the four engines' answers to one question sit
  together. Prominence is relative *within* an answer, but a labeler calibrates it
  far more consistently having just read three siblings. `parse_labeling_sheet`
  keys on the `item=N` marker, not on file order, so regrouping is free.
* **Every item carries the vocabulary inline.** A legend 2,000 lines up is a
  legend nobody reads; a mistyped enum is a validation error at the end of the
  afternoon.
* **Mention evidence per brand** — literal match count and where the first one
  falls in the answer. This is mechanical fact, NOT a suggested label: it is the
  scanning a human would otherwise do by eye, and it is exactly what prominence is
  read from. The label stays the human's, and `present` is deliberately still
  defaulted to `no` rather than pre-filled from the match, because a pre-filled
  answer gets rubber-stamped and a disavowal ("there is no such plumber") names
  the brand while meaning the opposite.

Usage:
    python -m scripts.build_labeling_sheet data/local_gold.json docs/local-labeling-sheet.md
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from src.storage.models import AccuracyFlagType

PROMINENCE = ["recommended_first", "mid_pack", "buried", "also_ran", "absent"]
FRAMING = ["positive", "neutral", "negative"]
# Read from the enum, never re-typed. This list was a hardcoded copy of the five
# CONSUMER types, so a local sheet offered a labeler no way to record wrong_hours,
# wrong_service_area, wrong_contact or licensing — the four dimensions a
# service-area gold set exists to calibrate. A label that cannot be written is a
# false negative in the ground truth, which then reads as judge recall.
FLAG_TYPES = [t.value for t in AccuracyFlagType]
SEVERITY = ["high", "med", "low"]


def _mentions(answer: str, brand: str) -> tuple[int, float | None]:
    """``(count, first-position as a fraction)`` for a literal, case-insensitive match.

    Word-boundaried so "Fort" does not match "comfort". Returns the position as a
    fraction of the answer because that is the shape prominence is judged on — a
    brand first named 4% in reads very differently from one at 85%.
    """
    if not answer or not brand:
        return 0, None
    hits = list(re.finditer(rf"\b{re.escape(brand)}\b", answer, re.I))
    if not hits:
        return 0, None
    return len(hits), hits[0].start() / max(len(answer), 1)


def _evidence_lines(answer: str, brands: list[str]) -> list[str]:
    lines = [
        "**Where each name appears** — literal text match, so you do not have to scan for it.",
        "This is evidence, not a label: a disavowal (\"there is no such company\") names the "
        "brand while meaning the opposite, and only you can see that.",
        "",
    ]
    for brand in brands:
        count, pos = _mentions(answer, brand)
        if count == 0:
            lines.append(f"- `{brand}` — **not found**")
        else:
            times = "once" if count == 1 else f"{count}×"
            assert pos is not None
            lines.append(f"- `{brand}` — {times}, first at **{pos:.0%}** through the answer")
    lines.append("")
    return lines


def _legend(client: str, fact_sheet: str | None, n_items: int) -> list[str]:
    lines = [
        f"# {client} — Gold-Set Labeling Sheet",
        "",
        f"{n_items} answers to label. Work down the file; items are **grouped by question**, so "
        "you read all four engines' answers to one query together and judge them consistently.",
        "",
        "Edit only the cells inside the `<!-- LABELS -->` markers — leave the markers alone, "
        "they are how the sheet is read back. Pipe alignment does not matter; "
        "`|Acme|yes|mid_pack|positive|` parses fine.",
        "",
        "When you are done:",
        "",
        "```bash",
        "python -m scripts.parse_labeling_sheet SHEET.md GOLD.json          # validate",
        "python -m scripts.parse_labeling_sheet SHEET.md GOLD.json --write  # apply",
        "```",
        "",
        "It validates every value and refuses to write if anything is off, so a typo costs "
        "you a re-run and never a corrupted set.",
        "",
        "## The three columns",
        "",
        "| column | values | what it means |",
        "| --- | --- | --- |",
        "| `present` | `yes` · `no` | Is the brand named at all? A **disavowal** — \"there is no "
        "such company\", \"I have no information about them\" — is `no`. The name appearing only "
        "because the question contained it is also `no`. |",
        f"| `prominence` | {' · '.join(f'`{p}`' for p in PROMINENCE)} | Relative *within this "
        "answer*: who is named first vs. buried at the bottom. Must be `absent` when "
        "`present=no`, and must not be when `present=yes`. |",
        f"| `framing` | {' · '.join(f'`{f}`' for f in FRAMING)} | How the answer treats it. "
        "Absent brands stay `neutral`. |",
        "",
        "## The flags block",
        "",
        f"Real errors the answer makes **about {client} only** — never about a competitor. "
        "One per line, `type | severity | note`. Leave it empty when the answer is accurate.",
        "",
        f"- **types** — {' · '.join(f'`{t}`' for t in FLAG_TYPES)}",
        f"- **severity** — {' · '.join(f'`{s}`' for s in SEVERITY)}",
        "",
        "A flag needs a line in the fact sheet below that the answer **contradicts**. If the "
        "sheet is silent on the topic, that is not a flag — put it in **uncovered claims** "
        "instead, which is the list of things the judge must *not* flag.",
        "",
    ]
    if fact_sheet:
        lines += [
            f"<details><summary><b>Ground truth — the {client} fact sheet</b> "
            "(open this before writing any flag)</summary>",
            "",
            fact_sheet.rstrip(),
            "",
            "</details>",
            "",
        ]
    else:
        lines += [
            f"> No fact sheet embedded — {client} accuracy is not assessed on this set, "
            "so leave every flags block empty.",
            "",
        ]
    return lines


def _index(groups: list[tuple[str, list[tuple[int, dict]]]]) -> list[str]:
    """A contents table: what is in the file, in the order it appears."""
    lines = [
        "## What you are labeling",
        "",
        "| question | items | engines |",
        "| --- | --- | --- |",
    ]
    for query, members in groups:
        nums = ", ".join(str(i) for i, _ in members)
        engines = ", ".join(sorted({str(it.get("engine", "?")) for _, it in members}))
        lines.append(f"| {query} | {nums} | {engines} |")
    lines += ["", "---", ""]
    return lines


def _present_str(label: dict) -> str:
    return "yes" if label.get("present") else "no"


def _item_section(idx: int, item: dict, position: str) -> list[str]:
    query = item.get("query", "")
    engine = item.get("engine", "?")
    client = item.get("client", "Client")
    competitors = item.get("competitors", [])
    answer = item.get("answer", "") or ""
    labels = item.get("labels", {})

    brands = [client] + [c for c in competitors if c != client]

    lines = [
        f"## Item {idx} · `{engine}`",
        "",
        f"> {query}",
        "",
        f"*{position}. Client: **{client}**. Competitors: {', '.join(competitors) or '—'}.*",
        "",
    ]
    lines += _evidence_lines(answer, brands)
    lines += [
        "<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>",
        "",
        "```text",
        answer.rstrip(),
        "```",
        "",
        "</details>",
        "",
        f"<!-- LABELS item={idx} -->",
        "",
        f"`present` yes/no · `prominence` {' / '.join(PROMINENCE)} · "
        f"`framing` {' / '.join(FRAMING)}",
        "",
        "| brand | present | prominence | framing |",
        "| --- | --- | --- | --- |",
    ]
    for b in brands:
        lab = labels.get(b, {})
        lines.append(
            f"| {b} | {_present_str(lab)} | "
            f"{lab.get('prominence', 'absent')} | {lab.get('framing', 'neutral')} |"
        )
    lines += [
        "",
        f"**Flags about {client}** — `type | severity | note`, one per line. Empty = accurate.",
        "",
        "```flags",
        "",
        "```",
        "",
        "**Uncovered claims** — things the answer asserts that the fact sheet does not cover, "
        "one per line. The judge must not flag these.",
        "",
        "```candidates",
        "",
        "```",
        "",
        f"<!-- /LABELS item={idx} -->",
        "",
        "---",
        "",
    ]
    return lines


def _grouped(items: list[dict]) -> list[tuple[str, list[tuple[int, dict]]]]:
    """Items bucketed by query, each keeping its ORIGINAL index.

    The index is the join key `parse_labeling_sheet` merges on, so it must survive
    the regrouping — the file's order is presentation, the marker is contract.
    """
    order: list[str] = []
    buckets: dict[str, list[tuple[int, dict]]] = {}
    for i, item in enumerate(items):
        query = str(item.get("query", ""))
        if query not in buckets:
            buckets[query] = []
            order.append(query)
        buckets[query].append((i, item))
    return [(q, buckets[q]) for q in order]


def build_sheet(gold_path: Path) -> str:
    items = json.loads(gold_path.read_text())["items"]
    client = next((str(it["client"]) for it in items if it.get("client")), "Client")
    fact_sheet = next((it.get("fact_sheet") for it in items if it.get("fact_sheet")), None)
    groups = _grouped(items)

    out = _legend(client, fact_sheet, len(items))
    out += _index(groups)
    for query, members in groups:
        out += [f"# Question: {query}", ""]
        for n, (idx, item) in enumerate(members, start=1):
            out += _item_section(idx, item, f"answer {n} of {len(members)} to this question")
    out.append(f"_Generated from `{gold_path.name}` — {len(items)} items to label._")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(prog="build_labeling_sheet")
    ap.add_argument("gold", help="path to the v2 gold skeleton (e.g. data/local_gold.json)")
    ap.add_argument("out", nargs="?", default="docs/oura-labeling-sheet.md")
    args = ap.parse_args()

    gold_path = Path(args.gold)
    sheet = build_sheet(gold_path)
    out_path = Path(args.out)
    out_path.write_text(sheet)
    n = len(json.loads(gold_path.read_text())["items"])
    print(f"Wrote {out_path} — {n} items, {len(sheet.splitlines())} lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
