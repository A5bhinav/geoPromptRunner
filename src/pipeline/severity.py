"""The four-level severity scale, and the pure classifier that produces it.

The judge emits three levels (``high``/``med``/``low``). The packaged report needs
a fourth so the top of page 1 can say *"3 Critical"* rather than burying a pricing
error among forty mediums — today ``high`` covers both "the model thinks you are a
pickleball app" and "minor feature overstatement"
(``docs/audit-packaging-spec.md`` P0-T2).

**Critical is derived, never judged.** Adding a value to the judge's tool schema
would change the prompt fingerprint and invalidate every cached verdict. Deriving
it here costs nothing, is free to re-run over already-stored runs, and — the real
reason — is *testable*: the escalation rule is a table you can read, not a model's
opinion that varies by call.

Colour lives in the token layer, not here. The ramp is monochrome navy, darkest =
most severe (``web/styles/sable.css``); Sable has no red and no gold, so an icon
and a label on every tier are load-bearing rather than belt-and-braces.
"""

from __future__ import annotations

import re

from src.storage.models import AccuracyFlagType, Severity

__all__ = [
    "SEVERITY_ORDER",
    "SEVERITY_RANK",
    "CRITICAL_TYPES",
    "escalate",
    "worst",
    "sort_key",
]

#: Display order, always. Never chronological, never alphabetical — a reader who
#: stops after the first row must have seen the worst thing in the report.
SEVERITY_ORDER: tuple[str, ...] = (
    Severity.CRITICAL.value,
    Severity.HIGH.value,
    Severity.MED.value,
    Severity.LOW.value,
)

#: Lower rank = more severe, so ``min`` and ``sorted`` do the obvious thing.
SEVERITY_RANK: dict[str, int] = {s: i for i, s in enumerate(SEVERITY_ORDER)}

#: Flag types whose *high* verdicts are category/identity or purchase-decision
#: errors by construction, and therefore escalate.
#:
#: - ``identity`` — being mistaken for another company is the category error the
#:   Critical tier exists for.
#: - ``wrong_pricing`` — a price a buyer acts on.
#: - ``wrong_contact`` — a wrong phone number or address routes a paying customer
#:   to nobody. On the local path this is the single most expensive error the
#:   models make, and it is exactly "materially changes a purchase decision".
CRITICAL_TYPES: frozenset[str] = frozenset(
    {
        AccuracyFlagType.IDENTITY.value,
        AccuracyFlagType.WRONG_PRICING.value,
        AccuracyFlagType.WRONG_CONTACT.value,
    }
)

#: Availability language inside a non-identity flag. "Already shipping" about a
#: pre-launch product changes a purchase decision as surely as a wrong price does,
#: and the judge routinely files it under `stale` rather than `identity`.
_AVAILABILITY_RE = re.compile(
    r"\b(?:already (?:shipping|available)|(?:is|are|now) (?:shipping|available|on sale)|"
    r"in stock|out of business|(?:permanently |now )?closed|discontinued|shut down|"
    r"no longer (?:operating|available|in business))\b",
    re.IGNORECASE,
)


def escalate(flag_type: str, severity: str, claim: str = "") -> str:
    """Map a judged severity onto the four-level scale. Pure and idempotent.

    Only ``high`` can escalate, and only on the triggers above; everything else
    passes through unchanged. An already-``critical`` input stays critical, so
    re-running this over a payload that has been through it once is a no-op —
    which is what makes it safe to call at every layer rather than exactly once.

    An unrecognized severity is returned verbatim rather than coerced: silently
    rewriting a value we do not understand is how a report starts asserting
    severities nobody assigned.
    """
    if severity == Severity.CRITICAL.value:
        return severity
    if severity != Severity.HIGH.value:
        return severity
    if flag_type in CRITICAL_TYPES:
        return Severity.CRITICAL.value
    if _AVAILABILITY_RE.search(claim):
        return Severity.CRITICAL.value
    return Severity.HIGH.value


def worst(severities: list[str]) -> str:
    """The most severe of a group. Empty input -> ``low`` (nothing to alarm about).

    Unknown values sort last, so a stray severity can never quietly become a
    group's headline.
    """
    if not severities:
        return Severity.LOW.value
    return min(severities, key=lambda s: SEVERITY_RANK.get(s, len(SEVERITY_ORDER)))


def sort_key(severity: str) -> int:
    """Rank for ordering. Unknown values sort after every known tier."""
    return SEVERITY_RANK.get(severity, len(SEVERITY_ORDER))


if __name__ == "__main__":
    cases = [
        ("identity", "high", "Fort is a pickleball scoring app."),
        ("wrong_pricing", "high", "The Fort band costs $349."),
        ("stale", "high", "The Fort band is already shipping."),
        ("stale", "high", "Fort launched relatively recently."),
        ("missing_or_invented_feature", "high", "It measures blood pressure."),
        ("missing_or_invented_feature", "med", "No Android app."),
    ]
    for t, s, c in cases:
        print(f"{escalate(t, s, c):9s}  <- {s:5s} {t:28s} {c}")
