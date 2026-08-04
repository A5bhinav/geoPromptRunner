"""The free "how wrong is AI about you" scan (P5-T1).

The top of the funnel: 10–15 prompts across the two cheapest, most recognisable
surfaces, run once. It shows a **count** — "AI got something wrong about you in
6 of 15 checks" — plus one competitor comparison, and it gates *which* errors
behind a signup that routes into the existing manual lead queue.

Two things this module is careful about, both of which are ways a free tier
quietly becomes expensive or dishonest:

**Its own cost cap, far below the audit cap.** ``MAX_AUDIT_COST_USD`` (25) is a
per-client guard for work someone is paying for. An anonymous scan behind a form
has no such backstop, and 25 dollars per stranger is a denial-of-wallet waiting
to happen. :data:`MAX_FREE_SCAN_COST_USD` is a separate, much lower ceiling and
:func:`check_free_scan_cost` refuses before any call.

**Gating that actually gates.** The ungated payload carries the COUNT and
nothing that identifies a specific error: no claim text, no fact-sheet line, no
prompt, no engine. Sending the full findings and hiding them in the UI would put
the whole product behind a `display: none`, and the first person to open dev
tools would have the audit for free. :func:`gate_findings` builds the public
shape from scratch rather than redacting the private one, because redaction
leaves the original in the response.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

__all__ = [
    "MAX_FREE_SCAN_COST_USD",
    "FREE_SCAN_ENGINES",
    "FREE_SCAN_MAX_PROMPTS",
    "FreeScanTooExpensive",
    "PublicScanResult",
    "check_free_scan_cost",
    "gate_findings",
]

#: A hard ceiling per anonymous scan, and deliberately not derived from
#: ``MAX_AUDIT_COST_USD``. That cap protects a paying client's bill; this one
#: protects us from an unauthenticated form. Roughly one scan's worth of two
#: cheap surfaces over fifteen prompts, with headroom.
MAX_FREE_SCAN_COST_USD = 0.75

#: The two cheapest, most recognisable surfaces. Recognisable matters as much as
#: cheap: a stranger has to believe the answer came from something they use.
FREE_SCAN_ENGINES: tuple[str, ...] = ("openai", "perplexity")

#: The spec's 10–15. One run each — a free scan is a hook, not a measurement, and
#: repeat runs are what makes a rate trustworthy rather than what makes it exist.
FREE_SCAN_MAX_PROMPTS = 15
FREE_SCAN_RUNS_PER_QUERY = 1


class FreeScanTooExpensive(RuntimeError):
    """Refused before any engine call. The message is safe to show a visitor."""


class PublicScanResult(TypedDict):
    """What an anonymous visitor gets. Built from scratch, never redacted.

    Everything here is a COUNT or a name the visitor already gave us. There is no
    claim text, no prompt, no fact-sheet line and no per-engine breakdown —
    those are the product, and they arrive after the signup that routes into the
    lead queue.
    """

    client_name: str
    #: "6 of 15" — the count with its denominator, same rule as the paid report.
    checks_with_a_problem: int
    checks_run: int
    headline: str
    #: One competitor, by name, with the same count. Enough to be interesting,
    #: not enough to be the competitive section.
    competitor_name: str
    competitor_checks_with_a_problem: int
    #: How many findings are waiting behind the signup. A number, not the
    #: findings — "4 more" is a reason to sign up; the claims themselves are the
    #: thing being sold.
    findings_withheld: int
    next_step: str


@dataclass(frozen=True)
class ScanCostEstimate:
    """What a scan would cost, and whether it may run."""

    prompts: int
    engines: int
    estimated_usd: float

    @property
    def calls(self) -> int:
        return self.prompts * self.engines


def check_free_scan_cost(
    n_prompts: int,
    engines: Sequence[str],
    cost_per_call_usd: float,
    cap_usd: float = MAX_FREE_SCAN_COST_USD,
) -> ScanCostEstimate:
    """Estimate and refuse BEFORE spending. Raises :class:`FreeScanTooExpensive`.

    Checked ahead of the calls rather than tallied during them: an anonymous
    endpoint that discovers it overspent has already overspent, and the person
    who triggered it is not identifiable.
    """
    if n_prompts > FREE_SCAN_MAX_PROMPTS:
        raise FreeScanTooExpensive(
            f"a free scan runs at most {FREE_SCAN_MAX_PROMPTS} questions"
        )
    if len(engines) > len(FREE_SCAN_ENGINES):
        raise FreeScanTooExpensive(
            f"a free scan runs at most {len(FREE_SCAN_ENGINES)} surfaces"
        )
    estimate = ScanCostEstimate(
        prompts=n_prompts,
        engines=len(engines),
        estimated_usd=n_prompts * len(engines) * FREE_SCAN_RUNS_PER_QUERY * cost_per_call_usd,
    )
    if estimate.estimated_usd > cap_usd:
        raise FreeScanTooExpensive(
            f"this scan would cost about ${estimate.estimated_usd:.2f}, over the "
            f"${cap_usd:.2f} free-scan limit"
        )
    return estimate


def gate_findings(
    *,
    client_name: str,
    findings: Sequence[object],
    checks_run: int,
    checks_with_a_problem: int,
    competitor_name: str = "",
    competitor_checks_with_a_problem: int = 0,
    shown: int = 1,
) -> PublicScanResult:
    """The public payload. **Constructed, not filtered.**

    ``findings`` is taken only to be counted. Nothing from it is copied into the
    result — which is the difference between gating and hiding, and the reason
    this signature does not accept a "redact" flag. A payload that carries the
    claims and marks them private has already sent them.

    ``shown`` is how many findings the marketing page teases in prose written by
    a human elsewhere; it affects only the withheld COUNT.
    """
    withheld = max(0, len(findings) - max(0, shown))
    headline = (
        f"AI got something wrong about {client_name} in "
        f"{checks_with_a_problem} of {checks_run} checks."
        if checks_run
        else f"No surface returned an answer about {client_name}, so nothing could be checked."
    )
    return PublicScanResult(
        client_name=client_name,
        checks_with_a_problem=checks_with_a_problem,
        checks_run=checks_run,
        headline=headline,
        competitor_name=competitor_name,
        competitor_checks_with_a_problem=competitor_checks_with_a_problem,
        findings_withheld=withheld,
        next_step=(
            "See which claims were wrong, on which surfaces, with the exact "
            "questions asked."
        ),
    )


if __name__ == "__main__":
    estimate = check_free_scan_cost(15, FREE_SCAN_ENGINES, cost_per_call_usd=0.02)
    print(f"{estimate.calls} calls, about ${estimate.estimated_usd:.2f}")
    public = gate_findings(
        client_name="Fort",
        findings=[object()] * 6,
        checks_run=15,
        checks_with_a_problem=6,
        competitor_name="Whoop",
        competitor_checks_with_a_problem=2,
    )
    print(public["headline"], f"({public['findings_withheld']} withheld)")
