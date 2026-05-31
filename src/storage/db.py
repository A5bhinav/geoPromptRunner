from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

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

TABLE_RUNS = "prompt_runs"
TABLE_RESULTS = "prompt_results"
TABLE_MENTIONS = "brand_mentions"
TABLE_CITATIONS = "citations"


class StorageError(Exception):
    """Raised when a storage operation fails. Wraps the underlying error."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _client() -> Client:
    """Build a Supabase client, or raise StorageError if not configured."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
        raise StorageError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY (see .env.example)."
        )
    try:
        return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    except Exception as exc:
        logger.warning("Failed to create Supabase client: %s", exc)
        raise StorageError("Failed to create Supabase client") from exc


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
    try:
        _client().table(TABLE_RUNS).insert(row).execute()
    except StorageError:
        raise
    except Exception as exc:
        logger.warning("create_run failed for client %s: %s", client_name, exc)
        raise StorageError("create_run failed") from exc
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
    try:
        _client().table(TABLE_RESULTS).insert(rows).execute()
    except StorageError:
        raise
    except Exception as exc:
        logger.warning("save_results failed for run %s: %s", run_id, exc)
        raise StorageError("save_results failed") from exc


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
    try:
        _client().table(TABLE_MENTIONS).insert(rows).execute()
    except StorageError:
        raise
    except Exception as exc:
        logger.warning("save_mentions failed for run %s: %s", run_id, exc)
        raise StorageError("save_mentions failed") from exc


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
    try:
        _client().table(TABLE_CITATIONS).insert(rows).execute()
    except StorageError:
        raise
    except Exception as exc:
        logger.warning("save_citations failed for run %s: %s", run_id, exc)
        raise StorageError("save_citations failed") from exc


def _select_rows(table: str, run_id: str, key: str = "run_id") -> list[dict[str, object]]:
    try:
        response = _client().table(table).select("*").eq(key, run_id).execute()
    except StorageError:
        raise
    except Exception as exc:
        logger.warning("read from %s failed for %s=%s: %s", table, key, run_id, exc)
        raise StorageError(f"read from {table} failed") from exc
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
