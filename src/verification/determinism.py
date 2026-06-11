from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from src.engines.base import BaseEngine

__all__ = [
    "DeterminismStats",
    "DeterminismBaseline",
    "normalize_answer",
    "agreement_stats",
    "suggest_runs_per_query",
    "measure_determinism",
    "render_baseline",
]

logger = logging.getLogger(__name__)

DEFAULT_K = 10
DEFAULT_QUERY = "What is the best budgeting app for college students?"


@dataclass(frozen=True)
class DeterminismStats:
    """Agreement profile of K fresh repeats of one query (Test D)."""

    k: int
    answered: int  # repeats that returned text (not None)
    unique_answers: int  # distinct answers after normalization
    modal_agreement: float  # share of answered repeats matching the most common answer
    identical: bool  # every answered repeat normalized-equal


@dataclass(frozen=True)
class DeterminismBaseline:
    """One engine's measured noise band for one query."""

    engine_name: str
    query: str
    stats: DeterminismStats
    responses: list[str | None]


def normalize_answer(text: str) -> str:
    """Collapse whitespace and case so trivial formatting differences don't
    count as disagreement — we're measuring content variance, not rendering."""
    return " ".join(text.split()).lower()


def agreement_stats(responses: Sequence[str | None]) -> DeterminismStats:
    """Compute the agreement profile of repeated responses. Pure."""
    answered = [normalize_answer(r) for r in responses if r is not None]
    if not answered:
        return DeterminismStats(
            k=len(responses), answered=0, unique_answers=0, modal_agreement=0.0, identical=False
        )
    counts = Counter(answered)
    modal = counts.most_common(1)[0][1]
    return DeterminismStats(
        k=len(responses),
        answered=len(answered),
        unique_answers=len(counts),
        modal_agreement=modal / len(answered),
        identical=len(counts) == 1,
    )


def suggest_runs_per_query(stats: DeterminismStats) -> int:
    """Recommend the runner's K from the measured noise band.

    High agreement means few repeats wash out the residual randomness; low
    agreement (typical of retrieval surfaces) needs more. Calibrates whether
    the default runs_per_query=3 is enough — or must rise.
    """
    if stats.answered == 0:
        return 3  # nothing measured; keep the default rather than guess
    if stats.modal_agreement >= 0.8:
        return 3
    if stats.modal_agreement >= 0.5:
        return 5
    return 10


def measure_determinism(
    engine: BaseEngine, query: str = DEFAULT_QUERY, k: int = DEFAULT_K
) -> DeterminismBaseline:
    """Run one query K times as separate fresh calls and profile the agreement.

    K live calls. Each repeat is its own isolated ``query`` call — exactly how
    the runner issues them — so the spread here is the spread a real audit sees.
    """
    if k < 2:
        raise ValueError(f"k must be >= 2 to measure agreement, got {k}")
    responses: list[str | None] = [engine.query(query) for _ in range(k)]
    return DeterminismBaseline(
        engine_name=engine.ENGINE_NAME,
        query=query,
        stats=agreement_stats(responses),
        responses=responses,
    )


def render_baseline(baselines: list[DeterminismBaseline]) -> str:
    """Human-readable noise-band table across engines."""
    lines = ["Determinism baseline (Test D) — how much variance is normal?", ""]
    for b in baselines:
        s = b.stats
        suggested = suggest_runs_per_query(s)
        lines.append(
            f"  {b.engine_name:<22} k={s.k:<3} answered={s.answered:<3} "
            f"unique={s.unique_answers:<3} modal-agreement={s.modal_agreement:.0%} "
            f"-> suggested runs_per_query={suggested}"
        )
    lines.append("")
    lines.append(
        "Parametric engines at temp 0 should sit near 100% agreement; retrieval "
        "surfaces vary by design (the live web) — read their numbers as the "
        "expected noise band, not as a defect."
    )
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    from src.cli import _load_engines

    engines = _load_engines("memory")
    if not engines:
        print("No engines configured (set API keys in .env).")
        raise SystemExit(0)
    print(f"Measuring {DEFAULT_K} repeats of: {DEFAULT_QUERY!r}\n")
    print(render_baseline([measure_determinism(e) for e in engines]))
