"""Render a blind gold-set skeleton into a human-fillable Markdown labeling sheet.

Reads a v2 gold file (e.g. data/oura_gold.json) and emits one Markdown section
per item: the verbatim answer (fenced so its own markdown can't break the sheet)
beside a pre-filled label table + flag/candidate blocks. Defaults come straight
from the skeleton (absent/neutral), so "losing query" items need few or no edits.

Each item's editable region is wrapped in `<!-- LABELS item=N -->` ...
`<!-- /LABELS -->` markers so a companion parser can later read the filled sheet
back into the gold JSON. The judge's verdicts are never shown — blindness is the
point (a labeler must not rubber-stamp the judge's own call).

Usage:
    python -m scripts.build_labeling_sheet data/oura_gold.json docs/oura-labeling-sheet.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROMINENCE = ["recommended_first", "mid_pack", "buried", "also_ran", "absent"]
FRAMING = ["positive", "neutral", "negative"]
FLAG_TYPES = [
    "wrong_pricing",
    "missing_or_invented_feature",
    "competitor_confusion",
    "identity",
    "stale",
]
SEVERITY = ["high", "med", "low"]


def _legend(client: str, fact_sheet: str | None) -> list[str]:
    lines = [
        f"# {client} Gold-Set Labeling Sheet",
        "",
        "Read each answer, then fill the **Label** table and the **Flags** block beneath it.",
        "Edit only the cells — keep the `<!-- LABELS -->` markers intact so the sheet can be",
        "parsed back into the gold JSON. The judge's own verdicts are deliberately omitted.",
        "",
        "**How to label each brand row**",
        "",
        "- **present** — `yes` / `no`: is the brand named anywhere in the answer?",
        f"- **prominence** — one of: {' · '.join(f'`{p}`' for p in PROMINENCE)}. "
        "Relative within *this* answer (who is named first vs. buried). `absent` iff present=no.",
        f"- **framing** — one of: {' · '.join(f'`{f}`' for f in FRAMING)}. "
        "Absent brands stay `neutral`.",
        "",
        f"**Flags** = real errors the answer makes **about {client}** "
        "(the client only — not competitors).",
        f"Format per line: `type | severity | note`. "
        f"Types: {' · '.join(f'`{t}`' for t in FLAG_TYPES)}. "
        f"Severity: {' · '.join(f'`{s}`' for s in SEVERITY)}. "
        f"Leave the block empty if the answer is accurate about {client}.",
        "",
        "**Uncovered claims** (optional) = claims the answer makes that the fact sheet does NOT",
        "cover — the judge must *not* flag these. One per line.",
        "",
    ]
    if fact_sheet:
        lines += [
            f"<details><summary><b>Ground truth — {client} fact sheet</b> "
            "(the source of truth for the Flags column)</summary>",
            "",
            fact_sheet.rstrip(),
            "",
            "</details>",
            "",
        ]
    else:
        lines += [
            f"> No fact sheet embedded — {client} accuracy is not assessed on this set.",
            "",
        ]
    lines += ["---", ""]
    return lines


def _present_str(label: dict) -> str:
    return "yes" if label.get("present") else "no"


def _item_section(idx: int, item: dict) -> list[str]:
    query = item.get("query", "")
    engine = item.get("engine", "?")
    client = item.get("client", "Client")
    competitors = item.get("competitors", [])
    answer = item.get("answer", "")
    labels = item.get("labels", {})

    # Brand order: client first, then competitors as listed.
    brands = [client] + [c for c in competitors if c != client]

    lines = [
        f"## Item {idx} · `{engine}` · _{query}_",
        "",
        f"**Client:** {client}  ·  **Competitors:** {', '.join(competitors) or '—'}",
        "",
        "<details open><summary><b>Answer</b> (click to collapse)</summary>",
        "",
        "```text",
        answer.rstrip(),
        "```",
        "",
        "</details>",
        "",
        f"<!-- LABELS item={idx} -->",
        "",
        "**Label** — edit the `prominence` / `framing` / `present` cells:",
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
        f"**Flags** about {client} — `type | severity | note` per line (empty = accurate):",
        "",
        "```flags",
        "",
        "```",
        "",
        "**Uncovered claims** (optional) — one per line:",
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


def build_sheet(gold_path: Path) -> str:
    items = json.loads(gold_path.read_text())["items"]
    client = next((str(it["client"]) for it in items if it.get("client")), "Client")
    fact_sheet = next((it.get("fact_sheet") for it in items if it.get("fact_sheet")), None)
    out = _legend(client, fact_sheet)
    for i, item in enumerate(items):
        out += _item_section(i, item)
    out.append(f"_Generated from `{gold_path.name}` — {len(items)} items to label._")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(prog="build_labeling_sheet")
    ap.add_argument("gold", help="path to the v2 gold skeleton (e.g. data/oura_gold.json)")
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
