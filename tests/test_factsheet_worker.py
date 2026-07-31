"""The cross-project fact-sheet worker (plan §12.3).

Two properties here are not refactorable niceties — they are the terms on which
this worker is allowed to run unattended at all:

1. **No prospect PII crosses projects.** It carries ``leads.id`` and nothing
   else. The test is on the SELECT itself, because the cheapest guarantee is
   never loading email or phone in the first place.
2. **Every job reaches a terminal state.** A job that is not run and not recorded
   is a spend decision nobody can audit, and it also never releases its domain —
   the in-flight index only covers queued/running.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.audit.factsheet import worker
from src.audit.factsheet.worker import LeadRow, WorkerResult, enqueue_pending, run_one_job
from src.storage import db


def _lead(**over: Any) -> LeadRow:
    base = {
        "id": "lead-1",
        "business": "Fort Plumbing",
        "website": "https://www.fortplumbing.example/",
        "area": "Berkeley",
        "description": "Emergency plumbing",
    }
    base.update(over)
    return LeadRow(**base)  # type: ignore[arg-type]  # kwargs are the dataclass fields


# --- the PII boundary ---------------------------------------------------------


def test_the_lead_query_never_selects_email_or_phone() -> None:
    """`leads` has email and phone columns; this worker must not read them."""
    assert "email" not in worker._LEAD_COLUMNS
    assert "phone" not in worker._LEAD_COLUMNS
    assert set(worker._LEAD_COLUMNS.split(", ")) == {
        "id",
        "business",
        "website",
        "area",
        "description",
    }


def test_the_lead_row_type_has_nowhere_to_put_contact_details() -> None:
    # Enforced by the type, not by remembering: adding an `email` field here
    # would be a deliberate act, not an accident of a wider SELECT.
    assert set(LeadRow.__dataclass_fields__) == {
        "id",
        "business",
        "website",
        "area",
        "description",
    }


def test_only_the_lead_id_is_carried_across(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        db,
        "enqueue_factsheet_job",
        lambda domain, lead_ref=None, tier=1: (
            seen.append({"domain": domain, "lead_ref": lead_ref, "tier": tier}) or "job-1"
        ),
    )
    enqueue_pending([_lead()])
    assert seen == [{"domain": "fortplumbing.example", "lead_ref": "lead-1", "tier": 1}]


def test_the_worker_only_ever_queues_tier_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2 calls models and spends; it is outside this worker's authority."""
    tiers: list[int] = []
    monkeypatch.setattr(
        db,
        "enqueue_factsheet_job",
        lambda domain, lead_ref=None, tier=1: tiers.append(tier) or "job-1",
    )
    enqueue_pending([_lead(), _lead(id="lead-2", website="acme.example")])
    assert tiers == [1, 1]


# --- enqueue behaviour --------------------------------------------------------


def test_a_duplicate_is_counted_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    # None is the normal "already in flight" answer — two submissions from one
    # business in a minute is ordinary, not an error.
    monkeypatch.setattr(db, "enqueue_factsheet_job", lambda *a, **k: None)
    enqueued, duplicates = enqueue_pending([_lead(), _lead(id="lead-2")])
    assert (enqueued, duplicates) == (0, 2)


def test_a_lead_with_no_website_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "enqueue_factsheet_job", lambda *a, **k: "job-1")
    assert enqueue_pending([_lead(website="  ")]) == (0, 0)


def test_the_domain_is_normalised_before_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """`www.` and the scheme must not create two in-flight jobs for one business."""
    domains: list[str] = []
    monkeypatch.setattr(
        db, "enqueue_factsheet_job", lambda domain, **k: domains.append(domain) or "job"
    )
    enqueue_pending(
        [_lead(website="https://www.fortplumbing.example/"), _lead(website="fortplumbing.example")]
    )
    assert domains == ["fortplumbing.example", "fortplumbing.example"]


# --- terminal states ----------------------------------------------------------


def _capture_finish(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        db,
        "finish_factsheet_job",
        lambda job_id, state, fact_sheet_id=None, cost_usd=None, error=None: calls.append(
            {"job_id": job_id, "state": state, "fact_sheet_id": fact_sheet_id, "error": error}
        ),
    )
    return calls


def test_a_job_whose_lead_vanished_is_skipped_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_finish(monkeypatch)
    state = run_one_job({"id": "job-1", "lead_ref": "gone"}, [])
    assert state is db.FactSheetJobState.SKIPPED_UNUSABLE
    assert calls[0]["state"] is db.FactSheetJobState.SKIPPED_UNUSABLE


def test_a_crawl_failure_writes_failed_and_logs_only_the_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_finish(monkeypatch)

    def _boom(**kwargs: Any) -> Any:
        raise ConnectionResetError("connection reset by peer while fetching /contact")

    monkeypatch.setattr("src.audit.crawl.run_site_audit_blocking", _boom)
    state = run_one_job({"id": "job-1", "lead_ref": "lead-1"}, [_lead()])
    assert state is db.FactSheetJobState.FAILED
    # The exception TYPE, never its message — a crawl error can echo page content
    # and this runs unattended against a stranger's site.
    assert calls[0]["error"] == "ConnectionResetError"


def test_a_thin_site_is_unusable_rather_than_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_finish(monkeypatch)

    class _Crawl:
        pages: list[Any] = []

    monkeypatch.setattr("src.audit.crawl.run_site_audit_blocking", lambda **k: _Crawl())

    def _thin(**kwargs: Any) -> Any:
        raise worker.ThinTextError("only 12 readable chars")

    monkeypatch.setattr(worker, "build_sheet", _thin)
    state = run_one_job({"id": "job-1", "lead_ref": "lead-1"}, [_lead()])
    # Refusing thin text is the extractor WORKING (§4.6). Filing it as a failure
    # would make a healthy worker look broken and bury the real failures.
    assert state is db.FactSheetJobState.SKIPPED_UNUSABLE
    assert calls[0]["state"] is db.FactSheetJobState.SKIPPED_UNUSABLE


def test_a_sheet_with_no_claims_is_not_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_finish(monkeypatch)

    class _Crawl:
        pages: list[Any] = []

    class _Empty:
        claims: list[Any] = []
        questions: list[Any] = []

    monkeypatch.setattr("src.audit.crawl.run_site_audit_blocking", lambda **k: _Crawl())
    monkeypatch.setattr(worker, "build_sheet", lambda **k: _Empty())
    stored: list[Any] = []
    monkeypatch.setattr(db, "save_fact_sheet", lambda s, **k: stored.append(s) or "sheet-1")

    state = run_one_job({"id": "job-1", "lead_ref": "lead-1"}, [_lead()])
    assert state is db.FactSheetJobState.SKIPPED_UNUSABLE
    # A sheet asserting nothing would occupy the domain's one active slot.
    assert stored == []
    assert calls[0]["error"] == "no claims survived the quote gate"


def test_a_built_sheet_is_stored_as_a_draft_and_costs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_finish(monkeypatch)

    class _Crawl:
        pages: list[Any] = []

    class _Sheet:
        claims = ["a claim"]
        questions: list[Any] = []
        domain = "fortplumbing.example"
        version = 1

    sheet = _Sheet()
    monkeypatch.setattr("src.audit.crawl.run_site_audit_blocking", lambda **k: _Crawl())
    monkeypatch.setattr(worker, "build_sheet", lambda **k: sheet)
    monkeypatch.setattr(db, "next_fact_sheet_version", lambda domain: 3)
    monkeypatch.setattr(db, "save_fact_sheet", lambda s, **k: "sheet-1")

    state = run_one_job({"id": "job-1", "lead_ref": "lead-1"}, [_lead()])
    assert state is db.FactSheetJobState.DONE
    assert calls[0]["fact_sheet_id"] == "sheet-1"
    # The allocated version is stamped BEFORE the save — without it the second
    # sheet for a known domain dies on unique (domain, version) and is filed as a
    # crawler failure.
    assert sheet.version == 3


def test_the_crawl_never_persists_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """No audit_runs row exists for a job id — persisting would orphan every page."""
    _capture_finish(monkeypatch)
    seen: dict[str, Any] = {}

    class _Crawl:
        pages: list[Any] = []

    class _Sheet:
        claims: list[Any] = []
        questions: list[Any] = []

    monkeypatch.setattr(
        "src.audit.crawl.run_site_audit_blocking", lambda **k: seen.update(k) or _Crawl()
    )
    monkeypatch.setattr(worker, "build_sheet", lambda **k: _Sheet())
    run_one_job({"id": "job-1", "lead_ref": "lead-1"}, [_lead()])
    assert seen["persist"] is False
    # And the crawl is identified by the JOB id — there is no audit_runs row.
    assert seen["run_id"] == "job-1"


# --- configuration ------------------------------------------------------------


def test_an_unset_leads_url_raises_rather_than_reporting_no_leads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.config import settings

    monkeypatch.setattr(settings, "LEADS_DB_URL", None)
    with pytest.raises(RuntimeError, match="LEADS_DB_URL"):
        worker.fetch_pending_leads()


def test_the_summary_reports_every_outcome() -> None:
    text = WorkerResult(
        leads_seen=3, enqueued=2, duplicates=1, built=1, failed=1, unusable=0
    ).summary()
    for fragment in ("3 lead(s) seen", "2 enqueued", "1 already in flight", "1 sheet(s) built"):
        assert fragment in text
