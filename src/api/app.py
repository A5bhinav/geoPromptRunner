from __future__ import annotations

import dataclasses
import hashlib
import hmac
import logging
import subprocess
import tempfile
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from src.api import auth, console, intake, projects, runner, sharing
from src.api import digest as digest_mod
from src.api import identity as identity_mod
from src.audit.competitors import candidates_from_local_pack
from src.audit.factsheet import FactSheet, suggested_run_inputs, to_markdown
from src.config import settings
from src.engines.local_pack import SOURCE_NONE, fetch_local_pack
from src.licensing import verdict_source
from src.pipeline import review
from src.pipeline.cost import CostBudgetExceeded
from src.pipeline.fixpack import render_fix_pack
from src.prompts.assemble import AssembleError, assemble_run_csv
from src.prompts.csv_loader import (
    ParseResult,
    build_template_csv,
    parse_csv_files,
)
from src.prompts.local_templates import TRADES
from src.storage import db

__all__ = ["app"]

logger = logging.getLogger(__name__)


def _warn_if_open() -> None:
    """Log a loud warning when the API is unauthenticated (no GEO_API_KEY).

    A blank key means anyone who can reach the API can trigger paid LLM work, read
    every run, and permanently delete projects — fine on localhost, dangerous once
    exposed. Surfaced at startup so an accidentally-open deploy is visible in logs.
    """
    if not settings.GEO_API_KEY:
        logger.warning(
            "GEO_API_KEY is not set — the API is OPEN. Anyone who can reach it can "
            "trigger paid LLM work, read every run, and delete projects. Set GEO_API_KEY "
            "before exposing this beyond localhost."
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """On startup, warn if the API is open, then resume any interrupted runs.

    The resume scan runs on a background thread so a slow/unreachable storage
    backend can't delay the server coming up.
    """
    _warn_if_open()
    threading.Thread(target=runner.resume_interrupted_runs, name="resume-scan", daemon=True).start()
    yield


def _docs_urls(api_key: str | None) -> dict[str, str | None]:
    """Interactive docs + the OpenAPI schema are exposed ONLY in open/dev mode (no
    key). With a key configured (prod), disable them so an unauthenticated caller
    can't map the whole surface — every endpoint, param, and shape — via
    ``/openapi.json``. Pure, so the gate is unit-testable."""
    open_mode = not api_key
    return {
        "docs_url": "/docs" if open_mode else None,
        "redoc_url": "/redoc" if open_mode else None,
        "openapi_url": "/openapi.json" if open_mode else None,
    }


_docs = _docs_urls(settings.GEO_API_KEY)
app = FastAPI(
    title="GEO Audit API",
    version="1.0",
    description="Thin wrapper over the GEO audit pipeline: upload CSVs, run, report.",
    lifespan=lifespan,
    docs_url=_docs["docs_url"],
    redoc_url=_docs["redoc_url"],
    openapi_url=_docs["openapi_url"],
)

# CORS: only the configured frontend origin(s) may script the API from a browser
# (never "*" in production — see GEO_CORS_ORIGINS). Credentials stay off; auth is
# the X-API-Key header, not cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.GEO_CORS_ORIGINS.split(",") if o.strip()],
    # True since LIC-T17, so the browser will send the httpOnly share cookie back
    # to `/shared/report` once the token has been cleaned out of the URL.
    #
    # Safe HERE specifically because `allow_origins` is an explicit list and never
    # "*" — the spec forbids the combination, and so does the browser. The usual
    # objection to credentialed CORS is CSRF, which needs a cookie that AUTHORISES
    # a state change; this API authenticates with the `X-API-Key` header or a
    # bearer token, neither of which a browser attaches automatically. The one
    # cookie that exists is read-only, scoped to `/shared`, and confers exactly the
    # access its holder already had by holding the token.
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
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
    # Constant-time compare so response timing can't leak the key byte-by-byte.
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


#: The fact-sheet intake surface, as route prefixes (LIC-T18). Named here rather
#: than left as a string in a `.env` file so the set is testable and so "did we
#: migrate all of intake" has one answer instead of depending on whoever wrote
#: the deploy config. DoD #4 — an agency onboarding its own client — runs
#: entirely through these two.
INTAKE_PREFIXES = ("/intake", "/fact-sheets")

#: The provisioning and console surface (LIC-T14 / LIC-T19). These are meaningless
#: on the shared key — every handler resolves the caller's own organization from
#: the verified identity and refuses to take it from the request — so they are
#: listed here to be migrated together, and a test asserts every console route
#: falls under them.
CONSOLE_PREFIXES = ("/admin", "/agency")


def _migrated_prefixes() -> tuple[str, ...]:
    """Route prefixes that require a JWT (LIC-T6). Read live, not at import, so a
    test or a deploy can move one route without restarting the process."""
    raw = settings.JWT_MIGRATED_ROUTES or ""
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def is_jwt_route(path: str) -> bool:
    """Whether ``path`` has migrated to per-user auth.

    Prefix matching on the PATH, so `/projects` covers `/projects/{key}/history`
    and a route migrates with its whole subtree. Pure, so the gate is
    unit-testable without a request.
    """
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in _migrated_prefixes())


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


async def authenticate(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Authenticate one request and bind its identity for the handler (LIC-T6).

    **Exactly one credential is accepted per route, and which one depends on
    whether the route has migrated.** A migrated route takes a verified Supabase
    JWT and REFUSES the shared key; an unmigrated route takes the shared key and
    refuses a JWT. Never both — a route that accepted either would leave "which
    credential authorised this request" unanswerable, which is exactly the
    question an incident starts with.

    The identity is bound into a ContextVar rather than returned, so every gate
    already calling `current_identity()` starts discriminating with no signature
    changes anywhere.

    **No explicit unbind, and that is not an oversight.** Starlette handles each
    request in its own task, and a task copies the context at creation — so a
    `set()` here is confined to this request and cannot leak into the next one.
    Sync handlers run in a threadpool that receives a copy of this context, so
    they read the value correctly. The tempting symmetric `reset()` in an HTTP
    middleware would in fact be a bug: `BaseHTTPMiddleware` runs `call_next` in a
    separate task, so the token would belong to a different context and the reset
    would raise.
    """
    if is_jwt_route(request.url.path):
        if x_api_key:
            raise HTTPException(
                status_code=401,
                detail="this endpoint uses per-user authentication; send a bearer token",
            )
        try:
            claims = auth.verify_access_token(_bearer(authorization))
        except auth.AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        identity = _identity_for(claims, _bearer(authorization))
    else:
        if _bearer(authorization) and not x_api_key:
            raise HTTPException(
                status_code=401,
                detail="this endpoint has not migrated to per-user auth; send X-API-Key",
            )
        require_api_key(x_api_key)
        identity = identity_mod.PLATFORM_ADMIN

    identity_mod.bind(identity)


def _identity_for(claims: auth.Claims, access_token: str) -> identity_mod.CallerIdentity:
    """Resolve a verified token to an identity, reading roles from the DATABASE.

    The token proves who; `memberships` and `users.is_platform_admin` decide what.
    Deliberately not read from the token: there is no first-party way to
    force-refresh a user's JWT claims mid-session, so a role baked into a token
    outlives its own revocation. One indexed lookup per request buys revocation
    that takes effect on the next request instead of the next refresh.

    A storage failure degrades to the LEAST privilege that still identifies the
    caller — a known user with no org and no admin flag — rather than to a
    platform admin. Failing open here would hand founder rights to anyone holding
    any valid token during an outage.
    """
    try:
        profile = db.get_user_profile(claims.subject)
    except db.StorageError:
        logger.warning("identity lookup failed; degrading to least privilege")
        return identity_mod.CallerIdentity(
            user_id=claims.subject, is_platform_admin=False, access_token=access_token
        )
    if profile is None:
        raise HTTPException(status_code=403, detail="this account is not provisioned")
    if profile.deactivated:
        raise HTTPException(status_code=403, detail="this account has been deactivated")
    return identity_mod.CallerIdentity(
        user_id=claims.subject,
        is_platform_admin=profile.is_platform_admin,
        organization_id=profile.organization_id,
        access_token=access_token,
    )


# All data routes live on this router so a single dependency gates them; the
# health check below stays open for load-balancer probes.
api = APIRouter(dependencies=[Depends(authenticate)])


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
def template_csv(trade: str | None = None) -> Response:
    """The starter CSV. With ``?trade=``, a filled local query set instead.

    `build_template_csv` has always taken a trade and this endpoint never passed
    one, so the only reachable template was the 4-query consumer starter — while
    `render_trade_queries` sat behind it generating 29 real local_intent questions
    per trade, deterministically and with no model call. The queries existed and
    could not be obtained.
    """
    if trade is not None and trade not in TRADES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown trade {trade!r}; expected one of: {', '.join(TRADES)}",
        )
    name = f"geo-audit-template-{trade}.csv" if trade else "geo-audit-template.csv"
    return Response(
        content=build_template_csv(trade),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


class AssembleBody(BaseModel):
    """A lead, plus the two things a lead form does not capture."""

    business: str
    website: str
    trade: str
    city: str
    # The state's FULL name. Not derivable from the lead's free-text "area", and
    # deliberately not guessed: nothing in this repo expands "CA" to "California",
    # because a wrong market is worse than a missing one.
    region: str
    country: str = "United States"
    category: str | None = None
    runs_per_query: int = 3
    judge: bool = False
    # Skip the local-pack call (which costs a Serper credit) and supply your own.
    competitors: list[str] | None = None


@api.post("/audits/assemble")
def assemble_audit(body: AssembleBody) -> dict[str, object]:
    """Build a runnable audit CSV for one local business.

    Combines the four inputs that already existed separately: the lead's fields, a
    trade query template (29 filled local questions, no model), competitors from
    Google's local pack, and the config block. Returns the CSV text plus what it
    excluded, so a caller can show the drops rather than present a list that looks
    complete.

    The fact sheet is NOT embedded — it attaches to the run by id, and a run
    carrying both is refused.
    """
    location = f"{body.city.strip()},{body.region.strip()},{body.country.strip()}"
    excluded: list[dict[str, str]] = []
    competitors = list(body.competitors or [])
    pack_source = "supplied"

    if body.competitors is None:
        seed = f"best {body.trade} in {body.city.strip()}"
        entities, pack_source = fetch_local_pack(seed, location)
        found = candidates_from_local_pack(
            entities,
            client_name=body.business,
            client_website=body.website,
            source_query=seed,
            location=location,
            as_of=datetime.now(UTC).date().isoformat(),
        )
        competitors = found.names
        excluded = [{"name": n, "reason": r} for n, r in found.exclusions]

    try:
        csv_text = assemble_run_csv(
            business=body.business,
            website=body.website,
            trade=body.trade,
            city=body.city,
            region=body.region,
            country=body.country,
            competitors=competitors,
            category=body.category,
            runs_per_query=body.runs_per_query,
            judge=body.judge,
        )
    except AssembleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "csv": csv_text,
        "competitors": competitors,
        "excluded": excluded,
        "competitor_source": pack_source,
        # Loud rather than silent: a run with no competitors measures share-of-voice
        # against nobody, and the caller has to decide whether that is acceptable.
        "warning": (
            "no competitors found — the local pack returned nothing usable. Add them "
            "by hand before running, or the audit measures the client against nobody."
            if not competitors
            else None
        ),
    }


@api.get("/trades")
def list_trades() -> list[str]:
    """Trades with a query template, so the UI never hardcodes the list."""
    return list(TRADES)


@api.get("/local-entities")
def local_entities(q: str, location: str) -> dict[str, object]:
    """Businesses in Google's local pack for ``q`` at ``location`` (W1.6).

    The teaser's ONLY sanctioned source of local competitor candidates. Exposed here
    rather than called from TypeScript because the vendor credential lives in
    ``settings.py`` and nowhere else (hard invariant) — the teaser must not hold a
    second copy of it.

    ``location`` is required and must be Google's canonical location name
    ("Berkeley,California,United States"). Without it Google answers from an unpinned locale and
    names businesses in the wrong metro — which, seeded into a teaser as "your
    competitors", is exactly the fabrication this endpoint exists to prevent. A
    missing location is a 422, never a silent nationwide lookup.
    """
    query = q.strip()
    canonical = location.strip()
    if not query:
        raise HTTPException(status_code=422, detail="q must not be empty")
    if not canonical:
        raise HTTPException(
            status_code=422,
            detail=(
                "location is required — a local pack from an unpinned locale names "
                "businesses in the wrong metro"
            ),
        )

    # Goes through the local-pack resolver, NOT the google_ai_overviews engine.
    #
    # It used to build that engine and call query_local_entities on it, which coupled the
    # local pack to whichever vendor happened to be serving AI Overviews. That broke the
    # moment AI Overviews gained a second vendor: DataForSEO captures Overviews but has no
    # local-pack method, so this endpoint would 500 on an isinstance assert as soon as
    # DataForSEO credentials existed. The two surfaces were never the same thing.
    #
    # fetch_local_pack also prefers Serper /places, which returns ~10 businesses with
    # street addresses, phone and website — the richest local-pack source available.
    entities, source = fetch_local_pack(query, canonical)
    if not entities and source == SOURCE_NONE:
        raise HTTPException(
            status_code=503,
            detail=(
                "local-entity capture unavailable: no local-pack vendor is configured "
                "(set SERPER_API_KEY)"
            ),
        )
    # An empty list from a working vendor is a real answer — that query surfaced no local
    # pack — and must not be reported as an outage.
    return {"query": query, "location": canonical, "source": source, "entities": entities}


@api.post("/audits/preview")
async def preview(files: Annotated[list[UploadFile], File()]) -> dict[str, object]:
    """Parse + merge + validate the upload without running anything."""
    uploads = await _read_uploads(files)
    return _serialize_parse(_parse_cached(uploads))


@api.post("/audits")
async def create_audit(
    files: Annotated[list[UploadFile], File()],
    fact_sheet_id: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    """Parse + validate; on success start the run and return its id.

    On validation failure returns 422 with the same structured preview the
    preview endpoint returns, so the UI can show errors inline.

    ``fact_sheet_id`` attaches an APPROVED sheet from ``/fact-sheets`` as this run's
    ground truth, instead of `fact` rows in the CSV. It is what connects the review
    queue to a run at all: without it, approving a sheet moved one column and
    nothing downstream ever read it.
    """
    uploads = await _read_uploads(files)
    result = _parse_cached(uploads)
    if result.audit is None:
        raise HTTPException(status_code=422, detail=_serialize_parse(result))
    _enforce_audit_caps(result)
    try:
        run_id = runner.start_run(result.audit, (fact_sheet_id or "").strip() or None)
    except runner.FactSheetNotUsable as exc:
        # 422: the upload is well-formed but the ground truth it names cannot be
        # used. A wrong reference is worse than none — it would judge every answer
        # against a document nobody approved.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CostBudgetExceeded as exc:
        # 402 Payment Required — the spend guard refused this run.
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return {"run_id": run_id}


@api.get("/audits")
def list_audits() -> list[dict[str, object]]:
    return [dataclasses.asdict(s) for s in runner.list_runs()]


# --- Projects: a domain-keyed roll-up of audits + teasers --------------------
#
# Derived, not stored: src/api/projects.py groups existing audit_runs and teasers
# by prospect domain so the UI can show "everything we've done for fort.cx" in one
# place. Read-only; degrades to whatever data is reachable (no 503 if Supabase is
# down — you just see the in-memory runs).


@api.get("/projects")
def list_projects() -> list[dict[str, object]]:
    return [dataclasses.asdict(p) for p in projects.list_projects()]


@api.get("/projects/{key}")
def get_project(key: str) -> dict[str, object]:
    detail = projects.get_project(key)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"project {key} not found")
    return dataclasses.asdict(detail)


@api.get("/projects/{key}/history")
def project_history(key: str) -> list[dict[str, object]]:
    """Completed cycles for one project, oldest first — the project page's trend.

    A separate route from `/projects/{key}` on purpose: the detail route is a
    cheap listing, and this one assembles a report per completed run. Both are
    free (stored rows plus the warm judge cache, no engine and no judge calls),
    but a dashboard should not pay for a chart it is not drawing.
    """
    return [dataclasses.asdict(p) for p in projects.project_history(key)]


@api.delete("/projects/{key}")
def delete_project(key: str) -> dict[str, object]:
    """Permanently delete a project's audits (children cascade) and teasers.

    503 if storage is unreachable; 404 if the key matches no audits or teasers.
    """
    try:
        result = projects.delete_project(key)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"project {key} not found")
    return result


@api.get("/audits/{run_id}/status")
def audit_status(run_id: str) -> dict[str, object]:
    status = runner.get_status(run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return dataclasses.asdict(status)


@api.get("/audits/{run_id}/report")
def audit_report(run_id: str) -> dict[str, object]:
    _require_deliverable(run_id)
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


# --- Phase 3: layering the delivery -------------------------------------------


@api.get("/audits/{run_id}/answers/{query_id}/{engine}/{run_index}")
def audit_answer_cell(run_id: str, query_id: str, engine: str, run_index: int) -> dict[str, object]:
    """The full model answer behind one finding (P3-T1).

    Answers are already stored — this is retrieval and presentation only. It
    exists because the evidence trail was otherwise reachable only by downloading
    the whole `answers.md`, and a finding a client cannot check is a finding they
    have to take on trust.
    """
    answers = runner.get_answers(run_id)
    if answers is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    for row in answers:
        if (
            row["query_id"] == query_id
            and row["engine_name"] == engine
            and row["run_index"] == run_index
        ):
            return dict(row)
    raise HTTPException(
        status_code=404,
        detail=f"no answer for {query_id}/{engine}/run {run_index} in run {run_id}",
    )


@api.get("/audits/{run_id}/digest")
def audit_digest(run_id: str, base_url: str = "") -> dict[str, str]:
    """The weekly digest as text + HTML (P3-T3). Delivery transport is elsewhere."""
    report = runner.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    root = base_url.rstrip("/")
    built = digest_mod.build_digest(
        report,
        report_url=f"{root}/audits/{run_id}" if root else "",
        answers_url=f"{root}/audits/{run_id}?tab=answers" if root else "",
    )
    return {"subject": built.subject, "text": built.text, "html": built.html}


@api.get("/audits/{run_id}/fix-pack.md")
def audit_fix_pack(run_id: str) -> Response:
    """Every prioritised finding as one pasteable markdown document (P3-T6)."""
    _guard_export_ready(run_id)
    report = runner.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    markdown = render_fix_pack(
        report.get("finding_groups") or [], report["client_name"], report["run_date"]
    )
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="geo-fix-pack-{run_id}.md"'
        },
    )


class ShareRequest(BaseModel):
    ttl_seconds: int = sharing.DEFAULT_TTL_SECONDS
    password: str = ""


@api.get("/audits/{run_id}/report.pdf")
def audit_report_pdf(run_id: str, base_url: str = "http://localhost:3000") -> Response:
    """Server-side PDF of the report route (P3-T5).

    Wraps `web/scripts/render-report-pdf.mjs` — the worker built in P1-T7, which
    owns every Chromium-specific trap (one margin source, isolated header iframe,
    the readiness gate). This endpoint is the scheduling surface, not a second
    renderer.

    Degrades the way the rest of the repo does: **503 with the install hint** when
    Chromium is absent, so an operator gets a fixable instruction rather than a
    stack trace. The print-ready HTML at `/audits/{id}?mode=print` still works.
    """
    _guard_export_ready(run_id)
    if runner.get_report(run_id) is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    script = Path(__file__).resolve().parents[2] / "web" / "scripts" / "render-report-pdf.mjs"
    if not script.exists():
        raise HTTPException(status_code=503, detail="the PDF worker is not installed")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{run_id}.pdf"
        result = subprocess.run(
            ["node", str(script), run_id, "--base", base_url, "--out", str(out)],
            cwd=script.parent.parent,
            capture_output=True,
            text=True,
            timeout=300,
        )
        # Exit 2 is the worker's "Chromium missing" code. DEGRADE rather than
        # fail: redirect to the print-ready route, which is the same document
        # one Cmd-P away. The repo's existing convention (teaser/render/audit/
        # pdf.ts) is that a missing browser costs you the PDF, not the
        # deliverable — a 503 would leave an operator with nothing while a
        # perfectly good printable page sits one URL away.
        if result.returncode == 2:
            return Response(
                status_code=302,
                headers={
                    "Location": f"{base_url.rstrip('/')}/audits/{run_id}?mode=print",
                    "X-PDF-Fallback": "chromium-unavailable",
                },
            )
        if result.returncode != 0 or not out.exists():
            raise HTTPException(
                status_code=500, detail=f"PDF render failed: {result.stderr.strip()[:300]}"
            )
        pdf = out.read_bytes()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="geo-report-{run_id}.pdf"'},
    )


def _require_deliverable(run_id: str, *, anonymous_visitor: bool = False) -> None:
    """Refuse to deliver a run whose verdicts were not produced by the API judge.

    LIC-T20's hard gate. It sits on the places a report LEAVES us — minting a
    share link, rendering a report, and the shared-link read itself — rather than
    on the judge, because warming the notebook on the subscription is a
    legitimate and encouraged dev loop. What must never happen is that output
    reaching a paying client while looking indistinguishable from the API-judged
    product they bought.

    **It keys on who OWNS the run, not only on who is asking.** The spec's rule is
    that a non-`api` verdict may not be rendered for or shared with a non-platform
    ORGANIZATION. So the gate fires when either side of that is true: the caller
    is not a platform admin, or the run belongs to a company managed by an agency.
    The second half matters for `/shared/{token}/report`, where the visitor is
    anonymous by design and there is no caller identity to reason about — an
    agency's client link is gated, while the founders' own manually-delivered
    client links (no managing agency) keep working exactly as before. Gating every
    anonymous read regardless of ownership would have broken live client links on
    deploy, for runs that predate verdict tagging.

    When storage is unreachable the gate opens rather than 503s: taking the whole
    report surface down because one metadata read failed trades a real outage for
    a hypothetical one, and an agency-run audit cannot exist without the storage
    that just failed.
    """
    identity = identity_mod.current_identity()
    try:
        row = db.get_audit_run(run_id)
    except db.StorageError:
        logger.warning("verdict-source gate: could not read run %s, allowing", run_id)
        return
    if row is None:
        return

    agency_owned = False
    company_id = row.get("company_id")
    if company_id:
        try:
            company = db.get_company(str(company_id))
            agency_owned = company is not None and company.managing_agency_id is not None
        except db.StorageError:
            logger.warning("verdict-source gate: could not read company, allowing")
            return

    # A platform admin reading a run nobody else owns is the dev loop; leave it be.
    if identity.is_platform_admin and not agency_owned and not anonymous_visitor:
        return
    if not agency_owned and anonymous_visitor:
        # A founder-delivered client link on an untenanted or direct-owned run.
        # Unchanged behaviour, deliberately — see the docstring.
        return

    decision = verdict_source.check_delivery(row.get("verdict_sources"), is_platform=False)
    if not decision.allowed:
        # 409, not 403: the caller is entitled to this run, and the request will
        # succeed once the run is re-judged. A 403 would read as "you may not see
        # your own client's report", which is both wrong and alarming.
        raise HTTPException(status_code=409, detail=decision.reason)


@api.post("/audits/{run_id}/share")
def create_share_link(run_id: str, body: ShareRequest) -> dict[str, object]:
    """Mint a signed, expiring read-only link (P3-T4, made durable by LIC-T17).

    A login wall is what kills forwardability, and forwardability is the one thing
    a PDF has over a dashboard. Requires the API key to MINT; the link itself does
    not, which is the point.

    Since LIC-T17 the link is also a ROW, carrying the tenant it belongs to. The
    signature is unchanged, so this is additive — but ``persistent`` in the
    response says which guarantee the caller actually got. A run that is not
    persisted, or not tenanted, cannot have a row written for it; the link still
    works and is still revocable through the deny list, but per-client revocation
    and the access log need a `company_id` that does not exist for it. Saying so
    beats reporting success and quietly delivering less.
    """
    if runner.get_status(run_id) is None and runner.get_report(run_id) is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    _require_deliverable(run_id)
    try:
        token = sharing.mint_share_token(run_id, body.ttl_seconds, body.password)
        parsed = sharing.verify_share_token(token, body.password, frozenset())
    except sharing.ShareError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    persistent = _record_share_token(parsed, body.password)
    return {
        "token": token,
        "path": f"/shared/{token}",
        "expires_in": body.ttl_seconds,
        "token_id": parsed.token_id,
        "persistent": persistent,
    }


def _record_share_token(parsed: sharing.ShareToken, password: str) -> bool:
    """Write the token row, returning whether it was actually recorded.

    Degrades rather than fails: a storage error here would turn "your link is
    minted" into a 500 for a link that is already cryptographically valid and
    would work. The caller learns the truth through ``persistent``.
    """
    try:
        row = db.get_audit_run(parsed.run_id)
    except db.StorageError:
        logger.warning("share token not recorded: run lookup failed")
        return False
    company_id = str((row or {}).get("company_id") or "")
    if not company_id:
        logger.info("share token not recorded: run has no tenant")
        return False
    identity = identity_mod.current_identity()
    try:
        db.create_share_token_row(
            token_id=parsed.token_id,
            run_id=parsed.run_id,
            company_id=company_id,
            expires_at=parsed.expires_at,
            password_hash=sharing.hash_password(password),
            created_by=identity.user_id or None,
        )
    except db.StorageError:
        logger.warning("share token not recorded: storage unavailable")
        return False
    return True


#: How long the exchanged share cookie outlives the first view, capped. The
#: cookie is a bearer credential for one report, so it expires with the link
#: rather than persisting as a long-lived session.
_SHARE_COOKIE = "geo_share"


def _harden_share_response(response: Response) -> None:
    """Headers a confidential report route must carry (design §3.6).

    `no-referrer` stops the token travelling to any origin the report links or
    embeds reach — without it the URL, which IS the credential, ends up in
    another host's access log. `noindex` keeps a forwarded link out of search
    results; different crawlers honour the header and the meta tag, so the web
    layer sets the tag too.
    """
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    # A shared report is per-token content; a shared cache holding it would serve
    # one client's report to the next visitor of the same URL.
    response.headers["Cache-Control"] = "private, no-store"


def _serve_shared_report(token: str, password: str, response: Response) -> dict[str, object]:
    """Verify a share token and return its report. The one anonymous read path.

    Order is deliberate and unchanged from P3-T4: signature FIRST, then the
    stateless deny list, then expiry, then password — checking expiry before the
    signature would let a visitor learn which run ids exist by reading the
    different error messages.

    LIC-T17 adds the row checks AFTER all of that, because they cost a database
    round trip and an unsigned token deserves none.
    """
    try:
        parsed = sharing.verify_share_token(token, password, _revoked_share_ids())
    except sharing.ShareError as exc:
        # 403 for every failure mode, with the reason in the body: a 404-vs-403
        # split would let a visitor enumerate which run ids exist.
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    row = None
    try:
        row = db.get_share_token_row(parsed.token_id)
    except db.StorageError:
        # The link is validly signed and not on the deny list. Refusing here would
        # take every client report down on a storage blip, for a check that only
        # ever NARROWS what the signature already allowed.
        logger.warning("share token row unavailable, falling back to the signature")

    if row is not None:
        if row.revoked:
            raise HTTPException(status_code=403, detail="this link has been revoked")
        if not db.company_delivery_live(row.company_id):
            # Not "revoked": nobody withdrew this link, the relationship behind it
            # ended. The distinction is what the client's own support call needs.
            raise HTTPException(
                status_code=403, detail="this report is no longer available"
            )
    # A validly-signed token with NO row is a link minted before LIC-T17, or one
    # for an untenanted run. Honoured deliberately — every client link already in
    # an inbox has to keep working, the same requirement LIC-T11 had.

    # Checked on the READ, not only when the link was minted: a run can be
    # re-judged from a warm subscription notebook after its link went out, and the
    # link would otherwise keep serving the newer, non-deliverable verdicts.
    _require_deliverable(parsed.run_id, anonymous_visitor=True)
    report = runner.get_report(parsed.run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")

    if row is not None:
        try:
            db.record_share_view(parsed.token_id)
        except db.StorageError:
            # The access log is an audit convenience, not an access control. It
            # must never be the reason a client cannot read their report.
            logger.warning("share view not recorded: storage unavailable")

    _harden_share_response(response)
    return dict(report)


# Deliberately on `app`, NOT `api`: a shared link that required the API key would
# be a login wall with extra steps.
@app.get("/shared/{token}/report")
def shared_report(token: str, response: Response, password: str = "") -> dict[str, object]:
    """Read-only report behind a signed link. No API key; the token IS the auth.

    Sets the token as an httpOnly cookie on the way out so the browser can drop
    it from the URL (design §3.6). While the token sits in the address bar it
    leaks through history and — absent the `no-referrer` header above — through
    the `Referer` of anything the page loads. The cookie is scoped, httpOnly and
    unreadable to script; `/shared/report` below is how the page reads the report
    once the URL has been cleaned.
    """
    payload = _serve_shared_report(token, password, response)
    response.set_cookie(
        _SHARE_COOKIE,
        token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=sharing.DEFAULT_TTL_SECONDS,
        path="/shared",
    )
    return payload


@app.get("/shared/report")
def shared_report_by_cookie(
    request: Request, response: Response, password: str = ""
) -> dict[str, object]:
    """The same report, read from the exchanged cookie instead of the URL.

    Declared as a separate path rather than an optional parameter so there is no
    ambiguity with `/shared/{token}/report`: a token always contains a `.`, but
    relying on that to disambiguate a route is the kind of cleverness that breaks
    the day a token format changes.
    """
    token = request.cookies.get(_SHARE_COOKIE, "")
    if not token:
        raise HTTPException(status_code=403, detail="this link is not valid")
    return _serve_shared_report(token, password, response)


# In-process mirror of the revocation deny list.
#
# NOT the source of truth — `revoked_share_tokens` is (data/schema_operations.sql).
# This exists so a revocation still holds for the life of the process when
# storage is unreachable, and so the read path has an answer if the table is
# missing. A share token is stateless and signed, so revoking it means
# remembering that we no longer honour it; a store that forgets on restart would
# bring a revoked link back to life after a deploy, which is the one failure mode
# a revocation mechanism may not have.
_REVOKED_SHARES: set[str] = set()


def _revoked_share_ids() -> frozenset[str]:
    """Every revoked token id: the durable list, unioned with this process's.

    Union rather than either alone. Storage may be unreachable (then the local
    set is all we have), and a token revoked by another process must still be
    honoured here — erring toward MORE revocations is the safe direction, since
    the failure is a link that stops working rather than one that should not.
    """
    try:
        return frozenset(db.revoked_share_ids() | _REVOKED_SHARES)
    except db.StorageError:
        return frozenset(_REVOKED_SHARES)


@api.post("/shares/{token_id}/revoke")
def revoke_share(token_id: str) -> dict[str, object]:
    """Withdraw one link. Per-token, so revoking one does not revoke them all.

    Writes through to the deny-list table and mirrors locally. ``persistent``
    tells the caller which of those happened: a revocation that only took effect
    in this process is a materially weaker guarantee, and the API says so rather
    than reporting success either way.
    """
    _REVOKED_SHARES.add(token_id)
    row_revoked = False
    try:
        # BOTH stores, deliberately. The row is the source of truth for a link
        # minted since LIC-T17 and is what the agency console reads; the deny list
        # still covers every token minted before it, which has no row to flip.
        # Writing only one of them would leave a live link looking revoked in the
        # UI, or a revoked link still serving.
        row_revoked = db.revoke_share_token_row(token_id, reason="revoked via API")
        db.revoke_share_token(token_id, reason="revoked via API")
    except db.StorageError:
        logger.warning("share revocation not persisted: storage unavailable")
        return {"revoked": token_id, "persistent": False}
    return {"revoked": token_id, "persistent": True, "row_revoked": row_revoked}


@api.post("/audits/{run_id}/cancel")
def cancel_audit(run_id: str) -> dict[str, str]:
    if not runner.request_cancel(run_id):
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return {"status": "cancelling"}


@api.get("/audits/{run_id}/judge-status")
def get_judge_status(run_id: str) -> dict[str, object]:
    """Warm status of the query + content notebooks for a run (pure cache reads).

    The UI polls this to show whether Judge / the report will be free (everything
    pre-judged on the subscription) or will still hit the API.
    """
    return runner.judge_status(run_id)


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


# --- QA review queue: sample, reconcile, persist (P4-T1/T2) -------------------
#
# The sampler and the reconciler were built and correct, and the loop had no
# ends: nothing fed the queue to a reviewer and nothing kept what came back. A
# review that is computed and discarded cannot answer the only questions worth
# asking of it — "did the reviewers disagree more this month", "which judge
# prompt was in force when this verdict was overridden".


class ReviewSubmission(BaseModel):
    """Two BLIND labels for one cell, plus the judge's, for reconciliation.

    Both reviewer labels are required and both are stored, even when they agree.
    Recording only the reconciled answer throws away the disagreement RATE, which
    is the number that says whether the labels themselves are trustworthy — and a
    gold set built by two people who never disagree is usually one where the
    second anchored on the first.
    """

    cell_id: str
    stratum: str
    judge_label: str
    reviewer_a: str
    reviewer_b: str
    prompt_fingerprint: str
    note: str = ""


@api.get("/audits/{run_id}/review-queue")
def get_review_queue(run_id: str) -> dict[str, object]:
    """The cells this cycle wants a human to check, stratified.

    Deterministic given the run: the sampler ranks by a hash of the cell id, so
    the same run always produces the same queue. A reviewer who reloads the page
    does not get a different sample, and two reviewers working the same queue are
    genuinely working the same queue.
    """
    report = runner.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    candidates = [
        review.ReviewCandidate(
            cell_id=f"{flag['query_id']}:{flag['engine_name']}:{flag['run_index']}",
            severity=str(flag["severity"]),
            lifecycle_status="",
        )
        for flag in report["accuracy_flags"]
    ]
    sampled = review.sample_for_review(candidates)
    return {
        "run_id": run_id,
        "client_name": report["client_name"],
        "pool": len(candidates),
        "items": [{"cell_id": cell_id, "stratum": stratum} for cell_id, stratum in sampled.items],
        "dropped": sampled.dropped,
    }


@api.post("/audits/{run_id}/reviews")
def submit_review(run_id: str, body: ReviewSubmission) -> dict[str, object]:
    """Reconcile two blind labels and append the record.

    Reconciliation ESCALATES to the more severe label when reviewers differ: for a
    client-facing product the errors are not symmetric — a false Critical is
    embarrassing and gets caught at the next review, a missed one ships as
    silence.
    """
    report = runner.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")

    record = review.reconcile(
        cell_id=body.cell_id,
        stratum=body.stratum,
        judge_label=body.judge_label,
        reviewer_a=body.reviewer_a,
        reviewer_b=body.reviewer_b,
        prompt_fingerprint=body.prompt_fingerprint,
        reviewed_at=datetime.now(UTC).isoformat(),
        note=body.note,
    )
    try:
        db.save_review_records(run_id, report["client_name"], [dataclasses.asdict(record)])
    except db.StorageError as exc:
        # 503, not 500: the reconciliation itself succeeded and is in the
        # response, so the caller can retry the write without re-labelling.
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    return dataclasses.asdict(record)


@api.get("/clients/{client_name}/reviews")
def list_reviews(client_name: str, limit: int = 500) -> dict[str, object]:
    """This client's review history, with the agreement figures it supports."""
    try:
        records = db.get_review_records(client_name, limit=limit)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail="storage unavailable") from exc
    outcomes: dict[str, int] = {}
    for r in records:
        outcomes[str(r.get("outcome", ""))] = outcomes.get(str(r.get("outcome", "")), 0) + 1
    total = len(records)
    return {
        "client_name": client_name,
        "records": records,
        "total": total,
        "by_outcome": outcomes,
        # Counted, with its denominator — the same rule the report follows.
        "reviewer_disagreement": (
            f"{outcomes.get('escalated', 0)} of {total} reviewed cells"
            if total
            else "none reviewed"
        ),
    }


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


# --- Fact sheets: the reachable human gate (plan F4) -------------------------
#
# The generator is deliberately cheap and unreviewed: `save_fact_sheet` always writes
# DRAFT, and `uq_fact_sheets_active_domain` allows exactly one ACTIVE row per domain.
# Promotion is therefore the ONLY way a generated sheet becomes something a run is
# judged against, and it happens here, through a person. That is the whole point of
# F4 — before it, the worker could fill a table and nothing could act on the contents.
#
# CRUD/state only, no LLM work, mirroring the /teasers lifecycle.


class RejectFactSheetBody(BaseModel):
    reason: str = ""


def _fact_sheet_or_404(sheet_id: str) -> FactSheet:
    try:
        sheet = db.get_fact_sheet(sheet_id)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if sheet is None:
        raise HTTPException(status_code=404, detail=f"fact sheet {sheet_id} not found")
    return sheet


@api.get("/fact-sheets")
def list_fact_sheets(
    state: str | None = None, domain: str | None = None
) -> list[dict[str, object]]:
    """The review queue: sheet rows newest first, optionally filtered by state.

    Rows, not documents — the queue shows a domain, a state and a claim count, and
    rehydrating every claim of every sheet to render that would be a join per row.
    """
    parsed: db.FactSheetState | None = None
    if state is not None:
        try:
            parsed = db.FactSheetState(state)
        except ValueError as exc:
            allowed = ", ".join(s.value for s in db.FactSheetState)
            raise HTTPException(
                status_code=422, detail=f"unknown state {state!r}; expected one of: {allowed}"
            ) from exc
    try:
        return db.list_fact_sheets(state=parsed, domain=domain)
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@api.get("/fact-sheets/{sheet_id}")
def get_fact_sheet(sheet_id: str) -> dict[str, object]:
    """One sheet with every claim's EVIDENCE attached — the reviewable unit.

    A reviewer cannot approve a claim they cannot check, so each claim carries its
    verbatim quote, source URL and as-of date, not just the assertion. The open
    questions come too: they are the call list, and the §4.3 disagreements are
    exactly what a human is here to resolve.
    """
    sheet = _fact_sheet_or_404(sheet_id)
    return {
        "id": sheet_id,
        "domain": sheet.domain,
        "business_name": sheet.business_name,
        "business_kind": sheet.business_kind.value,
        "version": sheet.version,
        "sheet_status": sheet.sheet_status.value,
        "verification_tier": sheet.verification_tier.value,
        "generated_at": sheet.generated_at,
        "lead_ref": sheet.lead_ref,
        "questions": list(sheet.questions),
        "claims": [
            {
                "claim_id": c.claim_id,
                "section": c.section.value,
                "key": c.key,
                "value": c.value,
                "polarity": c.polarity.value,
                "verbatim_quote": c.verbatim_quote,
                "source_url": c.source_url,
                "source_kind": c.source_kind.value,
                "as_of": c.as_of,
                "verification": c.verification.value,
                "confidence": c.confidence.value,
            }
            for c in sheet.claims
        ],
        "markdown": to_markdown(sheet),
        # What a run's config can be prefilled with, so "start from a lead" stops
        # asking for the name, domain and city this sheet was extracted from.
        # Any field may be null — that means ASK, never guess.
        "suggested": suggested_run_inputs(sheet),
    }


@api.post("/fact-sheets/{sheet_id}/approve")
def approve_fact_sheet(sheet_id: str) -> dict[str, object]:
    """Promote DRAFT -> ACTIVE, demoting the domain's incumbent in the same call.

    This is the moment a generated document becomes a measurement reference, so it
    is a person's decision and never the worker's.
    """
    _fact_sheet_or_404(sheet_id)
    try:
        db.activate_fact_sheet(sheet_id)
    except db.StorageError as exc:
        # 409, not 503: promoting a rejected sheet is a conflicting request, not a
        # storage outage, and the reviewer needs to be told which it was.
        if "was REJECTED" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"id": sheet_id, "state": db.FactSheetState.ACTIVE.value}


@api.delete("/fact-sheets/{sheet_id}")
def delete_fact_sheet(sheet_id: str) -> dict[str, object]:
    """Permanently delete one fact sheet and its claims.

    WHAT SURVIVES, AND WHY THIS IS SAFE. A finished run keeps its OWN copy of
    the sheet it was judged against — `audit_runs.fact_sheet` is the rendered
    text and `fact_sheet_version` records which version it was — so deleting the
    sheet row cannot retroactively change what a past report was measured
    against. `fact_claims` cascades; `factsheet_jobs.fact_sheet_id` and
    `factsheet_intake_sessions.fact_sheet_id` are ON DELETE SET NULL, so the
    record of what was spent producing it, and any conversation about it,
    outlive the row.

    Snapshots go FIRST, while the row that names their prefix still exists —
    same ordering as project deletion, for the same reason: the bucket is not
    covered by the row cascade and nothing else knows the prefix.

    THIS REPLACES REJECTION AS THE "NO" PATH. `reject_fact_sheet` still exists
    and still records a reason, but the queue no longer offers it: a sheet whose
    claims are wrong is now deleted and re-made through the intake, where the
    owner confirms every line. The cost of that choice is real and worth naming
    — a rejection reason was the only signal the extractor got about what it
    produced wrongly, and a deleted row teaches nothing.
    """
    sheet = db.get_fact_sheet(sheet_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail=f"fact sheet {sheet_id} not found")
    try:
        db.delete_factsheet_sources_for_sheets([sheet_id])
        deleted = db.delete_fact_sheets([sheet_id])
    except db.StorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("fact sheet deleted: domain=%s version=%s", sheet.domain, sheet.version)
    return {"id": sheet_id, "domain": sheet.domain, "deleted": deleted}


@api.post("/fact-sheets/{sheet_id}/reject")
def reject_fact_sheet(sheet_id: str, body: RejectFactSheetBody) -> dict[str, object]:
    """Record that a reviewer read this sheet and said no. The row stays.

    409 when the sheet is ACTIVE: live runs are judged against it, and pulling it
    out from under them would leave accuracy claims referencing a document that no
    longer exists. Activate a replacement instead.
    """
    _fact_sheet_or_404(sheet_id)
    try:
        db.reject_fact_sheet(sheet_id, body.reason)
    except db.StorageError as exc:
        if "is ACTIVE" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"id": sheet_id, "state": db.FactSheetState.REJECTED.value}


# The intake routes carry no auth of their own — they ride the `authenticate`
# dependency every other route on `api` does, which since LIC-T6 means they
# migrate to per-user auth by PREFIX rather than by code change.
#
# LIC-T18: the two prefixes to migrate are `/intake` and `/fact-sheets` (see
# INTAKE_PREFIXES). Their three tables — `factsheet_intake_sessions`,
# `fact_sheets`, `fact_claims` — already carry `company_id` with RLS, FORCE and a
# policy, and `db.ensure_company()` stamps the caller's agency on a company it
# creates, so an agency onboarding its own client lands in its own tenant.
api.include_router(intake.router)
# LIC-T14 provisioning and LIC-T19's console. On `api`, so both ride the same
# `authenticate` dependency: `/admin` and `/agency` are meaningless without a
# per-user identity, so migrate them with `JWT_MIGRATED_ROUTES=/admin,/agency`.
api.include_router(console.router)
app.include_router(api)
