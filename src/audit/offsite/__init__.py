"""Cat 6 — Offsite Authority & Entity Consensus (the one agentic part, §5).

A deterministic pre-pass (Wikidata, review presence, backlinks) plus a bounded
Anthropic tool-calling loop for the open-ended discovery (community threads,
listicles, press). Returns structured :class:`OffsiteFinding`s + an audit log;
never prose, never raises.
"""

from __future__ import annotations

from src.audit.offsite.agent import OffsiteAgent, run_offsite_research
from src.audit.offsite.models import (
    Confidence,
    FindingType,
    OffsiteFinding,
    OffsiteResult,
    ToolLogEntry,
)
from src.audit.offsite.tools import configured_tools

__all__ = [
    "run_offsite_research",
    "OffsiteAgent",
    "OffsiteFinding",
    "OffsiteResult",
    "FindingType",
    "Confidence",
    "ToolLogEntry",
    "configured_tools",
]
