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
from src.prompts.csv_loader import ParsedAudit
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
    """Register a run and kick it off on a background thread. Returns the run id."""
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
    with _LOCK:
        _RUNS[run_id] = state

    thread = threading.Thread(
        target=_execute_run, args=(state, engines), name=f"audit-{run_id[:8]}", daemon=True
    )
    thread.start()
    return run_id


def _execute_run(state: _RunState, engines: list[BaseEngine]) -> None:
    cfg = state.audit.config
    if not engines:
        state.state = "failed"
        state.error = (
            "no engines could be started — check API keys, or use engines=mock to demo without keys"
        )
        return

    state.state = "running"

    # Best-effort: open a persistent audit_run row if Supabase is configured.
    qs = state.audit.query_set
    try:
        state.db_run_id = db.create_audit_run(
            client_name=cfg.client_name,
            client_domains=cfg.client_domains,
            competitors=cfg.competitors,
            category=cfg.category,
            query_set_version=qs.version,
            query_set_locked_at=qs.locked_at,
            runs_per_query=cfg.runs_per_query,
        )
    except db.StorageError as exc:
        logger.info("Storage unavailable, running in-memory only: %s", exc)
        state.db_run_id = None

    try:
        for query in qs.queries:
            if state.cancel_requested:
                state.state = "cancelled"
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

        if state.cancel_requested:
            state.state = "cancelled"
            return

        if cfg.judge:
            _run_judge(state)

        state.state = "done"
    except Exception as exc:  # defensive: a run thread must never die silently
        logger.warning("Run %s failed: %s", state.run_id, type(exc).__name__)
        state.state = "failed"
        state.error = f"run failed: {type(exc).__name__}"


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


def get_status(run_id: str) -> RunStatus | None:
    state = _get(run_id)
    if state is None:
        return None
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
        return None
    return build_report(
        _outcome(state),
        judgments=state.judgments or None,
        fact_sheet_present=state.audit.fact_sheet is not None,
        run_date=state.created_at[:10],
    )


def list_runs() -> list[RunSummary]:
    with _LOCK:
        states = list(_RUNS.values())
    states.sort(key=lambda s: s.created_at, reverse=True)
    return [
        RunSummary(
            run_id=s.run_id,
            client_name=s.audit.config.client_name,
            state=s.state,
            created_at=s.created_at,
            n_queries=len(s.audit.query_set.queries),
            engines=s.active_engines,
        )
        for s in states
    ]


def request_cancel(run_id: str) -> bool:
    state = _get(run_id)
    if state is None:
        return False
    if state.state in ("running", "queued"):
        state.cancel_requested = True
    return True
