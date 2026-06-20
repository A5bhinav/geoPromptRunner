from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from src.pipeline.judge import AccuracyFlag, BrandJudgment, Judge
from src.pipeline.judge_cache import JudgeCache
from src.storage.models import Framing, Prominence, Severity

__all__ = [
    "GoldFlag",
    "GoldItem",
    "FlagStats",
    "CalibrationReport",
    "load_gold_set",
    "compare",
    "match_flags",
    "calibrate",
    "render_calibration",
]

# Severity as an ordinal so "within one band" is meaningful (high↔low is 2 apart).
_SEV_RANK: dict[str, int] = {Severity.HIGH.value: 0, Severity.MED.value: 1, Severity.LOW.value: 2}


@dataclass(frozen=True)
class GoldFlag:
    """One real client accuracy error a human says an answer makes.

    ``type`` is an ``AccuracyFlagType`` value (the claim dimension — pricing,
    model, feature, identity, competitor-confusion); ``severity`` a ``Severity``
    value; ``note`` is free text for the labeler (not scored).
    """

    type: str
    severity: str
    note: str = ""


@dataclass(frozen=True)
class GoldItem:
    """One hand-labeled answer: the inputs + the human verdict per brand.

    ``expected_flags`` is the human's typed list of the real client errors the
    answer makes (empty list = "checked, accurate"). It is ``None`` for legacy
    items that only carry the old ``expect_accuracy_flags`` boolean — those still
    feed the binary flag-detection metric but not precision/recall.

    ``fact_sheet_candidates`` are claims the answer makes that the fact sheet
    does NOT cover, so the judge should not flag them — the labeling counterpart
    to the over-flagging fix. ``engine``/``category`` enable the per-slice
    breakdowns; both optional.
    """

    query: str
    answer: str
    client: str
    competitors: list[str]
    fact_sheet: str | None
    labels: dict[str, dict[str, object]]  # brand -> {present, prominence, framing}
    expect_accuracy_flags: bool  # legacy binary: "should ≥1 client flag fire?"
    expected_flags: list[GoldFlag] | None = None  # None = not typed-labeled (legacy)
    fact_sheet_candidates: list[str] = field(default_factory=list)
    engine: str | None = None
    category: str | None = None

    @property
    def has_typed_flags(self) -> bool:
        """True once a human has provided the typed gold flags (even if empty)."""
        return self.expected_flags is not None


@dataclass(frozen=True)
class FlagStats:
    """Accuracy-flag agreement, type-matched (multiset by AccuracyFlagType).

    A judge flag matches a gold flag when their type agrees — robust to wording,
    and a mis-typed judge flag falls out as both a false positive (its type has
    no gold match) and a false negative (the real flag's type goes unmatched), so
    mis-typing shows up in precision *and* recall rather than a separate number.
    """

    tp: int = 0  # judge flags that matched a gold flag by type
    fp: int = 0  # judge flags with no gold match — the over-flagging signal
    fn: int = 0  # gold flags the judge missed
    severity_exact: int = 0  # matched pairs with identical severity
    severity_within_one: int = 0  # matched pairs within one severity band
    severity_total: int = 0  # matched pairs (severity denominator)
    n_items: int = 0  # typed-labeled items with a fact sheet (the precision/recall base)
    gold_types: Counter[str] = field(default_factory=Counter)
    judge_types: Counter[str] = field(default_factory=Counter)

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 1.0  # no judge flags + no golds = trivially clean

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 1.0

    @property
    def severity_exact_rate(self) -> float:
        return self.severity_exact / self.severity_total if self.severity_total else 0.0

    @property
    def severity_within_one_rate(self) -> float:
        return self.severity_within_one / self.severity_total if self.severity_total else 0.0


@dataclass(frozen=True)
class CalibrationReport:
    """Judge-vs-human agreement — the honest 'can I trust the flags?' answer."""

    n_items: int
    n_assessed: int
    present_match: int
    present_total: int
    prominence_match: int
    prominence_total: int
    framing_match: int
    framing_total: int
    # Legacy binary: did the judge flag at least one client error when expected?
    flag_detection_match: int
    flag_detection_total: int
    # Typed flag agreement + where prominence/framing err.
    flags: FlagStats = field(default_factory=FlagStats)
    prominence_confusion: dict[tuple[str, str], int] = field(default_factory=dict)
    framing_confusion: dict[tuple[str, str], int] = field(default_factory=dict)
    # Slices (empty on sub-reports to avoid recursion).
    by_engine: dict[str, CalibrationReport] = field(default_factory=dict)
    by_category: dict[str, CalibrationReport] = field(default_factory=dict)

    @staticmethod
    def _rate(match: int, total: int) -> float:
        return match / total if total else 0.0

    @property
    def present_agreement(self) -> float:
        return self._rate(self.present_match, self.present_total)

    @property
    def prominence_agreement(self) -> float:
        return self._rate(self.prominence_match, self.prominence_total)

    @property
    def framing_agreement(self) -> float:
        return self._rate(self.framing_match, self.framing_total)

    @property
    def flag_detection_agreement(self) -> float:
        return self._rate(self.flag_detection_match, self.flag_detection_total)


def load_gold_set(path: str | Path) -> list[GoldItem]:
    """Load a hand-labeled gold set from JSON (v2; legacy items still load).

    v2 items carry ``expected_flags`` (typed) and optional
    ``fact_sheet_candidates``/``engine``/``category``. Legacy items with only the
    ``expect_accuracy_flags`` boolean load with ``expected_flags=None`` and feed
    the binary metric only.
    """
    raw = json.loads(Path(path).read_text())
    items: list[GoldItem] = []
    for it in raw["items"]:
        if "expected_flags" in it:
            parsed = [
                GoldFlag(
                    type=str(f.get("type", "")),
                    severity=str(f.get("severity", Severity.MED.value)),
                    note=str(f.get("note", "")),
                )
                for f in it["expected_flags"]
                if isinstance(f, dict)
            ]
            expected: list[GoldFlag] | None = parsed
            expect_bool = len(parsed) > 0
        else:
            expected = None  # legacy: no typed labels
            expect_bool = bool(it.get("expect_accuracy_flags", False))
        items.append(
            GoldItem(
                query=str(it["query"]),
                answer=str(it["answer"]),
                client=str(it["client"]),
                competitors=[str(c) for c in it.get("competitors", [])],
                fact_sheet=(str(it["fact_sheet"]) if it.get("fact_sheet") else None),
                labels={str(k): dict(v) for k, v in it.get("labels", {}).items()},
                expect_accuracy_flags=expect_bool,
                expected_flags=expected,
                fact_sheet_candidates=[str(c) for c in it.get("fact_sheet_candidates", [])],
                engine=(str(it["engine"]) if it.get("engine") else None),
                category=(str(it["category"]) if it.get("category") else None),
            )
        )
    return items


def compare(
    brand_judgments: list[BrandJudgment], labels: dict[str, dict[str, object]]
) -> tuple[int, int, int, int, int, int]:
    """Compare judge brand-judgments to human labels for one item (pure).

    Returns (present_match, present_total, prom_match, prom_total, fram_match,
    fram_total) — one comparison per labeled brand that the judge also scored.
    """
    by_brand = {b.brand: b for b in brand_judgments}
    pm = pt = rm = rt = fm = ft = 0
    for brand, label in labels.items():
        bj = by_brand.get(brand)
        if bj is None:
            continue
        pt += 1
        if bj.present == bool(label.get("present")):
            pm += 1
        rt += 1
        if bj.prominence == str(label.get("prominence")):
            rm += 1
        ft += 1
        if bj.framing == str(label.get("framing")):
            fm += 1
    return pm, pt, rm, rt, fm, ft


def _within_one_severity(a: str, b: str) -> bool:
    ra, rb = _SEV_RANK.get(a), _SEV_RANK.get(b)
    if ra is None or rb is None:
        return False
    return abs(ra - rb) <= 1


def match_flags(
    judge_flags: list[AccuracyFlag], gold_flags: list[GoldFlag]
) -> FlagStats:
    """Type-multiset match judge flags against gold flags for ONE item (pure).

    For each AccuracyFlagType, the judge and gold flags are paired up to the
    smaller count; the rest are false positives (judge over-flagged) or false
    negatives (judge missed). Severity is compared on the paired flags.
    """
    gold_by_type: dict[str, list[GoldFlag]] = defaultdict(list)
    judge_by_type: dict[str, list[AccuracyFlag]] = defaultdict(list)
    for g in gold_flags:
        gold_by_type[g.type].append(g)
    for j in judge_flags:
        judge_by_type[j.type].append(j)

    tp = sev_exact = sev_within = sev_total = 0
    for ftype, golds in gold_by_type.items():
        judges = judge_by_type.get(ftype, [])
        matched = min(len(golds), len(judges))
        tp += matched
        for g, j in zip(golds[:matched], judges[:matched], strict=True):
            sev_total += 1
            if g.severity == j.severity:
                sev_exact += 1
            if _within_one_severity(g.severity, j.severity):
                sev_within += 1
    return FlagStats(
        tp=tp,
        fp=len(judge_flags) - tp,
        fn=len(gold_flags) - tp,
        severity_exact=sev_exact,
        severity_within_one=sev_within,
        severity_total=sev_total,
        n_items=1,
        gold_types=Counter(g.type for g in gold_flags),
        judge_types=Counter(j.type for j in judge_flags),
    )


def _merge_flag_stats(stats: list[FlagStats]) -> FlagStats:
    gold_types: Counter[str] = Counter()
    judge_types: Counter[str] = Counter()
    for s in stats:
        gold_types.update(s.gold_types)
        judge_types.update(s.judge_types)
    return FlagStats(
        tp=sum(s.tp for s in stats),
        fp=sum(s.fp for s in stats),
        fn=sum(s.fn for s in stats),
        severity_exact=sum(s.severity_exact for s in stats),
        severity_within_one=sum(s.severity_within_one for s in stats),
        severity_total=sum(s.severity_total for s in stats),
        n_items=sum(s.n_items for s in stats),
        gold_types=gold_types,
        judge_types=judge_types,
    )


@dataclass(frozen=True)
class _Eval:
    """One judged gold item: the human item + the judge's verdict."""

    item: GoldItem
    brands: list[BrandJudgment]
    flags: list[AccuracyFlag]
    assessed: bool


def _tally(evals: list[_Eval], breakdowns: bool = True) -> CalibrationReport:
    """Aggregate judged items into a report (pure). Recurses into per-engine and
    per-category sub-reports only at the top level."""
    assessed = [e for e in evals if e.assessed]
    pm = pt = rm = rt = fm = ft = 0
    flag_match = flag_total = 0
    prom_conf: dict[tuple[str, str], int] = {}
    fram_conf: dict[tuple[str, str], int] = {}
    flag_stats: list[FlagStats] = []

    for ev in assessed:
        a, b, c, d, e, f = compare(ev.brands, ev.item.labels)
        pm, pt, rm, rt, fm, ft = pm + a, pt + b, rm + c, rt + d, fm + e, ft + f

        by_brand = {bj.brand: bj for bj in ev.brands}
        for brand, label in ev.item.labels.items():
            bj = by_brand.get(brand)
            if bj is None:
                continue
            pk = (str(label.get("prominence")), bj.prominence)
            prom_conf[pk] = prom_conf.get(pk, 0) + 1
            fk = (str(label.get("framing")), bj.framing)
            fram_conf[fk] = fram_conf.get(fk, 0) + 1

        # Legacy binary flag detection (any fact-sheet item).
        if ev.item.fact_sheet:
            flag_total += 1
            if (len(ev.flags) > 0) == ev.item.expect_accuracy_flags:
                flag_match += 1
        # Typed precision/recall: only items a human typed-labeled, with a sheet.
        if ev.item.fact_sheet and ev.item.expected_flags is not None:
            flag_stats.append(match_flags(ev.flags, ev.item.expected_flags))

    by_engine: dict[str, CalibrationReport] = {}
    by_category: dict[str, CalibrationReport] = {}
    if breakdowns:
        engines = sorted({e.item.engine for e in evals if e.item.engine})
        by_engine = {
            eng: _tally([e for e in evals if e.item.engine == eng], breakdowns=False)
            for eng in engines
        }
        cats = sorted({e.item.category for e in evals if e.item.category})
        by_category = {
            cat: _tally([e for e in evals if e.item.category == cat], breakdowns=False)
            for cat in cats
        }

    return CalibrationReport(
        n_items=len(evals),
        n_assessed=len(assessed),
        present_match=pm,
        present_total=pt,
        prominence_match=rm,
        prominence_total=rt,
        framing_match=fm,
        framing_total=ft,
        flag_detection_match=flag_match,
        flag_detection_total=flag_total,
        flags=_merge_flag_stats(flag_stats),
        prominence_confusion=prom_conf,
        framing_confusion=fram_conf,
        by_engine=by_engine,
        by_category=by_category,
    )


def calibrate(
    judge: Judge,
    gold: list[GoldItem],
    progress: bool = False,
    cache: JudgeCache | None = None,
) -> CalibrationReport:
    """Run the judge over the gold set and tally agreement with the human labels.

    ``cache`` (optional) reuses verdicts keyed by the judge prompt + inputs, so a
    re-run over an unchanged gold set is free and byte-identical (which also
    removes the residual temperature-0 jitter on repeats). Editing the judge
    prompt changes the key and correctly forces a fresh judge pass.
    """
    evals: list[_Eval] = []
    for i, item in enumerate(gold, start=1):
        brands, flags, assessed = judge.judge_answer_cached(
            item.query, item.answer, item.client, item.competitors, item.fact_sheet, cache
        )
        evals.append(_Eval(item=item, brands=brands, flags=flags, assessed=assessed))
        if progress and (i % 10 == 0 or i == len(gold)):
            print(f"  calibrated {i}/{len(gold)} items", flush=True)
    return _tally(evals)


def _confusion_table(
    title: str, confusion: dict[tuple[str, str], int], order: list[str]
) -> list[str]:
    """Render a gold(row)-vs-judge(col) confusion matrix; off-diagonal = errors."""
    present = [v for v in order if any(g == v or j == v for (g, j) in confusion)]
    if not present:
        return []
    header = "| gold \\ judge | " + " | ".join(present) + " |"
    lines = [f"### {title} confusion (gold ↓ / judge →)", "", header]
    lines.append("| --- |" + " --- |" * len(present))
    for g in present:
        row = [str(confusion.get((g, j), 0)) for j in present]
        lines.append(f"| {g} | " + " | ".join(row) + " |")
    lines.append("")
    return lines


def _flag_section(stats: FlagStats) -> list[str]:
    if stats.n_items == 0:
        return ["_No typed-flag gold items yet — only the binary flag-detection check ran._", ""]
    type_rows = sorted(set(stats.gold_types) | set(stats.judge_types))
    lines = [
        f"Typed-flag items: {stats.n_items} · judge flags: {stats.tp + stats.fp} · "
        f"gold flags: {stats.tp + stats.fn}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| **flag precision** (TP/judge) | {stats.precision:.0%} |",
        f"| **flag recall** (TP/gold) | {stats.recall:.0%} |",
        f"| severity exact (matched) | {stats.severity_exact_rate:.0%} |",
        f"| severity within-one (matched) | {stats.severity_within_one_rate:.0%} |",
        f"| TP / FP / FN | {stats.tp} / {stats.fp} / {stats.fn} |",
        "",
    ]
    if type_rows:
        lines.append("Flag-type tally (gold vs judge — mis-typing shows as a column mismatch):")
        lines.append("")
        lines.append("| Type | gold | judge |")
        lines.append("| --- | --- | --- |")
        for t in type_rows:
            lines.append(f"| {t} | {stats.gold_types.get(t, 0)} | {stats.judge_types.get(t, 0)} |")
        lines.append("")
    return lines


def _agreement_rows(report: CalibrationReport) -> list[str]:
    flag_agree, flag_n = report.flag_detection_agreement, report.flag_detection_total
    rows = [
        "| Dimension | Agreement | n |",
        "| --- | --- | --- |",
        f"| present | {report.present_agreement:.0%} | {report.present_total} |",
        f"| prominence | {report.prominence_agreement:.0%} | {report.prominence_total} |",
        f"| framing | {report.framing_agreement:.0%} | {report.framing_total} |",
    ]
    if report.flags.n_items:
        fs = report.flags
        rows.append(f"| flag precision | {fs.precision:.0%} | {fs.tp + fs.fp} |")
        rows.append(f"| flag recall | {fs.recall:.0%} | {fs.tp + fs.fn} |")
    rows.append(f"| accuracy-flags (binary) | {flag_agree:.0%} | {flag_n} |")
    return rows


def render_calibration(report: CalibrationReport) -> str:
    """Markdown agreement report: headline table, flag precision/recall, severity,
    confusion matrices, and per-engine / per-category breakdowns."""
    prom_order = [p.value for p in Prominence]
    fram_order = [f.value for f in Framing]
    lines: list[str] = [
        "# Judge Calibration",
        "",
        f"Gold items: {report.n_items} · assessed: {report.n_assessed}",
        "",
        "## Agreement (headline)",
        "",
        *_agreement_rows(report),
        "",
        "## Accuracy flags (typed)",
        "",
        *_flag_section(report.flags),
        *_confusion_table("Prominence", report.prominence_confusion, prom_order),
        *_confusion_table("Framing", report.framing_confusion, fram_order),
    ]

    for title, slices in (("engine", report.by_engine), ("category", report.by_category)):
        if not slices:
            continue
        lines.append(f"## By {title}")
        lines.append("")
        lines.append(f"| {title} | present | prominence | framing | flag prec | flag recall | n |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for name, sub in slices.items():
            prec = f"{sub.flags.precision:.0%}" if sub.flags.n_items else "—"
            rec = f"{sub.flags.recall:.0%}" if sub.flags.n_items else "—"
            lines.append(
                f"| {name} | {sub.present_agreement:.0%} | {sub.prominence_agreement:.0%} | "
                f"{sub.framing_agreement:.0%} | {prec} | {rec} | {sub.present_total} |"
            )
        lines.append("")

    lines += [
        "_Build the gold set by hand-labeling real answers (blind first, never from_",
        "_the judge's own verdicts); report on held-out items. This is the honest_",
        "_check on an AI grading other AIs._",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    sample = Path(__file__).resolve().parents[2] / "data" / "sample_gold.json"
    gold = load_gold_set(sample)
    try:
        judge = Judge()
    except ValueError as exc:
        print(f"Cannot calibrate: {exc}")
        raise SystemExit(0) from None
    print(render_calibration(calibrate(judge, gold, progress=True)))
