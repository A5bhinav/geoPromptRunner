"""Parse a filled Markdown labeling sheet back into a v2 gold JSON.

Inverse of scripts/build_labeling_sheet.py. Reads each `<!-- LABELS item=N -->`
region — the brand table + the ```flags``` / ```candidates``` fenced blocks —
validates every value against the allowed enums and the present/absent
invariant, and merges the human labels into the gold file's items (matched by
index). Validation errors are reported; nothing is written unless --write is
passed AND the sheet is error-free (or --force is given).

Usage:
    python scripts/parse_labeling_sheet.py SHEET.md GOLD.json           # validate only
    python scripts/parse_labeling_sheet.py SHEET.md GOLD.json --write   # apply
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROMINENCE = {"recommended_first", "mid_pack", "buried", "also_ran", "absent"}
FRAMING = {"positive", "neutral", "negative"}
FLAG_TYPES = {
    "wrong_pricing",
    "missing_or_invented_feature",
    "competitor_confusion",
    "identity",
    "stale",
}
SEVERITY = {"high", "med", "low"}

_BLOCK = re.compile(r"<!-- LABELS item=(\d+) -->(.*?)<!-- /LABELS item=\1 -->", re.S)
_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|", re.M)
_FENCE = lambda tag, b: (  # noqa: E731
    m.group(1) if (m := re.search(rf"```{tag}\n(.*?)```", b, re.S)) else ""
)


def _parse_block(idx: int, body: str, errors: list[str]) -> dict:
    """Parse one LABELS region into {labels, expected_flags, fact_sheet_candidates}."""
    labels: dict[str, dict] = {}
    for brand, present_s, prom, fram in _ROW.findall(body):
        if brand.strip().lower() == "brand" or set(brand.strip()) <= {"-"}:
            continue
        brand = brand.strip()
        present = present_s.lower() == "yes"
        if present_s.lower() not in {"yes", "no"}:
            errors.append(f"item {idx} · {brand}: present='{present_s}' (want yes/no)")
        if prom not in PROMINENCE:
            errors.append(f"item {idx} · {brand}: prominence='{prom}' is not a valid value")
        if fram not in FRAMING:
            errors.append(
                f"item {idx} · {brand}: framing='{fram}' is not a valid value "
                f"(did a prominence word land in the framing column?)"
            )
        if present and prom == "absent":
            errors.append(f"item {idx} · {brand}: present=yes but prominence=absent")
        if not present and prom != "absent":
            errors.append(f"item {idx} · {brand}: present=no but prominence='{prom}' (want absent)")
        labels[brand] = {"present": present, "prominence": prom, "framing": fram}

    flags: list[dict] = []
    for ln in _FENCE("flags", body).splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = [p.strip() for p in ln.split("|")]
        if len(parts) < 2:
            errors.append(f"item {idx} · flag '{ln}': want 'type | severity | note'")
            continue
        ftype, sev = parts[0], parts[1]
        note = parts[2] if len(parts) > 2 else ""
        if ftype not in FLAG_TYPES:
            errors.append(f"item {idx} · flag type='{ftype}' is not valid")
        if sev not in SEVERITY:
            errors.append(f"item {idx} · flag severity='{sev}' is not valid")
        flags.append({"type": ftype, "severity": sev, "note": note})

    cands = [ln.strip() for ln in _FENCE("candidates", body).splitlines() if ln.strip()]
    return {"labels": labels, "expected_flags": flags, "fact_sheet_candidates": cands}


def main() -> int:
    ap = argparse.ArgumentParser(prog="parse_labeling_sheet")
    ap.add_argument("sheet")
    ap.add_argument("gold")
    ap.add_argument("--write", action="store_true", help="apply labels back into the gold file")
    ap.add_argument("--force", action="store_true", help="write even if validation errors exist")
    args = ap.parse_args()

    sheet = Path(args.sheet).read_text()
    gold_path = Path(args.gold)
    gold = json.loads(gold_path.read_text())
    items = gold["items"]

    errors: list[str] = []
    parsed: dict[int, dict] = {}
    blocks = _BLOCK.findall(sheet)
    for idx_s, body in blocks:
        idx = int(idx_s)
        parsed[idx] = _parse_block(idx, body, errors)

    n_present = sum(1 for p in parsed.values() if any(v["present"] for v in p["labels"].values()))
    n_flags = sum(len(p["expected_flags"]) for p in parsed.values())
    n_cands = sum(len(p["fact_sheet_candidates"]) for p in parsed.values())

    print(f"Parsed {len(parsed)}/{len(items)} label regions.")
    print(f"  items with >=1 present brand: {n_present}")
    print(f"  total expected_flags: {n_flags}")
    print(f"  total fact_sheet_candidates: {n_cands}")
    if errors:
        print(f"\n{len(errors)} validation issue(s):")
        for e in errors:
            print(f"  - {e}")
    else:
        print("\nNo validation issues.")

    if not args.write:
        print("\n(validate-only — pass --write to apply)")
        return 1 if errors else 0
    if errors and not args.force:
        print("\nNot writing: fix the issues above or pass --force.")
        return 1

    for idx, p in parsed.items():
        it = items[idx]
        it["labels"] = p["labels"]
        it["expected_flags"] = p["expected_flags"]
        it["fact_sheet_candidates"] = p["fact_sheet_candidates"]
        it.pop("_todo", None)
    gold_path.write_text(json.dumps(gold, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(parsed)} labeled items into {gold_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
