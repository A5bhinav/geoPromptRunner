from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.pipeline import metrics
from src.pipeline.judge import AccuracyFlag, AnswerJudgment, Framing, Prominence

__all__ = [
    "BrandLabel",
    "BrandCell",
    "LeaderRow",
    "PROMINENCE_ORDER",
    "PROMINENCE_LABELS",
    "brand_cells_map",
    "mention_rate",
    "prominence_distribution",
    "median_prominence",
    "prominence_label",
    "leaderboard",
    "framing_breakdown",
    "stability",
    "stability_by_engine",
    "split_cells",
    "collect_accuracy_flags",
    "losing_cells",
    "judge_sections",
    "render_judge_report",
]

# Prominence as an ordinal (best -> worst). An ORDINAL, and only an ordinal.
#
# There is no weight table here any more. `visibility_score()` used to turn these
# five levels into a 0..1 composite from hardcoded weights (1.0 / 0.6 / 0.3 / 0.1)
# that nothing derived, and `leaderboard()` SORTED BY IT — so the competitor
# ranking a client read was ordered by an invented number. A composite that orders
# a client-facing ranking is a score whether or not its value is printed, which
# the "no invented scores" rule forbids outright (spec TR-T0).
#
# Prominence now travels as a DISTRIBUTION across the five levels, or as a median
# ordinal LABEL ("mid-pack") — never as a decimal, never as a sort key. The rank
# below exists for ordering the levels themselves (which of two labels is better),
# not for arithmetic across them: the gap between "recommended first" and
# "mid-pack" is not measurably the same size as the gap between "buried" and
# "also-ran", and averaging them asserts that it is.
_PROM_RANK: dict[str, int] = {
    Prominence.RECOMMENDED_FIRST.value: 0,
    Prominence.MID_PACK.value: 1,
    Prominence.BURIED.value: 2,
    Prominence.ALSO_RAN.value: 3,
    Prominence.ABSENT.value: 4,
}

#: The five levels, best first. The fixed order every distribution renders in —
#: a chart whose axis order moves between editions cannot be compared at a glance.
PROMINENCE_ORDER: tuple[str, ...] = tuple(
    sorted(_PROM_RANK, key=lambda p: _PROM_RANK[p])
)

#: Client-facing wording for each level. Sentence case; the report never prints
#: the raw enum value (`recommended_first` is a join key, not content).
PROMINENCE_LABELS: dict[str, str] = {
    Prominence.RECOMMENDED_FIRST.value: "Recommended first",
    Prominence.MID_PACK.value: "Mid-pack",
    Prominence.BURIED.value: "Buried",
    Prominence.ALSO_RAN.value: "Also-ran",
    Prominence.ABSENT.value: "Absent",
}


#: One run's read of one brand: (present, prominence, framing).
BrandLabel = tuple[bool, str, str]


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
    # How many runs backed this cell, and how many of them produced the modal label.
    # The collapse above is lossy by design — these two keep the evidence behind it,
    # so a 3-of-5 coin flip and a 5-of-5 unanimous read stay distinguishable (see the
    # stability section below). Defaults describe an unrepeated cell, which
    # `metrics.MIN_RUNS_FOR_STABILITY` correctly treats as carrying no evidence.
    runs: int = 1
    agree_runs: int = 1


def _assessed(judgments: list[AnswerJudgment]) -> list[AnswerJudgment]:
    return [j for j in judgments if j.assessed]


def _collapse(rows: list[BrandLabel]) -> tuple[bool, str, str, int, int]:
    """Collapse one cell's per-run labels to (present, prominence, framing, runs,
    agree_runs).

    present = majority of runs; prominence = best (most prominent) seen while present;
    framing = modal. ``agree_runs`` counts the runs matching the modal *whole* label,
    which is the reproducibility question — a cell can agree on presence while its
    prominence wobbles, and that is a split read, not a stable one.

    Shared by ``_brand_cells`` and ``brand_cells_map`` so the one-brand and all-brands
    paths cannot drift apart.
    """
    present = sum(1 for p, _, _ in rows if p) * 2 >= len(rows)
    present_proms = [prom for p, prom, _ in rows if p]
    prominence = (
        min(present_proms, key=lambda p: _PROM_RANK.get(p, 4))
        if present and present_proms
        else Prominence.ABSENT.value
    )
    present_framings = [f for p, _, f in rows if p]
    framing = (
        Counter(present_framings).most_common(1)[0][0]
        if present_framings
        else Framing.NEUTRAL.value
    )
    agree_runs = Counter(rows).most_common(1)[0][1] if rows else 0
    return present, prominence, framing, len(rows), agree_runs


def _brand_cells(judgments: list[AnswerJudgment], brand: str) -> list[BrandCell]:
    """Collapse a brand's per-run judgments into one verdict per (query, engine)."""
    raw: dict[tuple[str, str], list[BrandLabel]] = {}
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
        present, prominence, framing, runs, agree = _collapse(rows)
        cells.append(
            BrandCell(
                key[0], key[1], intents[key], brand, present, prominence, framing, runs, agree
            )
        )
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
    raw: dict[tuple[str, str, str], list[BrandLabel]] = {}
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
        present, prominence, framing, runs, agree = _collapse(rows)
        out[brand].append(
            BrandCell(
                query_id,
                engine,
                intents[(brand, query_id, engine)],
                brand,
                present,
                prominence,
                framing,
                runs,
                agree,
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


def prominence_distribution(cells: list[BrandCell]) -> dict[str, int]:
    """How many cells landed at each of the five prominence levels.

    The reported form of prominence: counts, in a fixed order, every level
    present even at zero. A distribution is auditable — a client can add the
    numbers up and get the denominator back — where a weighted average is a
    claim about the spacing between levels that nothing in the data supports.
    """
    counts = Counter(c.prominence if c.present else Prominence.ABSENT.value for c in cells)
    return {level: counts.get(level, 0) for level in PROMINENCE_ORDER}


def median_prominence(cells: list[BrandCell]) -> str | None:
    """The median prominence level ACROSS THE CELLS WHERE THE BRAND IS PRESENT.

    Returns the raw level value, or ``None`` when the brand is present nowhere —
    which is "no typical position", not "absent-typical". A brand appearing in one
    cell in twelve has a median position in that one cell, and the mention rate
    beside it is what says how rare that is; conflating the two into one number is
    exactly what the composite did.

    The median (not the mean) because these are ordered categories, not
    quantities: the middle observation is well-defined, an average is not. On an
    even count it takes the WORSE of the two middle levels — the conservative
    read, so a tie never rounds a client's position up.
    """
    present = sorted(
        (c.prominence for c in cells if c.present),
        key=lambda p: _PROM_RANK.get(p, len(_PROM_RANK)),
    )
    if not present:
        return None
    # Sorted best -> worst, so index n//2 is the middle observation on an odd
    # count and the WORSE of the two middles on an even one.
    return present[len(present) // 2]


def prominence_label(level: str | None) -> str:
    """Client-facing wording for a level. ``None`` → an em dash, never "absent"."""
    if level is None:
        return "—"
    return PROMINENCE_LABELS.get(level, level.replace("_", " "))


@dataclass(frozen=True)
class LeaderRow:
    """One brand's row of the competitive leaderboard.

    Deliberately not a tuple: the old ``(brand, visibility, mention_rate)`` shape
    put a composite in the position callers read as "the number", and swapping
    two floats in a tuple is a silent change. Prominence travels as a label and a
    distribution, and it is never the sort key.
    """

    brand: str
    mention_rate: float
    present_cells: int
    cells: int
    prominence: str | None
    distribution: dict[str, int]


def leaderboard(
    judgments: list[AnswerJudgment],
    brands: list[str],
    *,
    cells_map: dict[str, list[BrandCell]] | None = None,
) -> list[LeaderRow]:
    """The competitive ranking, **sorted by mention rate**, best first.

    Mention rate is a measured quantity with a denominator a client can check.
    Ties break on brand name so the order is stable between editions rather than
    dependent on dict iteration — a leaderboard that reshuffles when nothing
    moved reads as movement.
    """
    cm = cells_map if cells_map is not None else brand_cells_map(judgments, brands)
    rows = [
        LeaderRow(
            brand=b,
            mention_rate=mention_rate(judgments, b, cells=cm.get(b, [])),
            present_cells=sum(1 for c in cm.get(b, []) if c.present),
            cells=len(cm.get(b, [])),
            prominence=median_prominence(cm.get(b, [])),
            distribution=prominence_distribution(cm.get(b, [])),
        )
        for b in brands
    ]
    return sorted(rows, key=lambda r: (-r.mention_rate, r.brand))


def framing_breakdown(
    judgments: list[AnswerJudgment], brand: str, *, cells: list[BrandCell] | None = None
) -> dict[str, int]:
    """Counts of positive/neutral/negative framing over the cells where present."""
    counts = Counter(c.framing for c in _cells_for(judgments, brand, cells) if c.present)
    return {f.value: counts.get(f.value, 0) for f in Framing}


# --- Stability of the judge read across repeat runs -----------------------------
#
# The judge path is what the report actually renders, so the run-count evidence has to
# live here too — `metrics.stability` covers only the regex fallback. Same rationale
# and the same scale (both roll up through `metrics.stability_from`): with one engine
# pinned to a model that cannot take a temperature, "the client is present here" needs
# to be separable from "the client was present in three of five tries here".


def stability(cells: list[BrandCell]) -> metrics.Stability:
    """How reproducibly ``cells`` returned the same (present, prominence, framing)."""
    return metrics.stability_from((c.agree_runs, c.runs) for c in cells)


def stability_by_engine(cells: list[BrandCell]) -> dict[str, metrics.Stability]:
    """Stability per engine — the split that motivates the metric, since the engines
    no longer share a sampling regime."""
    by_engine: dict[str, list[BrandCell]] = {}
    for c in cells:
        by_engine.setdefault(c.engine_name, []).append(c)
    return {name: stability(cs) for name, cs in by_engine.items()}


def split_cells(cells: list[BrandCell]) -> list[BrandCell]:
    """The repeated cells whose runs disagreed, worst agreement first.

    The drill-down behind the summary number: these are the cells whose verdict a
    re-run could flip, so they are the ones a finding must not rest on alone.
    """
    unstable = [
        c for c in cells if c.runs >= metrics.MIN_RUNS_FOR_STABILITY and c.agree_runs < c.runs
    ]
    return sorted(unstable, key=lambda c: (c.agree_runs / c.runs, c.query_id, c.engine_name))


def collect_accuracy_flags(judgments: list[AnswerJudgment]) -> list[AccuracyFlag]:
    """All distinct client accuracy flags across the run (deduped by type+claim).

    This is the *display* list (the report's flag listing). The findings pipeline
    re-clusters these into themes; nothing in this module scores them.
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



def losing_cells(
    judgments: list[AnswerJudgment],
    client: str,
    competitors: list[str],
    *,
    cells_map: dict[str, list[BrandCell]] | None = None,
) -> list[BrandCell]:
    """(query, engine) cells where the client is absent but a competitor is
    recommended-first — the judge-powered "symptom -> cause" view.

    One row per losing *cell*, not per (competitor, cell): because each brand's
    cell prominence is aggregated as the best seen across runs, two rivals can both
    read recommended-first for the same cell, which would otherwise emit that cell
    twice and inflate the "Losing Queries (N)" count. When several rivals lead a
    cell we keep one deterministic representative (matches metrics.losing_queries,
    which collapses to one row per cell).
    """
    cm = cells_map if cells_map is not None else brand_cells_map(judgments, [client, *competitors])
    client_present = {(c.query_id, c.engine_name) for c in cm.get(client, []) if c.present}
    best_by_cell: dict[tuple[str, str], BrandCell] = {}
    for comp in competitors:
        for c in cm.get(comp) or _brand_cells(judgments, comp):
            if (
                c.present
                and c.prominence == Prominence.RECOMMENDED_FIRST.value
                and (c.query_id, c.engine_name) not in client_present
            ):
                cell = (c.query_id, c.engine_name)
                current = best_by_cell.get(cell)
                if current is None or c.brand < current.brand:
                    best_by_cell[cell] = c
    return sorted(best_by_cell.values(), key=lambda c: (c.query_id, c.engine_name, c.brand))


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
    # NO GRADE SECTION. There is no letter and no composite anywhere in this
    # report: every headline number is counted or measured (spec TR-T0). What
    # opened this document used to be a letter derived from a weighted prominence
    # score nobody could audit or act on.
    lines.append("## Visibility Leaderboard")
    lines.append("")
    lines.append("| Brand | Mention rate | Typical position |")
    lines.append("| --- | --- | --- |")
    for row in leaderboard(judgments, brands, cells_map=cells_map):
        marker = " (client)" if row.brand == client else ""
        # Count first, percentage parenthetical — a bare rate at this sample size
        # is the most misleading thing this table could print.
        rate = f"{row.present_cells} of {row.cells} ({_pct(row.mention_rate)})"
        lines.append(f"| {row.brand}{marker} | {rate} | {prominence_label(row.prominence)} |")
    lines.append("")

    client_cells = cells_map.get(client) or []
    per_engine = stability_by_engine(client_cells)
    if any(s.is_measured for s in per_engine.values()):
        lines.append("## Verdict Stability")
        lines.append("")
        lines.append("| Engine | Repeated cells | Split | Mean agreement |")
        lines.append("| --- | --- | --- | --- |")
        for engine, s in sorted(per_engine.items()):
            if not s.is_measured:
                continue
            lines.append(
                f"| {engine} | {s.repeated_cells} | {s.split_cells} | {_pct(s.mean_agreement)} |"
            )
        lines.append("")
        splits = split_cells(client_cells)
        if splits:
            lines.append(
                f"_{len(splits)} cell(s) disagreed across their runs — the verdict there "
                "could flip on a re-run. Listed worst first:_"
            )
            lines.append("")
            for c in splits[:10]:
                lines.append(
                    f"- {c.query_id} · {c.engine_name} — {c.agree_runs}/{c.runs} runs agreed"
                )
            if len(splits) > 10:
                lines.append(f"- …and {len(splits) - 10} more")
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
