from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum

import anthropic
from anthropic import Anthropic
from anthropic.types import Message, ToolChoiceToolParam, ToolParam

from src.config import settings
from src.pipeline.judge_cache import JudgeCache, Verdict
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
    "accuracy ONLY against the provided fact sheet. Every accuracy flag must cite "
    "the exact fact-sheet line it contradicts (copied verbatim); with no such "
    "line, do not flag. But when a line IS contradicted — a wrong price, an "
    "outdated model, an invented product or feature — you MUST flag it."
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
  DISAVOWAL RULE: if the answer says it does not recognize the brand or has no
  information about it ("there isn't a widely known X", "I don't have specific
  information about X", "a product that launched after my training data"), mark
  present=FALSE. The brand name appearing only because the question named it is
  NOT a mention — the answer never surfaced it as a known product. (A disavowal
  is a knowledge gap, NEVER an accuracy flag.) But if the answer INVENTS details
  about the brand (a made-up product name, features, or price), that IS present —
  and those invented claims ARE flags.
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

For the CLIENT ONLY, flag claims the answer makes that **directly contradict a
specific line in the fact sheet above**. A flag requires a contradiction, not
just a topic the sheet is silent on. Flag EVERY such contradiction — but only
those you can back with a verbatim sheet line.

THE TEST for each client claim, in order:
1. Find the EXACT fact-sheet line it would contradict, ready to copy verbatim.
   If NO line addresses the topic, the claim is UNVERIFIABLE — do NOT flag it
   (silence is not disagreement). Example: the answer praises the client's
   privacy and the sheet says nothing about privacy → NOT a flag.
2. If a line addresses it AND the answer agrees → NOT a flag.
3. Only if a line addresses it AND the answer contradicts it → add a flag.

HARD GATE: "reality" MUST be a span copied VERBATIM from the fact sheet above.
If you cannot copy an exact contradicting line, drop the flag. Never paraphrase,
infer, or rely on outside knowledge of the brand.

HALLUCINATION: if the answer invents the client — a made-up product name, form
factor, or features found nowhere in the sheet, or it DENIES features the sheet
lists — those invented/denied claims ARE flags; cite the identity or feature
line they contradict. (This differs from a disavowal, which says nothing about
the brand and is never flagged.)

DISAVOWAL: if the answer says it does not recognize the client or has no
information about it ("there isn't a brand called X", "I don't have information
about X", "a product that launched after my training data"), that is a knowledge
gap and is NEVER a flag — not identity, not anything. Return [] for the client.

OMISSION: an omission is NEVER a flag. Only flag something the answer actually
STATES that contradicts a line. If the answer simply does NOT mention a fact —
the required subscription, the current model, a feature — that is not a flag, no
matter how important the omitted fact is. Never write a flag whose "claim" is
"the answer omits X" or "the answer does not mention X": there must be a positive
statement IN the answer that conflicts with the sheet.

Per-type rules (each STILL requires a verbatim contradicted line):
- wrong_pricing: only if the answer states a specific price/subscription figure
  that a sheet price line contradicts — including a stale/superseded figure (e.g.
  quoting an old base price the sheet has replaced, even inside a range). A vague
  "expensive"/"pricey" with NO number is NOT a flag.
- stale: you MUST flag it when the answer names an old model/version/date a
  sheet line supersedes — including naming an older generation as the current or
  best product (e.g. the answer says "Gen 3" or "Ring 4" while a sheet line names
  a newer current model). Cite that current-model line as "reality".
- missing_or_invented_feature: only if a sheet feature line or its "is NOT /
  misconceptions" line explicitly contradicts the claim (denies a feature the
  sheet lists, or asserts one the sheet rules out). Do NOT flag a plausible
  feature the sheet simply doesn't mention.
- identity: only if the answer states who/what the brand is in a way a sheet
  line contradicts (wrong category/company, fabricated product name). A
  disavowal ("there is no such brand") is NOT an identity flag.
- competitor_confusion: only if the answer attributes a named rival's
  identity/feature to the client against a sheet line.

Each client_accuracy_flags entry:
- "type": the dimension of the contradicted line.
- "claim": what the answer said (quote it)
- "reality": the EXACT fact-sheet line it contradicts, copied VERBATIM. If this
  is not a word-for-word quote from the sheet above, the flag is invalid.
- "severity": high (would change a buyer's decision — wrong price, wrong model),
  med (misleading but not decisive), low (minor)

EXAMPLES (the mistakes to avoid):
- Disavowal -> []: "There isn't a widely recognized brand called Fort." The
  client is absent; there is nothing to flag.
- Confirmed claim -> []: the answer says "membership is $5.99/month" and the
  sheet says "Membership: $5.99/month" — the claim MATCHES the sheet, NOT a flag.
- Omission -> []: the answer recommends Oura but never mentions the required
  membership. Saying nothing about a fact is NOT a flag — only a stated
  contradiction is.
- Real contradiction -> flag: the answer says "the newest is the Oura Ring 4" and
  the sheet says "Oura Ring 5 (current model)" — that contradicts the line, so
  flag stale with reality = the "Oura Ring 5 (current model)" line.

FINAL CHECK before you finish — for every flag confirm ALL THREE: (a) "reality"
is a word-for-word line from the fact sheet, (b) "claim" is something the answer
actually STATES (not an omission — never "the answer doesn't mention X"), AND
(c) the claim CONTRADICTS that line, not merely matches, restates, or is
confirmed by it. If the claim agrees with the cited line (e.g. the answer's price
equals the sheet's price), or is an omission, it is NOT a flag — delete it. If
the answer makes no claim that contradicts a sheet line, return [].
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
        # Fingerprint of the judge's prompt + tool schema. Folded into the cache
        # key so editing the system prompt or the tool (a determinant of the
        # verdict that the per-answer inputs don't capture) auto-invalidates the
        # cache, instead of relying on a manually-bumped schema version.
        self._prompt_fingerprint = hashlib.sha256(
            (
                _SYSTEM
                + _BASE_INSTRUCTIONS
                + _ACCURACY_BLOCK
                + _NO_ACCURACY_BLOCK
                + json.dumps(self._tool, sort_keys=True, default=str)
            ).encode("utf-8")
        ).hexdigest()

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
            # Forced tool call = guaranteed structured JSON; no thinking
            # (incompatible with a forced tool, unneeded for this classification
            # pass). temperature=0 makes the verdict reproducible — at the API
            # default of 1.0 the flag list swung run-to-run. Opus-4.8-class models
            # reject an explicit temperature, so omit it for them; the Haiku/Sonnet
            # judge models accept 0.
            tool_choice: ToolChoiceToolParam = {"type": "tool", "name": "record_judgment"}
            temperature = anthropic.omit if "opus-4-8" in self._model else 0.0
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_JUDGE_MAX_TOKENS,
                temperature=temperature,
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

    def judge_answer_cached(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None,
        cache: JudgeCache | None,
    ) -> tuple[list[BrandJudgment], list[AccuracyFlag], bool]:
        """``judge_answer`` with persistent caching for single-answer callers
        (e.g. calibration). A verdict keyed by (model, prompt fingerprint, client,
        competitors, fact sheet, query, answer) is reused with no API call — so a
        re-run over an unchanged gold set is free and byte-identical. Editing the
        judge prompt changes the fingerprint and correctly forces a re-judge.
        Only successfully-assessed verdicts are cached (a transient failure is
        re-judged next time, never persisted)."""
        if cache is None:
            return self.judge_answer(query_text, answer, client, competitors, fact_sheet)
        ck = cache.key(
            model=self._model,
            prompt_fingerprint=self._prompt_fingerprint,
            client=client,
            competitors=competitors,
            fact_sheet=fact_sheet,
            prompt=query_text,
            answer=answer,
        )
        hit = cache.get(ck) if ck is not None else None
        if hit is not None:
            return hit
        verdict = self.judge_answer(query_text, answer, client, competitors, fact_sheet)
        if ck is not None and verdict[2]:
            cache.put_many([(ck, verdict)])
        return verdict

    def judge_results(
        self,
        results: list[QueryResult],
        client: str,
        competitors: list[str],
        fact_sheet: str | None = None,
        progress: bool = False,
        cache: JudgeCache | None = None,
    ) -> list[AnswerJudgment]:
        """Judge every answered result. Identical answers (temp 0 repeats) are
        judged once and reused, so multi-run cycles don't multiply judge calls.

        The unique answers are judged **concurrently** (each ``judge_answer`` is
        an independent, stateless API call), then re-joined to the results in
        their original order, so dedup, ordering, and the verdicts are identical
        to the sequential version — only faster.

        ``cache`` — an optional persistent ``JudgeCache``. A verdict is fully
        determined by (judge model, client, competitors, fact sheet, prompt,
        answer), so an answer already judged under those exact inputs is reused
        with no API call — across resumes, re-runs, and cadence re-checks. Only
        the genuinely-new answers cost anything; editing the fact sheet changes
        the key and correctly forces a re-judge.

        ``progress`` prints an incremental count to stdout (every 20 answers plus
        the last) — a re-judge is many API calls, so a long run is otherwise
        silent. Off by default; callers with their own status surface (the API
        runner) leave it off.
        """
        # Distinct answers to judge, in first-seen order (deterministic).
        unique_keys: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for r in results:
            answer = r["response"]
            if answer is None:
                continue  # nothing to judge
            key = (r["prompt"], answer)
            if key not in seen:
                seen.add(key)
                unique_keys.append(key)

        verdicts: dict[tuple[str, str], tuple[list[BrandJudgment], list[AccuracyFlag], bool]] = {}
        if unique_keys:

            def cache_key(prompt: str, answer: str) -> str | None:
                if cache is None:
                    return None
                return cache.key(
                    model=self._model,
                    prompt_fingerprint=self._prompt_fingerprint,
                    client=client,
                    competitors=competitors,
                    fact_sheet=fact_sheet,
                    prompt=prompt,
                    answer=answer,
                )

            # Split into answers already judged (free reuse) and the rest. The
            # content key (computed once here) is carried alongside each
            # to-judge entry so it isn't hashed a second time when storing.
            to_judge: list[tuple[tuple[str, str], str | None]] = []
            reused = 0
            for key in unique_keys:
                prompt, answer = key
                ck = cache_key(prompt, answer)
                hit = cache.get(ck) if (cache is not None and ck is not None) else None
                if hit is not None:
                    verdicts[key] = hit
                    reused += 1
                else:
                    to_judge.append((key, ck))
            if reused and progress:
                print(f"  reused {reused} cached judgments", flush=True)

            def judge_key(
                item: tuple[tuple[str, str], str | None],
            ) -> tuple[
                tuple[str, str], str | None, tuple[list[BrandJudgment], list[AccuracyFlag], bool]
            ]:
                (prompt, answer), ck = item
                verdict = self.judge_answer(prompt, answer, client, competitors, fact_sheet)
                return (prompt, answer), ck, verdict

            if to_judge:
                # The judge is a single provider (Anthropic), so cap it like any
                # one provider rather than the whole-fleet ENGINE_CONCURRENCY —
                # firing 12+ at once risks 429s, which (returned as not-assessed)
                # would otherwise be cached as permanent failures.
                total = len(to_judge)
                workers = max(1, min(settings.ENGINE_PROVIDER_CONCURRENCY, total))
                done = 0
                # Only successfully-assessed verdicts are cached, in one batch —
                # a transient failure (assessed=False) is never persisted, so it
                # is re-judged next time instead of poisoning the cache.
                to_store: list[tuple[str, Verdict]] = []
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for key, ck, verdict in pool.map(judge_key, to_judge):
                        verdicts[key] = verdict
                        if cache is not None and ck is not None and verdict[2]:
                            to_store.append((ck, verdict))
                        done += 1
                        if progress and (done % 20 == 0 or done == total):
                            print(f"  judged {done}/{total} answers", flush=True)
                if cache is not None and to_store:
                    cache.put_many(to_store)

        judgments: list[AnswerJudgment] = []
        for r in results:
            answer = r["response"]
            if answer is None:
                continue
            brands, flags, assessed = verdicts[(r["prompt"], answer)]
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
