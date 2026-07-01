from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum

import anthropic
from anthropic import Anthropic
from anthropic.types import Message, TextBlockParam, ToolChoiceToolParam, ToolParam

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
    "answer to a consumer's question. You record your assessment by calling the "
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
- "severity": high (would change a consumer's decision — wrong price, wrong model),
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

STOP — RUN THIS DELETE GATE ON EVERY FLAG BEFORE YOU OUTPUT. Test each flag
against its OWN cited "reality" line. Delete the flag if ANY rule fires (when in
doubt, DELETE — a dropped false alarm costs nothing, a false alarm costs trust):

1. ABSENCE / OMISSION → DELETE. The "claim" faults the answer for what it does
   NOT say — it contains "omits", "does not mention", "doesn't state/mention",
   "fails to", "no mention of", "the answer doesn't", or otherwise points at a
   missing fact. An omission is NEVER a flag, however important the missing fact.
2. AGREEMENT / CONFIRMATION → DELETE. The value the answer states is the SAME as
   the cited line — agreement is not a contradiction. Concrete deletes:
   - answer "$5.99/month" vs sheet "Membership: $5.99/month or $69.99/year" — same value.
   - answer "subscription required for full features" vs sheet "required membership
     for full features" — same fact, just reworded.
   But a price RANGE or figure that DIFFERS from the sheet is NOT agreement — it
   misrepresents the price, so KEEP it (e.g. answer "$299–$549" when the sheet says
   $399 base / $499 premium — the range's ends are wrong; that is a real flag).
3. SHEET-SILENT → DELETE. The cited line does not itself state a value the claim
   contradicts — e.g. it is a feature/spec LIST that merely lacks the claimed item,
   or it is about a different topic. Citing a list because it omits the claim is
   not a contradiction; the topic is UNVERIFIABLE.

A flag SURVIVES only if the answer makes a POSITIVE statement whose value DIRECTLY
CONFLICTS with its cited verbatim line — a price the sheet has replaced, an older
model/version named as the current or best one, or a feature the sheet explicitly
lists-as-present that the answer denies (or one the sheet rules out that the answer
asserts). If nothing survives the gate, return [].
"""

_NO_ACCURACY_BLOCK = (
    "\nNo fact sheet provided: return client_accuracy_flags as [] (accuracy not assessed).\n"
)

# The single-judge prompt splits cleanly in two: a per-answer HEAD that varies
# every call (the question + answer), and a RUBRIC tail that is identical for every
# answer in a run (the brand list + decision rules + accuracy block + fact sheet —
# by far the bulk of the tokens). The subscription pre-judge batcher exploits this:
# it renders the rubric ONCE per batch instead of once per answer, which is the
# main token saving (see scripts/judge_via_workflow.py, docs/subscription-judge-plan.md).
# Both halves are DERIVED by slicing the untouched _BASE_INSTRUCTIONS literal at the
# rubric marker, so _BASE_INSTRUCTIONS — and therefore _single_fingerprint and the
# live API judge — stay byte-for-byte identical.
_RUBRIC_MARKER = "\nBrands to score (CLIENT is marked):"
_ANSWER_HEAD = _BASE_INSTRUCTIONS[: _BASE_INSTRUCTIONS.index(_RUBRIC_MARKER)]
_RUBRIC_TAIL = _BASE_INSTRUCTIONS[_BASE_INSTRUCTIONS.index(_RUBRIC_MARKER) :]

# Marks the single-judge prompt DELIVERY (not just wording), folded into the cache
# fingerprint. 2026-06-30: the shared rubric moved into a cached system block placed
# BEFORE the per-answer head (was: rubric AFTER the head, in the user message) so the
# Anthropic prompt cache can reuse it across every answer in a run. That reorders what
# the model sees, so bump this to force a clean re-judge instead of mixing verdicts
# from the two layouts. Change this string whenever the delivery changes again.
_PROMPT_LAYOUT = "single:rubric-in-cached-system:v1"


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


def _brand_lines(client: str, competitors: list[str]) -> str:
    """The brand list shared by the single and cascade structural prompts."""
    return "\n".join([f"- {client} [CLIENT]"] + [f"- {c}" for c in competitors])


def _single_fingerprint(tool: ToolParam) -> str:
    """Hash of the single-judge prompt (text + delivery layout) + tool schema, folded
    into the cache key so editing the prompt — or how it's delivered — auto-invalidates
    the cache and forces a clean re-judge. ``_PROMPT_LAYOUT`` is part of the hash so the
    2026-06-30 rubric-into-cached-system change bumped the fingerprint deliberately."""
    return hashlib.sha256(
        (
            _SYSTEM
            + _BASE_INSTRUCTIONS
            + _ACCURACY_BLOCK
            + _NO_ACCURACY_BLOCK
            + _PROMPT_LAYOUT
            + json.dumps(tool, sort_keys=True, default=str)
        ).encode("utf-8")
    ).hexdigest()


# --- Two-tier cascade (opt-in): a cheap model does the structural reads
# (present/prominence/framing), an accurate model does the accuracy block — and
# only when a fact sheet exists. Action A (docs/judge-accuracy-plan.md §3.1)
# measured Haiku ≈ Sonnet on structural reads but with disqualifying flag recall,
# so each pass is a self-contained prompt + forced tool: neither model wastes
# tokens (or accuracy) on the other's job. ---

_STRUCTURAL_SYSTEM = (
    "You are a strict evaluator measuring how brands appear in an AI assistant's "
    "answer to a consumer's question. You record your assessment by calling the "
    "record_brands tool. Do NOT use any outside knowledge about the brands — judge "
    "present/prominence/framing only from the answer text."
)

_STRUCTURAL_INSTRUCTIONS = """Question asked: {query}

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
  NOT a mention — the answer never surfaced it as a known product. But if the
  answer INVENTS details about the brand (a made-up product name, features, or
  price), that IS present.
- prominence: recommended_first | mid_pack | buried | also_ran | absent
  (absent iff not present; this is RELATIVE across the brands — who is named/
  recommended first vs. buried at the bottom).
- framing: positive | neutral | negative (e.g. "avoid X" is negative).

Record your assessment by calling the record_brands tool: one entry per brand
listed above."""

_ACCURACY_SYSTEM = (
    "You are a strict fact-checker measuring whether an AI assistant's answer about "
    "a brand contradicts a provided fact sheet. You record your assessment by "
    "calling the record_flags tool. Judge accuracy ONLY against the provided fact "
    "sheet — never use outside knowledge. Every accuracy flag must cite the exact "
    "fact-sheet line it contradicts (copied verbatim); with no such line, do not "
    "flag. But when a line IS contradicted — a wrong price, an outdated model, an "
    "invented product or feature — you MUST flag it."
)

_ACCURACY_ONLY_INSTRUCTIONS = """Question asked: {query}

AI answer:
\"\"\"
{answer}
\"\"\"

The CLIENT brand to fact-check: {client}
{accuracy_block}
Record your assessment by calling the record_flags tool: client_accuracy_flags
(empty list if none apply)."""


def _structural_tool() -> ToolParam:
    """Forced tool for the cascade's structural pass — brands only, no flags."""
    return {
        "name": "record_brands",
        "description": "Record how each brand appears in the answer (present/prominence/framing).",
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
            },
            "required": ["brands"],
        },
    }


def _accuracy_tool() -> ToolParam:
    """Forced tool for the cascade's accuracy pass — client flags only."""
    return {
        "name": "record_flags",
        "description": "Record client accuracy flags checked against the fact sheet.",
        "input_schema": {
            "type": "object",
            "properties": {
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
            "required": ["client_accuracy_flags"],
        },
    }


def _cascade_identity(structural_model: str, accuracy_model: str) -> tuple[str, str]:
    """(cache model-id, prompt fingerprint) for a cascade judge. The model-id is
    composite (``cascade:<structural>+<accuracy>``) so cascade verdicts occupy a
    distinct cache keyspace from any single-model judge — they can legitimately
    differ, and must never be served for one another."""
    fingerprint = hashlib.sha256(
        (
            _STRUCTURAL_SYSTEM
            + _STRUCTURAL_INSTRUCTIONS
            + _ACCURACY_SYSTEM
            + _ACCURACY_ONLY_INSTRUCTIONS
            + _ACCURACY_BLOCK
            + json.dumps(_structural_tool(), sort_keys=True, default=str)
            + json.dumps(_accuracy_tool(), sort_keys=True, default=str)
            + structural_model
            + accuracy_model
        ).encode("utf-8")
    ).hexdigest()
    return f"cascade:{structural_model}+{accuracy_model}", fingerprint


# --- Adversarial flag verifier (opt-in): reviews ONE proposed flag at a time and
# keeps it only if it is a real contradiction. A focused per-flag judgment that
# the model honours far better than the global delete-gate, so it removes the
# omission/confirmation/sheet-silent false positives that survive the prompt. It
# only ever drops flags and defaults to KEEP on any uncertainty/failure, so it is
# recall-safe. Cheap enough to run on Haiku (narrow yes/no, not open detection). ---

_VERIFIER_SYSTEM = (
    "You are an adversarial fact-check auditor. You are given ONE accuracy flag "
    "another model raised about a client, the fact-sheet line it cited, and the "
    "answer under review. Decide only whether this is a REAL contradiction worth "
    "keeping or a false alarm to drop. Keep genuine contradictions; drop omissions, "
    "confirmations, and sheet-silent claims. When genuinely unsure, KEEP."
)

_VERIFIER_INSTRUCTIONS = """CLIENT: {client}

The AI answer under review:
\"\"\"
{answer}
\"\"\"

FACT SHEET (ground truth):
\"\"\"
{fact_sheet}
\"\"\"

A flag was raised on the CLIENT:
- type: {type}
- claim (what the answer supposedly states): {claim}
- cited reality (the fact-sheet line it allegedly contradicts): {reality}

DROP (keep=false) if ANY of these is true:
1. OMISSION — the claim faults the answer for what it does NOT say ("omits", "does
   not mention", "without mentioning", "fails to"). Omissions are never flags.
2. CONFIRMATION — the answer's stated value is the SAME as the cited line (answer
   "$399" vs sheet "$399"; answer "subscription required" vs sheet "required
   membership"). A price range or figure that DIFFERS from the sheet (e.g.
   "$299–$549" vs $399/$499) misrepresents it and is NOT confirmation — KEEP it.
3. SHEET-SILENT / WRONG LINE — the cited line does not itself state a value the
   claim contradicts (it's a list that merely lacks the item, or another topic).
4. NOT STATED — the answer does not actually make the claimed statement.

KEEP (keep=true) ONLY if the answer makes a positive statement whose value
DIRECTLY conflicts with the cited line — a price the sheet has replaced, an older
model/version named as the current or best one, or a feature the sheet lists-as-
present that the answer denies (or one the sheet rules out that the answer asserts).

Record your decision with the record_verdict tool."""


def _verifier_tool() -> ToolParam:
    """Forced tool for the per-flag verifier — a keep/drop verdict."""
    return {
        "name": "record_verdict",
        "description": "Keep or drop one proposed client accuracy flag.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keep": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["keep", "reason"],
        },
    }


def _verdict_keep(raw: dict[str, object] | None) -> bool:
    """Whether to keep a flag given the verifier's tool output. Recall-safe: a
    failed/absent verdict keeps the flag (never silently drops a real error)."""
    if raw is None:
        return True
    return bool(raw.get("keep", True))


class Judge:
    """One held-constant LLM that scores every answer — the detection 'brain'.

    Separate pass from the runner: feed it stored answers and re-judge any time
    without re-querying the engines. JSON is forced via a single required tool
    call (the Anthropic API has no json_object mode); a failed call degrades to
    ``assessed=False`` ("not assessed"), never raises.
    """

    def __init__(
        self,
        model: str | None = None,
        *,
        cascade: bool = False,
        structural_model: str | None = None,
        accuracy_model: str | None = None,
        verify: bool = False,
        verifier_model: str | None = None,
    ) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set; the judge needs it (see .env.example).")
        self._client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )
        # Two identities, kept SEPARATE: ``self._model`` is the real model the
        # single-judge call passes to the API; ``self._cache_model_id`` +
        # ``self._prompt_fingerprint`` form the cache identity (read by
        # judge_results/judge_answer_cached). They diverge for cascade/verify,
        # where the verdict depends on more than one model — folding that into the
        # cache id (not the API model) is what the earlier bug got wrong.
        self._cascade = cascade
        if cascade:
            # Two-tier: cheap structural model + accurate flag model. The composite
            # cache id keeps cascade verdicts apart from any single judge's; the
            # per-pass calls use _structural_model / _accuracy_model, not _model.
            self._structural_model = structural_model or settings.JUDGE_STRUCTURAL_MODEL
            self._accuracy_model = accuracy_model or settings.JUDGE_ACCURACY_MODEL
            self._structural_tool = _structural_tool()
            self._accuracy_tool = _accuracy_tool()
            self._model = self._accuracy_model  # unused for calls in cascade
            cache_model_id, base_fingerprint = _cascade_identity(
                self._structural_model, self._accuracy_model
            )
        else:
            self._model = model or settings.JUDGE_MODEL
            self._tool = _judgment_tool()
            cache_model_id = self._model
            base_fingerprint = _single_fingerprint(self._tool)

        # The verifier filters flags, so it changes the verdict — fold it into the
        # cache id + fingerprint (NOT the API model) so verified verdicts never
        # collide with unverified ones.
        self._verify = verify
        if verify:
            self._verifier_model = verifier_model or settings.JUDGE_VERIFIER_MODEL
            self._verifier_tool = _verifier_tool()
            cache_model_id = f"{cache_model_id}+verify:{self._verifier_model}"
            base_fingerprint = hashlib.sha256(
                (
                    base_fingerprint
                    + _VERIFIER_SYSTEM
                    + _VERIFIER_INSTRUCTIONS
                    + json.dumps(self._verifier_tool, sort_keys=True, default=str)
                    + self._verifier_model
                ).encode("utf-8")
            ).hexdigest()
        self._cache_model_id = cache_model_id
        self._prompt_fingerprint = base_fingerprint

    def _single_judge_messages(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None,
    ) -> tuple[list[TextBlockParam], str]:
        """Split the single-judge call into (system blocks, user prompt).

        The shared RUBRIC (brand list + rules + accuracy block + fact sheet — identical
        for every answer in a run) goes in ONE system block marked ``cache_control:
        ephemeral``, placed BEFORE the per-answer head. That makes it a stable prefix the
        Anthropic prompt cache reuses across the run, so only the small per-answer head
        (question + answer, in the user message) is fresh input each call."""
        accuracy_instructions = (
            _ACCURACY_BLOCK.format(fact_sheet=fact_sheet) if fact_sheet else _NO_ACCURACY_BLOCK
        )
        rubric = _RUBRIC_TAIL.format(
            brand_lines=_brand_lines(client, competitors),
            accuracy_instructions=accuracy_instructions,
        )
        system: list[TextBlockParam] = [
            {
                "type": "text",
                "text": _SYSTEM + "\n" + rubric,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        user = _ANSWER_HEAD.format(query=query_text, answer=answer)
        return system, user

    def _call_tool(
        self,
        model: str,
        system: str | list[TextBlockParam],
        prompt: str,
        tool: ToolParam,
        tool_name: str,
    ) -> dict[str, object] | None:
        """One forced-tool call → the tool's parsed input dict, or None on any
        failure (logged, never raised).

        Forced tool call = guaranteed structured JSON; no thinking (incompatible
        with a forced tool, unneeded for this classification pass). temperature=0
        makes the verdict reproducible — at the API default of 1.0 the flag list
        swung run-to-run. Opus-4.8-class models reject an explicit temperature, so
        omit it for them; the Haiku/Sonnet judge models accept 0.
        """
        try:
            tool_choice: ToolChoiceToolParam = {"type": "tool", "name": tool_name}
            temperature = anthropic.omit if "opus-4-8" in model else 0.0
            response = self._client.messages.create(
                model=model,
                max_tokens=_JUDGE_MAX_TOKENS,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice=tool_choice,
            )
            return _extract_tool_input(response)
        except (anthropic.APIError, KeyError, IndexError, ValueError) as exc:
            logger.warning(
                "Judge call failed (%s, not assessed): %s", tool_name, type(exc).__name__
            )
            return None
        except Exception as exc:  # never crash a run on the judge
            logger.warning(
                "Judge unexpected error (%s, not assessed): %s", tool_name, type(exc).__name__
            )
            return None

    def judge_answer(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None = None,
    ) -> tuple[list[BrandJudgment], list[AccuracyFlag], bool]:
        """Judge one answer. Returns (brand judgments, client accuracy flags, assessed)."""
        if self._cascade:
            return self._judge_cascade(query_text, answer, client, competitors, fact_sheet)
        return self._judge_single(query_text, answer, client, competitors, fact_sheet)

    def _judge_single(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None,
    ) -> tuple[list[BrandJudgment], list[AccuracyFlag], bool]:
        """One held-constant model scores brands + accuracy flags in a single call.

        The shared rubric rides in a cached system block (see ``_single_judge_messages``)
        so the API prompt-caches it across every answer in the run."""
        system, user = self._single_judge_messages(
            query_text, answer, client, competitors, fact_sheet
        )
        raw = self._call_tool(self._model, system, user, self._tool, "record_judgment")
        if raw is None:
            return [], [], False
        brands = _parse_brands(raw, client, competitors)
        flags = _parse_flags(raw) if fact_sheet else []
        if self._verify and fact_sheet and flags:
            flags = self._verify_flags(answer, client, fact_sheet, flags)
        return brands, flags, True

    def _judge_cascade(
        self,
        query_text: str,
        answer: str,
        client: str,
        competitors: list[str],
        fact_sheet: str | None,
    ) -> tuple[list[BrandJudgment], list[AccuracyFlag], bool]:
        """Cheap model reads brands; accurate model checks flags (only with a fact
        sheet). If the structural pass fails, nothing is assessed; if only the
        accuracy pass fails, the answer is left not-assessed (so it's re-judged
        next time, never cached without its flags)."""
        s_prompt = _STRUCTURAL_INSTRUCTIONS.format(
            query=query_text, answer=answer, brand_lines=_brand_lines(client, competitors)
        )
        raw_s = self._call_tool(
            self._structural_model,
            _STRUCTURAL_SYSTEM,
            s_prompt,
            self._structural_tool,
            "record_brands",
        )
        if raw_s is None:
            return [], [], False
        brands = _parse_brands(raw_s, client, competitors)
        if not fact_sheet:
            return brands, [], True
        a_prompt = _ACCURACY_ONLY_INSTRUCTIONS.format(
            query=query_text,
            answer=answer,
            client=client,
            accuracy_block=_ACCURACY_BLOCK.format(fact_sheet=fact_sheet),
        )
        raw_a = self._call_tool(
            self._accuracy_model, _ACCURACY_SYSTEM, a_prompt, self._accuracy_tool, "record_flags"
        )
        if raw_a is None:
            return brands, [], False
        flags = _parse_flags(raw_a)
        if self._verify and flags:
            flags = self._verify_flags(answer, client, fact_sheet, flags)
        return brands, flags, True

    def _verify_flags(
        self, answer: str, client: str, fact_sheet: str, flags: list[AccuracyFlag]
    ) -> list[AccuracyFlag]:
        """Adversarially review each flag and keep only the real contradictions.

        One focused keep/drop call per flag (recall-safe: a failed verdict keeps
        the flag). Drops the omission/confirmation/sheet-silent false positives the
        main prompt's gate misses."""
        kept: list[AccuracyFlag] = []
        for f in flags:
            prompt = _VERIFIER_INSTRUCTIONS.format(
                client=client,
                answer=answer,
                fact_sheet=fact_sheet,
                type=f.type,
                claim=f.claim,
                reality=f.reality,
            )
            raw = self._call_tool(
                self._verifier_model,
                _VERIFIER_SYSTEM,
                prompt,
                self._verifier_tool,
                "record_verdict",
            )
            if _verdict_keep(raw):
                kept.append(f)
        return kept

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
            model=self._cache_model_id,
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
                    model=self._cache_model_id,
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
