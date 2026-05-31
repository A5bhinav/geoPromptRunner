from __future__ import annotations

from typing import TypedDict

__all__ = [
    "PromptResult",
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
