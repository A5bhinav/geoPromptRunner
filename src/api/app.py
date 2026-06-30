from __future__ import annotations

import dataclasses
import hashlib
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from src.api import runner
from src.config import settings
from src.pipeline.cost import CostBudgetExceeded
from src.prompts.csv_loader import (
    ParseResult,
    build_template_csv,
    parse_csv_files,
)
from src.storage import db

__all__ = ["app"]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """On startup, resume any runs a previous process left interrupted.

    Done on a background thread so a slow/unreachable storage backend can't
    delay the server coming up.
    """
    threading.Thread(target=runner.resume_interrupted_runs, name="resume-scan", daemon=True).start()
    yield


app = FastAPI(
    title="GEO Audit API",
    version="1.0",
    description="Thin wrapper over the GEO audit pipeline: upload CSVs, run, report.",
    lifespan=lifespan,
)

# CORS: only the configured frontend origin(s) may script the API from a browser
# (never "*" in production — see GEO_CORS_ORIGINS). Credentials stay off; auth is
# the X-API-Key header, not cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.GEO_CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    """Gate every data endpoint behind a shared key.

    No key configured (local dev) → open. Configured → the request must present
    a matching ``X-API-Key`` header, else 401. This closes anonymous access to
    runs/exports and stops anyone from triggering paid LLM work.
    """
    expected = settings.GEO_API_KEY
    if not expected:
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


# All data routes live on this router so a single dependency gates them; the
# health check below stays open for load-balancer probes.
api = APIRouter(dependencies=[Depends(require_api_key)])


# The UI previews an upload then runs it — the same bytes parsed twice. Cache the
# parse by content hash so /audits reuses /audits/preview's work. Bounded; cleared
# wholesale when full (parse results are cheap to recompute on a miss).
_PARSE_CACHE: dict[str, ParseResult] = {}
_PARSE_CACHE_MAX = 32
_PARSE_CACHE_LOCK = threading.Lock()


def _parse_cached(uploads: list[tuple[str, str]]) -> ParseResult:
    key = hashlib.sha256(
        "\x00".join(f"{name}\x01{text}" for name, text in uploads).encode("utf-8")
    ).hexdigest()
    with _PARSE_CACHE_LOCK:
        cached = _PARSE_CACHE.get(key)
    if cached is not None:
        return cached
    result = parse_csv_files(uploads)
    with _PARSE_CACHE_LOCK:
        if len(_PARSE_CACHE) >= _PARSE_CACHE_MAX:
            _PARSE_CACHE.clear()
        _PARSE_CACHE[key] = result
    return result


async def _read_uploads(files: list[UploadFile]) -> list[tuple[str, str]]:
    """Read uploaded files into (filename, text) pairs (UTF-8, lossy).

    Enforces a hard total-size cap so a giant upload can't exhaust memory.
    """
    out: list[tuple[str, str]] = []
    total = 0
    for f in files:
        raw = await f.read()
        total += len(raw)
        if total > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"upload exceeds {settings.MAX_UPLOAD_BYTES} bytes",
            )
        text = raw.decode("utf-8", errors="replace")
        out.append((f.filename or "upload.csv", text))
    return out


def _serialize_parse(result: ParseResult) -> dict[str, object]:
    """Shape a ParseResult for the Preview screen (always renderable)."""
    p = result.preview
    payload: dict[str, object] = {
        "ok": result.ok,
        "errors": [dataclasses.asdict(e) for e in result.errors],
        "config": [dataclasses.asdict(c) for c in p.config],
        "facts": [dataclasses.asdict(f) for f in p.facts],
        "queries": [dataclasses.asdict(q) for q in p.queries],
        "provenance": [
            {
                "filename": fp.filename,
                "n_config": fp.n_config,
                "n_fact": fp.n_fact,
                "n_query": fp.n_query,
                "summary": fp.summary,
            }
            for fp in p.provenance
        ],
        "config_resolved": None,
    }
    if result.audit is not None:
        cfg = result.audit.config
        payload["config_resolved"] = {
            **dataclasses.asdict(cfg),
            "fact_sheet_present": result.audit.fact_sheet is not None,
        }
    return payload


def _enforce_audit_caps(result: ParseResult) -> None:
    """Reject an audit that would run an unbounded bill / DoS the server.

    Hard caps on queries, engines, and runs-per-query, checked before any LLM
    call is made. Tunable via the MAX_* settings.
    """
    if result.audit is None:
        return
    n_queries = len(result.audit.query_set.queries)
    n_engines = len(result.audit.config.engines)
    runs = result.audit.config.runs_per_query
    if n_queries > settings.MAX_QUERIES:
        raise HTTPException(
            status_code=413, detail=f"too many queries ({n_queries} > {settings.MAX_QUERIES})"
        )
    if n_engines > settings.MAX_ENGINES:
        raise HTTPException(
            status_code=413, detail=f"too many engines ({n_engines} > {settings.MAX_ENGINES})"
        )
    if runs > settings.MAX_RUNS_PER_QUERY:
        raise HTTPException(
            status_code=413,
            detail=f"runs_per_query too high ({runs} > {settings.MAX_RUNS_PER_QUERY})",
        )


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "geo-audit-api"}


@api.get("/template.csv")
def template_csv() -> Response:
    return Response(
        content=build_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="geo-audit-template.csv"'},
    )


@api.post("/audits/preview")
async def preview(files: Annotated[list[UploadFile], File()]) -> dict[str, object]:
    """Parse + merge + validate the upload without running anything."""
    uploads = await _read_uploads(files)
    return _serialize_parse(_parse_cached(uploads))


@api.post("/audits")
async def create_audit(files: Annotated[list[UploadFile], File()]) -> dict[str, object]:
    """Parse + validate; on success start the run and return its id.

    On validation failure returns 422 with the same structured preview the
    preview endpoint returns, so the UI can show errors inline.
    """
    uploads = await _read_uploads(files)
    result = _parse_cached(uploads)
    if result.audit is None:
        raise HTTPException(status_code=422, detail=_serialize_parse(result))
    _enforce_audit_caps(result)
    try:
        run_id = runner.start_run(result.audit)
    except CostBudgetExceeded as exc:
        # 402 Payment Required — the spend guard refused this run.
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return {"run_id": run_id}


@api.get("/audits")
def list_audits() -> list[dict[str, object]]:
    return [dataclasses.asdict(s) for s in runner.list_runs()]


@api.get("/audits/{run_id}/status")
def audit_status(run_id: str) -> dict[str, object]:
    status = runner.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return dataclasses.asdict(status)


@api.get("/audits/{run_id}/report")
def audit_report(run_id: str) -> dict[str, object]:
    report = runner.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return dict(report)


def _guard_export_ready(run_id: str) -> None:
    """409 while a run is still producing answers — an export taken mid-run would
    be a silently partial file presented (via Content-Disposition) as complete.
    Terminal states (done/failed/cancelled) export whatever was collected."""
    status = runner.get_status(run_id)
    if status is not None and status.state in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"run {run_id} is still {status.state}; export once it finishes",
        )


@api.get("/audits/{run_id}/results.csv")
def audit_results_csv(run_id: str) -> Response:
    """Raw answers as CSV — one row per (query, engine, run): the query text and
    the full model response as columns."""
    _guard_export_ready(run_id)
    csv_text = runner.get_results_csv(run_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="geo-audit-{run_id}-answers.csv"'},
    )


@api.get("/audits/{run_id}/answers.md")
def audit_answers_markdown(run_id: str) -> Response:
    """Raw answers as a readable markdown doc — each query, every response, and
    the judge's verdict inline."""
    _guard_export_ready(run_id)
    md = runner.get_answers_markdown(run_id)
    if md is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="geo-audit-{run_id}-answers.md"'},
    )


@api.get("/audits/{run_id}/answers")
def audit_answers(run_id: str) -> list[dict[str, object]]:
    """Verbatim per-(query, engine, run) answers as JSON — the structured sibling
    of answers.md / results.csv. Each row matches the storage ``QueryResult``
    shape, which the teaser consumes as ``AnswerRecord`` to re-render proof cards.
    """
    _guard_export_ready(run_id)
    answers = runner.get_answers(run_id)
    if answers is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return [dict(a) for a in answers]


@api.post("/audits/{run_id}/cancel")
def cancel_audit(run_id: str) -> dict[str, str]:
    if not runner.request_cancel(run_id):
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return {"status": "cancelling"}


@api.post("/audits/{run_id}/judge")
def judge_audit(run_id: str) -> dict[str, object]:
    """Re-judge a completed run's stored answers and return the refreshed report.

    Pairs with the subscription pre-judge workflow: once the judge cache is warm
    (via ``/prejudge`` in Claude Code), this pass is all cache hits → free, and the
    UI gets judged metrics without a re-run. Returns the updated report so the
    client can render it without a second round-trip.
    """
    report = runner.rejudge_run(run_id)
    if report is None:
        raise HTTPException(
            status_code=404, detail=f"run {run_id} not found or has no answers to judge"
        )
    return dict(report)


# --- Teasers: persist a generated one-pager, then approve / edit / reject -----
#
# The teaser pipeline (teaser/) runs as a child process out of the Next route and
# returns {draft, html}; the browser POSTs that here so it lands in Supabase
# (via src/storage/db.py) and can be reviewed. CRUD/state-only — no LLM work — so
# these call straight into db.py rather than through a runner module. A storage
# failure surfaces as 503 (Supabase not configured/unreachable) rather than 500.


class SaveTeaserBody(BaseModel):
    draft: dict[str, object]
    html: str | None = None


class EditTeaserBody(BaseModel):
    # Reviewer overrides for the printable copy (headline / leadSentence / cta /
    # stakesLine, …). Stored in edited_fields; html (re-rendered with the edits)
    # is optional so the preview can reflect them.
    edited_fields: dict[str, object]
    html: str | None = None


class RejectTeaserBody(BaseModel):
    reason: str | None = None


def _teaser_or_404(teaser_id: str) -> dict[str, object]:
    try:
        row = db.get_teaser(teaser_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail=f"teaser {teaser_id} not found")
    return row


@api.post("/teasers")
def save_teaser(body: SaveTeaserBody) -> dict[str, object]:
    """Persist a freshly generated teaser draft (status='draft') and return its id."""
    try:
        teaser_id = db.save_teaser(dict(body.draft), body.html)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"teaser_id": teaser_id}


@api.get("/teasers")
def list_teasers() -> list[dict[str, object]]:
    """Recent teasers (id, company, status, created_at, …) for the saved list."""
    try:
        return db.list_teasers()
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api.get("/teasers/{teaser_id}")
def get_teaser(teaser_id: str) -> dict[str, object]:
    """A single teaser: full draft + html + status + edited_fields."""
    return _teaser_or_404(teaser_id)


@api.post("/teasers/{teaser_id}/approve")
def approve_teaser(teaser_id: str) -> dict[str, object]:
    _teaser_or_404(teaser_id)
    try:
        row = db.update_teaser_status(teaser_id, status="approved")
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return row or {}


@api.post("/teasers/{teaser_id}/edit")
def edit_teaser(teaser_id: str, body: EditTeaserBody) -> dict[str, object]:
    """Save reviewer copy edits into edited_fields (and optionally re-rendered html).

    Does not change status — an edited draft can still be approved or rejected.
    """
    _teaser_or_404(teaser_id)
    try:
        row = db.update_teaser_status(
            teaser_id, edited_fields=dict(body.edited_fields), html=body.html
        )
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return row or {}


@api.post("/teasers/{teaser_id}/reject")
def reject_teaser(teaser_id: str, body: RejectTeaserBody) -> dict[str, object]:
    _teaser_or_404(teaser_id)
    # Store a blank reason as NULL (not ""), so a rejected-without-reason teaser
    # is cleanly distinguishable from one whose reason failed to persist.
    reason = (body.reason or "").strip() or None
    try:
        row = db.update_teaser_status(teaser_id, status="rejected", reject_reason=reason)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return row or {}


# --- Audit deliverables: persist a generated audit, then approve / edit / reject ---
#
# The audit generator (teaser/, `npm run audit`) runs as a child process out of the
# Next route and returns {draft, html}; the browser POSTs that here so it lands in
# Supabase and can be reviewed. CRUD/state-only — no LLM work — so these call
# straight into db.py, mirroring the /teasers endpoints exactly.


class SaveAuditBody(BaseModel):
    draft: dict[str, object]
    html: str | None = None


class EditAuditBody(BaseModel):
    # Reviewer overrides for the narrative (headline / verdictSentence /
    # achievableGrade / projectedImpact / nextSteps). Stored in edited_fields;
    # html (re-rendered with the edits) is optional so the preview can reflect them.
    edited_fields: dict[str, object]
    html: str | None = None


class RejectAuditBody(BaseModel):
    reason: str | None = None


def _audit_or_404(deliverable_id: str) -> dict[str, object]:
    try:
        row = db.get_audit_deliverable(deliverable_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail=f"audit deliverable {deliverable_id} not found")
    return row


@api.post("/audit-deliverables")
def save_audit_deliverable(body: SaveAuditBody) -> dict[str, object]:
    """Persist a freshly generated audit draft (status='draft') and return its id."""
    try:
        deliverable_id = db.save_audit_deliverable(dict(body.draft), body.html)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"deliverable_id": deliverable_id}


@api.get("/audit-deliverables")
def list_audit_deliverables() -> list[dict[str, object]]:
    """Recent audit deliverables (id, client, grade, status, created_at) for the list."""
    try:
        return db.list_audit_deliverables()
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api.get("/audit-deliverables/{deliverable_id}")
def get_audit_deliverable(deliverable_id: str) -> dict[str, object]:
    """A single audit deliverable: full draft + html + status + edited_fields."""
    return _audit_or_404(deliverable_id)


@api.post("/audit-deliverables/{deliverable_id}/approve")
def approve_audit_deliverable(deliverable_id: str) -> dict[str, object]:
    _audit_or_404(deliverable_id)
    try:
        row = db.update_audit_status(deliverable_id, status="approved")
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return row or {}


@api.post("/audit-deliverables/{deliverable_id}/edit")
def edit_audit_deliverable(deliverable_id: str, body: EditAuditBody) -> dict[str, object]:
    """Save reviewer narrative edits into edited_fields (and optionally re-rendered html).

    Does not change status — an edited draft can still be approved or rejected.
    """
    _audit_or_404(deliverable_id)
    try:
        row = db.update_audit_status(
            deliverable_id, edited_fields=dict(body.edited_fields), html=body.html
        )
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return row or {}


@api.post("/audit-deliverables/{deliverable_id}/reject")
def reject_audit_deliverable(deliverable_id: str, body: RejectAuditBody) -> dict[str, object]:
    _audit_or_404(deliverable_id)
    reason = (body.reason or "").strip() or None
    try:
        row = db.update_audit_status(deliverable_id, status="rejected", reject_reason=reason)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return row or {}


app.include_router(api)
