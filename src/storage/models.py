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
    "JUDGE_SEVERITIES",
    "BrandJudgment",
    "AccuracyFlag",
    "AnswerJudgment",
    "brand_to_dict",
    "brand_from_dict",
    "flag_to_dict",
    "flag_from_dict",
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
    """Dimensions on which an answer can contradict the client's fact sheet.

    The local members are APPENDED, never substituted (SMB pivot §0.6). They are
    inert on the consumer path by construction rather than by gating: every flag
    requires a VERBATIM contradicting line from the fact sheet, and a consumer
    product's sheet has no hours / service-area / licensing lines for a local flag
    to cite. Nothing has to remember to switch them off.
    """

    # --- product + local (shared) ---
    WRONG_PRICING = "wrong_pricing"
    MISSING_OR_INVENTED_FEATURE = "missing_or_invented_feature"
    COMPETITOR_CONFUSION = "competitor_confusion"
    IDENTITY = "identity"
    STALE = "stale"

    # --- local-service dimensions (SMB pivot, W3.1) ---
    # A product's accuracy is pricing/features/model. A local business's accuracy is
    # "can I actually get them, where, and are they legitimate" — the facts a
    # customer acts on when their AC just died.
    WRONG_HOURS = "wrong_hours"  # opening hours, emergency/same-day availability
    WRONG_SERVICE_AREA = "wrong_service_area"  # which towns/areas they cover
    WRONG_CONTACT = "wrong_contact"  # phone number, address
    LICENSING = "licensing"  # licence, bonding, insurance, certifications


class Severity(StrEnum):
    """Four tiers, ordered CRITICAL -> HIGH -> MED -> LOW.

    ``CRITICAL`` is APPENDED for the packaged report (audit-packaging-spec P0-T2)
    and is never emitted by the judge: the judge's tool schema still offers three
    values, and widening it would bump ``_PROMPT_LAYOUT`` and invalidate every
    cached verdict. It is derived in Python by
    :func:`src.pipeline.severity.escalate` instead, which is also why it is
    re-runnable over already-stored runs.

    Triggers (mirrored in the client-facing methodology copy):

    - **critical** — a category/identity error, or a factual claim that materially
      changes a purchase decision (wrong price, wrong availability, confusion with
      a different company).
    - **high** — an invented or materially misstated capability, or a competitor's
      attributes applied to the client.
    - **med** — omission or understatement of a real capability; stale-but-
      becoming-true claims.
    - **low** — imprecise phrasing; unverifiable but not contradicted; cosmetic.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MED = "med"
    LOW = "low"


#: The severities the JUDGE is allowed to emit — frozen, and deliberately not
#: derived from :class:`Severity`.
#:
#: The judge's tool schema is part of the prompt fingerprint, so widening it
#: invalidates every cached verdict in Supabase. It did exactly that the first
#: time ``CRITICAL`` was appended above and the schema was still built with
#: ``[s.value for s in Severity]``. This tuple is the seam that lets the packaged
#: report have four tiers while the judge keeps the three it has always had.
#:
#: **Never add to this list to give the judge a new severity.** Deriving the tier
#: in Python (``src/pipeline/severity.escalate``) is free, testable and re-runnable
#: over stored runs; asking the model costs the entire cache.
JUDGE_SEVERITIES: tuple[str, ...] = ("high", "med", "low")


@dataclass(frozen=True)
class BrandJudgment:
    """How one brand appears in one answer (present / prominence / framing)."""

    brand: str
    present: bool
    prominence: str  # Prominence value
    framing: str  # Framing value


@dataclass(frozen=True)
class AccuracyFlag:
    """A client claim the answer got wrong, checked against the fact sheet.

    The four leading fields are the judge's verdict. The four trailing ones are
    PROVENANCE — which cell produced it — and they are derived in Python from the
    parent :class:`AnswerJudgment`, never asked of the judge model
    (``docs/audit-packaging-spec.md`` P0-T1). That distinction is what keeps them
    free: asking the model would mean a tool-schema change, which bumps
    ``_PROMPT_LAYOUT`` and invalidates every cached verdict.

    **They are stamped per cell, not per verdict.** ``judge_results`` dedups
    verdicts by ``(prompt, answer)``, so one flag object is shared by every cell
    whose answer text matched. Provenance therefore belongs to the join in
    ``judge_results``, and the defaults here are what an un-stamped flag looks
    like — which is also what comes back from the judge cache, since the cache is
    keyed per ANSWER and cannot know which cell will read it.

    A flag with empty provenance must never be rendered to a client: the
    audit-packaging rule is that a finding without engine + timestamp + verbatim
    prompt is not shippable.
    """

    type: str  # AccuracyFlagType value
    claim: str  # what the answer said
    reality: str  # what the fact sheet says
    severity: str  # Severity value
    # --- provenance (derived, not judged) ---
    query_id: str = ""
    engine_name: str = ""
    intent: str = ""
    run_index: int = 0
    # ISO-8601 UTC of the CELL, copied from `QueryResult.timestamp` — when the
    # engine said this, not when we judged it. Every client-facing finding is
    # attributed to a named model AND a date; this is the date.
    observed_at: str = ""
    # --- identity (derived at report build, see src/pipeline/finding_id.py) ---
    # Empty everywhere upstream of the report layer. `row_hash` is idempotency
    # only; `cluster_id` is the stable, client-facing finding id that survives
    # across weeks. Neither is stored in `flag_to_dict` — both are pure functions
    # of the claim plus the findings registry, so persisting them would create a
    # second copy that can disagree with the text it names.
    row_hash: str = ""
    cluster_id: str = ""

    @property
    def has_provenance(self) -> bool:
        """Whether this flag can name the cell it came from.

        False for anything read straight off the judge cache, and for legacy rows
        stored before P0-T1. Gate rendering on it rather than assuming.
        """
        return bool(self.query_id and self.engine_name)


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


# Canonical (de)serialization for the two judgment value types — one source of
# truth shared by the storage layer (db.py) and the judge cache (judge_cache.py)
# so a field change can't make the two drift. The ``from_dict`` readers coerce
# defensively (str()/bool() with defaults) so a partial/legacy row never crashes.


def brand_to_dict(b: BrandJudgment) -> dict[str, object]:
    return {
        "brand": b.brand,
        "present": b.present,
        "prominence": b.prominence,
        "framing": b.framing,
    }


def brand_from_dict(d: dict[str, object]) -> BrandJudgment:
    return BrandJudgment(
        brand=str(d.get("brand", "")),
        present=bool(d.get("present", False)),
        prominence=str(d.get("prominence", "")),
        framing=str(d.get("framing", "")),
    )


def flag_to_dict(f: AccuracyFlag) -> dict[str, object]:
    """The VERDICT only — deliberately without provenance.

    Shared by the judge cache and the judgments table, and the cache is what
    forces the omission: it is keyed per (prompt, answer), so a cell's
    ``query_id``/``engine_name`` written into it would be served back to a
    different cell that happened to produce identical answer text. Storing per-cell
    data in a per-answer cache is a wrong answer waiting to be read.

    Provenance is re-derived at the join in ``judge_results`` on every path,
    cache hit or miss, so nothing is lost by leaving it out. Keeping the payload
    at four keys also means existing cached entries stay byte-identical.
    """
    return {"type": f.type, "claim": f.claim, "reality": f.reality, "severity": f.severity}


def flag_from_dict(d: dict[str, object]) -> AccuracyFlag:
    """Read a flag back, tolerating both the 4-key cache shape and a stored row.

    Provenance defaults to empty rather than failing: every cached verdict
    predates it by construction (see :func:`flag_to_dict`), and a legacy
    judgments row has no such keys. ``run_index`` coerces defensively because a
    stored JSON number may arrive as a string.
    """
    try:
        run_index = int(str(d.get("run_index", 0)))
    except ValueError:
        run_index = 0
    return AccuracyFlag(
        type=str(d.get("type", "")),
        claim=str(d.get("claim", "")),
        reality=str(d.get("reality", "")),
        severity=str(d.get("severity", "")),
        query_id=str(d.get("query_id", "")),
        engine_name=str(d.get("engine_name", "")),
        intent=str(d.get("intent", "")),
        run_index=run_index,
        observed_at=str(d.get("observed_at", "")),
    )
