# Calibration & Judge-Accuracy Plan

*How we make the judge (the "generator" of every verdict and flag in the report) as accurate as possible, and prove that accuracy generalizes across clients — not just Oura. Plan only; build order at the end.*

**Why now.** The real Oura run produced a strong report but exposed concrete judge errors on inspection — e.g. flag #45 "Oura has a strong focus on data privacy → *Not mentioned in the fact sheet*" is flagged as a contradiction when, per the schema's own rule, a claim the sheet doesn't *cover* should be a `fact_sheet_candidate`, **not a flag**. The headline grade (F) is driven entirely by the flag count, so flag precision *is* the report's credibility. Today's calibration can't even see this error, because the flag check is binary. This plan fixes that and everything around it.

**The loop this plan builds.** Accuracy isn't a one-shot setting; it's a loop: **calibrate → diagnose failures → fix the judge prompt/rubric → re-calibrate on held-out data.** The work below upgrades both halves — the *measurement* (so it exposes real failures) and the *judge* (so the failures get fixed) — and the hygiene that keeps the number honest.

**Two layers, both must be calibrated.** A perfect judge feeding arbitrary weights still produces an arbitrary report, so accuracy is two problems:

- **Layer 1 — does the judge *read* each answer like a human?** (present / prominence / framing / typed flags). Parts 1–6.
- **Layer 2 — do the *scores and inputs built on top* match human and business judgment?** The A–F grade weights, severity, per-query weights, run-count (K), the trend "real-move" threshold, and the ground-truth inputs (fact sheet, alias lists). Parts 7–10.

The Oura **F** is the proof both are needed: it's as much a Layer-2 question (*are the −0.15/−0.07/−0.03 penalty weights right?*) as a Layer-1 one (*are the 156 flags right?*).

---

# Layer 1 — Judge reading accuracy

*Does the judge label each answer the way a human would? This is what the gold set measures.*

## Part 1 · Richer gold labels (`GoldItem` v2)

Today `GoldItem` carries `labels` (present/prominence/framing per brand) + `expect_accuracy_flags` (one boolean). The boolean is the weak link — it can't distinguish "found the right errors" from "found 5 wrong ones plus the right one." Extend it:

- **`expected_flags: [{type, severity, note}]`** — the human's list of the *real* errors that answer makes about the client (type from `AccuracyFlagType`, severity from `Severity`). Empty list = "checked, accurate."
- Keep `expect_accuracy_flags` derivable (`len(expected_flags) > 0`) for backward compatibility with the current harness and the 3 placeholder items.
- Optional **`fact_sheet_candidates`** — claims the answer makes that the sheet *doesn't cover* (so the judge should NOT flag them). This is the direct counter to the over-flagging we found: a judge flag landing on a candidate is a precision error.

Matching policy (avoid brittle string compares): a judge flag **matches** a gold flag when their **type** agrees on the **same underlying claim dimension** (pricing, model, feature, identity, competitor-confusion). Type-level matching is robust and still catches the failures that matter.

---

## Part 2 · Harness upgrade (`CalibrationReport` v2)

Replace the single binary with a real measurement (`src/pipeline/calibration.py`):

- **Flag precision** = correct judge flags / all judge flags. *Catches over-flagging — the Oura problem the binary is blind to.*
- **Flag recall** = gold flags matched / all gold flags. *Catches misses.*
- **Flag type-accuracy** = of matched flags, share with the right `AccuracyFlagType`. *Catches mis-typed flags (e.g. a design claim tagged `wrong_pricing`).*
- **Severity agreement** on matched flags (exact, and within-one-band).
- **Per-label confusion matrices** for prominence and framing — not just "82%", but *where* it errs (buried↔mid_pack is the known fuzzy boundary). A failure map generalizes; a single percentage doesn't.
- **Breakdowns** by **engine** (does it judge Perplexity's cited answers as well as plain prose?) and by **category** (Part 3) — the slices reveal whether accuracy is uniform or concentrated.
- `render_calibration` prints all of the above; keep the headline agreement table at the top.

Done right, this turns calibration from *"does the judge flag enough?"* into *"are the judge's flags right?"* — the property that has to hold before flag counts go to a client.

---

## Part 3 · Gold-set construction for generalization

The judge is a *reading* task, so a deep single-category set proves it reads ring answers — not that it reads. Generalize the data:

- **Multiple categories.** Build gold sets across ≥3 B2C categories — Oura (smart ring), Centsible (budgeting app — sample already in repo), plus one more (e.g. a meditation or skincare brand). One fact sheet per category. Report agreement per category *and* pooled.
- **Over-sample the hard cases, not the natural distribution.** Generalization breaks on edges. Deliberately include: brand names that are common words; **negative and mixed framing**; the client **confused with a competitor**; **list-tail** "also worth a look" mentions; and the **"claim the sheet doesn't cover"** trap (where the judge already fails). An easy-distribution gold set looks generalized and isn't.
- **Source from real runs.** `docs/answers.md` already pairs all 180 Oura answers with the judge's verdict — the ideal labeling substrate. Pull from there (and future runs) rather than inventing answers, so the gold set matches the instrument the judge actually sees.
- **Sizing.** ~25–40 labeled answers per category (→ ~100–150 brand rows). Variety beats volume.

---

## Part 4 · Hygiene that makes the number generalize

- **Train/test split.** Split each gold set into a **calibration (tune) subset** and a **held-out test subset**. Tune the judge prompt only against the tune subset; **report agreement only on held-out**. Few-shot examples placed in the judge prompt come **only from the tune split** — otherwise you're grading the judge on its own examples and the number won't predict the next client.
- **Inter-rater agreement (the human ceiling).** Josh and Abhi independently label the same ~10 answers; their agreement is the realistic ceiling (the judge can't beat the humans). Low inter-rater agreement on a field means the **label definition is too fuzzy** — tighten the `labeling-guide.md` rule. Crisper rules are *what makes the judge transfer*, because precise definitions cross categories better than gut feel.
- **Freeze + version.** Each gold set is frozen and dated once testing starts; a change log records additions. Calibration on a moving set is meaningless.

---

## Part 5 · Judge improvements the calibration will drive

Calibration is the instrument; these are the fixes it will validate. Each ships, then re-calibrate on held-out to confirm it helped and didn't regress another slice.

- **Stop flagging uncovered claims (the over-flagging fix).** Sharpen the judge system prompt: a claim the fact sheet doesn't *address* is a `fact_sheet_candidate`, never a flag. Directly targets the false positives (#2, #28, #35, #45 …) and lifts flag precision.
- **Flag-type discipline.** Require the judge to quote the specific fact-sheet line a flag contradicts; if it can't, it's not a flag. Targets mis-typed flags (design claim → `wrong_pricing`).
- **Prominence boundary clarity.** If the confusion matrix shows buried↔mid_pack churn, tighten those definitions in the prompt and the labeling guide together (they must stay in lockstep).
- **Few-shot from the worked failures.** Put 3–5 tune-split examples that demonstrate the correct call on the hard cases into the judge prompt.

---

## Part 6 · Ongoing (accuracy is maintained, not achieved once)

- **Per-category gate.** Every new client category, hand-label a small batch and confirm held-out agreement clears the bar *before* the report is trusted.
- **Drift re-runs.** Re-calibrate whenever `JUDGE_MODEL` changes (it's already moved gpt-4o → claude-sonnet-4-6) or a measured engine updates. Track the agreement numbers over time.

---

# Layer 2 — Scoring & input calibration

*Even with a perfect judge, the numbers built on top have free parameters. These are arbitrary v1 values today; they need calibrating against human/business judgment, not against the gold set.*

## Part 7 · The grade formula (highest Layer-2 leverage)

The A–F grade = prominence-weighted visibility **−** a severity-weighted accuracy penalty (`high −0.15`, `med −0.07`, `low −0.03` per flag), floored at 0, mapped to bands (`judge_metrics.visibility_grade`). Every one of those numbers is a guess — and they produced the result that should make this obvious: a category-*leading* 0.56 visibility was driven to **0.00 → F** purely by flag count. Is "F" the verdict a human analyst would give the most-recommended brand in its category?

**Calibrate it:** have Josh + Abhi (and ideally a third proxy) **gut-grade ~12–15 real client situations** A–F from the raw numbers, *before* looking at the formula's output. Then fit the penalty magnitudes, the floor behavior, and the band cutoffs so the formula **reproduces the human grades**. Output: a grade that's defensible to a client because it tracks expert intuition, not an unexamined constant.

## Part 8 · Severity weighting & per-query weights

- **Severity → grade.** Layer 1 checks the judge's `high/med/low` against human labels; Layer 2 checks the *penalty those severities carry*. Confirm the per-severity weights (Part 7) reflect "high = would change a buyer's decision," since a slightly trigger-happy "high" swings the grade hard.
- **Per-query commercial-value weights.** The `weight` field (problem 1.0 → brand 2.0) silently scales share-of-model and the Step-6 Impact formula. These are business judgments — set them **on purpose**, document the rationale, and hold them constant across cycles so trends stay comparable.

## Part 9 · Measurement stability — run count (K) and the trend noise floor

- **Set K from data, not the default.** The Oura report ran at **K=1** (single draws, no nondeterminism averaging). Run the `determinism` baseline (`geo verify determinism`, `suggest_runs_per_query`) to measure each engine's run-to-run agreement and pick the K that actually stabilizes the measurement — higher for the retrieval surfaces, where live results vary even at temperature 0.
- **Calibrate the trend "real-move" threshold.** When `geo compare` diffs two cadence runs, a delta only matters if it exceeds the measurement noise. Set that threshold = the noise band from the determinism baseline, so the §3 trend (the moat) reports real movement, not jitter.

## Part 10 · Ground-truth inputs (the GIGO layer)

The judge can't be more correct than what it's checked against.

- **The fact sheet.** Some "false flags" may be *fact-sheet* errors, not judge errors (the Oura sheet was built from public info, not client-verified). Spot-validate it; for a real client it's confirmed *with them* at Step-0 intake. No flag in the held-out set should trace to a wrong/stale fact-sheet line.
- **Alias / `name_variant` lists.** They drive mention detection — too narrow → false absences, too broad → over-matching (worst for brand names that are common words). Validate they catch real mentions without false hits (the gold set's `present` field measures this directly).
- **Peripheral thresholds, where live.** The technical-check rendering heuristic (text-length → "SPA shell"), the competitor-**discovery** frequency gate, and any citation **source-class** rules each carry a threshold that should be spot-checked against known cases. And if the deterministic rubric layer (PScore weights, RANKING/DEMOTION/POS/NEG vocabularies) is ever switched on, every one of those is a v1 seed needing the same discipline.

---

## Build order

| # | Item | Type | Owner |
|---|---|---|---|
| 1 | `GoldItem` v2 — `expected_flags` (+ optional `fact_sheet_candidates`), backward-compatible loader | code | Abhi |
| 2 | `CalibrationReport` v2 — flag precision/recall/type-accuracy, severity, prominence/framing confusion matrices, per-engine + per-category breakdown; richer `render_calibration` | code | Abhi |
| 3 | **Label the real Oura gold set** from `answers.md` (blind-label-first to avoid rubber-stamping the judge's own verdicts) — the first real numbers | process | Josh + Abhi |
| 4 | Train/test split + inter-rater pass on the Oura set; record the human ceiling | process | Josh + Abhi |
| 5 | Judge-prompt fix #1: stop flagging uncovered claims; re-calibrate on held-out, confirm precision ↑ | code + verify | Abhi |
| 6 | Second-category gold set (Centsible) → pooled + per-category agreement | process | Josh + Abhi |
| 7 | Remaining judge fixes (type discipline, prominence boundaries, few-shot) as the matrices dictate | code + verify | Abhi |
| 8 | Per-category gate + drift re-run into the SOP / `left.md` | process | both |
| **L2-1** | **Calibrate the grade formula** — analysts gut-grade ~12–15 situations; fit penalty weights, floor, bands to reproduce them | process + code | both |
| **L2-2** | **Set K from the determinism baseline**; define the trend "real-move" threshold from the measured noise band | code + verify | Abhi |
| **L2-3** | **Validate ground truth** — fact sheet (no flag traces to a sheet error) + alias lists (catch real mentions); spot-check peripheral thresholds | process | Josh + Abhi |
| **L2-4** | **Lock per-query weights on purpose** + document rationale | process | Josh |

Items 1–3 are the unlock for Layer 1: they convert the report's central number from *hoped-correct* to *measured*. L2-1 is the unlock for Layer 2 — it does the same for the headline grade. The two layers can proceed in parallel (different owners); both must clear the bar before a report goes to a prospect.

---

## Success criteria (what "accurate enough to show a client" means)

**Layer 1 — judge reading**, measured **on held-out data, pooled across ≥2 categories**, at or above the human inter-rater ceiling where it's lower:

- present agreement ≥ 95% · prominence ≥ 85% · framing ≥ 90%
- **flag precision ≥ 90%** (few false flags — the credibility gate) · flag recall ≥ 80% · type-accuracy ≥ 90%
- no single engine or category slice more than ~10 points below the pooled number

**Layer 2 — scoring & inputs:**

- the grade formula reproduces the analysts' gut-grades within **~1 letter** on the calibration situations
- **K** chosen so each engine's modal-answer agreement clears the determinism bar; the trend "real-move" threshold ≥ the measured noise band
- in the held-out set, **no accuracy flag traces to a fact-sheet error**, and alias lists catch ≥ 95% of true client mentions
- per-query weights are documented and frozen

Until **both layers** clear these bars, the report's flag counts and grade stay labeled "uncalibrated — internal only," exactly as the current `report.md` §6.3 already, honestly, does. A high Layer-1 score with an uncalibrated grade formula is still not client-ready — that's the whole point of separating them.
