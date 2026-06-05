from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.api.engine_registry import build_engines
from src.api.reports import ReportPayload, build_report
from src.engines.base import BaseEngine
from src.pipeline.cost import estimate_cost
from src.pipeline.orchestrator import AuditOutcome
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
    "list_runs",
    "request_cancel",
    "resume_interrupted_runs",
]

logger = logging.getLogger(__name__)


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
    engine_completed: dict[str, int] = field(default_factory=dict)
    active_engines: list[str] = field(default_factory=list)
    skipped_engines: list[tuple[str, str]] = field(default_factory=list)
    cancel_requested: bool = False


_RUNS: dict[str, _RunState] = {}
_LOCK = threading.Lock()


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
    _estimated, total_calls = estimate_cost(
        len(audit.query_set.queries), engines, cfg.runs_per_query
    )
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

    # Resume support: any per-query cells already persisted for this run are
    # reloaded and skipped, so an interrupted run continues from where it
    # stopped rather than re-paying for completed queries. (Empty for a fresh
    # run — each query's whole cell is saved atomically, so a query is either
    # fully stored or not at all.)
    done_query_ids: set[str] = set()
    if state.db_run_id is not None:
        try:
            prior = db.get_query_results(state.db_run_id)
        except db.StorageError:
            prior = []
        if prior:
            state.results.extend(prior)
            state.completed_calls = len(prior)
            done_query_ids = {r["query_id"] for r in prior}
            for r in prior:
                state.engine_completed[r["engine_name"]] = (
                    state.engine_completed.get(r["engine_name"], 0) + 1
                )

    try:
        for query in qs.queries:
            if query.query_id in done_query_ids:
                continue
            if state.cancel_requested:
                state.state = "cancelled"
                _persist_state(state)
                return
            cell = run_query_set([query], engines, cfg.runs_per_query)
            state.results.extend(cell)
            state.completed_calls += len(cell)
            for r in cell:
                state.engine_completed[r["engine_name"]] = (
                    state.engine_completed.get(r["engine_name"], 0) + 1
                )
            if state.db_run_id is not None:
                try:
                    db.save_query_results(state.db_run_id, cell)
                except db.StorageError as exc:
                    logger.info("Failed to persist a cell (continuing): %s", exc)
            _persist_state(state)

        if state.cancel_requested:
            state.state = "cancelled"
            _persist_state(state)
            return

        if cfg.judge:
            _run_judge(state)

        state.state = "done"
        _persist_state(state)
    except Exception as exc:  # defensive: a run thread must never die silently
        logger.warning("Run %s failed: %s", state.run_id, type(exc).__name__)
        state.state = "failed"
        state.error = f"run failed: {type(exc).__name__}"
        _persist_state(state, state.error)


def _run_judge(state: _RunState) -> None:
    """Best-effort LLM judging after the answers are collected.

    Skipped (not fatal) if the judge can't be built (no OPENAI_API_KEY).
    """
    from src.pipeline.judge import Judge

    cfg = state.audit.config
    try:
        judge = Judge()
    except ValueError as exc:
        logger.info("Judge skipped: %s", exc)
        return
    state.judgments = judge.judge_results(
        state.results, cfg.client_name, cfg.competitors, state.audit.fact_sheet
    )
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


def _report_from_db(run_id: str) -> ReportPayload | None:
    """Rebuild the report from storage for a run not in this process's memory."""
    try:
        row = db.get_audit_run(run_id)
        if row is None:
            return None
        results = db.get_query_results(run_id)
        judgments = db.get_judgments(run_id)
    except db.StorageError:
        return None
    outcome = _outcome_from_row(row, results)
    return build_report(
        outcome,
        judgments=judgments or None,
        fact_sheet_present=bool(row.get("fact_sheet_present")),
        run_date=str(row.get("created_at", ""))[:10],
    )


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
    return RunStatus(
        run_id=state.run_id,
        client_name=cfg.client_name,
        state=state.state,
        completed=state.completed_calls,
        total=state.total_calls,
        per_engine=per_engine,
        error=state.error,
    )


def get_report(run_id: str) -> ReportPayload | None:
    state = _get(run_id)
    if state is None:
        return _report_from_db(run_id)
    return build_report(
        _outcome(state),
        judgments=state.judgments or None,
        fact_sheet_present=state.audit.fact_sheet is not None,
        run_date=state.created_at[:10],
    )


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
