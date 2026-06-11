from __future__ import annotations

import dataclasses
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.api import runner
from src.prompts.csv_loader import (
    ParseResult,
    build_template_csv,
    parse_csv_files,
)

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

# Dev CORS: the Next.js frontend runs on a different origin (localhost:3000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _read_uploads(files: list[UploadFile]) -> list[tuple[str, str]]:
    """Read uploaded files into (filename, text) pairs (UTF-8, lossy)."""
    out: list[tuple[str, str]] = []
    for f in files:
        raw = await f.read()
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


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "geo-audit-api"}


@app.get("/template.csv")
def template_csv() -> Response:
    return Response(
        content=build_template_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="geo-audit-template.csv"'},
    )


@app.post("/audits/preview")
async def preview(files: Annotated[list[UploadFile], File()]) -> dict[str, object]:
    """Parse + merge + validate the upload without running anything."""
    uploads = await _read_uploads(files)
    return _serialize_parse(parse_csv_files(uploads))


@app.post("/audits")
async def create_audit(files: Annotated[list[UploadFile], File()]) -> dict[str, object]:
    """Parse + validate; on success start the run and return its id.

    On validation failure returns 422 with the same structured preview the
    preview endpoint returns, so the UI can show errors inline.
    """
    uploads = await _read_uploads(files)
    result = parse_csv_files(uploads)
    if result.audit is None:
        raise HTTPException(status_code=422, detail=_serialize_parse(result))
    run_id = runner.start_run(result.audit)
    return {"run_id": run_id}


@app.get("/audits")
def list_audits() -> list[dict[str, object]]:
    return [dataclasses.asdict(s) for s in runner.list_runs()]


@app.get("/audits/{run_id}/status")
def audit_status(run_id: str) -> dict[str, object]:
    status = runner.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return dataclasses.asdict(status)


@app.get("/audits/{run_id}/report")
def audit_report(run_id: str) -> dict[str, object]:
    report = runner.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return dict(report)


@app.post("/audits/{run_id}/cancel")
def cancel_audit(run_id: str) -> dict[str, str]:
    if not runner.request_cancel(run_id):
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return {"status": "cancelling"}
