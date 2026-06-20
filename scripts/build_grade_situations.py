"""Build REAL analyst-gut-grade situations for Layer-2 grade calibration.

Each situation is one (client, slice) with the two inputs the A-F grade formula
consumes — `raw_visibility` (prominence-weighted client visibility, 0..1) and
`flag_severities` (the slice's distinct client accuracy flags by severity) —
computed from the **verified gold labels** (not the judge), so the grade
calibration isn't polluted by the judge's known over-flagging. `human_grade` is
left blank: Josh + Abhi each gut-grade A-F from the numbers BEFORE running the
fit, then `grade_calibration.fit_grade_policy` fits the penalty weights + bands
to reproduce those human grades.

Slices: pooled per client + per-engine, for a real spread of visibility/flag
profiles. Usage:
    python scripts/build_grade_situations.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.pipeline.calibration import GoldItem, load_gold_set
from src.pipeline.judge_metrics import _PROM_SCORE, _SEVERITY_RANK

_GOLD = {"Oura": "data/oura_gold.json", "Fort": "data/fort_gold.json"}


def _visibility(items: list[GoldItem], client: str) -> float:
    """Mean prominence-weighted visibility of the client across the slice (0..1)."""
    if not items:
        return 0.0
    total = 0.0
    for it in items:
        lab = it.labels.get(client, {})
        prom = str(lab.get("prominence", "absent")) if lab.get("present") else "absent"
        total += _PROM_SCORE.get(prom, 0.0)
    return round(total / len(items), 3)


def _flag_severities(items: list[GoldItem]) -> list[str]:
    """The slice's client accuracy flags by severity, deduped per answer to one
    per type (worst severity wins) — mirrors grade_penalty_flags, so the numbers
    match what the live grade would see."""
    out: list[str] = []
    for it in items:
        best: dict[str, str] = {}
        for f in it.expected_flags or []:
            cur = best.get(f.type)
            if cur is None or _SEVERITY_RANK.get(f.severity, 1) < _SEVERITY_RANK.get(cur, 1):
                best[f.type] = f.severity
        out.extend(best.values())
    # canonical order high->med->low for readability
    return sorted(out, key=lambda s: _SEVERITY_RANK.get(s, 1))


def _situation(label: str, items: list[GoldItem], client: str) -> dict:
    vis = _visibility(items, client)
    sev = _flag_severities(items)
    present = sum(1 for it in items if it.labels.get(client, {}).get("present"))
    sev_summary = dict(Counter(sev)) or "none"
    return {
        "label": label,
        "_context": (
            f"{client}: present in {present}/{len(items)} answers · "
            f"visibility {vis:.2f} · flags {sev_summary}"
        ),
        "raw_visibility": vis,
        "flag_severities": sev,
        "human_grade": "",  # <- Josh + Abhi: gut-grade A/B/C/D/F from the numbers, BEFORE the fit
    }


def main() -> int:
    situations: list[dict] = []
    for client, path in _GOLD.items():
        items = load_gold_set(path)
        situations.append(_situation(f"{client} · all engines (pooled)", items, client))
        for engine in sorted({it.engine for it in items if it.engine}):
            slice_items = [it for it in items if it.engine == engine]
            situations.append(_situation(f"{client} · {engine}", slice_items, client))

    blob = {
        "_comment": (
            "REAL grade-calibration situations from the Oura + Fort gold sets "
            f"({len(situations)} slices). Each carries the two grade-formula inputs "
            "(raw_visibility, flag_severities) computed from verified human labels. "
            "Josh + Abhi: independently gut-grade each 'human_grade' A/B/C/D/F from the "
            "numbers BEFORE looking at the formula's output; reconcile; then run "
            "`python -m src.pipeline.grade_calibration` (point it at this file) to fit "
            "the penalty weights + bands to your grades."
        ),
        "_fields": (
            "label · raw_visibility (0..1) · "
            "flag_severities (worst per type per answer) · human_grade"
        ),
        "situations": situations,
    }
    out = Path("data/grade_situations.json")
    out.write_text(json.dumps(blob, indent=2, ensure_ascii=False))
    print(f"wrote {out}: {len(situations)} situations (human_grade blank, ready to gut-grade)")
    for s in situations:
        flags = s["flag_severities"] or "[]"
        print(f"  {s['label']:<34} vis={s['raw_visibility']:.2f}  flags={flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
