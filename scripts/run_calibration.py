"""Run judge calibration over one or more gold sets (pooled + per-slice).

Cheap by design: the judge defaults to claude-haiku-4-5 and every verdict is
content-addressed and cached (data/judge_cache.sqlite), so a re-run is free and
only new/edited answers cost an API call.

Combining gold sets gives a pooled report plus automatic per-engine and
per-category breakdowns (the property the calibration plan wants: agreement
pooled across >=2 categories, with no slice far below the pool).

Usage:
    python scripts/run_calibration.py data/oura_gold.json data/fort_gold.json
"""

from __future__ import annotations

import sys

from src.config import settings
from src.pipeline.calibration import calibrate, load_gold_set, render_calibration
from src.pipeline.judge import Judge
from src.pipeline.judge_cache import JudgeCache


def main(argv: list[str]) -> int:
    paths = argv or ["data/oura_gold.json", "data/fort_gold.json"]
    gold = []
    for p in paths:
        items = load_gold_set(p)
        print(f"loaded {len(items)} items from {p}")
        gold += items
    cache_path = settings.JUDGE_CACHE_PATH or "(disabled)"
    print(f"judge model: {settings.JUDGE_MODEL} · cache: {cache_path}")
    print(f"total items to judge: {len(gold)}\n")

    try:
        judge = Judge()
    except ValueError as exc:
        print(f"cannot calibrate: {exc}")
        return 1

    cache = JudgeCache(settings.JUDGE_CACHE_PATH)
    report = calibrate(judge, gold, progress=True, cache=cache)
    print()
    print(render_calibration(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
