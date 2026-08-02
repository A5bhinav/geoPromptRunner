from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.api.engine_registry import build_engines
from src.api.reports import (
    LocalPackPayload,
    ReportPayload,
    SiteAuditPayload,
    build_local_pack_payload,
    build_report,
)
from src.audit.factsheet import FactSheet, expected_fact_sheet_text
from src.config import settings
from src.engines.base import BaseEngine
from src.engines.local_pack import LocalEntity, LocalPackCapture
from src.pipeline import judge_metrics, lifecycle, metrics, preflight, themes
from src.pipeline.answers_export import build_answers_markdown, build_results_csv
from src.pipeline.cost import CostBudgetExceeded, estimate_total_cost_for_queries
from src.pipeline.engine_routing import routed_totals_by_name
from src.pipeline.orchestrator import AuditOutcome, engine_models
from src.pipeline.prompt_runner import run_query_set
from src.prompts.csv_loader import ParsedAudit, RunConfig
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet
from src.storage import db
from src.storage.models import AnswerJudgment, QueryResult

__all__ = [
    "EngineStatus",
    "RunStatus",
    "RunSummary",
    "start_run",
    "get_status",
    "get_report",
    "get_answers",
    "list_runs",
    "request_cancel",
    "resume_interrupted_runs",
]

logger = logging.getLogger(__name__)

# How many completed cells to buffer before a storage write + progress snapshot.
# Batched so a fully-parallel run doesn't hammer the DB once per call, while
# still persisting often enough that a crash loses little and resume is cheap.
_PERSIST_BATCH = 15


@dataclass
class _RunState:
    """Mutable in-memory state for one audit run.

    The API serves status and the report straight from here, so the UI works
    end to end whether or not Supabase is reachable. Persistence (when
    configured) is best-effort and never blocks the run.
    """

    run_id: str
    audit: ParsedAudit
    created_at: str
    total_calls: int
    state: str = "queued"  # queued | running | done | failed | cancelled
    completed_calls: int = 0
    error: str | None = None
    db_run_id: str | None = None
    # The APPROVED fact sheet this run was judged against, if one was attached.
    # `fact_sheet_verification` is the sheet's WEAKEST claim tier and is what gates
    # whether a flag may appear in anything sent to a prospect (factsheet/gate.py).
    # Carried on the state because the live report path has no DB row to read it
    # from, and `build_report` defaulting it to None silently suppressed every
    # accuracy finding on every real run.
    fact_sheet_id: str | None = None
    fact_sheet_version: int | None = None
    fact_sheet_verification: str | None = None
    results: list[QueryResult] = field(default_factory=list)
    judgments: list[AnswerJudgment] = field(default_factory=list)
    site_audit: SiteAuditPayload | None = None
    engine_completed: dict[str, int] = field(default_factory=dict)
    # Calls that came back with an actual answer, per engine. Tracked SEPARATELY from
    # engine_completed because a failed call still completes: run e186c524 reported
    # `openai_search 10/10` while that surface answered nothing at all (404 model).
    # Attempts alone cannot distinguish a working engine from a dead one.
    engine_answered: dict[str, int] = field(default_factory=dict)
    # What the preflight probe saw, per engine — persisted so a report can explain
    # WHY a surface is missing from the run rather than silently omitting it.
    engine_probe: dict[str, object] = field(default_factory=dict)
    # Google local-pack captures for the local-intent queries. Kept OUT of `results`
    # deliberately: a ranked business list is not an answer, and mixing it in would
    # feed it to the judge and to mention_rate (src/engines/local_pack.py).
    local_pack: list[LocalPackCapture] = field(default_factory=list)
    active_engines: list[str] = field(default_factory=list)
    # engine name -> the exact model string it sent, captured once the engines are
    # built. Every client-facing finding names the model that produced it, and
    # after a repin, re-deriving the pin at render time would attribute a months-
    # old answer to a model that never saw the question.
    engine_models: dict[str, str] = field(default_factory=dict)
    skipped_engines: list[tuple[str, str]] = field(default_factory=list)
    cancel_requested: bool = False


_RUNS: dict[str, _RunState] = {}
_LOCK = threading.Lock()

# Once a run is "done" its report is rebuilt from 3 Supabase round-trips + full
# aggregation on every re-fetch (and after a restart). Cache the built
# ReportPayload for done runs. A done run's report is stable EXCEPT when it is
# re-judged on demand (``rejudge_run``), which mutates the verdicts — so that path
# must invalidate this cache (``_invalidate_report_cache``). Resumes only touch
# interrupted/queued runs, never done ones, so they need no invalidation.
_REPORT_CACHE: dict[str, ReportPayload] = {}
_REPORT_CACHE_LOCK = threading.Lock()


def _invalidate_report_cache(run_id: str) -> None:
    """Drop a run's cached report so the next fetch rebuilds it (used after a
    re-judge changes a done run's verdicts)."""
    with _REPORT_CACHE_LOCK:
        _REPORT_CACHE.pop(run_id, None)


# Running total of estimated USD spend for audits accepted this process. The hard
# guard against burning credits: a single audit over MAX_AUDIT_COST_USD, or one
# that would push this total past MAX_TOTAL_SPEND_USD, is refused before any LLM
# call. Resets on restart (rough budgeting, not billing).
_spend_lock = threading.Lock()
_estimated_spend_usd = 0.0


def _reserve_budget(estimated_usd: float) -> None:
    """Charge ``estimated_usd`` against the spend caps or raise CostBudgetExceeded.

    Checked before a run starts. The per-audit cap rejects one oversized audit;
    the cumulative cap rejects once the process's accepted spend would exceed the
    ceiling. Either cap set to 0 disables it.
    """
    global _estimated_spend_usd
    audit_cap = settings.MAX_AUDIT_COST_USD
    total_cap = settings.MAX_TOTAL_SPEND_USD
    if audit_cap > 0 and estimated_usd > audit_cap:
        raise CostBudgetExceeded(
            f"estimated ${estimated_usd:.2f} exceeds the per-audit cap of ${audit_cap:.2f}"
        )
    with _spend_lock:
        if total_cap > 0 and _estimated_spend_usd + estimated_usd > total_cap:
            raise CostBudgetExceeded(
                f"estimated ${estimated_usd:.2f} would exceed the remaining budget "
                f"(${max(0.0, total_cap - _estimated_spend_usd):.2f} of ${total_cap:.2f} left)"
            )
        _estimated_spend_usd += estimated_usd


# --- Public status / summary types (plain dicts for JSON serialization) ------


@dataclass(frozen=True)
class EngineStatus:
    name: str
    state: str  # running | done | failed
    completed: int
    total: int
    detail: str | None = None
    # Of `completed` calls, how many returned an answer. Defaulted so existing
    # consumers (web/lib/api.ts) keep parsing. `completed > 0 and answered == 0` on a
    # terminal run means the surface produced no measurement at all.
    answered: int = 0


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    client_name: str
    state: str
    completed: int
    total: int
    per_engine: list[EngineStatus]
    error: str | None
    # Parallel site-audit progress (additive — existing consumers ignore these).
    # None when no domain was given / the audit wasn't requested for this run.
    site_audit_state: str | None = None  # running | done | failed
    site_audit_pages: int = 0


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    client_name: str
    state: str
    created_at: str
    n_queries: int
    engines: list[str]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _serialize_queries(queries: list[Query]) -> list[dict[str, object]]:
    """Persistable form of the locked query set (so a run can be rebuilt)."""
    return [
        {
            "query_id": q.query_id,
            "text": q.text,
            "intent": q.intent.value,
            "persona": q.persona,
            "weight": q.weight,
        }
        for q in queries
    ]


def _outcome(state: _RunState) -> AuditOutcome:
    cfg = state.audit.config
    return AuditOutcome(
        run_id=state.db_run_id,
        client_name=cfg.client_name,
        client_domains=cfg.client_domains,
        competitors=cfg.competitors,
        query_set_version=state.audit.query_set.version,
        runs_per_query=cfg.runs_per_query,
        results=list(state.results),
        engine_models=dict(state.engine_models),
    )


class FactSheetNotUsable(Exception):
    """An attached fact sheet cannot serve as a run's ground truth. Carries why."""


def _sheet_text(sheet: FactSheet) -> str:
    """The sheet as the flat text the judge is handed (`_build_fact_sheet`'s shape).

    `expected_fact_sheet_text` is the oracle for exactly that, so the run row stores
    the same bytes the judge will reason over rather than a second rendering of the
    same claims.
    """
    return expected_fact_sheet_text(sheet)


def _attach_fact_sheet(audit: ParsedAudit, fact_sheet_id: str | None) -> FactSheet | None:
    """Load the approved sheet a run was submitted against, or None.

    Three refusals, each because the alternative is a run judged against a document
    nobody vouched for:

    * **Unknown id** — better a 404 than silently running with no ground truth,
      which produces a report with no accuracy findings and no indication why.
    * **Not ACTIVE** — approval IS the gate (F4). Attaching a draft would route
      around the only human review in the pipeline, and rejecting one would resurrect
      a sheet a reviewer turned down.
    * **A sheet AND CSV fact rows** — two ground truths for one run. §4.3 says
      disagreement becomes a question, never a silent winner; here the honest move is
      to refuse rather than pick.
    """
    if fact_sheet_id is None:
        return None
    if audit.fact_sheet is not None:
        raise FactSheetNotUsable(
            "this upload carries `fact` rows AND a fact_sheet_id. Two sources of "
            "ground truth for one run — remove the fact rows, or submit without the "
            "sheet id."
        )
    try:
        sheet = db.get_fact_sheet(fact_sheet_id)
    except db.StorageError as exc:
        raise FactSheetNotUsable(f"could not load fact sheet {fact_sheet_id}: {exc}") from exc
    if sheet is None:
        raise FactSheetNotUsable(f"fact sheet {fact_sheet_id} not found")
    state = _sheet_state(fact_sheet_id)
    if state != db.FactSheetState.ACTIVE.value:
        raise FactSheetNotUsable(
            f"fact sheet {fact_sheet_id} is '{state}', not active. Approve it first — "
            "approval is what makes a sheet the reference accuracy is measured against."
        )
    if not sheet.claims:
        raise FactSheetNotUsable(
            f"fact sheet {fact_sheet_id} has no claims; a sheet asserting nothing "
            "cannot be contradicted, so no accuracy finding could ever be graded"
        )
    return sheet


def _sheet_state(sheet_id: str) -> str:
    """The stored lifecycle state of one sheet ('' when unreadable)."""
    for row in db.list_fact_sheets():
        if str(row.get("id")) == sheet_id:
            return str(row.get("state") or "")
    return ""


def start_run(audit: ParsedAudit, fact_sheet_id: str | None = None) -> str:
    """Register a run and kick it off on a background thread. Returns the run id.

    The run id is generated here and used as *both* the in-memory key and the
    stored ``audit_runs`` row id, so a finished run can be read back from storage
    by the same id the UI is polling — even after the API restarts.

    ``fact_sheet_id`` attaches an APPROVED sheet as this run's ground truth. Before
    it existed, `load_fact_sheet` had no caller anywhere and approving a sheet
    changed one column and nothing else — the review queue's own promise, that
    approval makes a sheet "the reference every accuracy finding is measured
    against", was not true of any code path.
    """
    cfg = audit.config
    run_id = str(uuid.uuid4())
    sheet = _attach_fact_sheet(audit, fact_sheet_id)
    # Cost/total are estimated against the engines that will actually build, so
    # the progress denominator matches what runs (a missing key drops calls).
    engines, skipped = build_engines(
        cfg.engines, cfg.client_name, cfg.competitors, location=cfg.location
    )
    # Routing-aware, and it counts the liveness probe: both are real effects on what
    # this run will spend, and the budget guard below refuses on this number.
    estimated, total_calls = estimate_total_cost_for_queries(
        audit.query_set.queries,
        engines,
        cfg.runs_per_query,
        cfg.judge,
        preflight=settings.ENGINE_PREFLIGHT,
        # A client domain means the site audit runs, which means the Cat 6 offsite
        # agent spends — previously invisible to the budget guard.
        offsite=bool(cfg.client_domains),
    )
    # Refuse before spending anything if this would blow the per-audit or
    # cumulative budget (raises CostBudgetExceeded → 402 at the API layer).
    _reserve_budget(estimated)
    state = _RunState(
        run_id=run_id,
        audit=audit,
        created_at=_now(),
        total_calls=total_calls,
        active_engines=[e.ENGINE_NAME for e in engines],
        skipped_engines=skipped,
        engine_completed={e.ENGINE_NAME: 0 for e in engines},
        fact_sheet_id=fact_sheet_id if sheet is not None else None,
        fact_sheet_version=sheet.version if sheet is not None else None,
        fact_sheet_verification=(sheet.verification_tier.value if sheet is not None else None),
    )

    # Best-effort: open the durable row up front, sharing run_id, so progress is
    # persisted from the start. If Supabase isn't reachable, run in-memory only.
    qs = audit.query_set
    try:
        db.create_audit_run(
            client_name=cfg.client_name,
            client_domains=cfg.client_domains,
            competitors=cfg.competitors,
            category=cfg.category,
            query_set_version=qs.version,
            query_set_locked_at=qs.locked_at,
            runs_per_query=cfg.runs_per_query,
            run_id=run_id,
            status="running",
            total_calls=total_calls,
            engines=[e.ENGINE_NAME for e in engines],
            n_queries=len(qs.queries),
            fact_sheet_present=(audit.fact_sheet is not None or sheet is not None),
            queries=_serialize_queries(qs.queries),
            fact_sheet=(_sheet_text(sheet) if sheet is not None else audit.fact_sheet),
            fact_sheet_id=(fact_sheet_id if sheet is not None else None),
            fact_sheet_version=(sheet.version if sheet is not None else None),
            judge=cfg.judge,
            location=cfg.location,
            engine_models=engine_models(engines),
        )
        state.db_run_id = run_id
    except db.StorageError as exc:
        logger.info("Storage unavailable, running in-memory only: %s", exc)
        state.db_run_id = None

    with _LOCK:
        _RUNS[run_id] = state

    thread = threading.Thread(
        target=_execute_run, args=(state, engines), name=f"audit-{run_id[:8]}", daemon=True
    )
    thread.start()
    return run_id


def _verification_for_run(row: dict[str, Any]) -> str | None:
    """The weakest claim tier of the sheet this run was judged against, or None.

    Resolved from the run's OWN `fact_sheet_id`, never from whichever sheet happens
    to be active for the domain now. A run is judged against a snapshot; attributing
    today's tier to yesterday's verdicts is the provenance laundering §8 exists to
    prevent, and it would silently upgrade what a flag is allowed to say.

    None when the run predates the pointer or carried a hand-uploaded CSV sheet —
    and None correctly suppresses every accuracy finding downstream, because a flag
    with no vouched-for source is exactly the one not to send.
    """
    sheet_id = row.get("fact_sheet_id")
    if not sheet_id:
        return None
    try:
        sheet = db.get_fact_sheet(str(sheet_id))
    except db.StorageError:
        return None
    return sheet.verification_tier.value if sheet is not None else None


def _persist_state(state: _RunState, error: str | None = None) -> None:
    """Best-effort: mirror the run's progress/state to storage. Never raises."""
    if state.db_run_id is None:
        return
    try:
        db.update_audit_run_progress(state.db_run_id, state.completed_calls, state.state, error)
    except db.StorageError as exc:
        logger.info("Failed to persist run progress (continuing): %s", exc)


def _execute_run(state: _RunState, engines: list[BaseEngine]) -> None:
    cfg = state.audit.config
    if not engines:
        state.state = "failed"
        state.error = (
            "no engines could be started — check API keys, or use engines=mock to demo without keys"
        )
        _persist_state(state, state.error)
        return

    state.state = "running"

    # Preflight: prove each surface can answer before spending the fan-out on it. A
    # dead engine is moved into skipped_engines, so it writes no rows at all and the
    # run's coverage reflects only surfaces that were actually measurable. Runs here
    # rather than in start_run so the probe never blocks the HTTP response.
    if settings.ENGINE_PREFLIGHT:
        live, dead, probe_record = preflight.split_by_liveness(engines)
        state.engine_probe = probe_record
        if state.db_run_id is not None:
            try:
                db.save_engine_probe(state.db_run_id, probe_record)
            except db.StorageError as exc:
                logger.info("Failed to persist the engine probe (continuing): %s", exc)
        if dead:
            dead_names = {name for name, _ in dead}
            state.skipped_engines.extend(dead)
            state.active_engines = [n for n in state.active_engines if n not in dead_names]
            for name in dead_names:
                state.engine_completed.pop(name, None)
            engines = live
        _persist_state(state)
        if not engines:
            state.state = "failed"
            state.error = (
                "every engine failed its liveness probe — no surface could answer a test query "
                "(check model pins and API keys)"
            )
            _persist_state(state, state.error)
            return

    # Record which model each SURVIVING engine will send, after preflight has
    # dropped the dead ones. Captured here rather than re-derived at render time:
    # a repin between the run and the report would otherwise attribute a stored
    # answer to a model that never saw the question, on every finding.
    state.engine_models = engine_models(engines)

    qs = state.audit.query_set

    # Site audit (Cat 1–5 on-site checks) runs concurrently with the engine
    # fan-out — the scrape doesn't need the answers and vice versa (plan §6), so
    # "linear for the user" isn't "slower under the hood". Best-effort: it writes
    # to state.site_audit and is joined before the report; a crawl failure never
    # touches the engine phase or the run's terminal state.
    site_thread: threading.Thread | None = None
    if cfg.client_domains:
        site_thread = threading.Thread(
            target=_run_site_audit_phase,
            args=(state,),
            name=f"siteaudit-{state.run_id[:8]}",
            daemon=True,
        )
        site_thread.start()

    # Local-pack capture rides alongside for the same reason: it is a SERP read that
    # doesn't need the engine answers. Only starts when a location is pinned.
    local_thread: threading.Thread | None = None
    if (cfg.location or "").strip():
        local_thread = threading.Thread(
            target=_run_local_pack_phase,
            args=(state,),
            name=f"localpack-{state.run_id[:8]}",
            daemon=True,
        )
        local_thread.start()

    # Resume support: any cells already persisted for this run are reloaded and
    # skipped at (query_id, engine, run_index) granularity, so an interrupted
    # run continues exactly where it stopped — including filling in an engine
    # that wasn't available last time or completing a query a crash left
    # half-finished. (Empty for a fresh run.)
    done_cells: set[tuple[str, str, int]] = set()
    if state.db_run_id is not None:
        try:
            prior = db.get_query_results(state.db_run_id)
        except db.StorageError:
            prior = []
        if prior:
            state.results.extend(prior)
            state.completed_calls = len(prior)
            done_cells = {(r["query_id"], r["engine_name"], r["run_index"]) for r in prior}
            for r in prior:
                state.engine_completed[r["engine_name"]] = (
                    state.engine_completed.get(r["engine_name"], 0) + 1
                )
                # Rebuild the answered count too, or a resumed run forgets which
                # surfaces were producing and reports every prior cell as answered.
                if r["response"] is not None:
                    state.engine_answered[r["engine_name"]] = (
                        state.engine_answered.get(r["engine_name"], 0) + 1
                    )

    try:
        # The whole query set runs as one concurrent fan-out (every
        # query/engine/run cell in flight at once, bounded by the pool), instead
        # of one query at a time. Results stream back via ``on_result`` — called
        # serialized, so no extra locking — where we update progress and persist
        # in batches. ``should_cancel`` lets a cancel stop issuing new calls
        # promptly; cells already done are skipped via ``done_cells``.
        pending: list[QueryResult] = []

        def flush() -> None:
            if not pending:
                return
            if state.db_run_id is not None:
                try:
                    db.save_query_results(state.db_run_id, pending)
                except db.StorageError as exc:
                    # Keep the batch and retry on the next flush rather than
                    # dropping it — clearing here would lose those answers from
                    # storage while completed_calls had already counted them,
                    # leaving the persisted progress ahead of the actual rows.
                    logger.info("Failed to persist a batch (will retry next flush): %s", exc)
                    return
            pending.clear()
            _persist_state(state)

        def on_result(r: QueryResult) -> None:
            state.results.append(r)
            state.completed_calls += 1
            state.engine_completed[r["engine_name"]] = (
                state.engine_completed.get(r["engine_name"], 0) + 1
            )
            if r["response"] is not None:
                state.engine_answered[r["engine_name"]] = (
                    state.engine_answered.get(r["engine_name"], 0) + 1
                )
            pending.append(r)
            if len(pending) >= _PERSIST_BATCH:
                flush()

        run_query_set(
            qs.queries,
            engines,
            cfg.runs_per_query,
            done_cells=done_cells,
            on_result=on_result,
            should_cancel=lambda: state.cancel_requested,
        )
        flush()  # persist whatever didn't fill a final batch

        if state.cancel_requested:
            _join_phases(site_thread, local_thread)
            state.state = "cancelled"
            _persist_state(state)
            return

        if cfg.judge:
            _run_judge(state)

        # Wait for the concurrent phases so the report includes them.
        _join_phases(site_thread, local_thread)
        state.state = "done"
        _persist_state(state)
    except Exception as exc:  # defensive: a run thread must never die silently
        # Log the real type server-side; surface only a generic message to the
        # client so internal details aren't disclosed.
        logger.warning("Run %s failed: %s", state.run_id, type(exc).__name__)
        _join_phases(site_thread, local_thread, timeout=30.0)
        state.state = "failed"
        state.error = "run failed (see server logs)"
        _persist_state(state, state.error)


def _join_phases(*threads: threading.Thread | None, timeout: float | None = None) -> None:
    """Join the concurrent best-effort phases (site audit, local-pack capture).

    Variadic so adding a phase means passing one more thread rather than remembering to
    join it at each of the three exit paths (done / cancelled / failed). A phase that is
    still running when the timeout expires is simply absent from the report — it is
    additive by construction and never blocks the run's terminal state.
    """
    for thread in threads:
        if thread is not None:
            thread.join(timeout)


def _run_site_audit_phase(state: _RunState) -> None:
    """Crawl the client domain and run the on-site checks (best-effort, never raises).

    Writes the result to ``state.site_audit``. Imported lazily so the crawl deps
    (Playwright/trafilatura/extruct) aren't pulled into the API import path, and
    so a missing crawl dependency degrades to "no site audit" rather than breaking
    the run — exactly the pattern ``_run_judge`` uses.
    """
    cfg = state.audit.config
    domain = cfg.client_domains[0]
    try:
        from src.audit.site_audit import run_site_audit

        # A stored location is what marks a run local, and it selects the Cat 6 fork:
        # which directories get probed (Yelp/GBP/BBB/Angi vs Trustpilot/app stores) and
        # which research brief the agent runs. Without it a plumber gets audited for its
        # App Store presence.
        location = (cfg.location or "").strip() or None
        state.site_audit = run_site_audit(
            state.run_id,
            domain,
            brand=cfg.client_name,
            competitors=cfg.competitors,
            persist=state.db_run_id is not None,
            business_kind="local_service" if location else "product",
            location=location,
        )
    except Exception as exc:  # phase is additive — its failure never fails the run
        logger.warning("Site audit failed for run %s: %s", state.run_id, type(exc).__name__)


def _run_local_pack_phase(state: _RunState) -> None:
    """Capture Google's local pack for this run's local-intent queries.

    Runs concurrently with the engine fan-out and the site audit, and is best-effort in
    exactly the same way: a failure here writes nothing and never touches the run's
    terminal state.

    Only fires when a location is pinned — ``fetch_local_pack`` refuses an unpinned
    market, because a pack from the wrong metro is worse than no pack. Each query is
    captured **once**, not ``runs_per_query`` times: a SERP listing has no LLM sampling
    noise to average out, so repeats would just multiply the vendor bill.

    This is the surface ``engine_routing`` stops asking AI Overviews about — Google shows
    a local pack for ~93% of local-intent queries and an Overview for ~15% — so without
    this phase those queries would be measured by nothing at all.
    """
    cfg = state.audit.config
    location = (cfg.location or "").strip()
    if not location:
        return
    local_queries = [
        q for q in state.audit.query_set.queries if q.intent is IntentBucket.LOCAL_INTENT
    ]
    if not local_queries:
        return
    try:
        from src.engines.local_pack import fetch_local_pack

        captures: list[LocalPackCapture] = []
        for query in local_queries:
            if state.cancel_requested:
                break
            entities, source = fetch_local_pack(query.text, location)
            if not entities:
                continue
            captures.append(
                LocalPackCapture(
                    query_id=query.query_id,
                    prompt=query.text,
                    source=source,
                    entities=entities,
                )
            )
        state.local_pack = captures
        if captures and state.db_run_id is not None:
            db.save_local_pack_entities(state.db_run_id, captures)
    except Exception as exc:  # phase is additive — its failure never fails the run
        logger.warning(
            "Local-pack capture failed for run %s: %s", state.run_id, type(exc).__name__
        )


def _judge_answers(
    results: list[QueryResult],
    client: str,
    competitors: list[str],
    fact_sheet: str | None,
) -> tuple[list[AnswerJudgment], str] | None:
    """Judge a set of answers through the persistent verdict cache.

    Returns ``(judgments, judge identity)``, or ``None`` if the judge can't be built
    (no API key). The identity travels with the verdicts so the caller can record WHO
    judged this run — see ``db.save_judgments``.
    Shared by the inline post-run judge and the on-demand re-judge. The cache
    means an answer already judged under these exact inputs (model, client,
    competitors, fact sheet, prompt) is reused, not re-judged — so a re-judge over
    a run whose verdicts were pre-filled on the subscription costs $0 (see
    docs/subscription-judge-plan.md). Judge/JudgeCache are imported lazily so the
    anthropic SDK isn't pulled into the API import path.
    """
    from src.pipeline.judge import Judge
    from src.pipeline.judge_cache import make_judge_cache

    try:
        judge = Judge(cascade=settings.JUDGE_CASCADE, verify=settings.JUDGE_VERIFY)
    except ValueError as exc:
        logger.info("Judge skipped: %s", exc)
        return None
    cache = make_judge_cache()
    try:
        return (
            judge.judge_results(results, client, competitors, fact_sheet, cache=cache),
            judge.identity,
        )
    finally:
        cache.close()


def _run_judge(state: _RunState) -> None:
    """Best-effort LLM judging after the answers are collected.

    Skipped (not fatal) if the judge can't be built (no API key).
    """
    cfg = state.audit.config
    judged = _judge_answers(
        state.results, cfg.client_name, cfg.competitors, state.audit.fact_sheet
    )
    if judged is None:
        return
    judgments, judge_identity = judged
    state.judgments = judgments
    if state.db_run_id is not None:
        try:
            db.save_judgments(state.db_run_id, state.judgments, judge_identity)
        except db.StorageError as exc:
            logger.info("Failed to persist judgments (continuing): %s", exc)


def judge_status(run_id: str) -> dict[str, object]:
    """Warm-status of the notebooks for a run: how many query answers and on-site
    content checks are already cached, so the UI can tell whether Judge / the report
    is free (all warm) or will still hit the API. Pure cache reads — never judges."""
    from src.audit.checks.content_judge import (
        _MAX_TEXT_CHARS,
        CONTENT_CHECKS,
        content_cache_key,
    )
    from src.audit.checks.content_judge_cache import make_content_judge_cache
    from src.pipeline.judge import Judge
    from src.pipeline.judge_cache import make_judge_cache

    run = db.get_audit_run(run_id) or {}
    client = str(run.get("client_name", ""))
    raw_comps = run.get("competitors") or []
    competitors = [str(c) for c in raw_comps] if isinstance(raw_comps, list) else []
    fact_sheet = str(run["fact_sheet"]) if run.get("fact_sheet") else None

    # Query notebook: unique (prompt, answer) pairs → keys → cache membership.
    q_total = q_cached = 0
    try:
        judge: Judge | None = Judge()
    except ValueError:
        judge = None
    if judge is not None:
        cache = make_judge_cache()
        try:
            seen: set[tuple[str, str]] = set()
            keys: list[str] = []
            for r in db.get_query_results(run_id):
                ans = r["response"]
                if ans is None or (r["prompt"], ans) in seen:
                    continue
                seen.add((r["prompt"], ans))
                keys.append(
                    cache.key(
                        model=judge._cache_model_id,
                        prompt_fingerprint=judge._prompt_fingerprint,
                        client=client,
                        competitors=competitors,
                        fact_sheet=fact_sheet,
                        prompt=r["prompt"],
                        answer=ans,
                    )
                )
            q_total = len(keys)
            q_cached = len(cache.get_many(keys)) if keys else 0
        finally:
            cache.close()

    # Content notebook: (crawled page × check) keys.
    ckeys: list[str] = []
    for row in db.get_site_audit_pages(run_id):
        text = row.get("extracted_text")
        if not text:
            continue
        capped = str(text)[:_MAX_TEXT_CHARS]
        ckeys += [content_cache_key(settings.JUDGE_MODEL, chk, capped) for chk in CONTENT_CHECKS]
    c_cached = len(make_content_judge_cache().get_many(ckeys)) if ckeys else 0

    def _block(total: int, cached: int) -> dict[str, object]:
        return {"total": total, "cached": cached, "warm": total > 0 and cached >= total}

    return {"query": _block(q_total, q_cached), "content": _block(len(ckeys), c_cached)}


def rejudge_run(run_id: str) -> ReportPayload | None:
    """Re-judge a completed run's stored answers and return its refreshed report.

    The on-demand counterpart to the inline post-run judge: pair it with the
    subscription pre-judge workflow (``/prejudge`` in Claude Code) so that, once
    ``data/judge_cache.sqlite`` is warm, this pass is all cache hits and the UI
    gets judged metrics for $0. Works whether the run is still in this process's
    memory or only in storage (e.g. after a restart). Returns ``None`` if the run
    is unknown or has no answers to judge.
    """
    state = _get(run_id)
    if state is not None:
        if not state.results:
            return None
        _run_judge(state)  # updates state.judgments + persists
        _invalidate_report_cache(run_id)
        return get_report(run_id)
    return _rejudge_from_db(run_id)


def _rejudge_from_db(run_id: str) -> ReportPayload | None:
    """Re-judge a run that isn't in this process's memory, straight from storage."""
    try:
        row = db.get_audit_run(run_id)
        if row is None:
            return None
        results = db.get_query_results(run_id)
    except db.StorageError:
        return None
    if not results:
        return None
    # The fact sheet stored on the run row is what the original run judged against
    # — use it so re-judge verdicts match (and hit) the pre-filled cache keys.
    stored_sheet = row.get("fact_sheet")
    fact_sheet = str(stored_sheet) if stored_sheet else None
    judged = _judge_answers(
        results, str(row.get("client_name", "")), _str_list(row.get("competitors")), fact_sheet
    )
    if judged is not None:
        try:
            db.save_judgments(run_id, judged[0], judged[1])
        except db.StorageError as exc:
            logger.info("Failed to persist judgments (continuing): %s", exc)
    _invalidate_report_cache(run_id)
    return _report_from_db(run_id)


def _get(run_id: str) -> _RunState | None:
    with _LOCK:
        return _RUNS.get(run_id)


def _str_list(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _outcome_from_row(row: dict[str, object], results: list[QueryResult]) -> AuditOutcome:
    raw_models = row.get("engine_models")
    return AuditOutcome(
        run_id=str(row.get("id", "")),
        client_name=str(row.get("client_name", "")),
        client_domains=_str_list(row.get("client_domains")),
        competitors=_str_list(row.get("competitors")),
        query_set_version=str(row.get("query_set_version", "")),
        runs_per_query=int(str(row.get("runs_per_query") or 1)),
        results=results,
        # Which model actually answered, as recorded at run time. Re-deriving the
        # pin here would name whatever is pinned TODAY — after a repin that is a
        # false attribution on every finding in a months-old run.
        engine_models=(
            {str(k): str(v) for k, v in raw_models.items()} if isinstance(raw_models, dict) else {}
        ),
    )


#: How many earlier cycles the lifecycle looks back over.
#:
#: The state machine itself is unbounded, but each cycle costs two Supabase reads
#: to reconstruct its theme set, so the window is capped and the report SAYS how
#: many cycles it considered rather than implying "since we started" over a
#: silently truncated history.
_LIFECYCLE_LOOKBACK_CYCLES = 12


def _cycle_history(
    run_id: str, client_name: str, created_at: str, query_set_version: str
) -> tuple[list[lifecycle.CycleObservation], dict[str, tuple[int, int]]]:
    """Rebuild the prior cycles' theme sets and the previous cycle's engine counts.

    Returns ``([] , {})`` on any storage problem — a report that renders without a
    comparison is degraded; one that fails to render is broken.

    Superseded runs are excluded: a run a correction replaced is the broken first
    attempt at a cycle, not a cycle. Comparing against it reports the repair as
    client progress.
    """
    try:
        runs = db.list_audit_runs(client_name)
        superseded = db.superseded_run_ids(client_name)
    except db.StorageError:
        return [], {}

    earlier = [
        r
        for r in runs
        if str(r.get("id", "")) != run_id
        and str(r.get("created_at", "")) < created_at
        and str(r.get("status") or "") == "done"
        and str(r.get("id", "")) not in superseded
        and str(r.get("query_set_version", "")) == query_set_version
    ][-_LIFECYCLE_LOOKBACK_CYCLES:]

    history: list[lifecycle.CycleObservation] = []
    engine_counts: dict[str, tuple[int, int]] = {}
    for index, row in enumerate(earlier):
        prior_id = str(row.get("id", ""))
        try:
            results = db.get_query_results(prior_id)
            judgments = db.get_judgments(prior_id)
        except db.StorageError:
            continue
        answered = sum(1 for r in results if r["response"] is not None)
        themes = _themes_of(judgments)
        history.append(
            lifecycle.CycleObservation(
                run=lifecycle.RunMeta(
                    run_id=prior_id,
                    run_date=str(row.get("created_at", ""))[:10],
                    status="done",
                    coverage_ratio=(answered / len(results) if results else 0.0),
                    query_set_version=str(row.get("query_set_version", "")),
                ),
                themes=themes,
            )
        )
        # Only the IMMEDIATELY prior cycle feeds the movement section — a
        # week-over-week delta compares two cycles, not a trend line.
        if index == len(earlier) - 1:
            engine_counts = _client_engine_counts_from(judgments, str(row.get("client_name", "")))
    return history, engine_counts


def _themes_of(judgments: list[AnswerJudgment]) -> frozenset[str]:
    """Which themes were open in a stored cycle.

    Classified with TODAY's rules, deliberately. Both sides of the diff are
    classified the same way on every render, so a rule change moves findings
    identically in both cycles and cannot manufacture a resolve.
    """
    return frozenset(
        themes.classify(f.type, f.claim, f.reality).theme
        for j in judgments
        if j.assessed
        for f in j.accuracy_flags
    )


def _client_engine_counts_from(
    judgments: list[AnswerJudgment], client: str
) -> dict[str, tuple[int, int]]:
    """(present, answered cells) per engine for the client, from stored verdicts."""
    counts: dict[str, tuple[int, int]] = {}
    for cell in judge_metrics.brand_cells_map(judgments, [client]).get(client, []):
        present, total = counts.get(cell.engine_name, (0, 0))
        counts[cell.engine_name] = (present + (1 if cell.present else 0), total + 1)
    return counts


def _prior_comparable_run(run_id: str, client_name: str, created_at: str) -> tuple[str, str] | None:
    """The most recent EARLIER run for this client, and its query-set version.

    Returns the candidate regardless of whether the version matches — deciding
    comparability is `build_report`'s job, and it needs to know the difference
    between "there is no prior run" and "there is one but the instrument
    changed". Those are different sentences to a client.

    Storage is create-only, so the history already exists; this is a query, not a
    schema change. Degrades to None on a storage failure: a missing comparison
    reads as a first cycle, which is conservative, whereas raising would take out
    a report that is otherwise complete.
    """
    try:
        runs = db.list_audit_runs(client_name)
    except db.StorageError:
        return None
    # A run a later correction replaced is not a cycle — it is the broken first
    # attempt at one. Comparing against it reports the repair of a failed
    # measurement as movement in the client's visibility.
    superseded = db.superseded_run_ids(client_name)
    earlier = [
        r
        for r in runs
        if str(r.get("id", "")) != run_id
        and str(r.get("created_at", "")) < created_at
        # A run that never finished measured a different (smaller) thing. Comparing
        # against it would report the shortfall as a drop in the client's
        # visibility, which is the single most damaging false claim available here.
        and str(r.get("status") or "") == "done"
        and str(r.get("id", "")) not in superseded
    ]
    if not earlier:
        return None
    latest = earlier[-1]  # list_audit_runs is oldest-first
    return str(latest.get("id", "")), str(latest.get("query_set_version", ""))


def _status_from_db(run_id: str) -> RunStatus | None:
    """Rebuild a run's status from storage (a run not in this process's memory —
    e.g. after a restart).

    Per-engine counts come from the stored result rows via ``metrics.coverage_by_engine``
    rather than from an even split of the run totals: an even split would hand a dead
    surface the same completed/answered profile as a working one, so a run read back
    after a restart would hide exactly the failure the live view now catches. Falls
    back to the even split only when the rows can't be read.
    """
    try:
        row = db.get_audit_run(run_id)
    except db.StorageError:
        return None
    if row is None:
        return None
    engines = _str_list(row.get("engines"))
    total = int(str(row.get("total_calls") or 0))
    completed = int(str(row.get("completed_calls") or 0))
    status = str(row.get("status") or "done")
    n = len(engines) or 1
    eng_state = "done" if status in ("done", "cancelled") else status
    try:
        cov = metrics.coverage_by_engine(db.get_query_results(run_id))
    except db.StorageError:
        cov = {}
    per_engine: list[EngineStatus] = []
    for e in engines:
        c = cov.get(e)
        if c is None:
            per_engine.append(
                EngineStatus(name=e, state=eng_state, completed=completed // n, total=total // n)
            )
            continue
        e_state, detail = eng_state, None
        if eng_state == "done" and c.total_cells > 0 and not c.is_measured:
            e_state = "failed"
            detail = (
                f"0 of {c.total_cells} cells returned an answer — no measurement from this surface"
            )
        per_engine.append(
            EngineStatus(
                name=e,
                state=e_state,
                completed=c.total_cells,
                total=c.total_cells,
                detail=detail,
                answered=c.answered_cells,
            )
        )
    return RunStatus(
        run_id=run_id,
        client_name=str(row.get("client_name", "")),
        state=status,
        completed=completed,
        total=total,
        per_engine=per_engine,
        error=(str(row["error"]) if row.get("error") else None),
    )


def _site_audit_from_db(run_id: str, domains: list[str], brand: str) -> SiteAuditPayload | None:
    """Rebuild the site-audit block from stored check + finding rows (best-effort).

    Self-contained so a site-audit storage hiccup degrades to "no site audit"
    rather than aborting the whole report rebuild.
    """
    try:
        rows = db.get_site_audit_checks(run_id)
        finding_rows = db.get_site_audit_findings(run_id)
    except db.StorageError:
        return None
    if not rows and not finding_rows:
        return None
    from src.audit.site_audit import site_audit_payload_from_rows

    return site_audit_payload_from_rows(
        domains[0] if domains else "", rows, finding_rows, brand=brand
    )


def _local_pack_from_db(run_id: str, client: str, location: str) -> LocalPackPayload | None:
    """Rebuild the local-pack block from stored rows (best-effort).

    Self-contained like ``_site_audit_from_db`` so a local-pack storage hiccup degrades
    to "no local pack" instead of aborting the whole report rebuild.
    """
    if not location:
        return None
    try:
        rows = db.get_local_pack_entities(run_id)
    except db.StorageError:
        return None
    if not rows:
        return None
    by_query: dict[str, LocalPackCapture] = {}
    for row in rows:
        query_id = str(row.get("query_id") or "")
        capture = by_query.get(query_id)
        if capture is None:
            capture = LocalPackCapture(
                query_id=query_id,
                prompt=str(row.get("prompt") or ""),
                source=str(row.get("source") or ""),
                entities=[],
            )
            by_query[query_id] = capture
        capture["entities"].append(
            LocalEntity(
                name=str(row.get("name") or ""),
                address=str(row.get("address") or ""),
                category=str(row.get("category") or ""),
                rating=(float(row["rating"]) if row.get("rating") is not None else None),
                reviews=(int(row["reviews"]) if row.get("reviews") is not None else None),
                ludocid=(str(row["ludocid"]) if row.get("ludocid") else None),
                position=(int(row["position"]) if row.get("position") is not None else None),
                phone=(str(row["phone"]) if row.get("phone") else None),
                website=(str(row["website"]) if row.get("website") else None),
            )
        )
    return build_local_pack_payload(list(by_query.values()), client, location)


def _report_from_db(run_id: str) -> ReportPayload | None:
    """Rebuild the report from storage for a run not in this process's memory."""
    try:
        row = db.get_audit_run(run_id)
        if row is None:
            return None
        results = db.get_query_results(run_id)
        judgments = db.get_judgments(run_id)
        site_audit = _site_audit_from_db(
            run_id, _str_list(row.get("client_domains")), str(row.get("client_name", ""))
        )
        local_pack = _local_pack_from_db(
            run_id,
            str(row.get("client_name", "")),
            (str(row["location"]).strip() if row.get("location") else ""),
        )
    except db.StorageError:
        return None
    outcome = _outcome_from_row(row, results)
    history, engine_counts = _cycle_history(
        run_id,
        str(row.get("client_name", "")),
        str(row.get("created_at", "")),
        str(row.get("query_set_version", "")),
    )
    report = build_report(
        outcome,
        judgments=judgments or None,
        fact_sheet_present=bool(row.get("fact_sheet_present")),
        fact_sheet_verification=_verification_for_run(row),
        run_date=str(row.get("created_at", ""))[:10],
        site_audit=site_audit,
        local_pack=local_pack,
        prior_run=_prior_comparable_run(
            run_id, str(row.get("client_name", "")), str(row.get("created_at", ""))
        ),
        prior_cycles=history,
        prior_engine_counts=engine_counts,
    )
    if str(row.get("status") or "") == "done":
        with _REPORT_CACHE_LOCK:
            _REPORT_CACHE[run_id] = report
    return report


def get_status(run_id: str) -> RunStatus | None:
    state = _get(run_id)
    if state is None:
        return _status_from_db(run_id)
    cfg = state.audit.config
    # Each engine's denominator is its OWN routed cell count, not queries x runs: an
    # engine skipped on some intents would otherwise sit at "9/145" forever.
    engine_totals = routed_totals_by_name(
        state.audit.query_set.queries, state.active_engines, cfg.runs_per_query
    )
    per_engine: list[EngineStatus] = []
    for name in state.active_engines:
        completed = state.engine_completed.get(name, 0)
        answered = state.engine_answered.get(name, 0)
        detail: str | None = None
        if state.state in ("done", "cancelled"):
            eng_state = "done"
        elif state.state == "failed":
            eng_state = "failed"
        else:
            eng_state = "running"
        # A surface that attempted calls and answered none produced no measurement.
        # Reporting that as "done" is what let run e186c524 look healthy, so mark it
        # failed once the run is terminal (mid-run it may simply not have landed yet).
        if eng_state == "done" and completed > 0 and answered == 0:
            eng_state = "failed"
            detail = f"0 of {completed} calls returned an answer — no measurement from this surface"
        per_engine.append(
            EngineStatus(
                name=name,
                state=eng_state,
                completed=completed,
                total=engine_totals.get(name, 0),
                detail=detail,
                answered=answered,
            )
        )
    for name, reason in state.skipped_engines:
        per_engine.append(
            EngineStatus(name=name, state="failed", completed=0, total=0, detail=reason)
        )

    site_audit_state: str | None = None
    site_audit_pages = 0
    if cfg.client_domains:
        if state.site_audit is not None:
            site_audit_state = "done"
            site_audit_pages = state.site_audit["pages_crawled"]
        elif state.state in ("done", "cancelled", "failed"):
            site_audit_state = state.state  # finished without a payload
        else:
            site_audit_state = "running"

    return RunStatus(
        run_id=state.run_id,
        client_name=cfg.client_name,
        state=state.state,
        completed=state.completed_calls,
        total=state.total_calls,
        per_engine=per_engine,
        error=state.error,
        site_audit_state=site_audit_state,
        site_audit_pages=site_audit_pages,
    )


def get_report(run_id: str) -> ReportPayload | None:
    with _REPORT_CACHE_LOCK:
        cached = _REPORT_CACHE.get(run_id)
    if cached is not None:
        return cached
    state = _get(run_id)
    if state is None:
        return _report_from_db(run_id)
    live_history, live_engine_counts = _cycle_history(
        state.db_run_id or "",
        state.audit.config.client_name,
        state.created_at,
        state.audit.query_set.version,
    )
    report = build_report(
        _outcome(state),
        judgments=state.judgments or None,
        fact_sheet_present=(
            state.audit.fact_sheet is not None or state.fact_sheet_id is not None
        ),
        fact_sheet_verification=state.fact_sheet_verification,
        run_date=state.created_at[:10],
        site_audit=state.site_audit,
        local_pack=build_local_pack_payload(
            state.local_pack,
            state.audit.config.client_name,
            (state.audit.config.location or "").strip(),
        ),
        prior_run=_prior_comparable_run(
            state.db_run_id or "", state.audit.config.client_name, state.created_at
        ),
        prior_cycles=live_history,
        prior_engine_counts=live_engine_counts,
    )
    if state.state == "done":
        with _REPORT_CACHE_LOCK:
            _REPORT_CACHE[run_id] = report
    return report


@dataclass(frozen=True)
class _ExportInputs:
    client: str
    competitors: list[str]
    results: list[QueryResult]
    judgments: list[AnswerJudgment]
    runs_per_query: int
    engine_order: list[str]
    run_date: str


def _export_inputs(run_id: str) -> _ExportInputs | None:
    """Gather a run's raw answers + judgments for export — in-memory if the run
    is live, else rebuilt from storage (same memory→DB fallback as the report)."""
    state = _get(run_id)
    if state is not None:
        cfg = state.audit.config
        return _ExportInputs(
            client=cfg.client_name,
            competitors=list(cfg.competitors),
            results=list(state.results),
            judgments=list(state.judgments),
            runs_per_query=cfg.runs_per_query,
            engine_order=list(state.active_engines) or list(cfg.engines),
            run_date=state.created_at[:10],
        )
    try:
        row = db.get_audit_run(run_id)
        if row is None:
            return None
        results = db.get_query_results(run_id)
        judgments = db.get_judgments(run_id)
    except db.StorageError:
        return None
    return _ExportInputs(
        client=str(row.get("client_name", "")),
        competitors=_str_list(row.get("competitors")),
        results=results,
        judgments=judgments,
        runs_per_query=int(str(row.get("runs_per_query") or 1)),
        engine_order=_str_list(row.get("engines")),
        run_date=str(row.get("created_at", ""))[:10],
    )


def get_results_csv(run_id: str) -> str | None:
    """Every (query, engine, run) cell as CSV — query text + full response per
    row. ``None`` if the run is unknown."""
    data = _export_inputs(run_id)
    if data is None:
        return None
    return build_results_csv(data.results, data.engine_order)


def get_answers_markdown(run_id: str) -> str | None:
    """The readable answers doc — each query, every raw response, judge verdict
    inline. ``None`` if the run is unknown."""
    data = _export_inputs(run_id)
    if data is None:
        return None
    return build_answers_markdown(
        client=data.client,
        competitors=data.competitors,
        results=data.results,
        judgments=data.judgments,
        run_id=run_id,
        run_date=data.run_date,
        runs_per_query=data.runs_per_query,
        engine_order=data.engine_order,
    )


def get_answers(run_id: str) -> list[QueryResult] | None:
    """The run's verbatim per-(query, engine, run) answers as structured rows.

    The JSON sibling of :func:`get_results_csv` / :func:`get_answers_markdown` —
    same memory→storage fallback via ``_export_inputs``. Each row is a
    ``QueryResult`` (query_id, intent, prompt, engine_name, run_index, response,
    citations, timestamp), which the teaser consumes as ``AnswerRecord`` to
    re-render proof cards. ``None`` if the run is unknown.
    """
    data = _export_inputs(run_id)
    if data is None:
        return None
    return data.results


def list_runs() -> list[RunSummary]:
    """Recent runs: everything in storage, with live in-memory runs overlaid
    (in-memory is authoritative for runs this process is actively driving)."""
    summaries: dict[str, RunSummary] = {}
    try:
        for row in db.list_all_audit_runs():
            rid = str(row.get("id", ""))
            summaries[rid] = RunSummary(
                run_id=rid,
                client_name=str(row.get("client_name", "")),
                state=str(row.get("status", "done")),
                created_at=str(row.get("created_at", "")),
                n_queries=int(str(row.get("n_queries") or 0)),
                engines=_str_list(row.get("engines")),
            )
    except db.StorageError:
        pass

    with _LOCK:
        states = list(_RUNS.values())
    for s in states:
        summaries[s.run_id] = RunSummary(
            run_id=s.run_id,
            client_name=s.audit.config.client_name,
            state=s.state,
            created_at=s.created_at,
            n_queries=len(s.audit.query_set.queries),
            engines=s.active_engines,
        )

    return sorted(summaries.values(), key=lambda x: x.created_at, reverse=True)


def request_cancel(run_id: str) -> bool:
    state = _get(run_id)
    if state is None:
        return False
    if state.state in ("running", "queued"):
        state.cancel_requested = True
    return True


def forget_run(run_id: str) -> None:
    """Drop a run from in-memory state (used when its stored rows are deleted).

    Without this, ``list_runs`` would overlay the still-cached in-memory run back
    on top of storage and the just-deleted project would reappear. If the run is
    still live we flag it cancelled first so its worker stops writing rows that no
    longer have a parent. Its cached report (if any) is evicted too.
    """
    with _LOCK:
        state = _RUNS.pop(run_id, None)
    if state is not None and state.state in ("running", "queued"):
        state.cancel_requested = True
    with _REPORT_CACHE_LOCK:
        _REPORT_CACHE.pop(run_id, None)


def _rebuild_audit_from_row(row: dict[str, object]) -> ParsedAudit | None:
    """Reconstruct the run input (config + query set + fact sheet) from a stored
    row so an interrupted run can be resumed. Returns None if the query set
    wasn't stored (a legacy row predating resume support — unrecoverable)."""
    raw_queries = row.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        return None
    queries: list[Query] = []
    for q in raw_queries:
        if not isinstance(q, dict):
            continue
        queries.append(
            Query(
                query_id=str(q.get("query_id", "")),
                text=str(q.get("text", "")),
                intent=IntentBucket(str(q.get("intent", ""))),
                weight=float(q.get("weight", 1.0) or 1.0),
                persona=(str(q["persona"]) if q.get("persona") else None),
            )
        )
    if not queries:
        return None
    competitors = _str_list(row.get("competitors"))
    config = RunConfig(
        client_name=str(row.get("client_name", "")),
        category=str(row.get("category", "")),
        competitors=competitors,
        engines=_str_list(row.get("engines")),
        runs_per_query=int(str(row.get("runs_per_query") or 1)),
        client_domains=_str_list(row.get("client_domains")),
        judge=bool(row.get("judge")),
        # Restored so a resumed LOCAL run keeps measuring the SAME market. A row
        # written before the column existed yields None — i.e. today's behaviour.
        location=(str(row["location"]).strip() or None) if row.get("location") else None,
    )
    query_set = QuerySet(
        version=str(row.get("query_set_version", "")),
        locked_at=str(row.get("query_set_locked_at") or ""),
        category=config.category,
        client=config.client_name,
        competitors=competitors,
        queries=queries,
    )
    fact_sheet = row.get("fact_sheet")
    return ParsedAudit(
        config=config,
        query_set=query_set,
        fact_sheet=(str(fact_sheet) if fact_sheet else None),
        facts=[],
        provenance=[],
    )


def resume_interrupted_runs() -> int:
    """Relaunch runs left non-terminal by a previous process (e.g. a restart).

    Each resumed run skips its already-persisted queries and continues. Rows
    with no stored query set (legacy, pre-resume) can't be rebuilt and are marked
    ``interrupted`` so they stop showing as active. Returns how many were
    relaunched. Best-effort — storage problems are swallowed, never fatal."""
    try:
        rows = db.list_resumable_runs()
    except db.StorageError as exc:
        logger.info("Could not list resumable runs: %s", exc)
        return 0

    resumed = 0
    for row in rows:
        run_id = str(row.get("id", ""))
        if not run_id or _get(run_id) is not None:
            continue
        try:
            audit = _rebuild_audit_from_row(row)
        except (ValueError, TypeError) as exc:
            logger.warning("Cannot rebuild run %s for resume: %s", run_id, exc)
            audit = None
        if audit is None:
            try:
                db.update_audit_run_progress(
                    run_id,
                    int(str(row.get("completed_calls") or 0)),
                    "interrupted",
                    "interrupted before resume support (no stored query set)",
                )
            except db.StorageError:
                pass
            continue

        cfg = audit.config
        engines, skipped = build_engines(
            cfg.engines, cfg.client_name, cfg.competitors, location=cfg.location
        )
        state = _RunState(
            run_id=run_id,
            audit=audit,
            created_at=str(row.get("created_at") or _now()),
            total_calls=int(str(row.get("total_calls") or 0)),
            db_run_id=run_id,
            active_engines=[e.ENGINE_NAME for e in engines],
            skipped_engines=skipped,
            engine_completed={e.ENGINE_NAME: 0 for e in engines},
        )
        with _LOCK:
            _RUNS[run_id] = state
        threading.Thread(
            target=_execute_run, args=(state, engines), name=f"resume-{run_id[:8]}", daemon=True
        ).start()
        resumed += 1
        logger.info("Resuming interrupted run %s (%s)", run_id, cfg.client_name)

    return resumed
