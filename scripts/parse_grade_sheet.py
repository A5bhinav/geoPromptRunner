"""Parse a filled grade-calibration sheet back into a grade_situations JSON.

Inverse of scripts/build_grade_sheet.py. Reads each `<!-- GRADE item=N -->`
region, pulls the single A/B/C/D/F letter, validates it, and merges it into the
JSON's situations (matched by index) as `human_grade`. Validation issues are
reported; nothing is written unless --write is passed AND the sheet is
error-free (or --force is given).

Usage:
    python scripts/parse_grade_sheet.py SHEET.md SITUATIONS.json           # validate only
    python scripts/parse_grade_sheet.py SHEET.md SITUATIONS.json --write   # apply
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

GRADES = {"A", "B", "C", "D", "F"}

_BLOCK = re.compile(r"<!-- GRADE item=(\d+) -->(.*?)<!-- /GRADE item=\1 -->", re.S)
# The grade is the first letter inside backticks, or after the "Grade ...:" label.
_BACKTICK = re.compile(r"`\s*([A-Za-z])\s*`")
_LABELLED = re.compile(r"[Gg]rade[^:`\n]*:\s*([A-Za-z])\b")


def _extract_grade(idx: int, body: str, errors: list[str]) -> str:
    # A blank cell is not an error — it's just unfilled (reported via the
    # "still blank" list). Only a present-but-invalid letter is a hard error.
    m = _BACKTICK.search(body) or _LABELLED.search(body)
    if not m:
        return ""
    grade = m.group(1).upper()
    if grade not in GRADES:
        errors.append(f"item {idx}: grade='{grade}' is not one of A/B/C/D/F")
        return ""
    return grade


def main() -> int:
    ap = argparse.ArgumentParser(prog="parse_grade_sheet")
    ap.add_argument("sheet")
    ap.add_argument("situations")
    ap.add_argument("--write", action="store_true", help="apply grades back into the JSON")
    ap.add_argument("--force", action="store_true", help="write even if validation issues exist")
    args = ap.parse_args()

    sheet = Path(args.sheet).read_text()
    situations_path = Path(args.situations)
    data = json.loads(situations_path.read_text())
    situations = data["situations"]

    errors: list[str] = []
    parsed: dict[int, str] = {}
    for idx_s, body in _BLOCK.findall(sheet):
        idx = int(idx_s)
        if idx >= len(situations):
            errors.append(f"item {idx}: no matching situation (JSON has {len(situations)})")
            continue
        grade = _extract_grade(idx, body, errors)
        if grade:
            parsed[idx] = grade

    missing = [i for i in range(len(situations)) if i not in parsed]
    print(f"Parsed {len(parsed)}/{len(situations)} grades.")
    if parsed:
        print("  " + " · ".join(f"{i}:{g}" for i, g in sorted(parsed.items())))
    if missing:
        print(f"  still blank: {missing}")
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

    for idx, grade in parsed.items():
        situations[idx]["human_grade"] = grade
    situations_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(parsed)} grades into {situations_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
