"""Layer-2 calibration: fit the A-F grade formula to analyst gut-grades.

**DEV-ONLY. NOTHING ON AN API, REPORT OR RENDER PATH MAY IMPORT THIS MODULE.**

The client-facing report has no letter grade and no composite score — every
headline number is counted (findings, resolved, cycles open) or measured
(sampled rate, share of model). That is a hard rule, and spec TR-T0 removed the
grade machinery from `judge_metrics` precisely because leaving a computation in
place is how a `B−` quietly comes back onto page 1.

What survives is this harness, and it survives for one reason: the *question*
"can a human's gut-grade be reproduced from the numbers we hold" is a real
research question about our own rubric, and answering it needs the formula. If
the answer ever justifies reintroducing a score, its full rubric must be
published in the methodology section first.

The grade = a caller-supplied visibility number − a severity-weighted flag
penalty, mapped to letter bands. Analysts independently gut-grade ~12-15 real
situations A-F from the raw numbers, then `fit_grade_policy` searches penalty
weights + band cutoffs for the `GradePolicy` that best reproduces those human
grades. The gold set (Layer 1) is NOT the input here — human grades are.

Note the input is a raw ``raw_visibility`` float the caller brings. There is no
longer a `visibility_score()` to produce one automatically, which is deliberate:
computing a composite now takes a conscious act rather than a function call.

Usage:
    python -m src.pipeline.grade_calibration            # demo on the sample file
    fit_grade_policy(load_grade_situations("situations.json"))
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from src.pipeline.judge import AccuracyFlag, AnswerJudgment
from src.storage.models import Severity

__all__ = [
    "VisibilityGrade",
    "GradePolicy",
    "DEFAULT_GRADE_POLICY",
    "grade_from",
    "grade_penalty_flags",
    "GradeSituation",
    "GradeFit",
    "load_grade_situations",
    "score_policy",
    "fit_grade_policy",
    "render_grade_calibration",
]


# --- The grade formula itself (moved here from judge_metrics by TR-T0) --------
#
# It lives in the calibration harness because the harness is the only sanctioned
# caller. `judge_metrics` is imported by `src/api/reports.py`; this module is not,
# and `tests/test_report_packaging.py` asserts that it stays that way.

# Severity as an ordinal so "the worst flag of this type wins" is well-defined.
_SEVERITY_RANK: dict[str, int] = {
    Severity.HIGH.value: 0,
    Severity.MED.value: 1,
    Severity.LOW.value: 2,
}

# How much each distinct client accuracy flag drags the grade down. A confident
# wrong claim ("it's $20/mo" when it's free) erodes trust even when visibility is
# fine, so the grade is visibility *discounted* by what the model gets wrong.
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
class VisibilityGrade:
    """A letter over our own rubric. Never rendered to a client."""

    letter: str
    score: float  # visibility after the accuracy penalty, 0..1
    raw_score: float  # the visibility number before the penalty
    accuracy_penalty: float
    n_flags: int
    rationale: str


@dataclass(frozen=True)
class GradePolicy:
    """The tunable parameters of the A-F grade: per-severity flag penalties and
    the score→letter band cutoffs."""

    penalty: dict[str, float]
    bands: tuple[tuple[float, str], ...]


DEFAULT_GRADE_POLICY = GradePolicy(penalty=dict(_FLAG_PENALTY), bands=_GRADE_BANDS)


def grade_from(
    raw_visibility: float, flag_severities: list[str], policy: GradePolicy = DEFAULT_GRADE_POLICY
) -> VisibilityGrade:
    """Pure grade core: a visibility number discounted by a severity-weighted flag
    penalty, floored at 0, mapped to a band."""
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


def grade_penalty_flags(judgments: list[AnswerJudgment]) -> list[AccuracyFlag]:
    """The flags that drive the grade penalty, deduped so repetition can't
    compound it (the guard against an over-flagging judge tanking the grade).

    WITHIN each answer, the same error *type* counts once, highest severity wins:
    a reply that says "Ring 4" three times has one stale problem, not three.
    ACROSS answers, each answer's distinct-type problems are kept, so a pervasive
    error still weighs more than a one-off.
    """
    out: list[AccuracyFlag] = []

    def rank(sev: str) -> int:  # lower rank = worse severity
        return _SEVERITY_RANK.get(sev, 1)

    for j in judgments:
        if not j.assessed:
            continue
        best: dict[str, AccuracyFlag] = {}
        for f in j.accuracy_flags:
            cur = best.get(f.type)
            if cur is None or rank(f.severity) < rank(cur.severity):
                best[f.type] = f
        out.extend(best.values())
    return out

# Letter scale (best→worst) for measuring how far a predicted grade is from the
# human's — "within one letter" is the success bar in the plan.
_LETTERS = ["A", "B", "C", "D", "F"]
_LETTER_RANK = {ltr: i for i, ltr in enumerate(_LETTERS)}

# Candidate parameter grids for the fit. Coarse on purpose — ~12-15 situations
# don't support a fine fit, and staying near the v1 defaults is a feature.
_HIGH_CANDS = (0.05, 0.10, 0.15, 0.20, 0.30)
_MED_CANDS = (0.03, 0.07, 0.12)
_LOW_CANDS = (0.0, 0.03)
_BAND_CANDS: tuple[tuple[tuple[float, str], ...], ...] = (
    ((0.70, "A"), (0.50, "B"), (0.30, "C"), (0.15, "D")),  # v1 default
    ((0.60, "A"), (0.40, "B"), (0.20, "C"), (0.08, "D")),  # lenient
    ((0.80, "A"), (0.60, "B"), (0.40, "C"), (0.20, "D")),  # strict
)


@dataclass(frozen=True)
class GradeSituation:
    """One real client situation an analyst gut-graded A-F from the raw numbers.

    ``flag_severities`` is the list of the run's distinct client accuracy flags
    by severity (e.g. ``["high", "high", "low"]``) — the same input the grade
    formula consumes. ``human_grade`` is the analyst's letter, set BEFORE seeing
    the formula's output.
    """

    label: str
    raw_visibility: float
    flag_severities: list[str]
    human_grade: str


@dataclass(frozen=True)
class GradeFit:
    """How well a policy reproduces the human grades."""

    n: int
    exact: int  # predicted letter == human letter
    within_one: int  # within one band of the human letter
    predictions: list[tuple[str, str, str]]  # (label, human, predicted)

    @property
    def exact_rate(self) -> float:
        return self.exact / self.n if self.n else 0.0

    @property
    def within_one_rate(self) -> float:
        return self.within_one / self.n if self.n else 0.0


def load_grade_situations(path: str | Path) -> list[GradeSituation]:
    """Load analyst-graded situations from JSON."""
    raw = json.loads(Path(path).read_text())
    out: list[GradeSituation] = []
    for s in raw["situations"]:
        out.append(
            GradeSituation(
                label=str(s.get("label", "")),
                raw_visibility=float(s["raw_visibility"]),
                flag_severities=[str(x) for x in s.get("flag_severities", [])],
                human_grade=str(s["human_grade"]).strip().upper(),
            )
        )
    return out


def score_policy(policy: GradePolicy, situations: list[GradeSituation]) -> GradeFit:
    """Grade every situation under ``policy`` and tally agreement with the human
    letters (pure)."""
    exact = within_one = 0
    preds: list[tuple[str, str, str]] = []
    for s in situations:
        predicted = grade_from(s.raw_visibility, s.flag_severities, policy).letter
        preds.append((s.label, s.human_grade, predicted))
        ph, pp = _LETTER_RANK.get(s.human_grade), _LETTER_RANK.get(predicted)
        if predicted == s.human_grade:
            exact += 1
        if ph is not None and pp is not None and abs(ph - pp) <= 1:
            within_one += 1
    return GradeFit(n=len(situations), exact=exact, within_one=within_one, predictions=preds)


def _distance_from_default(
    penalty: dict[str, float], bands: tuple[tuple[float, str], ...]
) -> float:
    """Tie-breaker: prefer a fitted policy that stays near the v1 defaults rather
    than an equally-accurate but wildly different one."""
    dp = DEFAULT_GRADE_POLICY.penalty
    pen_dist = sum(abs(penalty[k] - dp[k]) for k in dp)
    band_dist = 0.0 if bands == DEFAULT_GRADE_POLICY.bands else 0.25
    return pen_dist + band_dist


def fit_grade_policy(situations: list[GradeSituation]) -> tuple[GradePolicy, GradeFit]:
    """Grid-search penalty weights + band cutoffs for the policy that best
    reproduces the human grades. Ranks by exact matches, then within-one, then
    closeness to the v1 defaults (so we don't drift without reason)."""
    best: tuple[GradePolicy, GradeFit] | None = None
    best_key: tuple[int, int, float] | None = None
    for high, med, low, bands in product(_HIGH_CANDS, _MED_CANDS, _LOW_CANDS, _BAND_CANDS):
        penalty = {Severity.HIGH.value: high, Severity.MED.value: med, Severity.LOW.value: low}
        policy = GradePolicy(penalty=penalty, bands=bands)
        fit = score_policy(policy, situations)
        # higher exact, higher within-one, then SMALLER distance from default.
        key = (fit.exact, fit.within_one, -_distance_from_default(penalty, bands))
        if best_key is None or key > best_key:
            best_key, best = key, (policy, fit)
    assert best is not None  # _HIGH_CANDS etc. are non-empty
    return best


def render_grade_calibration(
    fitted: GradePolicy, fit: GradeFit, baseline: GradeFit | None = None
) -> str:
    """Markdown report: fitted policy, agreement, and per-situation predictions."""
    lines = [
        "# Grade-Formula Calibration",
        "",
        f"Situations: {fit.n} · exact-letter agreement: {fit.exact_rate:.0%} · "
        f"within-one: {fit.within_one_rate:.0%}",
        "",
    ]
    if baseline is not None:
        lines += [
            f"_v1 default policy scored {baseline.exact_rate:.0%} exact / "
            f"{baseline.within_one_rate:.0%} within-one on the same situations._",
            "",
        ]
    pen = fitted.penalty
    lines += [
        "## Fitted policy",
        "",
        f"- penalties: high −{pen.get('high', 0):.2f} · med −{pen.get('med', 0):.2f} · "
        f"low −{pen.get('low', 0):.2f}",
        "- bands: " + " · ".join(f"{ltr}≥{thr:.2f}" for thr, ltr in fitted.bands),
        "",
        "## Per-situation (human vs fitted)",
        "",
        "| Situation | Human | Fitted | |",
        "| --- | --- | --- | --- |",
    ]
    for label, human, predicted in fit.predictions:
        mark = "✓" if human == predicted else "✗"
        lines.append(f"| {label} | {human} | {predicted} | {mark} |")
    lines += [
        "",
        "_Grades are analyst gut-calls made BEFORE seeing the formula. Until this_",
        "_clears the within-one bar on held-out situations, the grade stays_",
        "_'uncalibrated — internal only'._",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    default = Path(__file__).resolve().parents[2] / "data" / "grade_situations.json"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    situations = load_grade_situations(path)
    graded = [s for s in situations if s.human_grade in _LETTER_RANK]
    if not graded:
        print(
            f"Loaded {len(situations)} situations from {path.name}, but none are graded yet.\n"
            "Gut-grade each 'human_grade' (A/B/C/D/F) from the raw numbers, then re-run "
            "to fit the policy."
        )
        raise SystemExit(0)
    print(f"Fitting on {len(graded)}/{len(situations)} graded situations.\n")
    baseline = score_policy(DEFAULT_GRADE_POLICY, graded)
    fitted, fit = fit_grade_policy(graded)
    print(render_grade_calibration(fitted, fit, baseline))
