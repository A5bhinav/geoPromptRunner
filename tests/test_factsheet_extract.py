"""F1: the deterministic extractor must be unable to invent a fact.

The adversarial cases are the point of this file. A test that a plumber's
JSON-LD yields a phone number only proves the happy path works; what protects a
stranger from a false accusation is that a quote the page does not contain gets
dropped, that a bot-challenge page refuses instead of profiling noise, and that
two sources disagreeing produce a question rather than a winner.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.audit.crawl.models import FetchMeta, PageCategory, PageRecord
from src.audit.factsheet import (
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SourceKind,
    Verification,
    expected_fact_sheet_text,
    to_markdown,
)
from src.audit.factsheet.extract import (
    LEAD_FORM_SOURCE_URL,
    MIN_EXTRACTION_TEXT_CHARS,
    ThinTextError,
    assert_sufficient_text,
    build_sheet,
    claims_from_html,
    claims_from_json_ld,
    claims_from_lead_form,
    derive_negative_claims,
    page_text_index,
    resolve_conflicts,
    verify_quotes,
)

_URL = "https://fortplumbing.example/"
_AS_OF = "2026-07-31"

# A real trade site's homepage markup: LocalBusiness under a subtype (`Plumber`),
# nested in an `@graph` alongside the WebSite node, which is exactly the shape
# extruct's uniform=True hands back from Yoast/RankMath-generated pages.
_PLUMBER_NODE: dict[str, Any] = {
    "@type": "Plumber",
    "@id": "https://fortplumbing.example/#business",
    "name": "Fort Plumbing",
    "telephone": "(510) 555-0100",
    "priceRange": "$$",
    "address": {
        "@type": "PostalAddress",
        "streetAddress": "1420 San Pablo Ave",
        "addressLocality": "Berkeley",
        "addressRegion": "CA",
        "postalCode": "94702",
    },
    "areaServed": [
        {"@type": "City", "name": "Berkeley"},
        {"@type": "City", "name": "Albany"},
        {"@type": "City", "name": "El Cerrito"},
    ],
    "sameAs": [
        "https://www.yelp.com/biz/fort-plumbing-berkeley",
        "https://www.facebook.com/fortplumbing",
    ],
    "openingHoursSpecification": [
        {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": [
                "https://schema.org/Monday",
                "https://schema.org/Tuesday",
                "https://schema.org/Wednesday",
                "https://schema.org/Thursday",
                "https://schema.org/Friday",
            ],
            "opens": "07:30",
            "closes": "17:00",
        },
        {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": "https://schema.org/Saturday",
            "opens": "08:00",
            "closes": "14:00",
        },
    ],
}

_PLUMBER_BLOCK: dict[str, Any] = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebSite", "name": "Fort Plumbing", "url": _URL},
        _PLUMBER_NODE,
    ],
}

# tel: in the header, NAP + mailto: in the footer — trafilatura keeps the middle
# and throws the rest away, which is why the gate cannot read only its output.
_SITE_HTML = """<html><body>
<header><a href="tel:+15105550100">(510) 555-0100</a></header>
<main><p>Emergency plumbing, drain cleaning and water-heater repair in Berkeley.</p></main>
<footer>
<p>Fort Plumbing &middot; 1420 San Pablo Ave, Berkeley, CA 94702</p>
<p><a href="mailto:dispatch@fortplumbing.example">dispatch@fortplumbing.example</a></p>
</footer>
</body></html>"""

_MAIN_TEXT = "Emergency plumbing, drain cleaning and water-heater repair in Berkeley. " * 4


def _page(
    *,
    json_ld: list[dict[str, Any]] | None = None,
    html: str | None = None,
    text: str = _MAIN_TEXT,
    blocked: bool = False,
    url: str = _URL,
) -> PageRecord:
    return PageRecord(
        url=url,
        normalized_url=url,
        category=PageCategory.HOMEPAGE,
        fetch_meta=FetchMeta(
            status_code=200,
            final_url=url,
            fetched_at="2026-07-31T09:00:00Z",
            was_rendered=False,
            request_ua="GPTBot",
            blocked=blocked,
            headers={},
        ),
        content_sha256="sha",
        raw_html=html,
        extracted_text=text,
        json_ld=json_ld or [],
    )


def _claim(**overrides: Any) -> FactClaim:
    fields: dict[str, Any] = {
        "section": SheetSection.CONTACT,
        "key": "contact_phone",
        "value": "(510) 555-0100",
        "polarity": Polarity.POSITIVE,
        "verbatim_quote": "Call us: (510) 555-0100",
        "source_url": _URL,
        "source_kind": SourceKind.SITE_TEXT,
        "as_of": _AS_OF,
        "verification": Verification.PUBLIC_SOURCE_ONLY,
        "confidence": Confidence.HIGH,
    }
    return FactClaim(**{**fields, **overrides})


def _by_key(claims: list[FactClaim]) -> dict[str, FactClaim]:
    return {claim.key: claim for claim in claims}


# --- C6: the thin-text refusal (§4.6) ----------------------------------------


def test_a_bot_challenge_page_refuses_extraction() -> None:
    # Cloudflare serves this at HTTP 200, so status is no defence. Extracting a
    # fact sheet from it would assert things no page ever said.
    with pytest.raises(ThinTextError):
        assert_sufficient_text(
            ["Just a moment...\nEnable JavaScript and cookies to continue"], _URL
        )


def test_an_unhydrated_spa_shell_refuses_extraction() -> None:
    with pytest.raises(ThinTextError):
        assert_sufficient_text([""], _URL)
    with pytest.raises(ThinTextError):
        assert_sufficient_text([None], _URL)


def test_a_real_homepage_passes_the_floor() -> None:
    assert_sufficient_text([_MAIN_TEXT], _URL)


def test_the_floor_matches_the_typescript_one() -> None:
    # teaser/src/resolver/profileExtraction.ts:48 — one threshold in two
    # languages, so both paths refuse exactly the same pages.
    assert MIN_EXTRACTION_TEXT_CHARS == 200


def test_the_refusal_message_names_the_url_and_the_shortfall() -> None:
    with pytest.raises(ThinTextError) as excinfo:
        assert_sufficient_text(["thin"], _URL)
    assert _URL in str(excinfo.value)
    assert "200" in str(excinfo.value)


# --- L0: the lead form (§3) --------------------------------------------------


def test_lead_form_yields_name_website_and_area() -> None:
    claims = claims_from_lead_form(
        "Fort Plumbing",
        "https://fortplumbing.example",
        "Berkeley, CA",
        "We do 24/7 emergency callouts and whole-house repipes",
        as_of=_AS_OF,
    )
    assert [c.key for c in claims] == ["identity_name", "identity_website", "service_area_primary"]
    assert all(c.source_kind is SourceKind.LEAD_FORM for c in claims)
    assert all(c.source_url == LEAD_FORM_SOURCE_URL for c in claims)


def test_the_lead_form_description_never_becomes_a_claim() -> None:
    """§3 L0: the description is a hint for later layers, never a fact on its own."""
    claims = claims_from_lead_form(
        "Fort Plumbing",
        "https://fortplumbing.example",
        "Berkeley, CA",
        "We do 24/7 emergency callouts and whole-house repipes",
        as_of=_AS_OF,
    )
    assert not any("emergency" in c.value.lower() for c in claims)
    assert not any("repipe" in c.value.lower() for c in claims)


def test_a_blank_lead_field_emits_nothing() -> None:
    claims = claims_from_lead_form("Fort Plumbing", "https://x.example", None, None, as_of=_AS_OF)
    assert [c.key for c in claims] == ["identity_name", "identity_website"]


def test_the_area_is_kept_exactly_as_typed() -> None:
    claims = claims_from_lead_form("F", "https://x.example", " Berkeley, CA ", None, as_of=_AS_OF)
    area = _by_key(claims)["service_area_primary"]
    # Not canonicalized to "Berkeley,California,United States": that form belongs
    # to the query config, and a rewritten string is no longer the verbatim thing
    # the lead typed, which is the only evidence this claim has.
    assert area.value == "Berkeley, CA"
    assert area.verbatim_quote == "Berkeley, CA"


# --- L1a: JSON-LD ------------------------------------------------------------


def _hours_only(claims: list[FactClaim]) -> list[FactClaim]:
    """The hours claims out of a node's harvest.

    NOT A WEAKENING OF THE TESTS BELOW. They each assert "this markup produces no
    hours" or "exactly these seven days", and they used to say it as a claim on
    the WHOLE list — which only worked while a bare `{"@type": "Plumber", ...}`
    node happened to yield nothing else. It yields `identity_category` now, so
    the incidental coupling has to go or the next harvested property breaks them
    again. What each one checks is unchanged.
    """
    return [c for c in claims if c.section is SheetSection.HOURS]


def test_local_business_subtype_inside_a_graph_is_harvested() -> None:
    claims = _by_key(claims_from_json_ld([_PLUMBER_BLOCK], _URL, _AS_OF))
    assert claims["identity_name"].value == "Fort Plumbing"
    assert claims["contact_phone"].value == "(510) 555-0100"
    assert claims["contact_address"].value == "1420 San Pablo Ave, Berkeley, CA 94702"
    assert claims["service_area_towns"].value == "Serves Berkeley, Albany and El Cerrito."
    assert claims["pricing_range"].value == "$$"
    assert "yelp.com" in claims["presence_profiles"].value
    assert all(c.source_kind is SourceKind.SITE_JSONLD for c in claims.values())
    assert all(c.confidence is Confidence.HIGH for c in claims.values())


def test_opening_hours_specification_becomes_one_claim_per_open_day() -> None:
    claims = _by_key(claims_from_json_ld([_PLUMBER_BLOCK], _URL, _AS_OF))
    assert claims["hours_monday"].value == "Open 07:30-17:00."
    assert claims["hours_saturday"].value == "Open 08:00-14:00."
    assert "hours_sunday" not in claims  # absence is not yet an assertion — see §4.4


def test_the_schema_type_becomes_what_youd_call_it() -> None:
    """`identity_category` is the framing the judge checks AND the slot the query
    generator fills, and until now nothing produced it — so every owner typed it
    from scratch and the query set was built from whatever they typed."""
    claims = _by_key(claims_from_json_ld([_PLUMBER_BLOCK], _URL, _AS_OF))
    assert claims["identity_category"].value == "It is a plumber."
    assert claims["identity_category"].verbatim_quote == '"@type": "Plumber"'


def test_a_generic_type_is_not_a_category() -> None:
    """"Organization" and "ProfessionalService" answer "what are you filed as",
    not "what would a customer search for". Emitting one puts an unfalsifiable
    line on the sheet that can never fire and displaces the one that could."""
    for generic in ("Organization", "LocalBusiness", "ProfessionalService"):
        claims = _by_key(
            claims_from_json_ld([{"@type": generic, "name": "Acme"}], _URL, _AS_OF)
        )
        assert "identity_category" not in claims, generic


def test_a_declared_additional_type_beats_the_parent_type() -> None:
    """A site that bothers to declare `additionalType` is being more specific
    than the generic its CMS emitted."""
    claims = _by_key(
        claims_from_json_ld(
            [
                {
                    "@type": "ProfessionalService",
                    "name": "Marek & Sons",
                    "additionalType": "https://schema.org/Attorney",
                }
            ],
            _URL,
            _AS_OF,
        )
    )
    assert claims["identity_category"].value == "It is a attorney."


def test_the_category_claim_survives_the_quote_gate() -> None:
    """The quote is the `@type` pair itself, and `page_text_index` serializes
    nodes the same way — so this faces the §4.1 gate like everything else rather
    than riding in on an exemption."""
    page = _page(json_ld=[_PLUMBER_BLOCK])
    claims = [c for c in claims_from_json_ld(page.json_ld, page.url, _AS_OF)]
    kept, dropped = verify_quotes(claims, page_text_index([page]))
    assert [c.key for c in dropped] == []
    assert "identity_category" in {c.key for c in kept}


def test_a_schema_quote_is_the_json_fragment_it_came_from() -> None:
    """A human has to be able to find this in the page's ld+json block."""
    claims = _by_key(claims_from_json_ld([_PLUMBER_BLOCK], _URL, _AS_OF))
    assert claims["contact_phone"].verbatim_quote == '"telephone": "(510) 555-0100"'
    assert claims["identity_name"].verbatim_quote == '"name": "Fort Plumbing"'


def test_every_schema_claim_survives_the_quote_gate() -> None:
    page = _page(json_ld=[_PLUMBER_BLOCK])
    claims = claims_from_json_ld(page.json_ld, page.url, _AS_OF)
    kept, dropped = verify_quotes(claims, page_text_index([page]))
    assert dropped == []
    assert len(kept) == len(claims)


def test_an_organizations_premises_fields_are_still_ignored() -> None:
    """The original rule, kept and sharpened rather than dropped.

    An `Organization` is a supertype, not a LocalBusiness: its `telephone` is an
    investor-relations line as often as a customer one, its `address` is a
    registered office, and `openingHours` describe a shopfront it may not have.
    Putting a switchboard number on the sheet as the number to call would make the
    judge grade a CORRECT answer wrong.
    """
    keys = _by_key(
        claims_from_json_ld(
            [
                {
                    "@type": "Organization",
                    "name": "Fort Holdings",
                    "telephone": "(510) 555-0199",
                    "address": {"@type": "PostalAddress", "streetAddress": "1 Corporate Plaza"},
                    "priceRange": "$$$",
                    "openingHours": ["Mo-Fr 09:00-17:00"],
                    "areaServed": ["Berkeley"],
                }
            ],
            _URL,
            _AS_OF,
        )
    )
    for premises_key in ("contact_phone", "contact_address", "pricing_range", "service_area_towns"):
        assert premises_key not in keys
    assert not any(k.startswith("hours_") for k in keys)


def test_an_organizations_identity_fields_ARE_read() -> None:
    """What changed: gating the whole NODE out meant an agency or SaaS — which
    marks up as Organization — contributed nothing at all, so the sheet could say
    where a company is but never what it does."""
    keys = _by_key(
        claims_from_json_ld(
            [
                {
                    "@type": "Organization",
                    "name": "Black Propeller",
                    "description": "A paid media agency.",
                    "foundingDate": "2015",
                    "sameAs": ["https://twitter.com/blackpropeller"],
                }
            ],
            _URL,
            _AS_OF,
        )
    )
    assert keys["identity_name"].value == "Black Propeller"
    assert keys["identity_description"].value == "A paid media agency."
    assert keys["identity_founded"].value == "Founded 2015."
    assert "presence_profiles" in keys


def test_legacy_opening_hours_strings_are_parsed_conservatively() -> None:
    parsed = _by_key(
        claims_from_json_ld(
            [{"@type": "Plumber", "openingHours": ["Mo-Fr 08:00-17:00", "Sa 09:00-13:00"]}],
            _URL,
            _AS_OF,
        )
    )
    assert parsed["hours_friday"].value == "Open 08:00-17:00."
    assert parsed["hours_saturday"].value == "Open 09:00-13:00."
    # An unparseable schedule yields nothing rather than a guess — a
    # half-understood week would feed a wrong "Closed …" below.
    vague = {"@type": "Plumber", "openingHours": "By appointment"}
    assert _hours_only(claims_from_json_ld([vague], _URL, _AS_OF)) == []


def test_a_day_that_opens_and_closes_at_the_same_time_is_not_open() -> None:
    spec = {
        "@type": "Plumber",
        "openingHoursSpecification": [
            {"dayOfWeek": "Sunday", "opens": "00:00", "closes": "00:00"},
        ],
    }
    assert _hours_only(claims_from_json_ld([spec], _URL, _AS_OF)) == []


# --- §4.4: negatives, only from closed enumerations --------------------------


def test_monday_to_saturday_hours_derive_a_closed_sunday() -> None:
    claims = claims_from_json_ld([_PLUMBER_BLOCK], _URL, _AS_OF)
    derived = derive_negative_claims(claims)
    assert [c.key for c in derived] == ["hours_sunday"]
    sunday = derived[0]
    # A complete assertion, because the judge has to quote a line an answer
    # contradicts: "hours_sunday: no" is not contradictable in words (§4.4).
    assert sunday.value == "Closed Sunday."
    assert sunday.polarity is Polarity.NEGATIVE
    # It reuses the enumeration's own evidence, so it faces the same §4.1 gate.
    assert sunday.verbatim_quote == _by_key(claims)["hours_monday"].verbatim_quote


def test_a_derived_negative_passes_the_quote_gate() -> None:
    page = _page(json_ld=[_PLUMBER_BLOCK])
    claims = claims_from_json_ld(page.json_ld, page.url, _AS_OF)
    kept, dropped = verify_quotes(derive_negative_claims(claims), page_text_index([page]))
    assert len(kept) == 1
    assert dropped == []


def test_no_negative_is_derived_from_a_services_list() -> None:
    """A services list is not a closed enumeration (§4.4).

    This is the rule that keeps the sheet from asserting "does not offer slab
    leak repair" because a services page did not happen to mention it — the
    highest-value negative we could invent, and the one most likely to be false.
    """
    services = _claim(
        section=SheetSection.SERVICES_PRICING,
        key="services_offered",
        value="Offers drain cleaning, water-heater repair and repiping.",
        verbatim_quote="Our services: drain cleaning, water heater repair, repiping",
    )
    hours = claims_from_json_ld([_PLUMBER_BLOCK], _URL, _AS_OF)
    derived = derive_negative_claims([services, *hours])
    assert [c.key for c in derived] == ["hours_sunday"]
    assert not any("does not" in c.value.lower() for c in derived)
    assert not any(c.section is SheetSection.SERVICES_PRICING for c in derived)


def test_no_negative_is_derived_from_a_service_area_list() -> None:
    areas = claims_from_json_ld(
        [{"@type": "Plumber", "areaServed": [{"@type": "City", "name": "Berkeley"}]}], _URL, _AS_OF
    )
    assert derive_negative_claims(areas) == []


def test_partial_hours_markup_derives_nothing() -> None:
    # Three marked-up days is lazy markup, not a four-day closure.
    partial = {
        "@type": "Plumber",
        "openingHoursSpecification": [
            {"dayOfWeek": ["Monday", "Tuesday", "Wednesday"], "opens": "08:00", "closes": "17:00"}
        ],
    }
    assert derive_negative_claims(claims_from_json_ld([partial], _URL, _AS_OF)) == []


def test_a_seven_day_week_derives_nothing() -> None:
    always = {
        "@type": "Plumber",
        "openingHours": "Mo-Su 00:00-23:59",
    }
    claims = claims_from_json_ld([always], _URL, _AS_OF)
    assert len(_hours_only(claims)) == 7
    assert derive_negative_claims(claims) == []


def test_two_different_hours_blocks_are_not_merged_into_one_week() -> None:
    """Each (source, quote) pair is one enumeration; they must not pool days."""
    left = claims_from_json_ld(
        [{"@type": "Plumber", "openingHours": "Mo-We 08:00-17:00"}], _URL, _AS_OF
    )
    right = claims_from_json_ld(
        [{"@type": "Plumber", "openingHours": "Th-Sa 08:00-17:00"}],
        "https://fortplumbing.example/contact",
        _AS_OF,
    )
    assert derive_negative_claims([*left, *right]) == []


# --- §4.1: the verbatim-quote gate -------------------------------------------


def test_a_quote_the_page_does_not_contain_is_dropped() -> None:
    claim = _claim(value="Open 24 hours.", verbatim_quote="Open 24 hours a day, 7 days a week")
    kept, dropped = verify_quotes([claim], {_URL: "We are open Monday to Saturday, 7:30 to 5."})
    assert kept == []
    assert dropped == [claim]


def test_the_gate_ignores_whitespace_and_case() -> None:
    claim = _claim(verbatim_quote="Call us:   (510) 555-0100")
    kept, _dropped = verify_quotes([claim], {_URL: "CALL US:\n(510) 555-0100\nfor same-day help"})
    assert kept == [claim]


def test_a_claim_whose_source_was_never_fetched_is_dropped() -> None:
    # Unverifiable and verified are different states, and only one may ship.
    claim = _claim(source_url="https://someone-elses-site.example/")
    kept, dropped = verify_quotes([claim], {_URL: "Call us: (510) 555-0100"})
    assert kept == []
    assert dropped == [claim]


def test_the_gate_matches_a_trailing_slash_difference() -> None:
    claim = _claim(source_url="https://fortplumbing.example")
    kept, _dropped = verify_quotes([claim], {_URL: "Call us: (510) 555-0100"})
    assert kept == [claim]


# --- §4.3: disagreement becomes a question -----------------------------------


def test_two_sources_disagreeing_on_a_phone_emit_no_claim_and_one_question() -> None:
    """The rule that stops us flagging a correct AI answer against a stale footer."""
    site = _claim(value="(510) 555-0100", source_url="https://fortplumbing.example/")
    contact = _claim(value="(510) 555-0199", source_url="https://fortplumbing.example/contact")
    kept, questions = resolve_conflicts([site, contact])
    assert kept == []
    assert len(questions) == 1
    assert "contact_phone" in questions[0]
    assert "(510) 555-0100" in questions[0]
    assert "(510) 555-0199" in questions[0]


def test_the_same_number_formatted_two_ways_is_not_a_disagreement() -> None:
    # Questions are the scarce resource — one raised over punctuation is one the
    # owner spends attention on instead of a fact the models get wrong.
    kept, questions = resolve_conflicts(
        [_claim(value="(510) 555-0100"), _claim(value="510-555-0100", source_url=_URL + "contact")]
    )
    assert len(kept) == 1
    assert questions == []


def test_agreement_does_not_upgrade_verification() -> None:
    # Two pages of one website are one source; cross-confirmation waits for an
    # off-site source (F7, §8).
    kept, _questions = resolve_conflicts(
        [_claim(), _claim(source_url="https://fortplumbing.example/contact")]
    )
    assert kept[0].verification is Verification.PUBLIC_SOURCE_ONLY


def test_a_disagreement_on_one_key_does_not_blank_the_others() -> None:
    phone_a = _claim(value="(510) 555-0100")
    phone_b = _claim(value="(510) 555-0199", source_url=_URL + "contact")
    name = _claim(
        section=SheetSection.IDENTITY,
        key="identity_name",
        value="Fort Plumbing",
        verbatim_quote="Fort Plumbing",
    )
    kept, questions = resolve_conflicts([phone_a, phone_b, name])
    assert [c.key for c in kept] == ["identity_name"]
    assert len(questions) == 1


# --- L1b: the HTML fallback --------------------------------------------------


def test_tel_and_mailto_and_the_footer_nap_become_claims() -> None:
    claims = _by_key(claims_from_html(_SITE_HTML, _URL, _AS_OF))
    assert claims["contact_phone"].value == "(510) 555-0100"
    assert claims["contact_email"].value == "dispatch@fortplumbing.example"
    assert claims["contact_address"].value == "1420 San Pablo Ave, Berkeley, CA 94702"
    assert all(c.source_kind is SourceKind.SITE_TEXT for c in claims.values())


def test_every_html_claim_quotes_the_line_it_came_from() -> None:
    for claim in claims_from_html(_SITE_HTML, _URL, _AS_OF):
        assert claim.value in claim.verbatim_quote


def test_html_claims_survive_the_gate_even_though_trafilatura_drops_the_footer() -> None:
    # extracted_text is main content only; the NAP block lives outside it. If the
    # gate read only that, it would drop every true footer claim — and a gate
    # that fails closed on real facts is a gate someone weakens.
    page = _page(html=_SITE_HTML, text="Emergency plumbing in Berkeley.")
    claims = claims_from_html(_SITE_HTML, page.url, _AS_OF)
    kept, dropped = verify_quotes(claims, page_text_index([page]))
    assert dropped == []
    assert len(kept) == 3


def test_a_tel_link_the_page_never_displays_is_not_claimed() -> None:
    # A call-tracking number in an href that no visitor can read is not something
    # a human can check on the page.
    html = '<html><body><header><a href="tel:+15105559999">Call now</a></header></body></html>'
    assert claims_from_html(html, _URL, _AS_OF) == []


def test_a_two_line_footer_address_is_joined_across_the_adjacent_lines() -> None:
    html = (
        "<html><body><footer><p><span>1420 San Pablo Ave</span>"
        "<span>Berkeley, CA 94702</span></p></footer></body></html>"
    )
    claims = _by_key(claims_from_html(html, _URL, _AS_OF))
    assert claims["contact_address"].value == "1420 San Pablo Ave, Berkeley, CA 94702"
    # The quote is the two lines exactly as the page reads them, so collapsing
    # whitespace is all the §4.1 gate needs.
    assert claims["contact_address"].verbatim_quote == "1420 San Pablo Ave Berkeley, CA 94702"


def test_a_footer_with_no_parseable_address_emits_nothing() -> None:
    html = "<html><body><footer><p>Serving the East Bay since 1998</p></footer></body></html>"
    assert claims_from_html(html, _URL, _AS_OF) == []


# --- build_sheet: L0 + L1 end to end -----------------------------------------


def _lead_sheet(**overrides: Any) -> FactSheet:
    kwargs: dict[str, Any] = {
        "business": "Fort Plumbing",
        "website": "https://fortplumbing.example",
        "area": "Berkeley, CA",
        "description": "24/7 emergency plumbing",
        "pages": [_page(json_ld=[_PLUMBER_BLOCK], html=_SITE_HTML)],
        "generated_at": "2026-07-31T12:00:00Z",
        "lead_ref": "lead-7",
    }
    return build_sheet(**{**kwargs, **overrides})


def test_build_sheet_produces_a_cited_sheet_with_no_model_call() -> None:
    sheet = _lead_sheet()
    claims = _by_key(sheet.claims)
    assert sheet.domain == "fortplumbing.example"
    assert claims["contact_phone"].value == "(510) 555-0100"
    assert claims["hours_sunday"].value == "Closed Sunday."
    assert claims["service_area_primary"].value == "Berkeley, CA"
    assert all(c.claim_id for c in sheet.claims)
    assert all(c.as_of in {"2026-07-31"} for c in sheet.claims)


def test_build_sheet_prefers_schema_over_the_pages_own_footer() -> None:
    # §3 L1 makes the HTML pass a fallback: a page with LocalBusiness markup does
    # not also get mined for text, so the site never argues with itself.
    sheet = _lead_sheet()
    assert "contact_email" not in {c.key for c in sheet.claims}


def test_build_sheet_falls_back_to_html_when_the_page_has_no_schema() -> None:
    sheet = _lead_sheet(pages=[_page(html=_SITE_HTML)])
    claims = _by_key(sheet.claims)
    assert claims["contact_email"].value == "dispatch@fortplumbing.example"
    assert claims["contact_address"].value == "1420 San Pablo Ave, Berkeley, CA 94702"


def test_build_sheet_turns_a_lead_form_name_that_contradicts_the_site_into_a_question() -> None:
    sheet = _lead_sheet(business="Fort Plumbing & Rooter")
    assert "identity_name" not in {c.key for c in sheet.claims}
    assert len(sheet.questions) == 1
    assert "identity_name" in sheet.questions[0]


def test_build_sheet_refuses_a_corpus_of_challenge_pages() -> None:
    blocked = _page(json_ld=[_PLUMBER_BLOCK], text="Just a moment...", blocked=True)
    with pytest.raises(ThinTextError):
        _lead_sheet(pages=[blocked])


def test_build_sheet_refuses_an_empty_crawl() -> None:
    with pytest.raises(ThinTextError):
        _lead_sheet(pages=[])


def test_the_sheet_renders_through_the_f0_renderers() -> None:
    sheet = _lead_sheet()
    rendered = expected_fact_sheet_text(sheet)
    assert "hours_sunday: Closed Sunday." in rendered
    assert "contact_phone: (510) 555-0100" in rendered
    markdown = to_markdown(sheet)
    assert "## Provenance appendix" in markdown
    # Nothing here is client-confirmed, and the render has to say so (§8).
    assert "UNCONFIRMED" in markdown


def test_a_services_catalog_becomes_one_positive_claim() -> None:
    """The dimension that makes an invented-service flag gradeable at all."""
    keys = _by_key(
        claims_from_json_ld(
            [
                {
                    "@type": "ProfessionalService",
                    "name": "Black Propeller",
                    "hasOfferCatalog": {
                        "@type": "OfferCatalog",
                        "itemListElement": [
                            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "Paid Search"}},
                            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "Paid Social"}},
                            {"@type": "Offer", "itemOffered": {"@type": "Service", "name": "SEO"}},
                        ],
                    },
                }
            ],
            _URL,
            _AS_OF,
        )
    )
    assert keys["services_offered"].value == "Services offered include Paid Search, Paid Social and SEO."


def test_the_services_claim_never_asserts_a_negative() -> None:
    """A services list is an OPEN enumeration (§4.4): naming three does not assert
    there is no fourth. Only hours may produce a closure, and only from a declared
    complete week."""
    claims = claims_from_json_ld(
        [
            {
                "@type": "ProfessionalService",
                "makesOffer": [{"@type": "Service", "name": "Paid Search"}],
            }
        ],
        _URL,
        _AS_OF,
    )
    services = [c for c in claims if c.key == "services_offered"]
    assert services and all(c.polarity is Polarity.POSITIVE for c in services)
    assert derive_negative_claims(claims) == []


def test_duplicate_service_names_collapse() -> None:
    keys = _by_key(
        claims_from_json_ld(
            [
                {
                    "@type": "ProfessionalService",
                    "makesOffer": [
                        {"@type": "Service", "name": "SEO"},
                        {"@type": "Service", "name": "seo"},
                        {"@type": "Service", "name": "Paid Search"},
                    ],
                }
            ],
            _URL,
            _AS_OF,
        )
    )
    assert keys["services_offered"].value == "Services offered include SEO and Paid Search."


def test_an_aggregate_rating_needs_both_numbers() -> None:
    # "4.8" from one review and from a thousand are different facts, so a partial
    # block yields nothing rather than half a claim.
    partial = _by_key(
        claims_from_json_ld(
            [{"@type": "Plumber", "aggregateRating": {"ratingValue": "4.8"}}], _URL, _AS_OF
        )
    )
    assert "presence_rating" not in partial

    full = _by_key(
        claims_from_json_ld(
            [
                {
                    "@type": "Plumber",
                    "aggregateRating": {"ratingValue": "4.8", "reviewCount": "126"},
                }
            ],
            _URL,
            _AS_OF,
        )
    )
    assert full["presence_rating"].value == "Rated 4.8/5 from 126 reviews."
