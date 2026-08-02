---
name: audit-packaging
description: Standing rules for how the client-facing GEO audit is packaged, worded, scored and charted. Load this before touching ANY report-facing code — web/components/report-view.tsx, charts.tsx, badges.tsx, web/app/audits/*, src/api/reports.py, src/pipeline/metrics.py, trend.py, lifecycle, priority or themes modules, digest/PDF/export paths, severity or finding taxonomies, or the methodology and disclaimer copy. Also load it when writing or reviewing any text a client reads, when deciding how to display a rate, delta, grade, severity or chart, when adding a finding type, or when executing any task in docs/audit-packaging-spec.md. These rules exist because the audit is sold; violating them costs credibility or creates legal exposure.
---

# Packaging the audit

The audit is a **paid, recurring deliverable** for a marketing team, and its whole pitch is *"we
catch what AI gets wrong about you."* That means the report is held to a higher evidentiary standard
than an internal dashboard: a finding a client can't verify, a number without a denominator, or a
sentence that overclaims does more damage here than a missing feature.

**Build spec:** `docs/audit-packaging-spec.md` (task list, dependency order, acceptance criteria).
**Research basis:** `docs/audit-packaging-research.md` (~500 sources; read only when a rule's
rationale matters). **Repo rules still apply on top of these** — see `CLAUDE.md` and the `geo-dev`
skill; where this file and a hard invariant in `CLAUDE.md` seem to conflict, `CLAUDE.md` wins and you
should flag the conflict rather than resolve it yourself.

## The five rules that are never negotiable

1. **No rate without its denominator.** At 3–5 runs × 4 engines, a 50% mention rate has a Wilson 95%
   CI of roughly 25–75%. Write **"7 of 12 runs"** with the percentage secondary — never a bare
   percentage, never a trend arrow without a significance gate. Use Wilson or Agresti–Coull, never
   Wald (unreliable near 0/100% at small n). Read the real denominator from the payload;
   `RUNS_PER_QUERY` defaults to 5 but stored runs vary.
2. **Never render an internal ID to a client.** `cat-01`, `cmp-05`, `pa-03`, `finding_id`, run
   UUIDs. Show the verbatim query in quotes with its engine and intent label. IDs are join keys, not
   content.
3. **Attribute every claim to a named model and a date.** "ChatGPT (checked 2026-06-13) states…" —
   never "AI says." A finding without engine + timestamp + verbatim prompt is not shippable.
4. **Never claim an outcome.** No "we'll get you cited," "guaranteed visibility," "this fix will
   raise your score." Recommendations are assessments of likely contributing sources. The FTC
   enforcement pattern against guaranteed-ranking SEO claims applies identically here.
5. **Never silently rewrite history.** Prior cycles' numbers are immutable (storage is create-only
   by design). When an engine changes underneath the measurement, annotate the cycle and start a new
   comparable series — never retro-adjust, never quietly re-baseline.

## Voice for findings

Flat, factual, third person — the register of a lab report or a CVE writeup, not a security vendor's
marketing. Severity carries the alarm; the prose does not.

- **Verbs:** "states," "describes," "lists," "omits." **Not** "falsely claims," "lies about,"
  "hallucinates that." Anthropomorphizing a model is both imprecise and legally careless when the
  vendor is named.
- **Stale ≠ fabricated.** "This was true once and hasn't been corrected" is a different, more
  accurate, and less inflammatory claim than "the model made this up." Say which one it is.
- **Prefer** "outdated," "unsupported by current source," "not verifiable against current
  documentation" over loaded words.
- **Every finding needs a "why it matters"** in business terms and **a concrete next action** with an
  owner. A finding with no action is the #1 cited driver of churn in this category — if you can't
  name the action, the finding isn't finished.
- Short active sentences. Second person for the client's action, third person for the model's output.

**Shape:**
> **{Theme} — {Severity}**
> {Engine} (checked {date}, {N} of {M} runs) states *"{verbatim excerpt}."*
> {The correct fact, from the fact sheet.}
> **Why it matters:** {one or two sentences of business consequence — not restated data.}
> **Fix:** {concrete action + channel.} *(Owner: {role} · Effort: {S|M|L})*

## The non-reproducibility disclosure — use verbatim

A client *will* re-run a prompt, get a different answer, and doubt the report. Pre-empt it; never let
them discover it. Ship this once per report, in the methodology section. **Do not paraphrase** — it
has been written to be honest without being self-undermining:

> We do not claim these errors are permanent or that they will reproduce on demand. AI models are
> updated frequently and produce different answers to identical prompts even when nothing about your
> brand has changed — a documented property of how these systems are served, not a flaw in our
> testing. Each finding states how many independent attempts we made, how many produced the error,
> the exact date and time, and the exact prompt used. Our claims are about what we observed, when —
> not a guarantee of what you will see if you ask right now.

Per-finding, the short form is the occurrence line: *"observed in 4 of 5 runs across 06-11 → 06-13."*

## No invented scores

**The report has no letter grade and no composite score.** Every headline number is either
*counted* (findings, resolved, cycles open) or *measured* (sampled rate, share of model).
This is a hard rule, and it is the one most likely to be quietly re-litigated — an earlier
draft compromised to "split the grade into two subscores," which smuggled a `B−` straight
back onto page 1.

Why it stays dead:

- A static score is the hero metric of a **one-off** audit. This is a recurring product, and
  its hero is the delta and the closing backlog — which the page already carries twice
  (accountability strip, per-engine deltas). A grade is redundant on top of them.
- A grade over our own rubric is opaque, unauditable and unmovable by the client. Moz DA,
  Klout, Nutri-Score and HubSpot Grader are the cautionary tales. Nobody can act on a `B−`.
- Grading a pre-launch brand on visibility it structurally cannot have is a category error —
  a thin file, not a bad score. Credit bureaus distinguish the two for exactly this reason.

**Instead, the scorecard row carries four measured tiles:** AI visibility ("8 of 24",
delta) · share of model (vs named competitor) · open findings (themes · critical count ·
instances) · **oldest still open** (cycles, naming the finding). The last one replaces the
grade and does the job better — SLA-style aging is what creates pressure to act, and it's a
count, not an opinion.

**Foundation readiness survives as a checklist, not a letter** — fact sheet ✓ · schema ✗ ·
PR footprint partial — placed later in the report where it is directly actionable.

If a score is ever reintroduced, its full rubric must be published in the methodology
section. Publish the *rubric and inputs*; keep the *prompt library and detection heuristics*
private, so brands fix underlying data rather than teaching the test.

## Severity

Four levels, ordered Critical → High → Medium → Low, always in that order — never chronological,
never alphabetical.

| Level | Trigger |
|---|---|
| **Critical** | Category/identity error, or a factual claim that materially changes a purchase decision (price, availability, confusion with another company) |
| **High** | Invented or materially misstated capability; competitor attributes applied to the client |
| **Medium** | Omission/understatement of a real capability; stale-but-becoming-true claims |
| **Low** | Imprecise phrasing; unverifiable but not contradicted; cosmetic |

- **Lead with the count bar** — "3 Critical · 12 High · 40 Medium · 180 Low" — *before* any
  individual finding. Most readers stop there; that is the design intent, not a failure.
- **Severity is a monochrome navy ramp — darkest is most severe.** Critical `#0E2340` ·
  High `#12325C` · Medium `#697585` · Low `#B2B7BC`. There is no red and no gold in Sable;
  the palette has no alert hue at all, and "no colours outside the palette" is an explicit
  Don't. The ramp mirrors the mark's own logic — the plumes step tone with height so the eye
  lands on the tallest, darkest form.
- **Icon + label on every tier, never colour alone.** Load-bearing here, not
  belt-and-braces: with a single-hue ramp colour genuinely cannot carry the distinction.
  It also fixes colourblind rendering and grayscale printing.
- Full cards for Critical/High only. Medium/Low collapse into a compact table.

## Brand — non-negotiable

The report wears **Sable** (Identity Guide, Berkeley v1.0). **This supersedes the "weir"
system in `geoWebsite`** — different typefaces, a different navy, and Sable has no gold.
Never mix tokens between them. Full spec: `docs/audit-packaging-implementation.md` §4.9.

- **Cormorant Garamond is display only** (headlines 32px+, tracked +0.01–0.04em, italic for
  emphasis only). **Libre Franklin is text and UI** (body 15/1.7, label 10/0.36em).
  The wordmark always stays Garamond.
- **Sentence case everywhere. The only uppercase in the system is the tracked label.**
  Chips read "Up from 1 of 6", never "UP FROM 1 OF 6".
- Palette: Berkeley Navy `#0E2340` (ink) · Sable Blue `#12325C` (links, active) ·
  Harbour `#697585` (body) · Mist `#B2B7BC` (rules) · Paper `#F2F1EC` (ground).
- **Sky `#7FA6D9` is legal on navy only, never on paper.** It is the one bright note in the
  system and loses its job if used twice on a page. In the report that means the masthead
  band — and nowhere else.
- The mark is three rising plumes (teardrop, three rounded corners, one square heel, shared
  baseline, tone stepping with height). Clearspace one plume-width. Never rotate, stretch,
  squash, or recolour it.
- Client-facing brand lives behind **one config object** — an agency white-label replaces
  the entire Sable skin, not just an accent colour, so build both skins from the abstraction.
- Both faces are metrically unlike `system-ui`: **re-measure every print layout after fonts
  land.**

## Charts

- **No donuts.** Arc-angle comparison across non-adjacent segments is a known perceptual weak point;
  use a 100% stacked horizontal bar. (Semrush's own design system caps donuts at 5 segments and says
  never use them to compare value sets.)
- **Heatmaps carry numbers in every cell.** Color to scan, digits to verify.
- **Change is a property of every chart, not its own chart** — delta pills on tiles, paired bars,
  arrow glyphs in cells. On a recurring report the delta is the second-largest element on a tile,
  after the value.
- **Fixed axis order across cycles.** Engine columns in a memorized order; the client row pinned. A
  chart whose layout moves between editions cannot be compared at a glance.
- Sequential single-hue ramps for magnitude. Don't add a charting dependency — recharts is already
  the heaviest thing in the bundle; hand-rolled SVG for bump charts.
- Every chart needs an empty state and a single-row state. Both are common in this data.

## The recurring contract

- **Lead with what changed**, not with a static score. Then the accountability line: *"3 of 7
  findings from last cycle are resolved, 1 regressed, 4 still open. 19 resolved since we started."*
  That sentence answers "did your recommendations do anything," which is what determines renewal.
- **Findings have a lifecycle** — new / persisting / resolved / regressed. Regressed outranks a
  same-severity new finding: a fix that didn't hold is worse news than a fresh problem.
- **"Flat" is a claim, not a blank.** *"Held steady at 8 of 12 runs on ChatGPT for the 3rd straight
  week."* A weekly product that manufactures news in flat weeks destroys itself faster than one that
  reports nothing happened.
- **Only compare like instruments.** A run is comparable only to a run with the same
  `query_set_version`. If the version changed, say so and show no comparison — never silently
  compare across a changed query set. Weekly is the *reporting* frequency, not the
  *instrument-change* frequency.

## Copy that is off-limits

| Don't write | Because |
|---|---|
| "AI is lying about you" / "hallucinating" | Anthropomorphizes, and edges toward defamation-adjacent language about a named vendor |
| "Guaranteed" anything | FTC substantiation standard; the SEO guaranteed-ranking enforcement pattern applies |
| A vendor logo or stylized wordmark | Nominative fair use covers plain-text names, not logos implying endorsement. Plain text only, plus the independence disclaimer |
| "Peer benchmark" for reference-panel data | Famous reference brands score systematically higher than a median client; calling it a peer benchmark is dishonest. Say "market context" |
| "FactCheck" as a product/feature name | Profound already ships a feature by that name for this exact use case |
| "What people actually ask AI" | No vendor in the category has published a sample size or validation study for prompt-volume claims. Don't inherit an unverifiable claim |

Every report carries the independence disclaimer: not affiliated with, sponsored by, or endorsed by
OpenAI, Anthropic, Google or Perplexity; product names used solely to identify which system produced
the observed output.

## Scope boundaries

- **The web report is the deliverable** — `web/components/report-view.tsx` + `charts.tsx` +
  `web/app/audits/[id]/`, fed by `src/api/reports.py`. This is what produced the client PDF.
- **`teaser/src/render/audit/*` is a separate, out-of-scope renderer.** Don't port packaging changes
  there and don't try to keep them in sync. `docs/audit-deliverable-fix-plan.md` is that path's own
  older, unstarted plan — unrelated to this work.
- **Theme classification, priority scoring, severity mapping and finding IDs are deterministic
  Python.** No LLM calls — they must be reproducible, free, and stable across re-renders.
- **The only sanctioned LLM in the report layer is template-constrained narrative generation**, and
  only behind a deterministic post-check that every quantitative claim in the prose matches a value
  in the findings table. A hallucinating summary in a hallucination-detection product is the single
  worst failure mode available; treat that post-check as load-bearing and never weaken it to make a
  test pass.
