"""The report contract's sections, as data (spec Phase T).

`reports.py` builds the measurement; this module shapes it into the eleven
front-matter sections and the six back-matter appendices the contract names, in
delivery order. Everything here is **presentation of numbers that already
exist** — `metrics.py`, `judge_metrics.py`, `stats.py`, `movement.py` and
`lifecycle.py` do the measuring, and no new engine call or judge pass happens on
this path.

Three rules bind every builder below, and they are why the shapes look the way
they do:

**No rate without its denominator.** Every rate ships as a ``RatePayload`` —
successes, n, and a Wilson interval on the design-corrected sample. A section
that wants a bare percentage has to go around the type to get one.

**Descriptive voice.** Sections 1–7, 10 and 11 state what was measured and stop.
"youtube.com was cited 31 times, up from 12 last cycle" — never "you need a
YouTube strategy". Interpretation lives in sections 8 and 9, which `reports.py`
builds from the findings pipeline. The separation is the product: a client who
distrusts the advice can still trust the measurement.

**Thin data is stated, not hidden.** Every section has a defined behaviour when
there is not enough data to say anything: a single-point baseline instead of a
trend line, a count and an interval instead of a point estimate, "no qualifying
example this cycle" instead of a substitute. None of them is an empty box.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

from src.pipeline import judge_metrics, metrics, movement, stats
from src.pipeline.fmt import NO_PRIOR, fmt_count_delta, fmt_pp, fmt_rate_delta
from src.prompts.intent import CONSUMER_BUCKETS, LOCAL_BUCKETS, IntentBucket
from src.storage.models import AnswerJudgment, QueryResult

__all__ = [
    "CycleMetrics",
    "TilePayload",
    "ExecSnapshotPayload",
    "TrendPoint",
    "TrendPayload",
    "QuestionTypeRow",
    "QuestionTypePayload",
    "SurfaceRow",
    "SurfacePayload",
    "CompetitiveRow",
    "CompetitivePayload",
    "CitationDomainRow",
    "CitationsPayload",
    "RepresentativeAnswer",
    "RepresentativePayload",
    "MethodologyPayload",
    "AppendixTable",
    "BackMatterPayload",
    "SOURCE_TYPES",
    "classify_source",
    "build_exec_snapshot",
    "build_trend",
    "build_question_types",
    "build_surfaces",
    "build_competitive",
    "build_citations",
    "build_representative_answers",
    "build_methodology",
    "build_back_matter",
    "engine_label",
    "bucket_label",
]


# --- shared vocabulary --------------------------------------------------------

#: Client-facing surface names. Internal engine keys are join keys, not content —
#: a client reads "ChatGPT", never `openai`. Mirrored in
#: `web/components/report-panels.tsx`; the two must agree, because a surface
#: named one way in a chart and another in a table reads as two surfaces.
_ENGINE_LABELS: dict[str, str] = {
    "openai": "ChatGPT",
    "anthropic": "Claude",
    "gemini": "Gemini",
    "perplexity": "Perplexity",
    "google_ai_overviews": "Google AI Overviews",
    "google_ai_mode": "Google AI Mode",
    "openai_search": "ChatGPT Search",
    "gemini_grounded": "Gemini (grounded)",
    "mock": "Mock engine",
}

#: Client-facing wording for each intent bucket, both families.
_BUCKET_LABELS: dict[str, str] = {
    IntentBucket.PROBLEM_AWARE.value: "Problem-aware",
    IntentBucket.CATEGORY.value: "Category",
    IntentBucket.COMPARISON.value: "Comparison",
    IntentBucket.ADJACENT_AUTHORITY.value: "Adjacent authority",
    IntentBucket.LOCAL_INTENT.value: "Local intent",
    IntentBucket.HYBRID.value: "Hybrid (local + commercial)",
    IntentBucket.INFORMATIONAL.value: "Informational",
    IntentBucket.BRAND.value: "Brand",
}


def engine_label(name: str) -> str:
    """Surface name a client reads. Unknown engines fall back to their key
    prettified rather than to an empty cell — an unlabelled surface is still a
    fact about the run."""
    return _ENGINE_LABELS.get(name, name.replace("_", " ").title())


def bucket_label(bucket: str) -> str:
    return _BUCKET_LABELS.get(bucket, bucket.replace("_", " ").capitalize())


class RatePayload(TypedDict):
    """Re-declared here rather than imported from `reports` to keep the import
    one-way (`reports` imports this module, never the reverse). Structurally
    identical — the same dict satisfies both."""

    successes: int
    n: int
    n_eff: float
    rate: float
    ci_low: float
    ci_high: float
    label: str


def rate_payload(successes: int, n: int, runs_per_query: int, unit: str = "runs") -> RatePayload:
    """The only shape a rate is allowed to ship in."""
    iv = stats.interval(successes, n, runs_per_query=max(1, runs_per_query))
    return RatePayload(
        successes=successes,
        n=n,
        n_eff=round(iv.n_eff, 2),
        rate=iv.point,
        ci_low=iv.lower,
        ci_high=iv.upper,
        label=stats.format_rate(successes, n, unit),
    )


@dataclass(frozen=True)
class CycleMetrics:
    """One earlier cycle's headline numbers, for the N-cycle trend (TR-T3).

    The lifecycle history already walks every comparable prior run and loads its
    results and judgments; this is what that walk keeps hold of so the trend does
    not need a second pass over storage.

    ``coverage_ratio`` is carried because a cycle that only half-measured is not
    a point on a trend line — P2-T2 guardrail A gates it out rather than letting
    a half-run render as a drop in visibility.
    """

    run_id: str
    run_date: str
    query_set_version: str
    coverage_ratio: float
    mention_successes: int
    mention_n: int
    citation_successes: int
    citation_n: int
    share_of_model: float
    prominence: str | None
    #: brand -> (present cells, answered cells). Counts rather than rates because
    #: the significance gate needs both sides' denominators; a rate alone cannot
    #: tell a 2-of-4 from a 50-of-100.
    brand_counts: dict[str, tuple[int, int]]
    #: intent bucket -> the client's mention rate in it, for the §4 delta.
    mention_by_bucket: dict[str, float]
    #: cited domain -> count, for the §7 "up from 12 last cycle" delta.
    citation_counts: dict[str, int]


# --- §1 Executive snapshot (TR-T1) -------------------------------------------


class TilePayload(TypedDict):
    """One measured tile. Every value is counted or measured — never scored.

    ``delta`` is already formatted by `fmt` (percentage points for a rate,
    percent change for a count), and ``direction`` is only ever "up"/"down" when
    the significance gate passed. An ungated move renders its value and interval
    flat: an arrow is a claim that something happened.
    """

    key: str
    label: str
    value: str
    secondary: str
    delta: str
    direction: str  # up | down | flat | unknown
    gated: bool


class ExecSnapshotPayload(TypedDict):
    """Six measured tiles and one NEUTRAL sentence.

    No composite, no grade, and **no action clause** — the BLUF action opens
    section 8, not this one. The two accountability tiles (open findings, oldest
    still open) live in section 2 where the accountability arithmetic is.
    """

    tiles: list[TilePayload]
    summary: str


def _interval_phrase(rate: RatePayload) -> str:
    if rate["n"] <= 0:
        return "no answers returned"
    return f"95% interval {rate['ci_low']:.0%}–{rate['ci_high']:.0%}"


def build_exec_snapshot(
    *,
    client: str,
    visibility: RatePayload,
    prior_visibility_rate: float | None,
    overall_direction: str,
    share_of_model: float,
    top_competitor: str | None,
    top_competitor_share: float | None,
    citation: RatePayload | None,
    prominence_distribution: dict[str, int],
    median_prominence: str | None,
    engines: Sequence[str],
    n_queries: int,
    runs_per_query: int,
    answered_cells: int,
) -> ExecSnapshotPayload:
    """The six tiles, in a fixed order, plus a neutral one-line summary."""
    tiles: list[TilePayload] = []

    tiles.append(
        TilePayload(
            key="mention_rate",
            label="AI visibility",
            value=visibility["label"],
            secondary=_interval_phrase(visibility),
            delta="",
            direction="flat",
            gated=False,
        )
    )

    # Tile 2 — the change, in PERCENTAGE POINTS, and only arrowed when gated.
    # A first cycle says "Baseline — no prior cycle", never "0.0 pp": nothing was
    # measured before, which is a different statement from "it did not move".
    gated = overall_direction in ("up", "down")
    tiles.append(
        TilePayload(
            key="change",
            label="Change vs prior cycle",
            value=(
                NO_PRIOR
                if prior_visibility_rate is None
                else fmt_rate_delta(prior_visibility_rate, visibility["rate"])
            ),
            secondary=(
                ""
                if prior_visibility_rate is None
                else "significant at this sample size"
                if gated
                else "within this cycle's noise"
            ),
            delta="",
            direction=overall_direction if prior_visibility_rate is not None else "unknown",
            gated=gated,
        )
    )

    tiles.append(
        TilePayload(
            key="share_of_model",
            label="Share of model",
            value=f"{share_of_model:.0%}",
            secondary=(
                f"{top_competitor} {top_competitor_share:.0%}"
                if top_competitor and top_competitor_share is not None
                else "no competitor measured"
            ),
            delta="",
            direction="flat",
            gated=False,
        )
    )

    tiles.append(
        TilePayload(
            key="citation_rate",
            label="Citation rate",
            value=(citation["label"] if citation else "not measured"),
            secondary=(
                _interval_phrase(citation)
                if citation
                else "no client domain was supplied, so citations cannot be attributed"
            ),
            delta="",
            direction="flat",
            gated=False,
        )
    )

    # Tile 5 — prominence as a DISTRIBUTION plus a median ordinal label. Never a
    # decimal: the composite that produced one was removed in TR-T0.
    present_levels = [
        f"{judge_metrics.prominence_label(level)} {count}"
        for level, count in prominence_distribution.items()
        if count
    ]
    tiles.append(
        TilePayload(
            key="prominence",
            label="Typical position",
            value=judge_metrics.prominence_label(median_prominence),
            secondary=" · ".join(present_levels) or "not measured",
            delta="",
            direction="flat",
            gated=False,
        )
    )

    # Tile 6 — what the numbers rest on. A snapshot whose answered count is a
    # small fraction of what was attempted is thin evidence however confident the
    # rates above look, and the reader is entitled to see the multiplication.
    tiles.append(
        TilePayload(
            key="coverage",
            label="Measured",
            value=f"{answered_cells} answers",
            secondary=(
                f"{len(engines)} surface{'s' if len(engines) != 1 else ''} × "
                f"{n_queries} question{'s' if n_queries != 1 else ''} × "
                f"{runs_per_query} run{'s' if runs_per_query != 1 else ''}"
            ),
            delta="",
            direction="flat",
            gated=False,
        )
    )

    # DESCRIPTIVE. States what was measured and stops — the action clause opens
    # section 8. A recommendation here would put interpretation on page 1 and
    # make the measurement inseparable from the advice.
    if visibility["n"] <= 0:
        summary = (
            f"No surface returned an answer this cycle, so {client}'s visibility "
            f"could not be measured."
        )
    else:
        summary = (
            f"{client} appears in {visibility['label']} across "
            f"{len(engines)} surface{'s' if len(engines) != 1 else ''}, with a "
            f"{share_of_model:.0%} share of model."
        )
        if top_competitor and top_competitor_share is not None:
            summary += f" {top_competitor} holds {top_competitor_share:.0%}."
    return ExecSnapshotPayload(tiles=tiles, summary=summary)


# --- §3 Visibility trend (TR-T3) ---------------------------------------------

#: Below this many comparable cycles, the section draws points without a
#: connecting line. A line through two points asserts a trend the data cannot
#: support, and a reader reads the slope, not the sample size.
MIN_CYCLES_FOR_LINE = 4


class TrendPoint(TypedDict):
    run_date: str
    run_id: str
    mention: RatePayload
    citation: RatePayload | None
    share_of_model: float
    prominence: str | None
    prominence_label: str
    is_current: bool


class TrendPayload(TypedDict):
    """Four series by cycle: mention rate, share of voice, citation rate,
    prominence. Only over cycles that are COMPARABLE INSTRUMENTS — same query set
    — and that passed the coverage gate."""

    points: list[TrendPoint]
    cycles: int
    draw_line: bool
    # What the section says instead of a chart when there is not enough history.
    # Never an empty plot: "we have one cycle" is information.
    statement: str
    excluded_cycles: int


def build_trend(
    *,
    history: Sequence[CycleMetrics],
    current: CycleMetrics,
    runs_per_query: int,
    query_set_version: str,
    min_coverage: float,
) -> TrendPayload:
    """The N-cycle series, gated on comparability and coverage."""
    candidates = [c for c in history if c.query_set_version == query_set_version]
    kept = [c for c in candidates if c.coverage_ratio >= min_coverage]
    excluded = len(candidates) - len(kept)
    series = [*kept, current]

    points: list[TrendPoint] = [
        TrendPoint(
            run_date=c.run_date,
            run_id=c.run_id,
            mention=rate_payload(
                c.mention_successes, c.mention_n, runs_per_query, unit="sampled answers"
            ),
            citation=(
                rate_payload(c.citation_successes, c.citation_n, runs_per_query)
                if c.citation_n
                else None
            ),
            share_of_model=c.share_of_model,
            prominence=c.prominence,
            prominence_label=judge_metrics.prominence_label(c.prominence),
            is_current=c.run_id == current.run_id,
        )
        for c in series
    ]

    cycles = len(points)
    if cycles < 2:
        latest = points[-1]["mention"]["label"] if points else "insufficient data"
        statement = (
            f"This is the first comparable cycle: {latest}. A trend needs a second "
            f"measurement of the same question set to exist."
        )
    elif cycles < MIN_CYCLES_FOR_LINE:
        statement = (
            f"{cycles} comparable cycles so far — plotted as points. A connecting "
            f"line is drawn from the {MIN_CYCLES_FOR_LINE}th cycle onward, because a "
            f"line through fewer points asserts a direction this sample cannot support."
        )
    else:
        statement = f"{cycles} comparable cycles of the {query_set_version} question set."
    if excluded:
        statement += (
            f" {excluded} earlier cycle{'s' if excluded != 1 else ''} "
            f"{'were' if excluded != 1 else 'was'} left out for incomplete coverage."
        )

    return TrendPayload(
        points=points,
        cycles=cycles,
        draw_line=cycles >= MIN_CYCLES_FOR_LINE,
        statement=statement,
        excluded_cycles=excluded,
    )


# --- §4 Results by question type (TR-T4) -------------------------------------

#: A bucket whose Wilson interval is wider than this renders its COUNT and
#: INTERVAL only, point estimate suppressed. P2-T3 defines no minimum n and this
#: does not invent one — it suppresses the misleading part (a point estimate the
#: interval does not support) while still reporting what was seen.
MAX_INTERVAL_WIDTH_PP = 30.0  # ±15 pp


class QuestionTypeRow(TypedDict):
    bucket: str
    label: str
    mention: RatePayload
    citation_rate: float | None
    delta: str
    # True when the interval is too wide to quote a point estimate from.
    suppress_point: bool


class QuestionTypePayload(TypedDict):
    """Per intent bucket, FAMILY-AWARE.

    ``IntentBucket`` carries two families — consumer and local-service — and
    hardcoding the consumer five would render an empty section for every
    local-service client. The family is read from the buckets the run actually
    used, so a set that mixes them still reports every bucket it measured.
    """

    family: str  # consumer | local | mixed
    rows: list[QuestionTypeRow]
    best: str
    weakest: str
    note: str


def _bucket_family(buckets: Sequence[str]) -> str:
    consumer = {b.value for b in CONSUMER_BUCKETS}
    local = {b.value for b in LOCAL_BUCKETS}
    seen = set(buckets)
    # BRAND is in both families and cannot discriminate on its own.
    discriminating = seen - {IntentBucket.BRAND.value}
    if discriminating and discriminating <= local:
        return "local"
    if discriminating and discriminating <= consumer:
        return "consumer"
    return "mixed"


def build_question_types(
    *,
    results: list[QueryResult],
    client: str,
    client_domains: Sequence[str],
    runs_per_query: int,
    prior_by_bucket: dict[str, float] | None = None,
) -> QuestionTypePayload:
    """Mention and citation rate per bucket, with the weak ones named."""
    coverage = metrics.coverage_by_bucket(results, client)
    mention = metrics.mention_rate_by_bucket(results, client)
    citation = (
        metrics.citation_rate_by_bucket(results, list(client_domains)) if client_domains else {}
    )

    rows: list[QuestionTypeRow] = []
    for bucket in sorted(mention):
        cov = coverage.get(bucket, metrics.Coverage(answered_cells=0, total_cells=0))
        successes = round(mention[bucket] * cov.answered_cells)
        rate = rate_payload(successes, cov.answered_cells, runs_per_query, unit="answers")
        width_pp = (rate["ci_high"] - rate["ci_low"]) * 100
        rows.append(
            QuestionTypeRow(
                bucket=bucket,
                label=bucket_label(bucket),
                mention=rate,
                citation_rate=(citation.get(bucket) if client_domains else None),
                delta=(
                    fmt_rate_delta((prior_by_bucket or {}).get(bucket), mention[bucket])
                    if prior_by_bucket
                    else NO_PRIOR
                ),
                suppress_point=cov.answered_cells > 0 and width_pp > MAX_INTERVAL_WIDTH_PP,
            )
        )

    measured = [r for r in rows if r["mention"]["n"] > 0]
    best = max(measured, key=lambda r: r["mention"]["rate"])["label"] if measured else "—"
    weakest = min(measured, key=lambda r: r["mention"]["rate"])["label"] if measured else "—"
    family = _bucket_family([r["bucket"] for r in rows])
    note = (
        "Buckets whose interval is wider than ±15 points show their count and interval "
        "only — the point estimate would imply a precision this sample does not have."
        if any(r["suppress_point"] for r in rows)
        else ""
    )
    return QuestionTypePayload(
        family=family, rows=rows, best=best, weakest=weakest, note=note
    )


# --- §5 Results by surface (TR-T5) -------------------------------------------


class SurfaceRow(TypedDict):
    engine_name: str
    label: str
    model_id: str
    mention: RatePayload
    prominence_distribution: dict[str, int]
    attempted_cells: int
    answered_cells: int
    coverage_ratio: float
    # False ⇒ this surface failed the coverage gate. Labelled as such and never
    # silently averaged into the total: a surface that half-answered looks like a
    # visibility drop and is not one.
    coverage_ok: bool
    delta: str
    direction: str


class SurfacePayload(TypedDict):
    rows: list[SurfaceRow]
    degraded: list[str]  # labels of surfaces that failed the coverage gate
    dead: list[str]  # surfaces that returned nothing at all
    note: str


def build_surfaces(
    *,
    results: list[QueryResult],
    cells: Sequence[judge_metrics.BrandCell],
    engines: Sequence[str],
    dead_engines: Sequence[str],
    engine_models: dict[str, str],
    runs_per_query: int,
    movements: Sequence[movement.Movement],
    min_coverage: float,
) -> SurfacePayload:
    """Per engine: rate with denominator, prominence spread, attempted vs returned."""
    coverage = metrics.coverage_by_engine(results)
    by_engine: dict[str, list[judge_metrics.BrandCell]] = {}
    for cell in cells:
        by_engine.setdefault(cell.engine_name, []).append(cell)
    moves = {m.key: m for m in movements}

    rows: list[SurfaceRow] = []
    degraded: list[str] = []
    for name in sorted(engines):
        cov = coverage.get(name, metrics.Coverage(answered_cells=0, total_cells=0))
        engine_cells = by_engine.get(name, [])
        present = sum(1 for c in engine_cells if c.present)
        ratio = cov.answered_cells / cov.total_cells if cov.total_cells else 0.0
        move = moves.get(name)
        ok = ratio >= min_coverage
        if not ok:
            degraded.append(engine_label(name))
        rows.append(
            SurfaceRow(
                engine_name=name,
                label=engine_label(name),
                model_id=engine_models.get(name, ""),
                mention=rate_payload(present, len(engine_cells), runs_per_query, unit="answers"),
                prominence_distribution=judge_metrics.prominence_distribution(engine_cells),
                attempted_cells=cov.total_cells,
                answered_cells=cov.answered_cells,
                coverage_ratio=round(ratio, 3),
                coverage_ok=ok,
                delta=(fmt_pp(move.delta_pp) if move else NO_PRIOR),
                direction=(move.direction if move else "unknown"),
            )
        )

    note = ""
    if degraded:
        note = (
            f"{', '.join(degraded)} returned answers for under "
            f"{min_coverage:.0%} of the cells attempted this cycle. Their rates are "
            f"reported but are not comparable to a fully-measured surface."
        )
    return SurfacePayload(
        rows=rows,
        degraded=degraded,
        dead=[engine_label(e) for e in dead_engines],
        note=note,
    )


# --- §6 Competitive position (TR-T6) -----------------------------------------


class CompetitiveRow(TypedDict):
    brand: str
    is_client: bool
    mention: RatePayload
    share_of_model: float
    prominence: str | None
    prominence_label: str
    prominence_distribution: dict[str, int]
    delta: str
    direction: str


class CompetitivePayload(TypedDict):
    rows: list[CompetitiveRow]
    gained: list[str]
    lost: list[str]
    note: str


def build_competitive(
    *,
    board: Sequence[judge_metrics.LeaderRow],
    client: str,
    shares: dict[str, float],
    prior_mention: dict[str, float] | None,
    runs_per_query: int,
    gated_brands: Sequence[str] = (),
) -> CompetitivePayload:
    """The leaderboard, ordered by mention rate, with gated movement.

    ``gated_brands`` are the brands whose change passed the significance gate.
    Everything else renders flat with its interval shown — a direction arrow is a
    claim that something happened, and at 3–5 runs most week-over-week wobble is
    the sampling, not the market.
    """
    rows: list[CompetitiveRow] = []
    gained: list[str] = []
    lost: list[str] = []
    for row in board:
        before = (prior_mention or {}).get(row.brand)
        moved = row.brand in set(gated_brands)
        direction = "unknown"
        if before is not None:
            if not moved:
                direction = "flat"
            elif row.mention_rate > before:
                direction = "up"
                gained.append(row.brand)
            else:
                direction = "down"
                lost.append(row.brand)
        rows.append(
            CompetitiveRow(
                brand=row.brand,
                is_client=row.brand == client,
                mention=rate_payload(
                    row.present_cells, row.cells, runs_per_query, unit="answers"
                ),
                share_of_model=shares.get(row.brand, 0.0),
                prominence=row.prominence,
                prominence_label=judge_metrics.prominence_label(row.prominence),
                prominence_distribution=row.distribution,
                delta=fmt_rate_delta(before, row.mention_rate),
                direction=direction,
            )
        )

    if prior_mention is None:
        note = "First comparable cycle — there is no prior standing to move from."
    elif not gained and not lost:
        note = "No brand's change cleared this cycle's noise threshold."
    else:
        parts = []
        if gained:
            parts.append(f"{', '.join(gained)} gained")
        if lost:
            parts.append(f"{', '.join(lost)} lost")
        note = "; ".join(parts) + " by more than this cycle's noise threshold."
    return CompetitivePayload(rows=rows, gained=gained, lost=lost, note=note)


# --- §7 Citation results (TR-T7) ---------------------------------------------

#: Source-type buckets, in the order they render. Deterministic classification,
#: no LLM: the report must produce the same table on every re-render, and a
#: model that reclassifies youtube.com between editions manufactures a change.
SOURCE_TYPES: tuple[str, ...] = (
    "owned",
    "earned",
    "directory",
    "social",
    "video",
    "competitor",
)

_SOCIAL_DOMAINS = frozenset(
    {
        "reddit.com",
        "x.com",
        "twitter.com",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "linkedin.com",
        "quora.com",
        "threads.net",
        "nextdoor.com",
    }
)
_VIDEO_DOMAINS = frozenset({"youtube.com", "youtu.be", "vimeo.com", "twitch.tv"})
_DIRECTORY_DOMAINS = frozenset(
    {
        "yelp.com",
        "g2.com",
        "capterra.com",
        "trustpilot.com",
        "bbb.org",
        "angi.com",
        "angieslist.com",
        "thumbtack.com",
        "houzz.com",
        "tripadvisor.com",
        "apps.apple.com",
        "play.google.com",
        "producthunt.com",
        "crunchbase.com",
        "yellowpages.com",
        "mapquest.com",
    }
)


def _root(domain: str) -> str:
    """"www.reddit.com" -> "reddit.com". Two labels is right for the common TLDs
    this data carries; a domain like "example.co.uk" collapses to "co.uk", which
    is wrong but harmless here — it only affects which BUCKET a citation lands in,
    never the count, and the full domain is what renders."""
    parts = domain.lower().removeprefix("www.").split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else domain.lower().removeprefix("www.")


def classify_source(
    domain: str, client_domains: Sequence[str], competitors: Sequence[str]
) -> str:
    """Which kind of source a cited domain is. Pure and deterministic.

    Competitor matching is on the domain's own name, not on prose: a rival's
    marketing site is "competitor", but an article that merely mentions them is
    "earned". Overreaching here would relabel half the earned coverage as
    competitor-owned and make the section useless.
    """
    root = _root(domain)
    if any(_root(d) == root for d in client_domains if d):
        return "owned"
    if root in _VIDEO_DOMAINS:
        return "video"
    if root in _SOCIAL_DOMAINS:
        return "social"
    if root in _DIRECTORY_DOMAINS:
        return "directory"
    stem = root.split(".")[0]
    for competitor in competitors:
        squashed = "".join(ch for ch in competitor.lower() if ch.isalnum())
        if squashed and squashed == stem:
            return "competitor"
    return "earned"


class CitationDomainRow(TypedDict):
    domain: str
    count: int
    share: float
    # Running total of `share`, domains ordered by count. Answers "are we
    # dependent on 2 sources or 20", which a descending bar chart cannot —
    # the Pareto read (Phase 2 remainder of P2-T6).
    cumulative_share: float
    source_type: str
    is_client: bool
    delta: str


class CitationsPayload(TypedDict):
    client_citations: int
    client_rate: RatePayload | None
    domains: list[CitationDomainRow]
    by_source_type: dict[str, int]
    total_citations: int
    # "The top 3 domains account for 61% of all citations" — the concentration
    # sentence the Pareto curve exists to support.
    concentration: str
    note: str


def build_citations(
    *,
    results: list[QueryResult],
    client_domains: Sequence[str],
    competitors: Sequence[str],
    runs_per_query: int,
    prior_counts: dict[str, int] | None = None,
    limit: int = 25,
) -> CitationsPayload:
    """Client-domain citation count and rate, top domains, source types.

    DESCRIPTIVE ONLY. "youtube.com was cited 31 times" — never "you need a
    YouTube strategy". The recommendation that follows from this table is
    section 8's job, and keeping them apart is what lets an agency resell the
    numbers under its own advice.
    """
    ranked = metrics.top_cited_domains(results, limit=limit)
    total = sum(count for _, count in ranked)
    client_roots = {_root(d) for d in client_domains if d}

    rows: list[CitationDomainRow] = []
    by_type: dict[str, int] = dict.fromkeys(SOURCE_TYPES, 0)
    running = 0
    for domain, count in ranked:
        running += count
        source_type = classify_source(domain, client_domains, competitors)
        by_type[source_type] = by_type.get(source_type, 0) + count
        rows.append(
            CitationDomainRow(
                domain=domain,
                count=count,
                share=(count / total if total else 0.0),
                cumulative_share=(running / total if total else 0.0),
                source_type=source_type,
                is_client=_root(domain) in client_roots,
                delta=(
                    fmt_count_delta((prior_counts or {}).get(domain), count)
                    if prior_counts is not None
                    else NO_PRIOR
                ),
            )
        )

    client_citations = sum(r["count"] for r in rows if r["is_client"])
    client_rate: RatePayload | None = None
    if client_domains:
        # Counted, not back-derived from the rate: multiplying a rate by an
        # assumed denominator is how a 7-of-12 becomes a count that disagrees
        # with the table beside it.
        verdicts = metrics.citation_verdicts(results, list(client_domains))
        answered = [v for v in verdicts if v.hit is not None]
        client_rate = rate_payload(
            sum(1 for v in answered if v.hit), len(answered), runs_per_query, unit="answers"
        )

    top3 = sum(r["count"] for r in rows[:3])
    concentration = (
        f"The top {min(3, len(rows))} domain{'s' if len(rows) != 1 else ''} account for "
        f"{top3 / total:.0%} of the {total} citations captured."
        if total
        else "No citations were captured this cycle."
    )
    note = (
        ""
        if client_domains
        else "No client domain was supplied, so citations to the client cannot be identified."
    )
    return CitationsPayload(
        client_citations=client_citations,
        client_rate=client_rate,
        domains=rows,
        by_source_type=by_type,
        total_citations=total,
        concentration=concentration,
        note=note,
    )


# --- §10 Representative answers (TR-T8) --------------------------------------

#: The five slots and the DETERMINISTIC rule each is filled by. Printed verbatim
#: in the methodology note: these are the examples a client reads most closely,
#: and "why did you pick this one" must have an answer that is not "we liked it".
#: Every tie breaks on (query_id, engine_name, run_index) ascending.
SELECTION_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "strong",
        "A strong appearance",
        "The highest-prominence cell where the client is present.",
    ),
    (
        "weak",
        "A weak or buried appearance",
        "The lowest-prominence cell where the client is still present.",
    ),
    (
        "missing",
        "A missing appearance",
        "A cell where the client is absent and a competitor is recommended first.",
    ),
    (
        "citation",
        "A citation",
        "The first answer citing a client domain.",
    ),
    (
        "inaccurate",
        "An inaccurate statement",
        "The highest-severity accuracy finding's first observation.",
    ),
)


class RepresentativeAnswer(TypedDict):
    slot: str
    slot_label: str
    rule: str
    available: bool
    prompt: str
    query_id: str
    run_index: int
    engine_name: str
    engine_label: str
    model_id: str
    observed_at: str
    excerpt: str
    note: str


class RepresentativePayload(TypedDict):
    slots: list[RepresentativeAnswer]
    selection_rules: list[str]


def _empty_slot(slot: str, label: str, rule: str) -> RepresentativeAnswer:
    """A slot with no qualifying answer says so. It is NEVER filled from another
    slot — substituting a strong appearance into the "missing" slot would make
    the section a highlight reel."""
    return RepresentativeAnswer(
        slot=slot,
        slot_label=label,
        rule=rule,
        available=False,
        prompt="",
        query_id="",
        run_index=0,
        engine_name="",
        engine_label="",
        model_id="",
        observed_at="",
        excerpt="",
        note="No qualifying example this cycle.",
    )


def build_representative_answers(
    *,
    results: list[QueryResult],
    client_cells: Sequence[judge_metrics.BrandCell],
    losing_cells: Sequence[judge_metrics.BrandCell],
    client_domains: Sequence[str],
    engine_models: dict[str, str],
    top_finding_evidence: dict[str, str] | None,
) -> RepresentativePayload:
    """Five slots, filled by published rules, ties broken deterministically."""
    by_cell: dict[tuple[str, str], QueryResult] = {}
    for r in sorted(results, key=lambda r: (r["query_id"], r["engine_name"], r["run_index"])):
        if r["response"] is None:
            continue
        by_cell.setdefault((r["query_id"], r["engine_name"]), r)

    def _from_cell(
        slot: str, label: str, rule: str, cell: judge_metrics.BrandCell, note: str
    ) -> RepresentativeAnswer:
        result = by_cell.get((cell.query_id, cell.engine_name))
        if result is None:
            return _empty_slot(slot, label, rule)
        answer = result["response"] or ""
        return RepresentativeAnswer(
            slot=slot,
            slot_label=label,
            rule=rule,
            available=True,
            prompt=result["prompt"],
            query_id=result["query_id"],
            run_index=result["run_index"],
            engine_name=result["engine_name"],
            engine_label=engine_label(result["engine_name"]),
            model_id=engine_models.get(result["engine_name"], ""),
            observed_at=result.get("timestamp", ""),
            # An excerpt, not the answer. Printing answers inline is what turned
            # the deliverable into 90 pages; the full text is in the export.
            excerpt=answer[:400] + ("…" if len(answer) > 400 else ""),
            note=note,
        )

    prom_rank = {level: i for i, level in enumerate(judge_metrics.PROMINENCE_ORDER)}
    present = sorted(
        (c for c in client_cells if c.present),
        key=lambda c: (prom_rank.get(c.prominence, 99), c.query_id, c.engine_name),
    )
    slots: list[RepresentativeAnswer] = []
    rules = {slot: (label, rule) for slot, label, rule in SELECTION_RULES}

    label, rule = rules["strong"]
    slots.append(
        _from_cell(
            "strong",
            label,
            rule,
            present[0],
            f"Position: {judge_metrics.prominence_label(present[0].prominence)}.",
        )
        if present
        else _empty_slot("strong", label, rule)
    )

    label, rule = rules["weak"]
    slots.append(
        _from_cell(
            "weak",
            label,
            rule,
            present[-1],
            f"Position: {judge_metrics.prominence_label(present[-1].prominence)}.",
        )
        if present
        else _empty_slot("weak", label, rule)
    )

    label, rule = rules["missing"]
    losses = sorted(losing_cells, key=lambda c: (c.query_id, c.engine_name))
    slots.append(
        _from_cell(
            "missing",
            label,
            rule,
            losses[0],
            f"{losses[0].brand} was recommended first; the client did not appear.",
        )
        if losses
        else _empty_slot("missing", label, rule)
    )

    label, rule = rules["citation"]
    cited = next(
        (
            r
            for r in sorted(
                results, key=lambda r: (r["query_id"], r["engine_name"], r["run_index"])
            )
            if r["response"] is not None
            and any(metrics.is_brand_citation(u, client_domains) for u in r["citations"])
        ),
        None,
    )
    if cited is None:
        slots.append(_empty_slot("citation", label, rule))
    else:
        answer = cited["response"] or ""
        slots.append(
            RepresentativeAnswer(
                slot="citation",
                slot_label=label,
                rule=rule,
                available=True,
                prompt=cited["prompt"],
                query_id=cited["query_id"],
                run_index=cited["run_index"],
                engine_name=cited["engine_name"],
                engine_label=engine_label(cited["engine_name"]),
                model_id=engine_models.get(cited["engine_name"], ""),
                observed_at=cited.get("timestamp", ""),
                excerpt=answer[:400] + ("…" if len(answer) > 400 else ""),
                note="Cited: "
                + ", ".join(
                    sorted(
                        {
                            metrics.domain_of(u)
                            for u in cited["citations"]
                            if metrics.is_brand_citation(u, client_domains)
                        }
                    )
                ),
            )
        )

    label, rule = rules["inaccurate"]
    if not top_finding_evidence:
        slots.append(_empty_slot("inaccurate", label, rule))
    else:
        slots.append(
            RepresentativeAnswer(
                slot="inaccurate",
                slot_label=label,
                rule=rule,
                available=True,
                prompt=top_finding_evidence.get("prompt", ""),
                query_id=top_finding_evidence.get("query_id", ""),
                run_index=int(top_finding_evidence.get("run_index", "0") or 0),
                engine_name=top_finding_evidence.get("engine_name", ""),
                engine_label=engine_label(top_finding_evidence.get("engine_name", "")),
                model_id=top_finding_evidence.get("model_id", ""),
                observed_at=top_finding_evidence.get("observed_at", ""),
                excerpt=top_finding_evidence.get("excerpt", ""),
                note=top_finding_evidence.get("reality", ""),
            )
        )

    return RepresentativePayload(
        slots=slots,
        selection_rules=[f"{label}: {rule}" for _, label, rule in SELECTION_RULES],
    )


# --- §11 Methodology note (TR-T9) --------------------------------------------


class MethodologyPayload(TypedDict):
    window_start: str
    window_end: str
    query_set_version: str
    n_queries: int
    runs_per_query: int
    # (surface label, pinned model id). A finding names the model that produced
    # it; the methodology names every model that could have.
    surfaces: list[tuple[str, str]]
    geography: str
    account_config: str
    # Every metric on page 1, defined. A tile a reader cannot define is a tile
    # they cannot check.
    definitions: list[tuple[str, str]]
    # Diffed from the prior cycle: query-set version and engine pins. A silent
    # instrument change is the one thing a recurring report may never do.
    changes_since_last: list[str]
    limitations: list[str]
    selection_rules: list[str]
    non_reproducibility: str
    independence: str
    judge_agreement: str


_DEFINITIONS: tuple[tuple[str, str], ...] = (
    (
        "AI visibility",
        "The share of answers that name you, counted over every answer a surface "
        "returned. Reported as a count with its denominator.",
    ),
    (
        "Share of model",
        "Your mention rate as a proportion of the mention rates of every brand we "
        "tracked. It says how much of the conversation is yours, not how often you appear.",
    ),
    (
        "Citation rate",
        "The share of answers that link to a domain you own.",
    ),
    (
        "Typical position",
        "The median place you hold in the answers where you appear, on a five-level "
        "scale from recommended-first to also-ran. An ordinal label, not a score.",
    ),
    (
        "Percentage points (pp)",
        "The difference between two rates. A move from 42% to 48% is six percentage "
        "points, not a 14% increase.",
    ),
    (
        "95% interval",
        "The range the true rate is likely to sit in given how many answers we "
        "sampled. Two rates whose intervals overlap have not been shown to differ.",
    ),
)

_LIMITATIONS: tuple[str, ...] = (
    "We measure the answers these systems returned to us, at the times listed. We do "
    "not have access to what any individual user is shown.",
    "Sample sizes are small by design — each additional run costs a real API call — so "
    "small movements are reported as flat unless they clear a significance threshold.",
    "Answers are graded by a language model against your fact sheet, with a human "
    "review sample. Where that grading has been measured against human labels, the "
    "agreement figure is published above.",
    "We make no claim about what will happen to these numbers if you act on the "
    "recommendations, and no vendor in this category can substantiate one.",
)


def build_methodology(
    *,
    results: list[QueryResult],
    query_set_version: str,
    runs_per_query: int,
    engines: Sequence[str],
    engine_models: dict[str, str],
    location: str,
    prior_query_set_version: str | None,
    prior_engine_models: dict[str, str] | None,
    non_reproducibility: str,
    independence: str,
    judge_agreement: str,
) -> MethodologyPayload:
    """Everything needed to re-run, check or challenge the measurement."""
    stamps = sorted(str(r.get("timestamp") or "") for r in results if r.get("timestamp"))
    changes: list[str] = []
    if prior_query_set_version and prior_query_set_version != query_set_version:
        changes.append(
            f"The question set changed from {prior_query_set_version} to "
            f"{query_set_version}. Figures are not compared across that change."
        )
    for name in sorted(engines):
        was = (prior_engine_models or {}).get(name)
        now = engine_models.get(name, "")
        if was and now and was != now:
            changes.append(
                f"{engine_label(name)} moved from {was} to {now}. A model change can "
                f"move these numbers on its own."
            )
    if not changes:
        changes.append("No change to the question set or the pinned models since last cycle.")

    return MethodologyPayload(
        window_start=(stamps[0][:19] if stamps else ""),
        window_end=(stamps[-1][:19] if stamps else ""),
        query_set_version=query_set_version,
        n_queries=len({r["query_id"] for r in results}),
        runs_per_query=runs_per_query,
        surfaces=[(engine_label(e), engine_models.get(e, "model not recorded")) for e in engines],
        geography=location or "Not pinned to a location",
        account_config="Logged-out API access, default settings, no personalization history.",
        definitions=list(_DEFINITIONS),
        changes_since_last=changes,
        limitations=list(_LIMITATIONS),
        selection_rules=[f"{label}: {rule}" for _, label, rule in SELECTION_RULES],
        non_reproducibility=non_reproducibility,
        independence=independence,
        judge_agreement=judge_agreement,
    )


# --- Back matter A1–A6 (TR-T10) ----------------------------------------------


class AppendixTable(TypedDict):
    """One appendix. Rows are pre-stringified so the renderer stays generic and
    the page budget is a function of row count rather than of component logic."""

    id: str  # A1..A6
    title: str
    columns: list[str]
    rows: list[list[str]]
    note: str
    total_rows: int  # before any cap, so a truncated table can say so


#: A cap per appendix, so one pathological run cannot produce a 200-page PDF.
#: When it bites the table SAYS SO — silent truncation reads as "this is
#: everything" when it is not.
_MAX_APPENDIX_ROWS = 400


def _table(
    id_: str, title: str, columns: list[str], rows: list[list[str]], note: str = ""
) -> AppendixTable:
    total = len(rows)
    capped = rows[:_MAX_APPENDIX_ROWS]
    if total > len(capped):
        note = (
            f"{note} Showing the first {len(capped)} of {total} rows; the full set is in "
            f"the CSV export."
        ).strip()
    return AppendixTable(
        id=id_, title=title, columns=columns, rows=capped, note=note, total_rows=total
    )


class BackMatterPayload(TypedDict):
    appendices: list[AppendixTable]
    note: str


def build_back_matter(
    *,
    results: list[QueryResult],
    judgments: Sequence[AnswerJudgment],
    client: str,
    competitors: Sequence[str],
    cells_map: dict[str, list[judge_metrics.BrandCell]],
    flags: Sequence[dict[str, object]],
    losing: Sequence[dict[str, object]],
    engine_models: dict[str, str],
) -> BackMatterPayload:
    """Six dense tables. **Verbatim answer text is never printed here.**

    At 6 surfaces × 25 queries × 3 runs that is 450 answers — 90–150 pages
    inline, which recreates exactly the blob this work exists to kill. A2 carries
    the outcome per cell and points at the export for the text.
    """
    ordered = sorted(results, key=lambda r: (r["query_id"], r["engine_name"], r["run_index"]))

    # A1 — every citation.
    a1_rows = [
        [
            url,
            engine_label(r["engine_name"]),
            r["prompt"],
            f"run {r['run_index']}",
            str(r.get("timestamp") or "")[:19],
        ]
        for r in ordered
        for url in r["citations"]
    ]

    # A2 — query x surface x run outcome.
    a2_rows = [
        [
            r["prompt"],
            engine_label(r["engine_name"]),
            str(r["run_index"]),
            "answered" if r["response"] is not None else "no answer returned",
            str(len(r["citations"])),
            str(r.get("timestamp") or "")[:19],
        ]
        for r in ordered
    ]

    # A3 — every flag, joined to its front-matter theme by cluster_id.
    a3_rows = [
        [
            str(f.get("cluster_id") or ""),
            str(f.get("theme") or ""),
            str(f.get("severity") or ""),
            str(f.get("type") or ""),
            str(f.get("claim") or ""),
            str(f.get("reality") or ""),
            engine_label(str(f.get("engine_name") or "")),
            str(f.get("observed_at") or "")[:19],
        ]
        for f in flags
    ]

    # A4 — competitor mentions, per cell.
    a4_rows = [
        [
            brand,
            cell.query_id,
            engine_label(cell.engine_name),
            "present" if cell.present else "absent",
            judge_metrics.prominence_label(cell.prominence) if cell.present else "—",
            cell.framing if cell.present else "—",
        ]
        for brand in competitors
        for cell in sorted(cells_map.get(brand, []), key=lambda c: (c.query_id, c.engine_name))
    ]

    # A5 — worst-performing queries.
    a5_rows = [
        [
            str(row.get("prompt") or ""),
            str(row.get("intent") or ""),
            engine_label(str(row.get("engine_name") or "")),
            str(row.get("competitor") or ""),
            judge_metrics.prominence_label(
                str(row["prominence"]) if row.get("prominence") else None
            ),
        ]
        for row in losing
    ]

    # A6 — the verbatim, versioned query set.
    seen: dict[str, str] = {}
    for r in ordered:
        seen.setdefault(r["query_id"], r["prompt"])
    intents = {r["query_id"]: r["intent"] for r in ordered}
    a6_rows = [[prompt, bucket_label(intents.get(qid, ""))] for qid, prompt in seen.items()]

    return BackMatterPayload(
        appendices=[
            _table(
                "A1",
                "Citation ledger",
                ["URL", "Surface", "Question", "Run", "Observed"],
                a1_rows,
                "Every URL any surface cited, whoever it belongs to.",
            ),
            _table(
                "A2",
                "Question × surface × run outcomes",
                ["Question", "Surface", "Run", "Outcome", "Citations", "Observed"],
                a2_rows,
                "The full answer text is in the CSV export, not printed here.",
            ),
            _table(
                "A3",
                "Full findings table",
                [
                    "Finding id",
                    "Theme",
                    "Severity",
                    "Type",
                    "Claim",
                    "Your fact sheet",
                    "Surface",
                    "Observed",
                ],
                a3_rows,
                "Every observation behind the themed findings in section 9.",
            ),
            _table(
                "A4",
                "Competitor mention ledger",
                ["Brand", "Question id", "Surface", "Presence", "Position", "Framing"],
                a4_rows,
            ),
            _table(
                "A5",
                "Worst-performing questions",
                ["Question", "Intent", "Surface", "Competitor named", "Their position"],
                a5_rows,
                f"Questions where a competitor was recommended and {client} was not.",
            ),
            _table(
                "A6",
                "The question set, verbatim",
                ["Question", "Intent"],
                a6_rows,
                "Every question exactly as it was asked.",
            ),
        ],
        note=(
            "These tables are the raw outputs behind the analysis. They are here so "
            "every figure in the front matter can be traced to the observation that "
            "produced it."
        ),
    )
