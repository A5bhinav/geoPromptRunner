from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import TypedDict

from src.engines.local_pack import LocalPackCapture
from src.pipeline import findings as findings_mod
from src.pipeline import judge_metrics, lifecycle, metrics, movement, stats
from src.pipeline import themes as themes_mod
from src.pipeline.calibration import load_agreement_summary
from src.pipeline.orchestrator import AuditOutcome
from src.pipeline.priority import sort_key as priority_sort_key
from src.pipeline.severity import SEVERITY_ORDER
from src.storage.models import AccuracyFlag, AnswerJudgment

__all__ = [
    "GradePayload",
    "RatePayload",
    "ScorecardPayload",
    "LeaderRow",
    "BucketRow",
    "StabilityRow",
    "EngineCellRow",
    "FlagRow",
    "OccurrenceRow",
    "EvidenceRow",
    "FindingGroupRow",
    "OpenFindingsPayload",
    "MovementRow",
    "WhatChangedPayload",
    "SourceRow",
    "LosingRow",
    "SiteCheckRow",
    "SiteFindingRow",
    "RoadmapRow",
    "SiteAuditPayload",
    "ReportPayload",
    "NON_REPRODUCIBILITY_DISCLOSURE",
    "INDEPENDENCE_DISCLAIMER",
    "JUDGE_AGREEMENT_UNMEASURED",
    "build_report",
]

#: Shipped once per report, in the methodology section, VERBATIM.
#:
#: A client will re-run a prompt, get a different answer, and doubt the report.
#: Pre-empt it; never let them discover it. This wording has been written to be
#: honest without being self-undermining — **do not paraphrase it**, and do not
#: "tighten" it in a copy pass. Standing rule:
#: ``.claude/skills/audit-packaging/SKILL.md``.
NON_REPRODUCIBILITY_DISCLOSURE = (
    "We do not claim these errors are permanent or that they will reproduce on demand. "
    "AI models are updated frequently and produce different answers to identical prompts "
    "even when nothing about your brand has changed — a documented property of how these "
    "systems are served, not a flaw in our testing. Each finding states how many "
    "independent attempts we made, how many produced the error, the exact date and time, "
    "and the exact prompt used. Our claims are about what we observed, when — not a "
    "guarantee of what you will see if you ask right now."
)

#: What the methodology says when no gold set has been run for this CLIENT.
#:
#: The genuine no-measurement case only — a client with a stored summary in
#: ``data/calibration/`` publishes its real figures instead. Saying nothing would
#: be worse than either: every Critical finding rests on the judge, and an
#: omission reads as "not applicable" rather than "not measured".
JUDGE_AGREEMENT_UNMEASURED = (
    "Judge agreement with a human reviewer has not yet been measured at a sample size "
    "that would support quoting a figure. Every finding in this report cites the exact "
    "prompt, model and date behind it so it can be checked directly."
)

#: Also once per report. Nominative fair use covers plain-text vendor names; it
#: does not cover logos, and it does not cover an implication of endorsement.
INDEPENDENCE_DISCLAIMER = (
    "Not affiliated with, sponsored by, or endorsed by OpenAI, Anthropic, Google or "
    "Perplexity. Product names are used solely to identify which system produced the "
    "observed output."
)


class GradePayload(TypedDict):
    letter: str
    score: float
    raw_score: float
    accuracy_penalty: float
    n_flags: int
    rationale: str


class RatePayload(TypedDict):
    """A rate WITH its denominator and its interval. The only shape a rate ships in.

    ``successes``/``n`` are what the report renders — "7 of 12 runs" — and ``rate``
    is secondary. ``ci_low``/``ci_high`` are Wilson bounds computed on the
    design-corrected effective sample (``n_eff``), so the interval reflects that
    repeat runs of one prompt are correlated rather than independent.

    ``n == 0`` means insufficient data. It does NOT mean 0%, and a consumer that
    renders it as 0% is asserting the opposite of what was measured.
    """

    successes: int
    n: int
    n_eff: float
    rate: float
    ci_low: float
    ci_high: float
    label: str  # "7 of 12 runs (58%)" — pre-formatted so every surface agrees


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
    """One raw flag. Kept for CSV/JSON export and the appendix — **not** the thing
    the report renders. ``finding_groups`` is what a client reads."""

    type: str
    severity: str  # the FOUR-level scale; `critical` is derived, see severity.py
    claim: str
    reality: str
    # Provenance: which cell produced this flag (P0-T1). Empty strings when the
    # flag predates the stamping — legacy stored judgments. Anything that RENDERS
    # a flag to a client needs these: a finding without engine + verbatim prompt
    # is not shippable.
    query_id: str
    engine_name: str
    intent: str
    run_index: int
    observed_at: str
    # Identity + root cause, derived at build time (P0-T1/T3).
    cluster_id: str
    theme: str


class OccurrenceRow(TypedDict):
    """How reproducibly a finding appeared. Both numbers or neither."""

    observed: int
    total: int
    first_seen_date: str
    last_seen_date: str
    # "observed in 4 of 5 runs across 06-11 → 06-13" — the per-finding short form
    # of the non-reproducibility disclosure. Pre-formatted so the wording cannot
    # drift between the web report, the digest and the PDF.
    phrase: str


class EvidenceRow(TypedDict):
    """What makes a finding checkable. Every field is required to ship one."""

    prompt: str  # VERBATIM question. Never the query id.
    # Join keys for the drill-down endpoint (P3-T1). Carried so the card can
    # fetch the full answer; NEVER rendered — `cmp-05` is the most actionable
    # data in the report made unreadable.
    query_id: str
    run_index: int
    engine_name: str
    model_id: str  # the pinned model that answered; "" when the run predates it
    intent: str
    observed_at: str
    excerpt: str  # the model's own words
    reality: str  # the fact-sheet line, verbatim


class FindingGroupRow(TypedDict):
    """One root cause, one card, one action. The unit the report is built from.

    Keyed on ``theme``, not on a claim cluster: "confused with Fitbit" and "not a
    recognized brand" cluster apart and are one root cause with one fix. Grouping
    on the cluster produced 54 cards from the real Fort run.
    """

    theme: str
    theme_label: str
    title: str
    severity: str
    instance_count: int  # SECONDARY. Headline counts are themes, not instances.
    engines: list[str]
    intents: list[str]
    occurrence: OccurrenceRow
    representative_claims: list[str]
    # Every distinct claim-cluster folded in. The lifecycle engine tracks THESE
    # across weeks (P2-T2); the card tracks the theme.
    member_cluster_ids: list[str]
    reality: str
    evidence: list[EvidenceRow]
    # Observations this finding HAS, vs the capped set above. A card that shows 4
    # of 94 must say so; one that implies it showed all 94 is overstating.
    evidence_total: int
    fix_channel: str
    owner: str
    effort: str  # S | M | L
    action: str
    verification: str
    priority: float
    flag_types: list[str]
    # --- lifecycle (P2-T2). "new" on a first cycle, which is honest: nothing has
    # been compared against, so nothing can be persisting or resolved. ---
    lifecycle_status: str  # new | persisting | resolved | regressed
    cycles_open: int
    first_seen_date: str


class EngineCellRow(TypedDict):
    """One brand's presence on one engine, as a count with its denominator."""

    brand: str
    engine_name: str
    present: int  # cells where the brand appeared
    cells: int  # cells that returned an answer at all — 0 means NOT MEASURED
    rate: float


class OpenFindingsPayload(TypedDict):
    """The open-findings tile. Counted, never scored.

    ``themes`` is the client-facing number. ``instances`` is the observation count
    behind it and appears only as a secondary figure — one counting unit per view.
    """

    themes: int
    critical: int
    instances: int
    # Theme counts per severity, in SEVERITY_ORDER. This is what the count bar
    # renders: "3 Critical · 12 High · 40 Medium · 180 Low", before any card.
    by_severity: dict[str, int]


class SourceRow(TypedDict):
    domain: str
    count: int


class LosingRow(TypedDict):
    # The verbatim question, which is what renders (P1-T3). `query_id` stays in
    # the payload as a join key and MUST NOT be shown: `cmp-05` is the most
    # actionable data in the report rendered unreadable. Every credible tool in
    # the category shows the real thing — Lighthouse the resource, axe the
    # selector, Semrush the URL.
    prompt: str
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
    """Four measured tiles. **No letter grade, no composite score.**

    Every headline number here is either *counted* (findings, cycles open) or
    *measured* (sampled rate, share of model). That is a hard rule and the one
    most likely to be quietly re-litigated — an earlier draft compromised to
    "split the grade into two subscores", which smuggled a `B−` straight back onto
    page 1 (P1-T6).

    Why it stays dead: a static score is the hero metric of a ONE-OFF audit, and
    this is a recurring product whose hero is the delta and the closing backlog —
    both already on the page. A grade over our own rubric is opaque, unauditable,
    and unmovable by the client; nobody can act on a `B−`. And grading a
    pre-launch brand on visibility it structurally cannot have is a category
    error: a thin file, not a bad score.

    ``visibility_grade`` survives in the payload for back-compat with stored
    deliverables and the CSV export. **Nothing renders it.**
    """

    visibility_grade: GradePayload | None
    # Tile 1 — AI visibility, as a count with its denominator.
    ai_visibility: RatePayload
    # Tile 3 — open findings, counted in THEMES.
    open_findings: OpenFindingsPayload
    # Tile 4 — the oldest still-open finding, which replaces the grade and does
    # its job better: SLA-style aging is what creates pressure to act, and it is
    # a count rather than an opinion. None until the lifecycle lands (P2-T2); the
    # tile renders "—" rather than inventing an age.
    oldest_open: FindingGroupRow | None
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


class MovementRow(TypedDict):
    """One surface's week-over-week change, already gated."""

    key: str  # the client-facing surface label
    before_successes: int
    before_n: int
    after_successes: int
    after_n: int
    delta_pp: float
    direction: str  # up | down | flat | unknown
    # "ChatGPT: held steady at 8 of 12 runs" — pre-formatted so the wording is the
    # same in the report, the digest and the PDF.
    phrase: str
    # Why it is flat, when it is. A reader who asks "why isn't this news" gets an
    # answer instead of a shrug.
    flat_reason: str


class WhatChangedPayload(TypedDict):
    """Lead with what changed, not with a static score.

    ``accountability`` is the sentence that determines renewal — *"3 of 7 findings
    from last cycle are resolved, 1 regressed, 4 still open"*. Its arithmetic must
    close exactly (``opening = resolved + still_open``,
    ``closing = still_open + new + regressed``) or a reader can do the subtraction
    and catch a contradiction, after which every number on the page is suspect.
    """

    available: bool  # False on a first cycle or a blocked comparison
    accountability: str
    opening: int
    resolved: int
    still_open: int
    new: int
    regressed: int
    closing: int
    resolved_all_time: int
    cycles_considered: int
    # Per-surface, in a FIXED order so the section can be compared at a glance
    # between editions. Flat cells are included, never omitted.
    movements: list[MovementRow]
    prior_run_date: str


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
    # Brand x engine presence, every cell carrying its own denominator. Engine
    # divergence is the most decision-relevant split in this data and nothing
    # showed it before. Empty on the regex path (no per-brand cell structure).
    engine_matrix: list[EngineCellRow]
    # --- the deliverable ---------------------------------------------------
    # One bold sentence a CMO can act on, generated DETERMINISTICALLY from
    # structured fields. No LLM: narrative generation is P4-T4 and must not land
    # before the grounding post-check exists. A hallucinating summary in a
    # hallucination-detection product is the worst failure mode available.
    exec_summary: str
    # Lead with what changed. Placed immediately after the exec summary and
    # before the scorecard, because "did your recommendations do anything" is
    # what determines renewal.
    what_changed: WhatChangedPayload
    # The theme-classification rules that produced these groupings. Both cycles
    # are always classified with the CURRENT rules, so a rule change cannot
    # manufacture a resolve — this is here so a future edition-diff can say
    # "we regrouped these findings; nothing about your brand moved".
    theme_rules_version: str
    # ≤15 themed findings, ordered Critical → High → Medium → Low then by
    # priority. THIS is what renders; `accuracy_flags` is the appendix.
    finding_groups: list[FindingGroupRow]
    # The 3–7 highest-priority actions, a subset of `finding_groups` in the same
    # order. Pre-sliced so every surface shows the same shortlist.
    priority_actions: list[FindingGroupRow]
    # How the theme classifier coped this run: rule / type-default / unclassified.
    # A rising type_default share is the leading indicator the rule set has
    # stopped keeping up. Reported, never averaged away.
    theme_coverage: dict[str, float]
    # Why no week-over-week comparison is shown, when there isn't one:
    # "no_prior_run" | "query_set_changed" | "" (a comparison IS available).
    # Rendered as an honest explanation rather than a silent absence.
    comparison_blocked_reason: str
    # Verbatim, once per report. See the module constants.
    methodology_disclosure: str
    independence_disclaimer: str
    # How often the judge agreed with a human reviewer, published in the
    # methodology section. Empty when it has not been measured — "the judge said
    # so" is not an evidentiary standard for a Critical finding shown to a CMO,
    # and the honest version of an unmeasured judge is saying so, not omitting it.
    judge_agreement: str
    accuracy_flags: list[FlagRow]
    # The WEAKEST verification across the fact sheet this run was judged against
    # (a `Verification` value), or None when no sheet was used. Consumers that
    # SEND a flag — the teaser one-pager above all — must gate on it via
    # `factsheet.gate.may_send_flag`; §8 lets an unconfirmed sheet produce only
    # low/med. It is on the payload rather than joined at render time because the
    # flag itself cannot carry a tier: the judge is handed the sheet as flat
    # "key: value" text and never sees one (see factsheet/gate.py).
    fact_sheet_verification: str | None
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


def _rate_payload(successes: int, n: int, runs_per_query: int, unit: str = "runs") -> RatePayload:
    """Wrap a count into the only shape a rate is allowed to ship in."""
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


def _group_row(g: findings_mod.FindingGroup) -> FindingGroupRow:
    return FindingGroupRow(
        theme=g.theme,
        theme_label=g.theme_label,
        title=g.title,
        severity=g.severity,
        instance_count=g.instance_count,
        engines=g.engines,
        intents=g.intents,
        occurrence=OccurrenceRow(
            observed=g.occurrence.observed,
            total=g.occurrence.total,
            first_seen_date=g.occurrence.first_seen_date,
            last_seen_date=g.occurrence.last_seen_date,
            phrase=g.occurrence.phrase(),
        ),
        representative_claims=g.representative_claims,
        member_cluster_ids=g.member_cluster_ids,
        reality=g.reality,
        evidence=[
            EvidenceRow(
                prompt=e.prompt,
                query_id=e.query_id,
                run_index=e.run_index,
                engine_name=e.engine_name,
                model_id=e.model_id,
                intent=e.intent,
                observed_at=e.observed_at,
                excerpt=e.excerpt,
                reality=e.reality,
            )
            for e in g.evidence
        ],
        evidence_total=g.evidence_total,
        fix_channel=g.fix_channel,
        owner=g.owner,
        effort=g.effort,
        action=g.action,
        verification=g.verification,
        priority=round(g.priority, 4),
        flag_types=g.flag_types,
        # Overwritten by `_with_lifecycle` once the comparable history is known.
        lifecycle_status="new",
        cycles_open=1,
        first_seen_date="",
    )


def _client_engine_counts(
    matrix: list[EngineCellRow], client: str
) -> list[tuple[str, tuple[int, int]]]:
    """(engine, (present, cells)) for the CLIENT only, engine order fixed.

    Sorted so the movement section keeps a memorized column order between
    editions — a section whose layout moves cannot be compared at a glance, which
    is the entire job of a recurring report.
    """
    return sorted(
        (row["engine_name"], (row["present"], row["cells"]))
        for row in matrix
        if row["brand"] == client
    )


def _with_lifecycle(
    groups: list[FindingGroupRow], facts: dict[str, lifecycle.LifecycleFact]
) -> list[FindingGroupRow]:
    """Stamp each card with its status and re-sort worst-news-first.

    REGRESSED outranks a same-severity NEW: a fix that did not hold means the
    recommendation was wrong or the change was reverted, and either way the
    client needs to hear it before a fresh problem.
    """
    stamped: list[FindingGroupRow] = []
    for group in groups:
        fact = facts.get(group["theme"])
        stamped.append(
            {
                **group,
                "lifecycle_status": fact.status if fact else "new",
                "cycles_open": fact.cycles_open if fact else 1,
                "first_seen_date": fact.first_seen_date if fact else "",
            }
        )
    stamped.sort(
        key=lambda g: priority_sort_key(
            g["severity"], g["priority"], g["theme"], g["lifecycle_status"] == "regressed"
        )
    )
    return stamped


def _exec_summary(
    client: str,
    visibility: RatePayload,
    engine_count: int,
    open_findings: OpenFindingsPayload,
    top_action: FindingGroupRow | None,
    comparison_blocked_reason: str,
    accuracy_assessed: bool,
) -> str:
    """The BLUF sentence. Deterministic; assembled from fields, never generated.

    Degrades rather than lies. With no measurement it says so; with no prior run
    it omits the direction rather than implying one; with no findings it says the
    models described the client accurately instead of manufacturing an action.
    """
    if not visibility["n"]:
        return (
            f"{client} could not be measured this cycle — no surface returned an "
            f"answer, so there is no visibility figure and no finding to act on."
        )

    surfaces = f"{engine_count} engine{'s' if engine_count != 1 else ''}"
    first = f"{client} appears in {visibility['label']} across {surfaces}."

    if comparison_blocked_reason == "query_set_changed":
        first += " The query set changed this cycle, so no comparison to the prior cycle is shown."
    elif comparison_blocked_reason == "no_prior_run":
        first += " This is the first cycle, so there is no prior figure to compare against."

    # "Nothing was checked" and "everything checked out" are opposite claims, and
    # zero findings is what BOTH look like from here. Without a fact sheet there
    # is no ground truth to contradict, so the honest sentence names the gap
    # rather than congratulating the client on an audit that never ran.
    if not accuracy_assessed:
        return (
            f"{first} Accuracy was not assessed this cycle — without a fact sheet there is no "
            f"ground truth to check the models' claims about {client} against."
        )

    themes_open = open_findings["themes"]
    if themes_open == 0:
        return f"{first} No findings are open — the models described {client} accurately."

    critical = open_findings["critical"]
    second = (
        f"{themes_open} finding{'s' if themes_open != 1 else ''} "
        f"{'are' if themes_open != 1 else 'is'} open"
    )
    second += f", {critical} of them Critical." if critical else "."

    if top_action is None:
        return f"{first} {second}"
    return (
        f"{first} {second} The highest-leverage fix this cycle is: "
        f"{top_action['action']} (Owner: {top_action['owner']} · Effort: {top_action['effort']})"
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
    fact_sheet_verification: str | None = None,
    prior_run: tuple[str, str] | None = None,
    prior_cycles: Sequence[lifecycle.CycleObservation] = (),
    prior_engine_counts: dict[str, tuple[int, int]] | None = None,
    judge_agreement: str = "",
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

    # --- Is a week-over-week comparison even legitimate? (P2-T1) ---
    # Only compare like instruments. A run is comparable only to a run with the
    # SAME query_set_version; `trend.compare_runs` says validity depends on that
    # and calls it the caller's job. This is the caller doing that job. When the
    # version changed we show NO comparison and say why — never a silent
    # comparison across a changed instrument, which would read as movement in the
    # client's visibility when the only thing that moved was the ruler.
    comparison_blocked_reason = ""
    if prior_run is None:
        comparison_blocked_reason = "no_prior_run"
    elif prior_run[1] != outcome.query_set_version:
        comparison_blocked_reason = "query_set_changed"

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

    # --- Brand x engine matrix (the heatmap's data) ---
    # Counted per (brand, engine) rather than rate-only, because a cell with no
    # answers and a cell where the brand is absent look identical as "0%" and are
    # opposite facts. `cells == 0` renders as "not measured", never as a zero.
    engine_matrix: list[EngineCellRow] = []
    if has_judge:
        for brand in brands:
            per_engine: dict[str, tuple[int, int]] = {}
            for cell in cells_map.get(brand, []):
                present, total = per_engine.get(cell.engine_name, (0, 0))
                per_engine[cell.engine_name] = (present + (1 if cell.present else 0), total + 1)
            for engine_name in engines:
                present, total = per_engine.get(engine_name, (0, 0))
                engine_matrix.append(
                    EngineCellRow(
                        brand=brand,
                        engine_name=engine_name,
                        present=present,
                        cells=total,
                        rate=(present / total if total else 0.0),
                    )
                )

    # --- Findings: identity -> theme -> group -> evidence -> rank (P0-T1/T3, P1-T1/T4) ---
    #
    # Built from the PER-CELL flags, not `judge_metrics.collect_accuracy_flags`,
    # which dedups by (type, claim) for display. Feeding the deduped list here
    # would report every finding as having occurred exactly once, which is the
    # opposite of what the occurrence line is for.
    # The honest denominator for "N of M runs": how many runs of each cell
    # RETURNED AN ANSWER. A cell that errored contributes to neither numerator nor
    # denominator — "not measured" is not "not found".
    runs_by_cell: dict[tuple[str, str], int] = {}
    prompts_by_query: dict[str, str] = {}
    observed_at_by_cell: dict[tuple[str, str, int], str] = {}
    for r in results:
        prompts_by_query.setdefault(r["query_id"], r["prompt"])
        observed_at_by_cell[(r["query_id"], r["engine_name"], r["run_index"])] = r.get(
            "timestamp", ""
        )
        if r["response"] is not None:
            key = (r["query_id"], r["engine_name"])
            runs_by_cell[key] = runs_by_cell.get(key, 0) + 1

    per_cell_flags: list[AccuracyFlag] = []
    if has_judge:
        assert judgments is not None
        for j in judgments:
            if not j.assessed:
                continue
            for f in j.accuracy_flags:
                # WHEN the engine said it. The judgments table has no per-cell
                # timestamp, so on the stored path this is the only place the date
                # can come from — and a finding without one is not shippable.
                # Idempotent: the live path already stamped it identically.
                per_cell_flags.append(
                    f
                    if f.observed_at
                    else replace(
                        f,
                        observed_at=observed_at_by_cell.get(
                            (f.query_id, f.engine_name, f.run_index), ""
                        ),
                    )
                )

    grouping = findings_mod.build_finding_groups(
        per_cell_flags,
        client=client,
        prompts_by_query=prompts_by_query,
        runs_by_cell=runs_by_cell,
        engine_models=outcome.engine_models,
        total_engines=len(engines),
    )
    finding_groups = [_group_row(g) for g in grouping.groups]
    # 3–7 rows: enough to be a plan, few enough to be done before the next cycle.
    # A 40-row "priority" list is a backlog wearing a plan's clothes.
    priority_actions = finding_groups[:7]

    # --- Accuracy flags (judge only) — the appendix / export list ---
    # Identity is READ BACK from the grouping rather than recomputed. Re-running
    # the clustering per flag would mint ids that disagree with the cards, and a
    # CSV whose finding ids don't match the report is worse than no CSV.
    identity_by_claim = grouping.identity_by_claim()
    accuracy_flags: list[FlagRow] = []
    if has_judge:
        for f in judge_flags:
            identity = identity_by_claim.get((f.type, f.claim))
            accuracy_flags.append(
                FlagRow(
                    type=f.type,
                    severity=identity.severity if identity else f.severity,
                    claim=f.claim,
                    reality=f.reality,
                    query_id=f.query_id,
                    engine_name=f.engine_name,
                    intent=f.intent,
                    run_index=f.run_index,
                    observed_at=f.observed_at,
                    cluster_id=identity.cluster_id if identity else "",
                    theme=identity.theme if identity else "",
                )
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
                    prompt=prompts_by_query.get(cell.query_id, ""),
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
                    prompt=prompts_by_query.get(loss.query_id, ""),
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

    # --- The four measured tiles (P1-T6) ---
    #
    # AI visibility as a COUNT with its denominator, never a bare percentage. The
    # numerator is the client's answered cells that mentioned it; the denominator
    # is the answered cells, read off the run rather than from RUNS_PER_QUERY
    # (which defaults to 5 while stored runs vary).
    answered_cells = sum(c.answered_cells for c in engine_coverage.values())
    attempted_cells = sum(c.total_cells for c in engine_coverage.values())
    client_mentions = round(mention_by_brand.get(client, 0.0) * answered_cells)
    ai_visibility = _rate_payload(
        client_mentions, answered_cells, outcome.runs_per_query, unit="sampled answers"
    )

    # Counted in THEMES — one counting unit per client-facing view. `instances` is
    # the observation count and stays secondary; a strip counting instances beside
    # a tile counting themes invites a reader to do the subtraction and catch a
    # contradiction, after which every number on the page is suspect.
    by_severity = {level: 0 for level in SEVERITY_ORDER}
    for row in finding_groups:
        by_severity[row["severity"]] = by_severity.get(row["severity"], 0) + 1
    open_findings = OpenFindingsPayload(
        themes=len(finding_groups),
        critical=by_severity.get("critical", 0),
        instances=grouping.total_instances,
        by_severity=by_severity,
    )

    # --- What changed since last cycle (P2-T2/T4/T5) ---
    #
    # The lifecycle runs over the PRIOR cycles plus this one, filtered by the
    # run-coverage gate and the query set. It is computed fresh from raw flags on
    # every render, so both sides of the diff are always classified with the same
    # theme rules — which is why a rule change cannot manufacture a resolve.
    this_cycle = lifecycle.CycleObservation(
        run=lifecycle.RunMeta(
            run_id=outcome.run_id or "",
            run_date=run_date,
            status="done",
            # The gate that stops a half-measured run being read as findings
            # disappearing. Computed from this run's own cells rather than taken
            # on trust — a run reporting itself complete is not evidence that it is.
            coverage_ratio=(answered_cells / attempted_cells if attempted_cells else 0.0),
            query_set_version=outcome.query_set_version,
        ),
        themes=frozenset(row["theme"] for row in finding_groups),
    )
    comparable = lifecycle.comparable_cycles(
        [*prior_cycles, this_cycle], outcome.query_set_version
    )
    facts = lifecycle.compute_lifecycle(comparable)
    account = lifecycle.accountability(comparable)

    # Per-surface movement, gated. Flat cells are INCLUDED — both because "flat"
    # is a claim the report must make, and because the FDR correction needs every
    # comparison performed in its family or it silently corrects nothing.
    movements: list[MovementRow] = []
    if len(comparable) > 1 and prior_engine_counts:
        raw = [
            movement.compare_cell(
                key=engine,
                before_successes=prior_engine_counts.get(engine, (0, 0))[0],
                before_n=prior_engine_counts.get(engine, (0, 0))[1],
                after_successes=present,
                after_n=cells,
                runs_per_query=outcome.runs_per_query,
            )
            for engine, (present, cells) in sorted(_client_engine_counts(engine_matrix, client))
        ]
        movements = [
            MovementRow(
                key=m.key,
                before_successes=m.before_successes,
                before_n=m.before_n,
                after_successes=m.after_successes,
                after_n=m.after_n,
                delta_pp=round(m.delta_pp, 1),
                direction=m.direction,
                phrase=m.phrase(),
                flat_reason=m.flat_reason,
            )
            for m in movement.gate_movements(raw)
        ]

    what_changed = WhatChangedPayload(
        available=len(comparable) > 1 and not comparison_blocked_reason,
        accountability=account.sentence(),
        opening=account.opening,
        resolved=account.resolved,
        still_open=account.still_open,
        new=account.new,
        regressed=account.regressed,
        closing=account.closing,
        resolved_all_time=account.resolved_all_time,
        cycles_considered=account.cycles_considered,
        movements=movements,
        prior_run_date=comparable[-2].run.run_date if len(comparable) > 1 else "",
    )
    # Attach each theme's lifecycle status to its card, and re-sort so a
    # REGRESSED finding outranks a same-severity NEW one: a fix that did not hold
    # is worse news than a fresh problem.
    finding_groups = _with_lifecycle(finding_groups, facts)
    priority_actions = finding_groups[:7]

    exec_summary = _exec_summary(
        client=client,
        visibility=ai_visibility,
        engine_count=len(engines),
        open_findings=open_findings,
        top_action=priority_actions[0] if priority_actions else None,
        comparison_blocked_reason=comparison_blocked_reason,
        accuracy_assessed=accuracy_assessed,
    )

    scorecard = ScorecardPayload(
        visibility_grade=grade_payload,
        ai_visibility=ai_visibility,
        open_findings=open_findings,
        # Needs `first_seen` from the lifecycle engine (P2-T2). Until that lands
        # the tile renders "—": an age we cannot compute is not an age we may
        # guess, and storage is create-only so the history is already there to
        # compute it from once the engine exists.
        oldest_open=None,
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
        answered_cells=answered_cells,
        attempted_cells=attempted_cells,
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
        engine_matrix=engine_matrix,
        exec_summary=exec_summary,
        what_changed=what_changed,
        theme_rules_version=themes_mod.rules_fingerprint(),
        finding_groups=finding_groups,
        priority_actions=priority_actions,
        theme_coverage={
            "total": float(grouping.coverage.total),
            "by_rule": float(grouping.coverage.by_rule),
            "by_type_default": float(grouping.coverage.by_type_default),
            "unclassified": float(grouping.coverage.unclassified),
            "unclassified_rate": grouping.coverage.unclassified_rate,
            "type_default_rate": grouping.coverage.type_default_rate,
        },
        comparison_blocked_reason=comparison_blocked_reason,
        methodology_disclosure=NON_REPRODUCIBILITY_DISCLOSURE,
        independence_disclaimer=INDEPENDENCE_DISCLAIMER,
        # Publish what IS measured. Saying "unmeasured" while holding 94% on 240
        # brand judgements understates the work; quoting a 43% flag precision off
        # 7 flags overstates it. `AgreementSummary.sentence` splits the two and
        # carries every denominator.
        judge_agreement=(
            judge_agreement
            or (summary.sentence() if (summary := load_agreement_summary(client)) else "")
            or JUDGE_AGREEMENT_UNMEASURED
        ),
        accuracy_flags=accuracy_flags,
        fact_sheet_verification=fact_sheet_verification,
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
