"""LIC-T4: entitlements resolve by capability, and slots enforce soft-then-hard."""

from __future__ import annotations

import pytest

from src.licensing.entitlements import (
    DEFAULT_PLAN_ID,
    GRACE_BAND,
    PLAN_ENTITLEMENTS,
    Entitlements,
    UnknownEntitlement,
    UnknownPlan,
    check_slot,
    resolve,
)


def test_the_two_plans_are_the_decided_ones() -> None:
    assert PLAN_ENTITLEMENTS["agency"].client_slots == 10
    assert PLAN_ENTITLEMENTS["agencyPro"].client_slots == 25
    # Two plans, deliberately. A third would mean a negotiated deal became a
    # plan name, which is the thing overrides exist to prevent.
    assert set(PLAN_ENTITLEMENTS) == {"agency", "agencyPro"}


def test_a_negotiated_deal_is_an_override_not_a_new_plan() -> None:
    """The acceptance criterion: 40 slots resolves WITHOUT touching the catalogue."""
    resolved = resolve("agency", {"client_slots": 40})
    assert resolved.client_slots == 40
    # The catalogue is untouched — no plan named for one customer, and no
    # mutation leaking into the next caller.
    assert PLAN_ENTITLEMENTS["agency"].client_slots == 10
    assert resolve("agency").client_slots == 10


def test_overrides_merge_rather_than_replace() -> None:
    resolved = resolve("agency", {"api_access": True})
    assert resolved.api_access is True          # overridden
    assert resolved.client_slots == 10          # inherited from the plan
    assert resolved.white_label_logo is True


def test_a_missing_plan_id_falls_back_rather_than_locking_the_owner_out() -> None:
    for empty in (None, ""):
        assert resolve(empty) == PLAN_ENTITLEMENTS[DEFAULT_PLAN_ID]


def test_an_unknown_plan_is_loud() -> None:
    with pytest.raises(UnknownPlan) as exc:
        resolve("enterprise-platinum")
    assert "agencyPro" in str(exc.value)  # names what IS known


def test_a_typo_in_an_override_key_raises_instead_of_doing_nothing() -> None:
    """A silently-ignored override looks exactly like a deal that was agreed,
    recorded, invoiced and never applied."""
    with pytest.raises(UnknownEntitlement) as exc:
        resolve("agency", {"clientSlots": 40})  # camelCase; canonical is snake
    assert "clientSlots" in str(exc.value)
    assert "client_slots" in str(exc.value)  # tells the caller the right key


def test_override_types_are_checked_not_trusted() -> None:
    """Overrides arrive from jsonb. `{"client_slots": "40"}` would otherwise
    compare as a string and make every slot check nonsense."""
    with pytest.raises(UnknownEntitlement):
        resolve("agency", {"client_slots": "40"})
    with pytest.raises(UnknownEntitlement):
        resolve("agency", {"client_slots": True})  # bool is an int in Python
    with pytest.raises(UnknownEntitlement):
        resolve("agency", {"api_access": 1})


# --- the slot band -----------------------------------------------------------

_TEN = Entitlements(client_slots=10, custom_domain=True, white_label_logo=True, api_access=False)


def test_at_or_below_the_limit_is_silent() -> None:
    for current in range(0, 10):
        verdict = check_slot(current, _TEN)
        assert verdict.allowed
        assert verdict.warning == ""


def test_slot_eleven_of_ten_is_allowed_with_a_warning() -> None:
    """Blocking a customer's business over a billing technicality costs more than
    the overage — so it goes through, and says so for the banner and the invoice."""
    verdict = check_slot(10, _TEN)
    assert verdict.allowed
    assert verdict.warning
    assert "11" in verdict.warning and "10" in verdict.warning
    assert verdict.would_be == 11


def test_slot_thirteen_of_ten_is_refused_with_the_limit_named() -> None:
    verdict = check_slot(12, _TEN)
    assert not verdict.allowed
    # The refusal has to name the resolved limit, or the agency cannot tell
    # whether they hit their own negotiated number or a default.
    assert "10" in verdict.warning
    assert "12" in verdict.warning  # the grace limit
    assert verdict.limit == 10 and verdict.grace_limit == 12


def test_the_band_edge_is_inclusive() -> None:
    """20% of 10 is 12, so client 12 is the LAST allowed one."""
    assert check_slot(11, _TEN).allowed        # would be client 12
    assert not check_slot(12, _TEN).allowed    # would be client 13
    assert GRACE_BAND == 0.20


def test_an_override_moves_the_band_with_the_limit() -> None:
    """The band is computed from the RESOLVED limit, not the plan's — otherwise a
    negotiated 40 slots would still refuse at 13."""
    forty = resolve("agency", {"client_slots": 40})
    assert check_slot(40, forty).allowed          # client 41, inside the band
    assert check_slot(47, forty).allowed          # client 48 == 40 * 1.2
    assert not check_slot(48, forty).allowed      # client 49


def test_a_zero_slot_plan_refuses_everything_past_the_band() -> None:
    """Guard against a 0 or negative override reading as 'unlimited'."""
    none_at_all = resolve("agency", {"client_slots": 0})
    verdict = check_slot(0, none_at_all)
    assert not verdict.allowed
