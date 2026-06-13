from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.pipeline import metrics
from src.storage.models import QueryResult

__all__ = [
    "RunComparison",
    "compare_runs",
    "render_comparison",
    "due_for_rerun",
    "is_real_move",
]

# Methodology re-runs the locked set on a ~4-6 week cadence (Step 8).
DEFAULT_CADENCE_DAYS = 42


def due_for_rerun(
    last_run_iso: str, cadence_days: int = DEFAULT_CADENCE_DAYS, now: datetime | None = None
) -> bool:
    """True if the last run is at least ``cadence_days`` old (so a re-run is due).

    An unparseable/empty timestamp is treated as due.
    """
    if not last_run_iso:
        return True
    try:
        last = datetime.fromisoformat(last_run_iso)
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    now = now or datetime.now(UTC)
    return (now - last) >= timedelta(days=cadence_days)


@dataclass(frozen=True)
class RunComparison:
    """The diff between two cycles of the same locked query set — Step 8, the moat."""

    brand: str
    mention_rate_before: float
    mention_rate_after: float
    mention_rate_by_bucket_before: dict[str, float]
    mention_rate_by_bucket_after: dict[str, float]
    share_of_voice_before: dict[str, float]
    share_of_voice_after: dict[str, float]
    queries_won: list[tuple[str, str]]  # (query_id, engine) absent before, present now
    queries_lost: list[tuple[str, str]]  # present before, absent now

    @property
    def mention_rate_delta(self) -> float:
        return self.mention_rate_after - self.mention_rate_before


def _present_cells(results: list[QueryResult], brand: str) -> set[tuple[str, str]]:
    return {(v.query_id, v.engine_name) for v in metrics.brand_verdicts(results, brand) if v.hit}


def compare_runs(
    before: list[QueryResult],
    after: list[QueryResult],
    brand: str,
    competitors: list[str],
) -> RunComparison:
    """Compare two runs of the *same* locked query set. Valid only if the
    instrument (query set version) was held constant — that's the caller's job.
    """
    before_cells = _present_cells(before, brand)
    after_cells = _present_cells(after, brand)
    return RunComparison(
        brand=brand,
        mention_rate_before=metrics.mention_rate(before, brand),
        mention_rate_after=metrics.mention_rate(after, brand),
        mention_rate_by_bucket_before=metrics.mention_rate_by_bucket(before, brand),
        mention_rate_by_bucket_after=metrics.mention_rate_by_bucket(after, brand),
        share_of_voice_before=metrics.share_of_voice(before, brand, competitors),
        share_of_voice_after=metrics.share_of_voice(after, brand, competitors),
        queries_won=sorted(after_cells - before_cells),
        queries_lost=sorted(before_cells - after_cells),
    )


def is_real_move(before: float, after: float, noise_floor: float) -> bool:
    """True if the change exceeds the measurement noise band (a fraction in
    [0,1] from the determinism baseline). Below it, a delta is jitter, not signal."""
    return abs(after - before) > noise_floor


def _delta(before: float, after: float, noise_floor: float | None = None) -> str:
    pts = (after - before) * 100
    arrow = "▲" if pts > 0 else ("▼" if pts < 0 else "—")
    out = f"{before * 100:.0f}% → {after * 100:.0f}% ({arrow}{abs(pts):.0f} pts)"
    if noise_floor is not None and pts != 0 and not is_real_move(before, after, noise_floor):
        out += " _(within noise)_"
    return out


def render_comparison(
    cmp: RunComparison,
    before_label: str,
    after_label: str,
    noise_floor: float | None = None,
) -> str:
    """Render the before/after diff as markdown — the clean handoff for §6.

    ``noise_floor`` (a fraction, e.g. 0.05 = 5 pts) is the measurement noise band
    from the determinism baseline (``geo verify determinism``). When given, deltas
    that don't clear it are tagged _(within noise)_ so the trend — the moat —
    reports real movement, not jitter.
    """
    lines: list[str] = []
    lines.append(f"# Trend — {cmp.brand}")
    lines.append("")
    lines.append(f"**Comparing:** {before_label} → {after_label}")
    if noise_floor is not None:
        lines.append("")
        lines.append(
            f"_Real-move threshold: ±{noise_floor * 100:.0f} pts (from the determinism "
            "baseline); smaller deltas are within measurement noise._"
        )
    lines.append("")
    lines.append(
        f"**Overall mention rate:** "
        f"{_delta(cmp.mention_rate_before, cmp.mention_rate_after, noise_floor)}"
    )
    lines.append("")

    lines.append("## Mention Rate by Funnel Stage")
    lines.append("")
    lines.append("| Bucket | Before → After |")
    lines.append("| --- | --- |")
    buckets = sorted(set(cmp.mention_rate_by_bucket_before) | set(cmp.mention_rate_by_bucket_after))
    for b in buckets:
        before = cmp.mention_rate_by_bucket_before.get(b, 0.0)
        after = cmp.mention_rate_by_bucket_after.get(b, 0.0)
        lines.append(f"| {b} | {_delta(before, after, noise_floor)} |")
    lines.append("")

    lines.append("## Share of Voice")
    lines.append("")
    lines.append("| Brand | Before → After |")
    lines.append("| --- | --- |")
    names = sorted(set(cmp.share_of_voice_before) | set(cmp.share_of_voice_after))
    for n in names:
        before = cmp.share_of_voice_before.get(n, 0.0)
        after = cmp.share_of_voice_after.get(n, 0.0)
        marker = " (client)" if n == cmp.brand else ""
        lines.append(f"| {n}{marker} | {_delta(before, after, noise_floor)} |")
    lines.append("")

    lines.append(f"## Queries Won ({len(cmp.queries_won)})")
    lines.append("")
    if cmp.queries_won:
        for qid, engine in cmp.queries_won:
            lines.append(f"- {qid} on {engine}")
    else:
        lines.append("_None._")
    lines.append("")

    lines.append(f"## Queries Lost ({len(cmp.queries_lost)})")
    lines.append("")
    if cmp.queries_lost:
        for qid, engine in cmp.queries_lost:
            lines.append(f"- {qid} on {engine}")
    else:
        lines.append("_None._")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":

    def _qr(qid: str, eng: str, resp: str | None, intent: str = "category") -> QueryResult:
        return QueryResult(
            query_id=qid,
            intent=intent,
            prompt="(mock)",
            engine_name=eng,
            run_index=0,
            response=resp,
            citations=[],
            timestamp="t",
        )

    before = [_qr("q1", "openai", "Salesforce wins."), _qr("q2", "openai", "Acme is good.")]
    after = [_qr("q1", "openai", "Acme is now recommended."), _qr("q2", "openai", "Acme is good.")]
    cmp = compare_runs(before, after, "Acme", ["Salesforce"])
    print(render_comparison(cmp, "v1 (2026-05-01)", "v1 (2026-06-01)"))
