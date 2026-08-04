"""P4-T4's generator, and the adversarial test the spec calls the point of it.

"An adversarial test where the generator emits a number absent from the source
data → the post-check rejects it. This test is the point of the task; do not
weaken it."

The generator is a `GenerateFn` — prompt in, text out — so every test here drives
a hostile one. No model is called, and none should ever be: what is under test is
whether a fabricated number can reach a client, not whether a model behaves.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from src.pipeline.narrative import Fact, Sentence, verify
from src.pipeline.narrative_generator import (
    build_prompt,
    facts_from_report,
    generate_narrative,
    parse_sentences,
)

FACTS = facts_from_report(
    mention_successes=7, mention_n=12, open_themes=3, critical=1, delta_pp=-8.0
)


def _emits(*sentences: tuple[str, list[str]]) -> object:
    def _generate(_prompt: str) -> str:
        return json.dumps(
            {"sentences": [{"text": text, "fact_ids": ids} for text, ids in sentences]}
        )

    return _generate


# --- the adversarial test -----------------------------------------------------


def test_a_fabricated_number_never_reaches_the_client() -> None:
    """The whole task, in one assertion.

    41 is not in the fact list. The model cites a real fact beside it — which is
    exactly the failure self-reported citations cannot catch — and the
    deterministic post-check catches it anyway.
    """
    result = generate_narrative(
        FACTS,
        generate=_emits(("41 of 12 answers name the client.", ["F1", "F2"])),  # type: ignore[arg-type]
        enabled=True,
    )
    assert result.source == "fallback"
    assert "41" not in result.text
    assert result.failures, "the rejection must say what was wrong"


@pytest.mark.parametrize(
    "text",
    [
        "The client appears in 9 of 12 answers.",  # wrong numerator
        "The client appears in 58 of 20 answers.",  # wrong denominator
        "Visibility is 91%.",  # a rate no fact carries
        "Mention rate fell 23 percentage points.",  # a delta no fact carries
        "There are 3 findings across 5 surfaces.",  # a smuggled second number
    ],
)
def test_every_shape_of_invented_number_is_rejected(text: str) -> None:
    result = generate_narrative(
        FACTS,
        generate=_emits((text, ["F1", "F2", "F3", "F5", "F6"])),  # type: ignore[arg-type]
        enabled=True,
    )
    assert result.source == "fallback", f"{text!r} was accepted"


def test_a_reversed_direction_is_rejected_even_with_the_right_number() -> None:
    """"rose 8 points" beside a −8 fact contains no wrong number at all — which is
    why the numeric check alone cannot catch it."""
    result = generate_narrative(
        FACTS,
        generate=_emits(("Mention rate rose 8 percentage points.", ["F5"])),  # type: ignore[arg-type]
        enabled=True,
    )
    assert result.source == "fallback"


def test_an_invented_severity_is_rejected() -> None:
    """The model may not characterise severity beyond what a fact's label says."""
    result = generate_narrative(
        FACTS,
        generate=_emits(("Visibility is low this cycle.", ["F1"])),  # type: ignore[arg-type]
        enabled=True,
    )
    assert result.source == "fallback"


def test_unparseable_output_falls_back_rather_than_shipping() -> None:
    result = generate_narrative(
        FACTS,
        generate=lambda _p: "I'm sorry, I can't help with that.",
        enabled=True,
    )
    assert result.source == "fallback"


def test_a_raising_generator_still_produces_a_report() -> None:
    """Every model call in this codebase degrades rather than raising. A report
    must render whether or not a model answered."""

    def _explode(_prompt: str) -> str:
        raise RuntimeError("upstream 500")

    result = generate_narrative(FACTS, generate=_explode, enabled=True)
    assert result.source == "fallback"
    assert result.text


# --- honest prose is not collateral damage ------------------------------------


def test_honest_prose_in_the_house_format_is_accepted() -> None:
    """A guard that rejects "7 of 12" would force the generator into a format the
    packaging rules forbid — the count-first phrasing is the house style."""
    result = generate_narrative(
        FACTS,
        generate=_emits(  # type: ignore[arg-type]
            ("7 of 12 measured answers name the client.", ["F1", "F2", "F6"]),
            ("That is 8 percentage points lower than last cycle.", ["F5"]),
        ),
        enabled=True,
    )
    assert result.source == "generated"
    assert result.verified
    assert result.attempts == 1


def test_direction_words_are_not_mistaken_for_severity_words() -> None:
    """Substring matching rejected correct prose: "lower" contains "low",
    "higher" contains "high", "the following" contains "low" too.

    Narrowing to word boundaries is not a weakening — "low" standing alone still
    fails, which is the case the rule exists to catch.
    """
    facts = [Fact("F1", "change in mention rate", Decimal("-8"), "pct_delta")]
    ok = verify([Sentence("The rate is 8 percentage points lower.", ("F1",))], facts)
    assert ok.ok, ok.reasons()

    still_caught = verify([Sentence("Visibility is low.", ("F1",))], facts)
    assert not still_caught.ok


def test_the_retry_feeds_the_failures_back() -> None:
    """A second attempt with no new information is a reroll of the same dice."""
    prompts: list[str] = []

    def _generate(prompt: str) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return json.dumps(
                {"sentences": [{"text": "There are 99 findings.", "fact_ids": ["F3"]}]}
            )
        return json.dumps(
            {"sentences": [{"text": "There are 3 open findings.", "fact_ids": ["F3"]}]}
        )

    result = generate_narrative(FACTS, generate=_generate, enabled=True)
    assert result.source == "generated"
    assert result.attempts == 2
    assert "REJECTED" in prompts[1]
    assert "99" in prompts[1], "the retry must name the specific rejected claim"


# --- what the model is allowed to see -----------------------------------------


def test_the_prompt_carries_only_enumerated_facts() -> None:
    """The model never sees raw findings, raw answers, or the fact sheet.

    That is what turns unconstrained factual recall — where recall errors are the
    dominant hallucination mode — into closed-set selection over a handful of
    numbers.
    """
    prompt = build_prompt(FACTS)
    for fact in FACTS:
        assert fact.id in prompt
    for leak in ("fact sheet", "verbatim", "raw answer", "$349"):
        assert leak not in prompt.lower()


def test_the_prompt_states_the_pp_rule() -> None:
    assert "percentage points" in build_prompt(FACTS)


# --- the default path ---------------------------------------------------------


def test_generation_is_off_by_default_and_the_fallback_is_correct() -> None:
    """A report is meant to be free to re-render. Generation is an optimisation on
    top of something that already works — the only footing on which an LLM
    belongs in this layer at all."""

    def _never_called(_prompt: str) -> str:  # pragma: no cover - must not run
        raise AssertionError("generation ran while disabled")

    result = generate_narrative(FACTS, generate=_never_called, enabled=False)
    assert result.source == "fallback"
    assert result.verified
    assert "7" in result.text and "12" in result.text


def test_the_fallback_states_every_fact_it_was_given() -> None:
    """Never silently drop the failing claim — that is data loss wearing a
    success. The wooden sentence says the same true things."""
    result = generate_narrative(FACTS, generate=lambda _p: "{}", enabled=True)
    for fact in FACTS:
        assert fact.label.split()[0] in result.text


def test_severe_findings_are_marked_for_sign_off() -> None:
    result = generate_narrative(FACTS, has_severe_finding=True, enabled=False)
    assert result.requires_signoff is True


def test_parse_sentences_survives_a_fenced_block() -> None:
    fenced = '```json\n{"sentences": [{"text": "3 findings.", "fact_ids": ["F3"]}]}\n```'
    assert parse_sentences(fenced) == [Sentence("3 findings.", ("F3",))]
