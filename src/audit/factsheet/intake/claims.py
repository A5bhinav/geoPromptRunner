"""Answers → ``FactClaim``s, and the run inputs that are deliberately not claims.

THE ONE THING THIS MODULE EXISTS FOR. ``FactSheet.verification_tier`` is the
WEAKEST verification across the sheet's claims, and
``SENDABLE_SEVERITIES[public_source_only]`` is ``{LOW, MED}``. Every
auto-generated sheet is permanently ``public_source_only`` — nothing else can
upgrade one — so HIGH and CRITICAL accuracy findings are structurally
unreachable today. The claims built here carry
``Verification.CLIENT_CONFIRMED``, and this is the only mechanism in the system
that can set it. It is not a nicer form; it is the switch that turns the accuracy
half of the product on.

Pure. No clock (``as_of`` is passed), no network, no storage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from src.audit.factsheet.extract import intake_source_url
from src.audit.factsheet.intake import assertions as assertions_mod
from src.audit.factsheet.intake.assertions import Answer
from src.audit.factsheet.intake.questions import BY_ID
from src.audit.factsheet.models import (
    Confidence,
    FactClaim,
    SheetSection,
    SourceKind,
    Verification,
)

__all__ = [
    "RunInputs",
    "claims_from_answers",
    "run_inputs_from_answers",
    "upgrade_confirmed",
    "sections_present",
]


@dataclass(frozen=True, kw_only=True)
class RunInputs:
    """What the intake learned that is NOT ground truth.

    Name variants, the trade and the state are matcher and query-generator
    inputs (plan §4.4). Asserting ``identity_aliases: Also known as Acme
    Plumbing.`` puts a line in front of the judge that cannot be true or false,
    which spends a claim and can never produce a finding. They ride here
    instead, and reach the run through ``render.suggested_run_inputs`` and the
    generated CSV's config block.
    """

    business: str = ""
    website: str = ""
    trade: str = ""
    city: str = ""
    region: str = ""
    category: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    competitors: tuple[str, ...] = field(default_factory=tuple)


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def claims_from_answers(
    answers: Sequence[Answer],
    *,
    session_id: str,
    as_of: str,
    business_name: str,
) -> list[FactClaim]:
    """Every claim the session produced, in the order it was answered.

    ``source_kind`` is CLIENT and ``source_url`` is
    ``intake://{session}/{question}``. That pair is the whole provenance story:
    the §4.1 substring gate exempts CLIENT precisely because there is no page to
    quote, and what makes the claim trustworthy instead is that we can point at
    the session and the question the owner answered.

    ``confidence`` is HIGH without qualification. The owner is the authority on
    their own phone number; a "medium confidence" client statement would be a
    hedge with nothing behind it.
    """
    out: list[FactClaim] = []
    for answer in answers:
        question = BY_ID.get(answer.question_id)
        if question is None or question.section is None:
            continue
        built = assertions_mod.assertions_for(
            question, answer, as_of=as_of, business_name=business_name
        )
        for assertion in built:
            out.append(
                FactClaim(
                    section=question.section,
                    key=assertion.key,
                    value=assertion.value,
                    polarity=assertion.polarity,
                    # The owner's own words, verbatim. Never the assertion: the
                    # quote is the evidence FOR the assertion, and making them
                    # the same string makes the provenance column decorative.
                    verbatim_quote=assertion.quote or assertion.value,
                    source_url=intake_source_url(session_id, question.id),
                    source_kind=SourceKind.CLIENT,
                    as_of=as_of,
                    verification=Verification.CLIENT_CONFIRMED,
                    confidence=Confidence.HIGH,
                )
            )
    return out


def run_inputs_from_answers(
    answers: Sequence[Answer],
    *,
    fallback_business: str = "",
    fallback_website: str = "",
) -> RunInputs:
    """The non-claim half of the session: what the query set needs to be built."""
    by_id = {a.question_id: a for a in answers if not a.is_blank}

    business = fallback_business
    website = fallback_website
    category = ""
    identity = _mapping(by_id["Q-ID-02"].value) if "Q-ID-02" in by_id else {}
    if identity.get("identity_name"):
        business = str(identity["identity_name"]).strip()
    if identity.get("identity_website"):
        website = str(identity["identity_website"]).strip()
    if identity.get("identity_category"):
        category = str(identity["identity_category"]).strip()

    trade = str(by_id["Q-LOC-00"].value or "") if "Q-LOC-00" in by_id else ""
    aliases = _as_list(by_id["Q-ID-05"].value) if "Q-ID-05" in by_id else []
    competitors = _as_list(by_id["Q-PRD-12"].value) if "Q-PRD-12" in by_id else []

    # City and region ride on the service-area card's structured value when the
    # UI supplies one. The REGION MUST BE THE FULL STATE NAME — `assemble.py`'s
    # `_ABBREVIATED_REGION_RE` rejects "CA", and the SERP vendor answers an
    # abbreviation with an empty local surface, which reads downstream as the
    # brand being absent rather than as a bad request. The lint blocks on it.
    city = ""
    region = ""
    area = _mapping(by_id["Q-LOC-06"].value) if "Q-LOC-06" in by_id else {}
    if area.get("city"):
        city = str(area["city"]).strip()
    if area.get("region"):
        region = str(area["region"]).strip()

    return RunInputs(
        business=business,
        website=website,
        trade=trade,
        city=city,
        region=region,
        category=category,
        aliases=tuple(aliases),
        competitors=tuple(competitors),
    )


def upgrade_confirmed(
    crawl_claims: Sequence[FactClaim],
    confirmed_keys: frozenset[str],
) -> list[FactClaim]:
    """Promote the crawl claims the owner actually vouched for, and only those.

    ``Verification`` is per-CLAIM: "a signature confers client_confirmed only on
    the lines the owner actually vouched for; it does not upgrade the rest"
    (plan §8). ``source_kind`` is PRESERVED — the fact still came off the
    website; what changed is that a human now stands behind it, and rewriting
    the source would destroy the provenance trail that made it checkable.
    """
    return [
        replace(c, verification=Verification.CLIENT_CONFIRMED) if c.key in confirmed_keys else c
        for c in crawl_claims
    ]


def sections_present(claims: Sequence[FactClaim]) -> list[SheetSection]:
    """Sections with at least one claim, in declaration order. For the review UI."""
    present = {c.section for c in claims}
    return [s for s in SheetSection if s in present]
