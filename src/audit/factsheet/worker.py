"""The cross-project fact-sheet worker (plan §12.3): leads in, DRAFT sheets out.

Two databases, one direction. `leads` lives in the WEBSITE's Supabase project;
`factsheet_jobs` and `fact_sheets` live in the PLATFORM's. A Postgres trigger on
`leads` therefore cannot enqueue anything — different database — and the `pg_net`
alternative needs the platform API hosted, which `run-api.sh` (localhost) is not.
Polling is the only bridge that works today, so this is a worker rather than a
trigger, and that is a fact about the deployment, not a preference.

**What crosses the boundary is `leads.id` and nothing else.** Not the email, not
the phone. The report is still sent from the queue that already holds the
address; copying contact details into a second project would put prospect PII
somewhere new for no operational gain (`data/schema_factsheets.sql`).

**Why this is allowed to run unattended at all.** `geoWebsite/CLAUDE.md` forbids
auto-triggering the teaser pipeline, and the 2026-07-31 amendment carves out
exactly this: Tier 1 is a crawl of the lead's OWN website plus a parse. It calls
no model, spends no engine budget, and writes a sheet in `draft` that nothing may
send until a human reviews it. The rule the invariant protects — nothing reaches
a prospect without a person deciding — is untouched, because a fact sheet reaches
no prospect. Tier 2 (which does call models and does spend) is explicitly NOT
covered and must not be added here without its own amendment.

The loop is deliberately boring: read leads → enqueue → claim → build → save →
finish. Every terminal state is written, the skips included, because a job that
is not run and not recorded is a decision nobody can audit afterwards.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from src.audit.factsheet.extract import ThinTextError, build_sheet
from src.audit.factsheet.models import BusinessKind
from src.config import settings
from src.storage import db

__all__ = [
    "LeadRow",
    "WorkerResult",
    "fetch_pending_leads",
    "enqueue_pending",
    "run_one_job",
    "run_once",
]

logger = logging.getLogger(__name__)

# Only the four columns Tier 1 actually extracts from, plus the id we carry
# across as `lead_ref`. Email and phone are NOT selected — the cheapest way to
# guarantee PII cannot leak across projects is never to load it.
_LEAD_COLUMNS = "id, business, website, area, description"

# A lead is a candidate the moment it exists. `enqueue_factsheet_job` owns dedup
# through its partial unique index, so re-reading the same lead is harmless and
# this deliberately does not track a cursor — a cursor that drifts silently skips
# a prospect, which is the failure that costs a customer.
_DEFAULT_LEAD_LIMIT = 50


@dataclass(frozen=True)
class LeadRow:
    """The four fields Tier 1 extracts from, plus the id carried as ``lead_ref``."""

    id: str
    business: str
    website: str
    area: str | None
    description: str | None


@dataclass(frozen=True)
class WorkerResult:
    """What one pass did. Counts, not sheets — the sheets are in the database."""

    leads_seen: int = 0
    enqueued: int = 0
    duplicates: int = 0
    built: int = 0
    failed: int = 0
    unusable: int = 0

    def summary(self) -> str:
        return (
            f"{self.leads_seen} lead(s) seen, {self.enqueued} enqueued "
            f"({self.duplicates} already in flight), {self.built} sheet(s) built, "
            f"{self.unusable} unusable, {self.failed} failed"
        )


def _domain_of(website: str) -> str:
    host = urlsplit(website if "//" in website else f"https://{website}").hostname or website
    return host.removeprefix("www.")


def fetch_pending_leads(limit: int = _DEFAULT_LEAD_LIMIT) -> list[LeadRow]:
    """Read recent leads from the WEBSITE project over the ``leads_reader`` role.

    Raises ``RuntimeError`` when ``LEADS_DB_URL`` is unset rather than returning
    an empty list: "no leads" and "not configured" are different answers, and
    silently reporting the first for the second is how an unattended worker looks
    healthy while doing nothing.

    psycopg is imported lazily so the whole package does not depend on it for the
    manual `geo factsheet` path.
    """
    if not settings.LEADS_DB_URL:
        raise RuntimeError(
            "LEADS_DB_URL is not set — the fact-sheet worker cannot read the leads "
            "queue. Use the SELECT-only leads_reader role (see .env.example)."
        )
    try:
        import psycopg
    except ImportError as exc:  # same optional-dependency handling as apply_schema.py
        raise RuntimeError(
            "psycopg is not installed — the worker needs it to read the leads "
            "project directly. Install with: pip install 'psycopg[binary]'"
        ) from exc

    rows: list[LeadRow] = []
    with psycopg.connect(settings.LEADS_DB_URL) as conn, conn.cursor() as cur:
        cur.execute(
            f"select {_LEAD_COLUMNS} from public.leads "  # noqa: S608 - fixed literal, no interpolation of input
            "order by created_at desc limit %s",
            (limit,),
        )
        for rec in cur.fetchall():
            rows.append(
                LeadRow(
                    id=str(rec[0]),
                    business=str(rec[1] or ""),
                    website=str(rec[2] or ""),
                    area=str(rec[3]) if rec[3] else None,
                    description=str(rec[4]) if rec[4] else None,
                )
            )
    return rows


def enqueue_pending(leads: list[LeadRow]) -> tuple[int, int]:
    """Queue a Tier-1 job per lead. Returns ``(enqueued, already_in_flight)``.

    A ``None`` from :func:`db.enqueue_factsheet_job` is the normal duplicate
    answer, not an error — two submissions from one business in the same minute is
    the ordinary case.
    """
    enqueued = duplicates = 0
    for lead in leads:
        if not lead.website.strip():
            continue
        job_id = db.enqueue_factsheet_job(_domain_of(lead.website), lead_ref=lead.id, tier=1)
        if job_id is None:
            duplicates += 1
        else:
            enqueued += 1
    return enqueued, duplicates


def _lead_for(job: dict[str, Any], leads: list[LeadRow]) -> LeadRow | None:
    ref = str(job.get("lead_ref") or "")
    return next((lead for lead in leads if lead.id == ref), None)


def run_one_job(job: dict[str, Any], leads: list[LeadRow]) -> db.FactSheetJobState:
    """Build and store one claimed job's sheet; returns the terminal state written.

    Returning the state rather than the sheet is what lets the caller count
    outcomes honestly — the sheet itself is in the database, and "did it produce
    one" is a poorer question than "what did it decide".

    Every exit writes a terminal state. A crawl that yields nothing usable is
    ``SKIPPED_UNUSABLE`` rather than ``FAILED``: refusing thin text is the
    extractor working (§4.6), and filing it as a failure would make a healthy
    worker look broken and bury the real ones.
    """
    job_id = str(job.get("id") or "")
    lead = _lead_for(job, leads)
    if lead is None:
        # The job outlived its lead in our window — the domain is on the job row,
        # but L0 (business name, area, description) is not, and a sheet without it
        # is thinner than one worth storing.
        db.finish_factsheet_job(
            job_id, db.FactSheetJobState.SKIPPED_UNUSABLE, error="lead not found in poll window"
        )
        return db.FactSheetJobState.SKIPPED_UNUSABLE

    from src.audit.crawl import run_site_audit_blocking

    try:
        crawl = run_site_audit_blocking(
            run_id=job_id,  # the job id IS this crawl's identity; no audit_runs row exists
            domain=lead.website,
            business_kind=BusinessKind.LOCAL_SERVICE.value,
            persist=False,
        )
        sheet = build_sheet(
            business=lead.business,
            website=lead.website,
            pages=crawl.pages,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            area=lead.area,
            description=lead.description,
            business_kind=BusinessKind.LOCAL_SERVICE,
            lead_ref=lead.id,
        )
    except ThinTextError as exc:
        logger.info("fact-sheet job %s: nothing usable to extract (%s)", job_id, exc)
        db.finish_factsheet_job(job_id, db.FactSheetJobState.SKIPPED_UNUSABLE, error=str(exc))
        return db.FactSheetJobState.SKIPPED_UNUSABLE
    except Exception as exc:
        # Log the TYPE, never the message: a crawl error can echo page content,
        # and this runs unattended against a stranger's site.
        logger.warning("fact-sheet job %s failed: %s", job_id, type(exc).__name__)
        db.finish_factsheet_job(job_id, db.FactSheetJobState.FAILED, error=type(exc).__name__)
        return db.FactSheetJobState.FAILED

    if not sheet.claims:
        # A sheet with no claims is a document asserting nothing. Storing it would
        # occupy the domain's one active slot with an empty record.
        db.finish_factsheet_job(
            job_id, db.FactSheetJobState.SKIPPED_UNUSABLE, error="no claims survived the quote gate"
        )
        return db.FactSheetJobState.SKIPPED_UNUSABLE

    try:
        sheet_id = db.save_fact_sheet(sheet)
    except db.StorageError as exc:
        logger.warning("fact-sheet job %s could not store: %s", job_id, type(exc).__name__)
        db.finish_factsheet_job(job_id, db.FactSheetJobState.FAILED, error=type(exc).__name__)
        return db.FactSheetJobState.FAILED

    # Tier 1 calls no model: the only cost is bandwidth, so the recorded spend is
    # genuinely 0 rather than unmeasured.
    db.finish_factsheet_job(job_id, db.FactSheetJobState.DONE, fact_sheet_id=sheet_id, cost_usd=0.0)
    logger.info(
        "fact-sheet job %s: %d claim(s), %d question(s) -> %s",
        job_id,
        len(sheet.claims),
        len(sheet.questions),
        sheet_id,
    )
    return db.FactSheetJobState.DONE


def run_once(limit: int = _DEFAULT_LEAD_LIMIT, max_jobs: int = 10) -> WorkerResult:
    """One pass: read leads, enqueue, then drain up to ``max_jobs`` Tier-1 jobs.

    ``max_jobs`` bounds a pass so a backlog cannot turn one invocation into an
    unbounded crawl of every prospect's website at once. Tier 1 only — Tier 2 is a
    separate authority this worker does not have.
    """
    leads = fetch_pending_leads(limit)
    enqueued, duplicates = enqueue_pending(leads)

    built = failed = unusable = 0
    for _ in range(max_jobs):
        job = db.claim_factsheet_job(tier=1)
        if job is None:
            break
        state = run_one_job(job, leads)
        if state is db.FactSheetJobState.DONE:
            built += 1
        elif state is db.FactSheetJobState.FAILED:
            failed += 1
        else:
            unusable += 1

    return WorkerResult(
        leads_seen=len(leads),
        enqueued=enqueued,
        duplicates=duplicates,
        built=built,
        failed=failed,
        unusable=unusable,
    )
