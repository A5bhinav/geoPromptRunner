# Grade-Calibration Sheet (Layer 2) — Fort

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

## Item 5 · Fort · all engines (pooled)

> Fort: present in 5/40 answers · visibility 0.12 · flags {'high': 2, 'med': 1}

- **Visibility:** 0.115
- **Accuracy flags:** high ×2 · med ×1

<!-- GRADE item=5 -->

**Grade (A/B/C/D/F):** `F`
Grade F:
The visibility is very low, there are not that many answers present from the responses.
There are not that many flags, which is good, but the visbility is still not that good.

<!-- /GRADE item=5 -->

---

## Item 6 · Fort · anthropic

> Fort: present in 2/10 answers · visibility 0.16 · flags none

- **Visibility:** 0.16
- **Accuracy flags:** none

<!-- GRADE item=6 -->

**Grade (A/B/C/D/F):** `F`
Grade F:
This is very similar to Item 5

<!-- /GRADE item=6 -->

---

## Item 7 · Fort · gemini

> Fort: present in 1/10 answers · visibility 0.10 · flags {'high': 2, 'med': 1}

- **Visibility:** 0.1
- **Accuracy flags:** high ×2 · med ×1

<!-- GRADE item=7 -->

**Grade (A/B/C/D/F):** `F`
Grade F:
This is very similar to Item 6

<!-- /GRADE item=7 -->

---

## Item 8 · Fort · openai

> Fort: present in 0/10 answers · visibility 0.00 · flags none

- **Visibility:** 0.0
- **Accuracy flags:** none

<!-- GRADE item=8 -->

**Grade (A/B/C/D/F):** `F`
Grade F:
Literally the worst possible outcome

<!-- /GRADE item=8 -->

---

## Item 9 · Fort · perplexity

> Fort: present in 2/10 answers · visibility 0.20 · flags none

- **Visibility:** 0.2
- **Accuracy flags:** none

<!-- GRADE item=9 -->

**Grade (A/B/C/D/F):** `D`
Grade D:
Similar to all of the other answers, just slightly more present and visibile.


<!-- /GRADE item=9 -->

---

_Generated from `grade_situations.json` — 5 of 10 situations to grade._
