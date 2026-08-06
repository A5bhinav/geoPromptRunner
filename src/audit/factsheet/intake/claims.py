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

import re
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
from src.prompts.local_templates import TRADES

__all__ = [
    "RunInputs",
    "derive_trade",
    "claims_from_answers",
    "run_inputs_from_answers",
    "upgrade_confirmed",
    "sections_present",
]


@dataclass(frozen=True, kw_only=True)
class RunInputs:
    """What the intake learned that is NOT ground truth.

    Name variants, the trade and the state are matcher and query-generator
    inputs (agent plan §4.4). Asserting ``identity_aliases: Also known as Acme
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
    #: What they sell, in the owner's words (``Q-OFFER-01``), and the places they
    #: serve (``Q-REACH-02``). FAN-OUT SLOTS, not decoration: one shape times six
    #: services is six real questions, which is what lifts a bank of ~30 lines
    #: past a 50-question set. Every value is a line somebody confirmed, so the
    #: extra questions are more specific rather than merely more numerous.
    services: tuple[str, ...] = field(default_factory=tuple)
    areas: tuple[str, ...] = field(default_factory=tuple)
    #: Who it is for (``Q-PROOF-02``'s second half) — one segment, not a list.
    segment: str = ""
    #: ``local_service`` | ``product`` | ``""``. THE ANSWER TO ``Q-KIND-01``, and
    #: the only source of it the query set is allowed to read — never the crawl,
    #: never the session's stored column, which was stamped at creation before
    #: anybody had been asked. Empty means unanswered or skipped, and unanswered
    #: builds the general set: a local set is built around a city, and guessing
    #: local is what produced "my digital marketing agency keeps breaking".
    business_kind: str = ""


#: How many values one fan-out slot may contribute. Six services is six good
#: questions; twenty is twenty near-duplicates, a near_duplicate warning per
#: pair, and a set that spends its whole budget on one dimension.
_MAX_FANOUT = 6


def _as_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _as_names(value: object) -> list[str]:
    """A list of BRAND NAMES, one per entry, however they were typed.

    ONE CHIP CAN HOLD SIX COMPETITORS. The chip control does not split on commas
    — deliberately, because "Berkeley, Albany" is one service area and tearing it
    in two invented a town nobody serves. But a competitor field typed the same
    way is six agencies in one string, and it reached the generator as a single
    name: the set shipped ``"Black Propeller vs Tinuiti, Directive, KlientBoost,
    Disruptive Advertising, Power Digital, JumpFly"`` as one question, and
    ``_guarantee_comparison_coverage`` thought all six were covered because a
    substring test passes against the joined string. Six head-to-heads — the
    highest-value questions in the instrument — became two nobody would ask.

    So names are split HERE, at the boundary, and only for the fields that hold
    names. Commas, semicolons, newlines and a trailing " and " all separate;
    ``_as_list`` is untouched and still keeps a place name whole.
    """
    out: list[str] = []
    for entry in _as_list(value):
        for part in re.split(r"[,;\n]| \band\b ", entry):
            name = part.strip(" \t.")
            if name:
                out.append(name)
    return out


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


def derive_trade(category: str) -> str:
    """A hand-written trade template id, or ``""`` — AND A MISS IS THE NORMAL CASE.

    Under the branched design "which trade is it?" was a gate question with a
    dead end at "something else". Under one spine it is not a question at all:
    the category label the owner already confirmed on ``Q-WHAT-01`` is matched
    against ``TRADES``, a hit buys 29 hand-written, human-validated queries for
    free, and a miss falls through to the generic generator with everything it
    needs (agent plan §4.5). The trade templates are a quality upgrade for three
    trades, not the only path for one business type.

    Substring rather than equality because the label is prose the owner wrote —
    "plumbing contractor", "family plumbing & heating" — not a chosen enum.
    """
    text = category.casefold()
    for trade in TRADES:
        if trade in text:
            return trade
    return ""


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
    identity = _mapping(by_id["Q-WHAT-01"].value) if "Q-WHAT-01" in by_id else {}
    if identity.get("identity_name"):
        business = str(identity["identity_name"]).strip()
    if identity.get("identity_website"):
        website = str(identity["identity_website"]).strip()
    if identity.get("identity_category"):
        category = str(identity["identity_category"]).strip()

    aliases = _as_list(by_id["Q-WHAT-03"].value) if "Q-WHAT-03" in by_id else []

    competitors: list[str] = []
    segment = ""
    if "Q-PROOF-02" in by_id:
        proof = _mapping(by_id["Q-PROOF-02"].value)
        competitors = _as_names(proof.get("competitors"))
        segment = str(proof.get("for") or "").strip()

    # WHAT THEY SELL, AS THE QUALIFIER ON A CATEGORY QUESTION. "best {category}"
    # is one question; "best {category} for {service}" is one per service, and
    # methodology §3.2 asks for exactly that — a qualifier drawn from the sheet's
    # real segments rather than a head term repeated. Capped, because the card
    # asks for categories rather than SKUs but a coffee roaster can still type
    # twenty, and twenty near-identical questions is a worse set than six.
    services = _as_list(by_id["Q-OFFER-01"].value)[:_MAX_FANOUT] if "Q-OFFER-01" in by_id else []

    # The kind, from the card that asks it and nowhere else. An unrecognised
    # value is dropped rather than coerced: "" means we were not told, and the
    # generator treats not-told as not-local.
    kind = ""
    if "Q-KIND-01" in by_id:
        answered = str(by_id["Q-KIND-01"].value or "").strip()
        kind = answered if answered in {"local_service", "product"} else ""

    # City and region ride inside Q-REACH-02's "specific places" answer — the
    # run's location anchor. `service_area_included` carries the falsifiable
    # version of where the business works; these two are the anchor the query set
    # is built around, and asserting them would spend a claim on something the
    # judge has no way to check.
    #
    # THE REGION MUST BE THE FULL STATE NAME. `assemble.py`'s
    # `_ABBREVIATED_REGION_RE` rejects "CA", and the SERP vendors answer an
    # abbreviation with an EMPTY local surface — which reads downstream as the
    # brand being absent rather than as a bad request. The lint blocks on it, and
    # the card renders a select rather than a text field so it cannot be typed
    # wrong in the first place.
    city = ""
    region = ""
    area = _mapping(by_id["Q-REACH-02"].value) if "Q-REACH-02" in by_id else {}
    if area.get("city"):
        city = str(area["city"]).strip()
    if area.get("region"):
        region = str(area["region"]).strip()
    # The towns they named, as their own local questions. "{category} in
    # Berkeley" and "{category} in Albany" are two different local packs and two
    # different answers; one home city could only ever ask about one of them.
    areas = [
        a for a in _as_list(area.get("included"))[:_MAX_FANOUT] if a.casefold() != city.casefold()
    ]

    return RunInputs(
        business=business,
        website=website,
        trade=derive_trade(category),
        city=city,
        region=region,
        category=category,
        aliases=tuple(aliases),
        competitors=tuple(competitors),
        business_kind=kind,
        services=tuple(services),
        areas=tuple(areas),
        segment=segment,
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
