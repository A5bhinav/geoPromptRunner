"""The generator half of P4-T4 — and the reason it was built second.

`narrative.verify()` came first deliberately: **the guard is what makes any
generator safe to switch on.** Forced tool calls and structured outputs guarantee
the JSON parses; they do not guarantee ``"12 findings"`` is a number this run
produced. So the trust in this module comes from nothing it does — it comes from
every sentence it emits being re-checked, by regex, against an enumerated fact
list before anything reaches a client.

Four constraints, all load-bearing:

1. **The model never sees raw findings, raw answers, or the fact sheet.** It sees
   a list of `Fact` rows — an id, a label, a value. That turns unconstrained
   factual recall, where recall errors are the dominant hallucination mode, into
   closed-set selection over a handful of enumerated numbers.
2. **It fills a fixed skeleton.** It may not invent a finding, re-interpret a
   severity, or add a sentence the skeleton did not ask for.
3. **Every sentence is verified.** On failure: one retry with the specific
   failures fed back, then the wooden fallback. **Never silently drop the failing
   claim** — that is data loss wearing a success.
4. **Critical/High narrative needs human sign-off.** This module marks it; it
   does not decide it has been given.

Nothing here runs unless ``RUN_NARRATIVE`` is on, and the fallback path calls no
model at all.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from src.config import settings
from src.pipeline.narrative import (
    Fact,
    Sentence,
    VerificationResult,
    fallback_narrative,
    verify,
)

__all__ = [
    "NarrativeResult",
    "GenerateFn",
    "build_prompt",
    "parse_sentences",
    "generate_narrative",
    "facts_from_report",
]

logger = logging.getLogger(__name__)

#: A generation function: prompt in, raw model text out. Injected so the whole
#: module is testable without a network call, and so the adversarial test can
#: hand it a generator that fabricates a number.
GenerateFn = Callable[[str], str]

#: How many times a failed verification is retried, with the failures fed back.
#: One. A model that invented a number once and was told exactly which one will
#: either fix it or keep inventing; a third attempt is spend without information.
MAX_RETRIES = 1


@dataclass(frozen=True)
class NarrativeResult:
    """What the report gets, and how much to trust it."""

    text: str
    #: "generated" | "fallback". A pipeline health metric, not decoration: a
    #: rising fallback rate is the signal that the skeleton or the model drifted,
    #: and it is invisible if the fallback is silent.
    source: str
    verified: bool
    attempts: int
    failures: list[str] = field(default_factory=list)
    #: True when the narrative touches a Critical or High finding. The report
    #: renders it as a draft until a human signs off — this module records the
    #: requirement, it cannot record that the requirement was met.
    requires_signoff: bool = False


_SKELETON = """You are writing two sentences of a client's AI-visibility report.

RULES — every one of them is checked automatically after you answer:
- You may ONLY state numbers that appear in the FACTS list below. No other number
  may appear in your text, not even a rounded or re-expressed one.
- You may not invent a finding, name a competitor, or characterise severity
  beyond what a fact's label already says.
- Write flat, factual, third person. The engine "states" or "describes"; it does
  not "lie", "hallucinate" or "falsely claim".
- Do not recommend anything. This is the measurement section, not the plan.
- A change in a rate is stated in percentage points ("6 percentage points"),
  never as a percent change.

FACTS (the only numbers you may use):
{facts}

SKELETON — write exactly these sentences, in this order:
1. What the measurement found this cycle.
2. What changed since the previous cycle, or that nothing did.

Answer with JSON only, no prose around it:
{{"sentences": [{{"text": "...", "fact_ids": ["F1"]}}, ...]}}
"""


def _render_fact(fact: Fact) -> str:
    if fact.kind == "pct":
        return f"{fact.value:.0f}%"
    if fact.kind == "pct_delta":
        return f"{fact.value:+.0f} percentage points"
    return f"{fact.value:.0f}"


def build_prompt(facts: Sequence[Fact], failures: Sequence[str] = ()) -> str:
    """The skeleton, filled with the enumerated facts.

    ``failures`` is the retry path: the specific rejected claims, quoted back, so
    the second attempt has information the first did not rather than being a
    reroll of the same dice.
    """
    lines = [
        f"{f.id} — {f.label.replace('_', ' ')}: {_render_fact(f)}" for f in facts
    ]
    prompt = _SKELETON.format(facts="\n".join(lines) or "(none)")
    if failures:
        prompt += (
            "\nYOUR PREVIOUS ATTEMPT WAS REJECTED. Every number below was not in "
            "the FACTS list:\n"
            + "\n".join(f"- {reason}" for reason in failures)
            + "\nRewrite using ONLY the facts above.\n"
        )
    return prompt


def parse_sentences(raw: str) -> list[Sentence]:
    """Model text → sentences. Returns ``[]`` on anything unparseable.

    An empty list fails verification and falls back, which is the correct
    handling: a generator that returned something we cannot read is a generator
    whose output we cannot check.
    """
    text = raw.strip()
    # Models fence JSON even when told not to.
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        data = json.loads(text)
        return [
            Sentence(
                text=str(s["text"]),
                fact_ids=tuple(str(i) for i in s.get("fact_ids", [])),
            )
            for s in data["sentences"]
        ]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        logger.warning("narrative generation returned unparseable output")
        return []


def _anthropic_generate(prompt: str) -> str:
    """The real generator. Imported lazily so the module has no hard SDK
    dependency on a path that may never call a model."""
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.NARRATIVE_MODEL,
        max_tokens=600,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )
    block = response.content[0]
    return block.text if hasattr(block, "text") else ""


def generate_narrative(
    facts: Sequence[Fact],
    *,
    generate: GenerateFn | None = None,
    has_severe_finding: bool = False,
    enabled: bool | None = None,
) -> NarrativeResult:
    """Generate, verify, retry once, then fall back. Never emits unverified prose.

    The fallback is not an error path — it is the DEFAULT path, and it produces
    correct prose. Generation is an optimisation on top of something that already
    works, which is the only footing on which an LLM belongs in this layer at
    all.
    """
    on = settings.RUN_NARRATIVE if enabled is None else enabled
    if not on or not facts:
        return NarrativeResult(
            text=fallback_narrative(facts),
            source="fallback",
            verified=True,  # built by f-string FROM the facts; it cannot disagree
            attempts=0,
            requires_signoff=has_severe_finding,
        )

    generator = generate or _anthropic_generate
    failures: list[str] = []
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            raw = generator(build_prompt(facts, failures))
        except Exception as exc:
            # Every engine and model call in this codebase degrades rather than
            # raising; the report must render whether or not a model answered.
            logger.warning("narrative generation failed: %s", type(exc).__name__)
            break

        sentences = parse_sentences(raw)
        result: VerificationResult = verify(sentences, facts)
        if result.ok and sentences:
            return NarrativeResult(
                text=" ".join(s.text for s in sentences),
                source="generated",
                verified=True,
                attempts=attempt,
                requires_signoff=has_severe_finding,
            )
        failures = [f.reason for f in result.failures] or ["the output could not be parsed"]
        logger.warning("narrative attempt %d rejected: %s", attempt, "; ".join(failures))

    # NEVER the failing claim with the number stripped out. Dropping it would be
    # data loss wearing a success; the wooden sentence says the same true things.
    return NarrativeResult(
        text=fallback_narrative(facts),
        source="fallback",
        verified=True,
        attempts=MAX_RETRIES + 1,
        failures=failures,
        requires_signoff=has_severe_finding,
    )


def facts_from_report(
    *,
    mention_successes: int,
    mention_n: int,
    open_themes: int,
    critical: int,
    delta_pp: float | None,
) -> list[Fact]:
    """The enumerated fact list, from figures the report already computed.

    Deliberately tiny. Every fact here is one the report renders elsewhere, so a
    narrative claim can be checked against the page it sits on — and a fact the
    model cannot see is a number it cannot invent a context for.
    """
    facts = [
        Fact("F1", "answers naming the client", Decimal(mention_successes), "count"),
        Fact("F2", "answers measured", Decimal(mention_n), "count"),
        Fact("F3", "open findings", Decimal(open_themes), "count"),
        Fact("F4", "critical findings", Decimal(critical), "count"),
    ]
    # The RATE, as its own fact. Without it the house phrasing "7 of 12" fails
    # verification: the extractor reads a ratio as an assertion about a rate as
    # well as about two counts, and it is right to — "7 of 12" does claim 58%.
    if mention_n:
        facts.append(
            Fact(
                "F6",
                "share of answers naming the client",
                (Decimal(mention_successes) / Decimal(mention_n) * 100).quantize(Decimal("0.01")),
                "pct",
            )
        )
    if delta_pp is not None:
        facts.append(
            Fact("F5", "change in mention rate", Decimal(str(round(delta_pp, 1))), "pct_delta")
        )
    return facts


if __name__ == "__main__":
    facts = facts_from_report(
        mention_successes=7, mention_n=12, open_themes=3, critical=1, delta_pp=-8.0
    )

    def _honest(_prompt: str) -> str:
        return json.dumps(
            {
                "sentences": [
                    {
                        "text": "7 of 12 measured answers name the client.",
                        "fact_ids": ["F1", "F2", "F6"],
                    },
                    {
                        "text": "That is 8 percentage points lower than last cycle.",
                        "fact_ids": ["F5"],
                    },
                ]
            }
        )

    def _fabricating(_prompt: str) -> str:
        return json.dumps(
            {"sentences": [{"text": "41 of 12 answers name the client.", "fact_ids": ["F1"]}]}
        )

    print("honest     ->", generate_narrative(facts, generate=_honest, enabled=True))
    print("fabricated ->", generate_narrative(facts, generate=_fabricating, enabled=True))
