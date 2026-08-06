"""Per-trade local query templates (W2.2).

The local query space is genuinely small — a trade has a few dozen questions that
matter, not thousands — so these are hand-written per trade rather than
LLM-generated, and the LLM path (the teaser's generator) falls back to them.

Each template holds exactly ``QUERY_SET_SIZE`` questions, in the same intent mix
the generator produces (11 local · 6 hybrid · 5 informational · 3 brand). A
hand-written set and a generated one have to be the same instrument, or a local
audit and a generic one cannot be read against each other.

Each ``data/queries_<trade>.json`` is a real query set with ``{city}`` and ``{brand}``
slots. It validates against the same schema as any other set; substitution just fills
the slots. This is the trade-side twin of the consumer starter template — the two are
FORKED, not merged (pivot §0.6): ``build_template_csv()`` with no argument still
returns the Oura consumer CSV byte-for-byte.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from src.prompts.query_set import Query, QuerySet

__all__ = ["TRADES", "trade_template_path", "load_trade_template", "render_trade_queries"]

#: Trades with a hand-written local query set. Keys are the CLI/API-facing names.
TRADES: tuple[str, ...] = ("hvac", "plumbing", "barbershop")

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# The slots a trade template may carry. Kept explicit so an unfilled slot is a loud
# error rather than a query reading "best plumber in {city}" sent to a live engine.
_CITY_SLOT = "{city}"
_BRAND_SLOT = "{brand}"


def trade_template_path(trade: str) -> Path:
    """Path to a trade's template file. Raises ``ValueError`` on an unknown trade."""
    key = trade.strip().lower()
    if key not in TRADES:
        raise ValueError(f"unknown trade {trade!r}; expected one of: {', '.join(TRADES)}")
    return _DATA_DIR / f"queries_{key}.json"


def load_trade_template(trade: str) -> QuerySet:
    """Load a trade's raw template — slots still unfilled.

    Useful for inspection/validation. To run one, call ``render_trade_queries``.
    """
    from src.prompts.query_set import load_query_set

    return load_query_set(trade_template_path(trade))


def render_trade_queries(trade: str, city: str, brand: str) -> QuerySet:
    """Fill a trade template's ``{city}``/``{brand}`` slots.

    Raises ``ValueError`` when ``city`` or ``brand`` is blank, or when any slot
    survives substitution. A literal "{city}" reaching an engine would measure a
    question no customer ever asks, and would silently score as a loss — so an
    unfilled slot fails loudly instead.
    """
    city = city.strip()
    brand = brand.strip()
    if not city:
        raise ValueError(f"city is required to render the {trade} template")
    if not brand:
        raise ValueError(f"brand is required to render the {trade} template")

    template = load_trade_template(trade)
    rendered: list[Query] = [
        dataclasses.replace(
            q, text=q.text.replace(_CITY_SLOT, city).replace(_BRAND_SLOT, brand)
        )
        for q in template.queries
    ]

    unfilled = [q.query_id for q in rendered if _CITY_SLOT in q.text or _BRAND_SLOT in q.text]
    if unfilled:
        raise ValueError(f"unfilled slots survived substitution in: {', '.join(unfilled)}")

    return dataclasses.replace(
        template,
        client=brand,
        queries=rendered,
    )


def build_trade_template_csv(trade: str, city: str = "{city}", brand: str = "{brand}") -> str:
    """A starter CSV for one trade, in the same shape as the consumer template.

    Defaults leave the slots in place so a shop owner (or Josh) can see exactly which
    two values to fill in before uploading — this is a template to EDIT, not a runnable
    set, which is why the slots are allowed to survive here and nowhere else.
    """
    import csv
    import io

    from src.prompts.csv_loader import _COLUMNS

    template = load_trade_template(trade)
    rows: list[list[str]] = [
        list(_COLUMNS),
        ["config", "client_name", brand, "", ""],
        ["config", "category", template.category, "", ""],
        ["config", "competitors", "", "", ""],
        # Corrected 2026-07-28. The previous comment claimed AI Overviews was "the
        # highest-weight surface for local intent" — measurement says the opposite: an
        # Overview appears for ~15% of local-intent SERPs (0 of 5 in run e186c524)
        # against ~93% for the local pack, so `engine_routing` no longer asks it those
        # queries at all. It stays in the list because it dominates the informational
        # (~92%) and hybrid (~97%) tiers, and the local pack is captured separately
        # (src/engines/local_pack.py).
        #
        # gemini_grounded leads now: it is Google's own AI answer over Google Search,
        # on the official API and an already-paid tier with a free monthly grounding
        # quota, and it was the richest surface on a live probe (2660 chars / 6
        # citations vs perplexity's 746 / 2). It was previously omitted entirely.
        #
        # openai_search is BACK as of 2026-08-01, after being dropped on 2026-07-28.
        # It was removed because OpenAI's search-class models were capped at 6,000
        # tokens/min on this account while one search answer consumed ~17,200 (mostly
        # retrieved context), so a real run lost every cell to 429s (verified twice:
        # 0 of 10 answered) at a sustainable 0.3 calls/min. The surface has since been
        # rewritten onto the Responses `web_search` tool on gpt-5.6-luna, which bills
        # against the calling model's own limits (500k TPM / 500 RPM at Tier 1) — so the
        # cap that excluded it no longer exists, and neither does the per-engine
        # concurrency override that used to serialize it (see prompt_runner.py).
        #
        # google_ai_mode REPLACES google_ai_overviews as the Google answer surface: AI
        # Mode answers every intent, so it has no routing skip and covers the local-intent
        # buying moment that AI Overviews structurally cannot (~15% of local SERPs, 0 of 5
        # measured). Needs DATAFORSEO_LOGIN/PASSWORD; without them it is reported in the
        # run's skipped_engines rather than silently dropped.
        #
        # openai is the parametric ChatGPT surface (gpt-5.6-luna, ~$0.0015/call), kept
        # alongside openai_search rather than replaced by it: parametric memory and live
        # retrieval are two different consumer moments, and the parametric one is the
        # cheapest ~100%-coverage surface in the stack.
        [
            "config",
            "engines",
            "gemini_grounded;perplexity;google_ai_mode;openai;openai_search",
            "",
            "",
        ],
        ["config", "runs_per_query", "3", "", ""],
        ["config", "client_domains", "", "", ""],
        # Google's canonical location name — "City,State,United States" (the country's
        # FULL NAME; an ISO code is rejected). Without it a local run
        # measures an unpinned locale, i.e. the wrong market.
        ["config", "location", f"{city},<STATE>,United States", "", ""],
    ]
    for q in template.queries:
        text = q.text.replace(_CITY_SLOT, city).replace(_BRAND_SLOT, brand)
        rows.append(["query", q.query_id, text, q.intent.value, q.persona or ""])

    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


if __name__ == "__main__":
    for trade in TRADES:
        qs = render_trade_queries(trade, city="Berkeley", brand="Acme Co")
        print(f"{trade}: {len(qs.queries)} queries, category={qs.category!r}")
        for q in qs.queries[:3]:
            print(f"    [{q.intent.value}] {q.text}")
