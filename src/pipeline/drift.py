"""Detect that an engine changed underneath the measurement (P4-T3).

No GEO vendor documents how they handle engine model-version changes, and silent
model updates make trend lines lie: a client's visibility appears to move when
the only thing that moved was the model answering.

Three of the six surfaces have **no dated model pin available at all** — OpenAI
and Google publish none, so ``src/engines/model_pins.py`` records the exception
rather than pretending. On those surfaces drift is undetectable from metadata,
which is exactly why a *behavioural* fingerprint is needed.

**What this does NOT do: re-baseline.** On a material shift the cycle is
ANNOTATED and the trend chart carries the annotation. Retroactively adjusting
history to make a line look continuous is the "never silently rewrite history"
rule, and it is the difference between a measurement and a story.

Structural properties only — length, refusal rate, citation counts. Never the
answer's meaning: a fingerprint over content would fire on the client's own
progress, which is the signal, not the noise.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from src.storage.models import QueryResult

__all__ = [
    "LENGTH_SHIFT_THRESHOLD",
    "REFUSAL_SHIFT_THRESHOLD",
    "EngineFingerprint",
    "DriftVerdict",
    "fingerprint_engine",
    "fingerprint_run",
    "compare_fingerprints",
]

#: Relative change in median answer length that counts as material.
#:
#: TUNABLE. 0.35 is deliberately loose: the cost of a false "possible engine
#: update" annotation is a footnote nobody needed, and the cost of a missed one is
#: a trend line that lies. Loose enough not to fire on normal variation, tight
#: enough to catch a model generation change, which typically moves length far
#: more than this.
LENGTH_SHIFT_THRESHOLD = 0.35

#: Absolute change in the share of cells that returned nothing.
REFUSAL_SHIFT_THRESHOLD = 0.20

#: Relative change in mean citations per answer. Only meaningful on surfaces that
#: cite at all; a surface that has never cited is skipped rather than scored 0.
CITATION_SHIFT_THRESHOLD = 0.50


@dataclass(frozen=True)
class EngineFingerprint:
    """One surface's structural behaviour in one cycle.

    Deliberately shallow. Anything deeper starts encoding what the model SAID,
    and a fingerprint that moves when the client's visibility moves cannot tell
    the two apart.
    """

    engine_name: str
    model_id: str
    n_cells: int
    n_answered: int
    median_length: float
    mean_citations: float

    @property
    def refusal_rate(self) -> float:
        """Cells that returned nothing. 1.0 when nothing was attempted."""
        return 1.0 - (self.n_answered / self.n_cells) if self.n_cells else 1.0

    @property
    def is_measurable(self) -> bool:
        """Below this there is no distribution to fingerprint, only anecdote."""
        return self.n_answered >= 5


@dataclass(frozen=True)
class DriftVerdict:
    """Whether a surface's behaviour moved, and what moved."""

    engine_name: str
    drifted: bool
    reasons: list[str]
    #: True when the recorded model id itself changed — a certainty, not an
    #: inference, and the only signal available on a dated-pin surface.
    model_changed: bool = False

    def annotation(self) -> str:
        """The line that goes on the trend chart for this cycle.

        Phrased as an observation about the instrument, never as a claim about
        the client, and never as a correction to the history.
        """
        if not self.drifted:
            return ""
        if self.model_changed:
            return (
                f"{self.engine_name}: the model answering this surface changed between "
                f"cycles. Figures either side of this point are not strictly comparable."
            )
        return (
            f"{self.engine_name}: possible engine update — {'; '.join(self.reasons)}. "
            f"Figures either side of this point may not be strictly comparable."
        )


def fingerprint_engine(
    results: Sequence[QueryResult], engine_name: str, model_id: str = ""
) -> EngineFingerprint:
    """Structural fingerprint of one surface in one cycle. Pure."""
    cells = [r for r in results if r["engine_name"] == engine_name]
    answered = [r for r in cells if r["response"] is not None]
    lengths = [len(r["response"] or "") for r in answered]
    citations = [len(r["citations"]) for r in answered]
    return EngineFingerprint(
        engine_name=engine_name,
        model_id=model_id,
        n_cells=len(cells),
        n_answered=len(answered),
        median_length=statistics.median(lengths) if lengths else 0.0,
        mean_citations=(sum(citations) / len(citations) if citations else 0.0),
    )


def fingerprint_run(
    results: Sequence[QueryResult], engine_models: dict[str, str] | None = None
) -> dict[str, EngineFingerprint]:
    """Fingerprint every surface in a cycle."""
    models = engine_models or {}
    names = sorted({r["engine_name"] for r in results})
    return {name: fingerprint_engine(results, name, models.get(name, "")) for name in names}


def compare_fingerprints(
    before: EngineFingerprint | None, after: EngineFingerprint
) -> DriftVerdict:
    """Did this surface behave differently enough to annotate the cycle?

    A missing prior fingerprint is NOT drift — a first cycle has nothing to have
    drifted from, and reporting one would make every new client's first report
    carry a warning about an engine update that did not happen.
    """
    if before is None:
        return DriftVerdict(after.engine_name, drifted=False, reasons=[])

    # A changed model id is certainty, not inference — report it whatever the
    # behavioural signals say, including when they say nothing.
    model_changed = bool(before.model_id and after.model_id and before.model_id != after.model_id)
    reasons: list[str] = []
    if model_changed:
        reasons.append(f"pinned model moved from {before.model_id} to {after.model_id}")

    if not (before.is_measurable and after.is_measurable):
        # Too little data to distinguish a model change from a quiet week. Say
        # nothing rather than guess — a spurious annotation trains people to
        # ignore annotations.
        return DriftVerdict(after.engine_name, drifted=model_changed, reasons=reasons,
                            model_changed=model_changed)

    if before.median_length > 0:
        shift = abs(after.median_length - before.median_length) / before.median_length
        if shift >= LENGTH_SHIFT_THRESHOLD:
            reasons.append(
                f"median answer length moved {shift:.0%} "
                f"({before.median_length:.0f} → {after.median_length:.0f} chars)"
            )

    refusal_shift = abs(after.refusal_rate - before.refusal_rate)
    if refusal_shift >= REFUSAL_SHIFT_THRESHOLD:
        reasons.append(
            f"unanswered share moved {refusal_shift:.0%} "
            f"({before.refusal_rate:.0%} → {after.refusal_rate:.0%})"
        )

    # Only where the surface cites at all — a parametric engine scoring 0 both
    # cycles is not evidence of anything.
    if before.mean_citations > 0:
        citation_shift = abs(after.mean_citations - before.mean_citations) / before.mean_citations
        if citation_shift >= CITATION_SHIFT_THRESHOLD:
            reasons.append(
                f"citations per answer moved {citation_shift:.0%} "
                f"({before.mean_citations:.1f} → {after.mean_citations:.1f})"
            )

    return DriftVerdict(
        engine_name=after.engine_name,
        drifted=bool(reasons),
        reasons=reasons,
        model_changed=model_changed,
    )


if __name__ == "__main__":

    def _qr(engine: str, i: int, text: str | None, citations: int = 0) -> QueryResult:
        return QueryResult(
            query_id=f"q{i}",
            intent="category",
            prompt="(mock)",
            engine_name=engine,
            run_index=0,
            response=text,
            citations=["https://x"] * citations,
            timestamp="t",
        )

    old = [_qr("perplexity", i, "a" * 900, 3) for i in range(10)]
    new_stable = [_qr("perplexity", i, "a" * 950, 3) for i in range(10)]
    new_drifted = [_qr("perplexity", i, "a" * 2600, 1) for i in range(10)]

    before = fingerprint_engine(old, "perplexity", "sonar")
    for label, results, model in (
        ("stable", new_stable, "sonar"),
        ("longer answers", new_drifted, "sonar"),
        ("repinned", new_stable, "sonar-pro"),
    ):
        verdict = compare_fingerprints(before, fingerprint_engine(results, "perplexity", model))
        print(f"{label:16s} drifted={verdict.drifted}  {verdict.annotation() or '(no annotation)'}")
