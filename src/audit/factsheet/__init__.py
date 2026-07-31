"""Fact sheets: the typed ground truth the accuracy judge measures answers against.

`docs/factsheet-autogen-plan.md` F0 and F1. Three modules with unrelated reasons
to change: the contract (:mod:`.models`) moves when the judge's inputs move, the
renderers (:mod:`.render`) move when a template does, and the deterministic
extraction (:mod:`.extract`) moves when a source format does.

F0 — the contract and the renderers — is deliberately inert: no fetching, no
clock, no model. That is what lets the teaser's CSV emitter (F2) and the review
screen (F4) depend on the type before any generation exists.

F1 — :func:`build_sheet` and the layers under it — is L0 (the lead form) plus L1
(JSON-LD, then ``tel:``/NAP prose where a page carried no markup). It calls no
model and none may be added; the cited-LLM layer (L2) and the off-site layer
(L3) land later as F6 and F7. Everything it emits passes the §4.1 quote gate,
so a claim whose verbatim quote is not a literal substring of its source is
dropped rather than shipped.
"""

from __future__ import annotations

from src.audit.factsheet.extract import (
    LEAD_FORM_SOURCE_URL,
    MIN_EXTRACTION_TEXT_CHARS,
    ThinTextError,
    build_sheet,
    claims_from_html,
    claims_from_json_ld,
    claims_from_lead_form,
    derive_negative_claims,
    resolve_conflicts,
    verify_quotes,
)
from src.audit.factsheet.gate import (
    SENDABLE_SEVERITIES,
    may_send_flag,
    sendable_flags,
)
from src.audit.factsheet.models import (
    BusinessKind,
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SheetStatus,
    SourceKind,
    Verification,
    assigned_claims,
)
from src.audit.factsheet.render import (
    FACT_CSV_HEADER,
    expected_fact_sheet_text,
    to_csv,
    to_fact_rows,
    to_markdown,
)

__all__ = [
    "SheetSection",
    "Polarity",
    "SourceKind",
    "Verification",
    "Confidence",
    "SheetStatus",
    "BusinessKind",
    "FactClaim",
    "FactSheet",
    "assigned_claims",
    "FACT_CSV_HEADER",
    "to_fact_rows",
    "to_csv",
    "to_markdown",
    "expected_fact_sheet_text",
    "build_sheet",
    "claims_from_lead_form",
    "claims_from_json_ld",
    "claims_from_html",
    "derive_negative_claims",
    "verify_quotes",
    "resolve_conflicts",
    "ThinTextError",
    "MIN_EXTRACTION_TEXT_CHARS",
    "LEAD_FORM_SOURCE_URL",
    "SENDABLE_SEVERITIES",
    "may_send_flag",
    "sendable_flags",
]
