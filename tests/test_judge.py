from __future__ import annotations

from src.pipeline.judge import (
    AccuracyFlagType,
    Framing,
    Prominence,
    Severity,
    _parse_brands,
    _parse_flags,
)


def test_parse_brands_fills_missing_and_coerces() -> None:
    raw = {
        "brands": [
            {
                "brand": "YNAB",
                "present": True,
                "prominence": "recommended_first",
                "framing": "positive",
            },
            {"brand": "Centsible", "present": True, "prominence": "buried", "framing": "bogus"},
        ]
    }
    brands = _parse_brands(raw, client="Centsible", competitors=["YNAB", "Rocket Money"])
    by = {b.brand: b for b in brands}

    # Client + every competitor is always present in the output (order: client first).
    assert [b.brand for b in brands] == ["Centsible", "YNAB", "Rocket Money"]
    assert by["YNAB"].prominence == Prominence.RECOMMENDED_FIRST.value
    # Unknown framing coerces to neutral.
    assert by["Centsible"].framing == Framing.NEUTRAL.value
    # Brand the judge omitted -> filled as absent / not present / neutral.
    assert by["Rocket Money"].present is False
    assert by["Rocket Money"].prominence == Prominence.ABSENT.value


def test_present_false_forces_absent_prominence() -> None:
    raw = {
        "brands": [{"brand": "X", "present": False, "prominence": "mid_pack", "framing": "neutral"}]
    }
    brands = _parse_brands(raw, client="X", competitors=[])
    assert brands[0].prominence == Prominence.ABSENT.value


def test_parse_flags_filters_invalid() -> None:
    raw = {
        "client_accuracy_flags": [
            {
                "type": "wrong_pricing",
                "claim": "$20/mo",
                "reality": "free + $5/mo",
                "severity": "high",
            },
            {"type": "not_a_real_type", "claim": "x", "reality": "y", "severity": "low"},  # dropped
            {
                "type": "stale",
                "claim": "",
                "reality": "",
                "severity": "low",
            },  # nothing checkable -> dropped
            {
                "type": "identity",
                "claim": "owned by Intuit",
                "reality": "independent",
            },  # severity defaults
        ]
    }
    flags = _parse_flags(raw)
    assert len(flags) == 2
    assert flags[0].type == AccuracyFlagType.WRONG_PRICING.value
    assert flags[1].type == AccuracyFlagType.IDENTITY.value
    assert flags[1].severity == Severity.MED.value  # default when omitted


def test_parse_flags_handles_missing_key() -> None:
    assert _parse_flags({}) == []
