"""Measure the determinism baseline and recommend K (runs_per_query).

Runs one probe query K times per engine and reports BOTH:
  - text-level agreement (the old metric — understates stability, since temp-0
    engines rarely repeat a long answer verbatim), and
  - label-level agreement (the audit-relevant one — does the judge's brand READ
    stay stable across the K fresh answers), with the suggested K and the trend
    real-move noise floor.

Live calls: K per engine (+ one judge call per answer; the judge is cached and
runs at temperature 0). Skip an engine with --engines to dodge quota limits
(e.g. Gemini) or retrieval cost (Perplexity).

Usage:
    python scripts/run_determinism.py --k 5 --engines openai,anthropic
"""

from __future__ import annotations

import argparse

from src.cli import _load_engines
from src.pipeline.judge import Judge
from src.verification.determinism import (
    measure_determinism,
    measure_label_determinism,
    render_baseline,
    render_label_baseline,
)

# An Oura-style commercial probe with a known brand set (matches the gold data).
PROBE_QUERY = "best smart ring for sleep tracking"
PROBE_CLIENT = "Oura"
PROBE_COMPETITORS = ["Whoop", "Ultrahuman", "Samsung Galaxy Ring", "RingConn"]


def main() -> int:
    ap = argparse.ArgumentParser(prog="run_determinism")
    ap.add_argument("--k", type=int, default=5, help="repeats per engine (>=2)")
    ap.add_argument("--query", default=PROBE_QUERY)
    ap.add_argument("--client", default=PROBE_CLIENT)
    ap.add_argument(
        "--engines", default=None, help="comma-separated engine names to include (default: all)"
    )
    ap.add_argument("--surface", default="memory", choices=["memory", "search", "both"])
    args = ap.parse_args()

    if args.surface == "both":
        by_name = {e.ENGINE_NAME: e for e in [*_load_engines("memory"), *_load_engines("search")]}
        engines = list(by_name.values())
    else:
        engines = _load_engines(args.surface)
    if args.engines:
        wanted = {e.strip() for e in args.engines.split(",")}
        engines = [e for e in engines if e.ENGINE_NAME in wanted]
    if not engines:
        print("No engines configured/selected (set API keys in .env).")
        return 1

    try:
        judge = Judge()
    except ValueError as exc:
        print(f"cannot judge: {exc}")
        return 1

    print(f"Probe: {args.query!r} · client={args.client} · k={args.k}")
    print(f"Engines: {', '.join(e.ENGINE_NAME for e in engines)}\n")

    text = [measure_determinism(e, args.query, args.k) for e in engines]
    labels = [
        measure_label_determinism(e, judge, args.query, args.client, PROBE_COMPETITORS, args.k)
        for e in engines
    ]
    print(render_baseline(text))
    print()
    print(render_label_baseline(labels))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
