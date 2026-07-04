"""Run judge calibration over one or more gold sets (pooled + per-slice).

Calibration measures the HELD-CONSTANT production judge (the model in
``JUDGE_MODEL``), so it uses an ISOLATED in-memory judge cache — never the shared
Supabase notebook. That notebook is also filled by the subscription pre-judge with
a different model's verdicts (Opus) under identical keys, and reading them would
silently calibrate the wrong model. Verdicts are re-judged fresh each run
(deduped within a run), so the reported agreement always reflects the real judge.

Combining gold sets gives a pooled report plus automatic per-engine and
per-category breakdowns (the property the calibration plan wants: agreement
pooled across >=2 categories, with no slice far below the pool).

Usage:
    python scripts/run_calibration.py data/oura_gold.json data/fort_gold.json
"""

from __future__ import annotations

import sys

from src.config import settings
from src.pipeline.calibration import (
    calibrate,
    isolated_cache,
    load_gold_set,
    render_calibration,
)
from src.pipeline.judge import Judge


def main(argv: list[str]) -> int:
    paths = argv or ["data/oura_gold.json", "data/fort_gold.json"]
    gold = []
    for p in paths:
        items = load_gold_set(p)
        print(f"loaded {len(items)} items from {p}")
        gold += items
    print(
        f"judge model: {settings.JUDGE_MODEL} · cache: isolated in-memory "
        "(never the shared pre-judge notebook)"
    )
    print(f"total items to judge: {len(gold)}\n")

    try:
        judge = Judge(cascade=settings.JUDGE_CASCADE, verify=settings.JUDGE_VERIFY)
    except ValueError as exc:
        print(f"cannot calibrate: {exc}")
        return 1
    if settings.JUDGE_CASCADE:
        print(
            f"cascade: structural={settings.JUDGE_STRUCTURAL_MODEL} · "
            f"accuracy={settings.JUDGE_ACCURACY_MODEL}"
        )
    if settings.JUDGE_VERIFY:
        print(f"verify: per-flag verifier={settings.JUDGE_VERIFIER_MODEL}")

    report = calibrate(judge, gold, progress=True, cache=isolated_cache())
    print()
    print(render_calibration(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
