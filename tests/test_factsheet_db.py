"""Fact-sheet storage: row shaping, the activation transition, and the queue.

Network-free, like ``tests/test_judgment_persistence.py``: the row-building and
row-parsing functions are pure and get called directly, and everything that has
to prove an *ordering* (demote before promote, insert before conflict check)
drives ``db`` through a fake client whose call log is the assertion. A live
Supabase would make these tests slower, flakier and — for the two race
behaviours below — impossible to provoke on demand.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.audit.factsheet import (
    BusinessKind,
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SheetStatus,
    SourceKind,
    Verification,
    to_markdown,
)
from src.storage import db
from src.storage.db import (
    BUCKET_FACTSHEET_SOURCES,
    BUCKET_SITE_AUDIT_HTML,
    FactSheetJobState,
    FactSheetState,
    StorageError,
    _fact_claim_to_row,
    _fact_sheet_to_row,
    _row_to_fact_sheet,
    factsheet_source_prefix,
)

# --- fixtures ----------------------------------------------------------------


def _claim(
    *,
    section: SheetSection = SheetSection.HOURS,
    key: str = "hours_sunday",
    value: str = "Closed Sunday.",
    polarity: Polarity = Polarity.NEGATIVE,
    verification: Verification = Verification.PUBLIC_SOURCE_ONLY,
) -> FactClaim:
    return FactClaim(
        section=section,
        key=key,
        value=value,
        polarity=polarity,
        verbatim_quote="Sunday: Closed",
        source_url="https://fortplumbing.example/contact",
        source_kind=SourceKind.SITE_JSONLD,
        as_of="2026-07-31",
        verification=verification,
        confidence=Confidence.HIGH,
    )


def _sheet(**overrides: Any) -> FactSheet:
    base: dict[str, Any] = {
        "domain": "fortplumbing.example",
        "business_name": "Fort Plumbing",
        "business_kind": BusinessKind.LOCAL_SERVICE,
        "claims": [
            _claim(),
            _claim(section=SheetSection.CONTACT, key="phone", value="Phone is (510) 555-0100."),
        ],
        "questions": ["Does the Sunday emergency line cost extra?"],
        "generated_at": "2026-07-31T12:00:00+00:00",
        "lead_ref": "lead-7",
    }
    base.update(overrides)
    return FactSheet(**base)


_SHEET_ID = "11111111-1111-4111-8111-111111111111"


# --- a fake Supabase client --------------------------------------------------


class _Call:
    """One executed query: which table, which verb, the payload, the filters."""

    def __init__(self, table: str, op: str, payload: Any, filters: list[tuple[str, Any, Any]]):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters = filters

    def filter_value(self, kind: str, column: str) -> Any:
        for k, col, val in self.filters:
            if k == kind and col == column:
                return val
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"_Call({self.table!r}, {self.op!r}, filters={self.filters!r})"


class _Response:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, name: str, client: _FakeClient) -> None:
        self._name = name
        self._client = client
        self._op = ""
        self._payload: Any = None
        self._filters: list[tuple[str, Any, Any]] = []

    def select(self, columns: str = "*") -> _FakeTable:
        self._op, self._payload = "select", columns
        return self

    def insert(self, rows: Any) -> _FakeTable:
        self._op, self._payload = "insert", rows
        return self

    def upsert(self, rows: Any, on_conflict: str | None = None) -> _FakeTable:
        self._op, self._payload = "upsert", rows
        self._filters.append(("on_conflict", on_conflict, None))
        return self

    def update(self, values: Any) -> _FakeTable:
        self._op, self._payload = "update", values
        return self

    def delete(self) -> _FakeTable:
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any) -> _FakeTable:
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column: str, value: Any) -> _FakeTable:
        self._filters.append(("neq", column, value))
        return self

    def in_(self, column: str, values: Any) -> _FakeTable:
        self._filters.append(("in", column, values))
        return self

    def order(self, column: str, desc: bool = False) -> _FakeTable:
        self._filters.append(("order", column, desc))
        return self

    def limit(self, n: int) -> _FakeTable:
        self._filters.append(("limit", n, None))
        return self

    def execute(self) -> _Response:
        call = _Call(self._name, self._op, self._payload, self._filters)
        self._client.calls.append(call)
        return _Response(self._client.respond(call))


class _FakeBucket:
    def __init__(self, name: str, client: _FakeClient) -> None:
        self._name = name
        self._client = client

    def list(self, prefix: str) -> list[dict[str, str]]:
        self._client.storage_calls.append(("list", self._name, prefix))
        return self._client.listing.get(prefix, [])

    def remove(self, paths: list[str]) -> list[dict[str, str]]:
        self._client.storage_calls.append(("remove", self._name, paths))
        return []

    def upload(self, path: str, file: bytes, file_options: dict[str, str]) -> None:
        self._client.storage_calls.append(("upload", self._name, path))

    def download(self, path: str) -> bytes:
        self._client.storage_calls.append(("download", self._name, path))
        return b"gz"


class _FakeStorage:
    def __init__(self, client: _FakeClient) -> None:
        self._client = client

    def from_(self, bucket: str) -> _FakeBucket:
        return _FakeBucket(bucket, self._client)


class _FakeClient:
    """Records every call and answers reads from a test-supplied responder."""

    def __init__(self, responder: Any = None, listing: Any = None) -> None:
        self.calls: list[_Call] = []
        self.storage_calls: list[tuple[str, str, Any]] = []
        self.listing: dict[str, list[dict[str, str]]] = listing or {}
        self._responder = responder
        self.storage = _FakeStorage(self)

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(name, self)

    def respond(self, call: _Call) -> Any:
        return [] if self._responder is None else self._responder(call)


def _install(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> _FakeClient:
    monkeypatch.setattr(db, "_client", lambda: client)
    return client


def _ops(client: _FakeClient, table: str, op: str) -> list[_Call]:
    return [c for c in client.calls if c.table == table and c.op == op]


# --- row shaping: the sheet round trip ---------------------------------------


def test_sheet_round_trips_through_its_rows() -> None:
    sheet = _sheet()
    sheet.assign_claim_ids()
    row = _fact_sheet_to_row(
        sheet, _SHEET_ID, state=FactSheetState.DRAFT, source_snapshot_prefix="x/v1"
    )
    claim_rows = [_fact_claim_to_row(_SHEET_ID, c) for c in sheet.claims]
    assert _row_to_fact_sheet(row, claim_rows) == sheet


def test_claims_come_back_in_claim_id_order_with_their_evidence() -> None:
    sheet = _sheet()
    sheet.assign_claim_ids()
    claim_rows = [_fact_claim_to_row(_SHEET_ID, c) for c in sheet.claims]
    row = _fact_sheet_to_row(
        sheet, _SHEET_ID, state=FactSheetState.DRAFT, source_snapshot_prefix="x/v1"
    )
    restored = _row_to_fact_sheet(row, claim_rows)
    assert [c.claim_id for c in restored.claims] == ["FS-01", "FS-02"]
    # Contact sorts before hours, so FS-01 is the phone line, not the one that
    # happened to be listed first.
    assert restored.claims[0].key == "phone"
    assert restored.claims[0].verbatim_quote == "Sunday: Closed"
    assert restored.claims[0].source_url == "https://fortplumbing.example/contact"


def test_sheet_status_does_not_survive_a_round_trip() -> None:
    # Pins a known gap rather than asserting it is fine: data/schema_factsheets.sql
    # has `state` (draft/active/superseded — the row's place in the version
    # history) and NO column for the document's draft/client_reviewed/signed axis.
    # Anything gating on a signature must read the store's state, not a rehydrated
    # sheet, until plan §11.5 reconciles the two.
    sheet = _sheet(sheet_status=SheetStatus.SIGNED)
    sheet.assign_claim_ids()
    row = _fact_sheet_to_row(
        sheet, _SHEET_ID, state=FactSheetState.ACTIVE, source_snapshot_prefix="x/v1"
    )
    assert "signed" not in row.values()
    restored = _row_to_fact_sheet(row, [_fact_claim_to_row(_SHEET_ID, c) for c in sheet.claims])
    assert restored.sheet_status is SheetStatus.DRAFT


def test_row_stores_the_human_render_and_not_the_csv() -> None:
    # Renderer 1 is derived from fact_claims at build time and deliberately not
    # stored — two stored representations of the same facts is how they drift.
    sheet = _sheet()
    row = _fact_sheet_to_row(
        sheet, _SHEET_ID, state=FactSheetState.DRAFT, source_snapshot_prefix="x/v1"
    )
    assert row["rendered_md"] == to_markdown(sheet)
    assert "block,key,value" not in str(row["rendered_md"])


def _row_tier(sheet: FactSheet) -> str:
    row = _fact_sheet_to_row(
        sheet, _SHEET_ID, state=FactSheetState.DRAFT, source_snapshot_prefix="x/v1"
    )
    return str(row["verification_tier"])


def test_verification_tier_column_is_the_weakest_claim() -> None:
    # Denormalized so "which sheets are still public_source_only" is a query, but
    # it is a min over the claims — one unconfirmed line drags the sheet down.
    sheet = _sheet(
        claims=[
            _claim(verification=Verification.CLIENT_CONFIRMED),
            _claim(
                key="phone",
                section=SheetSection.CONTACT,
                verification=Verification.CROSS_CONFIRMED,
            ),
        ]
    )
    assert _row_tier(sheet) == "cross_confirmed"
    sheet.claims.append(_claim(key="license", section=SheetSection.LICENSING))
    assert _row_tier(sheet) == "public_source_only"


def test_claim_row_ids_are_deterministic_per_sheet_and_claim() -> None:
    # A retried save must upsert the same claim rows, not duplicate them under
    # fresh uuid4s.
    sheet = _sheet()
    sheet.assign_claim_ids()
    first = [_fact_claim_to_row(_SHEET_ID, c)["id"] for c in sheet.claims]
    second = [_fact_claim_to_row(_SHEET_ID, c)["id"] for c in sheet.claims]
    assert first == second
    assert len(set(first)) == len(first)
    other = "22222222-2222-4222-8222-222222222222"
    assert set(_fact_claim_to_row(other, c)["id"] for c in sheet.claims).isdisjoint(first)


def test_row_to_fact_sheet_tolerates_nulls() -> None:
    restored = _row_to_fact_sheet({"domain": "x.example", "business_kind": "product"}, [])
    assert restored.domain == "x.example"
    assert restored.business_kind is BusinessKind.PRODUCT
    assert restored.version == 1
    assert restored.questions == []
    assert restored.lead_ref is None


def test_source_prefix_is_domain_and_version() -> None:
    assert factsheet_source_prefix("fortplumbing.example", 3) == "fortplumbing.example/v3"


# --- writing a sheet does not activate it ------------------------------------


def test_saving_a_sheet_leaves_it_in_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _install(monkeypatch, _FakeClient())
    sheet_id = db.save_fact_sheet(_sheet())
    (insert,) = _ops(client, "fact_sheets", "insert")
    assert insert.payload["state"] == FactSheetState.DRAFT.value
    assert insert.payload["id"] == sheet_id
    assert insert.payload["source_snapshot_prefix"] == "fortplumbing.example/v1"
    # Nothing promoted it: activation is the human gate, not a side effect of
    # generating a sheet nobody has looked at.
    assert _ops(client, "fact_sheets", "update") == []


def test_saving_a_sheet_writes_its_claims_upserted(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _install(monkeypatch, _FakeClient())
    db.save_fact_sheet(_sheet())
    (upsert,) = _ops(client, "fact_claims", "upsert")
    assert [r["claim_id"] for r in upsert.payload] == ["FS-01", "FS-02"]
    # The conflict target is the natural key, so a retried save overwrites the
    # same claims instead of accumulating a second copy of the sheet.
    assert ("on_conflict", "fact_sheet_id,claim_id", None) in upsert.filters


def test_saving_does_not_mutate_the_callers_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    # assigned_claims is pure; a caller that saves then keeps using its sheet must
    # not find the claim order silently rearranged underneath it.
    _install(monkeypatch, _FakeClient())
    sheet = _sheet()
    db.save_fact_sheet(sheet)
    assert [c.claim_id for c in sheet.claims] == ["", ""]


# --- activation: demote, then promote ----------------------------------------


def _sheet_row_responder(call: _Call) -> Any:
    if call.table == "fact_sheets" and call.op == "select":
        return [{"id": _SHEET_ID, "domain": "fortplumbing.example", "version": 2}]
    return []


def test_activate_demotes_the_incumbent_before_promoting(monkeypatch: pytest.MonkeyPatch) -> None:
    # The order is the whole behaviour: uq_fact_sheets_active_domain is a partial
    # unique index, so promoting first is rejected by Postgres outright.
    client = _install(monkeypatch, _FakeClient(_sheet_row_responder))
    db.activate_fact_sheet(_SHEET_ID)
    demote, promote = _ops(client, "fact_sheets", "update")
    assert demote.payload["state"] == FactSheetState.SUPERSEDED.value
    assert demote.filter_value("eq", "domain") == "fortplumbing.example"
    assert demote.filter_value("eq", "state") == FactSheetState.ACTIVE.value
    # ...and never demotes the sheet it is about to promote.
    assert demote.filter_value("neq", "id") == _SHEET_ID
    assert promote.payload["state"] == FactSheetState.ACTIVE.value
    assert promote.filter_value("eq", "id") == _SHEET_ID


def test_activate_refuses_an_unknown_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _install(monkeypatch, _FakeClient())
    with pytest.raises(StorageError):
        db.activate_fact_sheet(_SHEET_ID)
    assert _ops(client, "fact_sheets", "update") == []


def test_load_fact_sheet_asks_for_the_newest_version_in_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, _FakeClient(_sheet_row_responder))
    loaded = db.load_fact_sheet("fortplumbing.example")
    assert loaded is not None and loaded.version == 2
    select = _ops(client, "fact_sheets", "select")[0]
    assert select.filter_value("eq", "state") == "active"
    assert select.filter_value("order", "version") is True


def test_load_fact_sheet_returns_none_when_the_domain_has_no_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _FakeClient())
    assert db.load_fact_sheet("nobody.example") is None


# --- the queue: the conflict is the answer, not a thing to avoid -------------


class _DuplicateKey(Exception):
    """Stands in for the Supabase APIError a unique violation surfaces as."""

    code = "23505"


def test_enqueue_returns_none_when_a_job_is_already_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def responder(call: _Call) -> Any:
        if call.table == "factsheet_jobs" and call.op == "insert":
            raise _DuplicateKey("duplicate key value violates unique constraint")
        return []

    client = _install(monkeypatch, _FakeClient(responder))
    assert db.enqueue_factsheet_job("fortplumbing.example", lead_ref="lead-7") is None
    # Crucially, it did NOT look first: two submissions in the same minute is the
    # ordinary case, and only Postgres sees both writers.
    assert _ops(client, "factsheet_jobs", "select") == []
    assert len(_ops(client, "factsheet_jobs", "insert")) == 1


def test_enqueue_reraises_a_real_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def responder(call: _Call) -> Any:
        if call.op == "insert":
            raise RuntimeError("connection reset")
        return []

    _install(monkeypatch, _FakeClient(responder))
    with pytest.raises(StorageError):
        db.enqueue_factsheet_job("fortplumbing.example")


def test_enqueue_carries_the_lead_ref_and_nothing_else_about_the_prospect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, _FakeClient())
    db.enqueue_factsheet_job("fortplumbing.example", lead_ref="lead-7", tier=2)
    (insert,) = _ops(client, "factsheet_jobs", "insert")
    assert insert.payload["lead_ref"] == "lead-7"
    assert insert.payload["tier"] == 2
    assert insert.payload["state"] == FactSheetJobState.QUEUED.value
    assert set(insert.payload).isdisjoint({"email", "phone", "name"})


def test_claim_moves_on_when_another_worker_won_the_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The compare-and-set update returns zero rows to the loser. That is the only
    # signal there is, and skipping to the next candidate is the whole point of
    # scanning more than one.
    def responder(call: _Call) -> Any:
        if call.op == "select":
            return [{"id": "job-a", "attempts": 0}, {"id": "job-b", "attempts": 2}]
        if call.op == "update" and call.filter_value("eq", "id") == "job-a":
            return []
        if call.op == "update" and call.filter_value("eq", "id") == "job-b":
            return [{"id": "job-b", "state": "running"}]
        return []

    client = _install(monkeypatch, _FakeClient(responder))
    claimed = db.claim_factsheet_job()
    assert claimed is not None and claimed["id"] == "job-b"
    updates = _ops(client, "factsheet_jobs", "update")
    assert [u.filter_value("eq", "id") for u in updates] == ["job-a", "job-b"]
    # Every claim is a compare-and-set on the state, never a bare id update.
    assert all(u.filter_value("eq", "state") == "queued" for u in updates)
    # attempts is spent at claim time: a job that kills its worker mid-run must
    # still count against its retries.
    assert updates[1].payload["attempts"] == 3


def test_claim_returns_none_on_an_empty_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _FakeClient())
    assert db.claim_factsheet_job() is None


def test_finish_records_a_skip_as_carefully_as_a_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A skipped job is recorded, never dropped — the daily cap is computed off
    # these rows, so an unwritten skip is a spend decision nobody can audit.
    client = _install(monkeypatch, _FakeClient())
    db.finish_factsheet_job("job-a", FactSheetJobState.SKIPPED_CAP, cost_usd=0.0)
    (update,) = _ops(client, "factsheet_jobs", "update")
    assert update.payload["state"] == "skipped_cap"
    assert update.payload["cost_usd"] == 0.0
    assert update.payload["finished_at"]
    assert update.filter_value("eq", "id") == "job-a"


def test_finish_leaves_untouched_what_it_was_not_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, _FakeClient())
    db.finish_factsheet_job("job-a", FactSheetJobState.FAILED, error="thin text")
    (update,) = _ops(client, "factsheet_jobs", "update")
    assert update.payload["error"] == "thin text"
    assert "fact_sheet_id" not in update.payload
    assert "cost_usd" not in update.payload


def test_spend_today_reads_the_view_and_defaults_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _FakeClient())
    assert db.factsheet_spend_today() == {"tier2_runs": 0.0, "spend_usd": 0.0}

    def responder(call: _Call) -> Any:
        return [{"tier2_runs": 4, "spend_usd": "1.2500"}]

    _install(monkeypatch, _FakeClient(responder))
    assert db.factsheet_spend_today() == {"tier2_runs": 4.0, "spend_usd": 1.25}


# --- buckets: one pair of helpers, two buckets -------------------------------


def test_blob_helpers_default_to_the_site_audit_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every existing call site passes no bucket and must stay byte-identical.
    client = _install(monkeypatch, _FakeClient())
    db.upload_site_audit_html("run/page.html.gz", b"gz")
    db.download_site_audit_html("run/page.html.gz")
    assert [(op, bucket) for op, bucket, _ in client.storage_calls] == [
        ("upload", BUCKET_SITE_AUDIT_HTML),
        ("download", BUCKET_SITE_AUDIT_HTML),
    ]


def test_blob_helpers_reach_the_factsheet_bucket_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, _FakeClient())
    db.upload_site_audit_html("d/v1/abc.html.gz", b"gz", bucket=BUCKET_FACTSHEET_SOURCES)
    assert client.storage_calls == [("upload", BUCKET_FACTSHEET_SOURCES, "d/v1/abc.html.gz")]


def test_deleting_a_sheets_sources_removes_the_blobs_under_its_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def responder(call: _Call) -> Any:
        if call.table == "fact_sheets" and call.op == "select":
            return [{"id": _SHEET_ID, "source_snapshot_prefix": "d.example/v2"}]
        return []

    listing = {"d.example/v2": [{"name": "aa.html.gz"}, {"name": "bb.html.gz"}]}
    client = _install(monkeypatch, _FakeClient(responder, listing))
    assert db.delete_factsheet_sources_for_sheets([_SHEET_ID]) == 2
    removed = ["d.example/v2/aa.html.gz", "d.example/v2/bb.html.gz"]
    assert ("remove", BUCKET_FACTSHEET_SOURCES, removed) in client.storage_calls


def test_a_sheet_with_no_recorded_prefix_still_gets_cleaned_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rebuilding the conventional prefix is what stops a row written before the
    # column was populated from leaking its snapshots forever.
    def responder(call: _Call) -> Any:
        if call.table == "fact_sheets" and call.op == "select":
            return [{"id": _SHEET_ID, "domain": "d.example", "version": 3}]
        return []

    listing = {"d.example/v3": [{"name": "aa.html.gz"}]}
    client = _install(monkeypatch, _FakeClient(responder, listing))
    assert db.delete_factsheet_sources_for_sheets([_SHEET_ID]) == 1
    assert ("list", BUCKET_FACTSHEET_SOURCES, "d.example/v3") in client.storage_calls


def test_source_cleanup_never_blocks_the_row_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    # An orphaned blob is recoverable by listing the bucket; a half-deleted
    # project is not. So a Storage failure returns 0 rather than raising.
    def responder(call: _Call) -> Any:
        raise RuntimeError("storage unavailable")

    _install(monkeypatch, _FakeClient(responder))
    assert db.delete_factsheet_sources_for_sheets([_SHEET_ID]) == 0
    assert db.delete_factsheet_sources_for_sheets([]) == 0


# --- run provenance: the pointer back to the living sheet --------------------


def test_a_run_records_which_sheet_version_it_was_judged_against(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, _FakeClient())
    db.create_audit_run(
        "Fort Plumbing", ["fortplumbing.example"], [], "plumbing", "v1", "2026-07-31", 1,
        fact_sheet="hours_sunday: Closed Sunday.",
        fact_sheet_present=True,
        fact_sheet_id=_SHEET_ID,
        fact_sheet_version=2,
    )
    (insert,) = _ops(client, "audit_runs", "insert")
    # The frozen snapshot still goes in with the row; only the pointer is deferred.
    assert insert.payload["fact_sheet"] == "hours_sunday: Closed Sunday."
    assert "fact_sheet_id" not in insert.payload
    (update,) = _ops(client, "audit_runs", "update")
    assert update.payload["fact_sheet_id"] == _SHEET_ID
    assert update.payload["fact_sheet_version"] == 2


def test_a_run_without_a_sheet_costs_exactly_one_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _install(monkeypatch, _FakeClient())
    db.create_audit_run("Fort Plumbing", [], [], "plumbing", "v1", "2026-07-31", 1)
    assert len(_ops(client, "audit_runs", "insert")) == 1
    assert _ops(client, "audit_runs", "update") == []


def test_a_database_predating_the_provenance_columns_still_keeps_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Same trade as judge_model: lose the pointer, which is recoverable, not the
    # run, which is not.
    def responder(call: _Call) -> Any:
        if call.op == "update":
            raise RuntimeError("column audit_runs.fact_sheet_id does not exist")
        return []

    client = _install(monkeypatch, _FakeClient(responder))
    run_id = db.create_audit_run(
        "Fort Plumbing", [], [], "plumbing", "v1", "2026-07-31", 1,
        fact_sheet_id=_SHEET_ID,
    )
    assert run_id
    assert len(_ops(client, "audit_runs", "insert")) == 1
