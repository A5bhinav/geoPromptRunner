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

    questions.py   the registry — what can be asked
    plan.py        registry + prefill + branch — what will be asked
    assertions.py  an answer → the exact sentence the owner is quoted on
    claims.py      that sentence → a FactClaim, plus the run inputs that aren't

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
    run_inputs_from_answers,
    sections_present,
    upgrade_confirmed,
)
from src.audit.factsheet.intake.plan import branch_for, build_plan
from src.audit.factsheet.intake.questions import (
    BY_ID,
    MAX_CARDS,
    REGISTRY,
    AnswerKind,
    IntakeQuestion,
    Option,
    question,
)

__all__ = [
    "Answer",
    "Assertion",
    "AnswerKind",
    "IntakeQuestion",
    "Option",
    "REGISTRY",
    "BY_ID",
    "MAX_CARDS",
    "question",
    "build_plan",
    "branch_for",
    "assertions_for",
    "to_assertion",
    "unfalsifiable_terms",
    "RunInputs",
    "claims_from_answers",
    "run_inputs_from_answers",
    "sections_present",
    "upgrade_confirmed",
]
