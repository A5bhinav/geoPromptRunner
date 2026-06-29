# Grade-Calibration Sheet (Layer 2) — Oura

Fill the **grade** cell in each block with one letter: `A` · `B` · `C` · `D` · `F`.
Edit only the cell between the markers — keep the `<!-- GRADE -->` markers intact
so the sheet can be parsed back into the JSON's `human_grade` field.

**How to grade**

- **Gut, from the numbers — not the formula.** Read the context, picture the client,
  and write the letter that *feels* defensible. Do **not** run the grade formula first;
  you are the ground truth, not its checker.
- **The question to ask:** *"If this were the headline grade on a client's audit,
  would it be defensible?"* A category leader with a few stale nits isn't an F; an
  invisible brand isn't an A.

**Reading the inputs**

- **Visibility** (0..1) — prominence-weighted presence. `0.50` ≈ mid-pack on average;
  `0.10` ≈ barely there; `0.00` ≈ absent everywhere.
- **Accuracy flags** — distinct client errors by severity (`high` misleads a buyer,
  `med` outdated/incomplete, `low` cosmetic).

---

## Item 0 · Oura · all engines (pooled)

> Oura: present in 22/40 answers · visibility 0.41 · flags {'high': 3, 'med': 8, 'low': 7}

- **Visibility:** 0.412
- **Accuracy flags:** high ×3 · med ×8 · low ×7

<!-- GRADE item=0 -->

**Grade (A/B/C/D/F):** `D`
Grade: D
Because it shows up in about 50% of responses and has a visibility score of just below 0.412. 
There are many accuracy flags that bring this down tho.

<!-- /GRADE item=0 -->

---

## Item 1 · Oura · anthropic

> Oura: present in 7/10 answers · visibility 0.53 · flags {'high': 2, 'med': 2, 'low': 3}

- **Visibility:** 0.53
- **Accuracy flags:** high ×2 · med ×2 · low ×3

<!-- GRADE item=1 -->

**Grade (A/B/C/D/F):** `C`
Grade: C
It shows up in about 70% of the answers and has a visibility of 0.53 — the strongest in
the set. But it carries 2 high-severity flags (plus 2 med / 3 low), and those buyer-
misleading errors pull it down to a C, consistent with the gemini slice (similar profile).

<!-- /GRADE item=1 -->

---

## Item 2 · Oura · gemini

> Oura: present in 6/10 answers · visibility 0.47 · flags {'high': 1, 'med': 5}

- **Visibility:** 0.47
- **Accuracy flags:** high ×1 · med ×5

<!-- GRADE item=2 -->

**Grade (A/B/C/D/F):** `C`
Grade: C
This one gets a C because it has decent visibilty, but at the same time the flags bring it down.

<!-- /GRADE item=2 -->

---

## Item 3 · Oura · openai

> Oura: present in 4/10 answers · visibility 0.26 · flags none

- **Visibility:** 0.26
- **Accuracy flags:** none

<!-- GRADE item=3 -->

**Grade (A/B/C/D/F):** `D`
Grade: D
The visibility is very low and oura is not that present in the answers.
Only reason why it isn't F is because it has no accuracy flags.

<!-- /GRADE item=3 -->

---

## Item 4 · Oura · perplexity

> Oura: present in 5/10 answers · visibility 0.39 · flags {'med': 1, 'low': 4}

- **Visibility:** 0.39
- **Accuracy flags:** med ×1 · low ×4

<!-- GRADE item=4 -->

**Grade (A/B/C/D/F):** `C`

Grade: C
This grade is a C for the same reasons as item 0. There are less flags tho.

<!-- /GRADE item=4 -->

---

_Generated from `grade_situations.json` — 5 of 10 situations to grade._
