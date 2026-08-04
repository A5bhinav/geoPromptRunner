# Packaging the GEO Audit as a Recurring Product — Master Research

**Compiled:** 2026-07-31
**Method:** 12 parallel research agents across two waves, ~500 web sources
**Input artifact:** the 41-page `Fort — GEO Audit` PDF (2026-06-13, 4 engines, 3 runs/query, 235 accuracy flags)
**Status:** research only. No code changed.

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Diagnosis of the current deliverable](#2-diagnosis-of-the-current-deliverable)
3. [Competitive landscape](#3-competitive-landscape)
4. [The core architectural move: flags are a backlog](#4-the-core-architectural-move-flags-are-a-backlog)
5. [Statistical honesty](#5-statistical-honesty)
6. [Report architecture](#6-report-architecture)
7. [Visual and data-design spec](#7-visual-and-data-design-spec)
8. [Delivery architecture](#8-delivery-architecture)
9. [The input side: query sets, fact sheets, calibration](#9-the-input-side-query-sets-fact-sheets-calibration)
10. [Naming, voice, and metric branding](#10-naming-voice-and-metric-branding)
11. [Evidence, reproducibility, and defensibility](#11-evidence-reproducibility-and-defensibility)
12. [Operations: running this at 1 → 50 clients](#12-operations-running-this-at-1--50-clients)
13. [Benchmarks, indices, and the moat question](#13-benchmarks-indices-and-the-moat-question)
14. [Pricing and packaging](#14-pricing-and-packaging)
15. [Sales collateral and buyer journey](#15-sales-collateral-and-buyer-journey)
16. [Contradictions and calls](#16-contradictions-and-calls)
17. [Build order](#17-build-order)
18. [Open questions](#18-open-questions)
19. [Source index](#19-source-index)

---

## 1. Executive summary

**The thesis.** The audit's differentiated asset is the catalogue of severity-graded factual errors AI models state about a client brand. It is currently buried under 30 pages of undifferentiated red cards. The product should be repackaged around *accuracy findings as a tracked, closing backlog* — the vulnerability-management model — where every weekly edition leads with what changed and what got fixed.

**Seven findings that should change what gets built:**

1. **The flag list is structurally a vulnerability backlog.** Qualys/Snyk solved weekly reporting on a slow-moving issue list a decade ago. Adopt their four-state lifecycle (new / persisting / resolved / regressed). The highest-value sentence in the whole product becomes *"3 of 7 flags from last week are resolved, 1 regressed, 19 resolved since we started."*

2. **235 flags is roughly 10 root causes repeated.** Crash-dedup research, incident root-cause taxonomies, and qualitative coding all say: code every instance, report themes with counts. This collapses 30 pages to 4–6.

3. **Most week-over-week movement in the current design would be noise.** At n=12 per engine-week, a 50% mention rate has a Wilson 95% CI of ~25–75%. Ship significance gating and let most weeks honestly say "Flat."

4. **More prompts beats more runs.** MaxAEO's ICC analysis: within-prompt correlation ~0.57 means 20 prompts × 30 runs has an *effective* sample of ~34. Breadth buys statistical power; repeat runs don't. The current 3 runs/query is the right order of magnitude — the query set is what's under-invested.

5. **The accuracy white space closed while wave 1 was running.** Wave 1 concluded nobody owns hallucination tracking. Wave 2 found **Profound shipped "FactCheck"** — explicitly "the first way for brands to analyze AI accuracy at scale," comparing AI claims against a brand's own source of truth across pricing/spec/feature/policy errors. The category is no longer empty. See [§3](#3-competitive-landscape) and [§16](#16-contradictions-and-calls).

6. **There is a live ToS risk that could threaten the collection pipeline.** Consumer-facing terms at OpenAI and Perplexity contain language prohibiting automated/programmatic querying of the web products. API terms are materially more permissive and silent on benchmarking. **Confirm which surface the pipeline actually hits.** See [§11](#11-evidence-reproducibility-and-defensibility).

7. **Weekly cadence is cheap on compute and expensive on credibility.** *(Superseded by measured data — see `audit-packaging-implementation.md` §3.0. Measured: $0.0736/call across 6 surfaces, $5.52 per 25-query run at K=3. The estimate below was ~4× high on a per-query basis.)* The binding constraint is judge QA labor and the risk of manufacturing news in flat weeks — not API spend.

---

## 2. Diagnosis of the current deliverable

Read directly from the Fort PDF; corroborated independently by four wave-1 agents.

| Problem | Consequence |
|---|---|
| No executive summary — page 1 is tiles | A CMO reads one page. There is no page for them. |
| Big red **"F"** for a pre-launch startup | Structurally unearnable — Fort hasn't shipped. Reads as punitive and unactionable. |
| 30 pages of 235 identical flag cards | No hierarchy → no triage → nobody reads any of it. |
| Massive flag redundancy | "Confused with Fitbit," "confused with a pickleball app," "not a recognized brand" are one root cause repeated dozens of times. |
| No recommendations anywhere | The report ends at diagnosis. 68% of agency churn is attributed to lack of proactive guidance vs 37% price. |
| Opaque query IDs (`cat-01`, `cmp-05`, `pa-03`) | The losing-queries table — arguably the most actionable data — is unreadable. |
| One document doing three jobs (skim / drill-down / archive) | The structural bug. Split the jobs; don't shrink the doc. |
| No comparison to anything | Fatal for a recurring model. A recurring report with no delta is a status update, not a signal. |
| Funnel-stage data computed but unused for ranking | Bottom-funnel pricing errors and awareness-stage trivia are presented identically. |

### The four sections that already work
- The competitive share leaderboard (needs a week-over-week pairing, not replacement).
- Mention/citation by funnel stage (needs to drive prioritization, not just be displayed).
- Top cited domains (needs reframing as "pursue correction here").
- The accuracy flags themselves — the raw material is excellent. The presentation is the failure.

---

## 3. Competitive landscape

~20 vendors reviewed across both waves.

### 3.1 Pricing and packaging table

| Vendor | Entry | Mid | Metering | Cadence | Confidence |
|---|---|---|---|---|---|
| **Profound** | $99/mo (ChatGPT only, 50 prompts) | $399/mo (3 engines, 100 prompts, 9,000 responses) | Prompts × engines × responses; regions/languages gated | Daily | Verified (vendor page) |
| **Peec AI** | ~€89/mo (25–50 prompts) | ~€199 → €499+ | Prompts; engines as paid add-ons | Every 24h | Secondary |
| **AthenaHQ** | Free ($25/300 credits, 5 engines) | $295/mo (3,600 credits, 9 engines, API) | Blended credits | Not disclosed | Verified |
| **Scrunch AI** | 7-day trial | $250/mo Core; $500 Agency | Prompts + page audits + topics | ~every 3 days | Verified |
| **Otterly.AI** | $29/mo (15 prompts) | $189 / $489 | Prompts; Claude & Gemini are add-ons | Weekly | Secondary |
| **Evertune** | — | $800/mo Pro (100k prompts, 11 models) | Prompt volume | Configurable | Verified |
| **Goodie** | $399/mo (100 prompts, 3 engines) | Custom | Prompts × engines × optimization actions | Not disclosed | Verified |
| **Rankscale** | $20 → $99 → $385 → $780 | — | Credits | Daily | Mixed |
| **Gauge** | $99 → $599 | — | Tests ($1/test overage) | Daily | Verified |
| **Knowatoa** | $59 → $199 → $499 | — | — | Daily | Verified |
| **Trakkr** | $100 → $500 | — | — | Weekly synthesis | Verified |
| **Am I on AI** | $49/mo | — | — | Weekly | Secondary |
| **Ahrefs Brand Radar** | $129 base + $699 AI indexes | ~$828/mo effective | 2,500 prompt-checks/mo | AI index refresh monthly | Secondary |
| **Semrush AI Toolkit** | ~$99/mo add-on | — | Per domain | Daily/weekly mixed | Unverified |
| **seoClarity (ArcAI)** | ~$2,500/mo | — | — | — | Secondary |

**Agency service pricing (blog-sourced, directional — no survey data exists yet):** one-off AI-search audit $1,500–$7,500 · monitoring retainer $500–$2,000/mo · standard retainer $3,000–$9,000/mo · premium $10,000–$18,000/mo · enterprise $20,000–$30,000+/mo.

### 3.2 De-facto conventions (table stakes)

1. A single **named** composite score as hero metric (AI Brand Index, Visibility Score, AI Readiness Score, Influence Score).
2. **Per-engine breakout, never blended-only.** Universal.
3. Competitor benchmarking as a first-class section.
4. Citation/source tracking as the second major section.
5. A named "Actions" surface (depth varies wildly — mostly hand-waving).
6. Daily-to-weekly refresh. Monthly is now openly called stale (Ahrefs gets dinged for it publicly).
7. **Dashboard-first, PDF as export.** PDF-primary is the outlier; it reads as legacy agency.

### 3.3 White space — and what closed

**What is still open:**
- **Week-over-week diffing as a narrative.** Everyone has a trend line; nobody ships "here's what changed and the one thing to fix." Only agency templates (Averi, Cognizo) describe it, and those are consulting content, not shipped product.
- **De-duplicated, triaged findings.** The 235-flag problem is the category's problem. No vendor collapses N findings into a triaged top-5.
- **Executive-vs-practitioner tiering.** Only Evertune claims "executive-friendly framing" as a design goal.
- **Published methodology, drift policy, and error rates.** A comparison of GEO platforms found *no vendor publicly documents* how they handle engine model-version changes or API failures. Publishing a real data-integrity policy is a credible differentiator.
- **Accuracy as a *tracked, closing* backlog** — even Profound's FactCheck (below) is a measurement surface, not a lifecycle.

**What closed (important correction to wave 1):**
- **Profound launched "FactCheck"** — "the first way for brands to analyze AI accuracy at scale," comparing AI claims against the brand's own source of truth, tracking pricing / spec / feature / policy / rebrand errors. Their copy is notably clinical ("claims a brand never made," never "lies").
- "Brand Accuracy" is now used descriptively by Storyzee, Metricus, LSEO, CrawlQ. "Hallucination Detection" is used by Trakkr to describe a competitor feature.
- **Aggregate indices are crowded:** Profound Index (1.5bn prompts, daily), Similarweb 2026 Generative AI Brand Visibility Index, Conductor 2026 AEO/GEO Benchmarks (13,770 domains, 5.5M AI responses, 100M+ citations).

**Read:** the accuracy category is now contested, not empty. The remaining defensible position is not *"we measure accuracy"* but *"we run accuracy as a governed, auditable remediation program with a signed ground-truth document, a published rubric, human QA, and a closing backlog."* That's a workflow and methodology claim, not a data claim.

### 3.4 Independent validation of the existing methodology

Arcalea's teardown of AI-visibility reporting found:
- **2.3% citation consistency** across 3 identical ChatGPT runs — single-run reports are "statistically meaningless."
- AI Mode / ChatGPT swap **56–74% of cited sources weekly** — monthly cadence is too slow.
- Blending engines into one score hides platform-specific problems.

Their prescription — 3–5 runs per prompt, per-platform separation, persona-specific prompts, weekly cadence — is almost exactly the existing pipeline. **The methodology is the market's stated best practice and is currently invisible in the PDF. Sell it.**

---

## 4. The core architectural move: flags are a backlog

The single strongest structural insight across both waves.

235 accuracy flags is structurally identical to a vulnerability backlog. That industry solved "how do you report weekly on a slow-moving issue list without becoming noise."

### 4.1 The lifecycle

Qualys's four-state model, renamed:

| State | Definition | Treatment |
|---|---|---|
| **New** | First appeared in this week's runs | Chip, no age badge |
| **Persisting** | Present last week and still present | Chip + age badge ("open 3 weeks") — the SLA-aging analogue |
| **Resolved** | Was flagged, now absent across engines | Counted in the "N of M fixed" line |
| **Regressed** | Was resolved, has returned | Distinct badge. This is the state that should hit hardest — a prior win wasn't durable |

Snyk adds the piece Qualys doesn't emphasize: an **Identified-vs-Resolved cumulative trend chart where the gap between the lines is the visible backlog**, plus SLA aging buckets and a time-to-resolve velocity metric.

### 4.2 The accountability line

Lead every edition with:

> **"3 of 7 flags from last week are resolved, 1 regressed, 4 still open. 19 resolved since we started."**

This is the answer to "did the work you recommended do anything," which is what determines renewal. Nobody in GEO does this. Am I On AI comes closest with post-fix re-measurement ("+42% AI mentions").

### 4.3 The root-cause taxonomy

Evidence base: crash-deduplication by root-cause signature (Igor, ACM), Microsoft's AutoARTS incident root-cause taxonomy for Azure, Google SRE postmortem practice, and qualitative coding's codes-vs-themes distinction (code every instance, report themes with counts and representative quotes). Support-ticket taxonomy practice says top-level categories should number ~8–12, be mutually exclusive, and be organized around *who fixes it*.

Proposed level-1 taxonomy — each rendered as one card with an instance count, 2–3 verbatim quotes, engines/stages it clusters in, and one fix:

| # | Theme | Example level-2 clusters (from the Fort data) |
|---|---|---|
| 1 | **Identity & disambiguation** | confused with Fitbit; with a pickleball app; with Fortnite/Fortinet; "not a recognized brand" |
| 2 | **Category / domain confusion** | described as an app or software platform; as a barbell clip-on sensor; as a screen smartwatch |
| 3 | **Existence & lifecycle status** | reviewed as a shipping product; called "new entrant" without pre-launch status |
| 4 | **Pricing & offer accuracy** | $100–300 range (Fitbit's); ~$200; $349; "one-time purchase"; $10/mo subscription |
| 5 | **Feature accuracy — invented** | form analysis; personalized workout plans; community/coaching; GPS; notifications |
| 6 | **Feature accuracy — omitted/understated** | "limited recovery metrics"; "basic fitness tracking"; "narrow use case, lifting only" |
| 7 | **Competitive mischaracterization** | Fitbit attributes applied wholesale; omitted from comparisons it should appear in |
| 8 | **Founder / company facts** | funding, HQ, team composition |
| 9 | **Availability & geography** | where/how to buy; platform support ("no Android app") |
| 10 | **Source & citation quality** | cites stale articles superseded by the current pricing page |

*(Recommend adding an 11th for other clients: **Risk & reputation** — "is X reliable," "X lawsuit," "X layoffs" — where hallucination and defamation risk concentrate. See [§9](#9-the-input-side-query-sets-fact-sheets-calibration).)*

On the Fort data this collapses ~30 pages into 4–6.

### 4.4 The finding card spec

Synthesized from Lighthouse opportunities, Snyk issue cards (severity + exploit maturity + reachability), axe/WAVE accessibility findings, Semrush thematic issues, and SOC 2 gap analyses:

| Field | Notes |
|---|---|
| Claim ID | Stable, CVE-style (`FORT-2026-07-014`) so it can be tracked across editions |
| Human title | Plain language, ~8 words, never an internal ID |
| Root-cause theme | From the level-1/level-2 taxonomy |
| Severity | Critical/High/Medium/Low, defined by business consequence with objective triggers |
| Reach | Sampled-rate phrasing ("6 of 10 runs") + which engines + funnel stage(s) |
| Evidence | Verbatim prompt, engine + version, session context, timestamp, verbatim excerpt, screenshot |
| Why it matters | 1–2 sentences of business consequence, not restated data |
| Correct fact | From the signed fact sheet, with source URL and date |
| Root-cause hypothesis | Labeled as hypothesis: stale third-party listing, name collision, training lag |
| Recommended fix | Concrete action + channel (owned site/schema, PR, directory correction, review site) |
| Owner | Marketing / PR / Eng / Legal |
| Effort | S/M/L, mapped to fix channel |
| Expected impact | Which subscore moves, qualitatively |
| Verification | What re-check closes it next cycle |
| Status | New / Persisting / Resolved / Regressed |

### 4.5 Prioritization

Adapted RICE — a 2×2 severity matrix is insufficient for 235 heterogeneous findings:

```
Priority = (FunnelStageWeight × Reach × Magnitude × Confidence) / Effort
```

- **FunnelStageWeight** — bottom-funnel (pricing, comparison) ×3, awareness ×1. *The funnel-stage data already exists and drives nothing.*
- **Reach** — sampled rate, which engines.
- **Magnitude** — distance from fact sheet ($200 vs $289 = 31% under; "pickleball app" = categorical).
- **Confidence** — directly observed and unambiguous vs. a borderline judge call.
- **Effort** — by *fix channel*, not dev time: owned site/schema = S; third-party listing (Crunchbase, review site) = M; training-data misconception = L.

Worked example — *"Perplexity says the price is $200; it is $289"*: Reach moderate (6/10 Perplexity, 2/10 ChatGPT), FunnelStageWeight 3 (pricing = decision stage), Magnitude high (31% under, directly affects a buy decision), Confidence high, Effort M (likely a stale third-party listing + missing structured pricing data). Ranks far above a founder-bio error appearing once on an awareness query — a distinction the current report cannot make.

---

## 5. Statistical honesty

This is both a correctness requirement and a differentiator, because the market ships naive trend arrows with no error bounds.

### 5.1 The numbers

At 3 runs × 4 engines = **12 samples per query per week**:
- A 50% mention rate has a **Wilson 95% CI of roughly 25–75%**. Use Wilson or Agresti–Coull, not Wald — Wald is unreliable near 0/100% at small n.
- MaxAEO's ICC analysis: within-prompt correlation across repeated runs is **~0.57**, producing a design effect that collapses "20 prompts × 30 runs = 600 answers" to an **effective sample of ~34**. Brand-identity effects are ~1.5% of total variance; within-prompt resampling noise is ~35%.
- **Conclusion: adding runs to a narrow query set buys almost nothing. Adding prompts buys real power.** 3 runs is the right floor; the query set is what's under-invested.

### 5.2 The rules

1. **Never publish a bare percentage from n=12.** Use "7 of 12 runs." Statistically honest and it signals rigor.
2. **Compare 3–4 week rolling averages**, not raw weekly points. Google Search Console added weekly/monthly aggregation views specifically because day-over-day comparison manufactures fake variance (Mondays vs Thursdays).
3. **Two-gate significance.** Label Up/Down only if it clears *both* statistical significance *and* a minimum absolute threshold:
   - Per-engine weekly: `|Δ (3-week rolling avg)| ≥ 15pp` **and** non-overlapping Wilson CIs.
   - All-engine aggregate (n≈240/week, ≈720 rolling): `≥5pp` with a two-proportion z-test at p<.05.
4. **Everything else renders "Flat"** — and Flat is a claim, not a blank: *"Held steady at 8 of 12 runs on ChatGPT for the 3rd straight week."*
5. **Show a confidence band on the trend line**, Datadog-anomaly-style: a shaded normal range from prior weeks, only out-of-band points marked.

### 5.3 Why this is a selling point

A representative 2026 GEO metrics guide ships trend arrows (↑↓→) with **no confidence intervals, no error bounds, no volatility flags**, and never addresses run-to-run LLM variance. Independent commentators (Canonry, aicarma, SparkToro-cited research) are actively calling out vendors for selling false-precision rankings on non-deterministic systems. GPT-4's accuracy on one benchmark task moved from 84% to 51% between two 2023 releases with no announcement.

The honest posture — *"we don't sell you a score, we sell you a rate across repeated runs with a volatility band"* — is both correct and a differentiator most competitors won't match, because matching it means admitting their single numbers are noisy.

---

## 6. Report architecture

**Before:** 41 pages — tiles → donut → funnel bars → 30pp flag dump → domains → ID table.
**After:** ~13–18 page body + linked data appendix.

> **SUPERSEDED 2026-08-04.** The authoritative section order is now **"The report contract"**
> in `audit-packaging-spec.md`. Two things below are retired: row 4's scorecard framing
> (the grade is gone entirely — see spec P1-T6 and TR-T0), and the single-body page target
> (the deliverable is now 13–16 pp of front matter plus 12–20 pp of back-matter tables).
> The table is kept for the reasoning behind each section, not as the build target.

Evidence base: Minto Pyramid Principle (answer first), SCQA, BLUF, McKinsey one-page exec summary structure (Objective → Situation → Complication → Resolution → Benefits → CTA, with the key sentence of each block bolded), and Eval Academy's tiered-report argument (1–5 page summary / ~25 page mid / full appendix — three artifacts, not one document trying to be all three).

| # | Section | Length | Contents |
|---|---|---|---|
| 1 | Cover | ⅓ pg | Client logo + yours, "Prepared for X · Week of Y." No data. |
| 2 | **BLUF box + executive summary** | 1 pg | One sentence: standing + direction + the one action. Then SCQA. Bold the key sentence of each block. |
| 3 | **What changed this week** | 1 pg | Significance-gated delta chips per engine + the accountability line + top 3 movers |
| 4 | Scorecard, reframed | 1 pg | **Foundation Readiness** (fact sheet, schema, PR footprint — winnable pre-launch) vs **Current AI Visibility** (labeled "Baseline, Day 1" pre-launch, not graded F) |
| 5 | Competitive position | 1–2 pg | Paired week-vs-week leaderboard bar; bump chart of rank over time |
| 6 | **Engine breakdown** | 1 pg | Brand × engine heatmap — highest-value new chart |
| 7 | Funnel coverage | 1 pg | Stage × engine heatmap + "where you go dark" callouts |
| 8 | **This week's priority actions** | 1 pg | 3–7 ranked rows: theme, priority score, effort, owner, fix, expected effect |
| 9 | **Root-cause theme cards** | 4–5 pg | ~10 themes with instance counts + verbatim quotes (replaces the 30-page dump) |
| 10 | Flag backlog | 1 pg | Severity-count bar + New/Persisting/Resolved/Regressed table |
| 11 | Citation sources | 1 pg | Pareto bar (top domains + cumulative line), framed as "pursue correction here" |
| 12 | Top losing queries | 1–2 pg | **Verbatim query text**, engine, theme tag. Remainder → appendix. |
| 13 | Methodology | 1 pg | Engines + versions, query set, runs, judge rubric, sample sizes, drift log, corrections policy |
| — | Data appendix | CSV/portal | All instances tagged. Not printed inline. |

**Naming and readability:** every credible product shows the actual thing — Lighthouse shows the resource path, axe shows the DOM selector, Semrush shows the URL. `cat-01` / `cmp-05` / `pa-03` must never appear in a client-facing artifact. Show the verbatim query in quotes plus engine and funnel-stage label. Keep short IDs as a hidden join key in the backing CSV only.

---

## 7. Visual and data-design spec

### 7.1 Kill

The hero letter grade · the share-of-model donut · one-card-per-finding for Medium/Low · `position: fixed` for repeating print elements · hardcoded client branding.

### 7.2 Build

- **4–6 KPI tiles.** Value (large) + delta pill (second-largest element — for a recurring report the delta matters more than the value) + sparkline + `n=` sample size in small muted type. 4–6 is the scannability ceiling; group 3+3 with a visual break if six is non-negotiable. Reference: Stripe, Vercel Analytics, Linear Insights, Datadog (threshold line on tiles).
- **100% stacked horizontal bar** replaces the donut. Semrush's own design system caps donuts at ~5 segments and says never use them to compare value sets; non-adjacent arc-angle comparison is a known perceptual weak point.
- **Paired week-vs-week leaderboard bar.** The best existing chart — just add the comparison.
- **Bump chart** for competitive rank over time (inverted rank y-axis, one line per brand, ≤5 lines, direct labels, no legend). Hand-rolled SVG; no new dependency.
- **Brand × engine heatmap** — the single highest-value addition. Single-hue sequential ramp, **numbers inside cells always** (color for scanning, digits for verification, and color-alone fails accessibility), fixed cell size, stable memorized engine column order, rows sorted by aggregate with the client row pinned and bordered, plus a one-line "how to read this" caption. Precedent: cohort-retention tables (Amplitude, Mixpanel), Semrush position-tracking heat maps, Baymard UX benchmark grids.
- **Funnel-stage × engine heatmap** — client-only rows (diagnostic, not competitive). Don't build a 3D brand×stage×engine grid; run two grids.
- **Pareto bar** for citation concentration (top N domains descending + cumulative % line) — answers "are we dependent on 2 sources or 20," which a donut cannot past ~6 items.
- **Change as a property of every chart**, not its own chart: delta pills on tiles, paired bars, arrow glyphs in matrix cells, plus a compact "movers" text list (top 3 up, top 3 down).

### 7.3 Severity system

Four levels (Snyk's proven count; 5+ blur at a glance): Critical / High / Medium / Low.

- **Lead with a count-summary bar** — "3 Critical · 12 High · 40 Medium · 180 Low" — before any individual item. Most readers stop there, and that's the point. This is the direct fix for 235 red cards.
- Reserve red-family color for the top 1–2 tiers only. Icon + label token on every chip, never color alone (Carbon Design System rule; also survives grayscale printing and colorblind rendering).
- Order Critical → High → Medium → Low. Never chronological or alphabetical.
- Steal Lighthouse's "estimated impact" number per finding so severity ties to your own KPI language rather than a subjective adjective.
- **Collapse Medium/Low into a table** (finding, category, severity chip, first-seen date, status). Full cards only for Critical/High. This alone turns ~25 of 30 pages into 2–3 dense skimmable pages.

### 7.4 Density and rhythm

Tufte's data-ink ratio and Knaflic's decluttering argument both apply: identical framing on every card removes the only triage tool the reader has. Critical findings should look visually louder than Low ones; today they look identical, which is the actual bug — not "too much red."

Target six distinct visual textures across ~18 pages (cover / tiles / charts / heatmaps / cards / dense appendix table) instead of one texture repeated 30 times. Variety of layout, not volume of content, is what reads as premium.

### 7.5 Branding and white-label

Cover page (client logo + yours, "Prepared for X · Week of Y"), running header on every interior page, dedicated methodology page (also the legal-defensibility page), footer with confidentiality + contact.

Put the client-facing brand — name, logo, accent color — behind **one config object**, so cover/header/footer/chart-highlight all read from it. Vendasta and AgencyAnalytics white-label offerings center on exactly two levers: full logo/color swap, and optional "powered by" removal. Build both from day one; retrofitting a hardcoded brand is expensive.

### 7.6 Print CSS for headless Chromium

```css
@page { size: Letter; margin: 20mm 15mm; }

/* Chromium strips backgrounds by default to save ink */
* { print-color-adjust: exact; -webkit-print-color-adjust: exact; }

.finding-card, .kpi-tile, table tr, .chart-container { break-inside: avoid; }
.section-divider { break-before: page; }

table { border-collapse: collapse; }
thead { display: table-header-group; }   /* repeats header per page */
tfoot { display: table-footer-group; }

p { orphans: 3; widows: 3; }

/* Running headers/footers: NOT via CSS. See the note below. */
```

> **CORRECTED 2026-08-04.** An earlier version of this block used
> `position: running(header)` with `@top-center { content: element(header) }`. **Chromium does not
> implement `running()` or `element()`** — Chrome 131 shipped `@page` margin *boxes* but the
> running-element machinery was explicitly out of scope, so that CSS silently produces no header at
> all. Repeating headers and footers come from Playwright's `headerTemplate` / `footerTemplate`
> options on `page.pdf()`, which take their own HTML fragments with `.pageNumber` / `.totalPages`
> classes and require a non-zero top/bottom `margin`. See spec P1-T7.


- **TOC page numbers** need a two-pass render (render once, read landed page numbers via injected markers, re-render with numbers filled).
- **PDF bookmarks/outline** are not auto-generated from headings by `page.pdf()` — either accept their absence or post-process with `pdf-lib`.
- Internal TOC anchors (`<a href="#id">`) do survive as clickable in-document jumps with no extra config.

---

## 8. Delivery architecture

### 8.1 The evidence

AgencyAnalytics 2026 benchmarks (real agency survey):
- Client format preference: **35% 1:1 calls · 35% static reports (down from 42% in 2025) · 27% live dashboards.**
- Agency internal preference: 59% dashboards (down from 70%), 22% static reports, 18% meetings.
- Cadence: **69% report monthly, only 11% weekly**, 8% bi-weekly, 5% live-dashboard-only.
- What clients value: 84% "clear visual representation," 48% "easy access," 42% "actionable metrics." **Comprehensiveness is not in the top reasons** — which is exactly what the 41-page PDF optimizes for.

Every reporting vendor (Databox, Whatagraph, Swydo, DashThis, AgencyAnalytics) converged on the same layered stack. None treats PDF-vs-dashboard as either/or.

### 8.2 The four layers

| Layer | Artifact | Audience | Job |
|---|---|---|---|
| 1 | **Weekly email/Slack digest** | Everyone incl. CMO | 30 seconds. Headline number + delta, what changed (5 bullets), why, what we're doing (3 bullets), link out |
| 2 | **Live dashboard** | Marketing team | 10 minutes. Week-over-week, filter by engine/intent, **drill into the raw AI answer behind every flag** |
| 3 | **PDF export** from the same data | Forwarding, archive, board decks | Survives being forwarded with no login — the one thing a dashboard cannot do |
| 4 | **CSV/API** | Analyst | Escape hatch |

### 8.3 Feature priority

**Load-bearing (build first):**
- **Raw-answer drill-down.** Treated as non-negotiable by every source: *"If your tool can't preserve the evidence trail, it's hard to improve citation confidence systematically."* Scrunch ships a dedicated responses API separate from its aggregate query API, implying demand splits exactly this way.
- **Filtering by engine / intent** (Otterly's dashboard makes this core, not incidental).
- **Share links with password + expiry** (Amplitude's model — revocable, optional password, cached). A login wall is what kills dashboard forwardability.
- **CSV export.**

**Secondary:** historical timeline scrubbing (keep it to "compare to last week / last month"); threshold alerting (premature before ~4 weeks of baseline).

**Vanity — defer:** in-app commenting/annotation (a Slack thread does this for free), assigning issues to teammates inside the tool (that's rebuilding Jira), deep RBAC before you have multiple clients asking for it.

### 8.4 Slack/Teams

Vanta's documented pattern: event-driven alerts **batched on a 4-hour cadence**, plus separate periodic digests, notifications **off by default**, configured per-channel (team) vs per-user (owner). A GEO-specific practitioner guide prescribes routing **event-level changes to an operator channel and weekly roll-ups to executive channels** explicitly to prevent alert fatigue — *"Dashboards don't create outcomes, cadence does."*

Applied: real-time alert **only** for a genuinely new factual error (something comms/legal may need same-day). Everything else goes in the weekly digest. Never alert on sampling noise.

### 8.5 Email digest craft

B2B services average ~39.5% open / 2.2% CTR; SaaS ~38.1% / 1.2% — but Apple Mail Privacy Protection has inflated opens ~18pp industry-wide since 2021, so click-to-open and dashboard-link clicks are the real signal.

Zenloop's dashboard-fatigue research generalizes directly: people disengage from recurring reports **"when no action can be determined from the displayed data."** Every digest needs a "what we're doing about it" line — even if the answer is "nothing needed, holding steady."

Subject line encodes the delta, not the brand: *"Fort mentioned in 6/10 ChatGPT runs this week (+2)"* beats *"Your Weekly GEO Report."*

### 8.6 Draft digest

```
Subject: Fort mentioned in 6/10 ChatGPT runs this week (+2)

HEADLINE
Mentioned in 6 of 10 sampled runs across ChatGPT, Claude, Gemini and
Perplexity, up from 4/10. 3 of 7 flags from last week are resolved.

WHAT CHANGED
• ChatGPT: up on comparison queries (2/10 → 5/10)
• Claude: flat — still not citing Fort on "best strength tracker"
• Whoop newly cited on "[query]" where you previously appeared
• 1 flag regressed: Perplexity is quoting $200 again (was fixed wk 3)
• No new factual errors

WHY IT MOVED
[1–2 sentences, plain language]

WHAT WE'RE DOING
• Pushing the pricing correction to [third-party listing]
• Watching whether the Gemini identity fix holds

→ Full comparison + every raw AI answer: [link]   → PDF: [link]
```

Slack version: same four sections as Block Kit sections with dividers, header block = the subject line, one button ("Open dashboard").

### 8.7 Multi-stakeholder access

TapClicks' model, which maps 1:1 onto the three personas: *"The CMO's view should stop at revenue, pipeline, and channel ROI… An analyst's view should allow full drill-down… Trying to serve all three audiences with a single flat dashboard is exactly what produces the 20-metric wall nobody reads."*

| Persona | Layer | Content |
|---|---|---|
| CMO | Summary, 5–7 KPIs | Mention-rate trend, share vs top 1–2 competitors, count of open factual errors |
| Content lead | Middle | Per-query/intent breakdown, which assets correlate with citations, week-over-week movement |
| Analyst | Full drill-down | Every raw answer, every engine, CSV/API, historical timeline |

### 8.8 Presentation ritual

QBR literature asserts retention benefits but provides **no measured statistics** in any source fetched — it's practitioner consensus, not evidence. The well-evidenced signal is AgencyAnalytics' 35%-prefer-a-call finding. A weekly call isn't sustainable; a **monthly 2–3 minute async Loom** on top of the weekly digest is the reasonable middle.

---

## 9. The input side: query sets, fact sheets, calibration

### 9.1 Query set size — triangulated

| Source | Recommendation |
|---|---|
| Semrush | ~10 prompts/product as a baseline sanity check |
| Peec AI | 25 to start; 25–100 tracked daily for real monitoring |
| Parse.gl | 25–50 starter / 50–200 serious / 200–500+ enterprise. Below 25, noise exceeds signal |
| SE Ranking | 20–40; "15 per persona" |
| MaxAEO | 40–100 buyer-intent prompts; **300–900 prompt-runs per engine per period** |
| Profound pricing | 50 (Starter) / 100 (Growth) — prompt count *is* the pricing lever |

**Recommendation: 60–120 prompts** as the standing baseline, comfortably inside the 50–200 "serious tracking" band. Keep 3 runs/query. Do not add runs before adding prompts (see [§5.1](#51-the-numbers)).

### 9.2 Intent taxonomy

The existing 5 buckets (brand, category, comparison, problem-aware, adjacent) map cleanly onto every published taxonomy found — MaxAEO's 6, Parse.gl's 4, SE Ranking's 5. **The taxonomy is industry-standard, not idiosyncratic; defensible as-is.**

One gap: no explicit **risk/reputation** bucket ("is X reliable," "X lawsuit," "X layoffs") — exactly where hallucination and defamation risk concentrate. Add it as a 6th.

### 9.3 On "real AI search volume" claims

Three sourcing models coexist and vendors are inconsistent about disclosing which they use. Profound claims opt-in consumer panels ("consent twice"), reweighted, ~10 countries, weekly. Semrush claims "126 million AI search prompts analyzed" without saying whether they're observed, synthetic, or panel-derived. An independent methodology teardown calls vendor prompt-volume numbers "pseudo-accuracy… strategically massively prone to errors" — browser-extension sampling bias, large extrapolation from small samples, and a category error applying exact-match keyword logic to semantically fluid conversational prompts.

**No vendor has published a sample size, response rate, or validation study.** Do not market the product as tracking "what people actually ask AI" in the Google-Trends sense. That claim is unverifiable industry-wide and a sophisticated buyer can dismantle it in one meeting.

### 9.4 Expose the fact sheet

Currently invisible to customers. The evidence says that's backwards:

- A 2025 LLM-as-judge paper ("No Free Labels") finds judges are unreliable on questions they can't answer themselves, and the single most effective mitigation is **giving the judge a human-written reference answer** — a weak judge with a good reference beats a strong judge with a synthetic one.
- A 2026 rubric-evaluation paper ("Rulers") argues rubrics must be locked, versioned, evidence-anchored, with documented versions and calibration data, and open sharing of specs for reproducibility.

**The fact sheet is exactly the grounding reference the literature says the judge needs, and it's hidden.** Recommendation:

1. Ship it as **"Brand Fact Sheet v1.0"** — a readable structured doc (claimed features, explicitly unclaimed features/guardrails, pricing, positioning) with a changelog.
2. **Require written customer sign-off before the first run.** This converts an internal QA artifact into a contractual scope document, pre-empting the most predictable dispute ("why did you mark that wrong, we DO do that").
3. Changes go through a formal request channel, never silent edits.
4. The trust upside is asymmetric: hidden, every flag is only as credible as a black box. Exposed, the customer either agrees (flag is unimpeachable) or edits it (you've captured their correction). The only cost is review labor — which is what onboarding fees exist to cover.

*(No competitor documents a customer-facing, editable ground-truth sheet for GEO scoring. Athena's "Knowledge Base" is for a support bot's own answers, not for judging third-party outputs. Brandlight discusses "GEO governance" as strategy content, not a documented feature.)*

### 9.5 Competitor set policy

Brand-tracking practice distinguishes *realistic* (on par) from *aspirational* competitors and warns both ways: ignoring market leaders misses the expectations they set for the category; over-indexing on aspirational names produces useless, demoralizing data. Tracksuit's explicit ratio: **5 competitors, 3–4 direct/challenger + 1–2 aspirational/incumbent**, plus indirect competitors serving the same audience.

**Policy: 5–7 competitors, 3–4 direct + 1–2 aspirational, chosen collaboratively.** Client proposes; you validate against actual category co-occurrence (who else appears when the client's own category prompts run); both sign off. Cap aspirational slots so audits can't be gamed into flattery, and don't let a client omit the obvious market leader — an audit that quietly excludes the elephant is indefensible when leadership sees it. Same signed document as the fact sheet; competitor set and fact sheet are one governance artifact.

### 9.6 Query-set versioning — the methodology problem for a weekly product

The instrument-design literature has solved this:

- **Gartner MQ**: changes criteria year to year, openly states MQs "shouldn't be compared year-over-year in isolation," and compensates by publishing detailed methodology notes each cycle so clients can rationalize movement.
- **S&P Dow Jones Indices**: fixed quarterly rebalancing (5 weeks before the third Friday of Mar/Jun/Sep/Dec), mandatory advance-notice windows, and a dedicated **"Appendix B — Methodology Changes"** logging every version change with dates.
- **Brand tracking**: "bridging" — run old and new instruments in parallel for at least one wave to establish a conversion factor before cutting over.

**Policy:**

1. **Fixed rebalancing cadence, not ad hoc edits.** Quarterly review; weekly runs use a frozen set between rebalance dates. No silent edits.
2. **Two-tier query set:** a **frozen core (~75%)** that never changes within a quarter and drives the trend line, plus a **rotating discovery slice (~25%)** refreshed each cycle to catch new competitors, phrasings, and adjacent categories without touching comparability.
3. **Bridge, don't cut over.** Run old and new in parallel for one full cycle when the core must change, and publish a dated changelog.

> **Weekly is the reporting frequency, not the instrument-change frequency.** Conflating the two makes a tracker either stale or incomparable.

### 9.7 Personas and geography

Profound's pricing page gates **regions and languages** (1 each on Starter/Growth, custom on Enterprise) alongside prompt count and engine count — three pricing levers. Goodie markets segmentation "by geography, persona, model, language, and topic category." SE Ranking treats persona as the natural unit of query-set expansion.

**Sell persona and market expansions as add-ons**, each its own mini-calibration (own intent-bucket weighting, potentially own competitor emphasis), priced per-persona/per-market.

### 9.8 Calibration as a paid deliverable

GEO agency pricing precedent: a one-time paid audit ($1,500–$5,000) converting into a monthly retainer, with "prompt mapping and AI query research" folded into the retainer. **No GEO pricing guide found treats fact-sheet/query-set construction as its own priced setup fee.** That's the gap.

Package it explicitly as **"Calibration"**, priced separately, because: (1) it's the highest-judgment labor in the pipeline; (2) pricing it separately keeps the recurring run-rate below procurement thresholds; (3) it creates a natural re-calibration revenue event instead of a contract renegotiation.

---

## 10. Naming, voice, and metric branding

### 10.1 What makes a metric name stick

- **A quotable number + a proper-noun name.** NPS survived because "Net Promoter Score" is trademarked (Bain/Satmetrix/Reichheld) even though the math is trivial.
- **A free self-serve checker that spreads the term.** Domain Authority stuck because Moz gave away a free DA checker. Moz then explicitly tried to repeat it with "Brand Authority," pitched as a "first to market" metric.
- **Published, versioned methodology.** Lighthouse publishes its scoring curve; Nutri-Score's algorithm is public and peer-reviewed (which is why governments adopted it); G2 publishes scoring methodology.
- **Annual cadence + edition numbers** (Gartner MQ, Okta *Businesses at Work*, now 10 years running).
- **Cautionary tale: Klout.** An opaque 1–100 influence score, gameable and undocumented, died in 2018. *Publish the rubric or the metric gets dismissed the first time a client disputes a flag.*
- Category-design theory (Play Bigger, April Dunford): language creates category. A generic descriptor like "Share of Voice" can never be owned — which is exactly why every vendor uses it.

### 10.2 Names already taken

- **Profound owns "FactCheck"** for this exact use case — rules out FactCheck and close variants.
- "Brand Accuracy" / "Brand Accuracy Score" is used descriptively by Storyzee, Metricus, LSEO; CrawlQ has a five-dimension "BRAND Score."
- "Hallucination rate/index" is heavily used as a *model-level* ML benchmark term, conflating "models hallucinate generally" with "models get *your brand* wrong." Trakkr already labels a competitor feature "Hallucination Detection."
- None of the named competitors owns a **coined, accuracy-flavored** name. That's the remaining slot.

### 10.3 Framing: positive over negative

Loss-framed language grabs attention but is adversarial and anxiety-inducing. The market has already voted: Profound explicitly avoids "lie/hallucinate" in product copy and calls it an accuracy score; Storyzee's glossary covers the phenomenon without ever using "hallucination." There's also a legal reason — publicly implying a named AI vendor is "lying" edges toward defamation-adjacent language, whereas "how faithfully the model reproduces your brand" is neutral and defensible.

### 10.4 Candidate names — accuracy metric

| Rank | Name | Rationale | Risk |
|---|---|---|---|
| 1 | **Ground Truth Score** | Borrows an ML term-of-art that reads as rigorous to technical buyers while staying plain-English for a CMO. Creates a natural product tie-in: the client's fact sheet *is* the Ground Truth document. No branded collision found. | "Ground truth" is a common term-of-art — clear a formal TM search |
| 2 | **Brand Fidelity Score** | Built-in positive metaphor (hi-fi = faithful reproduction), CMO-legible, legally safe (measures faithfulness, not intent). Pairs with "Fidelity Flags." | Mild brand adjacency noise ("Fidelity Investments"), no direct product collision |
| 3 | **Brand Accuracy Index (BAI)** | Maximum clarity, zero explanation needed. Ownable the way DA is ownable — via capitalization, TM registration, published methodology, and an annual index. | Highest genericness risk; already used descriptively by several parties |
| 4 | **Brand Drift Score** | Uniquely strong for the Stale category (temporal decay), which no competitor names explicitly | Moderate collision with MLOps "model drift" |
| 5 | **Mention Integrity Score** | Corporate-safe, distinctive, low collision | Weakest quotability |

**Avoid:** *FactCheck* (Profound owns it) · *Truth Score / Truth-O-Meter* (accusatory + PolitiFact collision) · *Misinformation Score* (implies intent/malice, invites dispute) · *Hallucination Score* alone (overused generic ML term).

### 10.5 Candidate names — composite score

1. **AI Trust Index** — "Trust" legitimately spans both halves (are you shown, and shown correctly). No competitor uses it. Invites favorable association with Edelman's Trust Barometer as an annual waited-for format.
2. **Brand Reality Score** — quotable, bundles presence and truth into one idea.
3. **AI Standing Score** — safe, dignified, credit-standing analogy.

### 10.6 The recurring report ritual

Name it **"The Ground Truth Report"** (or Briefing), inheriting equity from the metric, with sequential edition numbers ("Ground Truth Report #14") so clients build an archive. Sets up the public aggregate as **"The Ground Truth Index"** — same brand, different altitude.

What makes a recurring branded artifact anticipated: fixed proper-noun name + consistent visual template (Gartner's quadrant, Okta's format), predictable cadence with numbered editions, proprietary data, a signature authorial voice (Mary Meeker's *Internet Trends* became inseparable from her personally), and a press moment on publication day.

### 10.7 Copy style guide for findings

Security (CVSS), clinical labs, and GOV.UK all converge on the same register: **flat, factual, third-person description, with severity conveyed by a defined tier rather than emotional adjectives or heavy visual alarm.** A lab report uses a small "H"/"L" flag, not bold red screaming text. The anti-pattern is alarmist SEO audit tools that over-flag routine issues as "Critical! 🚨" to manufacture urgency.

**Rules:**

1. **Attribute to a specific model and date**, never "AI" in general.
2. **Reserve red for the top tier only**, against a defined rubric.
3. **Neutral, non-anthropomorphizing verbs** — "states," "describes," "lists." Not "falsely claims," "lies about," "hallucinates that."
4. **Lead with the category tag** the way a lab report leads with the test name.
5. **Pair the correction with "why it matters" and a concrete next action.**
6. **For Stale findings, name it as decay, not fabrication** — "this was true once; it hasn't been corrected" is a different and more accurate claim.
7. **Avoid legally loaded words** — prefer "outdated," "unsupported by current source," "not verifiable against current documentation."
8. **Short, active sentences.** Second person for the client's action; third person for the model's output.

**Rewrites of real findings from the Fort report:**

> **Identity — Critical**
> ChatGPT (checked 2026-06-13) describes Fort as *"a platform that emphasizes personalized strength training programs."*
> Fort is a hardware product: a strength-training wearable — a lightweight wristband with automatic exercise detection and rep counting.
> **Why it matters:** Someone asking "what is Fort" is told to expect software, not a device — a category-level mismatch, the most severe class of error we track.
> **Fix:** State "wearable device / hardware" unambiguously above the fold on fort.cx and in structured data. *(Owner: Marketing · Effort: S)*

> **Pricing — High**
> Perplexity (checked 2026-06-13, 6 of 10 runs) states Fort is priced at *"$100–300."*
> Fort's pre-order price is $289; expected retail $319 + $79.99/yr membership. The $100–300 range is Fitbit's pricing.
> **Why it matters:** A prospect comparing cost before purchase anchors on a figure ~30% below actual, and the error traces to an identity confusion with Fitbit rather than to a pricing source.
> **Fix:** Publish `schema.org/Product` pricing markup on the pricing page and correct the third-party listings feeding this. *(Owner: Marketing + Eng · Effort: M)*

> **Stale — Medium**
> Claude (checked 2026-06-13) reviews Fort as a currently available product.
> Fort is pre-order only; Batch 1 ships Q3 2026.
> **Why it matters:** This is a decay error, not a fabrication — the claim will become true, and the model has no signal for the ship date.
> **Fix:** Publish an explicit availability statement with a dated ship window on the product page and in the press kit. *(Owner: Marketing · Effort: S)*

---

## 11. Evidence, reproducibility, and defensibility

> Not legal advice. Vendor policy text below came from automated fetches and should be re-verified by counsel against the live pages before any business-model decision.

### 11.1 Evidence bundle per finding

Modeled on CVE/OWASP disclosure, IFCN fact-checking principles, `schema.org/ClaimReview`, and NLP reproducibility checklists. Effectively a mini ClaimReview object with an LLM reproducibility annex:

Claim ID · engine + exact version/build string · **exact verbatim prompt in a code block** · session context (logged in/out, browsing/tools on/off, region, custom instructions) · UTC timestamp to the minute · full verbatim output · screenshot · ground truth + dated source URL · severity rationale tied to a published rubric · category tag · **reproducibility count ("observed in N of M attempts across [dates]")** · suggested cause labeled as hypothesis · retest instructions.

### 11.2 The non-reproducibility problem

This is a real credibility risk and worse than "it's non-deterministic." Thinking Machines' engineering writeup traces the root cause to batch-size variance in inference serving, not just temperature: **at temperature 0, across 1,000 samples of the same prompt they got 80 distinct completions, diverging as early as token 103.**

Shared conversation links are not a fix — OpenAI's own FAQ confirms a shared link dies if the source conversation or account is deleted. MIT Libraries' guidance to researchers concedes the same and pivots to "document and archive, don't promise reproducibility."

**Recommended report copy:**

> **Observed:** 2026-06-13 14:22 UTC · **Engine:** Perplexity (Pro Search, logged-out, US) · **Reproducibility:** observed in 4 of 5 runs across 06-11 → 06-13; the 5th run gave a different but still incorrect figure ($225).
>
> *A note on reproducibility: large language models do not reliably reproduce the same answer to the same question, even seconds apart — a documented property of how these systems are served, not a flaw in our testing. If you run this exact prompt and get a different, or even a correct, answer, that does not mean this finding is wrong. It means the model is inconsistent, which is itself part of what we measure: how often, not just whether, your brand is misrepresented.*

Standing methodology paragraph:

> We do not claim these errors are permanent or that they will reproduce on demand. AI models are updated frequently and produce different answers to identical prompts even when nothing about your brand has changed. Each finding states how many independent attempts we made, how many produced the error, the exact date and time, and the exact prompt used. Our claims are about what we observed, when — not a guarantee of what you will see if you ask right now.

This makes non-reproducibility the *expected, disclosed* behavior rather than something the client discovers and holds against you.

### 11.3 Screenshots

**Include one per finding, alongside — not instead of — verbatim text.**

- A screenshot shows UI chrome, model-selector state, and engine-surfaced citations that raw text can't prove weren't edited.
- But screenshots are *easier to fake convincingly* and *harder to verify* than plain text (no diffable string). So: corroborating artifact, not primary evidence.
- Watch file size (50 findings at hi-res easily exceeds 50–100MB) and accessibility — crop tightly, compress at fixed DPI, always pair with alt text so the receipt stays machine-searchable.
- Competitive signal: Knowatoa reportedly markets stored "answer snapshots," so the market is converging on screenshot-as-proof being expected.

### 11.4 Legal and ToS risk

**🔴 HIGH — automated querying of consumer products.** This is the risk most directly threatening the collection pipeline.

- **OpenAI Terms of Use** (consumer): language prohibiting users from *"automatically or programmatically extract[ing] data or Output,"* bypassing rate limits, and using Output to develop competing models.
- **OpenAI Business/API Service Terms**: no explicit ban on automated querying or benchmarking surfaced — the more permissive surface, consistent with expecting programmatic use through the API.
- **Perplexity ToS §5.2(i)** (consumer): explicit prohibition on *"robot, spider, crawlers, scraper, or other automatic device, process, software or queries that… mines, scrapes, extracts, or otherwise accesses the Services to monitor, extract, copy or collect information."* Separately — and this is good news — Perplexity's consumer terms require anyone publishing Output to *cite the Services* and not misrepresent the source, meaning their own terms anticipate and permit publication with attribution.
- **Perplexity API ToS**: separate document, rate-limit language, no explicit benchmarking/publishing ban surfaced.
- **Anthropic Usage Policy**: prohibits "model scraping"/"distillation," defined as using inputs and outputs to *train an AI model* without authorization. An audit that queries and reports is arguably outside the intent, but the line isn't crisp — confirm that aggregating/scoring/storing at scale doesn't functionally resemble the prohibited activity, and check the Commercial/API Terms separately.
- **Google Gemini API Additional ToS**: a "may not develop competing models" clause and an output-caution clause; **no explicit ban on benchmarking or automated querying** surfaced. Comparatively permissive.

> **Action: confirm exactly which surface the pipeline hits.** If any part of collection scripts a consumer web UI rather than calling paid APIs, that is the risk to fix before scaling. Note that silence in API terms ≠ permission, but it is a very different risk profile from an explicit ban.

**🟡 MEDIUM — defamation / trade libel.** *Walters v. OpenAI* (Georgia, summary judgment for OpenAI on three independent grounds) decided the AI vendor's liability for a hallucination about a third party — **not** the liability of someone who quotes an AI output while stating it is false. An Inforrm one-year retrospective (July 2026) specifically flags **republication risk** as the unresolved question: when a hallucinated falsehood is amplified to a wider audience by media or commercial reports, courts haven't settled who's exposed. A commercial report is structurally that amplification.

The mitigating factor: the report does not assert the false claim as true — it asserts that the model *said* it (verifiably true, with receipt) and then corrects it. Truth is a defense; the correction is arguably protected commentary about a software product's accuracy. **Harden by always framing the entry as "[Engine] output the following text, which is inaccurate" rather than repeating the claim as fact.** The evidence-bundle format already does this structurally by boxing raw output separately from the correction.

**🟡 MEDIUM — trademark.** Nominative fair use (three factors: not readily identifiable without the mark; used no more than necessary; no false suggestion of sponsorship) covers naming engines and competitors. Anthropic's trademark guidelines are restrictive on their face — no blanket third-party permission, pre-approval requirements. Practical: **plain text names only, no vendor logos or stylized wordmarks**, plus an explicit disclaimer that the report is independent and not affiliated with or endorsed by any named vendor.

**🟢 LOW-MED — the client's own exposure.** A brand receiving "AI says your price is $200" may itself bear responsibility if the figure traces to their own stale content — outdated Crunchbase listing, missing schema, conflicting directories. This is a useful framing (turns "AI is wrong" into "here's the stale source you control") and reduces liability for over-claiming a fix will work.

### 11.5 Outcome claims

FTC's core standard: claims can't exceed what's substantiated; unsubstantiated "typical result" claims are deceptive if they'd mislead a significant minority. **"We'll get you cited," "guaranteed visibility," "guaranteed ranking improvement"** are the exact unsafe pattern — the long-standing enforcement pattern against "guaranteed #1 ranking" SEO claims applies identically. No FTC action naming a GEO vendor has surfaced yet; the field is new.

**Suggested disclaimer (cover / recurring footer):**

> This report documents AI chatbot outputs we personally observed on the dates stated, using the exact prompts stated. We do not control, and cannot guarantee, what any AI product will say in response to any prompt at any other time — these systems are updated frequently and produce inconsistent answers even to identical questions (see Methodology). Corrective actions recommended here are based on our assessment of likely contributing sources; we cannot guarantee that a given fix will change what a specific AI model says, when, or for how long. We are an independent research and advisory service, not affiliated with, sponsored by, or endorsed by OpenAI, Anthropic, Google, Perplexity, or any AI product named in this report. Product names are used solely to identify which system produced the observed output.

### 11.6 Methodology page

Nielsen, Comscore, SecurityScorecard and Lighthouse all publish real methodology — SecurityScorecard published a full scoring whitepaper as a stated transparency differentiator — but they publish **scoring logic and inputs**, not the exact harvesting method that would let someone game an individual signal (Moz never published DA's ML weights).

Same split here. Publish at full transparency: what's tested, the severity rubric with objective triggers, runs per prompt, the reproducibility convention, the engine/methodology changelog, and a **corrections policy** ("if you believe a finding is stale or inaccurate, contact X; we re-verify and correct within N business days" — mirroring IFCN's visible-corrections requirement). Keep undisclosed: the exact prompt library, query cadence, and detection heuristics, so brands fix underlying data rather than teaching the test.

---

## 12. Operations: running this at 1 → 50 clients

### 12.1 The framing

The pipeline is an instrument measuring a moving target (4 engines that change weekly) using another moving target as referee (an LLM judge). Every policy below exists to answer one question defensibly, in writing, every week: **"How do we know this week's report is right, and what do we do when it isn't?"**

### 12.2 What breaks first

- **Scope creep re-enters through the back door.** "Can you also track this competitor's new line" / "re-run with the updated fact sheet mid-week" are the GEO equivalents. Price them and give them lead times from day one.
- **Over-automating the judgment clients are paying for.** Automate the predictable; keep humans on judgment. Judge QA is exactly that boundary.
- **Founder-as-quality-gatekeeper.** The classic productized-service failure: the founder becomes the sole quality gate, can't delegate with confidence, rework eats 2–5% of revenue. **This is the biggest 1→50 risk here** — whoever writes fact sheets and eyeballs output today cannot remain in that loop at 50 clients.
- Real subscription operators (DesignJoy) show the binding constraint is **ops/communication throughput**, not deliverable quality, once production is solid.

Treat fact-sheet maintenance, query curation, judge QA, and narrative writing as **four separately-priced production stations**, each with its own SOP — not one artisanal "run the audit" verb.

### 12.3 QA sampling policy

Industry practice (Braintrust): don't review every trace — run **50–100 reviewed traces/week** using four sampling strategies together: random (baseline), priority (low automated scores / high severities), stratified (coverage across query types and engines), and edge-case. Cost differential is stark: ~$5–15 to LLM-judge 10,000 outputs vs ~$800–1,800 to human-review 500. Labelbox's reliability targets: **Krippendorff's α ≥ 0.80** satisfactory; **percent agreement > 75–80%** good.

| Tier | What | Coverage |
|---|---|---|
| **0 — deterministic** | Schema validation, missing-run detection, empty/error responses, duplicate queries | 100%, every run |
| **1 — LLM judge** | Grade every answer against the fact sheet | 100% |
| **2 — human spot-check** | Random + priority + stratified sample | **15–20% of findings/client/week**, plus **100% of Critical/High**, **100% of anything that changed vs last week**, and a random 5% of "no issue found" to catch false negatives |
| **3 — calibration set** | ~50–100 hand-labeled query/answer/verdict triples | 100%, re-run on every judge-prompt change or detected engine update |

**Publish a target error rate.** Suggested commitment: *"Judge-flagged findings are human-reviewed for all Critical/High items and a stratified 15–20% sample of all others. Judge/human agreement on our calibration set is currently X% (target ≥85%, Krippendorff ≥0.80); we re-baseline monthly and disclose material drift."*

As you scale, the 15–20% shrinks in relative terms but the **calibration set and the Critical/High 100% rule stay fixed**.

### 12.4 LLM-as-judge reliability

Known biases: position bias, verbosity bias, self-preference. Some adversarial benchmarks show frontier judges failing over half of bias probes. **"The judge said so" cannot be the evidentiary standard for a Critical flag shown to a CMO.**

Checklist:

1. **Write a real rubric** — five parts: evaluation target, inputs, allowed labels, decision rules, worked examples. Most bad judges fail before the model is even called.
2. **Discrete labels, not 1–10 scores.** Include an explicit "insufficient evidence" category rather than forcing a verdict.
3. **Force chain-of-thought + cited evidence.** Structure output as `{label, explanation, cited_quote_from_fact_sheet}` so a reviewer can audit *why* in seconds.
4. **Calibrate before trusting.** Track accuracy, precision, recall, confusion matrix by severity, and Cohen's κ against the calibration set.
5. **Targeted ensembling.** Run a second judge from a *different model family* on Critical/High flags only. Full ensembling everywhere is overkill.
6. **Set expectations at the honest ceiling.** MT-Bench found strong judges reach **>80% agreement with human preference — the same level as human-human agreement.** Not "the judge is right," but "the judge agrees with a careful human about as often as two careful humans agree."

### 12.5 Engine model-version drift

No GEO vendor publicly documents how they handle this. Policy:

1. **Detect, don't assume.** Fingerprint each engine weekly against fixed canary probe queries. Material shifts in structure/length/refusal pattern → flag "possible engine update" before the report ships.
2. **Annotate, don't silently re-baseline.** Mark the week on the trend chart: *"⚠ Engine X updated between this edition and the prior one — treat trend comparison with caution."*
3. **Never retroactively adjust history.** Keep old numbers intact; start a new comparable series, clearly dated.
4. **Maintain a public "Engine & methodology changes" log.** LMSYS publishes its full rating methodology and model-availability policy; Label Studio's guidance is to version the benchmark like a release artifact recording what changed, why, and how it affects comparability.

### 12.6 SLA and data-gap disclosure

- **Turnaround:** fixed day/time weekly (e.g. Monday 09:00 client-local) with a defined grace window before it counts as a miss.
- **Partial data, disclosed not hidden:** retry with backoff (e.g. 3 attempts over 4h); if an engine is still unavailable, ship on time with that section marked **"Insufficient data this period — [Engine] unavailable during collection window."** This mirrors Nielsen's convention of flagging insufficient sample rather than publishing a number that looks complete.
- If fewer than 3 runs completed for a query, footnote the affected queries and actual run count rather than presenting them as equivalently sampled.
- **Keep a weekly per-client run log**: engines queried, runs completed/attempted, flags raised, human-review coverage %, anomalies. This is the audit trail if a finding is ever disputed.

### 12.7 Narrative automation

Automated narrative generation from structured data is mature, not experimental (Wordsmith, Quill, Power BI Smart Narrative, Databox AI insights). Copy their guardrail pattern exactly:

- **Template-constrained generation.** The LLM fills a fixed skeleton from structured, already-QA'd data. It does not invent findings or re-interpret severity.
- **Ground every sentence in a specific structured field** (a finding ID, a delta value) so any claim is traceable. Never let the summary writer see raw ungraded engine output.
- **Guard the second hallucination surface.** A narrative pass can introduce a claim the graded data doesn't support. Mitigation: a deterministic post-check — does every quantitative claim in the summary match a value in the findings table? Cheap, catches the worst failure mode.
- Human sign-off on Critical/High narrative sentences only.

**This is the first automation target** — highest hours removed for the least reliability risk. (Unlike judge grading, where the risk profile inverts.)

### 12.8 Weekly runbook and time estimates

| Step | Who | Time/client/week |
|---|---|---|
| 1. Engine canary check | Automated, shared | ~0 marginal |
| 2. Pipeline run (4 engines × 3 runs × query set) | Automated | ~0 marginal |
| 3. Fact-sheet freshness check | Human | 5–10 min routine; 30–60 min on update weeks |
| 4. Judge grading | Automated | ~0 marginal |
| 5. **Human QA sample** (100% Critical/High + 15–20% stratified) | Human | **20–40 min** |
| 6. Anomaly/drift triage | Human, exception-only | 0 normal; 20–45 min flagged weeks |
| 7. Narrative draft | LLM + spot-check | 5 min gen + 5–10 min review |
| 8. Render/PDF/delivery | Automated | ~0 marginal |
| 9. Data-gap footnotes | Templated + glance | 2–5 min |

**Steady state: ~35–65 minutes of human labor per client per week.** Query-set curation is monthly (~30–60 min/client), not weekly. At client #1 expect **2–4× higher**; you converge toward the steady-state figure around clients 5–10 once SOPs, the calibration set, and the narrative template exist.

**Automation priority:** (1) narrative generation with grounding guardrails; (2) Tier-0 deterministic pre-filtering to shrink the QA queue; (3) canary-based drift detection; (4) fact-sheet-change detection (diff the client's public pricing/product pages) to prompt-and-reduce, not replace, the human check.

### 12.9 Infrastructure principles

- **Per-client config as versioned data, not code** — fact sheet, query set, engine list, SLA params, one record per client per version, so every run is reproducible and diffable.
- **Snapshot every run immutably** — raw responses, judge verdicts, human overrides, rendered report, timestamped and never overwritten. This is what makes diffing, dispute resolution, and drift audit possible after the fact.
- **Separate the measurement plane from narrative generation** so you can re-render without re-running expensive engine queries.
- **Canary/calibration runs as first-class scheduled jobs**, on the same cadence as production.
- Orchestration: Dagster/Prefect are lower-ops than Airflow at this scale; the tool matters far less than the discipline above.

---

## 13. Benchmarks, indices, and the moat question

### 13.1 Benchmark context as a value multiplier

Every analytics benchmark product uses the same shape: **the benchmark is free bait; acting on it is the paid feature.**

- **Databox Benchmark Groups** — free in exchange for an email; fully anonymized both directions; explicitly a lead-gen and retention funnel ("keep your clients happy by using data to back up your expertise").
- **AgencyAnalytics Benchmarks** — gated behind Agency Pro, built on anonymized data from 150,000+ campaigns, positioned as "Retain more clients," bundled with forecasting and anomaly detection.
- **Klaviyo / HubSpot** — ungated, pure top-of-funnel authority content.
- **Vanta Trust Maturity Report** — same shape for compliance.
- **Contract mechanics**: the standard enabling clause is opt-in-by-default inside the MSA — *"You agree that [vendor] may obtain and aggregate… on a de-identified basis… to generate industry benchmarks"* — usable during and after the term, across unrelated customers.

### 13.2 Building a benchmark at low n

Statistical disclosure control norms:
- **n < 5**: universal suppression threshold.
- **n < 10 or 11**: the more conservative CDC/CMS default, often with complementary suppression (also hiding an adjacent cell to prevent inference by subtraction).
- Beyond suppression: **global recoding** (roll small segments up — report "DTC" rather than "DTC hardware sub-vertical") and perturbative masking.

**Rule:** no segment-level benchmark until **n ≥ 5**, prefer **n ≥ 10** before treating it as real. Report **P25/P50/P75 bands, not a mean** (mean is outlier-distorted at low n and a range communicates uncertainty honestly). Always disclose n and date range inline: *"median across 8 DTC brands audited May–July 2026."*

### 13.3 The reference brand panel — the key structural fix

**This should be the primary launch mechanism, not a nice-to-have.**

Unlike Databox/AgencyAnalytics benchmarks — which need real client behavioral data that only exists inside paying accounts — **the underlying data here (model outputs to structured prompts) is legally producible for any brand, client or not.** Run the same query taxonomy against a fixed panel of 15–30 well-known reference brands per vertical on the same weekly cadence.

- This is the one place where lacking Similarweb's or Profound's panel *doesn't matter* — everyone has equal access to the raw material.
- n=15–30 clears the suppression thresholds immediately, so benchmark context ships on day one with zero clients.
- **Caveat, and label it clearly:** reference brands are famous and well-covered; they will show systematically higher mention/citation rates than a median small/mid client. Call it a **"reference panel"** or "market context" band, never a "peer benchmark," and never silently blend it with a real client-cohort benchmark once one exists.

### 13.4 Is cross-client data a moat? No.

a16z's *"The Empty Promise of Data Moats"* argues most claimed data network effects are ordinary scale effects, and scale effects in data tend to *erode* rather than compound — acquisition costs rise, marginal value of each new data point falls, corpora go stale. Real moats come from proprietary/restricted-access sources, domains where more data compounds accuracy, and deep vertical expertise.

Applied here: **the substrate is not proprietary and not access-restricted.** Any competitor can query the same models with the same prompts today. Auditing Brand X does not get cheaper or more accurate because you audited 50 unrelated brands — each audit is a fresh independent query.

What *does* compound, and is worth building:
1. A validated query taxonomy per vertical (real IP, but copyable by inspection).
2. Methodology credibility and track record.
3. **Per-client historical trendlines** — a client with 18 months of weekly data has genuine lock-in. This is a retention moat, not a cross-client data moat.
4. Vertical GTM credibility.

**Do not pitch aggregate GEO data as a data moat internally or to investors.** Pitch it as a retention mechanism and a demand-gen mechanism.

### 13.5 The public index play

The genre works via: an ownable metric, fixed predictable cadence, semi-public methodology, and a liftable headline stat. Precedents: Cloudflare Radar Year in Review, Okta *Businesses at Work* (10 years), Edelman Trust Barometer (25+ years, disciplined published methodology, Davos-timed), Adobe Digital Price Index (monthly, own panel), SparkToro's zero-click studies (proof a small team can land one — a single simple re-citable stat gets cited for years).

**But the index space is crowded**: Profound Index (1.5bn prompts, daily), Similarweb's 2026 Generative AI Brand Visibility Index, Conductor's 2026 AEO/GEO Benchmarks (13,770 domains, 100M+ citations). A client-data-only index will not compete on scale.

**Recommendation — publish a narrow, defensible slice:** a quarterly **"AI Accuracy Index"** for 2–3 verticals, built entirely from the reference brand panel (zero client consent needed, launches immediately), with one ownable headline metric per release — **factual error rate by AI model**. None of the big three indices emphasize accuracy; they measure visibility and citation share. That's the genuine white space and it matches the existing expertise.

Publish it as a **persistent, crawlable web page** (Cloudflare Radar structure), not a static PDF — a live page is what makes it AI-citable over time, not just journalist-citable at launch.

**On the meta-irony (an AI-accuracy index is itself the kind of source AI engines cite):** partially real. Omniscient Digital's analysis of 23,000+ LLM citations found reviews/social proof dominate *branded*-query citations (57%), directories second (17%), thought leadership only 5.4% — but that's the weakest case for original research. The stronger case is unbranded/comparison queries. Growth Memo's counterweight is important: most original data *fails* to get cited because it isn't packaged as a scannable quotable stat. **Format matters more than novelty.**

### 13.6 Vertical packaging

The market has already moved: First Page Sage runs distinct "Top Healthcare GEO/AEO Agencies" and "Top B2B SaaS GEO/AEO Agencies" rankings; NoGood publishes a healthcare/pharma-specific GEO tools list. Verticalized positioning is an active buyer expectation.

**Recommendation:** package by vertical (start with 2–3 where there's existing traction), each with (a) a vertical-specific query taxonomy — healthcare has heavy "is X FDA approved / covered by insurance" patterns a generic taxonomy misses; (b) a reference brand panel per vertical; (c) vertical-specific error categories (healthcare needs a stricter compliance/misinformation flag than DTC hardware).

### 13.7 Consent

- **Opt-in-by-default inside the standard MSA**, not a separate consent screen — universal industry practice.
- **Give a visible opt-out toggle anyway.** Databox's core trust message is "no other company can see your performance"; a visible opt-out is good practice for a young company that runs on word-of-mouth.
- **Enforce suppression at the product layer** (n≥5/10), not just contractually.
- **Publish methodology on a stable URL** (Edelman model) — this is what makes a benchmark citable.
- Get a **perpetual license to use anonymized aggregate data post-termination** in writing early; losing it retroactively when clients churn quietly erodes the dataset.

---

## 14. Pricing and packaging

### 14.1 Metering

**Meter on prompts × engines, plus competitors benchmarked.** This matches category convention (Profound, Peec, Otterly, Goodie all converge here), so the unit is legible pre-signup — Stripe's usage-pricing framework sets that as a hard requirement: a customer must be able to estimate their bill from information they already have.

**Do not paywall cadence.** Three reasons:
1. It's a cost-to-you metric dressed as a value metric — refresh frequency tracks LLM spend, not willingness to pay.
2. Every competitor gives daily refresh away at the cheapest tier. Paywalling a *slower* cadence than competitors give away for less looks like a worse deal.
3. It creates the nothing-changed credibility trap: if a client paid *specifically* for weekly, a flat week reads as wasted money. If cadence is a given and the paywall is on breadth/depth, a flat week is just no news.

**Seats should be unlimited at every tier.** Every reviewed competitor offers unlimited seats, and gating seats works directly against multi-stakeholder distribution, which is a top retention mechanic.

### 14.2 Cost model (calculated, not published anywhere)

- Engine calls: 4 engines × 100 prompts × 3 runs = 1,200 calls at ~$0.008/call (≈300 in / ≈600 out tokens, blended across current frontier pricing) → **≈$10/run**.
- Judge pass: 1,200 verdicts × ~$0.006 (Sonnet-class, ~1,500 in / 300 out grading against a fact sheet) → **≈$7/run**.
- ~~≈$17–20 raw LLM cost per full 100-prompt audit.~~ **Superseded by measurement — see `audit-packaging-implementation.md` §3.0.** Measured: $0.0736/call, 6 surfaces, $5.52 per 25-query run at K=3 (≈$24/month weekly). The conclusion is unchanged and stronger: cost is not the constraint.

**Weekly is not economically risky on API cost.** It's risky on credibility (nothing-changed reports) and judge-QA labor, which don't scale down the way API cost does.

### 14.3 Tiers

| | **Starter** | **Growth** | **Agency / Enterprise** |
|---|---|---|---|
| Price | ~$349/mo ($299 annual) | ~$899/mo ($749 annual) | $2,000+/mo custom |
| Cadence | Monthly deep-dive + always-on dashboard | **Weekly digest + monthly deep-dive** | + on-demand runs |
| Prompts | 30 | 100 | 250+ |
| Engines | All 4 — **no engine paywall** (that's the differentiator vs commodity dashboards) | All 4 | + custom/regional |
| Competitors | 3 | 6 | Unlimited |
| Accuracy findings | Full catalogue — **core, never an upsell** | + lifecycle + trend | + material-change alerting |
| Seats | Unlimited | Unlimited | + multi-brand portfolio |
| Onboarding | Self-serve query-set builder | Guided calibration call | White-glove: fact sheet + query set co-built, dedicated analyst |
| Export | CSV | CSV + API | Full API, white-label |

**Calibration fee, separate:** $1,500–$5,000 one-time (agency precedent: $1,500–$7,500 for a one-off audit). Reposition the existing 41-page audit as the **paid first edition** that calibrates the fact sheet and query set, then rolls into subscription. It's already built — stop giving it away as the whole product.

**Free tier — "How wrong is AI about you?"** One-time, 10–15 prompts, 2 engines (ChatGPT + Perplexity — cheapest and most recognizable). Shows the **count** ("AI got something wrong about you in 6 of 15 checks") and one competitor comparison; gates *which* errors behind signup, routing to the manual lead queue. Freemium benchmarks: 1–5% for broad-market free tools, **5–15% for narrow high-intent tools** — this is about as high-intent as free tools get. (HubSpot's Website Grader conversion figures are widely cited narratively but were **not independently verifiable** — treat as an unverified story, not a number.)

**White-label/reseller:** wholesale per-end-client pricing (~50–60% of Growth list) rather than a flat markup. Agencies are the highest-LTV, lowest-CAC channel.

### 14.4 Retention mechanics, ranked

Churn context: **68% of agency-client departures cite lack of proactive strategic guidance, 57% poor communication, 53% inability to demonstrate value, only 37% price. 43% of churn decisions are effectively made in the first 90 days.** SEO-adjacent retainers run ~38% annual churn.

1. **Delta-first framing, every edition.** Highest-leverage fix for the nothing-changed risk; directly targets the "couldn't demonstrate value" driver.
2. **Honest correlational revenue layer.** GA4 has no dedicated AI-referral channel by default — AI traffic lands in Referral/Unassigned/Direct unless you build a custom channel-group regex. Once built, reported datasets show AI-referred visitors converting at outsized rates (one: 0.5% of traffic → 12.1% of signups; another: 15.9% ChatGPT vs 10.5% Perplexity referral conversion). Ship a GA4 setup guide plus a "how did you hear about us → AI assistant" field. **Never claim causation.**
3. **Competitive loss-framing.** A named-competitor trend showing lost ground is inherently sticky.
4. **Every finding ships with a next step.**
5. **Material-change alerting** — converts a fixed cadence into an event-driven signal.
6. **Multi-stakeholder distribution** — weekly digest to the team, monthly to the founder. Defends against single-champion churn and hedges the undecided-persona problem.
7. **Calibration lock-in, framed honestly** — "your calibrated benchmark," not vendor lock-in.
8. **Front-load engagement in months 1–3**, given 43% of churn decisions land there.

---

## 15. Sales collateral and buyer journey

### 15.1 The audit-as-wedge playbook

Shape is universal across adjacent categories: **free/cheap instant score → gated report → sales-assisted expansion.**

- **HubSpot Website Grader** — 10M+ leads since 2007, ranks #1 for its own category keyword, ~30–40% email-gate conversion *because the visitor sees a score before the ask*.
- **UpGuard Instant Security Score** — 13 risk factors, "see how hackers, partners, and customers see your organization from the outside," request-form gate.
- **SecurityScorecard / RiskRecon** — free 30-day vendor-risk access as a wedge into paid TPRM.
- **CRO agencies** universally lead with a free audit/teardown.

**What converts:** fast first signal (<10s), a real number, value before the hard gate, and a tool that lives permanently as an SEO asset.

**The spam problem:** the free-audit motion is polluted by "I noticed some SEO issues with your site" cold outreach, and buyers are trained to distrust it. Multiple agency blogs tell readers to be suspicious of these emails. The differentiator here is that each finding is **specific, falsifiable, and brand-specific** — much harder to dismiss as templated. But the *channel* still matters: inbound (SEO landing page + tool), partner/agency referral, and warm intros avoid the stigma; mass cold email inherits it.

### 15.2 Urgency stats — vetted, with source quality flagged

| Stat | Quality | Use? |
|---|---|---|
| Gartner: "search volume will drop 25% by 2026" | **Analyst prediction, not measured data.** No public methodology; the underlying report is paywalled. It's now 2026 — the prediction window has elapsed | Only as "Gartner predicted X in 2024," never as current fact |
| Conductor 2026: AI referral traffic averages **1.08%** | **Vendor-funded and the average is misleading.** 11x variance by industry (0.25%–2.80%); computed from 1,215 enterprise domains, not the full 13,770; skewed by authority domains (Mayo Clinic = 6.58% of healthcare AI citations); ignores the ~93% of AI sessions that never click through | **Don't use the headline.** Use the variance point — more honest and more useful |
| Conductor CMO survey: 56% made significant AEO investment in 2025, 94% plan to increase, ~12% of digital budget | Vendor-commissioned, ~250 enterprise respondents, self-selected, vendor sells the validated product | Usable as "even vendor-optimistic surveys show growth," disclosed |
| Exploding Topics (Semrush): **77.6%** used AI to help with shopping in 6 months; ~69% recall being influenced to buy | Vendor-funded but a real consumer survey, n=1,009 US, disclosed methodology | Best available purchase-influence stat; cite with funding disclosed |
| Google still sends **87.6%** of search referrals (July 2026) | Independent tracker, not a GEO vendor | **Use as the honesty check** |

**Honest framing:** there is currently **no clean, non-vendor-funded, large-sample stat proving AI-search visibility drives revenue at scale.** The strongest true statement available:

> *"AI referral share is still a low single-digit percentage of total traffic for most brands, but it's growing fast, wildly uneven by industry, and factual errors compound the longer they sit uncorrected. The risk isn't today's traffic share — it's the compounding cost of letting misinformation about your brand go unchallenged while the channel is still small and cheap to fix."*

### 15.3 The misrepresentation hook

Comparable "you have a problem you can't see" categories — dark-web/breach monitoring, reputation management, brand protection/anti-counterfeiting — all converge on the same lesson: **specificity works, genericity reads as fear-mongering.** Breach monitoring sells on "your credentials appeared in this specific breach," brand protection on "we found X counterfeit listings," never abstract risk. Best-practice guides in dark-web monitoring explicitly warn against fear-only pitches because they erode trust.

Transferable: the catalogue hook works **only** if each sample finding is specific, verifiable, and attributed to a named model and query. *"ChatGPT told a user your return window is 14 days; it's 30"* — not *"AI models may say inaccurate things about you."*

### 15.4 Collateral set, prioritized

| Artifact | Cost | Impact | Priority |
|---|---|---|---|
| **Public sample / redacted report** (turn one real 41-pager into a 6–8 page teaser with 3–5 real findings) | Low — repurpose | Very high; this is the "score" moment | **First** |
| **One-page methodology explainer** | Low | High — pre-empts "why trust this" and "numbers change" | **First** |
| **Live-scan-on-the-call** ("let's run your brand right now") | Low (process, not build) | Very high for close rate | **First** |
| **Interactive free scan tool** (brand in → partial score out, full report email-gated) | Medium-high | Very high long-term; permanent inbound engine | High, once funded |
| **Transparent pricing page** | Low | Medium-high — differentiator in a category where enterprise pricing is uniformly hidden | Early |
| **Comparison-vs-competitors page** | Low-med | Medium, once prospects are evaluating Profound/Athena/Otterly/Peec/Scrunch | Medium |
| **Case study format** | Low | Medium | See below |

**Case studies with no results history:** substitute outcome case studies with **correction case studies** — "here's the specific error we found, here's what the client changed, here's the before/after snapshot of the model's answer." This sidesteps the attribution problem entirely, because the proof point is directly observable. Vendor-published AEO case studies today mostly claim revenue/traffic numbers without disclosing methodology limits; a verifiable before/after model output is a *stronger* trust artifact for a new entrant.

### 15.5 First-call structure

Gap Selling layered with Challenger's "teach for differentiation":

1. **Current state, in their words** — what do they believe AI says about them today? Get the assumption stated before you correct it.
2. **Future state** — why accuracy matters to their business, in their language.
3. **Reveal the specific finding.** Frame as *"here's what we found, here's why it's common, here's what fixing it looks like."* Attribute the gap to the novelty of the category, not to their team's failure. This is the single most important delivery move — it keeps them from getting defensive.
4. **Quantify the gap** — what does this error cost? A support ticket, a lost sale, a return.
5. **Co-build the plan** — the subscription is the mechanism that keeps the gap from reopening, not a one-time fix.

**Run the scan live using their brand name.** More persuasive than any slide; creates the aha in real time rather than asking them to trust a pre-made PDF.

### 15.6 Objection handling

| Objection | Strongest answer |
|---|---|
| **"Isn't this just SEO?"** | SEO optimizes for ranking in a list of links. This optimizes for being cited *accurately* inside a generated answer where there's no list, no click, and no chance to correct the record after the fact. Sharper still: this isn't GEO-as-ranking, it's **fact-checking your brand inside a system you don't control** — closer to reputation management than keyword optimization. |
| **"The numbers change every time — why trust it?"** | **Answer with full honesty, not spin.** LLM outputs are genuinely non-deterministic — sampling, retrieval index changes, silent model updates. GPT-4's accuracy on one benchmark task moved 84% → 51% between two 2023 releases, unannounced. *"You're right to distrust a single score — that's why we don't sell you a score. We sell you a rate across repeated runs, with the volatility band shown."* This candor is itself a differentiator; most competitors are still selling false-precision rankings. |
| **"What do I actually do with this?"** | Each finding maps to a concrete correctable action (schema/FAQ update, canonical fact page, Wikidata/G2 correction, support/PR brief). **If the product stops at "here's the problem," this objection wins** — the subscription needs a what-to-do column, not just a what-we-found column. |
| **"Can't I just ask ChatGPT myself?"** | Yes — one prompt, once. You can't manually run multiple models × dozens of query variants × a recurring cadence with a consistent methodology to detect drift. A single manual check can't tell whether this week differs from last, or whether the error is being repeated to real customers versus a session fluke. |
| **"Our agency covers this."** | Most agencies don't have a GEO practice yet; where "AI visibility" is bolted onto an SEO retainer it's a slide, not a monitoring system. Position non-adversarially: this is a data feed the agency acts on, the way brand monitoring feeds PR — not an agency replacement. |
| **"How do I know your fix worked?"** | Use the **before/after model output** as proof, not revenue attribution (genuinely unsolved industry-wide, and worse here because ~93% of AI sessions never click through). "Here is the exact answer the model gave before; here is the exact answer now." |
| **"That's a lot for a report."** | It isn't a report — it's a monitoring subscription with a report as the interface. Same reframe HubSpot/UpGuard/Vanta use. If price resistance persists, land narrow (one brand, one market) rather than discounting the core offer. |

### 15.7 Land and expand

- **More entities**: sub-brands, product lines, additional competitors benchmarked, more markets/languages.
- **Services attached**: fixing findings — schema markup, canonical fact pages, PR/comms correction workflow, Wikidata/directory edits. Mirrors CRO audit → CRO retainer, and SecurityScorecard rating → remediation.
- **Agency reseller / white-label**: an active motion — GrackerAI, Ayzeo, Pierview, GeoScout all run partner/reseller programs. Sell once to the agency, fan out across its client base.

### 15.8 Where the sales case is weakest — be candid internally

1. **No non-vendor-funded stat proves AI-search visibility drives revenue at scale.** Every compelling number traces to a company selling GEO tooling.
2. **The category has an unsolved measurement-noise problem**, and independent commentators are actively calling vendors out for false precision. Honesty here is a differentiator *and* an admission competitors won't make.
3. **Attribution from "fixed a factual error" to "made more money" is not solvable today.** The honest proof is the before/after model output.
4. **AI referral traffic is still small in absolute terms** (~87.6% of referrals still Google as of July 2026). The urgency pitch must be forward-looking and risk-based, not "this is already costing you traffic."

---

## 16. Contradictions and calls

| Conflict | Call |
|---|---|
| Wave 1: *accuracy tracking is wide-open white space.* Wave 2: *Profound already shipped **FactCheck** for exactly this.* | **The category is contested, not empty — adjust the pitch.** The defensible position is no longer "we measure accuracy" but "we run accuracy as a governed remediation program": a signed ground-truth document, a published severity rubric, human QA with a stated agreement rate, a four-state closing backlog, and a drift/methodology changelog. That's a workflow and credibility claim Profound's measurement surface doesn't make. Verify FactCheck's actual depth before finalizing positioning. |
| Wave 1 competitor agent: *keep the letter grade — Am I On AI and Mangools validate it.* Wave 1 structure + visual agents: *kill the F.* | ~~Keep a graded score; kill the bare F.~~ **REVISED 2026-08-02 — kill the grade entirely.** The compromise below contradicted this doc's own §7.1 kill-list ("the hero letter grade") and reintroduced a `B−` on a second tile. A static score is the hero of a one-off audit; this product's hero is the delta and the closing backlog. See `audit-packaging-spec.md` P1-T6. Original reasoning retained:  Split into Foundation Readiness (winnable today) + Current AI Visibility (labeled "Baseline"). Moz DA, Nutri-Score and HubSpot Grader are all cautionary tales of an unexplained, unearnable, un-actionable score. Credit bureaus distinguish "thin file" from "bad score" for exactly this reason. |
| Wave 1 competitor agent: *PDF-primary is legacy; go dashboard-first.* Wave 1 delivery agent: *35% of clients still prefer static reports.* | **Both.** Dashboard is the product; PDF is the forwardable artifact generated from the same data. The PDF's sin isn't being a PDF — it's being the only thing. |
| Wave 1 competitor agent: *weekly is the credible minimum.* Delivery agent: *only 11% of agencies report weekly.* Recurring-design agent: *report one cadence coarser than you collect.* | **Collect weekly, digest weekly (thin, significance-gated), deep-dive monthly.** Weekly collection is cheap and builds the rolling window statistical honesty requires. A thin honest weekly that often says "Flat" beats a fat weekly that manufactures news. |
| Wave 1: *3 runs/query validated by Arcalea's consistency research.* Wave 2 (MaxAEO): *ICC ~0.57 means added runs buy almost nothing; breadth is what buys power.* | **Not actually in conflict — both are right about different axes.** 3 runs is the floor needed to detect inconsistency at all (Arcalea's point). Beyond 3, marginal runs are near-worthless (MaxAEO's point). **Hold runs at 3 and invest the budget in going from ~50 prompts to 60–120.** |
| Wave 2: *publish the fact sheet for trust.* Wave 2 (defensibility): *keep the prompt library undisclosed to prevent gaming.* | **Different artifacts, both right.** Publish the *fact sheet* (client-specific ground truth — the client should own and sign it) and the *rubric*. Keep the *prompt library and detection heuristics* private so brands fix underlying data rather than teaching the test. |
| Wave 2 (index play): *publish a public index as a demand engine.* Also wave 2: *Profound/Similarweb/Conductor already run indices at 100–1000× your scale.* | **Publish narrow, not broad.** Don't compete on visibility-index scale. Own **factual error rate by AI model**, quarterly, 2–3 verticals, built from the reference brand panel (no client consent needed, launches immediately), as a live crawlable page. None of the big three emphasize accuracy. |

---

## 17. Build order

### Phase 1 — restructure what already exists (biggest ROI, no new data)
1. Root-cause taxonomy — cluster 235 flags into ~10 themes with instance counts
2. Executive summary + BLUF at the top
3. Replace query IDs with verbatim query text everywhere client-facing
4. Priority actions table (adapted RICE using existing funnel-stage data)
5. Collapse Medium/Low into a table; severity-count bar; full cards only for Critical/High
6. Reframe the grade into two subscores; kill the bare F
7. Print CSS fixes (`print-color-adjust`, `break-inside`, `running()`, repeating table headers)

### Phase 2 — make it recurring (this is the actual product)
8. Flag lifecycle state machine (new/persisting/resolved/regressed) + immutable prior-run storage
9. Wilson intervals, rolling averages, two-gate significance thresholds
10. "What changed this week" section + the accountability line
11. Brand × engine heatmap; paired week-vs-week leaderboard bars
12. Evidence bundle per finding (verbatim prompt, engine version, timestamp, session context, N-of-M reproducibility, screenshot)

### Phase 3 — layer the delivery
13. Dashboard week-over-week view + raw-answer drill-down
14. Weekly email digest
15. Share links with password/expiry; PDF export from dashboard data
16. Fix-pack export (structured per-finding brief, copy-pasteable)

### Phase 4 — operationalize
17. Calibration set (50–100 hand-labeled triples) + published judge/human agreement rate
18. QA sampling policy (100% Critical/High + 15–20% stratified)
19. Canary probes + engine-drift detection and annotation
20. Template-constrained narrative generation with a deterministic fact-check pass
21. Per-client versioned config; quarterly query-set rebalance with bridging + changelog

### Phase 5 — commercialize
22. Free "how wrong is AI about you" scan → manual lead queue
23. Signed Fact Sheet v1.0 + competitor-set governance document as a paid Calibration deliverable
24. Tiering; white-label config behind one object
25. Reference brand panel (15–30 brands × 2–3 verticals) → benchmark bands in the report
26. Quarterly public AI Accuracy Index as a live crawlable page

### Immediate — before scaling anything
27. **Confirm which surface the collection pipeline hits (official APIs vs scripted consumer UIs).** See [§11.4](#114-legal-and-tos-risk).

---

## 18. Open questions

1. **Which API surface does the pipeline actually use today?** Determines whether §11.4's HIGH-severity item is a real exposure or already resolved.
2. **How deep is Profound's FactCheck?** Positioning in §16 depends on whether it's a measurement surface or a full lifecycle.
3. **Which vertical to lead with?** Vertical packaging (§13.6) and the reference panel (§13.3) both need this decision before build.
4. **Does the current judge output cite fact-sheet lines?** §12.4 rule 3 requires `{label, explanation, cited_quote}` — if the judge already does this, calibration is much cheaper.
5. **Is there prior-run storage today?** The entire Phase 2 lifecycle depends on immutable snapshots; if runs are overwritten, that's the first thing to fix.
6. **Buyer persona.** Still undecided (founders / in-house marketing / agencies / enterprise). Tiering in §14.3 hedges, but the free-scan funnel and sales collateral in §15 diverge meaningfully by persona.

---

## 19. Source index

Grouped by section. Fetched July 2026; vendor pricing and ToS pages change without notice.

**Competitors & pricing** — [Profound pricing](https://www.tryprofound.com/pricing) · [Profound FactCheck](https://www.tryprofound.com/blog/introducing-factcheck-measure-ai-accuracy-for-your-brand-at-scale) · [Profound Prompt Volumes](https://www.tryprofound.com/blog/introducing-prompt-volumes) · [Profound Index launch](https://finance.yahoo.com/technology/ai/articles/profound-launches-profound-index-zero-170300107.html) · [Peec AI](https://peec.ai/) · [AthenaHQ plans](https://athenahq.ai/plans) · [Scrunch FAQs](https://scrunch.com/faqs/) · [Otterly](https://otterly.ai/) · [Evertune pricing](https://www.evertune.ai/pricing) · [Evertune AI Brand Index](https://www.evertune.ai/products/ai-brand-index) · [Goodie pricing](https://higoodie.com/pricing/) · [Rankscale pricing](https://rankscale.ai/pricing) · [Gauge](https://www.withgauge.com/) · [Trakkr](https://trakkr.ai/) · [Trakkr Scrunch review](https://trakkr.ai/reviews/scrunch-review) · [Semrush AI Visibility Toolkit](https://www.semrush.com/kb/1493-ai-visibility-toolkit) · [Semrush 2026 AI Visibility Index](https://www.semrush.com/news/463141-semrush-releases-expanded-2026-ai-visibility-index-analyzing-126-million-ai-search-prompts/) · [Ahrefs Brand Radar review](https://www.tryanalyze.ai/blog/ahrefs-brand-radar-review) · [Similarweb 2026 GenAI Brand Visibility Index](https://www.similarweb.com/corp/reports/the-2026-generative-ai-brand-visibility-index/) · [Conductor AEO/GEO Benchmarks](https://www.conductor.com/academy/aeo-geo-benchmarks-report/) · [Ayzeo GEO platforms compared](https://ayzeo.com/comparisons/geo-platforms-compared) · [Rankability tool list](https://www.rankability.com/blog/best-ai-search-visibility-tracking-tools/)

**Methodology critique & sample size** — [Arcalea: why AI visibility reports are wrong](https://arcalea.com/blog/why-your-ai-visibility-reports-are-probably-wrong-how-to-fix-them) · [MaxAEO sample size](https://maxaeo.ai/blog/ai-visibility-sample-size/) · [MaxAEO how many prompts](https://maxaeo.ai/blog/how-many-prompts-to-test-ai-visibility/) · [Parse.gl prompt sets](https://parse.gl/blog/how-to-build-ai-visibility-prompt-set) · [SE Ranking prompt selection](https://seranking.com/blog/how-to-choose-prompts-to-track/) · [Semrush prompt research](https://www.semrush.com/blog/prompt-research-for-ai-seo/) · [Jaeckert-O'Daniel: prompt search volume critique](https://www.jaeckert-odaniel.com/en/prompt-search-volume-real-data-or-all-guessed/) · [Canonry: AI visibility tools are lying](https://canonry.ai/blog/ai-visibility-tools-are-lying) · [aicarma: AI search volatility](https://aicarma.com/blog/ai-search-volatility/)

**Statistics** — [Binomial proportion CI (Wilson)](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval) · [VWO: minimum detectable effect](https://help.vwo.com/hc/en-us/articles/36876638315929-Understanding-Minimum-Detectable-Effect-MDE) · [Spotify Confidence: effect sizes](https://confidence.spotify.com/docs/experiments/design/effect-sizes) · [NN/g confidence intervals](https://www.nngroup.com/articles/confidence-interval/) · [Nielsen ratings reliability](https://tapweb.nielsen.com/help/main/reference/ratingsreliability.htm) · [Quali-Fi always-on brand tracking](https://quali-fi.com/learn/always-on-brand-tracking) · [GSC weekly/monthly aggregation](https://ppc.land/google-search-console-adds-weekly-and-monthly-aggregation-views/) · [Vanderbilt: small-sample suppression](https://www.vanderbilt.edu/data/2026/04/03/small-sample-size-suppression-statistical-disclosure-control/) · [CMS cell-size suppression](https://resdac.org/articles/cms-cell-size-suppression-policy)

**Issue lifecycle & findings** — [Qualys vulnerability status levels](https://docs.qualys.com/en/vm/latest/scans/vulnerability_status.htm) · [Snyk remediation reports](https://docs.snyk.io/scan-fix-and-prevent/prevent/analytics/reports-tab/remediation-reports) · [Snyk severity levels](https://docs.snyk.io/manage-risk/prioritize-issues-for-fixing/severity-levels) · [Semrush Position Changes](https://ko.semrush.com/kb/495-organic-research-position-changes-report) · [Screaming Frog crawl comparison](https://www.screamingfrog.co.uk/seo-spider/tutorials/how-to-compare-crawls/) · [Semrush thematic reports](https://www.semrush.com/kb/959-site-audit-thematic-reports) · [Lighthouse opportunities](https://web.dev/articles/discover-performance-opportunities-with-lighthouse) · [Accessible.org: managing audit issues](https://accessible.org/manage-accessibility-issues-audit-report/)

**Clustering & taxonomy** — [Igor: crash dedup by root cause](https://dl.acm.org/doi/10.1145/3460120.3485364) · [Microsoft AutoARTS](https://www.microsoft.com/en-us/research/publication/autoarts-taxonomy-insights-and-tools-for-root-cause-labelling-of-incidents-in-microsoft-azure/) · [Google SRE postmortem analysis](https://sre.google/workbook/postmortem-analysis/) · [Quirkos: codes vs themes](https://www.quirkos.com/blog/post/whats-the-difference-between-codes-and-themes-in-qualitative-analysis/) · [SentiSum ticket categories](https://www.sentisum.com/customer-service-analytics/help-desk-ticket-categories-best-practices)

**Report structure** — [Slideworks: Pyramid Principle](https://slideworks.io/resources/the-pyramid-principle-mckinsey-toolbox-with-examples) · [Slideworks: executive summary](https://slideworks.io/resources/how-to-write-executive-summary) · [Management Consulted: SCQA](https://managementconsulted.com/scqa-framework/) · [BLUF](https://en.wikipedia.org/wiki/BLUF_(communication)) · [Intercom: RICE](https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers/) · [Eval Academy: in defence of long reports](https://www.evalacademy.com/articles/in-defence-of-long-reports)

**Scoring credibility** — [SEL: the case against Domain Authority](https://searchengineland.com/moz-domain-authority-case-against-431732) · [SecurityScorecard methodology](https://securityscorecard.com/resources/whitepapers/scoring-methodology/) · [Lighthouse scoring](https://developer.chrome.com/docs/lighthouse/performance/performance-scoring) · [Nutri-Score validation](https://www.frontiersin.org/journals/nutrition/articles/10.3389/fnut.2022.974003/full) · [HubSpot Grader score-drop thread](https://community.hubspot.com/t5/CMS-Development/Website-Grader-score-decrease-dramaticly/m-p/329777) · [Internal Audit 360: to rate or not to rate](https://internalaudit360.com/to-rate-or-not-to-rate-that-is-the-question/) · [Why Klout failed](https://www.sunsethq.com/blog/why-did-klout-fail)

**Visual design** — [Semrush Intergalactic donut guidance](https://developer.semrush.com/intergalactic/data-display/donut-chart/donut-chart) · [Domo bump charts](https://www.domo.com/learn/charts/bump-charts) · [Domo stacked area](https://www.domo.com/learn/charts/stacked-area-chart) · [Carbon accessibility/color](https://carbondesignsystem.com/guidelines/accessibility/color/) · [Baymard UX benchmarking](https://baymard.com/product/ux-benchmarking) · [Tufte data-ink](https://jtr13.github.io/cc19/tuftes-principles-of-data-ink.html) · [Storytelling with Data summary](https://www.shortform.com/summary/storytelling-with-data-summary-cole-nussbaumer-knaflic) · [Ahrefs Health Score](https://help.ahrefs.com/en/articles/1424673-what-is-health-score-and-how-is-it-calculated-in-ahrefs-site-audit)

**Print/PDF** — [MDN print-color-adjust](https://developer.mozilla.org/en-US/docs/Web/CSS/print-color-adjust) · [PrintCSS running headers/footers](https://printcss.net/articles/running-headers-and-footers) · [Generate PDF with TOC using Chrome](https://medium.com/@pofider/generate-pdf-with-toc-using-chrome-c3b44f924ff9) · [W3C paged media](https://www.w3.org/Style/2013/paged-media-tasks)

**Delivery** — [AgencyAnalytics 2026 benchmarks](https://agencyanalytics.com/agency-benchmarks-2026) · [Databox weekly digest](https://databox.com/new-in-databox-get-insights-on-your-top-kpis-with-the-metric-detail-page) · [Vanta notification settings](https://help.vanta.com/en/articles/11345394-notifications-and-notification-settings) · [Profound Slack integration](https://www.tryprofound.com/integrations/slack) · [Rank Masters: scheduled reports & Slack alerts](https://www.therankmasters.com/insights/ai-visibility/best-ai-visibility-tools-scheduled-email-reports-slack-alerts) · [Amplitude external sharing](https://amplitude.com/docs/analytics/share-external) · [Knock: designing Slack notifications](https://knock.app/blog/the-guide-to-designing-slack-notifications) · [Zenloop: dashboard fatigue](https://www.zenloop.com/en/blog/dashboard-fatigue/) · [HubSpot email benchmarks 2026](https://blog.hubspot.com/sales/average-email-open-rate-benchmark) · [TapClicks: dashboards executives read](https://www.tapclicks.com/blog/how-to-build-a-marketing-dashboard-executives-will-actually-read) · [Clearscope content brief](https://www.clearscope.io/blog/how-to-create-seo-content-brief) · [GEO tools: the evidence trail](https://geol.ai/briefing/geo-tools-comparison-review-which-platforms-best-measure-ai-visibility-and-citation-confidence)

**Judge reliability & ops** — [MT-Bench / Chatbot Arena](https://arxiv.org/abs/2306.05685) · [Arize: LLM-as-judge in production](https://arize.com/blog/how-to-build-llm-as-a-judge-evaluators-that-hold-up-in-production/) · [Braintrust: human-in-the-loop evals](https://www.braintrust.dev/articles/human-in-the-loop-evals-for-llm-apps) · [Braintrust: judge vs human](https://www.braintrust.dev/articles/llm-as-a-judge-vs-human-in-the-loop-evals) · [Labelbox: inside the data factory](https://labelbox.com/blog/inside-the-data-factory-how-labelbox-produces-the-highest-quality-data-at-scale/) · [Adaline: judge bias](https://www.adaline.ai/blog/llm-as-a-judge-reliability-bias) · [Comet: LLM juries](https://www.comet.com/site/blog/llm-juries-for-evaluation/) · [No Free Labels (arXiv 2503.05061)](https://arxiv.org/html/2503.05061v1) · [Rulers: rubric-based evaluation (arXiv 2601.08654)](https://arxiv.org/html/2601.08654) · [LMSYS Arena policy](https://www.lmsys.org/blog/2024-03-01-policy/) · [Label Studio: keeping benchmarks useful](https://labelstud.io/blog/the-five-stages-to-keeping-benchmarks-useful-as-models-evolve/) · [Wayfront: scaling productized services](https://wayfront.com/blog/scaling-productized-services-framework) · [Assembly: productized services](https://assembly.com/blog/productized-services) · [Jonathan Stark: FPS](https://jonathanstark.com/fps)

**Instrument versioning** — [Gartner Magic Quadrant FAQ (PDF)](https://www.gartner.com/imagesrv/pdf/magic_quad_faq.pdf) · [S&P DJI policies & practices (PDF)](https://www.spglobal.com/spdji/en/documents/policies-practices.pdf) · [TRC: modernizing brand trackers without losing trend data](https://trcmarketresearch.com/blog/how-to-modernize-your-brand-tracking-study-without-losing-trend-data/) · [Tracksuit competitor audit guide](https://www.gotracksuit.com/us/blog/posts/competitor-audit-guide)

**Evidence & legal** — [Thinking Machines: defeating nondeterminism](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) · [MIT Libraries: saving AI content](https://libguides.mit.edu/c.php?g=1353444&p=9994954) · [OpenAI ChatGPT shared links FAQ](https://help.openai.com/en/articles/7925741-chatgpt-shared-links-faq) · [OpenAI Terms of Use](https://openai.com/policies/row-terms-of-use/) · [OpenAI Service Terms](https://openai.com/policies/service-terms/) · [Anthropic Usage Policy](https://www.anthropic.com/legal/aup) · [Anthropic trademark guidelines](https://www.anthropic.com/legal/trademark-guidelines) · [Gemini API additional terms](https://ai.google.dev/gemini-api/terms) · [Perplexity ToS](https://www.perplexity.ai/hub/legal/terms-of-service) · [Perplexity API ToS](https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service) · [Walters v. OpenAI — Gibson Dunn](https://www.gibsondunn.com/gibson-dunn-wins-significant-victory-for-client-openai-defending-against-defamation-claim-based-on-hallucinated-generative-ai-output/) · [Eric Goldman on Walters](https://blog.ericgoldman.org/archives/2025/05/chatgpt-defeats-defamation-lawsuit-over-hallucination-walters-v-openai.htm) · [Inforrm: Walters one year on](https://inforrm.org/2026/07/24/ai-one-year-on-what-walters-v-openai-tells-us-about-ai-hallucinations-and-defamation-liability-nataly-tedone/) · [INTA: fair use of trademarks](https://www.inta.org/fact-sheets/fair-use-of-trademarks-intended-for-a-non-legal-audience/) · [FTC endorsement guides](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking) · [IFCN code of principles](https://ifcncodeofprinciples.poynter.org/the-commitments) · [schema.org/ClaimReview](https://schema.org/ClaimReview) · [OWASP vulnerability disclosure](https://cheatsheetseries.owasp.org/cheatsheets/Vulnerability_Disclosure_Cheat_Sheet.html)

**Benchmarks, indices, moats** — [Databox Benchmark Groups](https://databox.com/databox-benchmark-groups) · [AgencyAnalytics Benchmarks](https://agencyanalytics.com/features/benchmarks) · [a16z: the empty promise of data moats](https://a16z.com/the-empty-promise-of-data-moats/) · [Cloudflare Radar year in review](https://blog.cloudflare.com/radar-2025-year-in-review/) · [Okta Businesses at Work](https://www.okta.com/newsroom/articles/businesses-at-work-2025/) · [Edelman Trust Barometer methodology](https://www.edelman.com/trust/our-methodology) · [Omniscient: content types cited in LLMs](https://beomniscient.com/blog/content-types-cited-in-llms/) · [Growth Memo: why most original data never gets cited](https://www.growth-memo.com/p/why-most-original-data-never-gets) · [Law Insider: anonymized & aggregated data clauses](https://www.lawinsider.com/clause/anonymized-and-aggregated-data)

**Pricing & retention** — [Stripe: usage-based pricing](https://stripe.com/resources/more/usage-based-pricing-strategy-for-saas) · [Daydream: freemium conversion benchmarks](https://www.withdaydream.com/library/insights/freemium-conversion-rate) · [AgencyDashboard: month-six churn](https://agencydashboard.io/blog/agency-client-retention-month-six) · [Abmatic: track AI referral traffic in GA4](https://abmatic.ai/blog/track-ai-referral-traffic-ga4) · [Soar: AI visibility agency pricing 2026](https://www.soar.sh/blog/ai-visibility-agency-pricing-2026) · [DemandLocal: how to price GEO services](https://www.demandlocal.com/blog/how-to-price-geo-services/)

**Sales** — [UpGuard instant security score](https://www.upguard.com/instant-security-score) · [HubSpot Website Grader relaunch](https://blog.hubspot.com/marketing/website-grader-relaunch) · [Gartner: search volume prediction](https://www.gartner.com/en/newsroom/press-releases/2024-02-19-gartner-predicts-search-engine-volume-will-drop-25-percent-by-2026-due-to-ai-chatbots-and-other-virtual-agents) · [Conductor State of AEO/GEO](https://www.conductor.com/academy/state-of-aeo-geo-report/) · [Ekamoira: critique of Conductor benchmarks](https://www.ekamoira.com/blog/conductor-aeo-geo-benchmarks-2026) · [SEL: 77% use AI to shop](https://searchengineland.com/new-data-77-use-ai-to-shop-nearly-1-in-3-wont-let-it-spend-475614) · [Gong: gap selling](https://www.gong.io/blog/gap-selling) · [SEOptimer: selling GEO services](https://www.seoptimer.com/blog/sell-geo-services/) · [SEL: SEO vs GEO is wrong](https://searchengineland.com/guide/seo-vs-geo-is-wrong) · [SEL: fix your brand's AI hallucinations](https://searchengineland.com/guide/fix-your-brands-ai-hallucinations)

**Naming & voice** — [Medallia NPS guide](https://www.medallia.com/net-promoter-score/) · [Moz Brand Authority launch](https://www.businesswire.com/news/home/20230807278945/en/Moz-Launches-Brand-Authority-First-to-Market-Metric-for-Measuring-Brand-Strength-and-Salience) · [Play Bigger / category design](https://www.categorydesignadvisors.com/play-bigger/) · [April Dunford positioning framework](https://www.kathirvel.com/guide-april-dunford-positioning-framework/) · [G2 research methodology](https://research.g2.com/methodology/research-agenda) · [GOV.UK style guide](https://www.gov.uk/guidance/style-guide/a-to-z-of-gov-uk-style) · [Google developer docs: voice and tone](https://developers.google.com/style/tone) · [CVSS](https://en.wikipedia.org/wiki/Common_Vulnerability_Scoring_System) · [Storyzee: brand accuracy glossary](https://www.storyzee.com/resources/glossary/brand-accuracy/)

---

*Compiled 2026-07-31 from 12 research agents across two waves. Wave 1: competitive teardown, recurring-report design, narrative structure, visual standards, delivery formats, pricing. Wave 2: onboarding/query-set design, naming/voice, productized operations, benchmarks/moat, evidence/defensibility, sales collateral. Findings flagged verified vs. inferred where the underlying agent distinguished them.*
