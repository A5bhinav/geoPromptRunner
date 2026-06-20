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
    "BrandLabel",
    "LabelDeterminismStats",
    "LabelDeterminismBaseline",
    "label_agreement_stats",
    "suggest_runs_from_labels",
    "measure_label_determinism",
    "render_label_baseline",
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


def _k_from_agreement(modal_agreement: float, answered: int) -> int:
    """Recommend K from a measured modal-agreement band. High agreement means few
    repeats wash out the residual randomness; low agreement (retrieval surfaces)
    needs more. Shared by the text-level and label-level baselines."""
    if answered == 0:
        return 3  # nothing measured; keep the default rather than guess
    if modal_agreement >= 0.8:
        return 3
    if modal_agreement >= 0.5:
        return 5
    return 10


def suggest_runs_per_query(stats: DeterminismStats) -> int:
    """Recommend the runner's K from the measured *text* noise band. NOTE: at
    temperature 0 the engines rarely repeat a long answer verbatim, so text
    agreement understates real stability — prefer ``suggest_runs_from_labels``,
    which measures whether the *brand read* (present/prominence/framing) is
    stable, the thing the audit metrics and trends actually depend on."""
    return _k_from_agreement(stats.modal_agreement, stats.answered)


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


# --- Label-level determinism (the audit-relevant signal) -------------------
# Text never repeats verbatim at temp 0, but what the audit measures is the
# JUDGE's brand read. So the determinism that matters is: across K fresh answers
# to one query, does the brand's (present, prominence, framing) stay the same?
# The judge runs at temperature 0 (deterministic), so any disagreement here is
# ENGINE variance carrying through to a different read — exactly the audit noise.

BrandLabel = tuple[bool, str, str]  # (present, prominence, framing)


@dataclass(frozen=True)
class LabelDeterminismStats:
    """How stable the per-brand label is across K fresh repeats of one query."""

    k: int
    answered: int
    per_brand: dict[str, float]  # brand -> modal (present,prominence,framing) agreement

    @property
    def min_agreement(self) -> float:
        """Worst-stabilized brand — the conservative basis for K."""
        return min(self.per_brand.values()) if self.per_brand else 0.0

    @property
    def mean_agreement(self) -> float:
        return sum(self.per_brand.values()) / len(self.per_brand) if self.per_brand else 0.0


@dataclass(frozen=True)
class LabelDeterminismBaseline:
    engine_name: str
    query: str
    client: str
    stats: LabelDeterminismStats


def label_agreement_stats(runs: Sequence[dict[str, BrandLabel] | None]) -> LabelDeterminismStats:
    """Per-brand modal agreement of the label tuple across runs (pure)."""
    answered = [r for r in runs if r is not None]
    brands = sorted({b for r in answered for b in r})
    per_brand: dict[str, float] = {}
    for b in brands:
        labels = [r[b] for r in answered if b in r]
        if not labels:
            continue
        modal = Counter(labels).most_common(1)[0][1]
        per_brand[b] = modal / len(labels)
    return LabelDeterminismStats(k=len(runs), answered=len(answered), per_brand=per_brand)


def suggest_runs_from_labels(stats: LabelDeterminismStats) -> int:
    """Recommend K from the label noise band — the audit-relevant version."""
    return _k_from_agreement(stats.min_agreement, stats.answered)


def measure_label_determinism(
    engine: BaseEngine,
    judge: object,  # src.pipeline.judge.Judge — typed loosely to avoid an import cycle
    query: str,
    client: str,
    competitors: list[str],
    k: int = DEFAULT_K,
) -> LabelDeterminismBaseline:
    """K fresh answers to one query, each judged (no fact sheet → labels only),
    profiled for how stably the brand read reproduces. K live engine calls."""
    if k < 2:
        raise ValueError(f"k must be >= 2 to measure agreement, got {k}")
    runs: list[dict[str, BrandLabel] | None] = []
    for _ in range(k):
        answer = engine.query(query)
        if answer is None:
            runs.append(None)
            continue
        brands, _flags, assessed = judge.judge_answer(  # type: ignore[attr-defined]
            query, answer, client, competitors, None
        )
        labels = {b.brand: (b.present, b.prominence, b.framing) for b in brands}
        runs.append(labels if assessed else None)
    return LabelDeterminismBaseline(
        engine_name=engine.ENGINE_NAME,
        query=query,
        client=client,
        stats=label_agreement_stats(runs),
    )


def render_label_baseline(baselines: list[LabelDeterminismBaseline]) -> str:
    """Label-level noise-band table + the suggested K and trend noise floor."""
    lines = ["Label-level determinism — does the brand READ stay stable across repeats?", ""]
    worst = 1.0
    for b in baselines:
        s = b.stats
        k = suggest_runs_from_labels(s)
        worst = min(worst, s.min_agreement) if s.answered else worst
        lines.append(
            f"  {b.engine_name:<22} k={s.k:<3} answered={s.answered:<3} "
            f"min-agreement={s.min_agreement:.0%} mean={s.mean_agreement:.0%} "
            f"-> suggested runs_per_query={k}"
        )
    floor = round(1 - worst, 2)
    lines += [
        "",
        f"Suggested trend real-move threshold (noise floor): ±{floor * 100:.0f} pts "
        f"(1 − worst label agreement). Pass as --noise-floor {floor} to `geo compare`.",
    ]
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
