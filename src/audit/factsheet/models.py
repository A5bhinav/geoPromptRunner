"""The fact-sheet contract: one claim structure, two renderers read it.

`docs/factsheet-autogen-plan.md` §2. A fact sheet is the reference the judge
measures answers against, so a wrong line here does not produce a missing
finding — it produces a false accusation in a document we send a stranger. That
asymmetry is why every claim carries its own quote, source and verification
tier, and why the validation below refuses rather than repairs.

Nothing in this module fetches, extracts or infers. It is the type F1's
deterministic extraction, F2's CSV emitter and F4's review screen all agree on;
keeping it inert is what lets those land independently.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

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
]


class SheetSection(StrEnum):
    """Which part of the sheet a claim belongs to.

    Declaration order is the render order and the claim-ID order (see
    :func:`assigned_claims`), and it follows the §A–§G layout of
    ``docs/fact-sheet-template-local.md``. Reordering these members renumbers
    every sheet, which re-keys every cached verdict (plan §6) — so don't.
    """

    IDENTITY = "identity"
    CONTACT = "contact"
    HOURS = "hours"
    SERVICE_AREA = "service_area"
    LICENSING = "licensing"
    SERVICES_PRICING = "services_pricing"
    PRESENCE = "presence"
    # --- APPEND ONLY, added for the product branch of the intake ---
    #
    # A product sheet has nowhere to put features, positioning or the
    # watch-list, and the enum above is local-shaped.
    #
    # APPENDING IS SAFE AND INSERTING IS NOT. Declaration order is claim-ID
    # order (`assigned_claims`), and a claim ID change re-keys every cached
    # verdict for that client. Every pre-existing sheet's sections sort BEFORE
    # these three, so existing FS-nn ids are byte-identical — which
    # tests/test_factsheet_intake.py pins with a fixture. Inserting a member in
    # the middle, or reordering, renumbers sheets that are already in front of
    # clients. Don't.
    FEATURES = "features"
    POSITIONING = "positioning"
    WATCHLIST = "watchlist"


class Polarity(StrEnum):
    """Whether the claim asserts a thing is so, or asserts it is not.

    Negatives are where the value is (§4.4): "Closed Sunday." is what makes an
    "open 7 days" answer flaggable. The polarity is metadata for review and
    ranking — the negation itself must live in ``FactClaim.value`` as a complete
    assertion, because the judge only ever quotes the value.
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"


class SourceKind(StrEnum):
    """Where a claim came from, in roughly descending authority for a fact."""

    SITE_JSONLD = "site_jsonld"
    SITE_TEXT = "site_text"
    GBP = "gbp"
    DIRECTORY = "directory"
    REGISTRY = "registry"
    LEAD_FORM = "lead_form"
    CLIENT = "client"


class Verification(StrEnum):
    """How well corroborated one claim is (plan §8).

    This is per-CLAIM and orthogonal to :class:`SheetStatus`, which is per-SHEET.
    A signature confers ``CLIENT_CONFIRMED`` only on the lines the owner actually
    vouched for; it does not upgrade the rest.
    """

    PUBLIC_SOURCE_ONLY = "public_source_only"
    CROSS_CONFIRMED = "cross_confirmed"
    CLIENT_CONFIRMED = "client_confirmed"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SheetStatus(StrEnum):
    """Lifecycle state of the sheet as a document (plan §2, §11.5).

    "Brand Fact Sheet v1.0" in ``docs/audit-packaging-research.md`` §9.4 is
    defined as the snapshot at the moment this first reaches ``SIGNED``.
    """

    DRAFT = "draft"
    CLIENT_REVIEWED = "client_reviewed"
    SIGNED = "signed"


class BusinessKind(StrEnum):
    """Which template the sheet renders against.

    The values are pinned to the teaser's ``BusinessKind``
    (``teaser/src/types/domain.ts:25``) so a sheet crossing the Python/TypeScript
    boundary needs no translation table — one is exactly how the local flag types
    ended up inert on the consumer path instead of switched off by hand.
    """

    PRODUCT = "product"
    LOCAL_SERVICE = "local_service"


# Weakest first. `verification_tier` is a min over this, so the ordering is the
# semantics, not a display detail.
_VERIFICATION_RANK: dict[Verification, int] = {
    Verification.PUBLIC_SOURCE_ONLY: 0,
    Verification.CROSS_CONFIRMED: 1,
    Verification.CLIENT_CONFIRMED: 2,
}

_SECTION_ORDER: dict[SheetSection, int] = {s: i for i, s in enumerate(SheetSection)}


@dataclass(frozen=True, kw_only=True)
class FactClaim:
    """One falsifiable line of the sheet, with the evidence for it attached.

    Keyword-only on purpose: eleven positional fields, seven of which are short
    strings, is a transposition waiting to happen — and swapping ``value`` with
    ``verbatim_quote`` would pass every check here while silently defeating the
    §4.1 quote gate.

    ``claim_id`` defaults to empty because the extractor that builds a claim does
    not know its position yet; :meth:`FactSheet.assign_claim_ids` stamps it.
    """

    claim_id: str = ""
    section: SheetSection
    key: str  # the fact-row key ("hours_sunday") — carries the section for the judge
    value: str  # a complete assertion, quotable on its own (§4.4)
    polarity: Polarity
    verbatim_quote: str  # the literal source line, never a paraphrase (§4.1)
    source_url: str
    source_kind: SourceKind
    as_of: str  # ISO date, stamped from the fetch (§4.5)
    verification: Verification
    confidence: Confidence

    def __post_init__(self) -> None:
        # Every rule here is a way the sheet degrades SILENTLY rather than
        # loudly, which is why they are constructor errors and not warnings.
        if not self.key.strip():
            # `_build_fact_sheet` (csv_loader.py:204) falls back to the bare
            # value when the key is empty, and the key is the only section
            # signal the judge ever receives — a keyless row is a fact with no
            # dimension attached (plan §2.1). The parser strips cells, so
            # whitespace-only fails the same way.
            raise ValueError("FactClaim.key must be non-empty (plan §2.1)")
        if not self.value.strip():
            raise ValueError(f"FactClaim.value must be non-empty (key={self.key!r})")
        if not self.verbatim_quote.strip():
            # An unquoted claim cannot pass the §4.1 substring gate downstream,
            # so it must never enter the structure in the first place.
            raise ValueError(f"FactClaim.verbatim_quote must be non-empty (key={self.key!r})")
        if "\n" in self.value or "\r" in self.value:
            # The value becomes one CSV cell and one fact-sheet line. The csv
            # module would quote the newline and read it back intact, but
            # `_build_fact_sheet` joins lines with "\n" — so the tail of the
            # value arrives at the judge as a second, keyless fact.
            raise ValueError(f"FactClaim.value must not contain a newline (key={self.key!r})")


def assigned_claims(claims: Sequence[FactClaim]) -> list[FactClaim]:
    """Claims in section order, insertion order within a section, ids stamped.

    Pure. ``docs/query-generation-plan.md`` §1a scores accuracy against claim
    ids, so they must be stable across regenerations of the same sheet: same
    claims in, same ids out, regardless of the order the extraction layers
    happened to emit them in. Python's sort is stable, so two claims in one
    section keep the order they were extracted in.
    """
    ordered = sorted(claims, key=lambda c: _SECTION_ORDER[c.section])
    return [replace(c, claim_id=f"FS-{i:02d}") for i, c in enumerate(ordered, start=1)]


@dataclass(kw_only=True)
class FactSheet:
    """One business's sheet: the claims, the questions, and the document's state.

    Mutable, unlike the claims it holds — a sheet is a living record that gains
    claims, gets reviewed and gets signed (§12.2), while a claim is a value
    object that is replaced rather than edited. Keyword-only for the same reason
    as :class:`FactClaim`, and so ``generated_at`` can stay mandatory without
    being dragged ahead of the fields that have sane defaults.
    """

    domain: str
    business_name: str
    business_kind: BusinessKind
    claims: list[FactClaim] = field(default_factory=list)
    # Disagreements between sources become questions instead of claims (§4.3): a
    # stale footer plus a correct AI answer would otherwise flag the AI as wrong
    # when it is right.
    questions: list[str] = field(default_factory=list)
    version: int = 1
    sheet_status: SheetStatus = SheetStatus.DRAFT
    generated_at: str  # ISO-8601; required, because an undated sheet cannot go stale (§4.5)
    lead_ref: str | None = None

    def assign_claim_ids(self) -> None:
        """Reorder and renumber ``claims`` in place. Idempotent."""
        self.claims = assigned_claims(self.claims)

    @property
    def verification_tier(self) -> Verification:
        """The WEAKEST verification across the claims.

        A sheet is only as confirmed as its least-confirmed line, because §8's
        permissions are read off the document, not off whichever claim happens to
        be cited. An empty sheet reports the weakest tier: it has vouched for
        nothing, and the conservative answer is the safe one here.
        """
        if not self.claims:
            return Verification.PUBLIC_SOURCE_ONLY
        return min(
            (c.verification for c in self.claims),
            key=lambda v: _VERIFICATION_RANK[v],
        )
