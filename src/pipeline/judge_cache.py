"""Persistent, content-addressed cache ("the notebook") for judge verdicts.

A judge verdict is fully determined by its inputs — the judge model, the client
and competitor set, the fact sheet (ground truth), and the exact prompt+answer
text. So the same answer never needs judging twice: not across a resumed run,
not across a re-run, not across a cadence re-check. This cache stores each
verdict keyed by a hash of all of those inputs, so a repeated answer is a free
lookup instead of an API call.

Correctness hinges on the key: it includes the fact sheet and brand set, so
editing the Fort fact sheet (new ground truth) yields a different key and the
answer is correctly re-judged rather than served a stale accuracy verdict.

Backends (chosen by ``settings.JUDGE_CACHE_BACKEND`` via ``make_judge_cache()``):
  - ``supabase`` (default) — a shared table so the subscription pre-judge (which
    runs on one machine) and the UI/report step (which runs on the server) read
    and write the SAME notebook. This is what makes the "prejudge → generate
    report" flow work across machines.
  - ``memory`` — an in-process dict, for tests (no network).
  - ``none`` / ``""`` — disabled: every get misses, every put is a no-op (force a
    fresh judge pass).

Never raises into a run: any storage error degrades to a cache miss / no-op, so a
broken or slow notebook slows a run but never breaks it.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterable

from src.config import settings
from src.storage.models import (
    AccuracyFlag,
    BrandJudgment,
    brand_from_dict,
    brand_to_dict,
    flag_from_dict,
    flag_to_dict,
)

__all__ = [
    "JudgeCache",
    "Verdict",
    "make_judge_cache",
    "SupabaseJudgeCache",
    "InMemoryJudgeCache",
    "NoOpJudgeCache",
]

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

    NOTE: this is backend-independent — the same key is emitted whether the
    notebook is Supabase, in-memory, or disabled — so key parity with the live
    judge holds regardless of backend.
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


def _to_value(verdict: Verdict) -> dict[str, object]:
    """The JSON-safe stored form of a verdict (a Supabase ``jsonb`` value)."""
    brands, flags, assessed = verdict
    return {
        "brands": [brand_to_dict(b) for b in brands],
        "flags": [flag_to_dict(f) for f in flags],
        "assessed": assessed,
    }


def _from_value(data: dict[str, object]) -> Verdict:
    raw_brands = data["brands"]
    raw_flags = data["flags"]
    brands = [brand_from_dict(b) for b in raw_brands] if isinstance(raw_brands, list) else []
    flags = [flag_from_dict(f) for f in raw_flags] if isinstance(raw_flags, list) else []
    return brands, flags, bool(data["assessed"])


class JudgeCache(ABC):
    """A key→verdict notebook. ``key()`` is shared (backend-independent); backends
    implement how verdicts are stored and read."""

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
        return self.get_many([key]).get(key)

    @abstractmethod
    def get_many(self, keys: Iterable[str]) -> dict[str, Verdict]:
        """Verdicts for the given keys (missing keys simply absent). Batched so a
        network-backed notebook does ONE round-trip instead of one-per-answer."""

    def put(self, key: str, verdict: Verdict) -> None:
        self.put_many([(key, verdict)])

    @abstractmethod
    def put_many(self, items: Iterable[tuple[str, Verdict]]) -> None:
        """Store many verdicts in one batch."""

    def close(self) -> None:  # noqa: B027 - optional hook, most backends need nothing
        """Release any resources. No-op by default."""


class NoOpJudgeCache(JudgeCache):
    """Disabled notebook: every get misses, every put is a no-op."""

    def get_many(self, keys: Iterable[str]) -> dict[str, Verdict]:
        return {}

    def put_many(self, items: Iterable[tuple[str, Verdict]]) -> None:
        return None


class InMemoryJudgeCache(JudgeCache):
    """In-process dict notebook. Real store (put then get works) but non-persistent
    and network-free — used by tests."""

    def __init__(self) -> None:
        self._d: dict[str, Verdict] = {}
        self._lock = threading.Lock()

    def get_many(self, keys: Iterable[str]) -> dict[str, Verdict]:
        with self._lock:
            return {k: self._d[k] for k in keys if k in self._d}

    def put_many(self, items: Iterable[tuple[str, Verdict]]) -> None:
        with self._lock:
            for key, verdict in items:
                self._d[key] = verdict


class SupabaseJudgeCache(JudgeCache):
    """Shared notebook in Supabase — the store the subscription pre-judge writes and
    the UI/report step reads, across machines.

    Never raises into a run: a Supabase error (down, slow, misconfigured) degrades
    to a miss on reads and a dropped write on puts, logged at INFO. A cold or broken
    notebook therefore just means "judge it live", never a crashed run.
    """

    def get_many(self, keys: Iterable[str]) -> dict[str, Verdict]:
        from src.storage import db

        wanted = [k for k in keys if k]
        if not wanted:
            return {}
        try:
            rows = db.judge_cache_get_many(wanted)
        except db.StorageError as exc:
            logger.info("Judge cache read failed (treating as miss): %s", type(exc).__name__)
            return {}
        out: dict[str, Verdict] = {}
        for row in rows:
            try:
                out[str(row["key"])] = _from_value(row["value"])  # type: ignore[arg-type]
            except (KeyError, TypeError, ValueError) as exc:
                logger.info("Judge cache entry corrupt (skipping one): %s", type(exc).__name__)
        return out

    def put_many(self, items: Iterable[tuple[str, Verdict]]) -> None:
        from src.storage import db

        rows: list[dict[str, object]] = []
        for key, verdict in items:
            try:
                rows.append({"key": key, "value": _to_value(verdict)})
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                logger.info("Judge cache encode failed (skipping one): %s", type(exc).__name__)
        if not rows:
            return
        try:
            db.judge_cache_put_many(rows)
        except db.StorageError as exc:
            logger.info("Judge cache write failed (continuing): %s", type(exc).__name__)


def make_judge_cache() -> JudgeCache:
    """Build the notebook selected by ``settings.JUDGE_CACHE_BACKEND``.

    ``supabase`` (default, shared) · ``memory`` (tests) · ``none``/``""`` (disabled).
    An unknown value falls back to disabled with a warning, never a crash.
    """
    backend = (settings.JUDGE_CACHE_BACKEND or "").strip().lower()
    if backend == "supabase":
        return SupabaseJudgeCache()
    if backend == "memory":
        return InMemoryJudgeCache()
    if backend in ("none", ""):
        return NoOpJudgeCache()
    logger.warning("Unknown JUDGE_CACHE_BACKEND %r — disabling the judge cache", backend)
    return NoOpJudgeCache()
