"""Generated prose that cannot state a number the data does not contain (P4-T4).

Writing the summary by hand does not scale past a handful of clients. A naive LLM
summary pass introduces a **second hallucination surface — in a product whose
entire pitch is catching hallucinations**, which is the single worst failure mode
available here.

So the guarantee does NOT come from the generation step. Forced tool calls and
structured outputs guarantee the JSON parses and matches types; they do not
guarantee ``"delta": "23%"`` is real. Constrained decoding is not available on
hosted Anthropic/OpenAI anyway, and there is measured evidence it degrades
reasoning quality.

**The guarantee comes from a deterministic verifier**, and this module is that
verifier. Two independent checks per sentence:

1. every cited ``fact_id`` exists;
2. **every number extracted from the raw text** matches a cited fact — by regex,
   never by trusting the model's own citation list. That catches the model citing
   F1 while writing a different, fabricated number, which self-reported citations
   cannot.

**Unit normalization is the hard part.** "6 of 12", "50%" and "half" must all
reduce to the same value, and spans must be CONSUMED in order or "6 of 12" is
double-counted as the separate claims "6" and "12".

The generation step is not implemented here and is not needed for the guard to be
useful: :func:`verify` is what makes any generator safe to switch on, and
:func:`fallback_narrative` is what runs until one exists. Nothing in this module
calls a model.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

__all__ = [
    "Fact",
    "Sentence",
    "ExtractedClaim",
    "VerificationFailure",
    "VerificationResult",
    "extract_numeric_claims",
    "verify",
    "fallback_narrative",
]

#: How far a stated number may sit from the cited fact and still pass.
#:
#: Rounding is legitimate — "58%" for 7/12 (58.33%) must not fail. Anything wider
#: starts letting a wrong number through, so this is deliberately tight and is
#: expressed in the same units as the canonical value (percentage points for
#: rates, absolute for counts).
TOLERANCE = Decimal("0.6")


@dataclass(frozen=True)
class Fact:
    """One already-validated number the prose is allowed to mention.

    The model never sees raw findings or the fact sheet — only this list. That
    converts unconstrained factual recall, where recall errors are the dominant
    hallucination mode, into closed-set selection over a tiny enumerated set.
    """

    id: str  # "F1"
    label: str  # "open_findings"
    value: Decimal
    kind: str  # count | pct | pct_delta


@dataclass(frozen=True)
class Sentence:
    """One generated sentence and the facts it claims to rest on."""

    text: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedClaim:
    """A number found in the prose, normalized to a comparable value."""

    raw: str
    value: Decimal
    kind: str


@dataclass(frozen=True)
class VerificationFailure:
    sentence: str
    reason: str


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    failures: list[VerificationFailure] = field(default_factory=list)

    def reasons(self) -> str:
        return "; ".join(f.reason for f in self.failures)


# Order matters and the spans are CONSUMED. Ratio first, or "6 of 12" is read as
# the two bare numbers 6 and 12 — one of which will match some unrelated fact and
# quietly validate a fabricated sentence.
_RATIO_RE = re.compile(r"\b(\d+)\s+of\s+(\d+)\b", re.IGNORECASE)
_PP_DELTA_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(?:percentage\s*points?|pts?\b|pp\b)", re.IGNORECASE
)
_PCT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_WORD_RE = re.compile(r"\b(half|a\s+third|two\s+thirds|a\s+quarter|three\s+quarters)\b", re.I)
_PLAIN_NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")

_WORD_VALUES: dict[str, Decimal] = {
    "half": Decimal(50),
    "a third": Decimal("33.33"),
    "two thirds": Decimal("66.67"),
    "a quarter": Decimal(25),
    "three quarters": Decimal(75),
}


def extract_numeric_claims(text: str) -> list[ExtractedClaim]:
    """Every quantitative claim in a sentence, normalized. Pure.

    Spans are consumed as they match, which is the whole reason the passes run in
    this order. Percentages, ratios and "half" all normalize onto the same 0–100
    scale so a sentence may state a rate however it likes and still be checked
    against one fact.
    """
    claims: list[ExtractedClaim] = []
    consumed: list[tuple[int, int]] = []

    def free(span: tuple[int, int]) -> bool:
        return not any(start < span[1] and span[0] < end for start, end in consumed)

    for match in _RATIO_RE.finditer(text):
        numerator, denominator = int(match.group(1)), int(match.group(2))
        if denominator:
            value = (Decimal(numerator) / Decimal(denominator) * 100).quantize(Decimal("0.01"))
            claims.append(ExtractedClaim(match.group(0), value, "pct"))
            # The COUNT is a claim too — "7 of 12" asserts both a rate and a
            # numerator, and a sentence that gets the count wrong is wrong.
            claims.append(ExtractedClaim(match.group(1), Decimal(numerator), "count"))
            claims.append(ExtractedClaim(match.group(2), Decimal(denominator), "count"))
        consumed.append(match.span())

    for match in _PP_DELTA_RE.finditer(text):
        if free(match.span()):
            claims.append(ExtractedClaim(match.group(0), Decimal(match.group(1)), "pct_delta"))
            consumed.append(match.span())

    for match in _PCT_RE.finditer(text):
        if free(match.span()):
            claims.append(ExtractedClaim(match.group(0), Decimal(match.group(1)), "pct"))
            consumed.append(match.span())

    for match in _WORD_RE.finditer(text):
        if free(match.span()):
            key = " ".join(match.group(1).lower().split())
            claims.append(ExtractedClaim(match.group(0), _WORD_VALUES[key], "pct"))
            consumed.append(match.span())

    for match in _PLAIN_NUM_RE.finditer(text):
        if free(match.span()):
            claims.append(ExtractedClaim(match.group(0), Decimal(match.group(0)), "count"))
            consumed.append(match.span())

    return claims


#: Severity words the prose may use only if a cited fact carries them.
_ENUM_TERMS = ("critical", "high", "medium", "low", "regressed", "resolved")


def verify(sentences: Sequence[Sentence], facts: Sequence[Fact]) -> VerificationResult:
    """The actual guarantee. Deterministic; no model involved.

    A sentence passes only if every fact id it cites exists AND every number in
    its text matches one of those cited facts. Numbers are extracted from the raw
    string rather than taken from the citation list, because the failure being
    guarded against is precisely a model that cites a real fact and writes a
    different number beside it.
    """
    by_id = {fact.id: fact for fact in facts}
    failures: list[VerificationFailure] = []

    for sentence in sentences:
        unknown = [fid for fid in sentence.fact_ids if fid not in by_id]
        if unknown:
            failures.append(
                VerificationFailure(
                    sentence.text, f"cites unknown fact id(s): {', '.join(unknown)}"
                )
            )
            continue

        cited = [by_id[fid] for fid in sentence.fact_ids]
        for claim in extract_numeric_claims(sentence.text):
            if not any(_matches(claim, fact) for fact in cited):
                failures.append(
                    VerificationFailure(
                        sentence.text,
                        f"states {claim.raw!r} which matches no cited fact "
                        f"({', '.join(f'{f.id}={f.value}' for f in cited) or 'none cited'})",
                    )
                )

        direction_problem = _direction_ok(sentence.text, cited)
        if direction_problem:
            failures.append(VerificationFailure(sentence.text, direction_problem))

        lowered = sentence.text.lower()
        cited_words = " ".join(str(f.label).lower() + " " + str(f.value).lower() for f in cited)
        for term in _ENUM_TERMS:
            if term in lowered and term not in cited_words:
                failures.append(
                    VerificationFailure(
                        sentence.text,
                        f"uses the term {term!r} with no cited fact carrying it",
                    )
                )

    return VerificationResult(ok=not failures, failures=failures)


def _matches(claim: ExtractedClaim, fact: Fact) -> bool:
    """Whether a stated number is the cited fact, allowing for rounding.

    Kinds must agree loosely: a count may back a count, a rate may back a rate or
    a pp-delta. A count of 12 must never satisfy a claim of "12%" — the two are
    different assertions that happen to share a digit.

    **Deltas match on MAGNITUDE.** Natural prose puts the sign in the verb — "fell
    8 percentage points" against a fact of −8 — so comparing signed values would
    reject correct writing. Direction is checked separately and properly by
    :func:`_direction_ok`, which also catches the reversal a signed comparison
    would miss entirely: "rose 8 points" beside a −8 fact.
    """
    compatible = {
        "count": {"count"},
        "pct": {"pct", "pct_delta"},
        "pct_delta": {"pct", "pct_delta"},
    }
    if fact.kind not in compatible.get(claim.kind, set()):
        return False
    if fact.kind == "pct_delta" or claim.kind == "pct_delta":
        return abs(abs(claim.value) - abs(fact.value)) <= TOLERANCE
    return abs(claim.value - fact.value) <= TOLERANCE


#: Direction words. A delta sentence must agree with its fact's sign, and this is
#: the check a signed-number comparison cannot do — regex sees "8" either way.
_ROSE = re.compile(r"\b(rose|up|increased|grew|improved|gained|climbed|higher)\b", re.I)
_FELL = re.compile(r"\b(fell|down|decreased|dropped|declined|lost|slipped|lower)\b", re.I)


def _direction_ok(text: str, facts: Sequence[Fact]) -> str:
    """"" if the prose's direction agrees with every signed delta it cites.

    Qualitative overclaiming and direction reversal are what the numeric check
    cannot see: "improved" beside a −8 fact contains no wrong number at all.
    """
    deltas = [f for f in facts if f.kind == "pct_delta" and f.value != 0]
    if not deltas:
        return ""
    rose, fell = bool(_ROSE.search(text)), bool(_FELL.search(text))
    if rose == fell:  # both or neither — no direction asserted, nothing to check
        return ""
    stated_up = rose
    for fact in deltas:
        if (fact.value > 0) != stated_up:
            return (
                f"describes the change as {'a rise' if stated_up else 'a fall'} "
                f"while {fact.id} is {fact.value:+}"
            )
    return ""


def fallback_narrative(facts: Sequence[Fact]) -> str:
    """A wooden but provably-correct sentence built by f-string from the facts.

    The policy when verification fails, in order: retry once with the specific
    failures fed back, regenerating only the failing sentences; then fall back to
    this; **never silently drop the failing claim**, which is data loss wearing a
    success. Track the fallback rate as a pipeline health metric.

    Wooden and 100% correct is strictly better for a product whose pitch is "no
    invented facts".
    """
    if not facts:
        return "No summary is available for this cycle."
    parts = [f"{fact.label.replace('_', ' ')}: {_render(fact)}" for fact in facts]
    return "This cycle — " + "; ".join(parts) + "."


def _render(fact: Fact) -> str:
    if fact.kind == "pct":
        return f"{fact.value:.0f}%"
    if fact.kind == "pct_delta":
        return f"{fact.value:+.0f} percentage points"
    return f"{fact.value:.0f}"


if __name__ == "__main__":
    facts = [
        Fact("F1", "open_findings", Decimal(12), "count"),
        Fact("F2", "critical", Decimal(3), "count"),
        Fact("F3", "mention_delta_pp", Decimal(-8), "pct_delta"),
    ]
    good = [
        Sentence("This cycle surfaced 12 findings, 3 of them critical.", ("F1", "F2")),
        Sentence("Mention rate fell 8 percentage points.", ("F3",)),
    ]
    bad = [Sentence("This cycle surfaced 47 findings.", ("F1",))]
    print("honest prose  ->", verify(good, facts).ok)
    result = verify(bad, facts)
    print("invented number ->", result.ok, "|", result.reasons())
    print("fallback:", fallback_narrative(facts))
