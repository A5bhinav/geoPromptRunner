"""Per-trade sampling bands for local audits (W5.1).

How many times must a local query be repeated before its result means anything?

The consumer default was measured before it was set: the 2026-06-19 determinism baseline
found the brand READ is 100% stable on openai/anthropic but wobbles to ~60% worst-brand
on gemini/perplexity, which argued for K=5. (Re-measured 2026-07-28 on one category
query: openai and anthropic both floor at 60% worst-brand too — the "100% stable" half of
that finding did not reproduce.) It was nonetheless lowered to **K=3 on 2026-08-01** as a
deliberate cost/breadth trade, spending the saved cells on more queries instead; the
measurements above were not refuted. See ``settings.DEFAULT_RUNS_PER_QUERY`` for the full
reasoning — the fallback band below inherits whatever that default is. Local is noisier
still — SE
Ranking measured roughly 80% of URLs and >60% of domains swapping between repeat runs
of "near me" queries — and the noise is not uniform across trades or intents.

**This module deliberately ships with NO invented numbers.** Every band here must come
from ``geo verify determinism`` against that trade's real query set, and carries the
date and measurement it came from. Until a trade is measured, it falls back to the
global default and ``is_measured`` is False — so a report can say "sampling band not
yet established for this trade" instead of implying a rigour that does not exist.

That is the same discipline as the accuracy freeze: an unmeasured number is not a
conservative number, it is an unknown one.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import settings
from src.prompts.intent import IntentBucket

__all__ = [
    "TradeSamplingBand",
    "SAMPLING_BANDS",
    "band_for",
    "runs_for_trade",
    "NEAR_ME_NOISE_MULTIPLIER",
    "is_near_me",
    "sampling_note",
    "local_cadence_warning",
]

# SE Ranking's finding, kept as a documented constant rather than folded into a band:
# "near me" phrasings were roughly 2x less stable than the equivalent explicit-city
# query. The trade query sets already prefer explicit-city phrasing and tag the
# "near me" variants as a separate, noisier cohort (data/queries_*.json) — this
# constant is what a future band computation should multiply by, NOT a fudge factor to
# apply to a measured number after the fact.
NEAR_ME_NOISE_MULTIPLIER = 2.0


def is_near_me(query_text: str) -> bool:
    """Whether a query is in the noisier 'near me' cohort rather than explicit-city."""
    return "near me" in query_text.lower()


@dataclass(frozen=True)
class TradeSamplingBand:
    """The measured repeat count for one trade, with its provenance.

    ``measured_on`` / ``measured_note`` exist so a band can never become a folk number
    that nobody can trace. If you cannot fill them in, you do not have a band.
    """

    trade: str
    runs_per_query: int
    #: ISO date of the ``geo verify determinism`` run this came from. None = unmeasured.
    measured_on: str | None = None
    #: What was measured — engines, query cohort, observed agreement.
    measured_note: str = ""

    @property
    def is_measured(self) -> bool:
        return self.measured_on is not None

    @property
    def exceeds_cap(self) -> bool:
        """Whether this band needs more repeats than ``MAX_RUNS_PER_QUERY`` allows.

        A measured band above the cap is a real finding, not an error: it means local
        queries in this trade are too unstable to measure at the current ceiling.
        Raising the cap is a deliberate, cost-bearing decision — see ``runs_for_trade``.
        """
        return self.runs_per_query > settings.MAX_RUNS_PER_QUERY


#: Measured bands, keyed by trade. **Empty by design.**
#:
#: Populating this is a Phase-5 follow-up that costs real engine calls:
#:     python -m src.cli verify determinism   # per trade, against its query set
#: then add an entry with the date and the observed agreement. Do NOT add a trade here
#: from intuition — an unmeasured band that LOOKS measured is worse than none, because
#: it launders a guess into the report as a methodology figure.
SAMPLING_BANDS: dict[str, TradeSamplingBand] = {}


def band_for(trade: str) -> TradeSamplingBand:
    """The sampling band for a trade, or an unmeasured fallback at the global default."""
    key = trade.strip().lower()
    measured = SAMPLING_BANDS.get(key)
    if measured is not None:
        return measured
    return TradeSamplingBand(
        trade=key,
        runs_per_query=settings.DEFAULT_RUNS_PER_QUERY,
        measured_on=None,
        measured_note=(
            "no determinism run for this trade yet; using the global default. "
            "Local queries are known to be noisier than the consumer baseline this "
            "default was set from, so treat single-run findings with caution."
        ),
    )


def runs_for_trade(trade: str) -> int:
    """Repeats per (query, engine) for a trade, clamped to ``MAX_RUNS_PER_QUERY``.

    Clamping is deliberate and visible: ``band.exceeds_cap`` tells a caller the
    measurement asked for more than the guard allows, so raising
    ``MAX_RUNS_PER_QUERY`` is an explicit decision with a known cost rather than
    something that silently happens.
    """
    return min(band_for(trade).runs_per_query, settings.MAX_RUNS_PER_QUERY)


def sampling_note(trade: str) -> str:
    """One line a report can print about how this trade was sampled.

    Never claims a band was measured when it wasn't — the honest version is what makes
    the measured version worth anything.
    """
    band = band_for(trade)
    k = runs_for_trade(trade)
    if not band.is_measured:
        return (
            f"Sampling: {k} run(s) per query (global default — no determinism "
            f"measurement for {band.trade} yet, so this band is not established)."
        )
    capped = f" (capped from {band.runs_per_query} by MAX_RUNS_PER_QUERY)"
    return (
        f"Sampling: {k} run(s) per query{capped if band.exceeds_cap else ''}, "
        f"measured {band.measured_on} — {band.measured_note}"
    )


#: Intents whose findings are safe to report from a single run. Empty on the local
#: path: every local intent resolves against the live local pack, which SE Ranking
#: showed churning heavily between repeats. Kept as an explicit empty set rather than
#: an omission so the reasoning is discoverable.
SINGLE_RUN_SAFE_LOCAL_INTENTS: frozenset[IntentBucket] = frozenset()


if __name__ == "__main__":
    from src.prompts.local_templates import TRADES

    for trade in TRADES:
        print(f"{trade:<12} {sampling_note(trade)}")


def local_cadence_warning(trade: str) -> str | None:
    """The banner a local cadence comparison must carry when its noise floor is unknown.

    This exists because of a real trap in ``trend.render_comparison``: with
    ``noise_floor=None`` nothing is tagged _(within noise)_, so **every** delta reads
    as a real move. For the consumer path that is survivable — the baseline is
    measured and the engines are relatively stable. For local it is not: SE Ranking
    saw ~80% of URLs churn between repeat runs of the same query, so a month-on-month
    "improvement" is more likely jitter than progress, and reporting it to a shop
    owner as progress is exactly the kind of claim this codebase refuses elsewhere.

    Returns None once the trade has a measured band (then pass a real
    ``noise_floor`` to ``render_comparison`` and the tagging does its job).
    """
    if band_for(trade).is_measured:
        return None
    return (
        f"⚠️ No determinism baseline for {trade.strip().lower()} yet, so there is no "
        "noise floor to compare against. Local answers churn heavily between repeat "
        "runs — treat every delta below as UNVERIFIED movement, not progress. Run "
        "`python -m src.cli verify determinism` for this trade before reporting a trend."
    )
