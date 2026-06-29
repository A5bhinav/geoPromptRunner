# Plan — Make the Judge More Accurate at ~Flat Cost (cheap model, no Opus)

> **Status:** **Action A + cascade (idea #2) + atomic verifier (idea #4) built &
> validated 2026-06-28** — see §3.1, §4.1, §4.2. Cascade ship gate met (100% flag recall);
> verifier solved the precision problem (queue #9): **80% precision / 95% recall**. B1
> (few-shot) / B2 (reasoning-first) not started.
> **Audience:** a future session (or Josh/Abhi) that will execute Actions A & B.

---

## 0. The problem

The engine-answer judge (`src/pipeline/judge.py`) is accurate on **Sonnet**
(`claude-sonnet-4-5`) but that's the main API cost driver during iteration. On
**Haiku** (`claude-haiku-4-5`) cost drops a lot but **accuracy drops a lot too** —
especially, we suspect, on the **accuracy-flag** reasoning (verbatim fact-sheet
contradictions), not the structural reads.

**Goal:** recover Sonnet-level accuracy while keeping cost near Haiku. Explicitly
**not** jumping to Opus. The metric to protect is the one we already hit on Sonnet:
**100% accuracy-flag recall** (plus κ on present/prominence/framing).

## 1. Reframe — what "let it learn" actually means here

- **No fine-tuning.** Anthropic doesn't offer practical customer fine-tuning of Claude,
  so "train Haiku on Sonnet's outputs" (weight distillation) is **not available**.
- **"Learn on itself" would drift.** A judge that accumulates its *own* responses with no
  human-verified anchor reinforces its own mistakes. The **gold set is the anchor**
  (`data/fort_gold.json`, `data/oura_gold.json`).
- **The available version of the idea = in-context few-shot** drawn from the
  human-verified gold set. That's "learning from more judge responses" done the one way
  that raises accuracy rather than entrenching errors.

## 2. The idea menu (leverage-per-dollar order)

1. **Few-shot exemplars + prompt caching (biggest lever, ~flat cost).** Put 4–8 of the
   clearest gold examples *with reasoning* into the judge prompt, chosen to cover Haiku's
   failure modes (a disavowal that is NOT a flag, an omission that is NOT a flag, a real
   `stale`/`wrong_pricing` flag with its cited line). Wrap the static system + few-shot
   prefix in **Anthropic prompt caching** (`cache_control`) so the big prefix is ~90%
   cheaper per call. (Prior research: few-shot lifted judge consistency ~65%→77.5%.)
2. **Two-tier cascade — Haiku first, Sonnet only on the hard cases (best cost/accuracy).**
   Flags are rare and are where Haiku struggles. Run everything on Haiku; **escalate to
   Sonnet only answers where Haiku emits (or is unsure about) an accuracy flag.** Most
   answers (no flag) stay cheap; the small flag slice gets Sonnet. Variant: Haiku always
   does present/prominence/framing; Sonnet does the accuracy block only, and only when a
   fact sheet exists.
3. **Reasoning-first for the cheap model.** The judge currently forces an immediate
   `record_judgment` tool call (no thinking) — fine for a strong model, harmful for a weak
   one (strict structured output degrades reasoning). For Haiku, reason in text first,
   then emit the structured verdict.
4. **Atomic decomposition of the accuracy check.** Turn the accuracy block into a
   mechanical checklist (list client claims → for each, search the sheet for a
   contradicting line → flag only if a verbatim line exists). Weak models follow a
   procedure better than they follow prose.
5. **Selective self-consistency on Haiku.** For borderline answers only, run Haiku 3× at a
   small temperature and majority-vote. Three Haiku calls < one Sonnet call.

**Throughline:** keep the cheap model for the easy ~90%, spend the expensive model only on
the hard, high-value ~10% (accuracy flags), and few-shot the cheap model so it's better at
the easy stuff too — Sonnet-ish accuracy at near-Haiku cost, no Opus.

## 3. Action A — Diagnose where Haiku actually fails (do this first)

Don't optimize blind. Use the existing harness to get a per-check Haiku-vs-Sonnet gap.

- **Run:** the calibration harness with `JUDGE_MODEL=claude-haiku-4-5` against the gold
  sets, via `scripts/run_calibration.py` / `src/pipeline/judge_metrics.py`, over
  `data/fort_gold.json` and `data/oura_gold.json`. Repeat (or reuse stored) for Sonnet as
  the baseline.
- **Report, per model:** accuracy on present / prominence / framing, and **per-flag-type
  precision/recall** (`wrong_pricing`, `stale`, `missing_or_invented_feature`, `identity`,
  `competitor_confusion`) + confusion matrices.
- **Hypothesis to confirm/refute:** Haiku ≈ Sonnet on structural reads, but weak on
  accuracy flags (esp. `stale` / `wrong_pricing`). If true → the cascade only needs Sonnet
  for flags; few-shot may close most of the rest.
- **Output:** a Haiku-vs-Sonnet per-check gap table that decides whether **few-shot alone**
  is enough or we also need the **cascade**.
- **Cost note:** this is a bounded, deliberate spend (Haiku over the gold set, once); the
  judge cache makes a re-run free.

### 3.1 Action A results (2026-06-28, consumer judge prompt, 80 gold items, temp 0)

Haiku (`claude-haiku-4-5`) vs the Sonnet baseline (`claude-sonnet-4-5`), same prompt/gold:

| Check | Sonnet | Haiku | Gap |
|---|---|---|---|
| present | 96% | 94% | −2 |
| prominence | 88% | 86% | −2 |
| framing | 93% | 94% | +1 |
| flag **recall** | **95%** | **43%** | **−52** |
| flag precision | 42% | 56% | +14 |
| flag binary (per item) | 89% | 84% | −5 |
| TP / FP / FN | 20 / 28 / 1 | 9 / 7 / 12 | — |

**Hypothesis CONFIRMED, with a twist.** Haiku ≈ Sonnet on the structural reads
(present/prominence/framing all within ~2pp — Haiku is fine here). The divergence is
entirely in the accuracy flags, and the two models fail in **opposite** directions:
- **Sonnet over-flags** — recall 95% (catches ~everything) but precision 42% (28 FPs).
- **Haiku under-flags** — precision 56% but recall **43%** (misses 12 of 21 gold flags).
  By category, Haiku caught **0%** of the Fort ("strength training wearable") flags.

**Verdict — the cascade (idea #2) is required; few-shot alone is not enough.** A
52-point recall gap won't be closed by few-shot (prior art lifts consistency ~65→77.5%,
not +52 recall), and the metric to protect is 100% flag recall. So:
- **Structural reads → Haiku** (good enough, big cost win on the easy ~90%).
- **Accuracy block → Sonnet** (Haiku's recall is disqualifying for flags).
- Still A/B **B1 (few-shot) + B2 (reasoning-first)** to lift Haiku's standalone flag
  recall and shrink how often the cascade must escalate — but as an optimization on top
  of the cascade, not a replacement for it.
- Orthogonal: Sonnet's own **precision** problem (28 FPs) is queue #9 — the live/paid
  path keeps Sonnet (protect recall) and tightens the prompt to cut false positives.

## 4. Action B — Build the two levers to A/B test

Build these so each can be measured against the gold set independently.

- **B1 — Few-shot exemplar block.** Select 4–8 gold examples (with reasoning) targeting the
  failure modes Action A surfaces; insert into the judge prompt; wrap the static
  system+few-shot prefix in `cache_control` prompt caching to hold cost flat. *Note:*
  changing the prompt changes the judge's `prompt_fingerprint` → invalidates
  `judge_cache.sqlite` (expected — it's a new judge version; re-judge from the
  subscription/Haiku, not Sonnet, while iterating).
- **B2 — Reasoning-first variant (Haiku).** Change the forced-immediate tool call so the
  model reasons in text first, then emits the structured verdict (two-step, or a
  `reasoning` field ordered before the labels). A/B this specifically on Haiku.
- **A/B method:** re-run Action A's harness for each variant (baseline Sonnet, plain Haiku,
  Haiku+B1, Haiku+B1+B2). Keep whatever closes the gap at the lowest cost. **Ship gate:**
  match Sonnet's flag recall (the 100% bar) and non-regressing κ on the structural fields.

### 4.1 Cascade (idea #2) — built & validated (2026-06-28)

Built the fixed-split cascade: **Haiku does the structural reads** (`record_brands`),
**Sonnet does the accuracy block** (`record_flags`), each a self-contained prompt + forced
tool. The accuracy pass runs only when a fact sheet exists — so a visibility-only run (no
fact sheet) is **pure Haiku** (the ~3× win), and a full run reads structure cheaply while
Sonnet protects flag recall. Cascade verdicts get a composite cache identity
(`cascade:<structural>+<accuracy>`) so they never collide with a single-model judge's.

**Why the fixed split, not the "escalate-only-on-Haiku-flags" variant:** Action A showed
Haiku misses 57% of flags, so escalating only where Haiku flags would inherit Haiku's 43%
recall. The fixed split sends the accuracy block to Sonnet every time a fact sheet exists,
preserving recall.

Validation over the 80-item gold set (same harness, temp 0):

| Dimension | Single Sonnet | Single Haiku | **Cascade** |
|---|---|---|---|
| present | 96% | 94% | **96%** |
| prominence | 88% | 86% | **89%** |
| framing | 93% | 94% | **94%** |
| **flag recall** | 95% | 43% | **100%** ✅ |
| flag precision | 42% | 56% | **36%** |

**Ship gate MET:** flag recall 100% (≥ Sonnet) and structural κ non-regressing (actually
+1pp on prominence/framing — the dedicated brands-only prompt *helps* Haiku by removing the
accuracy distraction). **Regression to note:** flag precision dipped 42%→36% (58 judge
flags vs 48) — isolating the accuracy task makes Sonnet over-flag slightly more. Same root
cause as queue #9; fixing #9 on the accuracy prompt also fixes it here.

**Wiring:** `--cascade` on `audit`/`judge`, `JUDGE_CASCADE=1` for calibration/API, settings
`JUDGE_STRUCTURAL_MODEL` (default Haiku) / `JUDGE_ACCURACY_MODEL` (default Sonnet). Default
stays single-Sonnet per §5. 8 unit tests + full suite (206) green; mypy/ruff clean.

**Next levers (B1/B2):** few-shot + reasoning-first to lift Haiku's *standalone* flag
recall — if they close enough of the gap, the accuracy pass could move to Haiku too and even
the full-run path becomes near-pure-Haiku.

### 4.2 Atomic verifier (idea #4) — built & solved queue #9 (2026-06-28)

The judge over-flags: low precision from omission/confirmation/sheet-silent "flags" its
own prompt forbids. A prose delete-gate in `_ACCURACY_BLOCK` only nudged it (42%→44%).
The fix is **per-flag adversarial verification** (`_verify_flags`): after the judge
proposes flags, each flag is sent **alone** to a verifier (`record_verdict` keep/drop) with
four mechanical drop-rules (omission / confirmation / sheet-silent / not-stated). A focused
yes/no per flag is honoured far better than a global instruction. Recall-safe by
construction: it only removes flags and `_verdict_keep` KEEPS on any failure/uncertainty.
Opt-in via `--verify` / `JUDGE_VERIFY`; folded into the cache identity (`...+verify:<model>`)
so verified verdicts never collide with unverified ones.

Iteration (80-item gold, the loop the guardrail in §5 demands):

| Step | precision | recall | note |
|---|---|---|---|
| baseline | 42% | 95% | 28 FP |
| + prompt delete-gate | 44% | 95% | shipped by default |
| + Haiku verifier | 67% | 76% | Haiku over-drops real flags (gun-shy, per §3.1) |
| + Sonnet verifier | 62% | 86% | better, but a bad "range-contains" drop rule killed 2 real price flags |
| **+ Sonnet verifier, range rule removed** | **80%** | **95%** | **final — precision ~doubled, 0 TPs lost (5 FP / 20 TP / 1 FN)** |

Two evidence-driven fixes mattered: (1) the verifier model must be **Sonnet** — a Haiku
verifier inherits Haiku's flag-blindness and drops real flags; (2) the "a range that
*contains* the sheet price is agreement" rule was **wrong** — a range like "$299–$549" vs
the sheet's $399/$499 misrepresents the price and IS a real flag (the bad rule came from
misreading multiset-paired FP labels). Removing it recovered the 2 dropped true positives.

**Default:** `JUDGE_VERIFIER_MODEL` defaults to `JUDGE_MODEL` (Sonnet). Verifier stays
opt-in; recommended ON (`--verify`) for client deliverables (adds ~1 Sonnet call per
proposed flag — flags are few). The held-constant base judge is unchanged for
calibration/gold.

## 5. Guardrails

- **Never ship a judge change without re-running calibration** against the gold set — you
  have the scoreboard (`judge_metrics.py`), so prove each change moves κ / flag-recall
  instead of guessing.
- Any prompt edit invalidates the judge cache by design (fingerprint changes) — fine, but
  budget a re-judge.
- Keep **Sonnet (temp 0) as the held-constant judge for calibration/gold and paid client
  deliverables**; the cheap-model work here is for the dev/iteration loop and, if the
  cascade proves out, for the live path's easy-case majority.

## 6. Follow-ons (lower priority, from the menu)

The tiered cascade (#2), atomic decomposition (#4), and selective self-consistency (#5) are
captured above; pick them up only if Action A shows few-shot + reasoning-first (B1+B2)
don't close the gap on their own.

---

_Files this touches: `src/pipeline/judge.py` (prompt, tool, model routing),
`src/pipeline/judge_cache.py` (fingerprint), `src/pipeline/judge_metrics.py` +
`scripts/run_calibration.py` (measurement), gold sets in `data/`, `settings.JUDGE_MODEL`._
