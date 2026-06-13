from __future__ import annotations

import logging
from enum import StrEnum

import anthropic
from anthropic import Anthropic
from anthropic.types import Message, ToolChoiceToolParam, ToolParam

from src.config import settings
from src.storage.models import (
    AccuracyFlag,
    AccuracyFlagType,
    AnswerJudgment,
    BrandJudgment,
    Framing,
    Prominence,
    QueryResult,
    Severity,
)

# The judgment data types live in storage.models (the data layer) so the storage
# module can (de)serialize them without importing this pipeline module (which
# pulls in the openai SDK). Re-exported here for back-compat.
__all__ = [
    "Prominence",
    "Framing",
    "AccuracyFlagType",
    "Severity",
    "BrandJudgment",
    "AccuracyFlag",
    "AnswerJudgment",
    "Judge",
    "summarize_judgments",
]

logger = logging.getLogger(__name__)


_SYSTEM = (
    "You are a strict evaluator measuring how brands appear in an AI assistant's "
    "answer to a buyer's question. You record your assessment by calling the "
    "record_judgment tool. Do NOT use any outside knowledge about the brands — "
    "judge present/prominence/framing only from the answer text, and judge "
    "accuracy ONLY against the provided fact sheet."
)

# JSON shape is enforced by a forced tool call rather than a response_format flag
# (the Anthropic API has no json_object mode). Output is small structured JSON;
# 4096 leaves headroom for many accuracy flags without risking truncation.
_JUDGE_MAX_TOKENS = 4096

_BASE_INSTRUCTIONS = """Question asked: {query}

AI answer:
\"\"\"
{answer}
\"\"\"

Brands to score (CLIENT is marked):
{brand_lines}

For EACH brand above, decide:
- present: true/false — is the brand mentioned at all?
- prominence: recommended_first | mid_pack | buried | also_ran | absent
  (absent iff not present; this is RELATIVE across the brands — who is named/
  recommended first vs. buried at the bottom).
- framing: positive | neutral | negative (e.g. "avoid X" is negative).
{accuracy_instructions}
Record your assessment by calling the record_judgment tool: one brands entry per
brand listed above, plus client_accuracy_flags (empty if none apply)."""

_ACCURACY_BLOCK = """
CLIENT FACT SHEET (ground truth — the ONLY allowed source for accuracy):
\"\"\"
{fact_sheet}
\"\"\"

For the CLIENT ONLY, compare what the answer claims about the client to the fact
sheet. For each incorrect or invented claim, add a client_accuracy_flags entry with:
- "type": one of: wrong_pricing, missing_or_invented_feature,
  competitor_confusion, identity, stale
- "claim": what the answer said
- "reality": what the fact sheet says (the correct value)
- "severity": high, med, or low
Only flag claims checkable against the fact sheet — if a fact isn't in the sheet,
do NOT flag it. If the answer doesn't discuss the client, return [].
"""

_NO_ACCURACY_BLOCK = (
    "\nNo fact sheet provided: return client_accuracy_flags as [] (accuracy not assessed).\n"
)


def _judgment_tool() -> ToolParam:
    """The forced tool the judge calls — its input schema IS the judgment JSON.

    Enums are sourced from the data-layer types so the schema can't drift from
    what the parsers accept.
    """
    return {
        "name": "record_judgment",
        "description": (
            "Record how each brand appears in the answer, plus any client accuracy "
            "flags checked against the fact sheet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "brands": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "brand": {"type": "string"},
                            "present": {"type": "boolean"},
                            "prominence": {"type": "string", "enum": [p.value for p in Prominence]},
                            "framing": {"type": "string", "enum": [f.value for f in Framing]},
                        },
                        "required": ["brand", "present", "prominence", "framing"],
                    },
                },
                "client_accuracy_flags": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": [t.value for t in AccuracyFlagType]},
                            "claim": {"type": "string"},
                            "reality": {"type": "string"},
                            "severity": {"type": "string", "enum": [s.value for s in Severity]},
                        },
                        "required": ["type", "claim", "reality", "severity"],
                    },
                },
            },
            "required": ["brands", "client_accuracy_flags"],
        },
    }


def _extract_tool_input(response: Message) -> dict[str, object]:
    """Pull the record_judgment tool input (already a parsed dict) from the reply."""
    for block in response.content:
        if block.type == "tool_use" and isinstance(block.input, dict):
            return block.input
    raise ValueError("judge response contained no record_judgment tool call")


class Judge:
    """One held-constant LLM that scores every answer — the detection 'brain'.

    Separate pass from the runner: feed it stored answers and re-judge any time
    without re-querying the engines. JSON is forced via a single required tool
    call (the Anthropic API has no json_object mode); a failed call degrades to
    ``assessed=False`` ("not assessed"), never raises.
    """

    def __init__(self, model: str | None = None) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set; the judge needs it (see .env.example).")
        self._model = model or settings.JUDGE_MODEL
        self._client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )
        self._tool = _judgment_tool()

    def _build_prompt(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None,
    ) -> str:
        brand_lines = "\n".join([f"- {client} [CLIENT]"] + [f"- {c}" for c in competitors])
        accuracy_instructions = (
            _ACCURACY_BLOCK.format(fact_sheet=fact_sheet) if fact_sheet else _NO_ACCURACY_BLOCK
        )
        return _BASE_INSTRUCTIONS.format(
            query=query_text,
            answer=answer,
            brand_lines=brand_lines,
            accuracy_instructions=accuracy_instructions,
        )

    def judge_answer(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None = None,
    ) -> tuple[list[BrandJudgment], list[AccuracyFlag], bool]:
        """Judge one answer. Returns (brand judgments, client accuracy flags, assessed)."""
        prompt = self._build_prompt(query_text, answer, client, competitors, fact_sheet)
        try:
            # Forced tool call = guaranteed structured JSON. No temperature (Opus
            # 4.8 rejects it) and no thinking (incompatible with a forced tool and
            # unneeded for this classification pass).
            tool_choice: ToolChoiceToolParam = {"type": "tool", "name": "record_judgment"}
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_JUDGE_MAX_TOKENS,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                tools=[self._tool],
                tool_choice=tool_choice,
            )
            raw = _extract_tool_input(response)
        except (anthropic.APIError, KeyError, IndexError, ValueError) as exc:
            logger.warning("Judge failed (not assessed): %s", type(exc).__name__)
            return [], [], False
        except Exception as exc:  # never crash a run on the judge
            logger.warning("Judge unexpected error (not assessed): %s", type(exc).__name__)
            return [], [], False

        brands = _parse_brands(raw, client, competitors)
        flags = _parse_flags(raw) if fact_sheet else []
        return brands, flags, True

    def judge_results(
        self,
        results: list[QueryResult],
        client: str,
        competitors: list[str],
        fact_sheet: str | None = None,
        progress: bool = False,
    ) -> list[AnswerJudgment]:
        """Judge every answered result. Identical answers (temp 0 repeats) are
        judged once and reused, so multi-run cycles don't multiply judge calls.

        ``progress`` prints an incremental count to stdout (every 20 answers plus
        the last) — a re-judge is many sequential API calls, so a long run is
        otherwise silent. Off by default; callers with their own status surface
        (the API runner) leave it off.
        """
        cache: dict[tuple[str, str], tuple[list[BrandJudgment], list[AccuracyFlag], bool]] = {}
        total = sum(1 for r in results if r["response"] is not None)
        done = 0
        judgments: list[AnswerJudgment] = []
        for r in results:
            answer = r["response"]
            if answer is None:
                continue  # nothing to judge
            key = (r["prompt"], answer)
            if key not in cache:
                cache[key] = self.judge_answer(r["prompt"], answer, client, competitors, fact_sheet)
            brands, flags, assessed = cache[key]
            done += 1
            if progress and (done % 20 == 0 or done == total):
                print(f"  judged {done}/{total} answers", flush=True)
            judgments.append(
                AnswerJudgment(
                    query_id=r["query_id"],
                    engine_name=r["engine_name"],
                    intent=r["intent"],
                    run_index=r["run_index"],
                    assessed=assessed,
                    brands=brands,
                    accuracy_flags=flags,
                )
            )
        return judgments


def _coerce(value: object, allowed: type[StrEnum], default: str) -> str:
    try:
        return allowed(str(value)).value
    except ValueError:
        return default


def _parse_brands(
    raw: dict[str, object], client: str, competitors: list[str]
) -> list[BrandJudgment]:
    by_name: dict[str, dict[str, object]] = {}
    raw_brands = raw.get("brands")
    if isinstance(raw_brands, list):
        for item in raw_brands:
            if isinstance(item, dict) and item.get("brand"):
                by_name[str(item["brand"]).strip().lower()] = item

    out: list[BrandJudgment] = []
    for brand in [client, *competitors]:
        item = by_name.get(brand.strip().lower(), {})
        present = bool(item.get("present", False))
        prominence = _coerce(item.get("prominence"), Prominence, Prominence.ABSENT.value)
        if not present:
            prominence = Prominence.ABSENT.value
        framing = _coerce(item.get("framing"), Framing, Framing.NEUTRAL.value)
        out.append(
            BrandJudgment(brand=brand, present=present, prominence=prominence, framing=framing)
        )
    return out


def _parse_flags(raw: dict[str, object]) -> list[AccuracyFlag]:
    flags: list[AccuracyFlag] = []
    raw_flags = raw.get("client_accuracy_flags")
    if not isinstance(raw_flags, list):
        return flags
    for item in raw_flags:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim", "")).strip()
        reality = str(item.get("reality", "")).strip()
        if not claim and not reality:
            continue  # nothing checkable
        flag_type = item.get("type")
        try:
            type_value = AccuracyFlagType(str(flag_type)).value
        except ValueError:
            continue  # unknown flag type -> skip rather than invent
        flags.append(
            AccuracyFlag(
                type=type_value,
                claim=claim,
                reality=reality,
                severity=_coerce(item.get("severity"), Severity, Severity.MED.value),
            )
        )
    return flags


def summarize_judgments(
    judgments: list[AnswerJudgment], client: str, competitors: list[str]
) -> str:
    """Markdown summary: per-brand present/recommended-first rates + client flags."""
    assessed = [j for j in judgments if j.assessed]
    lines: list[str] = ["# Judge Summary", ""]
    lines.append(f"Assessed {len(assessed)} of {len(judgments)} answers.")
    lines.append("")
    lines.append("| Brand | Present | Recommended-first | Negative |")
    lines.append("| --- | --- | --- | --- |")
    total = len(assessed) or 1
    for brand in [client, *competitors]:
        bjs = [b for j in assessed for b in j.brands if b.brand == brand]
        present = sum(1 for b in bjs if b.present)
        rec_first = sum(1 for b in bjs if b.prominence == Prominence.RECOMMENDED_FIRST.value)
        negative = sum(1 for b in bjs if b.framing == Framing.NEGATIVE.value)
        marker = " (client)" if brand == client else ""
        lines.append(
            f"| {brand}{marker} | {present}/{total} | {rec_first}/{total} | {negative}/{total} |"
        )
    lines.append("")

    flags = [f for j in assessed for f in j.accuracy_flags]
    lines.append(f"## Client Accuracy Flags ({len(flags)})")
    lines.append("")
    if not flags:
        lines.append("_None flagged (or no fact sheet provided → accuracy not assessed)._")
    else:
        lines.append("| Type | Severity | Claim → Reality |")
        lines.append("| --- | --- | --- |")
        for f in flags:
            lines.append(f"| {f.type} | {f.severity} | {f.claim} → {f.reality} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        judge = Judge()
    except ValueError as exc:
        print(f"Cannot run judge: {exc}")
        raise SystemExit(0) from None

    answer = (
        "For students, the best budgeting app is YNAB. Centsible is a newer option but "
        "it's pricey at $20/month and only on iOS. Rocket Money is also worth a look."
    )
    fact_sheet = "Centsible pricing: free tier + $5/month premium. Platforms: iOS and Android."
    brands, flags, assessed = judge.judge_answer(
        "best budgeting app for college students",
        answer,
        client="Centsible",
        competitors=["YNAB", "Rocket Money"],
        fact_sheet=fact_sheet,
    )
    print("assessed:", assessed)
    for b in brands:
        print(f"  {b.brand}: present={b.present} prominence={b.prominence} framing={b.framing}")
    for f in flags:
        print(f"  FLAG {f.type} ({f.severity}): {f.claim} -> {f.reality}")
