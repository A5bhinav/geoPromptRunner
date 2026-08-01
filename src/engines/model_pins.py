"""Which engine pins are allowed to be undated, and what we gave up to allow it.

The isolation plan's Layer 3 rule is that every engine pins a **dated model snapshot**,
so a provider's silent model update shows up as a metadata diff rather than an
unexplained movement in a client's numbers. ``tests/test_isolation.py`` enforces it.

That rule can only be followed when the provider actually publishes a dated snapshot.
Some don't. This registry is the deliberate, reviewed list of exceptions — its purpose is
to make an undated pin a **decision with a written cost**, never an accident. An engine
absent from here must still be dated, and the test fails if it isn't.

Adding an entry means accepting that cycle-over-cycle comparisons on that surface can
move for reasons we cannot see. Say so in the reason string; do not add an entry to make
a test pass.
"""

from __future__ import annotations

__all__ = ["UNDATED_PINS", "is_pin_exempt"]

#: engine name -> why no dated pin exists, and what drift control replaces it.
UNDATED_PINS: dict[str, str] = {
    "openai": (
        "gpt-5.6-luna. OpenAI publishes no dated snapshot for the 5.6 family (verified "
        "live 2026-07-28: only gpt-5.6-luna/-sol/-terra exist) and the model returns "
        "system_fingerprint=None, so neither of the two available drift signals exists. "
        "DRIFT IS UNDETECTABLE ON THIS SURFACE — accepted knowingly for a ~3.3x price "
        "cut over the sunsetting gpt-4o-2024-08-06. Re-pin to a dated id the moment "
        "OpenAI publishes one."
    ),
    "gemini": (
        "gemini-2.5-flash. Google offers no dated snapshots for the Gemini API at all, "
        "so this has always been undated — recorded here to make the existing exception "
        "visible rather than implicit."
    ),
    "gemini_grounded": (
        "gemini-3.6-flash, same reason as `gemini`: Google publishes no dated snapshots "
        "for stable models — dated forms exist only on previews. Repinned off "
        "gemini-2.5-flash 2026-08-01 because 2.5 was two generations behind the surface "
        "this engine claims to measure; the repin costs more, not less."
    ),
    "openai_search": (
        "gpt-5.6-luna via the Responses web_search tool. OpenAI publishes no dated "
        "snapshot for the 5.6 family (verified live 2026-08-01: each model page's "
        "Snapshots section lists only the bare id) and returns no system_fingerprint, "
        "so neither drift signal exists. Accepted knowingly: the previous pin "
        "`gpt-5-search-api-2025-10-14` WAS dated but answered 0 of 10 cells against a "
        "6,000 TPM account cap, and a dated pin on a surface that returns nothing is "
        "worth less than an undated pin that returns data. DRIFT IS UNDETECTABLE HERE."
    ),
    "anthropic_search": (
        "claude-sonnet-5. Anthropic publishes no dated snapshot for the Sonnet 5 "
        "generation (verified live 2026-08-01: `claude-sonnet-5` is its own canonical "
        "id, as are opus-5 and sonnet-4-6). Repinned off claude-sonnet-4-5-20250929, "
        "which carried a dated id but a retirement floor of 2026-09-29 — so the choice "
        "was a dated pin that dies in eight weeks or an undated pin that does not. "
        "Drift here is detectable only through the run's engine_models metadata and "
        "answer-level change, not through the model id."
    ),
    "perplexity": (
        "sonar. Perplexity exposes only floating model aliases; no dated variant exists."
    ),
}


def is_pin_exempt(engine_name: str) -> bool:
    """Whether ``engine_name`` is a reviewed exception to the dated-snapshot rule."""
    return engine_name in UNDATED_PINS
