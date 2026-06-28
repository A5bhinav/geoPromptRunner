from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.api.engine_registry import build_engines
from src.api.reports import ReportPayload, SiteAuditPayload, build_report
from src.config import settings
from src.engines.base import BaseEngine
from src.pipeline.answers_export import build_answers_markdown, build_results_csv
from src.pipeline.cost import CostBudgetExceeded, estimate_total_cost
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
    results: list[QueryResult] = field(default_factory=list)
    judgments: list[AnswerJudgment] = field(default_factory=list)
    site_audit: SiteAuditPayload | None = None
    engine_completed: dict[str, int] = field(default_factory=dict)
    active_engines: list[str] = field(default_factory=list)
    skipped_engines: list[tuple[str, str]] = field(default_factory=list)
    cancel_requested: bool = False


_RUNS: dict[str, _RunState] = {}
_LOCK = threading.Lock()

# Once a run is "done" its report is immutable, but the UI may re-fetch it and a
# restarted process rebuilds it from 3 Supabase round-trips + full aggregation
# every time. Cache the built ReportPayload for done runs (done is terminal-final
# — interrupted/queued runs are what get resumed, never done ones — so no
# invalidation is needed).
_REPORT_CACHE: dict[str, ReportPayload] = {}
_REPORT_CACHE_LOCK = threading.Lock()

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
    )


def start_run(audit: ParsedAudit) -> str:
    """Register a run and kick it off on a background thread. Returns the run id.

    The run id is generated here and used as *both* the in-memory key and the
    stored ``audit_runs`` row id, so a finished run can be read back from storage
    by the same id the UI is polling — even after the API restarts.
    """
    cfg = audit.config
    run_id = str(uuid.uuid4())
    # Cost/total are estimated against the engines that will actually build, so
    # the progress denominator matches what runs (a missing key drops calls).
    engines, skipped = build_engines(cfg.engines, cfg.client_name, cfg.competitors)
    estimated, total_calls = estimate_total_cost(
        len(audit.query_set.queries), engines, cfg.runs_per_query, cfg.judge
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
            fact_sheet_present=audit.fact_sheet is not None,
            queries=_serialize_queries(qs.queries),
            fact_sheet=audit.fact_sheet,
            judge=cfg.judge,
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
            _join_site_audit(site_thread)
            state.state = "cancelled"
            _persist_state(state)
            return

        if cfg.judge:
            _run_judge(state)

        # Wait for the concurrent site audit so the report includes it.
        _join_site_audit(site_thread)
        state.state = "done"
        _persist_state(state)
    except Exception as exc:  # defensive: a run thread must never die silently
        # Log the real type server-side; surface only a generic message to the
        # client so internal details aren't disclosed.
        logger.warning("Run %s failed: %s", state.run_id, type(exc).__name__)
        _join_site_audit(site_thread, timeout=30.0)
        state.state = "failed"
        state.error = "run failed (see server logs)"
        _persist_state(state, state.error)


def _join_site_audit(site_thread: threading.Thread | None, timeout: float | None = None) -> None:
    """Join the concurrent site-audit thread (best-effort; never raises)."""
    if site_thread is not None:
        site_thread.join(timeout)


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

        state.site_audit = run_site_audit(
            state.run_id,
            domain,
            brand=cfg.client_name,
            competitors=cfg.competitors,
            persist=state.db_run_id is not None,
        )
    except Exception as exc:  # phase is additive — its failure never fails the run
        logger.warning("Site audit failed for run %s: %s", state.run_id, type(exc).__name__)


def _run_judge(state: _RunState) -> None:
    """Best-effort LLM judging after the answers are collected.

    Skipped (not fatal) if the judge can't be built (no OPENAI_API_KEY).
    """
    from src.config import settings
    from src.pipeline.judge import Judge
    from src.pipeline.judge_cache import JudgeCache

    cfg = state.audit.config
    try:
        judge = Judge()
    except ValueError as exc:
        logger.info("Judge skipped: %s", exc)
        return
    # Persistent verdict cache: an answer already judged under these exact inputs
    # (model, client, competitors, fact sheet, prompt) is reused, not re-judged —
    # so resumes and re-runs don't re-pay for the same answers.
    cache = JudgeCache(settings.JUDGE_CACHE_PATH)
    try:
        state.judgments = judge.judge_results(
            state.results,
            cfg.client_name,
            cfg.competitors,
            state.audit.fact_sheet,
            cache=cache,
        )
    finally:
        cache.close()
    if state.db_run_id is not None:
        try:
            db.save_judgments(state.db_run_id, state.judgments)
        except db.StorageError as exc:
            logger.info("Failed to persist judgments (continuing): %s", exc)


def _get(run_id: str) -> _RunState | None:
    with _LOCK:
        return _RUNS.get(run_id)


def _str_list(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _outcome_from_row(row: dict[str, object], results: list[QueryResult]) -> AuditOutcome:
    return AuditOutcome(
        run_id=str(row.get("id", "")),
        client_name=str(row.get("client_name", "")),
        client_domains=_str_list(row.get("client_domains")),
        competitors=_str_list(row.get("competitors")),
        query_set_version=str(row.get("query_set_version", "")),
        runs_per_query=int(str(row.get("runs_per_query") or 1)),
        results=results,
    )


def _status_from_db(run_id: str) -> RunStatus | None:
    """Rebuild a run's status from storage (a run not in this process's memory —
    e.g. after a restart). Coarser than the live view: per-engine counts are
    split evenly from the stored totals."""
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
    per_engine = [
        EngineStatus(name=e, state=eng_state, completed=completed // n, total=total // n)
        for e in engines
    ]
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
    except db.StorageError:
        return None
    outcome = _outcome_from_row(row, results)
    report = build_report(
        outcome,
        judgments=judgments or None,
        fact_sheet_present=bool(row.get("fact_sheet_present")),
        run_date=str(row.get("created_at", ""))[:10],
        site_audit=site_audit,
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
    per_query_runs = len(state.audit.query_set.queries) * cfg.runs_per_query
    per_engine: list[EngineStatus] = []
    for name in state.active_engines:
        completed = state.engine_completed.get(name, 0)
        if state.state in ("done", "cancelled"):
            eng_state = "done"
        elif state.state == "failed":
            eng_state = "failed"
        else:
            eng_state = "running"
        per_engine.append(
            EngineStatus(name=name, state=eng_state, completed=completed, total=per_query_runs)
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
    report = build_report(
        _outcome(state),
        judgments=state.judgments or None,
        fact_sheet_present=state.audit.fact_sheet is not None,
        run_date=state.created_at[:10],
        site_audit=state.site_audit,
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
        engines, skipped = build_engines(cfg.engines, cfg.client_name, cfg.competitors)
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
