"""Typed records for the Cat 6 offsite research agent (impl guide §5).

The agent returns structured findings — never prose — plus a JSONL-able audit log
of every tool call so a run is reconstructable and reproducible (§5.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "FindingType",
    "Confidence",
    "OffsiteFinding",
    "ToolLogEntry",
    "OffsiteResult",
    "TOOL_QUOTAS",
    "MAX_STEPS",
    "WALL_CLOCK_SECONDS",
]


class FindingType(StrEnum):
    WIKIDATA = "wikidata"  # entity present in Wikidata/KG
    ENTITY_CONSISTENCY = "entity_consistency"  # name/description consistent across web
    COMMUNITY = "community"  # Reddit / forum presence
    REVIEWS = "reviews"  # Trustpilot / app-store review presence
    BACKLINKS = "backlinks"  # referring domains / authority
    LISTICLE = "listicle"  # named in a "best [category]" roundup
    PRESS = "press"  # press / news mention


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class OffsiteFinding:
    finding_type: FindingType
    title: str
    url: str | None
    confidence: Confidence
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolLogEntry:
    """One tool invocation — the reproducibility/audit record (§5.2)."""

    step: int
    tool: str
    args: dict[str, Any]
    status: str  # ok | error | quota_exhausted | cache_hit
    latency_ms: int
    response_hash: str


@dataclass
class OffsiteResult:
    brand: str
    domain: str
    findings: list[OffsiteFinding] = field(default_factory=list)
    audit_log: list[ToolLogEntry] = field(default_factory=list)
    status: str = "ok"  # ok | partial | no_tools | failed
    note: str = ""


# Per-tool call budget enforced in the dispatcher (no framework bounds tool-call
# count — §5.1). Conservative: the offsite layer is the slowest/flakiest phase.
TOOL_QUOTAS: dict[str, int] = {
    "web_search": 5,
    "reddit_search": 3,
}

# Hard stop on the agent loop; return partial findings on exhaustion (§5.2).
MAX_STEPS = 8
# Wall-clock ceiling for the whole agent loop.
WALL_CLOCK_SECONDS = 90.0
