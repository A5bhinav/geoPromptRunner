from __future__ import annotations

import re

import pytest

from src.audit.factsheet import (
    BusinessKind,
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SheetStatus,
    SourceKind,
    Verification,
    expected_fact_sheet_text,
    to_csv,
    to_fact_rows,
    to_markdown,
)
from src.prompts.csv_loader import build_template_csv, parse_csv_files

# A markdown cell delimiter: a "|" that `render._cell` did not escape. The
# provenance quote is whatever the page said, so a literal "|" in it is normal.
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")

# A run file supplying everything a fact file deliberately does not: the audit
# cannot parse without `client_name`, `category`, at least one known engine and
# at least one query, so the round trip needs a partner file. That split is the
# point — facts merge in from their own file (csv_loader merges per block).
_RUN_CSV = """block,key,value,intent,persona
config,client_name,Fort Plumbing,,
config,category,plumbing contractor,,
config,engines,openai,,
query,q1,best plumber in Berkeley,category,homeowner
"""


def _claim(
    *,
    section: SheetSection = SheetSection.HOURS,
    key: str = "hours_sunday",
    value: str = "Closed Sunday.",
    polarity: Polarity = Polarity.NEGATIVE,
    verbatim_quote: str = "Sunday: Closed",
    source_url: str = "https://fortplumbing.example/contact",
    source_kind: SourceKind = SourceKind.SITE_JSONLD,
    as_of: str = "2026-07-31",
    verification: Verification = Verification.PUBLIC_SOURCE_ONLY,
    confidence: Confidence = Confidence.HIGH,
) -> FactClaim:
    return FactClaim(
        section=section,
        key=key,
        value=value,
        polarity=polarity,
        verbatim_quote=verbatim_quote,
        source_url=source_url,
        source_kind=source_kind,
        as_of=as_of,
        verification=verification,
        confidence=confidence,
    )


def _sheet(*claims: FactClaim, questions: list[str] | None = None) -> FactSheet:
    return FactSheet(
        domain="fortplumbing.example",
        business_name="Fort Plumbing",
        business_kind=BusinessKind.LOCAL_SERVICE,
        claims=list(claims),
        questions=questions or [],
        generated_at="2026-07-31T12:00:00Z",
        lead_ref="lead-7",
    )


def _local_sheet() -> FactSheet:
    return _sheet(
        _claim(
            section=SheetSection.SERVICE_AREA,
            key="service_area_towns",
            # The comma is load-bearing: it is what makes the CSV quoting real.
            value="Serves Berkeley, Albany and El Cerrito.",
            polarity=Polarity.POSITIVE,
            verbatim_quote="Areas served: Berkeley, Albany, El Cerrito",
        ),
        _claim(
            section=SheetSection.IDENTITY,
            key="identity_trade",
            value="Plumbing contractor serving the East Bay since 1998.",
            polarity=Polarity.POSITIVE,
            verbatim_quote="Family-owned plumbing contractor serving the East Bay since 1998",
            source_kind=SourceKind.SITE_TEXT,
        ),
        _claim(),
        _claim(
            section=SheetSection.CONTACT,
            key="contact_phone",
            value="Primary phone is (510) 555-0100.",
            polarity=Polarity.POSITIVE,
            verbatim_quote="Call us: (510) 555-0100",
            verification=Verification.CLIENT_CONFIRMED,
            source_kind=SourceKind.CLIENT,
        ),
    )


# --- the round trip: claims -> fact rows -> the real parser -> the judge's view ---


def test_fact_rows_round_trip_through_the_real_parser() -> None:
    sheet = _local_sheet()
    result = parse_csv_files([("run.csv", _RUN_CSV), ("facts.csv", to_csv(sheet))])
    assert result.ok, [e.message for e in result.errors]
    assert result.audit is not None
    assert result.audit.fact_sheet == expected_fact_sheet_text(sheet)


def test_round_trip_preserves_a_value_containing_a_comma() -> None:
    sheet = _local_sheet()
    result = parse_csv_files([("run.csv", _RUN_CSV), ("facts.csv", to_csv(sheet))])
    assert result.audit is not None
    assert "Serves Berkeley, Albany and El Cerrito." in result.audit.fact_sheet or ""
    assert len(result.audit.facts) == len(sheet.claims)


def test_fact_rows_are_shaped_for_the_platform_csv() -> None:
    rows = to_fact_rows(_local_sheet())
    assert all(block == "fact" for block, _k, _v, _i, _p in rows)
    # intent and persona are query columns; a fact row that fills them would
    # parse identically and mislead every human reading the file.
    assert all((intent, persona) == ("", "") for *_head, intent, persona in rows)


# The three Oura fact rows in `build_template_csv` are hand-written and pinned
# byte-for-byte by tests/test_consumer_path_regression.py. They are the only
# fact rows in the repo that predate this contract, which makes them a free
# oracle: the renderer has to reproduce exactly what they already produce.
_OURA_IDENTITY = "Smart ring for sleep/recovery; founded 2013 in Finland; CEO Tom Hale"
_OURA_PRICING = "Ring 5 $399 base / $499 premium + required $5.99/mo membership"
_OURA_FEATURES = (
    "Sleep stages, HRV, SpO2, temperature; Ring 5 shipped 2026, 40% smaller than Ring 4"
)


def test_renderer_reproduces_the_pinned_oura_fact_sheet() -> None:
    oura = FactSheet(
        domain="ouraring.com",
        business_name="Oura",
        business_kind=BusinessKind.PRODUCT,
        claims=[
            _claim(
                section=SheetSection.IDENTITY,
                key="identity",
                value=_OURA_IDENTITY,
                polarity=Polarity.POSITIVE,
                verbatim_quote=_OURA_IDENTITY,
            ),
            _claim(
                section=SheetSection.SERVICES_PRICING,
                key="pricing",
                value=_OURA_PRICING,
                polarity=Polarity.POSITIVE,
                verbatim_quote=_OURA_PRICING,
            ),
            _claim(
                section=SheetSection.SERVICES_PRICING,
                key="features",
                value=_OURA_FEATURES,
                polarity=Polarity.POSITIVE,
                verbatim_quote=_OURA_FEATURES,
            ),
        ],
        generated_at="2026-07-31T12:00:00Z",
    )
    pinned = parse_csv_files([("template.csv", build_template_csv())])
    assert pinned.audit is not None
    assert pinned.audit.fact_sheet == expected_fact_sheet_text(oura)


# --- validation (plan §2.1) ---


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("key", ""),
        ("key", "   "),
        ("value", ""),
        ("verbatim_quote", ""),
        ("value", "Closed Sunday.\nOpen Monday."),
        ("value", "Closed Sunday.\rOpen Monday."),
    ],
)
def test_degenerate_claims_are_rejected_at_construction(field_name: str, bad_value: str) -> None:
    with pytest.raises(ValueError):
        _claim(**{field_name: bad_value})


def test_a_valid_claim_still_constructs() -> None:
    assert _claim().key == "hours_sunday"


# --- claim ids ---


def test_claim_ids_are_stable_across_rebuilds() -> None:
    first = _local_sheet()
    first.assign_claim_ids()
    second = _local_sheet()
    second.assign_claim_ids()
    assert [c.claim_id for c in first.claims] == [c.claim_id for c in second.claims]
    assert [c.key for c in first.claims] == [c.key for c in second.claims]


def test_claim_ids_follow_section_order_then_insertion_order() -> None:
    sheet = _local_sheet()
    sheet.assign_claim_ids()
    assert [(c.claim_id, c.key) for c in sheet.claims] == [
        ("FS-01", "identity_trade"),
        ("FS-02", "contact_phone"),
        ("FS-03", "hours_sunday"),
        ("FS-04", "service_area_towns"),
    ]


def test_claim_ids_do_not_move_when_extraction_order_changes() -> None:
    """The ids key cached verdicts, so emission order must not perturb them."""
    forward = _local_sheet()
    backward = _sheet(*reversed(_local_sheet().claims))
    forward.assign_claim_ids()
    backward.assign_claim_ids()
    assert {c.claim_id: c.key for c in forward.claims} == {
        c.claim_id: c.key for c in backward.claims
    }


def test_assign_claim_ids_is_idempotent() -> None:
    sheet = _local_sheet()
    sheet.assign_claim_ids()
    once = list(sheet.claims)
    sheet.assign_claim_ids()
    assert sheet.claims == once


# --- verification tier ---


def test_verification_tier_is_the_weakest_claim() -> None:
    sheet = _sheet(
        _claim(verification=Verification.CLIENT_CONFIRMED),
        _claim(key="contact_phone", verification=Verification.CROSS_CONFIRMED),
        _claim(key="licence_number", verification=Verification.PUBLIC_SOURCE_ONLY),
    )
    assert sheet.verification_tier is Verification.PUBLIC_SOURCE_ONLY


def test_verification_tier_rises_only_when_every_claim_does() -> None:
    cross = _sheet(
        _claim(verification=Verification.CLIENT_CONFIRMED),
        _claim(key="contact_phone", verification=Verification.CROSS_CONFIRMED),
    )
    assert cross.verification_tier is Verification.CROSS_CONFIRMED
    confirmed = _sheet(
        _claim(verification=Verification.CLIENT_CONFIRMED),
        _claim(key="contact_phone", verification=Verification.CLIENT_CONFIRMED),
    )
    assert confirmed.verification_tier is Verification.CLIENT_CONFIRMED


def test_an_empty_sheet_reports_the_weakest_tier() -> None:
    assert _sheet().verification_tier is Verification.PUBLIC_SOURCE_ONLY


# --- markdown ---


def _claim_line(markdown: str, key: str) -> str:
    prefix = f"- **{key}:**"
    matches = [line for line in markdown.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1, f"expected exactly one line for {key!r}, got {matches}"
    return matches[0]


def test_markdown_marks_unconfirmed_claims_visibly() -> None:
    sheet = _local_sheet()
    sheet.sheet_status = SheetStatus.SIGNED
    markdown = to_markdown(sheet)
    # A signature must not launder provenance the client never gave (§8).
    assert "UNCONFIRMED" in _claim_line(markdown, "hours_sunday")
    assert "UNCONFIRMED" not in _claim_line(markdown, "contact_phone")
    assert "client-confirmed" in _claim_line(markdown, "contact_phone")
    assert "3 of 4 claims are NOT client-confirmed" in markdown


def test_markdown_uses_the_local_template_headings() -> None:
    markdown = to_markdown(_local_sheet())
    assert markdown.startswith("# Client Fact Sheet (LOCAL SERVICE) — Fort Plumbing")
    assert "## C · Hours & availability → `wrong_hours`" in markdown
    # Sections with no claims are omitted, not rendered empty (§4.2).
    assert "Licensing" not in markdown


def test_markdown_ends_with_the_provenance_appendix() -> None:
    sheet = _local_sheet()
    sheet.assign_claim_ids()
    markdown = to_markdown(sheet)
    assert "## Provenance appendix" in markdown
    assert "| claim_id | quote | source_url | as_of | verification |" in markdown
    for claim in sheet.claims:
        assert f"| {claim.claim_id} | {claim.verbatim_quote}" in markdown
    tail = markdown.strip().splitlines()[-1]
    assert tail.startswith("| FS-04 |")


def test_provenance_cells_survive_a_quote_containing_a_pipe() -> None:
    sheet = _sheet(_claim(verbatim_quote="Mon-Sat 8-5 | Sunday: Closed"))
    row = [ln for ln in to_markdown(sheet).splitlines() if ln.startswith("| FS-01 |")]
    assert len(row) == 1
    # The quote's own pipe is ESCAPED, so it is not a cell delimiter — the row
    # still has exactly 5 cells. Counting raw "|" would count the escape too and
    # report a broken table for the one case the escaping exists to fix.
    assert len(_UNESCAPED_PIPE.findall(row[0])) == 6
    assert r"Mon-Sat 8-5 \| Sunday: Closed" in row[0]


def test_markdown_lists_open_questions() -> None:
    sheet = _sheet(_claim(), questions=["Footer phone and GBP phone disagree — which is live?"])
    markdown = to_markdown(sheet)
    assert "## Open questions" in markdown
    assert "1. Footer phone and GBP phone disagree" in markdown


# --- derived run inputs (the "start from a lead" prefill) ---------------------


def test_suggested_inputs_read_the_business_and_domain_back_out() -> None:
    """The sheet was extracted from the business's own site, so a run form asking
    for its name and domain again is retyping data we already hold."""
    from src.audit.factsheet import suggested_run_inputs

    sheet = _sheet(
        _claim(
            section=SheetSection.CONTACT,
            key="contact_address",
            value="3465 Box Hill Drive - Suite 100, Abingdon, Maryland 21009",
            verbatim_quote="3465 Box Hill Drive - Suite 100, Abingdon, Maryland 21009",
            polarity=Polarity.POSITIVE,
        )
    )
    out = suggested_run_inputs(sheet)
    assert out["business"] == "Fort Plumbing"
    assert out["city"] == "Abingdon"
    assert out["region"] == "Maryland"


def test_a_two_letter_state_yields_no_region_rather_than_an_expansion() -> None:
    """Nothing here expands "MD" to "Maryland". The SERP vendors reject the short
    form and return an empty surface, which reads as the business being absent —
    so a blank field the human fills is the safe answer."""
    from src.audit.factsheet import suggested_run_inputs

    sheet = _sheet(
        _claim(
            section=SheetSection.SERVICE_AREA,
            key="service_area_primary",
            value="Abingdon, MD",
            verbatim_quote="Abingdon, MD",
            polarity=Polarity.POSITIVE,
        )
    )
    assert suggested_run_inputs(sheet)["region"] is None


def test_a_sheet_with_no_address_suggests_no_city() -> None:
    from src.audit.factsheet import suggested_run_inputs

    out = suggested_run_inputs(_sheet(_claim()))
    assert out["city"] is None and out["region"] is None
    assert out["business"] == "Fort Plumbing"
