from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from src.engines.local_pack import LocalPackCapture
from src.pipeline import judge_metrics, metrics
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import AccuracyFlag, AnswerJudgment

__all__ = [
    "GradePayload",
    "ScorecardPayload",
    "LeaderRow",
    "BucketRow",
    "StabilityRow",
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
    # How many of this bucket's (query, engine) cells actually returned an answer.
    # When answered_cells == 0 the rates above carry NO information and must render
    # as "—", never "0%": `metrics._rate` returns 0.0 for an empty denominator, so a
    # bucket nothing answered is otherwise indistinguishable from one the client is
    # genuinely absent from.
    answered_cells: int
    total_cells: int


class StabilityRow(TypedDict):
    """How reproducibly one engine returned the same client verdict across repeat runs.

    Per engine, not run-wide, because the engines no longer share a sampling regime:
    `openai` is pinned to a model that rejects `temperature` and samples at its default,
    while every other engine still runs at ENGINE_TEMPERATURE (see openai_engine.MODEL).
    One averaged agreement figure would describe neither.
    """

    engine_name: str
    # False when none of this engine's cells ran twice. The figures below then carry NO
    # information and must render as "—", never as 100% — an unrepeated cell looks
    # unanimous precisely because nothing was ever compared against it.
    is_measured: bool
    repeated_cells: int
    # Cells whose runs disagreed: their verdict could flip on a re-run, so a finding
    # resting on one of them is weaker than the binary hit/miss makes it look.
    split_cells: int
    mean_agreement: float


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
    # Judge prominence of the competitor in this cell ("recommended_first", ...).
    # None on the regex path, which only detects presence. Downstream copy
    # (e.g. the teaser's "it recommends X") must grade its verb off this instead
    # of assuming every losing cell is a first recommendation.
    prominence: str | None


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
    # host -> was the brand found there. Present only on the `reviews` finding, which is
    # the only one with a per-platform breakdown. Flattening this row used to drop it,
    # so the local report's directory checklist could never populate — it reported
    # "not checked" even after the offsite agent had checked. Empty dict, never None,
    # so a consumer can iterate without a guard.
    platforms: dict[str, bool]


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


class LocalPackRow(TypedDict):
    """One business in one query's local pack."""

    query_id: str
    prompt: str
    position: int | None
    name: str
    is_client: bool
    address: str | None
    rating: float | None
    reviews: int | None
    phone: str | None
    website: str | None


class LocalPackPayload(TypedDict):
    """Google's local pack for this run's local-intent queries.

    The surface that actually answers local queries (~93% of local-intent SERPs, vs
    ~15% showing an AI Overview). Deliberately NOT folded into mention_rate /
    share_of_model / the visibility grade: a ranked business list is not an AI answer,
    and averaging the two would produce a number describing neither.

    ``client_positions`` maps query_id → the client's rank in that pack, or None when
    the client is absent from it. That — *does this shop appear in its own city's pack,
    and where* — is the single most actionable local figure the platform produces, and
    it was captured nowhere before this payload existed.
    """

    present: bool
    location: str
    # 'serper_places' | 'searchapi_local_results' — the two return different depths
    # (10 businesses vs 3), so a vendor change between cycles must not read as churn.
    sources: list[str]
    queries_captured: int
    entities: list[LocalPackRow]
    client_positions: dict[str, int | None]


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
    # The denominator behind every rate above: cells that returned an answer, out of
    # cells attempted. A scorecard whose answered_cells is a small fraction of
    # attempted_cells is thin evidence regardless of how confident the rates look.
    answered_cells: int
    attempted_cells: int


class ReportPayload(TypedDict):
    client_name: str
    run_date: str
    query_set_version: str
    runs_per_query: int
    # Engines that returned at least one answer — i.e. that actually measured this
    # client. Built from answer existence, NOT row existence: a 404'd model still
    # writes a row per attempted cell, and listing it here told a client that a
    # surface had been measured when it had produced nothing (run e186c524).
    engines: list[str]
    # Engines that were run and returned nothing at all. Never silently dropped:
    # a surface that failed is a fact about the run's coverage, and the report has
    # to be able to say so.
    dead_engines: list[str]
    competitors: list[str]
    client_domains: list[str]
    detection: str  # "judge" | "regex"
    scorecard: ScorecardPayload
    leaderboard: list[LeaderRow]
    by_bucket: list[BucketRow]
    # Per-engine reproducibility of the client's verdict across repeat runs. Empty on a
    # single-run cycle (nothing to compare), which is itself the honest answer.
    stability: list[StabilityRow]
    accuracy_flags: list[FlagRow]
    sources: list[SourceRow]
    losing_queries: list[LosingRow]
    site_audit: SiteAuditPayload | None  # on-site technique checks (Cat 1–5); None if not run
    # Google local pack for local-intent queries; None on a consumer run (and on any
    # local run with no pinned location, since an unpinned pack is the wrong market).
    local_pack: LocalPackPayload | None


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


def _is_same_business(pack_name: str, client: str) -> bool:
    """Whether a local-pack listing is the client.

    Substring containment either way, case-folded. A shop's Google listing is routinely
    longer than the name on its own website ("Albert Nahman Plumbing, Heating, and
    Cooling" vs "Albert Nahman Plumbing"), so exact equality would report a present
    business as absent — the one error this figure must not make.

    Deliberately NOT fuzzy: `detect_mention`'s job is reading prose, whereas these are
    two business names, and a fuzzy match here would eventually claim a rival is the
    client. When containment fails the answer is "absent", which is the honest,
    checkable outcome.
    """
    a, b = pack_name.strip().casefold(), client.strip().casefold()
    if not a or not b:
        return False
    return a in b or b in a


def build_local_pack_payload(
    captures: list[LocalPackCapture], client: str, location: str
) -> LocalPackPayload | None:
    """Shape captured local packs into the report block. Pure; None when nothing captured."""
    if not captures:
        return None
    rows: list[LocalPackRow] = []
    client_positions: dict[str, int | None] = {}
    for capture in captures:
        client_rank: int | None = None
        for entity in capture["entities"]:
            is_client = _is_same_business(entity["name"], client)
            if is_client and client_rank is None:
                client_rank = entity["position"]
            rows.append(
                LocalPackRow(
                    query_id=capture["query_id"],
                    prompt=capture["prompt"],
                    position=entity["position"],
                    name=entity["name"],
                    is_client=is_client,
                    address=entity["address"] or None,
                    rating=entity["rating"],
                    reviews=entity["reviews"],
                    phone=entity["phone"],
                    website=entity["website"],
                )
            )
        # Recorded for EVERY captured query, including as None — "the client is not in
        # its own city's pack for this query" is the finding, not missing data.
        client_positions[capture["query_id"]] = client_rank
    return LocalPackPayload(
        present=True,
        location=location,
        sources=sorted({c["source"] for c in captures}),
        queries_captured=len(captures),
        entities=rows,
        client_positions=client_positions,
    )


def build_report(
    outcome: AuditOutcome,
    judgments: list[AnswerJudgment] | None = None,
    fact_sheet_present: bool = False,
    run_date: str | None = None,
    site_audit: SiteAuditPayload | None = None,
    local_pack: LocalPackPayload | None = None,
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
    # Split the engines that measured something from the ones that produced nothing.
    # Row existence is not evidence of measurement — see ReportPayload.engines.
    engine_coverage = metrics.coverage_by_engine(results)
    engines = sorted(name for name, c in engine_coverage.items() if c.is_measured)
    dead_engines = sorted(name for name, c in engine_coverage.items() if not c.is_measured)
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
    bucket_coverage = metrics.coverage_by_bucket(results, client)
    _empty = metrics.Coverage(answered_cells=0, total_cells=0)
    by_bucket: list[BucketRow] = [
        BucketRow(
            bucket=bucket,
            mention_rate=rate,
            citation_rate=(citation_buckets.get(bucket) if domains else None),
            answered_cells=bucket_coverage.get(bucket, _empty).answered_cells,
            total_cells=bucket_coverage.get(bucket, _empty).total_cells,
        )
        for bucket, rate in sorted(mention_buckets.items())
    ]

    # --- Stability (repeat-run reproducibility of the client's verdict) ---
    # Read off the same cells the rates above are computed from, so the two can't
    # disagree: the judge's label on the judge path, the regex mention read otherwise.
    stability_by_engine = (
        judge_metrics.stability_by_engine(cells_map[client])
        if has_judge
        else metrics.stability_by_engine(results, client)
    )
    stability: list[StabilityRow] = [
        StabilityRow(
            engine_name=name,
            is_measured=s.is_measured,
            repeated_cells=s.repeated_cells,
            split_cells=s.split_cells,
            mean_agreement=s.mean_agreement,
        )
        for name, s in sorted(stability_by_engine.items())
        # A single-run engine contributes nothing but a row of zeros that reads as a
        # finding; leave it out and let the absent row mean "not repeated".
        if s.is_measured
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
                    prominence=cell.prominence,
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
                    prominence=None,
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
        answered_cells=sum(c.answered_cells for c in engine_coverage.values()),
        attempted_cells=sum(c.total_cells for c in engine_coverage.values()),
    )

    return ReportPayload(
        client_name=client,
        run_date=run_date,
        query_set_version=outcome.query_set_version,
        runs_per_query=outcome.runs_per_query,
        engines=engines,
        dead_engines=dead_engines,
        competitors=competitors,
        client_domains=domains,
        detection="judge" if has_judge else "regex",
        scorecard=scorecard,
        leaderboard=leaderboard,
        by_bucket=by_bucket,
        stability=stability,
        accuracy_flags=accuracy_flags,
        sources=sources,
        losing_queries=losing_queries,
        site_audit=site_audit,
        local_pack=local_pack,
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
