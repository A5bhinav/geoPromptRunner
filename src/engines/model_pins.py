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
        "gemini-2.5-flash, same reason as `gemini`: Google publishes no dated snapshots."
    ),
    "perplexity": (
        "sonar. Perplexity exposes only floating model aliases; no dated variant exists."
    ),
}


def is_pin_exempt(engine_name: str) -> bool:
    """Whether ``engine_name`` is a reviewed exception to the dated-snapshot rule."""
    return engine_name in UNDATED_PINS
