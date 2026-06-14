"""Persistent, content-addressed cache for judge verdicts.

A judge verdict is fully determined by its inputs — the judge model, the client
and competitor set, the fact sheet (ground truth), and the exact prompt+answer
text. So the same answer never needs judging twice: not across a resumed run,
not across a re-run, not across a cadence re-check. This cache stores each
verdict keyed by a hash of all of those inputs, so a repeated answer is a free
lookup instead of an API call.

Correctness hinges on the key: it includes the fact sheet and brand set, so
editing the Fort fact sheet (new ground truth) yields a different key and the
answer is correctly re-judged rather than served a stale accuracy verdict.

Backed by SQLite (stdlib, survives restarts). Never raises into a run: any
storage error degrades to a cache miss, so a broken cache slows a run but never
breaks it. An empty path makes a no-op cache, so callers can always pass one.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from src.storage.models import (
    AccuracyFlag,
    BrandJudgment,
    brand_from_dict,
    brand_to_dict,
    flag_from_dict,
    flag_to_dict,
)

__all__ = ["JudgeCache", "Verdict"]

logger = logging.getLogger(__name__)

# The judge's verdict for one answer: brand reads, client accuracy flags, and
# whether the judge actually assessed it (False = judge call failed).
Verdict = tuple[list[BrandJudgment], list[AccuracyFlag], bool]

# Bump when the judge prompt or output schema changes in a way that would make
# an old stored verdict wrong for the same inputs — invalidates the whole cache.
_SCHEMA_VERSION = "v1"


def _verdict_key(
    *,
    model: str,
    prompt_fingerprint: str,
    client: str,
    competitors: Iterable[str],
    fact_sheet: str | None,
    prompt: str,
    answer: str,
) -> str:
    """A stable hash over every input that determines a verdict.

    ``prompt_fingerprint`` is a hash of the judge's own system prompt + tool
    schema, so editing the judge prompt (a determinant of the verdict the
    inputs don't otherwise capture) changes the key and forces a re-judge —
    rather than relying on someone remembering to bump ``_SCHEMA_VERSION``.
    Competitor order is normalized so the key doesn't change just because the
    list was passed in a different order. The client is recorded both on its own
    and inside the brand set so swapping which brand is "the client" (same brand
    set) still yields a distinct key.
    """
    brands = "\x1f".join(sorted({client, *competitors}))
    parts = [
        _SCHEMA_VERSION,
        model,
        prompt_fingerprint,
        client,
        brands,
        fact_sheet or "",
        prompt,
        answer,
    ]
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()


class JudgeCache:
    """Thread-safe key→verdict store backed by SQLite (or a no-op if disabled)."""

    def __init__(self, path: str | None) -> None:
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        if not path:
            return  # disabled — every get() misses, every put() is a no-op
        try:
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False + our own lock: the judge pool calls from
            # many threads, but every access is serialized through self._lock.
            conn = sqlite3.connect(path, check_same_thread=False)
            # WAL lets readers proceed without blocking on writers' commits —
            # matters because the judge pool reads and writes the cache from
            # several threads at once.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS verdicts (key TEXT PRIMARY KEY, value TEXT)")
            conn.commit()
            self._conn = conn
        except (sqlite3.Error, OSError) as exc:
            logger.warning("Judge cache disabled (could not open %s): %s", path, exc)
            self._conn = None

    def key(
        self,
        *,
        model: str,
        prompt_fingerprint: str,
        client: str,
        competitors: Iterable[str],
        fact_sheet: str | None,
        prompt: str,
        answer: str,
    ) -> str:
        return _verdict_key(
            model=model,
            prompt_fingerprint=prompt_fingerprint,
            client=client,
            competitors=competitors,
            fact_sheet=fact_sheet,
            prompt=prompt,
            answer=answer,
        )

    def get(self, key: str) -> Verdict | None:
        if self._conn is None:
            return None
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT value FROM verdicts WHERE key = ?", (key,)
                ).fetchone()
        except sqlite3.Error as exc:
            logger.info("Judge cache read failed (treating as miss): %s", exc)
            return None
        if row is None:
            return None
        try:
            return _decode(row[0])
        except (ValueError, KeyError, TypeError) as exc:
            logger.info("Judge cache entry corrupt (treating as miss): %s", exc)
            return None

    def put(self, key: str, verdict: Verdict) -> None:
        if self._conn is None:
            return
        try:
            payload = _encode(verdict)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            logger.info("Judge cache encode failed (skipping store): %s", exc)
            return
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO verdicts (key, value) VALUES (?, ?)", (key, payload)
                )
                self._conn.commit()
        except sqlite3.Error as exc:
            logger.info("Judge cache write failed (continuing): %s", exc)

    def put_many(self, items: Iterable[tuple[str, Verdict]]) -> None:
        """Store many verdicts in ONE transaction — a single commit/fsync for the
        whole batch instead of one per answer, so the concurrent judge isn't
        throttled by per-write disk syncs."""
        if self._conn is None:
            return
        rows: list[tuple[str, str]] = []
        for key, verdict in items:
            try:
                rows.append((key, _encode(verdict)))
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                logger.info("Judge cache encode failed (skipping one): %s", exc)
        if not rows:
            return
        try:
            with self._lock:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO verdicts (key, value) VALUES (?, ?)", rows
                )
                self._conn.commit()
        except sqlite3.Error as exc:
            logger.info("Judge cache batch write failed (continuing): %s", exc)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


def _encode(verdict: Verdict) -> str:
    brands, flags, assessed = verdict
    return json.dumps(
        {
            "brands": [brand_to_dict(b) for b in brands],
            "flags": [flag_to_dict(f) for f in flags],
            "assessed": assessed,
        }
    )


def _decode(payload: str) -> Verdict:
    data = json.loads(payload)
    brands = [brand_from_dict(b) for b in data["brands"]]
    flags = [flag_from_dict(f) for f in data["flags"]]
    return brands, flags, bool(data["assessed"])
