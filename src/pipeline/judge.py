from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum

import openai
from openai import OpenAI

from src.config import settings
from src.storage.models import QueryResult

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
    run_index: int
    assessed: bool  # False = judge failed -> "not assessed", never crashes
    brands: list[BrandJudgment]
    accuracy_flags: list[AccuracyFlag]  # client only; empty without a fact sheet


_SYSTEM = (
    "You are a strict evaluator measuring how brands appear in an AI assistant's "
    "answer to a buyer's question. You output ONLY JSON. Do NOT use any outside "
    "knowledge about the brands — judge present/prominence/framing only from the "
    "answer text, and judge accuracy ONLY against the provided fact sheet."
)

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
Return JSON exactly in this shape and nothing else:
{{"brands":[{{"brand":"<name>","present":true,"prominence":"mid_pack","framing":"neutral"}}],"client_accuracy_flags":[{accuracy_example}]}}"""

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


class Judge:
    """One held-constant LLM that scores every answer — the detection 'brain'.

    Separate pass from the runner: feed it stored answers and re-judge any time
    without re-querying the engines. Low temperature + forced JSON; a failed call
    degrades to ``assessed=False`` ("not assessed"), never raises.
    """

    def __init__(self, model: str | None = None) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set; the judge needs it (see .env.example).")
        self._model = model or settings.JUDGE_MODEL
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def _build_prompt(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None,
    ) -> str:
        brand_lines = "\n".join([f"- {client} [CLIENT]"] + [f"- {c}" for c in competitors])
        if fact_sheet:
            accuracy_instructions = _ACCURACY_BLOCK.format(fact_sheet=fact_sheet)
            accuracy_example = (
                '{"type":"wrong_pricing","claim":"...","reality":"...","severity":"high"}'
            )
        else:
            accuracy_instructions = _NO_ACCURACY_BLOCK
            accuracy_example = ""
        return _BASE_INSTRUCTIONS.format(
            query=query_text,
            answer=answer,
            brand_lines=brand_lines,
            accuracy_instructions=accuracy_instructions,
            accuracy_example=accuracy_example,
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
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=settings.ENGINE_TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or ""
            raw = json.loads(content)
        except (openai.APIError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
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
    ) -> list[AnswerJudgment]:
        """Judge every answered result. Identical answers (temp 0 repeats) are
        judged once and reused, so multi-run cycles don't multiply judge calls.
        """
        cache: dict[tuple[str, str], tuple[list[BrandJudgment], list[AccuracyFlag], bool]] = {}
        judgments: list[AnswerJudgment] = []
        for r in results:
            answer = r["response"]
            if answer is None:
                continue  # nothing to judge
            key = (r["prompt"], answer)
            if key not in cache:
                cache[key] = self.judge_answer(r["prompt"], answer, client, competitors, fact_sheet)
            brands, flags, assessed = cache[key]
            judgments.append(
                AnswerJudgment(
                    query_id=r["query_id"],
                    engine_name=r["engine_name"],
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
