from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from src.pipeline import judge_metrics, metrics
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import AccuracyFlag, AnswerJudgment

__all__ = [
    "GradePayload",
    "ScorecardPayload",
    "LeaderRow",
    "BucketRow",
    "FlagRow",
    "SourceRow",
    "LosingRow",
    "SiteCheckRow",
    "SiteFindingRow",
    "RoadmapRow",
    "SiteAuditPayload",
    "ReportPayload",
    "build_report",
]


class GradePayload(TypedDict):
    letter: str
    score: float
    raw_score: float
    accuracy_penalty: float
    n_flags: int
    rationale: str


class LeaderRow(TypedDict):
    brand: str
    is_client: bool
    visibility: float | None  # None in regex mode (needs the judge)
    mention_rate: float
    share_of_model: float


class BucketRow(TypedDict):
    bucket: str
    mention_rate: float
    citation_rate: float | None


class FlagRow(TypedDict):
    type: str
    severity: str
    claim: str
    reality: str


class SourceRow(TypedDict):
    domain: str
    count: int


class LosingRow(TypedDict):
    query_id: str
    intent: str
    engine_name: str
    competitor: str


class SiteCheckRow(TypedDict):
    check_key: str  # "ssr_rendering" | "schema_valid" | "internal_linking"
    category: int  # the technique-checklist category (1..6)
    page_url: str
    status: str  # pass | partial | fail | ungradeable
    detail: str


class SiteFindingRow(TypedDict):
    finding_type: str  # wikidata | community | reviews | backlinks | listicle | press | ...
    title: str
    url: str | None
    confidence: str  # high | medium | low


class RoadmapRow(TypedDict):
    category: str
    check_name: str
    status: str  # partial | fail (passing checks aren't gaps)
    impact_label: str  # High | Medium | Low
    effort: str  # low | medium | high
    phase: int  # 1 accessibility → 2 content → 3 off-site → 4 measurement


class SiteAuditPayload(TypedDict):
    present: bool  # False when no domain was crawled / the audit didn't run
    domain: str
    pages_crawled: int
    checks: list[SiteCheckRow]
    summary: dict[str, int]  # status counts keyed "<check_key>.<status>"
    errors: int  # per-page crawl failures (best-effort)
    offsite: list[SiteFindingRow]  # Cat 6 offsite findings (empty if not run)
    roadmap: list[RoadmapRow]  # §5 prioritized gaps synthesized from the audit


class ScorecardPayload(TypedDict):
    visibility_grade: GradePayload | None
    share_of_model_client: float
    top_competitor: str | None
    top_competitor_share: float | None
    mention_rate_client: float
    mention_rate_top_competitor: float | None
    citation_rate_client: float | None
    accuracy_assessed: bool
    accuracy_flag_count: int | None


class ReportPayload(TypedDict):
    client_name: str
    run_date: str
    query_set_version: str
    runs_per_query: int
    engines: list[str]
    competitors: list[str]
    client_domains: list[str]
    detection: str  # "judge" | "regex"
    scorecard: ScorecardPayload
    leaderboard: list[LeaderRow]
    by_bucket: list[BucketRow]
    accuracy_flags: list[FlagRow]
    sources: list[SourceRow]
    losing_queries: list[LosingRow]
    site_audit: SiteAuditPayload | None  # on-site technique checks (Cat 1–5); None if not run


def _grade_payload(grade: judge_metrics.VisibilityGrade) -> GradePayload:
    return GradePayload(
        letter=grade.letter,
        score=grade.score,
        raw_score=grade.raw_score,
        accuracy_penalty=grade.accuracy_penalty,
        n_flags=grade.n_flags,
        rationale=grade.rationale,
    )


def _shares(mention_by_brand: dict[str, float]) -> dict[str, float]:
    """Normalize per-brand mention rates into share-of-model.

    Every brand is measured over the same (query, engine) cells, so the
    answered-cell denominator is identical across brands — share-of-voice is
    therefore proportional to mention rate.
    """
    total = sum(mention_by_brand.values())
    if total == 0:
        return {b: 0.0 for b in mention_by_brand}
    return {b: r / total for b, r in mention_by_brand.items()}


def build_report(
    outcome: AuditOutcome,
    judgments: list[AnswerJudgment] | None = None,
    fact_sheet_present: bool = False,
    run_date: str | None = None,
    site_audit: SiteAuditPayload | None = None,
) -> ReportPayload:
    """Assemble the structured report the UI renders.

    Judge-aware: when judgments are present (and any were assessed) the grade,
    visibility, framing and accuracy come from the LLM judge; otherwise it falls
    back to regex mention detection (no grade, no accuracy). Bucket rates,
    citations and sources are results-based and render in either mode. The
    ``site_audit`` block (on-site technique checks) is additive and best-effort —
    the report renders with it absent (``None``) so a late/failed crawl never
    blocks the answer report. Pure.
    """
    client = outcome.client_name
    competitors = outcome.competitors
    brands = [client, *competitors]
    results = outcome.results
    domains = outcome.client_domains
    engines = sorted({r["engine_name"] for r in results})
    run_date = run_date or datetime.now(UTC).date().isoformat()
    has_judge = bool(judgments) and any(j.assessed for j in (judgments or []))

    # Compute every brand's cells and the accuracy flags ONCE on the judge path,
    # then reuse them across mention/visibility/grade/losing — instead of each
    # metric re-walking the judgments (and re-aggregating) per brand.
    cells_map: dict[str, list[judge_metrics.BrandCell]] = {}
    judge_flags: list[AccuracyFlag] = []
    if has_judge:
        assert judgments is not None
        cells_map = judge_metrics.brand_cells_map(judgments, brands)
        judge_flags = judge_metrics.collect_accuracy_flags(judgments)

    # --- Per-brand mention rate + leaderboard ---
    if has_judge:
        assert judgments is not None
        mention_by_brand = {
            b: judge_metrics.mention_rate(judgments, b, cells=cells_map[b]) for b in brands
        }
        visibility_by_brand: dict[str, float | None] = {
            b: judge_metrics.visibility_score(judgments, b, cells=cells_map[b]) for b in brands
        }
    else:
        mention_by_brand = {b: metrics.mention_rate(results, b) for b in brands}
        visibility_by_brand = {b: None for b in brands}

    share_by_brand = _shares(mention_by_brand)

    # Rank competitors by the active detection's mention rate.
    ranked_competitors = sorted(
        competitors, key=lambda c: mention_by_brand.get(c, 0.0), reverse=True
    )
    top_competitor = ranked_competitors[0] if ranked_competitors else None

    leaderboard: list[LeaderRow] = []
    for brand in sorted(brands, key=lambda b: mention_by_brand.get(b, 0.0), reverse=True):
        leaderboard.append(
            LeaderRow(
                brand=brand,
                is_client=brand == client,
                visibility=visibility_by_brand[brand],
                mention_rate=mention_by_brand[brand],
                share_of_model=share_by_brand[brand],
            )
        )

    # --- By-bucket (results-based; valid in either mode) ---
    mention_buckets = metrics.mention_rate_by_bucket(results, client)
    citation_buckets = metrics.citation_rate_by_bucket(results, domains) if domains else {}
    by_bucket: list[BucketRow] = [
        BucketRow(
            bucket=bucket,
            mention_rate=rate,
            citation_rate=(citation_buckets.get(bucket) if domains else None),
        )
        for bucket, rate in sorted(mention_buckets.items())
    ]

    # --- Accuracy flags (judge only) ---
    accuracy_flags: list[FlagRow] = []
    if has_judge:
        for f in judge_flags:
            accuracy_flags.append(
                FlagRow(type=f.type, severity=f.severity, claim=f.claim, reality=f.reality)
            )

    # --- Sources ---
    sources: list[SourceRow] = [
        SourceRow(domain=domain, count=count)
        for domain, count in metrics.top_cited_domains(results)
    ]

    # --- Losing queries ---
    losing_queries: list[LosingRow] = []
    if has_judge:
        assert judgments is not None
        for cell in judge_metrics.losing_cells(judgments, client, competitors, cells_map=cells_map):
            losing_queries.append(
                LosingRow(
                    query_id=cell.query_id,
                    intent=cell.intent,
                    engine_name=cell.engine_name,
                    competitor=cell.brand,
                )
            )
    else:
        for loss in metrics.losing_queries(results, client, competitors):
            losing_queries.append(
                LosingRow(
                    query_id=loss.query_id,
                    intent=loss.intent,
                    engine_name=loss.engine_name,
                    competitor=", ".join(loss.competitors_present),
                )
            )

    # --- Scorecard ---
    grade_payload: GradePayload | None = None
    if has_judge:
        assert judgments is not None
        grade_payload = _grade_payload(
            judge_metrics.visibility_grade(judgments, client, cells=cells_map.get(client))
        )

    citation_rate_client = metrics.citation_rate(results, domains) if domains else None

    # Accuracy was assessed iff the judge ran against a fact sheet. The run row's
    # fact_sheet_present is the intended signal, but it's only set on UI-created
    # runs — a CLI `judge --fact-sheet` leaves it False. The judge only emits
    # flags when given a fact sheet, so any flag is itself proof a sheet was used.
    # Keying off both keeps the scorecard from contradicting the flags table /
    # grade it's shown beside (e.g. grade F with a full flag list but a blank
    # count). Residual: a fact-sheet run that found zero errors with the row flag
    # unset reads as "not assessed" — conservative, and gone once the row is set.
    accuracy_assessed = has_judge and (fact_sheet_present or bool(accuracy_flags))

    scorecard = ScorecardPayload(
        visibility_grade=grade_payload,
        share_of_model_client=share_by_brand.get(client, 0.0),
        top_competitor=top_competitor,
        top_competitor_share=(share_by_brand.get(top_competitor) if top_competitor else None),
        mention_rate_client=mention_by_brand.get(client, 0.0),
        mention_rate_top_competitor=(
            mention_by_brand.get(top_competitor) if top_competitor else None
        ),
        citation_rate_client=citation_rate_client,
        accuracy_assessed=accuracy_assessed,
        accuracy_flag_count=(len(accuracy_flags) if accuracy_assessed else None),
    )

    return ReportPayload(
        client_name=client,
        run_date=run_date,
        query_set_version=outcome.query_set_version,
        runs_per_query=outcome.runs_per_query,
        engines=engines,
        competitors=competitors,
        client_domains=domains,
        detection="judge" if has_judge else "regex",
        scorecard=scorecard,
        leaderboard=leaderboard,
        by_bucket=by_bucket,
        accuracy_flags=accuracy_flags,
        sources=sources,
        losing_queries=losing_queries,
        site_audit=site_audit,
    )


if __name__ == "__main__":
    from src.storage.models import QueryResult

    def _qr(qid: str, intent: str, engine: str, run: int, resp: str | None) -> QueryResult:
        return QueryResult(
            query_id=qid,
            intent=intent,
            prompt="(mock)",
            engine_name=engine,
            run_index=run,
            response=resp,
            citations=["https://www.reddit.com/r/x"] if run == 0 else [],
            timestamp="t",
        )

    outcome = AuditOutcome(
        run_id=None,
        client_name="Oura",
        client_domains=["ouraring.com"],
        competitors=["Whoop", "Ultrahuman"],
        query_set_version="csv-2026-06-03",
        runs_per_query=1,
        results=[
            _qr("q1", "category", "mock", 0, "The best option is Whoop. Oura also exists."),
            _qr("q2", "comparison", "mock", 0, "Oura is the top pick for sleep."),
        ],
    )
    payload = build_report(outcome)
    print(f"detection={payload['detection']}")
    print(f"grade={payload['scorecard']['visibility_grade']}")
    for row in payload["leaderboard"]:
        print(f"  {row['brand']:12s} mention={row['mention_rate']:.0%}")
    print(f"sources={payload['sources']}")
