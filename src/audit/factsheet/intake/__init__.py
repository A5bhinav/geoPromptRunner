"""Fact-sheet intake: a conversation that ends in a client-confirmed sheet.

Why this package exists, in one paragraph. ``FactSheet.verification_tier`` is the
weakest verification across a sheet's claims, and a ``public_source_only`` sheet
may only carry LOW and MEDIUM accuracy findings. Every auto-generated sheet is
permanently ``public_source_only`` — ``resolve_conflicts`` refuses to upgrade on
agreement, and no other writer exists — so HIGH and CRITICAL findings, which are
exactly the class the product sells ("ChatGPT is quoting your old phone number"),
are structurally unreachable. This package is the only thing in the system that
can set ``Verification.CLIENT_CONFIRMED``.

Layout mirrors the data's path through it:

    questions.py   the registry — the sixteen cards asked of every business
    plan.py        the ordered plan for one session
    assertions.py  an answer → the exact sentence the owner is quoted on
    claims.py      that sentence → a FactClaim, plus the run inputs that aren't
    prefill.py     a crawl's claims → a draft answer, so a card is a confirm

Every module here is INERT in the same sense the extractor is: no fetching, no
clock, no model. ``as_of`` is a parameter. That is what lets the API and the UI
land independently, and what makes the whole package testable for nothing.
"""

from __future__ import annotations

from src.audit.factsheet.intake.assertions import (
    Answer,
    Assertion,
    assertions_for,
    to_assertion,
    unfalsifiable_terms,
)
from src.audit.factsheet.intake.claims import (
    RunInputs,
    claims_from_answers,
    derive_trade,
    run_inputs_from_answers,
    sections_present,
    upgrade_confirmed,
)
from src.audit.factsheet.intake.plan import build_plan
from src.audit.factsheet.intake.prefill import (
    PREFILLED_QUESTIONS,
    has_prefill,
    prefill_answer,
    prefilled_keys,
)
from src.audit.factsheet.intake.questions import (
    BY_ID,
    MAX_CARDS,
    REGISTRY,
    AnswerKind,
    Examples,
    IntakeQuestion,
    Option,
    Part,
    PartKind,
    question,
)

__all__ = [
    "Answer",
    "Assertion",
    "AnswerKind",
    "Examples",
    "IntakeQuestion",
    "Option",
    "Part",
    "PartKind",
    "REGISTRY",
    "BY_ID",
    "MAX_CARDS",
    "question",
    "build_plan",
    "PREFILLED_QUESTIONS",
    "prefill_answer",
    "has_prefill",
    "prefilled_keys",
    "assertions_for",
    "to_assertion",
    "unfalsifiable_terms",
    "RunInputs",
    "derive_trade",
    "claims_from_answers",
    "run_inputs_from_answers",
    "sections_present",
    "upgrade_confirmed",
]
