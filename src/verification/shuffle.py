from __future__ import annotations

import logging
from dataclasses import dataclass

from src.engines.base import BaseEngine
from src.verification.determinism import normalize_answer

__all__ = [
    "ShuffleComparison",
    "ShuffleResult",
    "compare_passes",
    "run_order_shuffle",
    "render_shuffle_results",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShuffleComparison:
    """One query's answers from the forward pass vs the reversed pass."""

    prompt: str
    forward: str | None
    backward: str | None
    match: bool  # normalized-equal (both-None counts as a match)


@dataclass(frozen=True)
class ShuffleResult:
    """Order-shuffle outcome for one engine (Test C)."""

    engine_name: str
    comparisons: list[ShuffleComparison]
    match_rate: float  # matching queries / total (1.0 for an empty set)


def compare_passes(
    prompts: list[str], forward: list[str | None], backward: list[str | None]
) -> list[ShuffleComparison]:
    """Pair up per-query answers from the two passes. Pure.

    ``forward`` and ``backward`` are both in *prompt order* (the caller un-reverses
    the second pass). A position where either pass changed its answer is a
    mismatch — expected occasionally from plain run-to-run noise, but a *systematic*
    pattern (e.g. late queries flipping when run early) would indicate leakage.
    """
    if not (len(prompts) == len(forward) == len(backward)):
        raise ValueError(
            f"length mismatch: {len(prompts)} prompts, "
            f"{len(forward)} forward, {len(backward)} backward"
        )
    comparisons: list[ShuffleComparison] = []
    for prompt, fwd, bwd in zip(prompts, forward, backward, strict=True):
        if fwd is None or bwd is None:
            match = fwd is None and bwd is None
        else:
            match = normalize_answer(fwd) == normalize_answer(bwd)
        comparisons.append(ShuffleComparison(prompt=prompt, forward=fwd, backward=bwd, match=match))
    return comparisons


def run_order_shuffle(engine: BaseEngine, prompts: list[str]) -> ShuffleResult:
    """Run the prompt set in order, then reversed, and compare per-query answers.

    2 × len(prompts) live calls. If calls are isolated, a query's answer cannot
    depend on what ran before it — so order must not matter beyond normal
    run-to-run noise (compare against the Test D baseline).
    """
    forward = [engine.query(p) for p in prompts]
    backward_reversed = [engine.query(p) for p in reversed(prompts)]
    backward = list(reversed(backward_reversed))  # back into prompt order
    comparisons = compare_passes(prompts, forward, backward)
    matched = sum(1 for c in comparisons if c.match)
    match_rate = matched / len(comparisons) if comparisons else 1.0
    return ShuffleResult(
        engine_name=engine.ENGINE_NAME, comparisons=comparisons, match_rate=match_rate
    )


def render_shuffle_results(results: list[ShuffleResult]) -> str:
    """Human-readable order-shuffle table across engines."""
    lines = ["Order-shuffle (Test C) — does running order change answers?", ""]
    for r in results:
        lines.append(f"  {r.engine_name:<22} match rate {r.match_rate:.0%}")
        for c in r.comparisons:
            if c.match:
                continue
            prompt = c.prompt if len(c.prompt) <= 60 else c.prompt[:57] + "..."
            lines.append(f"    differs: {prompt}")
    lines.append("")
    lines.append(
        "Mismatches at the level of the Test D noise band are normal randomness; "
        "a systematic shift tied to position would indicate cross-query leakage."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from pathlib import Path

    from src.cli import _load_engines
    from src.prompts.query_set import load_query_set

    engines = _load_engines("memory")
    if not engines:
        print("No engines configured (set API keys in .env).")
        raise SystemExit(0)
    sample = Path(__file__).resolve().parents[2] / "data" / "sample_queries.json"
    prompts = [q.text for q in load_query_set(sample).queries]
    print(f"Shuffling {len(prompts)} queries (2 passes per engine)\n")
    print(render_shuffle_results([run_order_shuffle(e, prompts) for e in engines]))
