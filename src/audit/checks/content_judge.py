"""Cat 3/4 — Content structure & E-E-A-T LLM judge (impl guide §4).

Clones the ``src/pipeline/judge.py`` discipline for the on-site subjective checks:
forced-tool-call structured output, reasoning-first ordering, mandatory evidence
spans validated in code, and a per-check truth table computed in Python (not a
gestalt grade). It judges the deterministic checkers' blind spots — answer-first
leads, self-contained chunks, original data, expert commentary, external
citations — over a page's extracted main text.

Design (per §4):
- **Atomic decomposition (§4.2):** each check is 2–4 binary yes/no/unknown
  sub-questions; the verdict is a fixed truth table (all-yes→pass, all-no→fail,
  mixed→partial, any-unknown→unknown). The table is the rubric's contract — it is
  versioned with :data:`CONTENT_RUBRIC_VERSION`.
- **Reasoning-first (§4.1):** the tool schema emits ``reasoning`` then
  ``evidence_quote`` then the ``answer`` enum last, so the model thinks before it
  decides. All fields are required (Anthropic emits required props first).
- **Evidence enforcement (§4.3):** an affirmative (``yes``) sub-answer must quote
  a verbatim span that actually appears in the page text (whitespace/case/NFC
  normalized, rapidfuzz fallback); if it doesn't, the sub-answer is downgraded to
  ``unknown`` and the check is flagged ``needs_review``.

**Not wired into the live run yet** — per plan §7 the subjective judge must be
calibrated against a hand-labeled gold set (κ ≥ 0.6) before any verdict is shown
to a client. See ``content_calibration.py`` for the harness this plugs into.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import anthropic
from anthropic import Anthropic
from anthropic.types import Message, ToolChoiceToolParam, ToolParam
from rapidfuzz import fuzz

from src.audit.crawl.models import PageRecord

if TYPE_CHECKING:
    from src.audit.checks.content_judge_cache import ContentJudgeCache

__all__ = [
    "ContentClass",
    "SubQuestion",
    "ContentCheck",
    "SubAnswer",
    "CheckVerdict",
    "ContentJudgeResult",
    "CONTENT_CHECKS",
    "CONTENT_RUBRIC_VERSION",
    "ContentJudge",
    "evidence_supported",
    "verdict_from_answers",
    "finalize_check",
]

logger = logging.getLogger(__name__)

# Bump on any change to CONTENT_CHECKS or the truth table — verdicts are only
# comparable within a version, and it's folded into the verdict-cache key (§4.6).
CONTENT_RUBRIC_VERSION = "2026-06-content-v1"

# Affirmative evidence quotes must match the source at least this well (rapidfuzz
# partial-ratio) when not an exact normalized substring — a last-resort allowance
# for minor tokenization differences, per §4.3.
_EVIDENCE_FUZZ_FLOOR = 95.0

_JUDGE_MAX_TOKENS = 2048


class ContentClass(StrEnum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    UNKNOWN = "unknown"  # abstain / needs review


@dataclass(frozen=True)
class SubQuestion:
    key: str
    text: str


@dataclass(frozen=True)
class ContentCheck:
    check_id: str
    category: int  # 3 or 4
    title: str
    sub_questions: tuple[SubQuestion, ...]


@dataclass
class SubAnswer:
    key: str
    question: str
    reasoning: str
    evidence_quote: str
    answer: str  # yes | no | unknown
    evidence_valid: bool


@dataclass
class CheckVerdict:
    check_id: str
    category: int
    classification: ContentClass
    reason: str
    sub_answers: list[SubAnswer]
    needs_review: bool


@dataclass
class ContentJudgeResult:
    page_url: str
    verdicts: list[CheckVerdict]
    assessed: bool  # False if the page had no text / the model couldn't be reached
    rubric_version: str = CONTENT_RUBRIC_VERSION


# --- the rubric (versioned contract) -----------------------------------------

CONTENT_CHECKS: tuple[ContentCheck, ...] = (
    ContentCheck(
        "answer_first_lead",
        3,
        "Answer-first lead",
        (
            SubQuestion(
                "direct",
                "Does the page open with a direct answer to its main question in ~60 words?",
            ),
            SubQuestion(
                "before_preamble", "Does the answer come before background/marketing preamble?"
            ),
            SubQuestion(
                "concise", "Is the opening answer concise (about one 40–60 word paragraph)?"
            ),
        ),
    ),
    ContentCheck(
        "self_contained_chunks",
        3,
        "Self-contained chunks",
        (
            SubQuestion(
                "standalone", "Can each major section be understood without earlier sections?"
            ),
            SubQuestion(
                "explicit_subject", "Does each section name its subject, not far-back pronouns?"
            ),
        ),
    ),
    ContentCheck(
        "definition_first",
        3,
        "Definition-first sentences",
        (
            SubQuestion(
                "has_definition", "Are key terms defined with a clear 'X is …' style sentence?"
            ),
            SubQuestion("early", "Do those definitions appear early, not after long discussion?"),
        ),
    ),
    ContentCheck(
        "expert_commentary",
        4,
        "Expert quotes / original commentary",
        (
            SubQuestion(
                "original_analysis", "Does the page give original analysis beyond common knowledge?"
            ),
            SubQuestion(
                "expert_voice", "Does it include a named expert quote or first-hand insight?"
            ),
        ),
    ),
    ContentCheck(
        "original_data",
        4,
        "Original data / first-hand evidence",
        (
            SubQuestion(
                "first_hand",
                "Does the page show original data, first-hand testing, or a case study?",
            ),
            SubQuestion(
                "specific", "Are specific numbers/results tied to a described method or source?"
            ),
        ),
    ),
    ContentCheck(
        "external_citations",
        4,
        "Authoritative external citations",
        (
            SubQuestion(
                "cites_sources", "Does the page cite authoritative external sources for its claims?"
            ),
            SubQuestion(
                "credible", "Are those sources credible, not just internal/marketing links?"
            ),
        ),
    ),
)


# --- evidence enforcement + truth table (pure, unit-tested) ------------------


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().lower()


def evidence_supported(quote: str, source_text: str) -> bool:
    """True if ``quote`` appears in ``source_text`` (normalized substring, fuzzy floor).

    Used only to validate **affirmative** sub-answers — a ``yes`` must be backed by
    a span that exists, which is the anti-hallucination guard (§4.3). Absence
    answers (``no``/``unknown``) can't quote what isn't there, so they're exempt.
    """
    nq = _normalize(quote)
    if not nq:
        return False
    ns = _normalize(source_text)
    if nq in ns:
        return True
    return fuzz.partial_ratio(nq, ns) >= _EVIDENCE_FUZZ_FLOOR


def verdict_from_answers(answers: list[str]) -> ContentClass:
    """The rubric truth table: all-yes→pass, all-no→fail, mixed→partial, unknown→unknown."""
    if not answers:
        return ContentClass.UNKNOWN
    if "unknown" in answers:
        return ContentClass.UNKNOWN
    if all(a == "yes" for a in answers):
        return ContentClass.PASS
    if all(a == "no" for a in answers):
        return ContentClass.FAIL
    return ContentClass.PARTIAL


def finalize_check(
    check: ContentCheck, raw_answers: list[dict[str, Any]], source_text: str
) -> CheckVerdict:
    """Validate evidence, downgrade unsupported affirmatives, apply the truth table.

    ``raw_answers`` is the model's list aligned to ``check.sub_questions`` (each a
    dict with ``reasoning``/``evidence_quote``/``answer``). A missing or malformed
    entry becomes ``unknown``.
    """
    by_key = {str(a.get("key", "")): a for a in raw_answers if isinstance(a, dict)}
    sub_answers: list[SubAnswer] = []
    needs_review = False
    for sub_q in check.sub_questions:
        raw = by_key.get(sub_q.key, {})
        answer = str(raw.get("answer", "unknown")).lower().strip()
        if answer not in ("yes", "no", "unknown"):
            answer = "unknown"
        quote = str(raw.get("evidence_quote", ""))
        valid = True
        if answer == "yes":
            valid = evidence_supported(quote, source_text)
            if not valid:
                # Unsupported affirmative → don't trust it; abstain + flag.
                answer = "unknown"
                needs_review = True
        sub_answers.append(
            SubAnswer(
                key=sub_q.key,
                question=sub_q.text,
                reasoning=str(raw.get("reasoning", "")),
                evidence_quote=quote,
                answer=answer,
                evidence_valid=valid,
            )
        )

    classification = verdict_from_answers([s.answer for s in sub_answers])
    if classification is ContentClass.UNKNOWN:
        needs_review = True
    reason = _verdict_reason(check, sub_answers, classification)
    return CheckVerdict(
        check.check_id, check.category, classification, reason, sub_answers, needs_review
    )


def _verdict_reason(
    check: ContentCheck, sub_answers: list[SubAnswer], classification: ContentClass
) -> str:
    yes = sum(1 for s in sub_answers if s.answer == "yes")
    no = sum(1 for s in sub_answers if s.answer == "no")
    unknown = sum(1 for s in sub_answers if s.answer == "unknown")
    return (
        f"{check.title}: {classification.value} "
        f"({yes} yes / {no} no / {unknown} unknown of {len(sub_answers)} sub-checks)"
    )


# --- the judge (Anthropic forced tool call, mirrors judge.py) ----------------

_SYSTEM = (
    "You are a strict content evaluator for AI-answer optimization. You assess a "
    "single web page's main text against one rubric check, by calling the "
    "record_check tool. Answer each sub-question yes / no / unknown. For every "
    "'yes' you MUST copy a short verbatim quote from the page text that proves it; "
    "if you cannot quote it, answer 'no' or 'unknown'. Judge ONLY from the provided "
    "page text — never outside knowledge. Use 'unknown' when the text is "
    "insufficient to decide, not a guess."
)

_PROMPT = """Page URL: {url}

Rubric check: {title}

Answer each sub-question below. For each, give your reasoning first, then a
verbatim evidence quote copied from the page text (required for any 'yes'), then
the answer.

Sub-questions:
{questions}

Page text:
\"\"\"
{text}
\"\"\"
"""

# Cap the page text fed to the judge so a huge page can't blow the context / cost.
_MAX_TEXT_CHARS = 16000


def _check_tool(check: ContentCheck) -> ToolParam:
    """Forced-tool schema for one check — reasoning-first, answer enum last (§4.1)."""
    return {
        "name": "record_check",
        "description": f"Record the yes/no/unknown sub-answers for the '{check.title}' check.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sub_answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "enum": [q.key for q in check.sub_questions]},
                            "reasoning": {"type": "string"},
                            "evidence_quote": {"type": "string"},
                            "answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
                        },
                        "required": ["key", "reasoning", "evidence_quote", "answer"],
                    },
                }
            },
            "required": ["sub_answers"],
        },
    }


# --- content-address key ("the notebook" key; mirrors judge.py's cache identity) ---

# A hash of the content judge's own prompt + rubric version, so editing either
# changes every key and forces a re-judge (like judge.py's prompt fingerprint).
_CONTENT_PROMPT_FINGERPRINT = hashlib.sha256(
    (_SYSTEM + _PROMPT + CONTENT_RUBRIC_VERSION).encode("utf-8")
).hexdigest()

# Reasons judge_check emits on an API/parse FAILURE — a verdict carrying one is a
# non-assessment and must NOT be cached (else a transient failure poisons the notebook).
_UNCACHEABLE_REASONS = frozenset({"judge call failed", "no sub-answers returned"})


def _check_identity(check: ContentCheck) -> str:
    """The check's semantic definition, so editing its sub-questions changes the key."""
    return check.check_id + "\x1f" + "\x1f".join(f"{q.key}:{q.text}" for q in check.sub_questions)


def content_cache_key(model: str, check: ContentCheck, text: str) -> str:
    """Content-address for one (page-text, check) verdict — the notebook key. Keyed on
    the TRUNCATED text the judge actually sees, so identical inputs hit."""
    parts = [
        "content-v1",
        model,
        _CONTENT_PROMPT_FINGERPRINT,
        _check_identity(check),
        text[:_MAX_TEXT_CHARS],
    ]
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()


class ContentJudge:
    """LLM judge for the Cat 3/4 subjective checks (one forced tool call per check).

    Mirrors ``judge.py``: Anthropic client, temperature 0 (omitted for opus-4-8),
    and best-effort degrade — a check the model can't answer becomes ``unknown``
    rather than raising. Verdicts are cached in the content notebook (content-
    addressed by page text + check), so a repeated page/check is a free lookup.
    """

    def __init__(
        self,
        model: str | None = None,
        max_workers: int = 4,
        cache: ContentJudgeCache | None = None,
    ) -> None:
        from src.config import settings

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set; the content judge needs it.")
        self._model = model or settings.JUDGE_MODEL
        self._client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )
        self._max_workers = max_workers
        if cache is not None:
            self._cache: ContentJudgeCache = cache
        else:
            from src.audit.checks.content_judge_cache import make_content_judge_cache

            self._cache = make_content_judge_cache()

    def judge_check(self, check: ContentCheck, url: str, text: str) -> CheckVerdict:
        """Run one rubric check over the page text. Never raises (degrades to unknown)."""
        questions = "\n".join(f"- [{q.key}] {q.text}" for q in check.sub_questions)
        prompt = _PROMPT.format(
            url=url, title=check.title, questions=questions, text=text[:_MAX_TEXT_CHARS]
        )
        tool = _check_tool(check)
        try:
            temperature = anthropic.omit if "opus-4-8" in self._model else 0.0
            tool_choice: ToolChoiceToolParam = {"type": "tool", "name": "record_check"}
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_JUDGE_MAX_TOKENS,
                temperature=temperature,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool],
                tool_choice=tool_choice,
            )
            raw = _extract_tool_input(response)
        except Exception as exc:  # best-effort: any failure → an unknown verdict
            logger.warning(
                "content judge failed for %s/%s: %s", url, check.check_id, type(exc).__name__
            )
            return _unknown_verdict(check, "judge call failed")

        raw_answers = raw.get("sub_answers")
        if not isinstance(raw_answers, list):
            return _unknown_verdict(check, "no sub-answers returned")
        return finalize_check(check, raw_answers, text)

    def judge_page_text(self, url: str, text: str) -> ContentJudgeResult:
        """Run every rubric check over a page's main text. Checks already in the
        notebook are reused for free; only the misses hit the API (concurrently),
        and their (assessed) verdicts are written back in one batch."""
        if not text.strip():
            return ContentJudgeResult(
                page_url=url,
                verdicts=[_unknown_verdict(c, "no page text to judge") for c in CONTENT_CHECKS],
                assessed=False,
            )
        keys = {c.check_id: content_cache_key(self._model, c, text) for c in CONTENT_CHECKS}
        cached = self._cache.get_many(list(keys.values()))
        by_id: dict[str, CheckVerdict] = {}
        to_judge: list[ContentCheck] = []
        for check in CONTENT_CHECKS:
            hit = cached.get(keys[check.check_id])
            if hit is not None:
                by_id[check.check_id] = hit
            else:
                to_judge.append(check)
        if to_judge:
            with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                fresh = list(pool.map(lambda c: (c, self.judge_check(c, url, text)), to_judge))
            store: list[tuple[str, CheckVerdict]] = []
            for check, verdict in fresh:
                by_id[check.check_id] = verdict
                if verdict.reason not in _UNCACHEABLE_REASONS:  # never cache a failure
                    store.append((keys[check.check_id], verdict))
            if store:
                self._cache.put_many(store)
        verdicts = [by_id[c.check_id] for c in CONTENT_CHECKS]
        return ContentJudgeResult(page_url=url, verdicts=verdicts, assessed=True)

    def judge_page(self, page: PageRecord) -> ContentJudgeResult:
        return self.judge_page_text(page.url, page.extracted_text or "")


def _extract_tool_input(response: Message) -> dict[str, Any]:
    for block in response.content:
        if block.type == "tool_use" and isinstance(block.input, dict):
            return block.input
    raise ValueError("content judge response contained no record_check tool call")


def _unknown_verdict(check: ContentCheck, reason: str) -> CheckVerdict:
    subs = [SubAnswer(q.key, q.text, "", "", "unknown", True) for q in check.sub_questions]
    return CheckVerdict(check.check_id, check.category, ContentClass.UNKNOWN, reason, subs, True)
