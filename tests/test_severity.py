"""The four-level severity scale (audit-packaging P0-T2).

The escalation rule is a table, deliberately, so it can be argued with and
re-run over already-stored runs. These tests are that table.
"""

from __future__ import annotations

import pytest

from src.pipeline.severity import (
    CRITICAL_TYPES,
    SEVERITY_ORDER,
    escalate,
    sort_key,
    worst,
)
from src.storage.models import AccuracyFlagType, Severity


def test_the_scale_has_four_levels_in_the_only_legal_order() -> None:
    assert SEVERITY_ORDER == ("critical", "high", "med", "low")
    assert set(SEVERITY_ORDER) == {s.value for s in Severity}


@pytest.mark.parametrize(
    ("flag_type", "severity", "claim", "expected"),
    [
        # --- escalates: category/identity, or a purchase decision ---
        ("identity", "high", "Fort is a pickleball scoring app.", "critical"),
        ("identity", "high", "There isn't a brand called Fort.", "critical"),
        ("wrong_pricing", "high", "The Fort band costs $349.", "critical"),
        ("wrong_contact", "high", "Their number is 510-234-9981.", "critical"),
        ("stale", "high", "The Fort band is already shipping.", "critical"),
        ("stale", "high", "The business is permanently closed.", "critical"),
        # --- stays high: a misstated capability is serious, not category-level ---
        ("missing_or_invented_feature", "high", "It measures blood pressure.", "high"),
        ("competitor_confusion", "high", "It's just a Whoop clone.", "high"),
        ("stale", "high", "Fort launched relatively recently.", "high"),
        # --- med and low never escalate, whatever the type ---
        ("identity", "med", "Fort is a pickleball app.", "med"),
        ("wrong_pricing", "low", "Pricing is roughly $300.", "low"),
        ("wrong_contact", "med", "The address is imprecise.", "med"),
    ],
)
def test_escalation_matrix(flag_type: str, severity: str, claim: str, expected: str) -> None:
    assert escalate(flag_type, severity, claim) == expected


def test_escalation_is_idempotent() -> None:
    """Safe to call at every layer, which is why it is called at every layer."""
    once = escalate("identity", "high", "Fort is a pickleball app.")
    assert escalate("identity", once, "Fort is a pickleball app.") == once == "critical"


def test_an_unrecognized_severity_passes_through_rather_than_being_coerced() -> None:
    assert escalate("identity", "catastrophic", "anything") == "catastrophic"


def test_every_flag_type_is_classifiable_and_critical_types_are_the_documented_three() -> None:
    for t in AccuracyFlagType:
        assert escalate(t.value, "high", "") in SEVERITY_ORDER
    assert CRITICAL_TYPES == {"identity", "wrong_pricing", "wrong_contact"}


def test_worst_of_a_group_and_the_empty_case() -> None:
    assert worst(["low", "critical", "med"]) == "critical"
    assert worst(["med", "low"]) == "med"
    assert worst([]) == "low"


def test_unknown_severities_sort_last_and_never_become_a_headline() -> None:
    assert sort_key("critical") < sort_key("low") < sort_key("bogus")
    assert worst(["bogus", "med"]) == "med"
