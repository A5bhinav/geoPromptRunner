from __future__ import annotations

import logging
from dataclasses import dataclass

from src.engines.base import BaseEngine

__all__ = [
    "MARKER",
    "SETUP_PROMPT",
    "PROBE_PROMPT",
    "CanaryResult",
    "evaluate_canary",
    "run_canary",
    "run_canaries",
    "render_canary_results",
]

logger = logging.getLogger(__name__)

# A marker no model would produce unprompted. If the *second*, fully separate
# call can echo it back, the first call's content leaked across calls and
# isolation is broken.
MARKER = "zanzibar-cerulean-47"

SETUP_PROMPT = (
    f'Remember this code phrase for later: "{MARKER}". Acknowledge in one short sentence.'
)
PROBE_PROMPT = (
    "What was the code phrase in my previous message? "
    "If you have no record of any previous message from me, "
    "reply with exactly: NO PRIOR CONTEXT."
)


@dataclass(frozen=True)
class CanaryResult:
    """Outcome of the memory-probe canary for one engine (Test A)."""

    engine_name: str
    verdict: str  # isolated | leaked | inconclusive
    setup_response: str | None
    probe_response: str | None


def evaluate_canary(probe_response: str | None, marker: str = MARKER) -> str:
    """Judge a probe response: did the second call see the first call's content?

    Pure. ``leaked`` iff the marker from the setup call appears in the probe
    response; ``inconclusive`` if the probe call itself failed (no response to
    judge); otherwise ``isolated`` — a stateless API cannot answer.
    """
    if probe_response is None:
        return "inconclusive"
    return "leaked" if marker.lower() in probe_response.lower() else "isolated"


def run_canary(engine: BaseEngine) -> CanaryResult:
    """Run the two-call memory probe against one engine.

    Call 1 plants the marker; call 2 — a completely separate ``query`` call —
    asks what came before. Two live calls per engine.
    """
    setup_response = engine.query(SETUP_PROMPT)
    probe_response = engine.query(PROBE_PROMPT)
    verdict = evaluate_canary(probe_response)
    if setup_response is None and verdict == "isolated":
        # The marker was never planted, so a clean probe proves nothing.
        verdict = "inconclusive"
    return CanaryResult(
        engine_name=engine.ENGINE_NAME,
        verdict=verdict,
        setup_response=setup_response,
        probe_response=probe_response,
    )


def run_canaries(engines: list[BaseEngine]) -> list[CanaryResult]:
    """Run the memory probe against every engine, never aborting on one failure."""
    return [run_canary(engine) for engine in engines]


def render_canary_results(results: list[CanaryResult]) -> str:
    """Human-readable verdict table for the canary run."""
    lines = ["Memory-probe canary (Test A) — is each call fresh?", ""]
    for r in results:
        snippet = (r.probe_response or "(no response)").strip().replace("\n", " ")
        if len(snippet) > 90:
            snippet = snippet[:87] + "..."
        flag = {"isolated": "OK", "leaked": "FAIL", "inconclusive": "?"}[r.verdict]
        lines.append(f"  [{flag:>4}] {r.engine_name:<22} {r.verdict:<12} probe: {snippet}")
    leaked = [r.engine_name for r in results if r.verdict == "leaked"]
    lines.append("")
    if leaked:
        lines.append(f"ISOLATION BROKEN on: {', '.join(leaked)} — investigate before measuring.")
    else:
        lines.append("No engine could recall the prior call: every call is a clean room.")
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from src.cli import _load_engines

    # Both surfaces, deduped (Perplexity appears in each list).
    by_name = {e.ENGINE_NAME: e for e in [*_load_engines("memory"), *_load_engines("search")]}
    engines = list(by_name.values())
    if not engines:
        print("No engines configured (set API keys in .env).")
        raise SystemExit(0)
    print(render_canary_results(run_canaries(engines)))
