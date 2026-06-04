from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.pipeline.judge import BrandJudgment, Judge

__all__ = [
    "GoldItem",
    "CalibrationReport",
    "load_gold_set",
    "compare",
    "calibrate",
    "render_calibration",
]


@dataclass(frozen=True)
class GoldItem:
    """One hand-labeled answer: the inputs + the human verdict per brand."""

    query: str
    answer: str
    client: str
    competitors: list[str]
    fact_sheet: str | None
    labels: dict[str, dict[str, object]]  # brand -> {present, prominence, framing}
    expect_accuracy_flags: bool


@dataclass(frozen=True)
class CalibrationReport:
    """Judge-vs-human agreement — the honest 'can I trust it?' answer."""

    n_items: int
    n_assessed: int
    present_match: int
    present_total: int
    prominence_match: int
    prominence_total: int
    framing_match: int
    framing_total: int
    flag_detection_match: int
    flag_detection_total: int

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
    """Load a hand-labeled gold set from JSON."""
    raw = json.loads(Path(path).read_text())
    items: list[GoldItem] = []
    for it in raw["items"]:
        items.append(
            GoldItem(
                query=str(it["query"]),
                answer=str(it["answer"]),
                client=str(it["client"]),
                competitors=[str(c) for c in it.get("competitors", [])],
                fact_sheet=(str(it["fact_sheet"]) if it.get("fact_sheet") else None),
                labels={str(k): dict(v) for k, v in it.get("labels", {}).items()},
                expect_accuracy_flags=bool(it.get("expect_accuracy_flags", False)),
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


def calibrate(judge: Judge, gold: list[GoldItem]) -> CalibrationReport:
    """Run the judge over the gold set and tally agreement with the human labels."""
    n_assessed = 0
    pm = pt = rm = rt = fm = ft = 0
    flag_match = flag_total = 0
    for item in gold:
        brands, flags, assessed = judge.judge_answer(
            item.query, item.answer, item.client, item.competitors, item.fact_sheet
        )
        if not assessed:
            continue
        n_assessed += 1
        a, b, c, d, e, f = compare(brands, item.labels)
        pm, pt, rm, rt, fm, ft = pm + a, pt + b, rm + c, rt + d, fm + e, ft + f
        if item.fact_sheet:
            flag_total += 1
            if (len(flags) > 0) == item.expect_accuracy_flags:
                flag_match += 1
    return CalibrationReport(
        n_items=len(gold),
        n_assessed=n_assessed,
        present_match=pm,
        present_total=pt,
        prominence_match=rm,
        prominence_total=rt,
        framing_match=fm,
        framing_total=ft,
        flag_detection_match=flag_match,
        flag_detection_total=flag_total,
    )


def render_calibration(report: CalibrationReport) -> str:
    """Markdown agreement report — 'matches our human labels X% of the time'."""
    return "\n".join(
        [
            "# Judge Calibration",
            "",
            f"Gold items: {report.n_items} · assessed: {report.n_assessed}",
            "",
            "| Dimension | Agreement | n |",
            "| --- | --- | --- |",
            f"| present | {report.present_agreement:.0%} | {report.present_total} |",
            f"| prominence | {report.prominence_agreement:.0%} | {report.prominence_total} |",
            f"| framing | {report.framing_agreement:.0%} | {report.framing_total} |",
            f"| accuracy-flags | {report.flag_detection_agreement:.0%} | {report.flag_detection_total} |",
            "",
            "_Build the gold set by hand-labeling ~20–40 real answers; this is the_",
            "_honest check on an AI grading other AIs._",
            "",
        ]
    )


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
    print(render_calibration(calibrate(judge, gold)))
