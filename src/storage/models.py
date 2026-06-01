from __future__ import annotations

from typing import TypedDict

__all__ = [
    "PromptResult",
    "QueryResult",
    "PromptRun",
    "BrandMention",
    "Citation",
    "ReportData",
]


class PromptResult(TypedDict):
    """One engine's answer to one prompt, captured during a run."""

    prompt: str
    engine_name: str
    response: str | None
    timestamp: str  # ISO-8601 UTC


class QueryResult(TypedDict):
    """One engine's answer to one intent-tagged query on one run.

    Richer than PromptResult: carries the query id, funnel-stage intent, the
    run index (queries are run multiple times per cycle to average out LLM
    nondeterminism), and any citation URLs the engine surfaced.
    """

    query_id: str
    intent: str  # IntentBucket value
    prompt: str
    engine_name: str
    run_index: int
    response: str | None
    citations: list[str]
    timestamp: str  # ISO-8601 UTC


class PromptRun(TypedDict):
    """A single audit run row (table: ``prompt_runs``)."""

    id: str
    client_name: str
    prompt_count: int
    created_at: str  # ISO-8601 UTC
    archived_at: str | None  # soft-delete marker; never hard-delete


class BrandMention(TypedDict):
    """A brand/competitor mention detected in one response (table: ``brand_mentions``)."""

    brand: str
    engine_name: str
    prompt: str
    mention_type: str  # one of MentionType's values


class Citation(TypedDict):
    """A citation URL extracted from a response (table: ``citations``)."""

    url: str
    engine_name: str
    prompt: str


class ReportData(TypedDict):
    """All inputs needed to render a markdown audit report.

    Pure render input — assembled from storage (or mocked in tests) and passed
    to ``render_report``.
    """

    client_name: str
    client_brand: str
    run_date: str
    engine_names: list[str]
    results: list[PromptResult]
    mentions: list[BrandMention]
    competitors: list[str]
    citations: list[Citation]
