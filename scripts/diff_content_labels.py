"""Diff two sets of content labels and report where they disagree.

Built for the human-vs-model comparison, but it is the same tool the two-human
independent pass needs: `docs/grade-calibration-guide.md` has Josh and Abhi label blind
and then reconcile, and reconciliation needs the disagreement list.

Deliberately NOT a κ calculation. `content_calibration.score_against_gold` is the gate,
and it takes a human gold set — running κ against model labels would produce a number
that looks like calibration and is not. This only tells you *where* two labellers differ, so
the ambiguous check definitions can be found and written down.

Usage:
    python -m scripts.diff_content_labels docs/content-labels-model-comparison.md \\
        docs/content-labeling-sheet.md
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

_LABELS = {"pass", "partial", "fail"}
# Sheet form: "<!-- LABELS url=... -->\n- check: label"
_SHEET_BLOCK = re.compile(
    r"<!--\s*LABELS url=(?P<url>\S+?)\s*-->(?P<body>.*?)<!--\s*/LABELS\s*-->", re.DOTALL
)
_SHEET_LINE = re.compile(r"^\s*-\s*(?P<check>[a-z_]+)\s*:\s*(?P<label>\S*)\s*$", re.MULTILINE)
# Markdown-table form: "## N. <url>" then "| check | label | ... |"
_MD_SECTION = re.compile(r"^##\s+\d+\.\s+(?P<url>\S+)", re.MULTILINE)
_MD_ROW = re.compile(r"^\|\s*(?P<check>[a-z_]+)\s*\|\s*\**(?P<label>[a-z]+)\**\s*\|", re.MULTILINE)


def _parse(text: str) -> dict[tuple[str, str], str]:
    """Read either format into {(url, check): label}. Unfilled slots are skipped."""
    out: dict[tuple[str, str], str] = {}
    for match in _SHEET_BLOCK.finditer(text):
        for line in _SHEET_LINE.finditer(match.group("body")):
            label = line.group("label").strip().lower()
            if label in _LABELS:
                out[(match.group("url"), line.group("check"))] = label
    if out:
        return out
    sections = list(_MD_SECTION.finditer(text))
    for i, section in enumerate(sections):
        end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
        for row in _MD_ROW.finditer(text[section.start() : end]):
            label = row.group("label").strip().lower()
            if label in _LABELS:
                out[(section.group("url"), row.group("check"))] = label
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a", help="first label set (sheet or markdown table)")
    parser.add_argument("b", help="second label set")
    args = parser.parse_args()

    left = _parse(Path(args.a).read_text(encoding="utf-8"))
    right = _parse(Path(args.b).read_text(encoding="utf-8"))
    shared = sorted(set(left) & set(right))
    if not shared:
        print("no overlapping (page, check) pairs — has the second set been filled in?")
        return 1

    agree = [k for k in shared if left[k] == right[k]]
    disagree = [k for k in shared if left[k] != right[k]]
    print(f"compared {len(shared)} pairs: {len(agree)} agree, {len(disagree)} differ "
          f"({len(agree) / len(shared):.0%} raw agreement)\n")

    if disagree:
        by_check = Counter(check for _url, check in disagree)
        print("disagreements by check — the top one is usually an ambiguous definition,")
        print("not a mistake. Write down the ruling; it becomes a judge-prompt rule.\n")
        for check, n in by_check.most_common():
            print(f"  {check:<24} {n}")
        print()
        for url, check in disagree:
            print(f"  {url[-46:]:<48}{check:<24}{args.a[:1]}={left[(url, check)]:<8}"
                  f"{args.b[:1]}={right[(url, check)]}")
    print("\nRaw agreement is not κ. The gate is content_calibration.score_against_gold,")
    print("and it needs a HUMAN gold set — see docs/content-labels-model-comparison.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
