"""The intake: registry shape, assertion quality, the quote gate, claim-ID stability.

Every test here makes ZERO engine calls and costs nothing. That is not a nice
property, it is the design: `src/audit/factsheet/intake/` has no clock, no
network and no model, so the whole package can be checked exhaustively on every
commit rather than sampled.

The adversarial tests (the quote gate, claim-ID stability) guard invariants where
the failure is silent and expensive — a false accusation in a document we send a
stranger, or a renumbering that re-keys every cached verdict for a client. Never
weaken them to make a change land.

THE SIX-AUDIENCE TEST. The registry is one spine of sixteen asked of every
business, so the fixtures below deliberately mix archetypes — a plumber's hours,
a law firm's hourly rate, a SaaS's "we have no phone line", a product's
discontinued model. A card that only holds one of those is a card that has
started to fork again, and these tests are where that shows up.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from src.audit.factsheet.extract import (
    INTAKE_SOURCE_URL_PREFIX,
    intake_question_id,
    intake_source_url,
    verify_quotes,
)
from src.audit.factsheet.intake import (
    MAX_CARDS,
    REGISTRY,
    Answer,
    AnswerKind,
    PartKind,
    assertions_for,
    build_plan,
    claims_from_answers,
    derive_trade,
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

_ID_RE = re.compile(r"^Q-(WHAT|KIND|OFFER|COST|REACH|PROOF|AI)-\d\d$")

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
        assert _ID_RE.match(qid), (
            f"{qid} is not in the Q-(WHAT|KIND|OFFER|COST|REACH|PROOF|AI)-nn space"
        )


def test_the_spine_is_exactly_seventeen_cards() -> None:
    """Seventeen is the ceiling AND the floor.

    It was sixteen, and the rule was that a new card has to displace one because
    every fix so far had been a widening rather than an addition — the
    for-instance line absorbed all of it. `Q-KIND-01` is the exception that
    earned its place: the for-instance line CANNOT absorb it, because the
    business kind is what SELECTS the for-instance line, and it also selects the
    query allocation. Left unasked it was defaulted to `local_service` at session
    creation, and a B2B agency was measured with "my digital marketing agency
    keeps breaking, what should I do".
    """
    assert len(REGISTRY) == MAX_CARDS == 17


@pytest.mark.parametrize("q", REGISTRY, ids=lambda q: q.id)
def test_every_question_is_structurally_answerable(q: object) -> None:
    """A card must know what it asks, why, and where the answer goes."""
    assert getattr(q, "prompt", "").strip(), "a card with no prompt cannot be rendered"
    assert getattr(q, "why", "").strip(), "a card whose point cannot be stated should not be asked"
    for key in getattr(q, "keys", ()):
        assert key.strip(), "an empty fact-row key is a fact with no dimension attached"
    kind = q.kind
    assert isinstance(kind, AnswerKind)
    if kind in {AnswerKind.CHOICE, AnswerKind.MULTI, AnswerKind.AVAILABILITY}:
        assert q.parts or len(q.options) >= 2, "a choice needs choices"


@pytest.mark.parametrize("q", REGISTRY, ids=lambda q: q.id)
def test_every_part_is_renderable_and_points_at_a_sibling(q: object) -> None:
    """The composite cards describe their own shape IN THE REGISTRY. Without
    that the frontend has to know which card is which, and the contract this
    module exists to keep — the UI hardcodes no question — stops being true."""
    keys = {p.key for p in q.parts}
    assert len(keys) == len(q.parts), f"{q.id} has two parts writing the same key"
    for p in q.parts:
        assert p.label.strip(), f"{q.id}.{p.key} has no label"
        assert isinstance(p.kind, PartKind)
        if p.kind is PartKind.CHOICE:
            assert len(p.options) >= 2, f"{q.id}.{p.key} is a choice with no choices"
            if p.reveal_on:
                assert p.reveal_on in {o.value for o in p.options}
        if p.kind is PartKind.PAIRS:
            assert all(p.labels), f"{q.id}.{p.key} is a pairs part with an unlabelled column"
        if p.show_when is not None:
            sibling, expected = p.show_when
            assert sibling in keys, f"{q.id}.{p.key} depends on unknown part {sibling}"
            other = next(x for x in q.parts if x.key == sibling)
            assert expected in {o.value for o in other.options}, (
                f"{q.id}.{p.key} waits on a value {sibling} can never hold"
            )


@pytest.mark.parametrize("q", REGISTRY, ids=lambda q: q.id)
def test_every_card_has_a_neutral_for_instance(q: object) -> None:
    """`neutral` is what a business that is neither local nor product sees — an
    agency, a restaurant, a nonprofit, a marketplace. It is REQUIRED precisely
    so an unknown business kind is never a broken card."""
    assert q.examples.neutral.strip(), f"{q.id} has no neutral for-instance"
    assert q.examples.pick(None) == q.examples.neutral
    assert q.examples.pick(BusinessKind.PRODUCT).strip()
    assert q.examples.pick(BusinessKind.LOCAL_SERVICE).strip()


def test_every_card_is_skippable() -> None:
    """There is no gate question and no unskippable card. Rule 2 says a blank is
    safe, and a router that cannot be skipped is a router that produces guesses —
    which is what the old branched registry did with "which trade is it?"."""
    for q in REGISTRY:
        assert q.skippable, f"{q.id} cannot be skipped; the spine has no gate"


def test_a_question_that_produces_claims_has_a_section() -> None:
    """Section routes the claim. A claim with no section has nowhere to render
    and no place in the claim-ID ordering."""
    for q in REGISTRY:
        if q.produces_claims and q.keys:
            assert q.section is not None, f"{q.id} produces claims but has no section"


def test_the_plan_is_the_whole_spine_for_every_business() -> None:
    """`business_kind` is no longer a router. All sixteen, always — the plan does
    not vary by kind, by prefill, or by what has been answered so far."""
    plan = build_plan()
    assert [q.id for q in plan] == [q.id for q in REGISTRY]
    assert plan == build_plan(prefill={"identity_name": {"value": BUSINESS}})
    assert plan == build_plan(answers={"Q-WHAT-01": {"identity_name": BUSINESS}})


def test_every_flag_dimension_has_a_negative_producer() -> None:
    """Negatives are where the value is: an invented capability, an over-claimed
    price and a fabricated support line are all UNFLAGGABLE without a stated
    negative to contradict them, because an omission is never a finding."""
    negatives = {q.section for q in REGISTRY if q.negative_first and q.section is not None}
    for section in (
        SheetSection.IDENTITY,
        SheetSection.CONTACT,
        SheetSection.HOURS,
        SheetSection.SERVICE_AREA,
        SheetSection.SERVICES_PRICING,
    ):
        assert section in negatives, f"{section} has no negative-first producer"


# --- assertions ---------------------------------------------------------------

# One fixture answer per card that produces claims. Parametrised over the whole
# registry, so a new card with no fixture fails loudly here rather than shipping
# with an untested sentence. The values deliberately span archetypes.
_ANSWERS: dict[str, object] = {
    "Q-WHAT-01": {"identity_name": BUSINESS, "identity_category": "a plumbing contractor"},
    "Q-WHAT-02": "Family-owned plumbing and heating contractor serving the East Bay since 1982",
    "Q-WHAT-03": ["Nahman Plumbing", "A. Nahman"],
    "Q-WHAT-04": ["Nahman Plumbing of San Jose"],
    "Q-OFFER-01": ["drain cleaning", "water heaters"],
    "Q-OFFER-02": ["septic work"],
    "Q-OFFER-03": {
        "current": "the Ring 5, released 2026-05-28",
        "added": [{"what": "emergency water damage", "when": "March"}],
        "removed": [{"what": "duct cleaning", "when": "January 2026"}],
    },
    "Q-COST-01": [
        {
            "what": "a diagnostic visit",
            "price": "$89",
            "basis": "per_visit",
            "includes": "the callout",
        }
    ],
    "Q-COST-02": {"extra": "$5.99/month membership", "free": "no"},
    "Q-REACH-01": {
        "contact_phone": "(510) 408-7879",
        "none": ["address"],
        "retired": ["(510) 555-0100"],
    },
    "Q-REACH-02": {
        "scope": "places",
        "included": ["Berkeley", "Albany"],
        "excluded": ["Marin County"],
        "city": "Berkeley",
        "region": "California",
    },
    "Q-REACH-03": {
        "scope": "set_hours",
        "days": {"sunday": "closed", "monday": "8:00 AM to 5:00 PM"},
        "after_hours": "no",
    },
    "Q-PROOF-01": {
        "credentials": [{"what": "licence 1083634", "issuer": "CSLB"}],
        "not_held": ["HIPAA compliance"],
    },
    "Q-PROOF-02": {"competitors": ["Ultrahuman"], "for": "East Bay homeowners"},
    "Q-AI-01": {
        "watchlist": [{"said": "they are open on Sundays", "truth": "the shop is closed Sunday"}]
    },
    "Q-AI-02": "It is sometimes described as a franchise. It is not one",
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


def test_the_alias_card_produces_no_claim_at_all() -> None:
    """`Q-WHAT-03` is a MATCHER input, not ground truth. "Also known as Acme
    Plumbing." is not falsifiable, so asserting it spends a line that can never
    fire — while missing the mention scores as absence, which is the most
    expensive kind of wrong the measurement can be."""
    q = question("Q-WHAT-03")
    assert not q.produces_claims
    assert (
        assertions_for(
            q,
            Answer(question_id=q.id, value=["Nahman Plumbing"]),
            as_of=AS_OF,
            business_name=BUSINESS,
        )
        == []
    )


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


# The worked table from the agent plan §4.2, pinned key by key. These are the
# sentences the owner is quoted on and the sentences that make an over-claiming
# answer flaggable; a well-meaning rewrite into a positive silently defeats the
# card, and a wording drift breaks the demo the whole feature is sold on.
@pytest.mark.parametrize(
    ("qid", "value", "key", "expected", "polarity"),
    [
        # --- identity
        (
            "Q-WHAT-04",
            ["Nahman Plumbing of San Jose"],
            "identity_not_1",
            "Not affiliated with Nahman Plumbing of San Jose.",
            Polarity.NEGATIVE,
        ),
        # --- what you don't offer: the single highest-value card in the set
        (
            "Q-OFFER-02",
            ["septic work"],
            "services_excluded_1",
            "Does not offer septic work.",
            Polarity.NEGATIVE,
        ),
        (
            "Q-OFFER-02",
            ["an Android app"],
            "services_excluded_1",
            "Does not offer an Android app.",
            Polarity.NEGATIVE,
        ),
        # --- staleness: the removed half is the valuable one
        (
            "Q-OFFER-03",
            {"removed": [{"what": "duct cleaning", "when": "January 2026"}]},
            "features_removed_1",
            f"No longer offers duct cleaning, discontinued January 2026 (as of {AS_OF}).",
            Polarity.NEGATIVE,
        ),
        # --- price + basis. A PRICE WITH NO BASIS IS UNCHECKABLE.
        (
            "Q-COST-01",
            [{"what": "a diagnostic visit", "price": "$89", "basis": "per_visit"}],
            "pricing_row_1",
            f"The price for a diagnostic visit is $89 per visit (as of {AS_OF}).",
            Polarity.POSITIVE,
        ),
        (
            "Q-COST-01",
            [{"what": "partner time", "price": "$450", "basis": "per_hour"}],
            "pricing_row_1",
            f"The price for partner time is $450 per hour (as of {AS_OF}).",
            Polarity.POSITIVE,
        ),
        (
            "Q-COST-01",
            [{"what": "the Business plan", "price": "$12", "basis": "per seat/mo"}],
            "pricing_row_1",
            f"The price for the Business plan is $12 per seat per month (as of {AS_OF}).",
            Polarity.POSITIVE,
        ),
        (
            "Q-COST-01",
            [{"what": "estimates", "price": "Free"}],
            "pricing_row_1",
            f"There is no charge for estimates (as of {AS_OF}).",
            Polarity.POSITIVE,
        ),
        (
            "Q-COST-01",
            [{"what": "repiping", "price": "Quote only"}],
            "pricing_row_1",
            (
                "The price for repiping is quoted individually rather than at a "
                f"fixed price (as of {AS_OF})."
            ),
            Polarity.POSITIVE,
        ),
        # --- the most demo-able claim the system can make
        (
            "Q-COST-02",
            {"extra": "$5.99/month membership"},
            "pricing_mandatory_extra",
            (
                "A $5.99/month membership is required in addition to the listed "
                f"price (as of {AS_OF})."
            ),
            Polarity.POSITIVE,
        ),
        (
            "Q-COST-02",
            {"free": "no"},
            "pricing_free_option",
            f"There is no free option (as of {AS_OF}).",
            Polarity.NEGATIVE,
        ),
        # --- contact absences: unflaggable unless asserted
        (
            "Q-REACH-01",
            {"none": ["phone"]},
            "contact_none_phone",
            "There is no phone support.",
            Polarity.NEGATIVE,
        ),
        (
            "Q-REACH-01",
            {"none": ["address"]},
            "contact_none_address",
            "There is no public office address.",
            Polarity.NEGATIVE,
        ),
        (
            "Q-REACH-01",
            {"retired": ["(510) 555-0100"]},
            "contact_retired_1",
            "(510) 555-0100 is no longer in use by this business.",
            Polarity.NEGATIVE,
        ),
        # --- service area, including the half nothing else in the system produces
        (
            "Q-REACH-02",
            {"scope": "anywhere"},
            "service_area_scope",
            "Available anywhere.",
            Polarity.POSITIVE,
        ),
        (
            "Q-REACH-02",
            {"excluded": ["Marin County"]},
            "service_area_excluded_1",
            "Does not serve Marin County.",
            Polarity.NEGATIVE,
        ),
        # --- availability: "reach a person", never "available"
        (
            "Q-REACH-03",
            {"days": {"sunday": "closed"}},
            "hours_sunday",
            "Closed Sunday.",
            Polarity.NEGATIVE,
        ),
        (
            "Q-REACH-03",
            {"days": {"monday": "8:00 AM to 5:00 PM"}},
            "hours_monday",
            "Open Monday 8:00 AM to 5:00 PM.",
            Polarity.POSITIVE,
        ),
        (
            "Q-REACH-03",
            {"scope": "always"},
            "hours_scope",
            "A person can be reached 24 hours a day, 7 days a week.",
            Polarity.POSITIVE,
        ),
        (
            "Q-REACH-03",
            {"after_hours": "no"},
            "hours_after_hours",
            "No after-hours service.",
            Polarity.NEGATIVE,
        ),
        # --- licensing: the only producer this dimension has anywhere
        (
            "Q-PROOF-01",
            {"credentials": [{"what": "licence 1083634", "issuer": "CSLB"}]},
            "licensing_credentials_1",
            "Holds licence 1083634, issued by CSLB.",
            Polarity.POSITIVE,
        ),
        (
            "Q-PROOF-01",
            {"credentials": [{"what": "a SOC 2 Type II report", "issuer": "Prescient"}]},
            "licensing_credentials_1",
            "Holds a SOC 2 Type II report, issued by Prescient.",
            Polarity.POSITIVE,
        ),
        (
            "Q-PROOF-01",
            {"not_held": ["HIPAA compliance"]},
            "licensing_not_held_1",
            "Does not hold HIPAA compliance.",
            Polarity.NEGATIVE,
        ),
    ],
)
def test_the_worked_assertion_table_is_pinned(
    qid: str, value: object, key: str, expected: str, polarity: Polarity
) -> None:
    built = {
        a.key: a
        for a in assertions_for(
            question(qid),
            Answer(question_id=qid, value=value),
            as_of=AS_OF,
            business_name=BUSINESS,
        )
    }
    assert key in built, f"{qid} produced {sorted(built)}, not {key}"
    assert built[key].value == expected
    assert built[key].polarity is polarity


def test_one_claim_per_thing_not_one_claim_listing_everything() -> None:
    """A wrong figure on the Business plan should flag the Business plan. A
    single combined line makes every finding about all of them."""
    built = assertions_for(
        question("Q-OFFER-02"),
        Answer(question_id="Q-OFFER-02", value=["septic work", "commercial jobs"]),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert [a.key for a in built] == ["services_excluded_1", "services_excluded_2"]


def test_a_day_the_owner_left_alone_produces_nothing() -> None:
    """ "We don't know Tuesday" and "closed Tuesday" are different facts and only
    one of them is ours to assert."""
    built = assertions_for(
        question("Q-REACH-03"),
        Answer(question_id="Q-REACH-03", value={"days": {"sunday": "closed", "tuesday": ""}}),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert [a.key for a in built] == ["hours_sunday"]


def test_a_price_row_with_no_number_is_not_a_price_claim() -> None:
    """Rule 2 again. A label with no figure asserts nothing the judge can grade."""
    built = assertions_for(
        question("Q-COST-01"),
        Answer(question_id="Q-COST-01", value=[{"what": "repiping", "price": ""}]),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert built == []


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
    the shortest, most-quoted lines of a sheet, and opening hours are already
    covered by the claim's own `as_of` column and the sheet's `generated_at`.
    Prices and what-changed are the two places a model is systematically behind
    reality, and they are the two that carry it."""
    built = assertions_for(
        question("Q-REACH-03"),
        Answer(question_id="Q-REACH-03", value={"days": {"sunday": "closed"}}),
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
        question("Q-WHAT-02"),
        Answer(question_id="Q-WHAT-02", value="The leading plumber in Berkeley"),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert built and built[0].value == "The leading plumber in Berkeley."


# --- claims -------------------------------------------------------------------


def _answers() -> list[Answer]:
    return [
        Answer(question_id=qid, value=value, raw=str(value))
        for qid, value in _ANSWERS.items()
        if qid in {"Q-WHAT-01", "Q-REACH-01", "Q-REACH-03", "Q-OFFER-02", "Q-COST-02"}
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


def test_a_pricing_note_is_asserted_in_the_owners_own_words() -> None:
    """The escape hatch for terms four columns cannot hold — "we bill in
    15-minute increments", "first hour 1.5x after 6pm". It is NOT reformatted
    into the row frame: forcing "The price for … is …" onto it produces a
    sentence nobody said, and the whole reason the box exists is that the answer
    did not fit a row."""
    built = assertions_for(
        question("Q-COST-01"),
        Answer(
            question_id="Q-COST-01",
            value={
                "rows": [{"what": "Diagnostic visit", "price": "$89", "basis": "per_visit"}],
                "note": "After 6pm the first hour is billed at 1.5x",
            },
        ),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    keys = {a.key for a in built}
    assert "pricing_note" in keys
    note = next(a for a in built if a.key == "pricing_note")
    assert note.value.startswith("After 6pm the first hour is billed at 1.5x")
    # Date-stamped like every other price claim: pricing is the most volatile
    # thing on the sheet.
    assert AS_OF in note.value
    # And the rows still produce their own claims alongside it.
    assert any(k.startswith("pricing_row_") for k in keys)


def test_a_pricing_answer_stored_before_the_note_existed_is_unchanged() -> None:
    """A bare list is what every already-approved sheet holds. Those claims must
    come out byte-identical — the owner signed them, and re-keying a stored
    sheet's claims would invalidate every cached verdict measured against it."""
    rows = [{"what": "Diagnostic visit", "price": "$89", "basis": "per_visit"}]
    legacy = assertions_for(
        question("Q-COST-01"),
        Answer(question_id="Q-COST-01", value=rows),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    wrapped = assertions_for(
        question("Q-COST-01"),
        Answer(question_id="Q-COST-01", value={"rows": rows}),
        as_of=AS_OF,
        business_name=BUSINESS,
    )
    assert [(a.key, a.value, a.quote) for a in legacy] == [
        (a.key, a.value, a.quote) for a in wrapped
    ]
    assert "pricing_note" not in {a.key for a in legacy}


def test_every_claim_names_the_card_that_produced_it() -> None:
    """The review screen edits a claim by RE-ANSWERING its card, so every claim
    has to be able to say which card that was. Without this round trip the
    approve gate is read-only and a wrong founding date can only be fixed by
    deleting the session and starting over."""
    claims = claims_from_answers(
        _answers(), session_id=SESSION, as_of=AS_OF, business_name=BUSINESS
    )
    assert claims
    answered = {a.question_id for a in _answers()}
    for c in claims:
        qid = intake_question_id(c.source_url)
        assert qid in answered, f"{c.key} points at {qid!r}, which nobody answered"
        # The id has to resolve to a real card, or the editor opens nothing.
        assert question(qid).id == qid


def test_a_claim_with_no_card_behind_it_is_not_editable() -> None:
    """A crawl claim carried over from the previous sheet has no answer to
    re-open. It reports "" rather than a plausible-looking id, because the
    review screen decides whether to offer Edit on exactly this test — and an
    Edit button that opens a card the owner never saw would rewrite facts they
    did not touch."""
    assert intake_question_id("https://example.com/about") == ""
    assert intake_question_id("") == ""
    assert intake_question_id(intake_source_url(SESSION, "Q-WHAT-01")) == "Q-WHAT-01"


def test_run_inputs_are_not_claims() -> None:
    """Aliases, the city and the derived trade are matcher and query-generator
    inputs. Asserting "Also known as Acme Plumbing." spends a line the judge
    cannot falsify."""
    answers = [
        Answer(question_id="Q-WHAT-03", value=["Nahman Plumbing", "A. Nahman"]),
        Answer(
            question_id="Q-WHAT-01",
            value={"identity_name": BUSINESS, "identity_category": "a plumbing contractor"},
        ),
        Answer(
            question_id="Q-REACH-02",
            value={"scope": "places", "city": "Berkeley", "region": "California"},
        ),
        Answer(question_id="Q-PROOF-02", value={"competitors": ["Ultrahuman"]}),
    ]
    claims = claims_from_answers(
        answers, session_id=SESSION, as_of=AS_OF, business_name=BUSINESS
    )
    assert all(c.key != "identity_aliases" for c in claims)
    # The location anchor is a run input too — `service_area_included` carries
    # the falsifiable version of where the business works.
    assert all(c.key not in {"city", "region"} for c in claims)

    inputs = run_inputs_from_answers(answers)
    assert inputs.aliases == ("Nahman Plumbing", "A. Nahman")
    assert inputs.business == BUSINESS
    assert inputs.city == "Berkeley"
    assert inputs.region == "California"
    assert inputs.competitors == ("Ultrahuman",)


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


def test_the_trade_is_derived_and_a_miss_is_normal() -> None:
    """Under the branched design "which trade is it?" was a gate question with a
    dead end at "something else". It is now derived from the category the owner
    already confirmed, and a miss falls through to the generic generator."""
    assert derive_trade("a plumbing contractor") == "plumbing"
    assert derive_trade("HVAC and refrigeration") == "hvac"
    assert derive_trade("an employment law firm") == ""
    assert derive_trade("") == ""


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
        source_url=f"{INTAKE_SOURCE_URL_PREFIX}{SESSION}/Q-REACH-01",
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
