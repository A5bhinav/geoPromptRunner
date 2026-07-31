"""§8's send-permission table, and the ways it could silently over-permit.

Every test here is about the same asymmetry: a flag wrongly WITHHELD costs a
finding, a flag wrongly SENT is a false accusation in a document we mailed a
stranger. So the interesting assertions are all on the deny side.
"""

from __future__ import annotations

import pytest

from src.audit.factsheet import BusinessKind, FactSheet, Verification
from src.audit.factsheet.gate import SENDABLE_SEVERITIES, may_send_flag, sendable_flags
from src.storage.models import AccuracyFlag, Severity


def _flag(severity: str, *, claim: str = "closes at 5pm") -> AccuracyFlag:
    return AccuracyFlag(
        type="wrong_hours", claim=claim, reality="Open until 7pm.", severity=severity
    )


def _sheet(*claims: object, tier: Verification = Verification.PUBLIC_SOURCE_ONLY) -> FactSheet:
    del claims, tier  # an empty sheet reports the weakest tier by construction
    return FactSheet(
        domain="fortplumbing.example",
        business_name="Fort Plumbing",
        business_kind=BusinessKind.LOCAL_SERVICE,
        generated_at="2026-07-31T00:00:00+00:00",
    )


# --- the table itself ---------------------------------------------------------


def test_unconfirmed_sheet_may_send_low_and_med() -> None:
    for severity in (Severity.LOW, Severity.MED):
        assert may_send_flag(Verification.PUBLIC_SOURCE_ONLY, severity.value)


def test_unconfirmed_sheet_may_not_send_high() -> None:
    # The whole point of the gate: one public source is not enough to accuse a
    # named vendor of a decision-changing error in cold outreach.
    assert not may_send_flag(Verification.PUBLIC_SOURCE_ONLY, Severity.HIGH.value)


def test_corroborated_and_confirmed_sheets_may_send_any_known_severity() -> None:
    for tier in (Verification.CROSS_CONFIRMED, Verification.CLIENT_CONFIRMED):
        for severity in Severity:
            assert may_send_flag(tier, severity.value)


def test_every_tier_has_a_policy() -> None:
    # A tier missing from the table would KeyError at send time, in the one code
    # path where an exception is worst. Adding a Verification member must fail
    # here, not in production.
    assert set(SENDABLE_SEVERITIES) == set(Verification)


# --- the ways it could over-permit --------------------------------------------


@pytest.mark.parametrize("severity", ["critical", "CRITICAL", "", "urgent", "high ", "None"])
def test_an_unrecognised_severity_is_refused_everywhere(severity: str) -> None:
    """Refuse rather than coerce — including for the CRITICAL tier P0-T2 adds.

    An unknown severity is not evidence a flag is harmless. If this ever returns
    True for "critical", the audit-packaging spec's new top tier ships to
    strangers off an unconfirmed sheet on the day it lands.
    """
    for tier in Verification:
        assert not may_send_flag(tier, severity)


def test_severity_matching_is_not_case_insensitive_by_accident() -> None:
    # Severity values are lowercase; a stored "High" is a data bug, and treating
    # it as HIGH would let an unconfirmed sheet send it.
    assert not may_send_flag(Verification.PUBLIC_SOURCE_ONLY, "High")


# --- filtering ----------------------------------------------------------------


def test_sendable_flags_drops_high_from_an_unconfirmed_sheet() -> None:
    flags = [_flag("low"), _flag("high", claim="wrong phone"), _flag("med")]
    kept = sendable_flags(flags, Verification.PUBLIC_SOURCE_ONLY)
    assert [f.severity for f in kept] == ["low", "med"]
    # Suppressed, never downgraded: the high flag is gone, not relabelled.
    assert all(f.claim != "wrong phone" for f in kept)


def test_sendable_flags_keeps_everything_once_the_client_confirms() -> None:
    flags = [_flag("low"), _flag("high"), _flag("med")]
    assert len(sendable_flags(flags, Verification.CLIENT_CONFIRMED)) == 3


def test_sendable_flags_accepts_a_custom_severity_reader() -> None:
    # The report payload's FlagRow is a dict-shaped mirror of AccuracyFlag; the
    # policy must not be duplicated for it.
    rows = [{"severity": "low"}, {"severity": "high"}]
    kept = sendable_flags(
        rows, Verification.PUBLIC_SOURCE_ONLY, severity_of=lambda r: str(r["severity"])
    )
    assert kept == [{"severity": "low"}]


def test_an_empty_sheet_gates_at_the_weakest_tier() -> None:
    """A sheet that has vouched for nothing must not license a high-severity send."""
    sheet = _sheet()
    assert sheet.verification_tier is Verification.PUBLIC_SOURCE_ONLY
    assert not may_send_flag(sheet.verification_tier, Severity.HIGH.value)
