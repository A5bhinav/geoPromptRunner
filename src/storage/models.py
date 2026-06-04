from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict

__all__ = [
    "PromptResult",
    "QueryResult",
    "PromptRun",
    "BrandMention",
    "Citation",
    "ReportData",
    "RubricScore",
    "Prominence",
    "Framing",
    "AccuracyFlagType",
    "Severity",
    "BrandJudgment",
    "AccuracyFlag",
    "AnswerJudgment",
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


class RubricScore(TypedDict):
    """One human Pass/Partial/Fail judgment for a rubric check on a subject."""

    subject: str  # client or competitor name
    category: str  # RubricCategory value
    check_name: str
    status: str  # CheckStatus value: pass / partial / fail
    weight: float
    note: str
    query_ids: list[str]  # gap->query link: which queries this gap touches


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


# --- LLM judge output (moved here so the storage layer doesn't depend on the
# pipeline/judge module — which pulls in the openai SDK — just to (de)serialize
# rows). pipeline.judge re-exports these for back-compat. ---


class Prominence(StrEnum):
    RECOMMENDED_FIRST = "recommended_first"
    MID_PACK = "mid_pack"
    BURIED = "buried"
    ALSO_RAN = "also_ran"
    ABSENT = "absent"


class Framing(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class AccuracyFlagType(StrEnum):
    WRONG_PRICING = "wrong_pricing"
    MISSING_OR_INVENTED_FEATURE = "missing_or_invented_feature"
    COMPETITOR_CONFUSION = "competitor_confusion"
    IDENTITY = "identity"
    STALE = "stale"


class Severity(StrEnum):
    HIGH = "high"
    MED = "med"
    LOW = "low"


@dataclass(frozen=True)
class BrandJudgment:
    """How one brand appears in one answer (present / prominence / framing)."""

    brand: str
    present: bool
    prominence: str  # Prominence value
    framing: str  # Framing value


@dataclass(frozen=True)
class AccuracyFlag:
    """A client claim the answer got wrong, checked against the fact sheet."""

    type: str  # AccuracyFlagType value
    claim: str  # what the answer said
    reality: str  # what the fact sheet says
    severity: str  # Severity value


@dataclass(frozen=True)
class AnswerJudgment:
    """The judge's structured read of one answer (all brands + client accuracy)."""

    query_id: str
    engine_name: str
    intent: str
    run_index: int
    assessed: bool  # False = judge failed -> "not assessed", never crashes
    brands: list[BrandJudgment]
    accuracy_flags: list[AccuracyFlag]  # client only; empty without a fact sheet
