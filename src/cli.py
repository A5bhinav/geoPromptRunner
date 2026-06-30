from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.audit.query_report import render_audit_report
from src.audit.rubric import load_rubric_scores, render_roadmap
from src.audit.technical_audit import render_technical, run_competitive
from src.config import settings
from src.engines.ai_overviews_engine import AIOverviewsEngine
from src.engines.anthropic_engine import AnthropicEngine
from src.engines.anthropic_search_engine import AnthropicSearchEngine
from src.engines.base import BaseEngine
from src.engines.gemini_engine import GeminiEngine
from src.engines.gemini_grounded_engine import GeminiGroundedEngine
from src.engines.openai_engine import OpenAIEngine
from src.engines.openai_search_engine import OpenAISearchEngine
from src.engines.perplexity_engine import PerplexityEngine
from src.pipeline.calibration import calibrate, load_gold_set, render_calibration
from src.pipeline.cost import CostBudgetExceeded
from src.pipeline.discovery import discover_competitors
from src.pipeline.judge import Judge
from src.pipeline.judge_cache import JudgeCache
from src.pipeline.orchestrator import AuditOutcome, run_audit, run_teaser
from src.pipeline.trend import compare_runs, due_for_rerun, render_comparison
from src.prompts.query_set import load_query_set
from src.storage import db
from src.verification.canary import render_canary_results, run_canaries
from src.verification.determinism import (
    DEFAULT_QUERY,
    measure_determinism,
    render_baseline,
)
from src.verification.shuffle import render_shuffle_results, run_order_shuffle

__all__ = ["main"]

logger = logging.getLogger(__name__)

# "memory" = parametric (training-data) surfaces; "search" = live-retrieval
# surfaces (ChatGPT-with-search, Claude-with-search, Gemini grounding, Perplexity,
# Google AI Overviews). They measure different channels — keep them distinct.
_MEMORY_CLASSES = (OpenAIEngine, AnthropicEngine, GeminiEngine, PerplexityEngine)
_SEARCH_CLASSES = (
    OpenAISearchEngine,
    AnthropicSearchEngine,
    GeminiGroundedEngine,
    PerplexityEngine,
    AIOverviewsEngine,
)


def _load_engines(surface: str = "memory") -> list[BaseEngine]:
    """Instantiate every engine whose API key is configured; skip the rest."""
    classes = _SEARCH_CLASSES if surface == "search" else _MEMORY_CLASSES
    engines: list[BaseEngine] = []
    for cls in classes:
        try:
            engines.append(cls())
        except ValueError as exc:
            print(f"  (skipping {cls.__name__}: {exc})")
    return engines


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def _outcome_from_run(run_id: str) -> AuditOutcome | None:
    run = db.get_audit_run(run_id)
    if run is None:
        return None
    results = db.get_query_results(run_id)
    domains = run.get("client_domains") or []
    competitors = run.get("competitors") or []
    return AuditOutcome(
        run_id=run_id,
        client_name=str(run.get("client_name", "")),
        client_domains=[str(d) for d in domains] if isinstance(domains, list) else [],
        competitors=[str(c) for c in competitors] if isinstance(competitors, list) else [],
        query_set_version=str(run.get("query_set_version", "")),
        runs_per_query=int(str(run.get("runs_per_query") or 1)),
        results=results,
    )


def _cmd_audit(args: argparse.Namespace) -> int:
    qs = load_query_set(args.query_set)
    engines = _load_engines(args.surface)
    if not engines:
        print("No engines configured (set API keys in .env).")
        return 1
    # Resume must keep the original instrument: unless --runs is given
    # explicitly, inherit runs_per_query from the stored run rather than the
    # CLI default — mixed run counts within one run skew aggregation.
    runs = args.runs
    if runs is None:
        runs = settings.DEFAULT_RUNS_PER_QUERY
        if args.resume:
            stored = db.get_audit_run(args.resume)
            if stored is not None:
                runs = int(str(stored.get("runs_per_query") or settings.DEFAULT_RUNS_PER_QUERY))
    try:
        outcome = run_audit(
            qs,
            engines,
            client_domains=_split(args.domains),
            runs_per_query=runs,
            persist=not args.no_persist,
            max_cost=args.max_cost,
            resume_run_id=args.resume,
        )
    except CostBudgetExceeded as exc:
        print(f"Aborted: {exc}")
        return 1

    judgments = None
    if args.judge:
        fact_sheet = Path(args.fact_sheet).read_text() if args.fact_sheet else None
        try:
            judge = Judge(
                cascade=args.cascade or settings.JUDGE_CASCADE,
                verify=args.verify or settings.JUDGE_VERIFY,
            )
            judgments = judge.judge_results(
                outcome.results,
                outcome.client_name,
                outcome.competitors,
                fact_sheet,
                progress=True,
                cache=JudgeCache(settings.JUDGE_CACHE_PATH),
            )
            if outcome.run_id and not args.no_persist:
                try:
                    db.save_judgments(outcome.run_id, judgments)
                except db.StorageError as exc:
                    print(f"(warning: could not persist judgments: {exc})")
        except ValueError as exc:
            print(f"(judge skipped: {exc})")

    previous = None
    if args.compare:
        prior = _outcome_from_run(args.compare)
        if prior is None:
            print(f"(trend skipped: run {args.compare} not found)")
        else:
            previous = prior.results
    print()
    print(
        render_audit_report(
            outcome,
            judgments=judgments,
            previous=previous,
            previous_label=f"run {args.compare[:8]}" if args.compare else "previous run",
            query_set=qs,
        )
    )
    return 0


def _cmd_teaser(args: argparse.Namespace) -> int:
    qs = load_query_set(args.query_set)
    engines = _load_engines(args.surface)
    if not engines:
        print("No engines configured (set API keys in .env).")
        return 1
    outcome = run_teaser(qs, engines, client_domains=_split(args.domains), max_queries=args.max)
    print()
    print(render_audit_report(outcome))
    return 0


def _cmd_discover(args: argparse.Namespace) -> int:
    outcome = _outcome_from_run(args.run_id)
    if outcome is None:
        print(f"Run {args.run_id} not found.")
        return 1
    engines = _load_engines("memory")
    if not engines:
        print("No engines configured for extraction (set API keys in .env).")
        return 1
    known = [outcome.client_name, *outcome.competitors]
    discovered = discover_competitors(outcome.results, known, extractor=engines[0])
    print(f"Competitors discovered in answers (excluding {known}):")
    if not discovered:
        print("  none")
    for name, count in discovered:
        print(f"  {count:3d}  {name}")
    return 0


def _cmd_judge(args: argparse.Namespace) -> int:
    outcome = _outcome_from_run(args.run_id)
    if outcome is None:
        print(f"Run {args.run_id} not found.")
        return 1

    if args.stored:
        stored = db.get_judgments(args.run_id)
        if not stored:
            print("No stored judgments for this run; run `judge` without --stored first.")
            return 1
        print(render_audit_report(outcome, judgments=stored))
        return 0

    fact_sheet = Path(args.fact_sheet).read_text() if args.fact_sheet else None
    try:
        judge = Judge(
            cascade=args.cascade or settings.JUDGE_CASCADE,
            verify=args.verify or settings.JUDGE_VERIFY,
        )
    except ValueError as exc:
        print(exc)
        return 1
    judgments = judge.judge_results(
        outcome.results,
        outcome.client_name,
        outcome.competitors,
        fact_sheet,
        progress=True,
        cache=JudgeCache(settings.JUDGE_CACHE_PATH),
    )
    if not args.no_persist:
        try:
            db.save_judgments(args.run_id, judgments)
        except db.StorageError as exc:
            print(f"(warning: could not persist judgments: {exc})")
    print(render_audit_report(outcome, judgments=judgments))
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    gold = load_gold_set(args.gold)
    try:
        judge = Judge(cascade=settings.JUDGE_CASCADE, verify=settings.JUDGE_VERIFY)
    except ValueError as exc:
        print(exc)
        return 1
    print(render_calibration(calibrate(judge, gold)))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    outcome = _outcome_from_run(args.run_id)
    if outcome is None:
        print(f"Run {args.run_id} not found.")
        return 1
    # Use stored judge output if this run was judged; else the regex fallback.
    try:
        judgments = db.get_judgments(args.run_id)
    except db.StorageError:
        judgments = []

    previous = None
    if args.previous:
        prior = _outcome_from_run(args.previous)
        if prior is None:
            print(f"(trend skipped: run {args.previous} not found)")
        else:
            previous = prior.results
    print(
        render_audit_report(
            outcome,
            judgments=judgments or None,
            previous=previous,
            previous_label=f"run {args.previous[:8]}" if args.previous else "previous run",
        )
    )
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    before = _outcome_from_run(args.before)
    after = _outcome_from_run(args.after)
    if before is None or after is None:
        print("One or both runs not found.")
        return 1
    if before.query_set_version != after.query_set_version:
        print(
            f"Warning: query-set versions differ ({before.query_set_version} vs "
            f"{after.query_set_version}); the comparison may not be valid."
        )
    cmp = compare_runs(before.results, after.results, after.client_name, after.competitors)
    print(
        render_comparison(
            cmp, f"run {args.before[:8]}", f"run {args.after[:8]}", noise_floor=args.noise_floor
        )
    )
    return 0


def _cmd_runs(args: argparse.Namespace) -> int:
    # No client → the recent runs across all clients (newest first), so you can
    # find a run_id when you don't already know which client it belongs to.
    if args.client:
        runs = db.list_audit_runs(args.client)  # oldest first (trend/cadence order)
        if not runs:
            print(f"No runs for {args.client!r}.")
            return 0
        print(f"Runs for {args.client!r}:")
        rows = runs
    else:
        rows = db.list_all_audit_runs(limit=args.limit)
        if not rows:
            print("No runs found.")
            return 0
        print(f"Recent runs (newest first, up to {args.limit}):")
    for run in rows:
        created = str(run.get("created_at", ""))[:10]
        fact = "fact-sheet" if run.get("fact_sheet_present") else "no-sheet"
        print(
            f"  {run.get('id')}  {created}  {str(run.get('client_name', '')):<14}  "
            f"{run.get('query_set_version')}  [{fact}]"
        )
    return 0


def _cmd_technical(args: argparse.Namespace) -> int:
    print(render_technical(run_competitive(args.domains)))
    return 0


def _cmd_roadmap(args: argparse.Namespace) -> int:
    scores = load_rubric_scores(args.rubric)
    query_weights: dict[str, float] | None = None
    if args.query_set:
        qs = load_query_set(args.query_set)
        query_weights = {q.query_id: q.weight for q in qs.queries}
    print(render_roadmap(scores, brand=args.brand or "client", query_weights=query_weights))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    """Run an isolation/determinism probe (docs/isolation-determinism-plan.md)."""
    if args.probe == "canary":
        # Both surfaces, deduped (Perplexity appears in each list) — the canary
        # is cheap (2 calls/engine) and the guarantee should hold everywhere.
        by_name = {e.ENGINE_NAME: e for e in [*_load_engines("memory"), *_load_engines("search")]}
        engines = list(by_name.values())
    else:
        engines = _load_engines(args.surface)
    if not engines:
        print("No engines configured (set API keys in .env).")
        return 1

    if args.probe == "canary":
        print(render_canary_results(run_canaries(engines)))
        return 0
    if args.probe == "determinism":
        print(f"Measuring {args.k} repeats of: {args.query!r}\n")
        print(render_baseline([measure_determinism(e, args.query, args.k) for e in engines]))
        return 0
    # shuffle
    if not args.query_set:
        print("shuffle needs --query-set (the prompt list to run in both orders).")
        return 1
    prompts = [q.text for q in load_query_set(args.query_set).queries]
    print(f"Shuffling {len(prompts)} queries (2 passes per engine)\n")
    print(render_shuffle_results([run_order_shuffle(e, prompts) for e in engines]))
    return 0


def _cmd_due(args: argparse.Namespace) -> int:
    runs = db.list_audit_runs(args.client)
    if not runs:
        print(f"{args.client}: no prior runs — due for a baseline.")
        return 0
    last = str(runs[-1].get("created_at", ""))
    due = due_for_rerun(last, cadence_days=args.cadence)
    print(
        f"{args.client}: last run {last} — {'DUE for re-run' if due else 'not yet due'} "
        f"(cadence {args.cadence}d)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="geo", description="GEO measurement CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="run a full audit from a query set")
    p_audit.add_argument("query_set")
    p_audit.add_argument("--domains", help="comma-separated client domains")
    p_audit.add_argument(
        "--runs",
        type=int,
        default=None,
        help="runs per query (default 3; a resumed run inherits its stored value)",
    )
    p_audit.add_argument("--surface", choices=("memory", "search"), default="memory")
    p_audit.add_argument(
        "--max-cost", type=float, default=None, help="abort if est. $ exceeds this"
    )
    p_audit.add_argument("--resume", default=None, help="resume an interrupted run by id")
    p_audit.add_argument("--judge", action="store_true", help="LLM-judge the answers inline")
    p_audit.add_argument("--fact-sheet", help="client fact sheet for --judge accuracy")
    p_audit.add_argument(
        "--cascade",
        action="store_true",
        help="two-tier judge: cheap model reads brands, accurate model checks accuracy flags",
    )
    p_audit.add_argument(
        "--verify",
        action="store_true",
        help="adversarially verify each accuracy flag (drops over-flagged false positives)",
    )
    p_audit.add_argument(
        "--compare", default=None, help="prior run id to show the §3 trend column against"
    )
    p_audit.add_argument("--no-persist", action="store_true")
    p_audit.set_defaults(func=_cmd_audit)

    p_teaser = sub.add_parser("teaser", help="fast demo: a few queries, 1 run, no persist")
    p_teaser.add_argument("query_set")
    p_teaser.add_argument("--domains")
    p_teaser.add_argument("--max", type=int, default=5)
    p_teaser.add_argument("--surface", choices=("memory", "search"), default="memory")
    p_teaser.set_defaults(func=_cmd_teaser)

    p_discover = sub.add_parser("discover", help="find competitors mentioned in a stored run")
    p_discover.add_argument("run_id")
    p_discover.set_defaults(func=_cmd_discover)

    p_report = sub.add_parser("report", help="render the report for a stored run")
    p_report.add_argument("run_id")
    p_report.add_argument(
        "--previous", default=None, help="prior run id to show the §3 trend column against"
    )
    p_report.set_defaults(func=_cmd_report)

    p_judge = sub.add_parser("judge", help="LLM-judge a stored run (prominence/framing/accuracy)")
    p_judge.add_argument("run_id")
    p_judge.add_argument("--fact-sheet", help="path to the client fact sheet (enables accuracy)")
    p_judge.add_argument(
        "--cascade",
        action="store_true",
        help="two-tier judge: cheap model reads brands, accurate model checks accuracy flags",
    )
    p_judge.add_argument(
        "--verify",
        action="store_true",
        help="adversarially verify each accuracy flag (drops over-flagged false positives)",
    )
    p_judge.add_argument("--no-persist", action="store_true", help="don't save judgments")
    p_judge.add_argument(
        "--stored", action="store_true", help="render saved judgments (no re-judging)"
    )
    p_judge.set_defaults(func=_cmd_judge)

    p_cal = sub.add_parser("calibrate", help="check the judge against a hand-labeled gold set")
    p_cal.add_argument("gold")
    p_cal.set_defaults(func=_cmd_calibrate)

    p_compare = sub.add_parser("compare", help="diff two runs (cadence/trend)")
    p_compare.add_argument("before")
    p_compare.add_argument("after")
    p_compare.add_argument(
        "--noise-floor",
        type=float,
        default=None,
        help="real-move threshold as a fraction (e.g. 0.05 = 5 pts) from the determinism "
        "baseline; deltas below it are tagged 'within noise'",
    )
    p_compare.set_defaults(func=_cmd_compare)

    p_runs = sub.add_parser("runs", help="list stored runs (all clients, or one client)")
    p_runs.add_argument("client", nargs="?", help="filter to one client; omit for all recent runs")
    p_runs.add_argument(
        "--limit", type=int, default=20, help="max runs to show when listing all (default 20)"
    )
    p_runs.set_defaults(func=_cmd_runs)

    p_tech = sub.add_parser("technical", help="run technical checks across domains")
    p_tech.add_argument("domains", nargs="+")
    p_tech.set_defaults(func=_cmd_technical)

    p_roadmap = sub.add_parser("roadmap", help="render §4/§5 from a rubric JSON")
    p_roadmap.add_argument("rubric")
    p_roadmap.add_argument("--brand")
    p_roadmap.add_argument("--query-set", help="query set JSON for commercial-value weights")
    p_roadmap.set_defaults(func=_cmd_roadmap)

    p_verify = sub.add_parser(
        "verify", help="prove isolation/determinism (canary, determinism, shuffle probes)"
    )
    p_verify.add_argument("probe", choices=("canary", "determinism", "shuffle"))
    p_verify.add_argument("--surface", choices=("memory", "search"), default="memory")
    p_verify.add_argument("--query", default=DEFAULT_QUERY, help="query for the determinism probe")
    p_verify.add_argument("--k", type=int, default=10, help="repeats for the determinism probe")
    p_verify.add_argument("--query-set", help="query set JSON for the shuffle probe")
    p_verify.set_defaults(func=_cmd_verify)

    p_due = sub.add_parser("due", help="check if a client is due for a cadence re-run")
    p_due.add_argument("client")
    p_due.add_argument("--cadence", type=int, default=42)
    p_due.set_defaults(func=_cmd_due)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
