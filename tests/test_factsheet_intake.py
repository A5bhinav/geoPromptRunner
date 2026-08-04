"""The intake: registry shape, assertion quality, the quote gate, claim-ID stability.

Every test here makes ZERO engine calls and costs nothing. That is not a nice
property, it is the design: `src/audit/factsheet/intake/` has no clock, no
network and no model, so the whole package can be checked exhaustively on every
commit rather than sampled.

The adversarial tests (the quote gate, claim-ID stability) guard invariants where
the failure is silent and expensive — a false accusation in a document we send a
stranger, or a renumbering that re-keys every cached verdict for a client. Never
weaken them to make a change land.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from src.audit.factsheet.extract import INTAKE_SOURCE_URL_PREFIX, verify_quotes
from src.audit.factsheet.intake import (
    MAX_CARDS,
    REGISTRY,
    Answer,
    AnswerKind,
    assertions_for,
    build_plan,
    claims_from_answers,
    question,
    run_inputs_from_answers,
    to_assertion,
    unfalsifiable_terms,
    upgrade_confirmed,
)
from src.audit.factsheet.intake.assertions import _VOLATILE_PREFIXES
from src.audit.factsheet.models import (
    BusinessKind,
    Confidence,
    FactClaim,
    Polarity,
    SheetSection,
    SourceKind,
    Verification,
    assigned_claims,
)
from src.audit.factsheet.render import expected_fact_sheet_text, to_csv
from src.prompts.csv_loader import parse_csv_files

AS_OF = "2026-08-04"
BUSINESS = "Albert Nahman Plumbing"
SESSION = "11111111-2222-3333-4444-555555555555"

_ID_RE = re.compile(r"^Q-(ID|LOC|PRD|END)-\d\d$")

_RUN_CSV = """block,key,value,intent,persona
config,client_name,Albert Nahman Plumbing,,
config,category,plumbing contractor,,
config,engines,openai,,
query,q1,best plumber in Berkeley California,category,homeowner
"""


# --- registry properties ------------------------------------------------------


def test_every_question_id_is_unique_and_well_formed() -> None:
    ids = [q.id for q in REGISTRY]
    assert len(ids) == len(set(ids)), "duplicate question id in the registry"
    for qid in ids:
        assert _ID_RE.match(qid), f"{qid} is not in the Q-(ID|LOC|PRD|END)-nn namespace"


@pytest.mark.parametrize("q", REGISTRY, ids=lambda q: q.id)
def test_every_question_is_structurally_answerable(q: object) -> None:
    """A card must know what it asks, why, and where the answer goes."""
    assert getattr(q, "prompt", "").strip(), "a card with no prompt cannot be rendered"
    assert getattr(q, "why", "").strip(), "a card whose point cannot be stated should not be asked"
    for key in getattr(q, "keys", ()):
        assert key.strip(), "an empty fact-row key is a fact with no dimension attached"
    kind = q.kind
    assert isinstance(kind, AnswerKind)
    if kind in {AnswerKind.CHOICE, AnswerKind.MULTI}:
        assert len(getattr(q, "options", ())) >= 2, "a choice needs choices"


def test_a_question_that_produces_claims_has_a_section() -> None:
    """Section routes the claim. A claim with no section has nowhere to render
    and no place in the claim-ID ordering."""
    for q in REGISTRY:
        if q.produces_claims and q.keys:
            assert q.section is not None, f"{q.id} produces claims but has no section"


def test_show_if_only_ever_points_backwards() -> None:
    """A card cannot be conditional on an answer that has not been given yet."""
    order = {q.id: i for i, q in enumerate(REGISTRY)}
    for q in REGISTRY:
        if q.show_if is None:
            continue
        other = q.show_if[0]
        assert other in order, f"{q.id} depends on unknown question {other}"
        assert order[other] < order[q.id], f"{q.id} depends on a LATER question"


@pytest.mark.parametrize("kind", list(BusinessKind))
def test_a_plan_never_exceeds_the_card_ceiling(kind: BusinessKind) -> None:
    plan = build_plan(business_kind=kind)
    assert len(plan) <= MAX_CARDS, f"{kind} plan is {len(plan)} cards"
    assert plan, "a plan with no cards asks nothing"


@pytest.mark.parametrize("kind", list(BusinessKind))
def test_a_plan_only_contains_its_own_branch(kind: BusinessKind) -> None:
    for q in build_plan(business_kind=kind):
        assert q.branch in (None, kind), f"{q.id} leaked into the {kind} plan"


def test_trimming_never_drops_a_negative_or_an_unskippable_card() -> None:
    """Negatives are where the value is; dropping one to fit a card budget
    trades the highest-yield question on the sheet for a cosmetic one."""
    for kind in BusinessKind:
        plan = build_plan(business_kind=kind)
        kept = {q.id for q in plan}
        for q in REGISTRY:
            if q.branch not in (None, kind):
                continue
            if q.negative_first or not q.skippable:
                assert q.id in kept, f"{q.id} was trimmed and must never be"


# --- assertions ---------------------------------------------------------------

# One fixture answer per card that produces claims. Parametrised over the whole
# registry, so a new card with no fixture fails loudly here rather than shipping
# with an untested sentence.
_ANSWERS: dict[str, object] = {
    "Q-ID-01": "local_service",
    "Q-ID-02": {"identity_name": BUSINESS, "identity_category": "a plumbing contractor"},
    "Q-ID-03": "Family-owned plumbing and heating contractor serving the East Bay since 1982",
    "Q-ID-06": ["Nahman Plumbing of San Jose"],
    "Q-LOC-01": {"contact_phone": "(510) 408-7879"},
    "Q-LOC-02": ["(510) 555-0100"],
    "Q-LOC-03": {"sunday": "closed", "monday": "8:00 AM to 5:00 PM"},
    "Q-LOC-04": "no",
    "Q-LOC-06": ["Berkeley", "Albany"],
    "Q-LOC-07": ["Marin County"],
    "Q-LOC-08": "CSLB 1083634",
    "Q-LOC-09": ["drain cleaning", "water heaters"],
    "Q-LOC-10": ["septic work"],
    "Q-LOC-11": "0",
    "Q-LOC-12": {"presence_gbp": "https://maps.google.com/x"},
    "Q-PRD-01": "subscription",
    "Q-PRD-02": [{"name": "Pro", "price": "$20/month", "includes": "everything"}],
    "Q-PRD-03": "$5.99/month membership",
    "Q-PRD-04": "no",
    "Q-PRD-05": "Ring 5, released 2026-05-28",
    "Q-PRD-06": ["sleep tracking"],
    "Q-PRD-07": ["a redesigned app"],
    "Q-PRD-08": ["Android app"],
    "Q-PRD-09": ["iOS"],
    "Q-PRD-11": "endurance athletes",
    "Q-PRD-12": ["Ultrahuman"],
    "Q-END-01": [{"said": "Oura has no subscription", "truth": "a membership is required"}],
    "Q-END-02": "It is sometimes described as a medical device. It is not one",
}

_CLAIMING_IDS = [q.id for q in REGISTRY if q.produces_claims and q.keys]


def test_every_claiming_card_has_a_fixture_answer() -> None:
    missing = [qid for qid in _CLAIMING_IDS if qid not in _ANSWERS]
    assert not missing, f"no fixture answer for {missing} — its sentence is untested"


@pytest.mark.parametrize("qid", _CLAIMING_IDS)
def test_every_assertion_is_a_complete_quotable_sentence(qid: str) -> None:
    q = question(qid)
    built = assertions_for(
        q, Answer(question_id=qid, value=_ANSWERS[qid]), as_of=AS_OF, business_name=BUSINESS
    )
    assert built, f"{qid} produced no assertion from a filled answer"
    for a in built:
        assert a.value.strip(), "an empty assertion is a line asserting nothing"
        # FactClaim.__post_init__ raises on these, three layers from the builder
        # that let a textarea through.
        assert "\n" not in a.value and "\r" not in a.value
        assert a.value.rstrip().endswith("."), f"{qid}: {a.value!r} is not a sentence"
        assert a.quote.strip(), "a claim with no quote cannot show its provenance"


@pytest.mark.parametrize("qid", _CLAIMING_IDS)
def test_a_skipped_card_produces_zero_claims(qid: str) -> None:
    """Rule 2. A blank must produce zero claims, not an empty claim — a
    dimension the sheet is silent on is one that can never produce a false flag."""
    q = question(qid)
    for blank in (
        Answer(question_id=qid, value=_ANSWERS[qid], skipped=True),
        Answer(question_id=qid, value=None),
        Answer(question_id=qid, value=""),
    ):
        assert assertions_for(q, blank, as_of=AS_OF, business_name=BUSINESS) == []
        for key in q.keys:
            assert to_assertion(q, key, blank, as_of=AS_OF, business_name=BUSINESS) is None


@pytest.mark.parametrize(
    ("qid", "value", "expected"),
    [
        ("Q-LOC-04", "no", "No after-hours or emergency service."),
        ("Q-LOC-07", ["Marin County"], "Does not serve Marin County."),
        ("Q-LOC-10", ["septic work"], "Does not offer septic work."),
        # Pricing is volatile, so this one carries its date inside the sentence.
        ("Q-PRD-04", "no", f"There is no free tier (as of {AS_OF})."),
        ("Q-PRD-08", ["Android app"], "There is no Android app."),
        ("Q-ID-06", ["Nahman Plumbing of San Jose"], None),
    ],
)
def test_the_worked_negative_sentences_are_pinned(
    qid: str, value: object, expected: str | None
) -> None:
    """The exact wording the owner is quoted on. Pinned because these are the
    sentences that make an over-claiming answer flaggable, and a well-meaning
    rewrite into a positive would silently defeat the whole card."""
    built = assertions_for(
        question(qid), Answer(question_id=qid, value=value), as_of=AS_OF, business_name=BUSINESS
    )
    assert built
    assert built[0].polarity is Polarity.NEGATIVE
    if expected is not None:
        assert built[0].value == expected


def test_closed_and_open_days_read_as_sentences() -> None:
    built = {
        a.key: a
        for a in assertions_for(
            question("Q-LOC-03"),
            Answer(question_id="Q-LOC-03", value={"sunday": "closed", "monday": "8am to 5pm"}),
            as_of=AS_OF,
            business_name=BUSINESS,
        )
    }
    assert built["hours_sunday"].value.startswith("Closed Sunday.")
    assert built["hours_sunday"].polarity is Polarity.NEGATIVE
    assert built["hours_monday"].value.startswith("Open Monday 8am to 5pm")
    assert built["hours_monday"].polarity is Polarity.POSITIVE


def test_a_day_the_owner_left_alone_produces_nothing() -> None:
    """"We don't know Tuesday" and "closed Tuesday" are different facts and only
    one of them is ours to assert."""
    built = assertions_for(
        question("Q-LOC-03"),
        Answer(question_id="Q-LOC-03", value={"sunday": "closed", "tuesday": ""}),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert [a.key for a in built] == ["hours_sunday"]


@pytest.mark.parametrize("qid", _CLAIMING_IDS)
def test_volatile_keys_carry_their_date(qid: str) -> None:
    """A price from March is not a wrong price, it is an old one, and the
    sentence has to say which — inside the value, because the judge reads
    nothing else."""
    built = assertions_for(
        question(qid),
        Answer(question_id=qid, value=_ANSWERS[qid]),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    # Imported, not restated: a second copy of the prefix list is a second
    # opinion about what goes stale, and the two would drift.
    for a in built:
        if a.key.startswith(_VOLATILE_PREFIXES):
            assert f"(as of {AS_OF})" in a.value, f"{a.key} is volatile and undated"


def test_hours_are_not_date_stamped() -> None:
    """Deliberate. A stamp on all seven day claims is seven pieces of noise on
    the shortest, most-quoted lines of a local sheet, and opening hours are
    already covered by the claim's own `as_of` column and the sheet's
    `generated_at`. Prices and version numbers are the two places a model is
    systematically behind reality, and they are the two that carry it."""
    built = assertions_for(
        question("Q-LOC-03"),
        Answer(question_id="Q-LOC-03", value={"sunday": "closed"}),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert built[0].value == "Closed Sunday."


def test_the_marketing_guard_reports_and_never_blocks() -> None:
    assert "leading" in unfalsifiable_terms("the leading platform for teams")
    assert "award-winning" in unfalsifiable_terms("Award-Winning service")
    assert unfalsifiable_terms("open 8am to 5pm, closed Sunday") == ()
    # Reporting only: the sentence is still built. Refusing to let an owner
    # describe their own business is worse than one unfireable claim.
    built = assertions_for(
        question("Q-ID-03"),
        Answer(question_id="Q-ID-03", value="The leading plumber in Berkeley"),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert built and built[0].value == "The leading plumber in Berkeley."


# --- claims -------------------------------------------------------------------


def _answers() -> list[Answer]:
    return [
        Answer(question_id=qid, value=value, raw=str(value))
        for qid, value in _ANSWERS.items()
        if qid in {"Q-ID-01", "Q-LOC-01", "Q-LOC-04", "Q-LOC-07", "Q-LOC-10"}
    ]


def test_claims_are_client_confirmed_and_carry_session_provenance() -> None:
    """The point of the whole feature: this is the only writer of
    CLIENT_CONFIRMED, and the tier is what unlocks HIGH and CRITICAL findings."""
    claims = claims_from_answers(
        _answers(), session_id=SESSION, as_of=AS_OF, business_name=BUSINESS
    )
    assert claims
    for c in claims:
        assert c.verification is Verification.CLIENT_CONFIRMED
        assert c.source_kind is SourceKind.CLIENT
        assert c.confidence is Confidence.HIGH
        assert c.source_url.startswith(INTAKE_SOURCE_URL_PREFIX)
        assert SESSION in c.source_url


def test_run_inputs_are_not_claims() -> None:
    """Aliases and the trade are matcher and query-generator inputs. Asserting
    "Also known as Acme Plumbing." spends a line the judge cannot falsify."""
    answers = [
        Answer(question_id="Q-ID-05", value=["Nahman Plumbing", "A. Nahman"]),
        Answer(question_id="Q-LOC-00", value="plumbing"),
        Answer(question_id="Q-ID-02", value={"identity_name": BUSINESS}),
    ]
    claims = claims_from_answers(
        answers, session_id=SESSION, as_of=AS_OF, business_name=BUSINESS
    )
    assert all(c.key != "identity_aliases" for c in claims)
    inputs = run_inputs_from_answers(answers)
    assert inputs.aliases == ("Nahman Plumbing", "A. Nahman")
    assert inputs.trade == "plumbing"
    assert inputs.business == BUSINESS


def test_confirming_a_crawl_claim_upgrades_only_that_claim() -> None:
    """A signature confers client_confirmed only on the lines the owner actually
    vouched for; it does not upgrade the rest. `source_kind` is preserved —
    the fact still came off the website."""
    crawl = [
        FactClaim(
            section=SheetSection.CONTACT,
            key="contact_phone",
            value="The published phone number is (510) 408-7879.",
            polarity=Polarity.POSITIVE,
            verbatim_quote="Call us: (510) 408-7879",
            source_url="https://example.test/contact",
            source_kind=SourceKind.SITE_TEXT,
            as_of=AS_OF,
            verification=Verification.PUBLIC_SOURCE_ONLY,
            confidence=Confidence.MEDIUM,
        ),
        FactClaim(
            section=SheetSection.IDENTITY,
            key="identity_founded",
            value="The business has operated since 1982.",
            polarity=Polarity.POSITIVE,
            verbatim_quote="since 1982",
            source_url="https://example.test/about",
            source_kind=SourceKind.SITE_TEXT,
            as_of=AS_OF,
            verification=Verification.PUBLIC_SOURCE_ONLY,
            confidence=Confidence.MEDIUM,
        ),
    ]
    upgraded = {c.key: c for c in upgrade_confirmed(crawl, frozenset({"contact_phone"}))}
    assert upgraded["contact_phone"].verification is Verification.CLIENT_CONFIRMED
    assert upgraded["contact_phone"].source_kind is SourceKind.SITE_TEXT
    assert upgraded["identity_founded"].verification is Verification.PUBLIC_SOURCE_ONLY


# --- the quote gate (adversarial; never weaken) --------------------------------


def _claim(**overrides: object) -> FactClaim:
    base = {
        "section": SheetSection.CONTACT,
        "key": "contact_phone",
        "value": "The published phone number is (510) 408-7879.",
        "polarity": Polarity.POSITIVE,
        "verbatim_quote": "Call us: (510) 408-7879",
        "source_url": "https://example.test/contact",
        "source_kind": SourceKind.SITE_TEXT,
        "as_of": AS_OF,
        "verification": Verification.PUBLIC_SOURCE_ONLY,
        "confidence": Confidence.MEDIUM,
    }
    base.update(overrides)
    return FactClaim(**base)  # type: ignore[arg-type]  # the mapping is literal above


def test_a_site_claim_whose_quote_is_absent_is_still_dropped() -> None:
    """The CLIENT carve-out is on the SOURCE KIND and never on the content. A
    crawl claim the page does not support must not survive because a client
    claim now can."""
    kept, dropped = verify_quotes(
        [_claim()], {"https://example.test/contact": "we have no phone number here"}
    )
    assert kept == []
    assert len(dropped) == 1


def test_a_client_claim_passes_the_gate_with_no_page_at_all() -> None:
    """The owner said so, on the record, in a session we can point at. There is
    no page to quote and demanding one would make the intake impossible."""
    claim = _claim(
        source_kind=SourceKind.CLIENT,
        source_url=f"{INTAKE_SOURCE_URL_PREFIX}{SESSION}/Q-LOC-01",
    )
    kept, dropped = verify_quotes([claim], {})
    assert kept == [claim]
    assert dropped == []


def test_a_client_claim_with_an_empty_quote_cannot_be_constructed() -> None:
    """The carve-out relaxes the SUBSTRING test, not the requirement that a
    claim have evidence behind it at all."""
    with pytest.raises(ValueError):
        _claim(source_kind=SourceKind.CLIENT, verbatim_quote="   ")


# --- claim-ID stability (the appended-sections regression) ---------------------


def test_appending_sections_did_not_renumber_existing_local_claims() -> None:
    """FEATURES / POSITIONING / WATCHLIST were APPENDED to SheetSection.

    Declaration order is claim-ID order, and a claim ID is inside the judge
    cache key — renumbering a sheet re-keys every cached verdict for that
    client. Every pre-existing section sorts before the three new ones, so these
    ids are pinned to the bytes they had before the change.
    """
    claims = [
        _claim(section=SheetSection.PRESENCE, key="presence_gbp", value="A.", verbatim_quote="a"),
        _claim(section=SheetSection.IDENTITY, key="identity_name", value="B.", verbatim_quote="b"),
        _claim(section=SheetSection.CONTACT, key="contact_phone", value="C.", verbatim_quote="c"),
        _claim(section=SheetSection.HOURS, key="hours_sunday", value="D.", verbatim_quote="d"),
        _claim(
            section=SheetSection.SERVICE_AREA,
            key="service_area_towns",
            value="E.",
            verbatim_quote="e",
        ),
        _claim(
            section=SheetSection.LICENSING, key="licensing_number", value="F.", verbatim_quote="f"
        ),
        _claim(
            section=SheetSection.SERVICES_PRICING,
            key="services_offered",
            value="G.",
            verbatim_quote="g",
        ),
    ]
    assigned = assigned_claims(claims)
    assert [(c.claim_id, c.key) for c in assigned] == [
        ("FS-01", "identity_name"),
        ("FS-02", "contact_phone"),
        ("FS-03", "hours_sunday"),
        ("FS-04", "service_area_towns"),
        ("FS-05", "licensing_number"),
        ("FS-06", "services_offered"),
        ("FS-07", "presence_gbp"),
    ]


def test_a_watchlist_claim_sorts_after_every_pre_existing_section() -> None:
    claims = [
        _claim(section=SheetSection.WATCHLIST, key="watchlist_1", value="W.", verbatim_quote="w"),
        _claim(section=SheetSection.IDENTITY, key="identity_name", value="I.", verbatim_quote="i"),
    ]
    assert [c.key for c in assigned_claims(claims)] == ["identity_name", "watchlist_1"]


# --- round trip ---------------------------------------------------------------


def test_intake_claims_round_trip_through_the_real_parser() -> None:
    """answers → claims → fact rows → the parser the run actually uses.

    The judge's view of the sheet has to survive a CSV round trip byte for byte;
    the value is one cell and one line, and anything that splits it delivers the
    tail as a second, keyless fact.
    """
    from src.audit.factsheet.models import FactSheet

    claims = claims_from_answers(
        _answers(), session_id=SESSION, as_of=AS_OF, business_name=BUSINESS
    )
    sheet = FactSheet(
        domain="albertnahmanplumbing.com",
        business_name=BUSINESS,
        business_kind=BusinessKind.LOCAL_SERVICE,
        claims=list(claims),
        generated_at=AS_OF,
    )
    result = parse_csv_files([("run.csv", _RUN_CSV), ("facts.csv", to_csv(sheet))])
    assert result.ok, [e.message for e in result.errors]
    assert result.audit is not None
    assert result.audit.fact_sheet == expected_fact_sheet_text(sheet)
    assert len(result.audit.facts) == len(sheet.claims)


def test_a_generated_sheet_reaches_the_client_confirmed_tier() -> None:
    """The whole point. One `public_source_only` claim caps the sheet at
    LOW/MED and hides every serious finding, so a sheet built purely from intake
    answers must reach the top tier."""
    from src.audit.factsheet.models import FactSheet

    sheet = FactSheet(
        domain="albertnahmanplumbing.com",
        business_name=BUSINESS,
        business_kind=BusinessKind.LOCAL_SERVICE,
        claims=claims_from_answers(
            _answers(), session_id=SESSION, as_of=AS_OF, business_name=BUSINESS
        ),
        generated_at=AS_OF,
    )
    assert sheet.verification_tier is Verification.CLIENT_CONFIRMED

    # And one leftover crawl claim drags the whole sheet back down — which is
    # why the review screen must drop or confirm every last one.
    sheet.claims.append(
        replace(sheet.claims[0], verification=Verification.PUBLIC_SOURCE_ONLY, key="stale_key")
    )
    assert sheet.verification_tier is Verification.PUBLIC_SOURCE_ONLY
