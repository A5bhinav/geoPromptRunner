"""Projects: a domain-keyed view over audit runs and teasers.

A "project" is not a stored entity — it is derived on the fly by grouping the
existing ``audit_runs`` and ``teasers`` by the prospect domain (e.g. every run
and teaser for ``fort.cx`` rolls up into one FORT project). This gives the UI a
dashboard of "everything we've done for this prospect" with zero schema change.

Grouping key:
  * If we know a domain (an audit's ``client_domains[0]`` or a teaser's
    ``prospect_url``) the key IS the normalized domain.
  * Otherwise we fall back to ``name:<slug-of-client-name>`` so a domain-less
    run still gets its own bucket rather than colliding with unrelated work.

A teaser-generated audit carries the prospect domain, so it lands in the same
bucket as the teaser. A manually-uploaded audit with no domain stays in its own
name bucket until/unless a domain is supplied.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from src.api import runner
from src.storage import db

logger = logging.getLogger(__name__)

__all__ = [
    "ProjectAudit",
    "ProjectTeaser",
    "ProjectSummary",
    "ProjectDetail",
    "ProjectHistoryPoint",
    "list_projects",
    "get_project",
    "project_history",
    "delete_project",
]


@dataclass(frozen=True)
class ProjectAudit:
    run_id: str
    client_name: str
    state: str
    created_at: str
    n_queries: int
    engines: list[str]


@dataclass(frozen=True)
class ProjectTeaser:
    id: str
    company_name: str | None
    status: str
    created_at: str


@dataclass(frozen=True)
class ProjectSummary:
    key: str
    label: str
    domain: str | None
    audit_count: int
    teaser_count: int
    last_activity: str
    last_state: str | None
    engines: list[str]


@dataclass(frozen=True)
class ProjectDetail:
    key: str
    label: str
    domain: str | None
    audits: list[ProjectAudit]
    teasers: list[ProjectTeaser]


@dataclass(frozen=True)
class ProjectHistoryPoint:
    """One completed cycle, reduced to the four numbers the project page plots.

    Every one is COUNTED or MEASURED — no composite score, and the mention rate
    ships with its denominator rather than as a bare percentage, because at this
    sample size a bare percentage is misleading.

    ``query_set_version`` rides along because a run is comparable only to a run
    that asked the same questions. The client decides what to CONNECT with a
    line; the API's job is to make the version visible so it cannot silently
    compare across a changed instrument.
    """

    run_id: str
    run_date: str
    query_set_version: str
    mention_successes: int
    mention_n: int
    share_of_model: float
    open_findings: int
    critical: int


@dataclass
class _Acc:
    key: str
    label: str
    domain: str | None
    audits: list[ProjectAudit] = field(default_factory=list)
    teasers: list[ProjectTeaser] = field(default_factory=list)


def _norm_domain(raw: object) -> str:
    """Bare host of a URL or domain string (lowercased, scheme/path/port/www stripped).

    Accepts both ``https://www.fort.cx/pricing`` and a bare ``fort.cx`` so an
    audit's domain and a teaser's prospect_url normalize to the same key.
    """
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s)  # drop scheme
    s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    s = s.split("@")[-1]  # drop any userinfo
    s = s.split(":", 1)[0]  # drop port
    return s[4:] if s.startswith("www.") else s


def _slugify(raw: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(raw or "").strip().lower()).strip("-")


def _domains_of(raw: object) -> list[str]:
    """A row's ``client_domains`` as a clean list of strings. DB row values are
    typed ``object``, so guard the type: a non-list value (e.g. a bare string)
    must yield ``[]`` rather than being iterated character-by-character."""
    if not isinstance(raw, list):
        return []
    return [str(d) for d in raw if d]


def _key_for(domain: str, name: object) -> tuple[str, str, str | None]:
    """(key, label, domain) for a domain (preferred) or a client/company name."""
    if domain:
        return domain, domain, domain
    slug = _slugify(name) or "untitled"
    return f"name:{slug}", (str(name).strip() if name else "Untitled"), None


def _collect() -> dict[str, _Acc]:
    """Bucket every audit and teaser into a project accumulator keyed by domain."""
    accs: dict[str, _Acc] = {}

    def ensure(key: str, label: str, domain: str | None) -> _Acc:
        acc = accs.get(key)
        if acc is None:
            acc = _Acc(key=key, label=label, domain=domain)
            accs[key] = acc
        elif domain and not acc.domain:
            # We learned a real domain for a bucket first seen via a name only.
            acc.domain, acc.label = domain, domain
        return acc

    # Audit runs (in-memory state overlaid on storage). Domains come from the
    # stored rows; in-memory-only runs (storage down) fall back to the name key.
    domains_by_id: dict[str, list[str]] = {}
    try:
        for row in db.list_all_audit_runs():
            domains_by_id[str(row.get("id", ""))] = _domains_of(row.get("client_domains"))
    except db.StorageError:
        pass

    for s in runner.list_runs():
        doms = domains_by_id.get(s.run_id, [])
        key, label, domain = _key_for(_norm_domain(doms[0]) if doms else "", s.client_name)
        ensure(key, label, domain).audits.append(
            ProjectAudit(
                run_id=s.run_id,
                client_name=s.client_name,
                state=s.state,
                created_at=s.created_at,
                n_queries=s.n_queries,
                engines=list(s.engines),
            )
        )

    # Teasers (best-effort: skipped if storage is unconfigured/unreachable).
    try:
        for row in db.list_teasers_with_url():
            name = row.get("company_name")
            key, label, domain = _key_for(_norm_domain(row.get("prospect_url")), name)
            ensure(key, label, domain).teasers.append(
                ProjectTeaser(
                    id=str(row.get("id", "")),
                    company_name=str(name) if name else None,
                    status=str(row.get("status", "")),
                    created_at=str(row.get("created_at", "")),
                )
            )
    except db.StorageError:
        pass

    return accs


def list_projects() -> list[ProjectSummary]:
    """All projects, most-recently-active first, with rolled-up counts/state."""
    summaries: list[ProjectSummary] = []
    for acc in _collect().values():
        stamps = [a.created_at for a in acc.audits] + [t.created_at for t in acc.teasers]
        last_activity = max(stamps) if stamps else ""
        recent_audit = max(acc.audits, key=lambda a: a.created_at, default=None)
        engines = sorted({e for a in acc.audits for e in a.engines})
        summaries.append(
            ProjectSummary(
                key=acc.key,
                label=acc.label,
                domain=acc.domain,
                audit_count=len(acc.audits),
                teaser_count=len(acc.teasers),
                last_activity=last_activity,
                last_state=recent_audit.state if recent_audit else None,
                engines=engines,
            )
        )
    return sorted(summaries, key=lambda p: p.last_activity, reverse=True)


def get_project(key: str) -> ProjectDetail | None:
    """Full audit + teaser history for one project, newest first, or None."""
    acc = _collect().get(key)
    if acc is None:
        return None
    return ProjectDetail(
        key=acc.key,
        label=acc.label,
        domain=acc.domain,
        audits=sorted(acc.audits, key=lambda a: a.created_at, reverse=True),
        teasers=sorted(acc.teasers, key=lambda t: t.created_at, reverse=True),
    )


# A project page plots a cadence, not an archive. Twelve monthly cycles is a
# year, and each point costs one report assembly — free (it reads stored rows and
# the warm judge cache) but not instant.
_HISTORY_LIMIT = 12


def project_history(key: str, limit: int = _HISTORY_LIMIT) -> list[ProjectHistoryPoint]:
    """Completed cycles for one project, OLDEST FIRST so the list plots left to right.

    Only ``done`` runs: a cancelled or still-running cycle has no defensible
    numbers, and plotting a partial one would put a figure nobody stands behind
    on a chart a client reads. A run whose report cannot be assembled is skipped
    rather than zero-filled — a missing point is honest, a zero is a claim.
    """
    acc = _collect().get(key)
    if acc is None:
        return []

    points: list[ProjectHistoryPoint] = []
    # Newest-first for the cap, so a long history keeps its RECENT cycles.
    for audit in sorted(acc.audits, key=lambda a: a.created_at, reverse=True):
        if len(points) >= limit:
            break
        if audit.state != "done":
            continue
        report = runner.get_report(audit.run_id)
        if report is None:
            continue
        scorecard = report.get("scorecard")
        if not isinstance(scorecard, dict):
            continue
        visibility = scorecard.get("ai_visibility")
        findings = scorecard.get("open_findings")
        points.append(
            ProjectHistoryPoint(
                run_id=audit.run_id,
                run_date=str(report.get("run_date", audit.created_at)),
                query_set_version=str(report.get("query_set_version", "")),
                mention_successes=_int(visibility, "successes"),
                mention_n=_int(visibility, "n"),
                share_of_model=_float(scorecard, "share_of_model_client"),
                open_findings=_int(findings, "themes"),
                critical=_int(findings, "critical"),
            )
        )
    return list(reversed(points))


def _int(payload: object, field_name: str) -> int:
    """A payload field as an int, or 0. Payload shapes are versioned and optional
    (older stored runs predate several of them), so read defensively rather than
    letting one missing key 500 the whole page."""
    if isinstance(payload, dict):
        value = payload.get(field_name)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _float(payload: object, field_name: str) -> float:
    if isinstance(payload, dict):
        value = payload.get(field_name)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


# The UI collection (_collect) caps audits/teasers for a light dashboard; deleting
# must instead find EVERY row for the key or it would orphan a large project's
# older runs. This bound is far above any realistic single project's history.
_DELETE_SCAN_LIMIT = 100_000


def delete_project(key: str) -> dict[str, object] | None:
    """Permanently delete everything in a project: its audit runs (child rows
    cascade) and its teasers. Returns counts, or None if the key matches nothing.

    The id set is gathered from a COMPLETE storage scan (not the capped UI
    collection, which would leave a >100-run / >200-teaser project's older rows
    behind), unioned with the in-memory view so a live run not yet flushed is
    caught too. In-memory state is dropped first (``runner.forget_run``) so a live
    or still-cached run can't write its rows back and resurrect the project. Site-
    audit HTML blobs (not covered by the row cascade) are removed before the rows
    that point to them. A ``db.StorageError`` from the row deletes propagates to
    the caller (a 503).
    """
    run_ids: set[str] = set()
    teaser_ids: set[str] = set()
    label: str | None = None

    try:
        for row in db.list_all_audit_runs(limit=_DELETE_SCAN_LIMIT):
            doms = _domains_of(row.get("client_domains"))
            k, lbl, _ = _key_for(_norm_domain(doms[0]) if doms else "", row.get("client_name"))
            if k == key:
                run_ids.add(str(row.get("id", "")))
                label = label or lbl
    except db.StorageError:
        pass
    try:
        for row in db.list_teasers_with_url(limit=_DELETE_SCAN_LIMIT):
            k, lbl, _ = _key_for(_norm_domain(row.get("prospect_url")), row.get("company_name"))
            if k == key:
                teaser_ids.add(str(row.get("id", "")))
                label = label or lbl
    except db.StorageError:
        pass

    # Fold in the in-memory-aware view too — catches a live run not yet in storage.
    acc = _collect().get(key)
    if acc is not None:
        run_ids.update(a.run_id for a in acc.audits)
        teaser_ids.update(t.id for t in acc.teasers)
        label = label or acc.label

    run_ids_list = sorted(r for r in run_ids if r)
    teaser_ids_list = sorted(t for t in teaser_ids if t)
    if not run_ids_list and not teaser_ids_list:
        return None

    for rid in run_ids_list:
        runner.forget_run(rid)
    db.delete_site_audit_html_for_runs(run_ids_list)
    audits_deleted = db.delete_audit_runs(run_ids_list)
    teasers_deleted = db.delete_teasers(teaser_ids_list)
    # Intake sessions are keyed by DOMAIN, not by run — so they are not reachable
    # through the row cascade above. Left behind, an abandoned session keeps
    # holding the domain's `uq_intake_sessions_live` slot, and re-adding the
    # client would resume into a conversation about a sheet that no longer
    # exists. Best-effort: an orphaned session is recoverable, a half-deleted
    # project is not.
    if acc is not None and acc.domain:
        try:
            db.delete_intake_sessions_for_domains([acc.domain])
        except db.StorageError:
            logger.warning("could not delete intake sessions for %s", acc.domain)
    return {
        "key": key,
        "label": label or key,
        "audits_deleted": audits_deleted,
        "teasers_deleted": teasers_deleted,
    }
