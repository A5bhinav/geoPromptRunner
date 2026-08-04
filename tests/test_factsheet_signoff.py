"""P5-T2 — the fact sheet as a signed, client-facing artifact.

The spec's own test: "editing the sheet produces a different cache key and
surfaces the warning."

The reason it matters twice over: the sheet is the ground truth behind every
accuracy finding, AND it is in the judge cache key. So an edit is simultaneously
a change to what counts as an error and a bill for re-judging everything — and
both facts have to reach the person clicking Save before they click it.
"""

from __future__ import annotations

import dataclasses
import hashlib

from src.audit.factsheet import (
    BusinessKind,
    Confidence,
    FactClaim,
    FactSheet,
    Polarity,
    SheetSection,
    SourceKind,
    Verification,
    expected_fact_sheet_text,
)
from src.audit.factsheet.signoff import (
    SignoffRecord,
    cache_impact,
    changelog_between,
    may_run_without_signoff,
    to_client_markdown,
)

# The private key builder, on purpose. This test asserts a property of the REAL
# cache key rather than of a re-implementation — a parallel hash here could agree
# with itself forever while the cache disagreed.
from src.pipeline.judge_cache import _verdict_key


def _claim(
    key: str = "pricing_callout",
    value: str = "Free estimates on all residential jobs.",
    verification: Verification = Verification.CLIENT_CONFIRMED,
) -> FactClaim:
    return FactClaim(
        section=SheetSection.IDENTITY,
        key=key,
        value=value,
        polarity=Polarity.POSITIVE,
        verbatim_quote=value,
        source_url="https://fortplumbing.example/pricing",
        source_kind=SourceKind.SITE_JSONLD,
        as_of="2026-07-31",
        verification=verification,
        confidence=Confidence.HIGH,
    )


def _sheet(*claims: FactClaim, version: int = 1, questions: list[str] | None = None) -> FactSheet:
    return FactSheet(
        domain="fortplumbing.example",
        business_name="Fort Plumbing",
        business_kind=BusinessKind.LOCAL_SERVICE,
        claims=list(claims) or [_claim()],
        questions=questions or [],
        generated_at="2026-07-31T12:00:00Z",
        version=version,
    )


def _signature(sheet: FactSheet, who: str = "Dana Reyes") -> SignoffRecord:
    return SignoffRecord(
        sheet_version=sheet.version,
        signed_text_sha256=hashlib.sha256(
            expected_fact_sheet_text(sheet).encode("utf-8")
        ).hexdigest(),
        signed_by=who,
        signed_role="Owner",
        signed_at="2026-08-01",
    )


# --- the cache-key half -------------------------------------------------------


def test_editing_the_sheet_produces_a_different_judge_cache_key() -> None:
    """The spec's test. A verdict reached against different ground truth is a
    different verdict, so the cache must miss — and it does."""
    before = _sheet(_claim(value="Free estimates on all residential jobs."))
    after = _sheet(_claim(value="Free estimates on residential jobs under $5,000."))

    key_before = _verdict_key(
        model="claude-sonnet-4-5",
        prompt_fingerprint="fp",
        client="Fort Plumbing",
        competitors=["Rival"],
        fact_sheet=expected_fact_sheet_text(before),
        prompt="best plumber in Berkeley",
        answer="Fort Plumbing offers free estimates.",
    )
    key_after = _verdict_key(
        model="claude-sonnet-4-5",
        prompt_fingerprint="fp",
        client="Fort Plumbing",
        competitors=["Rival"],
        fact_sheet=expected_fact_sheet_text(after),
        prompt="best plumber in Berkeley",
        answer="Fort Plumbing offers free estimates.",
    )
    assert key_before != key_after


def test_the_warning_is_surfaced_before_saving() -> None:
    before = _sheet(_claim(value="Free estimates on all residential jobs."))
    after = _sheet(_claim(value="Free estimates on residential jobs under $5,000."))

    impact = cache_impact(before, after)
    assert impact["invalidates_cache"] is True
    assert impact["changed_claims"] == 1
    assert impact["before_key_fragment"] != impact["after_key_fragment"]
    # The warning has to say what it costs, not just that something happened.
    assert "cached verdict" in impact["warning"]
    assert "charged" in impact["warning"]


def test_the_warning_says_past_reports_are_unaffected() -> None:
    """Storage is create-only and a stored run keeps the sheet it was measured
    against. A client who fears an edit rewrites their history will not edit."""
    impact = cache_impact(_sheet(_claim(value="a")), _sheet(_claim(value="b")))
    assert "Past reports are unaffected" in impact["warning"]


def test_an_edit_the_judge_cannot_see_invalidates_nothing() -> None:
    """Provenance quotes, source URLs and open questions never reach the judge.

    A hash over the whole sheet object would report a fixed typo in a source URL
    as a measurement change, and charge for it.
    """
    before = _sheet(_claim(), questions=["What is your after-hours policy?"])
    after = _sheet(_claim(), questions=["What is your after-hours callout policy?"])
    impact = cache_impact(before, after)
    assert impact["invalidates_cache"] is False
    assert impact["warning"] == ""


# --- the changelog ------------------------------------------------------------


def test_the_changelog_names_what_moved() -> None:
    """"We changed your fact sheet" with no diff is the same failure as
    retro-adjusting a prior cycle's numbers."""
    before = _sheet(_claim("pricing_callout", "Free estimates."), _claim("hours_sunday", "Closed."))
    after = _sheet(
        _claim("pricing_callout", "Free estimates under $5,000."),
        _claim("service_area", "Berkeley and Albany."),
    )
    entries = changelog_between(before, after)
    by_kind = {e["kind"]: e for e in entries}

    assert by_kind["changed"]["key"] == "pricing_callout"
    assert by_kind["changed"]["before"] == "Free estimates."
    assert by_kind["removed"]["key"] == "hours_sunday"
    assert by_kind["added"]["key"] == "service_area"


def test_a_re_extraction_does_not_report_everything_as_changed() -> None:
    """Claim ids are minted per extraction; keying the diff on them would make a
    re-extracted sheet report every line as removed-and-added, and a diff that
    says everything changed says nothing."""
    before = _sheet(_claim())
    after = _sheet(dataclasses.replace(_claim(), as_of="2026-08-04"))
    assert changelog_between(before, after) == []


# --- the client artifact ------------------------------------------------------


def test_the_client_render_leaks_no_internal_vocabulary() -> None:
    """Built from the claims, not redacted from the internal document — a
    redacted file still contains the redacted thing."""
    sheet = _sheet(_claim(verification=Verification.PUBLIC_SOURCE_ONLY))
    rendered = to_client_markdown(sheet)
    for internal in ("claim_id", "§", "verbatim_quote", "source_kind", "public_source_only"):
        assert internal not in rendered
    assert "Provenance appendix" not in rendered


def test_the_client_render_says_which_lines_are_unconfirmed() -> None:
    """A signature covers only the lines the owner vouched for."""
    sheet = _sheet(_claim(verification=Verification.PUBLIC_SOURCE_ONLY))
    rendered = to_client_markdown(sheet)
    assert "needs your confirmation" in rendered


def test_a_confirmed_sheet_carries_no_confirmation_nag() -> None:
    rendered = to_client_markdown(_sheet(_claim(verification=Verification.CLIENT_CONFIRMED)))
    assert "needs your confirmation" not in rendered


def test_the_artifact_is_titled_as_a_version() -> None:
    assert "Brand Fact Sheet v2.0" in to_client_markdown(_sheet(version=2))


def test_a_signature_that_no_longer_describes_the_sheet_is_flagged() -> None:
    """A stale signature is worse than none: it looks like assurance and is not."""
    original = _sheet(_claim(value="Free estimates."))
    signature = _signature(original)
    edited = _sheet(_claim(value="Free estimates under $5,000."))

    assert signature.covers(original) is True
    assert signature.covers(edited) is False
    rendered = to_client_markdown(edited, signoff=signature)
    assert "needs to be signed again" in rendered


def test_a_current_signature_is_named_on_the_artifact() -> None:
    sheet = _sheet()
    rendered = to_client_markdown(sheet, signoff=_signature(sheet))
    assert "Signed off by Dana Reyes (Owner)" in rendered


def test_an_unsigned_sheet_asks_for_a_signature() -> None:
    assert "Not yet signed off" in to_client_markdown(_sheet())


# --- the sign-off gate --------------------------------------------------------


def test_a_first_run_needs_a_current_signature() -> None:
    """The findings a fact sheet produces are assertions that a named vendor's
    model said something untrue about a company. Making that assertion against
    ground truth nobody at the company confirmed is the one place this product
    could be badly wrong in public."""
    sheet = _sheet()
    assert may_run_without_signoff(sheet, None) is False
    assert may_run_without_signoff(sheet, _signature(sheet)) is True


def test_a_signature_does_not_survive_an_edit() -> None:
    signature = _signature(_sheet(_claim(value="a")))
    assert may_run_without_signoff(_sheet(_claim(value="b")), signature) is False
