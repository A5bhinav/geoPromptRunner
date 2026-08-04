"""Phase 4's missing half: the operational records that were computed and dropped.

Three mechanisms were built, tested and correct, and all three threw their result
away — QA review records, engine drift fingerprints, per-client config. Each is
only useful as a SERIES ("the reviewers disagreed more this month", "Perplexity's
answers got 40% shorter in June"), and a series cannot be built from a value that
lives for the length of one render.

A fourth follows the same logic for share-link revocation, which lived in a
process-local set: a revoked link coming back after a deploy is the one failure
mode a revocation mechanism may not have.

These tests drive the storage layer through a fake Supabase client, so nothing
here touches a network.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.storage import db


class _FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeTable:
    """Records what was asked of it. Enough of the builder to assert on."""

    def __init__(self, store: dict[str, list[dict[str, Any]]], name: str) -> None:
        self.store = store
        self.name = name
        self.filters: list[tuple[str, Any]] = []
        self.upserted: list[dict[str, Any]] = []
        self.on_conflict: str = ""
        self.deleted = False

    def select(self, *_cols: str) -> _FakeTable:
        return self

    def eq(self, key: str, value: Any) -> _FakeTable:
        self.filters.append((key, value))
        return self

    def order(self, *_a: Any, **_k: Any) -> _FakeTable:
        return self

    def limit(self, *_a: Any) -> _FakeTable:
        return self

    def delete(self) -> _FakeTable:
        self.deleted = True
        return self

    def upsert(self, rows: Any, on_conflict: str = "") -> _FakeTable:
        self.on_conflict = on_conflict
        self.upserted = rows if isinstance(rows, list) else [rows]
        return self

    def execute(self) -> _FakeResponse:
        if self.upserted:
            existing = self.store.setdefault(self.name, [])
            keys = [k.strip() for k in self.on_conflict.split(",") if k.strip()]
            for row in self.upserted:
                match = next(
                    (r for r in existing if all(r.get(k) == row.get(k) for k in keys)),
                    None,
                )
                if match is not None and keys:
                    match.update(row)
                else:
                    existing.append(dict(row))
            return _FakeResponse([])
        if self.deleted:
            rows = self.store.get(self.name, [])
            kept = [r for r in rows if not all(r.get(k) == v for k, v in self.filters)]
            removed = len(rows) - len(kept)
            self.store[self.name] = kept
            return _FakeResponse([{} for _ in range(removed)])
        rows = [
            r
            for r in self.store.get(self.name, [])
            if all(r.get(k) == v for k, v in self.filters)
        ]
        return _FakeResponse(rows)


class _FakeClient:
    def __init__(self) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {}
        self.tables: list[_FakeTable] = []

    def table(self, name: str) -> _FakeTable:
        t = _FakeTable(self.store, name)
        self.tables.append(t)
        return t


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    fake = _FakeClient()
    monkeypatch.setattr(db, "_client", lambda: fake)
    return fake


# --- review records (P4-T1/T2) ------------------------------------------------

_REVIEW = {
    "cell_id": "cmp-02:perplexity:0",
    "stratum": "severe",
    "judge_label": "high",
    "reviewer_a": "critical",
    "reviewer_b": "high",
    "final_label": "critical",
    "outcome": "escalated",
    "prompt_fingerprint": "fp-abc",
    "reviewed_at": "2026-08-04T10:00:00Z",
    "note": "",
}


def test_both_reviewer_labels_are_stored_even_when_they_agree(client: _FakeClient) -> None:
    """Recording only the reconciled answer throws away the disagreement RATE —
    the number that says whether the labels themselves are trustworthy."""
    agreed = {**_REVIEW, "reviewer_a": "high", "reviewer_b": "high", "outcome": "agreed"}
    db.save_review_records("run-1", "Fort", [agreed])
    stored = client.store["review_records"][0]
    assert stored["reviewer_a"] == "high"
    assert stored["reviewer_b"] == "high"


def test_the_same_reconciliation_twice_leaves_one_row(client: _FakeClient) -> None:
    db.save_review_records("run-1", "Fort", [_REVIEW])
    db.save_review_records("run-1", "Fort", [_REVIEW])
    assert len(client.store["review_records"]) == 1


def test_a_review_under_a_new_prompt_fingerprint_is_a_new_record(
    client: _FakeClient,
) -> None:
    """The judge being reviewed after a prompt change is a different judge."""
    db.save_review_records("run-1", "Fort", [_REVIEW])
    db.save_review_records("run-1", "Fort", [{**_REVIEW, "prompt_fingerprint": "fp-xyz"}])
    assert len(client.store["review_records"]) == 2


def test_review_records_carry_the_prompt_in_force_when_judged(
    client: _FakeClient,
) -> None:
    """Without it, "the judge feels off lately" cannot become a queryable
    regression: you cannot separate a prompt change from a model change."""
    db.save_review_records("run-1", "Fort", [_REVIEW])
    assert client.store["review_records"][0]["prompt_fingerprint"] == "fp-abc"


# --- engine fingerprints (P4-T3) ----------------------------------------------

_PRINT = {
    "engine_name": "perplexity",
    "model_id": "sonar",
    "n_cells": 12,
    "n_answered": 12,
    "median_length": 1840.0,
    "mean_citations": 4.5,
}


def test_re_rendering_a_report_does_not_duplicate_a_fingerprint(
    client: _FakeClient,
) -> None:
    db.save_engine_fingerprints("run-1", "Fort", "2026-06-13", [_PRINT])
    db.save_engine_fingerprints("run-1", "Fort", "2026-06-13", [_PRINT])
    assert len(client.store["engine_fingerprints"]) == 1


def test_a_fingerprint_records_the_pin_that_answered(client: _FakeClient) -> None:
    """A model change is a CERTAINTY that the instrument moved, not an inference
    from the distribution."""
    db.save_engine_fingerprints("run-1", "Fort", "2026-06-13", [_PRINT])
    assert client.store["engine_fingerprints"][0]["model_id"] == "sonar"


def test_fingerprints_from_two_runs_form_a_series(client: _FakeClient) -> None:
    db.save_engine_fingerprints("run-1", "Fort", "2026-06-13", [_PRINT])
    db.save_engine_fingerprints("run-2", "Fort", "2026-06-20", [{**_PRINT, "median_length": 900.0}])
    series = db.get_engine_fingerprints("Fort", "perplexity")
    assert len(series) == 2
    assert {row["median_length"] for row in series} == {1840.0, 900.0}


# --- client config (P4-T6) ----------------------------------------------------


def test_an_unchanged_config_does_not_create_a_revision(client: _FakeClient) -> None:
    """The fingerprint is what makes two cycles comparable. A table with one row
    per render could not answer "when did this last change"."""
    config = {"engines": ["perplexity"], "runs_per_query": 3}
    db.save_client_config("Fort", "fp-1", config, reason="run 1")
    db.save_client_config("Fort", "fp-1", config, reason="run 2")
    assert len(client.store["client_configs"]) == 1


def test_a_changed_config_is_a_new_row_not_an_update(client: _FakeClient) -> None:
    """Create-only: overwriting a config would silently rewrite the answer to
    "were these two runs measured the same way"."""
    db.save_client_config("Fort", "fp-1", {"runs_per_query": 3})
    db.save_client_config("Fort", "fp-2", {"runs_per_query": 5})
    rows = client.store["client_configs"]
    assert len(rows) == 2
    assert {r["fingerprint"] for r in rows} == {"fp-1", "fp-2"}


# --- share revocation (P3-T4) -------------------------------------------------


def test_a_revoked_token_survives_a_restart(client: _FakeClient) -> None:
    """The whole point. A share token is stateless and signed, so revoking it
    means remembering that we no longer honour it — and a store that forgets on
    restart brings a revoked link back after a deploy."""
    db.revoke_share_token("tok-1", run_id="run-1", reason="client offboarded")
    assert db.revoked_share_ids() == {"tok-1"}


def test_revoking_one_link_does_not_revoke_the_others(client: _FakeClient) -> None:
    db.revoke_share_token("tok-1")
    db.revoke_share_token("tok-2")
    assert db.revoked_share_ids() == {"tok-1", "tok-2"}


def test_the_deny_list_stores_the_id_not_the_token(client: _FakeClient) -> None:
    """Storing the signed token would put a working credential in a table whose
    entire purpose is that the credential no longer works."""
    db.revoke_share_token("tok-1")
    stored = client.store["revoked_share_tokens"][0]
    assert set(stored) <= {"jti", "run_id", "reason"}
    assert "token" not in stored


# --- offboarding --------------------------------------------------------------


def test_forgetting_a_client_scrubs_only_that_client(client: _FakeClient) -> None:
    client.store["findings_registry"] = [
        {"client_name": "Fort", "cluster_id": "c1", "normalized": "a"},
        {"client_name": "Oura", "cluster_id": "c2", "normalized": "b"},
    ]
    db.forget_findings_for_client("Fort")
    assert [r["client_name"] for r in client.store["findings_registry"]] == ["Oura"]
