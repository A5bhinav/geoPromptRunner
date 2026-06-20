from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.pipeline.judge import AccuracyFlag, AnswerJudgment, Framing, Prominence
from src.storage.models import Severity

__all__ = [
    "BrandCell",
    "VisibilityGrade",
    "brand_cells_map",
    "mention_rate",
    "visibility_score",
    "leaderboard",
    "framing_breakdown",
    "collect_accuracy_flags",
    "grade_penalty_flags",
    "GradePolicy",
    "DEFAULT_GRADE_POLICY",
    "grade_from",
    "visibility_grade",
    "losing_cells",
    "judge_sections",
    "render_judge_report",
]

# Prominence as an ordinal (best -> worst) and as a 0..1 visibility weight.
_PROM_RANK: dict[str, int] = {
    Prominence.RECOMMENDED_FIRST.value: 0,
    Prominence.MID_PACK.value: 1,
    Prominence.BURIED.value: 2,
    Prominence.ALSO_RAN.value: 3,
    Prominence.ABSENT.value: 4,
}
_PROM_SCORE: dict[str, float] = {
    Prominence.RECOMMENDED_FIRST.value: 1.0,
    Prominence.MID_PACK.value: 0.6,
    Prominence.BURIED.value: 0.3,
    Prominence.ALSO_RAN.value: 0.1,
    Prominence.ABSENT.value: 0.0,
}


@dataclass(frozen=True)
class BrandCell:
    """One brand's aggregated verdict for one (query, engine) across its runs."""

    query_id: str
    engine_name: str
    intent: str
    brand: str
    present: bool
    prominence: str
    framing: str


def _assessed(judgments: list[AnswerJudgment]) -> list[AnswerJudgment]:
    return [j for j in judgments if j.assessed]


def _brand_cells(judgments: list[AnswerJudgment], brand: str) -> list[BrandCell]:
    """Collapse a brand's per-run judgments into one verdict per (query, engine).

    present = majority of runs; prominence = best (most prominent) seen while
    present; framing = modal. (With temp 0 the runs are usually identical.)
    """
    raw: dict[tuple[str, str], list[tuple[bool, str, str]]] = {}
    intents: dict[tuple[str, str], str] = {}
    for j in _assessed(judgments):
        bj = next((b for b in j.brands if b.brand == brand), None)
        if bj is None:
            continue
        key = (j.query_id, j.engine_name)
        raw.setdefault(key, []).append((bj.present, bj.prominence, bj.framing))
        intents[key] = j.intent

    cells: list[BrandCell] = []
    for key, rows in raw.items():
        present = sum(1 for p, _, _ in rows if p) * 2 >= len(rows)
        present_proms = [prom for p, prom, _ in rows if p]
        prominence = (
            min(present_proms, key=lambda p: _PROM_RANK.get(p, 4))
            if present and present_proms
            else Prominence.ABSENT.value
        )
        framing = Counter(f for _, _, f in rows).most_common(1)[0][0]
        cells.append(BrandCell(key[0], key[1], intents[key], brand, present, prominence, framing))
    return cells


def brand_cells_map(
    judgments: list[AnswerJudgment], brands: list[str]
) -> dict[str, list[BrandCell]]:
    """Every brand's cells from a SINGLE pass over the judgments.

    Equivalent to ``{b: _brand_cells(judgments, b) for b in brands}`` but walks
    the judgments once instead of once per brand — the report needs cells for the
    client and all competitors, so this replaces N full passes with one. Per
    brand the result matches ``_brand_cells`` (same aggregation), so callers use
    them interchangeably.
    """
    wanted = set(brands)
    raw: dict[tuple[str, str, str], list[tuple[bool, str, str]]] = {}
    intents: dict[tuple[str, str, str], str] = {}
    for j in _assessed(judgments):
        for bj in j.brands:
            if bj.brand not in wanted:
                continue
            key = (bj.brand, j.query_id, j.engine_name)
            raw.setdefault(key, []).append((bj.present, bj.prominence, bj.framing))
            intents[key] = j.intent
    out: dict[str, list[BrandCell]] = {b: [] for b in brands}
    for (brand, query_id, engine), rows in raw.items():
        present = sum(1 for p, _, _ in rows if p) * 2 >= len(rows)
        present_proms = [prom for p, prom, _ in rows if p]
        prominence = (
            min(present_proms, key=lambda p: _PROM_RANK.get(p, 4))
            if present and present_proms
            else Prominence.ABSENT.value
        )
        framing = Counter(f for _, _, f in rows).most_common(1)[0][0]
        out[brand].append(
            BrandCell(
                query_id, engine, intents[(brand, query_id, engine)], brand, present,
                prominence, framing,
            )
        )
    return out


def _cells_for(
    judgments: list[AnswerJudgment], brand: str, cells: list[BrandCell] | None
) -> list[BrandCell]:
    """Use precomputed cells when a caller has them, else compute for one brand."""
    return cells if cells is not None else _brand_cells(judgments, brand)


def mention_rate(
    judgments: list[AnswerJudgment], brand: str, *, cells: list[BrandCell] | None = None
) -> float:
    """Fraction of (query, engine) cells where ``brand`` is present."""
    cells = _cells_for(judgments, brand, cells)
    return sum(1 for c in cells if c.present) / len(cells) if cells else 0.0


def visibility_score(
    judgments: list[AnswerJudgment], brand: str, *, cells: list[BrandCell] | None = None
) -> float:
    """Prominence-weighted visibility in [0, 1] — the leaderboard metric.

    Rewards being recommended first over being buried, unlike a flat mention rate.
    """
    cells = _cells_for(judgments, brand, cells)
    return sum(_PROM_SCORE.get(c.prominence, 0.0) for c in cells) / len(cells) if cells else 0.0


def leaderboard(
    judgments: list[AnswerJudgment],
    brands: list[str],
    *,
    cells_map: dict[str, list[BrandCell]] | None = None,
) -> list[tuple[str, float, float]]:
    """(brand, visibility_score, mention_rate) ranked by visibility, best first."""
    cm = cells_map if cells_map is not None else brand_cells_map(judgments, brands)
    rows = [
        (
            b,
            visibility_score(judgments, b, cells=cm.get(b, [])),
            mention_rate(judgments, b, cells=cm.get(b, [])),
        )
        for b in brands
    ]
    return sorted(rows, key=lambda r: r[1], reverse=True)


def framing_breakdown(
    judgments: list[AnswerJudgment], brand: str, *, cells: list[BrandCell] | None = None
) -> dict[str, int]:
    """Counts of positive/neutral/negative framing over the cells where present."""
    counts = Counter(c.framing for c in _cells_for(judgments, brand, cells) if c.present)
    return {f.value: counts.get(f.value, 0) for f in Framing}


def collect_accuracy_flags(judgments: list[AnswerJudgment]) -> list[AccuracyFlag]:
    """All distinct client accuracy flags across the run (deduped by type+claim).

    This is the *display* list (the report's flag listing). The grade penalty uses
    ``grade_penalty_flags`` instead — a coarser dedup that repetition can't game.
    """
    seen: set[tuple[str, str]] = set()
    out: list[AccuracyFlag] = []
    for j in _assessed(judgments):
        for f in j.accuracy_flags:
            key = (f.type, f.claim)
            if key not in seen:
                seen.add(key)
                out.append(f)
    return out


# Severity as an ordinal so "the worst flag of this type wins" is well-defined.
_SEVERITY_RANK: dict[str, int] = {
    Severity.HIGH.value: 0,
    Severity.MED.value: 1,
    Severity.LOW.value: 2,
}


def grade_penalty_flags(judgments: list[AnswerJudgment]) -> list[AccuracyFlag]:
    """The flags that drive the A-F grade penalty, deduped so repetition can't
    compound it (the Layer-2 guard against an over-flagging judge tanking the
    grade).

    WITHIN each answer, the same error *type* counts once, highest severity wins:
    a reply that says "Ring 4" three times has one stale problem, not three —
    `collect_accuracy_flags` keeps all three (different claim text) for display,
    but the grade must not be penalized thrice for one mistake. ACROSS answers,
    each answer's distinct-type problems are kept, so a pervasive error (many
    replies make it) still weighs more than a one-off.
    """
    out: list[AccuracyFlag] = []
    def rank(sev: str) -> int:  # lower rank = worse severity
        return _SEVERITY_RANK.get(sev, 1)

    for j in _assessed(judgments):
        best: dict[str, AccuracyFlag] = {}
        for f in j.accuracy_flags:
            cur = best.get(f.type)
            if cur is None or rank(f.severity) < rank(cur.severity):
                best[f.type] = f
        out.extend(best.values())
    return out


# How much each distinct client accuracy flag drags the grade down. A confident
# wrong claim ("it's $20/mo" when it's free) erodes trust even when visibility is
# fine, so the grade is visibility *discounted* by what the model gets wrong.
# These magnitudes + the band cutoffs are v1 guesses — calibration (Layer 2 of
# the calibration plan) fits them to analyst gut-grades via GradePolicy.
_FLAG_PENALTY: dict[str, float] = {
    Severity.HIGH.value: 0.15,
    Severity.MED.value: 0.07,
    Severity.LOW.value: 0.03,
}
# Penalized-score thresholds, best first. Below the last band is an F.
_GRADE_BANDS: tuple[tuple[float, str], ...] = (
    (0.70, "A"),
    (0.50, "B"),
    (0.30, "C"),
    (0.15, "D"),
)


@dataclass(frozen=True)
class GradePolicy:
    """The tunable Layer-2 parameters of the A-F grade: per-severity flag
    penalties and the score→letter band cutoffs. Defaults are the v1 guesses;
    ``grade_calibration`` fits a policy to human gut-grades."""

    penalty: dict[str, float]
    bands: tuple[tuple[float, str], ...]


DEFAULT_GRADE_POLICY = GradePolicy(penalty=dict(_FLAG_PENALTY), bands=_GRADE_BANDS)


def grade_from(
    raw_visibility: float, flag_severities: list[str], policy: GradePolicy = DEFAULT_GRADE_POLICY
) -> VisibilityGrade:
    """Pure grade core: prominence-weighted visibility discounted by a
    severity-weighted flag penalty, floored at 0, mapped to a band. Shared by
    ``visibility_grade`` (live judgments) and the grade-calibration harness
    (raw numbers), so both score a policy identically.
    """
    low = policy.penalty.get(Severity.LOW.value, 0.0)
    penalty = sum(policy.penalty.get(sev, low) for sev in flag_severities)
    score = max(0.0, raw_visibility - penalty)
    letter = next((g for threshold, g in policy.bands if score >= threshold), "F")
    rationale = f"visibility {raw_visibility:.2f}"
    if flag_severities:
        rationale += f" − {penalty:.2f} for {len(flag_severities)} accuracy flag(s) → {score:.2f}"
    return VisibilityGrade(
        letter=letter,
        score=score,
        raw_score=raw_visibility,
        accuracy_penalty=penalty,
        n_flags=len(flag_severities),
        rationale=rationale,
    )


@dataclass(frozen=True)
class VisibilityGrade:
    """The §1 A-F headline: prominence-weighted visibility, discounted by the
    client accuracy flags the judge raised."""

    letter: str
    score: float  # visibility after the accuracy penalty, 0..1
    raw_score: float  # prominence-weighted visibility before the penalty
    accuracy_penalty: float
    n_flags: int
    rationale: str


def visibility_grade(
    judgments: list[AnswerJudgment],
    client: str,
    policy: GradePolicy = DEFAULT_GRADE_POLICY,
    *,
    cells: list[BrandCell] | None = None,
    flags: list[AccuracyFlag] | None = None,
) -> VisibilityGrade:
    """Roll the client's judge metrics up into an A-F grade.

    Base is the prominence-weighted ``visibility_score`` (recommended-first beats
    buried); each distinct client accuracy flag subtracts a severity-weighted
    penalty, floored at 0. ``policy`` carries the (calibratable) penalty weights
    and band cutoffs. ``cells``/``flags`` let a caller pass already-computed data
    to avoid recomputing. Pure — derives entirely from data already produced.
    """
    raw = visibility_score(judgments, client, cells=cells)
    # The grade penalty uses the deduped problem set, not the per-claim display
    # list — repetition of one error must not multiply the penalty.
    flags = flags if flags is not None else grade_penalty_flags(judgments)
    severities = [f.severity for f in flags]
    return grade_from(raw, severities, policy)


def losing_cells(
    judgments: list[AnswerJudgment],
    client: str,
    competitors: list[str],
    *,
    cells_map: dict[str, list[BrandCell]] | None = None,
) -> list[BrandCell]:
    """(query, engine) cells where the client is absent but a competitor is
    recommended-first — the judge-powered "symptom -> cause" view.
    """
    cm = cells_map if cells_map is not None else brand_cells_map(judgments, [client, *competitors])
    client_present = {(c.query_id, c.engine_name) for c in cm.get(client, []) if c.present}
    losses: list[BrandCell] = []
    for comp in competitors:
        for c in cm.get(comp) or _brand_cells(judgments, comp):
            if (
                c.present
                and c.prominence == Prominence.RECOMMENDED_FIRST.value
                and (c.query_id, c.engine_name) not in client_present
            ):
                losses.append(c)
    return sorted(losses, key=lambda c: (c.query_id, c.engine_name, c.brand))


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def judge_sections(
    judgments: list[AnswerJudgment], client: str, competitors: list[str]
) -> list[str]:
    """The judge-powered §2/§3 section lines (no document header) — the single
    source of truth shared by the standalone judge report and the unified audit
    report: visibility leaderboard, framing, losing queries, and accuracy flags.
    """
    # Compute every brand's cells and the accuracy flags once, then thread them
    # through the section builders (each used to re-walk the judgments).
    brands = [client, *competitors]
    cells_map = brand_cells_map(judgments, brands)
    flags = collect_accuracy_flags(judgments)

    lines: list[str] = []
    grade = visibility_grade(judgments, client, cells=cells_map.get(client))
    lines.append("## AI Visibility Grade")
    lines.append("")
    lines.append(f"**{grade.letter}** — {grade.rationale}")
    lines.append("")

    lines.append("## Visibility Leaderboard")
    lines.append("")
    lines.append("| Brand | Visibility | Mention rate |")
    lines.append("| --- | --- | --- |")
    for brand, vis, mention in leaderboard(judgments, brands, cells_map=cells_map):
        marker = " (client)" if brand == client else ""
        lines.append(f"| {brand}{marker} | {vis:.2f} | {_pct(mention)} |")
    lines.append("")

    fb = framing_breakdown(judgments, client, cells=cells_map.get(client))
    lines.append("## Client Framing")
    lines.append("")
    lines.append(
        f"- positive: {fb['positive']} · neutral: {fb['neutral']} · negative: {fb['negative']}"
    )
    lines.append("")

    losses = losing_cells(judgments, client, competitors, cells_map=cells_map)
    lines.append(f"## Losing Queries ({len(losses)})")
    lines.append("")
    if losses:
        lines.append("| Query | Engine | Competitor recommended first |")
        lines.append("| --- | --- | --- |")
        for c in losses:
            lines.append(f"| {c.query_id} | {c.engine_name} | {c.brand} |")
    else:
        lines.append("_None: the client is present wherever a competitor leads._")
    lines.append("")

    lines.append(f"## Client Accuracy Flags ({len(flags)})")
    lines.append("")
    if not flags:
        lines.append("_None flagged (or no fact sheet → accuracy not assessed)._")
    else:
        lines.append("| Type | Severity | Claim → Reality |")
        lines.append("| --- | --- | --- |")
        for f in flags:
            lines.append(f"| {f.type} | {f.severity} | {f.claim} → {f.reality} |")
    lines.append("")
    return lines


def render_judge_report(
    judgments: list[AnswerJudgment], client: str, competitors: list[str]
) -> str:
    """Standalone judge report: header + the shared judge sections."""
    assessed = _assessed(judgments)
    lines: list[str] = [
        f"# Judge Report — {client}",
        "",
        f"Assessed {len(assessed)} of {len(judgments)} answers.",
        "",
    ]
    lines.extend(judge_sections(judgments, client, competitors))
    return "\n".join(lines)
