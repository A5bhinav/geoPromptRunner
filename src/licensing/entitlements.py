"""What a plan grants, and what happens when an agency exceeds it (LIC-T4).

**Check by capability, never by plan name.** ``if org.plan == "pro"`` scattered
through handlers is the anti-pattern this module exists to prevent: adding a
plan, renaming one, or giving one agency a negotiated limit then means hunting
every check. Handlers ask ``resolve(...).client_slots``, never which plan it was.

**A negotiated deal is an override, never a new plan name.** The plans stay
``agency`` (10 slots) and ``agencyPro`` (25); an agency's real slot count lives in
`organizations.entitlement_overrides`, merged over the plan at read time.

**The frontend gate is UX; this is the boundary.** `web/` may hide the "add
client" button, but the check that matters runs at the API before the INSERT,
because a hidden button is not an access control.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any

__all__ = [
    "Entitlements",
    "PLAN_ENTITLEMENTS",
    "DEFAULT_PLAN_ID",
    "GRACE_BAND",
    "SlotVerdict",
    "UnknownEntitlement",
    "UnknownPlan",
    "resolve",
    "check_slot",
]


@dataclass(frozen=True)
class Entitlements:
    """One resolved answer to "what may this organization do?".

    Frozen because an entitlement set that a handler can mutate is an entitlement
    set that a handler will mutate.
    """

    #: How many client companies this agency may manage.
    client_slots: int
    #: Reserved for the white-label work `docs/licensing-spec.md` puts out of
    #: scope until the second agency arrives. Present so the capability EXISTS to
    #: check against — a handler asking `custom_domain` today gets a truthful
    #: False rather than a NameError, and the feature lands without touching this
    #: module's shape.
    custom_domain: bool
    white_label_logo: bool
    api_access: bool


#: The catalogue. Two plans, deliberately. Retained from design §5.3 by the
#: 2026-08-05 decision, which chose overrides over new plan names.
PLAN_ENTITLEMENTS: dict[str, Entitlements] = {
    "agency": Entitlements(
        client_slots=10, custom_domain=True, white_label_logo=True, api_access=False
    ),
    "agencyPro": Entitlements(
        client_slots=25, custom_domain=True, white_label_logo=True, api_access=True
    ),
}

DEFAULT_PLAN_ID = "agency"

#: How far past the limit an agency may go before the API refuses. 20%.
#:
#: DEPARTURE FROM design §5.2, deliberate and called out in the spec. The design
#: says enforcement should be a soft warning only — "blocking slot creation risks
#: blocking your customer's business over a billing technicality". That reasoning
#: is right about the paying agency's own growth and wrong about an unbounded
#: limit, since every slot is real spend on OUR vendor keys. So: silent at or
#: below the limit, allowed-with-a-warning inside the band (the banner and the
#: invoice reconciliation both read that warning), refused beyond it.
GRACE_BAND = 0.20


class UnknownPlan(ValueError):
    """A plan id that is not in the catalogue."""


class UnknownEntitlement(ValueError):
    """An override key that names no capability.

    Loud on purpose. A typo'd override key that silently did nothing would look
    exactly like a negotiated deal that was agreed, recorded, invoiced — and never
    actually applied. The agency would hit the un-negotiated limit and nothing in
    the system would explain why.
    """


def _known_keys() -> frozenset[str]:
    return frozenset(f.name for f in fields(Entitlements))


def resolve(plan_id: str | None, overrides: dict[str, Any] | None = None) -> Entitlements:
    """The entitlements for a plan, with any negotiated overrides merged over it.

    ``plan_id`` of None/"" resolves to the default plan rather than raising: an
    organization row written before `plan_id` had a default is an operational
    accident, and locking its owner out of their own console is a worse answer
    than giving them the base plan.
    """
    base = PLAN_ENTITLEMENTS.get(plan_id or DEFAULT_PLAN_ID)
    if base is None:
        raise UnknownPlan(
            f"unknown plan {plan_id!r}; known plans: {sorted(PLAN_ENTITLEMENTS)}"
        )
    if not overrides:
        return base

    unknown = set(overrides) - _known_keys()
    if unknown:
        raise UnknownEntitlement(
            f"unknown entitlement override(s): {sorted(unknown)}; "
            f"known capabilities: {sorted(_known_keys())}"
        )
    # Types are checked here rather than trusted from jsonb: `{"client_slots":
    # "40"}` would otherwise compare as a string and make every slot check
    # nonsense.
    typed: dict[str, Any] = {}
    for key, value in overrides.items():
        expected = {f.name: f.type for f in fields(Entitlements)}[key]
        if expected is int or expected == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise UnknownEntitlement(f"override {key!r} must be an int, got {value!r}")
        elif not isinstance(value, bool):
            raise UnknownEntitlement(f"override {key!r} must be a bool, got {value!r}")
        typed[key] = value
    return replace(base, **typed)


@dataclass(frozen=True)
class SlotVerdict:
    """The answer to "may this agency add one more client company?"."""

    allowed: bool
    #: Set whenever the agency is over its limit — inside the band (allowed) or
    #: beyond it (refused). The banner shows it; the refusal message is it.
    warning: str
    limit: int
    grace_limit: int
    #: Company count AFTER the add this verdict is about.
    would_be: int


def check_slot(current_count: int, entitlements: Entitlements) -> SlotVerdict:
    """Whether one more client company may be added, given the current count.

    ``current_count`` is what the agency manages NOW; the verdict is about the
    company that would be number ``current_count + 1``. Counted live at the API
    (`db.count_companies_for_agency`) rather than cached, because a stale count
    either blocks a customer who is under their limit or admits one who is over.
    """
    limit = max(0, entitlements.client_slots)
    grace_limit = int(limit * (1 + GRACE_BAND))
    would_be = current_count + 1

    if would_be <= limit:
        return SlotVerdict(True, "", limit, grace_limit, would_be)

    if would_be <= grace_limit:
        return SlotVerdict(
            True,
            f"over the plan limit: this is client {would_be} of {limit} included. "
            f"Allowed within the {int(GRACE_BAND * 100)}% grace band "
            f"(up to {grace_limit}); the overage will appear on the next invoice.",
            limit,
            grace_limit,
            would_be,
        )

    return SlotVerdict(
        False,
        f"client slot limit reached: {limit} included, {grace_limit} with the "
        f"{int(GRACE_BAND * 100)}% grace band, and this would be client {would_be}. "
        f"Raise the limit with an entitlement override on the organization.",
        limit,
        grace_limit,
        would_be,
    )
