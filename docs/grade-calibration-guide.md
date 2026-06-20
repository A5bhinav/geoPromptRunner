# Grade-Calibration Gut-Grade Guide (Layer 2)

*How Josh + Abhi calibrate the A–F grade formula so it tracks expert intuition, not unexamined constants. ~30 minutes.*

The A–F grade = prominence-weighted **visibility** − a severity-weighted **flag penalty**, mapped to letter bands. Every one of those numbers (the −0.15/−0.07/−0.03 penalties, the band cutoffs) is a v1 guess. This session fits them to *your* judgment: you gut-grade real situations from the raw numbers, then the harness searches for the policy that best reproduces your grades.

---

## The file

`data/grade_situations.json` — **10 real situations** from the Oura + Fort gold sets (pooled per client + per engine). Each has two inputs, computed from the **verified human labels** (not the judge, so this isn't polluted by the judge's over-flagging):

- **`raw_visibility`** (0..1) — prominence-weighted client visibility. `recommended_first`=1.0, `mid_pack`=0.6, `buried`=0.3, `also_ran`=0.1, `absent`=0.0, averaged across the slice. (So 0.50 ≈ "mid-pack on average"; 0.10 ≈ "barely there.")
- **`flag_severities`** — the slice's distinct client accuracy errors by severity (one per type per answer).
- **`_context`** — a plain-English summary so you don't have to read raw numbers.

---

## How to grade

1. **Independently.** Josh and Abhi each fill `human_grade` (`A`/`B`/`C`/`D`/`F`) on their own copy. Don't compare until both are done — independent judgment is the whole point.
2. **Gut, then numbers.** Read the `_context`, picture the client, and write the letter that *feels* right for a client you'd hand this to. **Do not look at the formula's current output** — you're the ground truth, not its checker.
3. **The question to ask:** *"If this were the headline grade on a client's audit, would it be defensible?"* A category-leading brand with a couple of stale-info nits shouldn't be an F; an invisible brand shouldn't be an A.
4. **Reconcile.** Compare. Where you disagree by more than one letter, talk it out and pick one — that conversation is itself calibration. Record the reasoning.
5. **Fit.** Once `human_grade` is filled, run:
   ```bash
   python -m src.pipeline.grade_calibration        # reads data/grade_situations.json
   ```
   It prints the fitted penalty weights + band cutoffs, how well they reproduce your grades (exact + within-one), and per-situation predictions. The plan's bar: **within one letter** on held-out situations.

---

## Notes

- **No anchor letters are provided** — that's deliberate. If we wrote in "F" anywhere you'd anchor to it.
- The set spans the space well already: visibility 0.00 → 0.53, flag loads 0 → 18. Add more situations from future clients over time (re-run `scripts/build_grade_situations.py`).
- This calibrates *weights*, not the judge. Keep it separate from the gold-set (Layer-1) work.
- Until this clears the within-one bar, the grade stays "uncalibrated — internal only," exactly as `report.md` §6.3 says.
