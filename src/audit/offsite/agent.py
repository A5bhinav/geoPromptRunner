"""Cat 6 offsite research — deterministic pre-pass + bounded agentic loop (§5).

Two layers, per impl guide §5.2:
1. A **deterministic pre-pass** (no LLM): Wikidata entity, review-platform
   presence, and the backlinks summary are looked up directly — they're not
   open-ended, so the agent shouldn't spend steps on them.
2. A **bounded tool-calling loop** for the genuinely open-ended part — which
   community threads / listicles / press actually matter. It's a hand-rolled
   Anthropic loop (no framework), with per-tool quotas enforced in our own
   dispatcher, a hard step + wall-clock budget, a tool-result cache, and a JSONL
   audit log — because no framework bounds *tool-call count* (§5.1).

The agent must finish by calling the terminal ``submit_findings`` tool; on budget
exhaustion we force one final submit so a partial result is still structured.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import anthropic
from anthropic import Anthropic
from anthropic.types import Message, ToolParam, ToolUseBlock

from src.audit.offsite.models import (
    MAX_STEPS,
    TOOL_QUOTAS,
    WALL_CLOCK_SECONDS,
    Confidence,
    FindingType,
    OffsiteFinding,
    OffsiteResult,
    ToolLogEntry,
)
from src.audit.offsite.tools import (
    ToolResult,
    dataforseo_backlinks,
    reddit_search,
    reviews_presence,
    serper_search,
    wikidata_entity,
)
from src.config import settings

__all__ = ["run_offsite_research", "OffsiteAgent"]

logger = logging.getLogger(__name__)

_AGENT_MAX_TOKENS = 2048


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]


# --- deterministic pre-pass --------------------------------------------------


def _deterministic_prepass(
    brand: str, domain: str
) -> tuple[list[OffsiteFinding], list[ToolLogEntry]]:
    findings: list[OffsiteFinding] = []
    log: list[ToolLogEntry] = []

    def _record(tool: str, args: dict[str, Any], result: ToolResult) -> None:
        log.append(
            ToolLogEntry(
                step=0,
                tool=tool,
                args=args,
                status="ok" if result.available else "error",
                latency_ms=0,
                response_hash=_hash(result.data if result.available else result.error),
            )
        )

    wiki = wikidata_entity(brand, domain)
    _record("wikidata", {"brand": brand}, wiki)
    if wiki.available:
        found = bool(wiki.data.get("found"))
        findings.append(
            OffsiteFinding(
                FindingType.WIKIDATA,
                f"Wikidata entity {'found' if found else 'not found'} for {brand}",
                f"https://www.wikidata.org/wiki/{wiki.data['qid']}" if found else None,
                Confidence.HIGH,
                wiki.data,
            )
        )

    reviews = reviews_presence(brand)
    _record("reviews", {"brand": brand}, reviews)
    if reviews.available:
        platforms = reviews.data.get("platforms", {})
        present = [host for host, info in platforms.items() if info.get("present")]
        findings.append(
            OffsiteFinding(
                FindingType.REVIEWS,
                f"Review presence on {len(present)}/{len(platforms)} platforms",
                None,
                Confidence.MEDIUM if present else Confidence.LOW,
                reviews.data,
            )
        )

    backlinks = dataforseo_backlinks(domain)
    _record("dataforseo", {"domain": domain}, backlinks)
    if backlinks.available:
        findings.append(
            OffsiteFinding(
                FindingType.BACKLINKS,
                f"{backlinks.data.get('referring_domains', '?')} referring domains",
                None,
                Confidence.HIGH,
                backlinks.data,
            )
        )

    return findings, log


# --- agent tools (model-facing) ----------------------------------------------


def _search_tool() -> ToolParam:
    return {
        "name": "web_search",
        "description": "Search Google; returns organic results and any knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }


def _reddit_tool() -> ToolParam:
    return {
        "name": "reddit_search",
        "description": "Search Reddit for brand/community discussion (titles, subreddits, scores).",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }


def _submit_tool() -> ToolParam:
    return {
        "name": "submit_findings",
        "description": "Submit the final structured offsite findings and end the research.",
        "input_schema": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finding_type": {
                                "type": "string",
                                "enum": ["community", "listicle", "press", "entity_consistency"],
                            },
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            "summary": {"type": "string"},
                        },
                        "required": ["finding_type", "title", "confidence", "summary"],
                    },
                }
            },
            "required": ["findings"],
        },
    }


def _dispatch_tool(
    name: str,
    args: dict[str, Any],
    quotas: dict[str, int],
    cache: dict[str, Any],
    step: int,
    log: list[ToolLogEntry],
) -> Any:
    """Run one model-requested tool, enforcing the cache then per-tool quota (§5.2).

    Cache is checked before the quota so a repeated call costs neither a quota slot
    nor an API call. Module-level (no agent state) so it's unit-testable directly.
    """
    cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
    if cache_key in cache:
        log.append(ToolLogEntry(step, name, args, "cache_hit", 0, _hash(cache[cache_key])))
        return cache[cache_key]
    if quotas.get(name, 0) <= 0:
        log.append(ToolLogEntry(step, name, args, "quota_exhausted", 0, ""))
        return {"error": f"quota exhausted for {name}"}

    start = time.monotonic()
    query = str(args.get("query", ""))
    if name == "web_search":
        result = serper_search(query)
    elif name == "reddit_search":
        result = reddit_search(query)
    else:
        result = ToolResult(False, name, error="unknown tool")
    quotas[name] = quotas.get(name, 0) - 1
    payload = result.data if result.available else {"error": result.error}
    log.append(
        ToolLogEntry(
            step,
            name,
            args,
            "ok" if result.available else "error",
            int((time.monotonic() - start) * 1000),
            _hash(payload),
        )
    )
    cache[cache_key] = payload
    return payload


_SYSTEM = (
    "You are an offsite-presence researcher for a brand's GEO/AEO audit. The "
    "deterministic facts (Wikidata, review platforms, backlinks) are already "
    "gathered and given to you. Your job is the open-ended part: use web_search "
    "and reddit_search to find the community threads, 'best [category]' listicles, "
    "and press that actually mention the brand. Be efficient — you have a small "
    "search budget. When done, call submit_findings with concrete, evidence-backed "
    "findings (real URLs). Do not invent results."
)


class OffsiteAgent:
    """Hand-rolled, budget-bounded Anthropic tool-calling loop (§5.1)."""

    def __init__(self, model: str | None = None) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set; the offsite agent needs it.")
        self._model = model or settings.OFFSITE_AGENT_MODEL
        self._client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def run(
        self, brand: str, domain: str, prepass: list[OffsiteFinding]
    ) -> tuple[list[OffsiteFinding], list[ToolLogEntry], str]:
        tools: list[ToolParam] = [_search_tool(), _reddit_tool(), _submit_tool()]
        quotas = dict(TOOL_QUOTAS)
        cache: dict[str, Any] = {}
        log: list[ToolLogEntry] = []
        prepass_summary = json.dumps(
            [{"type": f.finding_type.value, "title": f.title} for f in prepass]
        )
        messages: list[Any] = [
            {
                "role": "user",
                "content": (
                    f"Brand: {brand}\nDomain: {domain}\n\n"
                    f"Already-gathered deterministic findings:\n{prepass_summary}\n\n"
                    "Research the open-ended offsite presence and submit findings."
                ),
            }
        ]
        temperature = anthropic.omit if "opus-4-8" in self._model else 0.0
        start = time.monotonic()

        for step in range(MAX_STEPS):
            if time.monotonic() - start > WALL_CLOCK_SECONDS:
                break
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=_AGENT_MAX_TOKENS,
                    temperature=temperature,
                    system=_SYSTEM,
                    messages=messages,
                    tools=tools,
                    tool_choice={"type": "auto"},
                )
            except anthropic.APIError as exc:
                logger.warning("offsite agent API error: %s", type(exc).__name__)
                return [], log, "failed"

            tool_uses = [b for b in response.content if isinstance(b, ToolUseBlock)]
            if not tool_uses:
                break  # model stopped calling tools without submitting

            messages.append({"role": "assistant", "content": _assistant_content(response)})
            tool_results: list[dict[str, Any]] = []
            for block in tool_uses:
                args = block.input if isinstance(block.input, dict) else {}
                if block.name == "submit_findings":
                    return _parse_findings(args), log, "ok"
                output = _dispatch_tool(block.name, args, quotas, cache, step, log)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output)[:4000],
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        # Budget exhausted without a submit — force one final structured submit.
        return self._force_submit(messages), log, "partial"

    def _force_submit(self, messages: list[Any]) -> list[OffsiteFinding]:
        try:
            messages.append(
                {
                    "role": "user",
                    "content": "Budget reached. Call submit_findings now with what you found.",
                }
            )
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_AGENT_MAX_TOKENS,
                temperature=anthropic.omit if "opus-4-8" in self._model else 0.0,
                system=_SYSTEM,
                messages=messages,
                tools=[_submit_tool()],
                tool_choice={"type": "tool", "name": "submit_findings"},
            )
            for block in response.content:
                if isinstance(block, ToolUseBlock) and isinstance(block.input, dict):
                    return _parse_findings(block.input)
        except anthropic.APIError as exc:
            logger.warning("offsite force-submit failed: %s", type(exc).__name__)
        return []


def _assistant_content(response: Message) -> list[dict[str, Any]]:
    """Re-serialize the assistant turn (text + tool_use blocks) for the next request."""
    blocks: list[dict[str, Any]] = []
    for block in response.content:
        if isinstance(block, ToolUseBlock):
            blocks.append(
                {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            )
        elif block.type == "text":
            blocks.append({"type": "text", "text": block.text})
    return blocks


def _parse_findings(submitted: dict[str, Any]) -> list[OffsiteFinding]:
    out: list[OffsiteFinding] = []
    for item in submitted.get("findings", []):
        if not isinstance(item, dict):
            continue
        try:
            ftype = FindingType(str(item.get("finding_type", "community")))
        except ValueError:
            ftype = FindingType.COMMUNITY
        try:
            conf = Confidence(str(item.get("confidence", "low")))
        except ValueError:
            conf = Confidence.LOW
        out.append(
            OffsiteFinding(
                finding_type=ftype,
                title=str(item.get("title", "")),
                url=(str(item["url"]) if item.get("url") else None),
                confidence=conf,
                payload={"summary": str(item.get("summary", ""))},
            )
        )
    return out


# --- orchestrator ------------------------------------------------------------


def run_offsite_research(brand: str, domain: str) -> OffsiteResult:
    """Run the pre-pass (always) and the agent loop (if an LLM + a search tool exist).

    Never raises — degrades to whatever findings the available sources produced.
    """
    result = OffsiteResult(brand=brand, domain=domain)
    try:
        pre_findings, pre_log = _deterministic_prepass(brand, domain)
    except Exception as exc:  # best-effort: pre-pass network hiccup
        logger.warning("offsite pre-pass failed: %s", type(exc).__name__)
        pre_findings, pre_log = [], []
    result.findings.extend(pre_findings)
    result.audit_log.extend(pre_log)

    if not settings.ANTHROPIC_API_KEY:
        result.status = "partial"
        result.note = "no LLM key — deterministic pre-pass only"
        return result
    has_search = bool(settings.SERPER_API_KEY) or bool(
        settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET
    )
    if not has_search:
        result.status = "partial"
        result.note = "no search tool configured — deterministic pre-pass only"
        return result

    try:
        findings, log, status = OffsiteAgent().run(brand, domain, pre_findings)
        result.findings.extend(findings)
        result.audit_log.extend(log)
        result.status = status
    except Exception as exc:  # agent is additive — never fail the phase
        logger.warning("offsite agent failed: %s", type(exc).__name__)
        result.status = "partial"
        result.note = "agent error — pre-pass findings only"
    return result
