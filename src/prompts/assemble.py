"""Assemble a runnable audit CSV from a lead, so nobody hand-edits one.

The four inputs a local run needs all exist programmatically — the lead's own
fields, a trade query template, competitors from the local pack, and an approved
fact sheet — and nothing combined them. So the flow was: download a template,
find-and-replace ``{city}`` in 29 rows, type eight config lines, type a
competitor list, upload. Five minutes of clerical work per audit, one line of
which was data we already had.

This is the pure assembler. It takes competitors as an ARGUMENT rather than
fetching them, so it stays testable without a network and the API layer owns the
one call that costs money.

**No fact block is emitted.** The sheet attaches to the run by id
(``POST /audits`` ``fact_sheet_id``), and a run carrying both is refused — two
sources of ground truth for one measurement.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence

from src.prompts.local_templates import TRADES, render_trade_queries

__all__ = [
    "DEFAULT_LOCAL_ENGINES",
    "AssembleError",
    "assemble_run_csv",
]

# Mirrors the local template's engine row, which was measured rather than chosen:
# `openai` is the parametric ChatGPT surface, included because ~100% coverage at
# $0.0015/call beats a retrieval surface that answers nothing (openai_search is
# out on a 6k TPM cap). Kept in one place so the assembled CSV and the downloadable
# template cannot drift.
DEFAULT_LOCAL_ENGINES: tuple[str, ...] = (
    "gemini_grounded",
    "perplexity",
    "google_ai_mode",
    "openai",
)

_COLUMNS = ("block", "key", "value", "intent", "persona")

# A region that is two letters is an abbreviation, and an abbreviation is rejected
# by the SERP vendors — DataForSEO returns zero tasks and the surface comes back
# silently empty, which reads as "the brand does not appear". Verified twice on two
# different vendors. Refusing here is the only place it is still cheap to catch.
_ABBREVIATED_REGION_RE = re.compile(r"^[A-Za-z]{2}\.?$")

# Any template slot that survived rendering. A literal "{city}" reaching an engine
# measures a question no customer asks and scores as a loss.
_UNFILLED_SLOT_RE = re.compile(r"\{[a-z_]+\}")


class AssembleError(ValueError):
    """The inputs cannot produce a runnable audit. Carries the reason for the user."""


def assemble_run_csv(
    *,
    business: str,
    website: str,
    trade: str,
    city: str,
    region: str,
    competitors: Sequence[str],
    country: str = "United States",
    category: str | None = None,
    engines: Sequence[str] = DEFAULT_LOCAL_ENGINES,
    runs_per_query: int = 3,
    judge: bool = False,
) -> str:
    """A complete, uploadable audit CSV for one local business. Pure.

    ``region`` must be the state's FULL NAME ("California", not "CA") and is
    refused otherwise — see ``_ABBREVIATED_REGION_RE``. Nothing in this repo
    expands abbreviations, deliberately: the resolver's own instruction is that a
    guessed location silently geo-anchors every query to the wrong place, and a
    wrong market is worse than a missing one.

    ``judge`` defaults to False because the prejudge flow makes judging free: run
    with it off, warm the cache on the subscription, then judge for $0.
    """
    business = business.strip()
    city = city.strip()
    region = region.strip()
    if trade not in TRADES:
        raise AssembleError(f"unknown trade {trade!r}; expected one of: {', '.join(TRADES)}")
    if not business:
        raise AssembleError("business name is required — it is the brand every query is scored on")
    if not city:
        raise AssembleError("city is required; a local query set without one measures nowhere")
    if not region:
        raise AssembleError("region is required (the state's full name, e.g. 'California')")
    if _ABBREVIATED_REGION_RE.match(region):
        raise AssembleError(
            f"region {region!r} looks like an abbreviation. Use the full name "
            "('California', not 'CA') — the SERP vendors reject the short form and "
            "return an empty surface, which reads as the brand being absent."
        )

    query_set = render_trade_queries(trade, city, business)
    rows: list[tuple[str, str, str, str, str]] = [
        ("config", "client_name", business, "", ""),
        ("config", "category", category or f"{trade} service", "", ""),
        ("config", "competitors", ";".join(c.strip() for c in competitors if c.strip()), "", ""),
        ("config", "engines", ";".join(engines), "", ""),
        ("config", "runs_per_query", str(runs_per_query), "", ""),
        ("config", "client_domains", _domain(website), "", ""),
        ("config", "location", f"{city},{region},{country}", "", ""),
        ("config", "judge", "true" if judge else "false", "", ""),
    ]
    for query in query_set.queries:
        text = query.text
        if _UNFILLED_SLOT_RE.search(text):
            # render_trade_queries raises on this too; re-checked because an
            # unfilled slot that reaches an engine is unrecoverable — it scores as
            # a loss on a question nobody asked.
            raise AssembleError(f"template slot survived rendering: {text!r}")
        rows.append(("query", query.query_id, text, query.intent.value, query.persona or ""))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_COLUMNS)
    writer.writerows(rows)
    return buffer.getvalue()


def _domain(website: str) -> str:
    """Bare host, as `config,client_domains` expects."""
    host = re.sub(r"^https?://", "", (website or "").strip(), flags=re.IGNORECASE)
    return host.split("/")[0].removeprefix("www.").strip()
