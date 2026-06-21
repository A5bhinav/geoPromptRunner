"""Calibration harness for the Cat 3/4 content judge (impl guide §4.5).

The non-negotiable gate before the subjective judge is trusted in front of a
client (plan §7): score judge-vs-human agreement on a hand-labeled gold set with
**quadratic-weighted Cohen's kappa** (partial-vs-fail should cost less than
pass-vs-fail) and block ship if κ < 0.6.

Kappa is implemented in pure Python — like the link-graph PageRank, it avoids
pulling scipy/sklearn for a handful of small formulas. The harness is ready to
run the moment the gold set lands; the scoring functions are pure and tested now.

Gold-set format — one JSON object per line (JSONL):
    {"page_url": "...", "text": "<page main text>",
     "labels": {"answer_first_lead": "pass", "original_data": "fail", ...}}
Labels are the rubric ``check_id``s (see content_judge.CONTENT_CHECKS) → one of
pass | partial | fail. Omit a check to leave it unlabeled for that page.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.audit.checks.content_judge import ContentJudgeResult

__all__ = [
    "GoldExample",
    "CheckCalibration",
    "KAPPA_SHIP_THRESHOLD",
    "ORDINAL_LABELS",
    "load_gold_set",
    "quadratic_weighted_kappa",
    "score_check",
    "score_against_gold",
    "flag_disagreements",
    "meets_ship_bar",
]

logger = logging.getLogger(__name__)

# Block ship below this judge-vs-human kappa (§4.5).
KAPPA_SHIP_THRESHOLD = 0.6

# Ordinal label order for the quadratic weights (distance matters: pass↔fail is
# the costliest disagreement, pass↔partial the cheapest). "unknown" is an
# abstention, excluded from kappa and counted separately.
ORDINAL_LABELS = ("fail", "partial", "pass")


@dataclass
class GoldExample:
    page_url: str
    text: str
    labels: dict[str, str]  # check_id -> pass|partial|fail


@dataclass
class CheckCalibration:
    check_id: str
    n: int  # human/judge pairs scored (excludes judge-unknown abstentions)
    n_unknown: int  # judge abstained where a human label existed
    kappa: float | None  # None when there's nothing (or one class) to score
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def ship_ok(self) -> bool:
        return self.kappa is not None and self.kappa >= KAPPA_SHIP_THRESHOLD


def load_gold_set(path: str) -> list[GoldExample]:
    """Load a JSONL gold set. Malformed lines are skipped with a warning."""
    examples: list[GoldExample] = []
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                examples.append(
                    GoldExample(
                        page_url=str(obj["page_url"]),
                        text=str(obj.get("text", "")),
                        labels={str(k): str(v) for k, v in dict(obj.get("labels", {})).items()},
                    )
                )
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning("skipping malformed gold line %d: %s", lineno, exc)
    return examples


def quadratic_weighted_kappa(
    human: list[str], judge: list[str], labels: tuple[str, ...] = ORDINAL_LABELS
) -> float | None:
    """Quadratic-weighted Cohen's kappa over ordinal ``labels``.

    Returns ``None`` if there are no pairs or only a single label is ever used (no
    variance — kappa undefined). Pairs whose label isn't in ``labels`` are dropped.
    """
    index = {label: i for i, label in enumerate(labels)}
    pairs = [(h, j) for h, j in zip(human, judge, strict=True) if h in index and j in index]
    if not pairs:
        return None
    k = len(labels)
    observed = [[0.0] * k for _ in range(k)]
    for h_label, j_label in pairs:
        observed[index[h_label]][index[j_label]] += 1.0
    n = float(len(pairs))
    human_marg = [sum(observed[a]) for a in range(k)]
    judge_marg = [sum(observed[a][b] for a in range(k)) for b in range(k)]
    distinct = {h_label for h_label, _ in pairs} | {j_label for _, j_label in pairs}
    if all(m == 0 for m in human_marg) or len(distinct) < 2:
        return None  # single class on both sides — kappa undefined

    denom = (k - 1) ** 2 if k > 1 else 1
    num = 0.0
    den = 0.0
    for a in range(k):
        for b in range(k):
            weight = ((a - b) ** 2) / denom
            expected = human_marg[a] * judge_marg[b] / n
            num += weight * observed[a][b]
            den += weight * expected
    if den == 0:
        return 1.0  # perfect agreement (no weighted expected disagreement)
    return 1.0 - num / den


def score_check(check_id: str, human: list[str], judge: list[str]) -> CheckCalibration:
    """Kappa + confusion for one check, excluding judge ``unknown`` abstentions."""
    n_unknown = sum(1 for j in judge if j == "unknown")
    h_scored = [h for h, j in zip(human, judge, strict=True) if j != "unknown"]
    j_scored = [j for j in judge if j != "unknown"]
    confusion: dict[str, dict[str, int]] = {
        h: dict.fromkeys(ORDINAL_LABELS, 0) for h in ORDINAL_LABELS
    }
    for h, j in zip(h_scored, j_scored, strict=True):
        if h in confusion and j in confusion[h]:
            confusion[h][j] += 1
    return CheckCalibration(
        check_id=check_id,
        n=len(h_scored),
        n_unknown=n_unknown,
        kappa=quadratic_weighted_kappa(h_scored, j_scored),
        confusion=confusion,
    )


def score_against_gold(
    gold: list[GoldExample], judged: dict[str, ContentJudgeResult]
) -> dict[str, CheckCalibration]:
    """Score every check across the gold set.

    ``judged`` maps ``page_url`` → the judge's result for that page (the caller
    runs :meth:`ContentJudge.judge_page_text` over each example first). Only
    (page, check) cells with a human label are scored.
    """
    human_by_check: dict[str, list[str]] = {}
    judge_by_check: dict[str, list[str]] = {}
    for example in gold:
        result = judged.get(example.page_url)
        if result is None:
            continue
        verdicts = {v.check_id: v.classification.value for v in result.verdicts}
        for check_id, human_label in example.labels.items():
            if check_id not in verdicts:
                continue
            human_by_check.setdefault(check_id, []).append(human_label)
            judge_by_check.setdefault(check_id, []).append(verdicts[check_id])
    return {
        check_id: score_check(check_id, human_by_check[check_id], judge_by_check[check_id])
        for check_id in human_by_check
    }


def flag_disagreements(
    gold: list[GoldExample], judged: dict[str, ContentJudgeResult]
) -> list[dict[str, str]]:
    """Every judge≠human cell, for triage (rubric-ambiguity vs prompt-bias vs bad-label)."""
    out: list[dict[str, str]] = []
    for example in gold:
        result = judged.get(example.page_url)
        if result is None:
            continue
        verdicts = {v.check_id: v.classification.value for v in result.verdicts}
        for check_id, human_label in example.labels.items():
            judge_label = verdicts.get(check_id)
            if judge_label is not None and judge_label != human_label:
                out.append(
                    {
                        "page_url": example.page_url,
                        "check_id": check_id,
                        "human": human_label,
                        "judge": judge_label,
                    }
                )
    return out


def meets_ship_bar(scores: dict[str, CheckCalibration]) -> bool:
    """True only if every scored check meets the κ ship threshold (§4.5)."""
    scored = [c for c in scores.values() if c.kappa is not None]
    return bool(scored) and all(c.ship_ok for c in scored)
