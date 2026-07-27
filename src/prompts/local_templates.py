"""Per-trade local query templates (W2.2).

The local query space is genuinely small — a trade has on the order of 30 questions
that matter, not thousands — so these are hand-written per trade rather than
LLM-generated, and the LLM path (the teaser's generator) falls back to them.

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
        # Google AI Overviews first: it is the highest-weight surface for local
        # intent, and the only one that takes a location.
        ["config", "engines", "google_ai_overviews;perplexity;openai_search", "", ""],
        ["config", "runs_per_query", "5", "", ""],
        ["config", "client_domains", "", "", ""],
        # Canonical SearchApi location — "City,State,United States" (the country's
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
