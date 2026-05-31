from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from supabase import Client, create_client

from src.config import settings
from src.storage.models import BrandMention, Citation, PromptResult

__all__ = [
    "StorageError",
    "create_run",
    "save_results",
    "save_mentions",
    "save_citations",
    "get_run",
    "get_results",
    "get_mentions",
    "get_citations",
]

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

TABLE_RUNS = "prompt_runs"
TABLE_RESULTS = "prompt_results"
TABLE_MENTIONS = "brand_mentions"
TABLE_CITATIONS = "citations"


class StorageError(Exception):
    """Raised when a storage operation fails. Wraps the underlying error."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


_cached_client: Client | None = None


def _client() -> Client:
    """Return a cached Supabase client, or raise StorageError if not configured.

    The client (and its underlying HTTP session) is built once and reused for
    every read and write rather than reconstructed per call.
    """
    global _cached_client
    if _cached_client is not None:
        return _cached_client
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise StorageError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY (see .env.example)."
        )
    try:
        _cached_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    except Exception as exc:
        # Log the type only — the message can echo connection details.
        logger.warning("Failed to create Supabase client: %s", type(exc).__name__)
        raise StorageError("Failed to create Supabase client") from exc
    return _cached_client


def _execute(op_label: str, operation: Callable[[Client], _T]) -> _T:
    """Run a Supabase operation against the cached client, normalizing errors.

    Single owner of the storage try/except: on failure it logs only the
    exception **type** (a Supabase/Postgres message can echo back row values or
    connection detail) and raises ``StorageError``; the original exception still
    chains via ``from exc`` for callers that want full detail. ``op_label`` is a
    caller-controlled string (never the exception), safe to log.

    ``_client()`` is called outside the try so a "not configured" ``StorageError``
    propagates unchanged rather than being re-wrapped.
    """
    client = _client()
    try:
        return operation(client)
    except Exception as exc:
        logger.warning("%s failed: %s", op_label, type(exc).__name__)
        raise StorageError(f"{op_label} failed") from exc


def create_run(client_name: str, prompt_count: int) -> str:
    """Insert a new run row and return its generated ``run_id``."""
    run_id = str(uuid.uuid4())
    row: dict[str, Any] = {
        "id": run_id,
        "client_name": client_name,
        "prompt_count": prompt_count,
        "created_at": _now(),
        "archived_at": None,
    }
    _execute(
        f"create_run for client {client_name}", lambda c: c.table(TABLE_RUNS).insert(row).execute()
    )
    return run_id


def save_results(run_id: str, results: list[PromptResult]) -> None:
    """Persist prompt results for a run."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "prompt": r["prompt"],
            "engine_name": r["engine_name"],
            "response": r["response"],
            "timestamp": r["timestamp"],
        }
        for r in results
    ]
    if not rows:
        return
    _execute(
        f"save_results for run {run_id}", lambda c: c.table(TABLE_RESULTS).insert(rows).execute()
    )


def save_mentions(run_id: str, mentions: list[BrandMention]) -> None:
    """Persist brand/competitor mentions for a run."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "brand": m["brand"],
            "engine_name": m["engine_name"],
            "prompt": m["prompt"],
            "mention_type": m["mention_type"],
        }
        for m in mentions
    ]
    if not rows:
        return
    _execute(
        f"save_mentions for run {run_id}", lambda c: c.table(TABLE_MENTIONS).insert(rows).execute()
    )


def save_citations(run_id: str, citations: list[Citation]) -> None:
    """Persist citation URLs for a run."""
    rows = [
        {
            "id": str(uuid.uuid4()),
            "run_id": run_id,
            "url": c["url"],
            "engine_name": c["engine_name"],
            "prompt": c["prompt"],
        }
        for c in citations
    ]
    if not rows:
        return
    _execute(
        f"save_citations for run {run_id}",
        lambda c: c.table(TABLE_CITATIONS).insert(rows).execute(),
    )


def _select_rows(table: str, run_id: str, key: str = "run_id") -> list[dict[str, object]]:
    response = _execute(
        f"read from {table} ({key}={run_id})",
        lambda c: c.table(table).select("*").eq(key, run_id).execute(),
    )
    data = getattr(response, "data", None) or []
    return list(data)


def get_run(run_id: str) -> dict[str, object] | None:
    """Fetch a single run row by id, or None if absent."""
    rows = _select_rows(TABLE_RUNS, run_id, key="id")
    return rows[0] if rows else None


def get_results(run_id: str) -> list[dict[str, object]]:
    """Fetch all stored results for a run."""
    return _select_rows(TABLE_RESULTS, run_id)


def get_mentions(run_id: str) -> list[dict[str, object]]:
    """Fetch all stored mentions for a run."""
    return _select_rows(TABLE_MENTIONS, run_id)


def get_citations(run_id: str) -> list[dict[str, object]]:
    """Fetch all stored citations for a run."""
    return _select_rows(TABLE_CITATIONS, run_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        run_id = create_run("Demo Client", prompt_count=1)
        save_results(
            run_id,
            [
                PromptResult(
                    prompt="What is the best CRM?",
                    engine_name="openai",
                    response="Acme is a strong choice.",
                    timestamp=_now(),
                )
            ],
        )
        save_mentions(
            run_id,
            [
                BrandMention(
                    brand="Acme",
                    engine_name="openai",
                    prompt="What is the best CRM?",
                    mention_type="recommended",
                )
            ],
        )
        save_citations(
            run_id,
            [
                Citation(
                    url="https://example.com/acme",
                    engine_name="perplexity",
                    prompt="What is the best CRM?",
                )
            ],
        )
        stored = get_results(run_id)
        print(f"Created run {run_id} and stored {len(stored)} result row(s) in Supabase.")
    except StorageError as exc:
        print(f"Cannot run storage test: {exc}")
        raise SystemExit(0) from None
