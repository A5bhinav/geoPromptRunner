"""Content-addressed cache ("the notebook") for on-site ContentJudge verdicts.

Parallel to :mod:`src.pipeline.judge_cache` but for a :class:`CheckVerdict` per
(page-text × rubric check). Same backends — ``supabase`` (default, shared),
``memory`` (tests), ``none`` (disabled) — selected by the SAME
``settings.JUDGE_CACHE_BACKEND`` knob, and the same "never raises into a run →
miss/no-op" contract. Stored in a SEPARATE Supabase table (``content_judge_cache``)
from the query-answer notebook so the two keyspaces / value shapes never mix.

Keys come from :func:`src.audit.checks.content_judge.content_cache_key`.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterable

from src.audit.checks.content_judge import CheckVerdict, ContentClass, SubAnswer
from src.config import settings

__all__ = [
    "ContentJudgeCache",
    "make_content_judge_cache",
    "SupabaseContentJudgeCache",
    "InMemoryContentJudgeCache",
    "NoOpContentJudgeCache",
]

logger = logging.getLogger(__name__)


def _to_value(v: CheckVerdict) -> dict[str, object]:
    """The JSON-safe stored form of a content verdict (a Supabase ``jsonb`` value)."""
    return {
        "check_id": v.check_id,
        "category": v.category,
        "classification": v.classification.value,
        "reason": v.reason,
        "needs_review": v.needs_review,
        "sub_answers": [
            {
                "key": s.key,
                "question": s.question,
                "reasoning": s.reasoning,
                "evidence_quote": s.evidence_quote,
                "answer": s.answer,
                "evidence_valid": s.evidence_valid,
            }
            for s in v.sub_answers
        ],
    }


def _from_value(d: dict[str, object]) -> CheckVerdict:
    raw_subs = d.get("sub_answers")
    subs = [
        SubAnswer(
            key=str(s.get("key", "")),
            question=str(s.get("question", "")),
            reasoning=str(s.get("reasoning", "")),
            evidence_quote=str(s.get("evidence_quote", "")),
            answer=str(s.get("answer", "unknown")),
            evidence_valid=bool(s.get("evidence_valid", True)),
        )
        for s in raw_subs
        if isinstance(s, dict)
    ] if isinstance(raw_subs, list) else []
    return CheckVerdict(
        check_id=str(d["check_id"]),
        category=int(str(d["category"])),
        classification=ContentClass(str(d["classification"])),
        reason=str(d["reason"]),
        sub_answers=subs,
        needs_review=bool(d["needs_review"]),
    )


class ContentJudgeCache(ABC):
    """A key→CheckVerdict notebook. Keys come from ``content_cache_key``."""

    def get(self, key: str) -> CheckVerdict | None:
        return self.get_many([key]).get(key)

    @abstractmethod
    def get_many(self, keys: Iterable[str]) -> dict[str, CheckVerdict]:
        """Verdicts for the given keys, batched (one round-trip, not one per check)."""

    def put(self, key: str, verdict: CheckVerdict) -> None:
        self.put_many([(key, verdict)])

    @abstractmethod
    def put_many(self, items: Iterable[tuple[str, CheckVerdict]]) -> None:
        """Store many verdicts in one batch."""

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release any resources. No-op by default."""


class NoOpContentJudgeCache(ContentJudgeCache):
    """Disabled notebook: every get misses, every put is a no-op."""

    def get_many(self, keys: Iterable[str]) -> dict[str, CheckVerdict]:
        return {}

    def put_many(self, items: Iterable[tuple[str, CheckVerdict]]) -> None:
        return None


class InMemoryContentJudgeCache(ContentJudgeCache):
    """In-process dict notebook (real store, network-free) — used by tests."""

    def __init__(self) -> None:
        self._d: dict[str, CheckVerdict] = {}
        self._lock = threading.Lock()

    def get_many(self, keys: Iterable[str]) -> dict[str, CheckVerdict]:
        with self._lock:
            return {k: self._d[k] for k in keys if k in self._d}

    def put_many(self, items: Iterable[tuple[str, CheckVerdict]]) -> None:
        with self._lock:
            for key, verdict in items:
                self._d[key] = verdict


class SupabaseContentJudgeCache(ContentJudgeCache):
    """Shared content notebook in Supabase. Never raises into a run: a Supabase error
    degrades to a miss on reads and a dropped write on puts (logged at INFO)."""

    def get_many(self, keys: Iterable[str]) -> dict[str, CheckVerdict]:
        from src.storage import db

        wanted = [k for k in keys if k]
        if not wanted:
            return {}
        try:
            rows = db.content_judge_cache_get_many(wanted)
        except db.StorageError as exc:
            logger.info("Content cache read failed (treating as miss): %s", type(exc).__name__)
            return {}
        out: dict[str, CheckVerdict] = {}
        for row in rows:
            try:
                out[str(row["key"])] = _from_value(row["value"])  # type: ignore[arg-type]
            except (KeyError, TypeError, ValueError) as exc:
                logger.info("Content cache entry corrupt (skipping one): %s", type(exc).__name__)
        return out

    def put_many(self, items: Iterable[tuple[str, CheckVerdict]]) -> None:
        from src.storage import db

        rows: list[dict[str, object]] = []
        for key, verdict in items:
            try:
                rows.append({"key": key, "value": _to_value(verdict)})
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                logger.info("Content cache encode failed (skipping one): %s", type(exc).__name__)
        if not rows:
            return
        try:
            db.content_judge_cache_put_many(rows)
        except db.StorageError as exc:
            logger.info("Content cache write failed (continuing): %s", type(exc).__name__)


def make_content_judge_cache() -> ContentJudgeCache:
    """Build the content notebook selected by ``settings.JUDGE_CACHE_BACKEND`` (shared
    with the query notebook): ``supabase`` (default) · ``memory`` · ``none``/``""``."""
    backend = (settings.JUDGE_CACHE_BACKEND or "").strip().lower()
    if backend == "supabase":
        return SupabaseContentJudgeCache()
    if backend == "memory":
        return InMemoryContentJudgeCache()
    if backend in ("none", ""):
        return NoOpContentJudgeCache()
    logger.warning("Unknown JUDGE_CACHE_BACKEND %r — disabling the content cache", backend)
    return NoOpContentJudgeCache()
