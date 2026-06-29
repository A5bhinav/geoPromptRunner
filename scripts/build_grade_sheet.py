"""Render a grade-calibration situations file into a human-fillable Markdown sheet.

The grade-calibration analogue of scripts/build_labeling_sheet.py. Reads a
grade_situations JSON (e.g. data/grade_situations_abhi.json) and emits one
Markdown block per situation: the plain-English context + the two formula inputs
(raw_visibility, flag_severities) beside a single editable **grade** cell.

Each situation's editable region is wrapped in `<!-- GRADE item=N -->` ...
`<!-- /GRADE item=N -->` markers so the companion parser can read the filled
sheet back into the JSON's `human_grade` field. The formula's own output is never
shown — blindness is the point (you are the ground truth, not its checker).

Usage:
    python -m scripts.build_grade_sheet data/grade_situations_abhi.json docs/grade-sheet-abhi.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

GRADES = ["A", "B", "C", "D", "F"]
SEVERITY_ORDER = ["high", "med", "low"]


def _legend(title: str) -> list[str]:
    suffix = f" — {title}" if title else ""
    return [
        f"# Grade-Calibration Sheet (Layer 2){suffix}",
        "",
        "Fill the **grade** cell in each block with one letter: "
        f"{' · '.join(f'`{g}`' for g in GRADES)}.",
        "Edit only the cell between the markers — keep the `<!-- GRADE -->` markers intact",
        "so the sheet can be parsed back into the JSON's `human_grade` field.",
        "",
        "**How to grade**",
        "",
        "- **Gut, from the numbers — not the formula.** Read the context, picture the client,",
        "  and write the letter that *feels* defensible. Do **not** run the grade formula first;",
        "  you are the ground truth, not its checker.",
        "- **The question to ask:** *\"If this were the headline grade on a client's audit,",
        "  would it be defensible?\"* A category leader with a few stale nits isn't an F; an",
        "  invisible brand isn't an A.",
        "",
        "**Reading the inputs**",
        "",
        "- **Visibility** (0..1) — prominence-weighted presence. `0.50` ≈ mid-pack on average;",
        "  `0.10` ≈ barely there; `0.00` ≈ absent everywhere.",
        "- **Accuracy flags** — distinct client errors by severity (`high` misleads a buyer,",
        "  `med` outdated/incomplete, `low` cosmetic).",
        "",
        "---",
        "",
    ]


def _flag_summary(severities: list[str]) -> str:
    if not severities:
        return "none"
    counts = Counter(severities)
    parts = [f"{sev} ×{counts[sev]}" for sev in SEVERITY_ORDER if counts.get(sev)]
    # include any unexpected severities at the end so nothing is silently dropped
    parts += [f"{sev} ×{n}" for sev, n in counts.items() if sev not in SEVERITY_ORDER]
    return " · ".join(parts)


def _item_section(idx: int, sit: dict[str, object]) -> list[str]:
    label = sit.get("label", f"situation {idx}")
    context = sit.get("_context", "")
    vis = sit.get("raw_visibility", 0.0)
    raw_flags = sit.get("flag_severities", [])
    severities = [str(s) for s in raw_flags] if isinstance(raw_flags, list) else []
    flags = _flag_summary(severities)
    current = str(sit.get("human_grade", "") or "").strip()

    lines = [
        f"## Item {idx} · {label}",
        "",
    ]
    if context:
        lines += [f"> {context}", ""]
    lines += [
        f"- **Visibility:** {vis}",
        f"- **Accuracy flags:** {flags}",
        "",
        f"<!-- GRADE item={idx} -->",
        "",
        f"**Grade (A/B/C/D/F):** `{current}`",
        "",
        f"<!-- /GRADE item={idx} -->",
        "",
        "---",
        "",
    ]
    return lines


def build_sheet(
    situations_path: Path, only: str | None = None, title: str | None = None
) -> tuple[str, int]:
    """Render the sheet. ``only`` keeps situations whose label contains it
    (case-insensitive); original indices are preserved so the parser writes the
    grade back to the right row of the source JSON. Returns (markdown, count)."""
    data = json.loads(situations_path.read_text())
    situations = data["situations"]
    out = _legend(title if title is not None else (only or ""))
    n = 0
    for i, sit in enumerate(situations):
        if only and only.lower() not in str(sit.get("label", "")).lower():
            continue
        out += _item_section(i, sit)
        n += 1
    out.append(
        f"_Generated from `{situations_path.name}` — {n} of {len(situations)} situations to grade._"
    )
    out.append("")
    return "\n".join(out), n


def main() -> int:
    ap = argparse.ArgumentParser(prog="build_grade_sheet")
    ap.add_argument(
        "situations",
        help="path to a grade_situations JSON (e.g. data/grade_situations.json)",
    )
    ap.add_argument("out", nargs="?", default="docs/grade-sheet.md")
    ap.add_argument(
        "--filter",
        dest="only",
        default=None,
        help="only include situations whose label contains this (e.g. 'Fort'); indices preserved",
    )
    ap.add_argument("--title", default=None, help="heading suffix (defaults to the filter value)")
    args = ap.parse_args()

    situations_path = Path(args.situations)
    sheet, n = build_sheet(situations_path, only=args.only, title=args.title)
    out_path = Path(args.out)
    out_path.write_text(sheet)
    print(f"Wrote {out_path} — {n} situations, {len(sheet.splitlines())} lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
