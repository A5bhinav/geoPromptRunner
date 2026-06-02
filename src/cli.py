from __future__ import annotations

import argparse
import logging

from src.audit.query_report import render_audit_report
from src.audit.rubric import load_rubric_scores, render_roadmap
from src.audit.technical_audit import render_technical, run_competitive
from src.engines.anthropic_engine import AnthropicEngine
from src.engines.base import BaseEngine
from src.engines.gemini_engine import GeminiEngine
from src.engines.openai_engine import OpenAIEngine
from src.engines.perplexity_engine import PerplexityEngine
from src.pipeline.orchestrator import AuditOutcome, run_audit, run_teaser
from src.pipeline.trend import compare_runs, render_comparison
from src.prompts.query_set import load_query_set
from src.storage import db

__all__ = ["main"]

logger = logging.getLogger(__name__)

_ENGINE_CLASSES = (OpenAIEngine, AnthropicEngine, GeminiEngine, PerplexityEngine)


def _load_engines() -> list[BaseEngine]:
    """Instantiate every engine whose API key is configured; skip the rest."""
    engines: list[BaseEngine] = []
    for cls in _ENGINE_CLASSES:
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
    engines = _load_engines()
    if not engines:
        print("No engines configured (set API keys in .env).")
        return 1
    outcome = run_audit(
        qs,
        engines,
        client_domains=_split(args.domains),
        runs_per_query=args.runs,
        persist=not args.no_persist,
    )
    print()
    print(render_audit_report(outcome))
    return 0


def _cmd_teaser(args: argparse.Namespace) -> int:
    qs = load_query_set(args.query_set)
    engines = _load_engines()
    if not engines:
        print("No engines configured (set API keys in .env).")
        return 1
    outcome = run_teaser(qs, engines, client_domains=_split(args.domains), max_queries=args.max)
    print()
    print(render_audit_report(outcome))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    outcome = _outcome_from_run(args.run_id)
    if outcome is None:
        print(f"Run {args.run_id} not found.")
        return 1
    print(render_audit_report(outcome))
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
    print(render_comparison(cmp, f"run {args.before[:8]}", f"run {args.after[:8]}"))
    return 0


def _cmd_runs(args: argparse.Namespace) -> int:
    runs = db.list_audit_runs(args.client)
    if not runs:
        print(f"No runs for {args.client!r}.")
        return 0
    print(f"Runs for {args.client!r}:")
    for run in runs:
        print(f"  {run.get('id')}  {run.get('created_at')}  {run.get('query_set_version')}")
    return 0


def _cmd_technical(args: argparse.Namespace) -> int:
    print(render_technical(run_competitive(args.domains)))
    return 0


def _cmd_roadmap(args: argparse.Namespace) -> int:
    scores = load_rubric_scores(args.rubric)
    print(render_roadmap(scores, brand=args.brand or "client"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="geo", description="GEO measurement CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="run a full audit from a query set")
    p_audit.add_argument("query_set")
    p_audit.add_argument("--domains", help="comma-separated client domains")
    p_audit.add_argument("--runs", type=int, default=3)
    p_audit.add_argument("--no-persist", action="store_true")
    p_audit.set_defaults(func=_cmd_audit)

    p_teaser = sub.add_parser("teaser", help="fast demo: a few queries, 1 run, no persist")
    p_teaser.add_argument("query_set")
    p_teaser.add_argument("--domains")
    p_teaser.add_argument("--max", type=int, default=5)
    p_teaser.set_defaults(func=_cmd_teaser)

    p_report = sub.add_parser("report", help="render the report for a stored run")
    p_report.add_argument("run_id")
    p_report.set_defaults(func=_cmd_report)

    p_compare = sub.add_parser("compare", help="diff two runs (cadence/trend)")
    p_compare.add_argument("before")
    p_compare.add_argument("after")
    p_compare.set_defaults(func=_cmd_compare)

    p_runs = sub.add_parser("runs", help="list stored runs for a client")
    p_runs.add_argument("client")
    p_runs.set_defaults(func=_cmd_runs)

    p_tech = sub.add_parser("technical", help="run technical checks across domains")
    p_tech.add_argument("domains", nargs="+")
    p_tech.set_defaults(func=_cmd_technical)

    p_roadmap = sub.add_parser("roadmap", help="render §4/§5 from a rubric JSON")
    p_roadmap.add_argument("rubric")
    p_roadmap.add_argument("--brand")
    p_roadmap.set_defaults(func=_cmd_roadmap)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
