# Spec — Repackage the Audit Deliverable as a Recurring Product

> **Status:** not started. **Audience:** a Claude Code session (one task per session, in order).
> **Research basis:** `docs/audit-packaging-research.md` (12 agents, ~500 sources). This file is the
> normative build spec; the research file is the *why* and is not required reading to execute a task.
> **Standing rules:** `.claude/skills/audit-packaging/SKILL.md` — load it before any task here.
>
> **Target render path:** the **web report** — `web/components/report-view.tsx` (601 lines),
> `web/components/charts.tsx`, `web/app/audits/[id]/page.tsx`, fed by `ReportPayload` in
> `web/lib/api.ts` ← `src/api/reports.py`. This is the path that produced the 41-page Fort PDF
> (footer: `localhost:3000/audits/<uuid>`). **The `teaser/` audit renderer
> (`teaser/src/render/audit/*`, `teaser/src/select/buildAudit.ts`) is OUT OF SCOPE** for this spec —
> do not port changes there, do not "keep them in sync." If a task tempts you into `teaser/`, stop
> and flag it.
>
> **Guiding principle:** the measurement pipeline is good and largely stays put. Everything here is
> about *identity, hierarchy, comparison, and honesty* in the layer between the judge and the reader.
> Reuse existing helpers (`src/pipeline/metrics.py`, `src/pipeline/trend.py`, `judge_metrics.py`) —
> extract and extend rather than reimplement.
>
> **Every task ends green:** `mypy src/` → `ruff check src/` → `pytest tests/` for Python;
> `npm run typecheck` (or `tsc --noEmit`) + any web tests for TypeScript. One regression test per task.

---

## The one-paragraph problem

The audit is a blob because **every finding is anonymous**. `AccuracyFlag`
(`src/storage/models.py:175`) is `{type, claim, reality, severity}` — no id, no query, no engine, no
timestamp, no occurrence count. `FlagRow` (`web/lib/api.ts`) mirrors it. An anonymous finding cannot
be deduplicated, prioritized, tracked across runs, evidenced, or closed. That single gap is why 235
flags render as 235 identical cards over 30 pages, why there is no week-over-week story, and why
there are no recommendations. **P0-T1 is the keystone; almost everything else is blocked on it.**

---

## Dependency graph

```
P0-T0 (API surface check — do first, no code)
P0-T4 (Sable tokens + fonts) ──► blocks EVERY render task (P1-T2, T5, T6, P2-T6, P3-T5)
P0-T1 (flag identity + provenance)  ──┬── P0-T2 (4-level severity)
                                      ├── P0-T3 (root-cause taxonomy)
                                      └── P2-T1 (prior-run resolution)
   P0-T2 + P0-T3 ──► P1-T1 (theme dedup) ──► P1-T2 (severity bar / collapse)
                                          └► P1-T4 (priority) ──► P1-T5 (exec summary)
   P1-T3 (verbatim queries) — independent, do early, high visible win
   P1-T6 (grade split) — independent
   P1-T7 (print pipeline) — independent, do last in Phase 1
   P1-T8 (lazy/virtualization audit) — independent; pairs with P1-T7, same RenderModeContext
   P2-T1 ──► P2-T2 (lifecycle) ──► P2-T5 (what changed)
   P2-T3 (Wilson CIs) ──► P2-T4 (significance gating) ──► P2-T5
   P0-T1 ──► P2-T7 (evidence bundle) ──► P3-T1 (drill-down)
   Phase 3 needs Phase 2 complete. Phases 4 and 5 are independent of each other.
```

---

# Phase 0 — Foundation

## P0-T0 — ✅ DONE 2026-08-02 — Confirm which API surface the pipeline queries
**Problem:** Consumer-facing terms at OpenAI (*"automatically or programmatically extract data or
Output"*) and Perplexity (ToS §5.2(i), *"robot, spider, crawlers, scraper… or queries that… mines,
scrapes, extracts"*) contain language prohibiting automated querying of the **consumer web
products**. The **API** terms of all four vendors are materially more permissive and silent on
benchmarking. Scaling a weekly commercial product on a scripted consumer UI is the one research
finding that could threaten the business model rather than just the deliverable.
**Change:** Read `src/engines/*.py` and confirm every engine calls an official paid API with a key
from `src/config/settings.py` — including `dataforseo_ai_overviews.py` / `dataforseo_ai_mode.py` /
`local_pack.py` (third-party SERP vendors: verify *their* terms permit resale of derived data, and
that they aren't scraping a consumer surface on your behalf). Write findings into
`docs/gtm-legal-readiness.md` as a dated section: per engine → surface, auth method, terms URL,
verdict. **No code changes.** If any engine drives a consumer UI, stop and escalate to Josh/Abhi
before continuing this spec.
**Test:** none (documentation task). Acceptance = the table exists and every engine has a verdict.

> **✅ Completed 2026-08-02 — findings in `docs/gtm-legal-readiness.md`, section "Data-source &
> API-surface audit".** Verdict: **cleared.** All ten surfaces call official, key-authenticated APIs
> via official SDKs or documented endpoints; no headless-browser automation and no scripted consumer
> UI anywhere in `src/engines/`. Secrets hygiene confirmed (`os.getenv` appears nowhere outside
> `src/config/settings.py`). Two follow-ups moved out of this task and into the doc: **(a) Perplexity
> ToS §1.1(b) requires citing the Services when Output is published** — needs a line in the report
> methodology template that survives white-labelling; **(b) DataForSEO and Serper are scraping
> intermediaries** whose risk is contractual/continuity, not code, and DataForSEO's indemnity
> currently runs against us. Also corrected: the "Anthropic barred external paying customers on a
> shared key" flag was a misread of a consumer-OAuth restriction — Commercial Terms §A.1 expressly
> permit powering products for your own customers.

## P0-T1 — [KEYSTONE] Give findings identity and provenance
**Problem:** `AccuracyFlag` = `{type, claim, reality, severity}`. It is not addressable. Two identical
Fitbit-confusion flags from different engines are indistinguishable from one flag counted twice;
nothing can be tracked, cited, or closed.

> **Revised 2026-08-02.** This task previously specified a single content hash
> (`sha256(client + type + claim_stem)`). **That design breaks the lifecycle** and must not be built:
> "Fort is a relatively new **player**" and "…new **entrant**" hash to unrelated values, so next
> week's report shows a fixed finding plus a new one when nothing changed. Any pure hash is brittle
> by construction. Use the two-layer design below. Rationale and sources:
> `audit-packaging-implementation.md` §1.

**Change — two layers, not one:**

| Layer | What | Purpose |
|---|---|---|
| `row_hash` | `sha256(normalize(claim))[:16]`, recomputed every run | **Idempotency only** — "did I already ingest this exact row this run?" |
| `cluster_id` | UUID, **persisted**, assigned by matching against previously-seen findings | The stable, client-facing finding ID. This is what survives across weeks. |

1. Extend `AccuracyFlag` (`src/storage/models.py`) with: `cluster_id: str`, `row_hash: str`,
   `query_id: str`, `engine_name: str`, `intent: str`, `run_index: int`, `observed_at: str` (ISO-8601 UTC).
2. New `findings_registry` table: `cluster_id uuid PK`, `representative text`, `normalized_text text`,
   `theme text`, `first_seen_run uuid`, `occurrence_count int`. Index
   `USING GIN (normalized_text gin_trgm_ops)` (`CREATE EXTENSION IF NOT EXISTS pg_trgm`).
3. Assignment, in `src/pipeline/finding_id.py`:
   - normalize (lowercase, collapse whitespace, strip punctuation) → exact-match dict lookup first (O(1));
   - else block via `pg_trgm` (`normalized_text % $1`, `similarity_threshold = 0.25`, `LIMIT 20`);
   - re-score candidates with **`rapidfuzz.fuzz.token_set_ratio`** (already a dependency, C++-backed,
     deterministic, robust to reordering and subset phrasing);
   - best match ≥ threshold → attach existing `cluster_id`; else mint a new UUID.
4. `DUP_THRESHOLD = 85.0` is a **starting point, not a constant to ship**. Build
   `tests/fixtures/labeled_pairs.csv` (~150–300 hand-labeled `claim_a, claim_b, is_duplicate` rows),
   sweep 70→95, pick the knee. Record the chosen value and its precision/recall in the docstring.
5. **Do not use SimHash, MinHash/LSH, embeddings or pgvector.** SimHash/MinHash are document-scale
   techniques that lose their guarantees on 10–40 word sentences; embeddings break the determinism
   requirement (BLAS/hardware float variance). Semantic-only near-matches are caught by the *theme*
   classifier (P0-T3), not by this layer — do not make similarity solve semantic equivalence.
6. `AnswerJudgment` already carries `query_id`/`engine_name`/`intent`/`run_index` (`models.py:185`) —
   populate the provenance fields from the parent judgment in `src/pipeline/judge.py`.
7. Update `flag_to_dict` / `flag_from_dict` with defensive defaults so legacy rows parse.
8. Storage: columns in `data/schema_*.sql`, writes in `src/storage/db.py`. Create-only.
9. Surface through `src/api/reports.py` → `FlagRow` in `web/lib/api.ts`.

> ⚠ **Judge invariant.** The intended implementation derives every new field in Python from data the
> judge already returns. **Do not touch the judge prompt, tool schema, or message layout.** If you
> find yourself editing them, re-read this task. If it genuinely requires it: bump `_PROMPT_LAYOUT`,
> keep `tests/test_judge.py` parity green, and tell the user stored runs need re-prejudging.

**Test:** `tests/test_finding_id.py` — same claim from two engines → same `cluster_id`; a paraphrase
above threshold → same `cluster_id`; a materially different claim → new one; punctuation/casing/
whitespace variants collapse; **assignment is deterministic under input reordering** (sort by
`row_hash` then index before iterating). Plus a `tests/test_judge.py` case asserting flags inherit the
parent judgment's provenance, and a `flag_to_dict`/`from_dict` round-trip including a legacy dict.

## P0-T2 — [Depends: P0-T1] Move to a 4-level severity scale
**Problem:** `Severity` is `HIGH|MED|LOW` (`models.py:158`). Research (Snyk's proven 4 tiers; 5+ blur
at a glance) needs a Critical tier so the top of the report can say "3 Critical" rather than burying
a pricing error among 40 mediums. Today HIGH covers both "AI thinks you're a pickleball app" and
"minor feature overstatement."
**Change:** Add `CRITICAL = "critical"` to `Severity`. Define objective triggers in code comments
**and** in the client-facing methodology copy — proposed rubric:
- **Critical** — category/identity error, or a factual claim that materially changes a purchase
  decision (wrong price, wrong availability, confusion with a different company).
- **High** — invented or materially misstated capability, or competitor attributes applied to the
  client.
- **Medium** — omission or understatement of a real capability; stale-but-becoming-true claims.
- **Low** — imprecise phrasing, unverifiable-but-not-contradicted, cosmetic.

Existing rows: map `high → critical` **only** where `type ∈ {identity, wrong_pricing}`, else
`high → high`. Do this as a pure classifier function so it is testable and re-runnable, not a
one-shot SQL update. `SeverityBadge` (`web/components/badges.tsx`) needs a 4th variant.

> **Colour, corrected 2026-08-02.** An earlier draft said "reserve the red family for Critical only."
> **There is no red in Sable, and no gold either** — the palette is entirely cool and has no alert
> hue, and "no colours outside the palette" is an explicit brand Don't. Severity is a **monochrome
> navy ramp, darkest = most severe**: Critical `--sev-critical` (`#0E2340`) · High `--sev-high`
> (`#12325C`) · Medium `--sev-medium` (`#697585`) · Low `--sev-low` (`#B2B7BC`), all read from the
> tokens created in **P0-T4**. This mirrors the mark's own logic — the plumes step tone with height so
> the eye lands on the tallest, darkest form. **Icon + label on every chip is therefore load-bearing,
> not belt-and-braces:** with a single-hue ramp, colour cannot carry the distinction alone.

**Test:** classifier unit tests over the mapping matrix; a `badges.tsx` render test that every
severity renders a distinct icon+label pair, that every fill comes from a `--sev-*` token (no raw
hex), and that no component references a red or gold value.

## P0-T3 — [Depends: P0-T1] Add the root-cause theme taxonomy
**Problem:** `AccuracyFlagType` (`models.py:131`) has 9 members that describe *what kind of fact* was
wrong. The report needs a second axis: *what underlying cause* produced it, which is what gets fixed.
"Confused with Fitbit," "confused with a pickleball app," and "not a recognized brand" are all
`identity` but one root cause: the models cannot disambiguate the entity.
**Change:** New module `src/pipeline/themes.py` defining a level-1 theme enum and a
`(AccuracyFlagType, claim_text) → Theme` classifier. Level-1 themes:
`identity_disambiguation`, `category_confusion`, `lifecycle_status`, `pricing_offer`,
`feature_invented`, `feature_omitted`, `competitor_mischaracterization`, `company_facts`,
`availability_geography`, `source_citation_quality`, `risk_reputation`.
Note that `feature_invented` and `feature_omitted` **split** the existing
`missing_or_invented_feature` type — the fix for each is opposite (remove a claim vs. publish a
missing one), which is exactly why they must be different themes. Classification is deterministic
(type + keyword/pattern rules) — **not an LLM call**; it must be reproducible and free.
**Test:** `tests/test_themes.py` with ≥3 real claim strings per theme lifted verbatim from the Fort
run (`docs/fort-labeling-sheet.md` has them). Assert full coverage: every `AccuracyFlagType` value
maps to at least one theme, and no flag can produce `None`.

---

## P0-T4 — [Blocks every render task] Sable design tokens and fonts
**Problem:** The brand exists only in `docs/audit-packaging-implementation.md` §4.9 and a mockup.
There is no token file in this repo and no brand fonts in `web/package.json`, so any agent building
report UI has nothing to import and will invent near-miss colours.

**Change:**
1. `web/styles/sable.css` (or a `@theme` block) defining the locked palette as CSS custom properties:
   `--navy #0E2340` (ink) · `--blue #12325C` (links, active) · `--sky #7FA6D9` · `--harbour #697585`
   (body) · `--mist #B2B7BC` (rules) · `--paper #F2F1EC` (ground) · `--white #FFFFFF`, plus
   `--rule rgba(14,35,64,.12)` / `--rule-soft rgba(14,35,64,.07)`.
2. **Encode the Sky constraint in the token layer, not in reviewers' heads.** `--sky` is legal on navy
   only, never on paper. Expose it as `--on-navy-accent` and only reference it inside a
   `.on-navy` scope, so misuse is a missing-variable error rather than a design review.
3. Severity ramp as named tokens: `--sev-critical: var(--navy)` · `--sev-high: var(--blue)` ·
   `--sev-medium: var(--harbour)` · `--sev-low: var(--mist)`.
4. Fonts via `next/font/google`, self-hosted at build (never a CDN `<link>` — it breaks static
   export): **Cormorant Garamond** 300/400 + 400 italic (display only) and **Libre Franklin**
   400/500/600 (text and UI). Expose as `--font-display` / `--font-text`.
5. A single `brandConfig` object — name, wordmark, mark, accent — that the cover, masthead, footer and
   chart highlight all read from. Sable is its default tenant; the agency white-label replaces the
   whole object (`licensing-implementation.md` §4.1). Build the indirection now; it is free today and
   a rewrite later.

**Test:** a render test asserting no raw hex literal appears in report components (all colour comes
from tokens), and that `--sky` is unreachable outside `.on-navy`.


# Phase 1 — Restructure the deliverable

## P1-T1 — [Depends: P0-T1,T3] Collapse findings into themed groups
**Problem:** `report.accuracy_flags.map(...)` (`report-view.tsx:461`) renders one card per flag —
235 cards, ~30 pages, no hierarchy.

**Change:** In `src/api/reports.py`, group by `(theme, cluster_id)` and emit `finding_groups:
FindingGroup[]` alongside the raw list (**keep `accuracy_flags`** — CSV/JSON export and the appendix
need it). Each group carries: `theme`, `title`, `severity` (max of members), `instance_count`,
`engines[]`, `intents[]`, `occurrence: {observed, total}`, `representative_claims[]` (2–3 verbatim),
`reality`, `member_cluster_ids[]`.

**Clustering within a run: Union-Find over the similarity graph, then registry assignment.**
Do **not** use HDBSCAN or `scipy.fcluster` — both recompute from the whole dataset and return
arbitrary integer labels, so adding item #236 can reshuffle which integer means which real finding.
That instability is exactly what would make the weekly diff lie. Union-Find with path compression and
a deterministic tie-break (lower index becomes root) is single-linkage clustering computed
incrementally, and it composes with the persisted registry without relabelling anything.

> **Determinism requires sorting the input** by `(row_hash, original_index)` before iterating.
> Union-Find on an unsorted list can produce different components near the threshold.

**Representative and title:** pick the **medoid** (min total distance to other members), ties broken
by shortest → lexicographically first. Generate the title from a **template keyed off the classifying
rule**, not from the text.

**Unit rule (see Global acceptance):** `instance_count` counts individual observations;
**every client-facing count on page 1 counts themes.** Do not mix the two in one view.

**Test:** fixture with the real Fort flag set → ≤15 groups, every input flag in exactly one group,
`instance_count` sums to input length, and the Fitbit / pickleball / "not a recognized brand" flags
all land in `identity_disambiguation`. Plus a determinism test: shuffle the input, assert identical
group membership and identical `cluster_id`s.

## P1-T2 — [Depends: P1-T1, P0-T2] Severity summary bar; collapse Medium/Low
**Problem:** All findings look visually identical, so the reader has no triage signal and stops
reading. Critical and Low render the same card.
**Change:** In `report-view.tsx`, replace the flag `<ul>` with, in order: (a) a **count-summary bar**
— "3 Critical · 12 High · 40 Medium · 180 Low" — rendered *before* any individual finding; (b) full
cards for Critical and High groups only; (c) Medium and Low in a compact `<Table>` (title, theme,
severity chip, instances, first-seen). Order Critical → High → Medium → Low always; never
chronological, never alphabetical.
**Test:** render test — with 200 mixed findings, the DOM contains the summary bar before the first
card, card count equals Critical+High group count, and every Medium/Low group appears as a table row.

## P1-T3 — [Independent, do early] Show verbatim query text, never query IDs
**Problem:** The losing-queries table renders `l.query_id` (`report-view.tsx:584`) — `cat-01`,
`cmp-05`, `pa-03`. The most actionable data in the report is unreadable. Every credible tool shows
the real thing (Lighthouse shows the resource, axe the selector, Semrush the URL).
**Change:** Thread the prompt text through. `QueryResult` already has `prompt`
(`src/storage/models.py:38`) — carry it into `LosingRow` in `src/api/reports.py` and `web/lib/api.ts`,
render the quoted query with the engine and an `IntentBadge`. Keep `query_id` in the payload as a
join key but **never render it**. Grep the whole web tree for other `query_id` renders and fix them
too.
**Test:** a render test asserting no string matching `/^(cat|cmp|pa|brand|adj)-\d+$/` appears in the
rendered output for a fixture whose rows all have prompt text; and a payload test that `prompt` is
non-empty for every losing row.

## P1-T4 — [Depends: P1-T1] Priority scoring and the actions table
**Problem:** The report ends at diagnosis. There are no recommendations anywhere — the single
largest gap versus what buyers say they want (68% of agency churn cites lack of proactive guidance).
`by_bucket` funnel-stage data is computed and displayed but drives no ranking.
**Change:** New `src/pipeline/priority.py`:
`priority = (funnel_weight × reach × magnitude × confidence) / effort`, where `funnel_weight` is 3.0
for bottom-funnel intents (comparison, brand) and 1.0 for awareness/adjacent — **this is the first
real use of the intent data**; `reach` is `occurrence.observed / occurrence.total` × engine breadth;
`magnitude` is derived from severity; `confidence` is 1.0 for a direct fact-sheet contradiction and
0.6 for a borderline judge call; `effort` is mapped from **fix channel** — S = owned site/schema,
M = third-party listing, L = training-data misconception. Add `fix_channel` and `owner`
(Marketing / PR / Eng / Legal) to `FindingGroup`, derived per theme via a static lookup table.
Render a "This week's priority actions" section — 3–7 rows max — above the theme cards.
**Test:** `tests/test_priority.py` — a bottom-funnel pricing error outranks an awareness-stage
founder-bio error with identical reach and severity; the ordering is stable and deterministic for a
fixed input.

## P1-T5 — [Depends: P1-T4] Executive summary / BLUF block
**Problem:** Page 1 is five metric tiles. There is no page for a CMO.
**Change:** New section at the very top of `ReportView`, above Scorecard: one bold sentence
(standing + direction + the single most important action), then a short SCQA block. Generated
deterministically from structured fields in this release — **no LLM in this task** (narrative
generation is P4-T4, and it must not land before the grounding guard exists). Template:
> **{Client} appears in {X of Y} sampled answers across {N} engines, {direction vs last cycle}.
> {K} findings are open, {C} of them Critical. The highest-leverage fix this cycle is {top action}.**

**Test:** snapshot test over three fixtures (no prior run / improved / regressed) asserting the
sentence is well-formed, contains no placeholder tokens, and degrades gracefully when there is no
prior run.

## P1-T6 — [Independent] Remove the grade entirely; replace the scorecard row
**Problem:** `gradeColor` (`report-view.tsx:98`) puts a large red **F** at the top of the report for
a pre-launch startup. The grade is structurally unearnable and therefore unactionable — the Moz DA /
Klout / Nutri-Score / HubSpot Grader failure mode.

> **Revised 2026-08-02.** This task previously said *"split the grade into Foundation Readiness +
> Current AI Visibility."* That compromise smuggled the letter grade straight back in as a `B−` on
> a different tile, and it does not survive the recurring model: a static score is the hero of a
> **one-off** audit, whereas this product's hero is the delta and the closing backlog — both already
> on page 1. A grade over our own rubric is also opaque and unmovable; nobody can act on a `B−`.
> **The report now carries no letter grade and no composite score.**

**Change:** Delete `gradeColor` and the `visibility_grade` tile. Replace the scorecard row with four
tiles that are each **counted or measured, never invented**:

| Tile | Value | Sub | Delta chip |
|---|---|---|---|
| AI visibility | `8 of 24` | sampled answers, all six surfaces | `Up from 5 of 24` |
| Share of model | `19%` | named competitors | significance-gated |
| Open findings | `10` | themes · N critical · N instances | `3 fewer` |
| **Oldest still open** | `4 cycles` | the finding, quoted, + engine | `Open since edition N` |

The fourth tile replaces the grade and does its job better: SLA-style aging is what creates pressure
to act, and it is a count rather than an opinion. It depends on `first_seen` from P2-T2, so ship it
with a `—` placeholder until the lifecycle lands.

**Foundation readiness survives as a checklist, not a letter** — fact sheet ✓ / schema ✗ / PR
footprint partial — rendered later in the report from `src/audit/rubric.py` + `synthesize.py`, where
it is directly actionable. Do **not** roll those signals into a score.

Keep `visibility_grade` in the payload for back-compat; simply stop rendering it.
**Test:** render test asserting no `/^[A-F][+-]?$/` string appears anywhere in the report output for
any fixture, and that `gradeColor` has no call sites.

## P1-T7 — [Independent, last in phase] Print pipeline for headless Chromium
**Problem:** The PDF is produced by a human pressing `window.print()`. Chromium strips backgrounds by
default, cards break across pages, and table headers don't repeat.

> **Revised 2026-08-02.** This task previously specified running headers via `position: running()` +
> `@page` margin boxes. **That does not work.** Chrome 131 shipped `@page` margin boxes with
> `counter(page)`, but `position: running()` and `string-set()` were explicitly out of scope and are
> **not implemented in Chromium** (`string-set()` is an open unresolved issue). Only Paged.js, Prince
> and WeasyPrint implement them. Dynamic, section-aware running headers are impossible in headless
> Chromium — use Playwright's `headerTemplate`/`footerTemplate`.

**Change:**
1. Print stylesheet: `print-color-adjust: exact` (+ `-webkit-`) · `break-inside: avoid` on cards,
   chart containers and table rows · `break-before: page` on section dividers ·
   `thead { display: table-header-group }` · `orphans/widows: 3` · `[class*="overflow-"] { overflow: visible !important }`
   (shadcn `Card` clips otherwise).
2. Header/footer via `page.pdf({ displayHeaderFooter: true, headerTemplate, footerTemplate })`.
   Templates render in an **isolated iframe** — no external stylesheet, no webfonts by relative path,
   images must be base64, and **default font-size is effectively 0 so set it inline**. Recognized
   classes: `date`, `title`, `url`, `pageNumber`, `totalPages`.
3. **Pick exactly one margin source.** Either `@page { margin }` or Playwright's `margin` option,
   never both — mixing them is an open Playwright bug with unpredictable results. Recommended:
   `@page { margin: 0 }` + margins in `page.pdf()`, with `margin.top/bottom` reserving space for the
   templates or the header is clipped.
4. Headless Chrome **silently refuses to fetch `url()` resources inside `@page` CSS** — a logo in a
   margin box will simply not appear. Base64 data-URIs work.
5. `break-inside: avoid` fails on flex/grid containers — put it on a plain `display:block` wrapper
   *around* the flex content, not on the flex element.

**Test:** Playwright test printing a fixture to PDF asserting page count is in an expected band, and
a DOM-level pagination test under `emulateMedia({media:'print'})` asserting each card's top and
bottom fall in the same page-height multiple (`Math.floor(top/pageH) === Math.floor(bottom/pageH)`) —
catches the failure earlier than parsing the PDF.

## P1-T8 — [Independent] Lazy-loading and virtualization audit for print
**Problem:** **Print never scrolls the viewport, so `IntersectionObserver` never fires.** Anything
below the fold that depends on it silently drops out of the PDF while the live page looks perfect:
`loading="lazy"` images render blank · `next/dynamic(..., {ssr:false})` sections vanish · a
virtualized/windowed table renders only its visible slice, so a 200-row appendix becomes 20 rows.
This is invisible until a client asks where their data went.

**Change:** Introduce one `RenderModeContext` (`'screen' | 'print'`) set from a `?mode=print` query
param that the PDF worker passes. One flag drives every print fork:
- `ResponsiveContainer` → fixed pixel dimensions matching the `@page` content box
  (`ResponsiveContainer` does not resize for print — it sizes via `ResizeObserver`, which print
  doesn't trigger);
- `isAnimationActive={false}` on every chart;
- lazy sections eager, `ssr:false` dynamics forced in;
- virtualized tables fully rendered.

Then gate capture on three signals, not `networkidle` alone (which only means HTTP quiesced while
client-rendered SVG finishes on later frames): `document.fonts.ready`, animations off, and an
app-emitted `document.body.dataset.reportReady` flag from a per-chart `useLayoutEffect` counter.

**Note:** Recharts is client-only permanently — it still ships legacy class components and throws in
a Server Component. Plan `'use client'` boundaries as permanent, not a workaround.

**Test:** a Playwright test that prints a fixture containing a below-the-fold lazy image and a
200-row table, then asserts via PDF text extraction that the last row is present.


# Phase 2 — Make it recurring

## P2-T1 — [Depends: P0-T1] Resolve the prior comparable run
**Problem:** Nothing links a run to its predecessor. `src/pipeline/trend.py` has `compare_runs()`
but the caller must supply both runs, and its docstring says validity depends on the query set being
held constant — *"that's the caller's job."* Nobody is doing that job.
**Change:** Add `previous_run_id` and `query_set_version` resolution to `src/api/reports.py`: given a
run, find the most recent prior run for the same client **with the same `query_set_version`**. If the
version differs, return `None` and set a payload flag `comparison_blocked_reason:
"query_set_changed"` so the UI can say so honestly rather than silently comparing incomparable
instruments. Storage is create-only, so history already exists — this is a query, not a schema
change.
**Test:** fixtures with (a) two same-version runs → resolves; (b) a version change between them →
returns None with the reason; (c) a first-ever run → returns None with reason `"no_prior_run"`.

## P2-T2 — [Depends: P2-T1] Finding lifecycle state machine
**Problem:** Every edition would restate the same findings from scratch. There is no way to say what
got fixed — the question that determines renewal.

**Change:** New `src/pipeline/lifecycle.py` assigning `new` / `persisting` / `resolved` / `regressed`,
with `first_seen`, `cycles_open`, `consecutive_absences` on `FindingGroup`.

**Two guardrails, both normative — this is the highest-risk correctness bug in the product.**
Telling a client something is fixed when an engine timed out is the worst failure available.

- **A — run coverage gate.** A run counts as evidence only if
  `status == 'COMPLETE' AND coverage_ratio >= 0.95 AND query_set_version_id == current`.
  Failing runs are stored immutably but **skipped entirely** by the state machine — they never
  trigger `resolved` and never break an absence streak. This is the answer to "not found vs not
  measured."
- **B — confirmation count.** `resolved` only after **N=2 consecutive comparable-run absences**
  (per-org configurable). A single missed week stays `persisting`.

Together these make the cutoff **state-based, not time-based**: a finding absent 3 weeks then
returning is `regressed` only if it actually reached confirmed `resolved`; otherwise it is
continuation (`persisting`). `new` is assigned once, on the run where the `cluster_id` was first
minted, and is never reassigned. `regressed` outranks a same-severity `new` in P1-T4 ordering.

Vendor precedent (Tenable, Qualys) marks Fixed after **one** absent scan — do not copy it. That works
for deterministic scanners, not an LLM-judged pipeline. The confirmation rule is borrowed from
monitoring flapping-detection instead.

**Merges/splits** when clustering changes: never rewrite a `cluster_id`. Append to a
`finding_identities` ledger — `MERGED_INTO` (canonicalize via recursive CTE for historical queries) or
`SPLIT_FROM` (pre-split history stays with the old id; new ids start fresh, annotated).

**Test:** `tests/test_lifecycle.py` — table-driven over presence sequences: `[T]`→new ·
`[T,F,T]`→new,persisting,persisting (guardrail) · `[T,F,F,T]`→new,persisting,resolved,regressed ·
a 4-cycle regression requiring a 3-cycle look-back. Hypothesis property tests: exactly one status per
(finding, run); first fact always `new`; `resolved` only after ≥N falses; `regressed` only
immediately after `resolved`; `cycles_open` resets to 1 exactly on `regressed`. Assert a
`PARTIAL`/`FAILED` run never produces a `resolved`.

## P2-T3 — [Independent within phase] Wilson intervals and sampled-rate copy
**Problem:** `pct()` renders bare percentages from tiny samples. At 3 runs × 6 surfaces on a
42-query set, per-engine weekly n is small enough that a 50% rate has a Wilson 95% CI of roughly
25–75%. The report presents that as "50%".

**Change:**
1. New `src/pipeline/stats.py`. **Hand-roll it — add no new dependency.**
   `statistics.NormalDist().inv_cdf()` is stdlib; every formula needed is a dozen lines of closed-form
   arithmetic, which means the module can be fully typed and exhaustively property-tested.
   **Do not add statsmodels** (heavyweight, pulls pandas+scipy+patsy, no official type stubs).
   If scipy is already a hard dependency, `scipy.stats.binomtest(...).proportion_ci(method="wilson")`
   is acceptable for the base CI only — Newcombe, ICC/DEFF and MDE must still be hand-written.
2. **Wilson score interval with continuity correction.** Never Wald (unreliable near 0/100% at small
   n). Edge cases are normative: `n == 0` returns `(0.0, 1.0)` — full uncertainty, which signals the
   report layer to say *"insufficient data"*, **not "0%"**. `successes == 0` and `successes == n` must
   return non-degenerate intervals inside [0,1].
3. **Design-effect correction — plug `n_eff`, never raw n, into every interval.**
   `DEFF = 1 + (m − 1)·ICC`, `n_eff = n / DEFF`, where m is runs-per-query. Compute ICC(1) from your
   own run-level data via one-way random-effects ANOVA (hand-rolled; do not add pingouin). Published
   LLM-eval work reports ICC 0.48–0.86 (mean 0.68), so this is a large correction, and it is a strict
   widening — it can never make an interval falsely narrow.
4. Add `n` (the real denominator) to every rate in the payload. Render as **"7 of 12 runs"** with the
   percentage secondary. Read the denominator from the payload — `RUNS_PER_QUERY` defaults to 5 but
   stored runs vary.

**Test:** golden values hardcoded from a reference implementation (so tests carry no runtime dep);
Hypothesis properties — bounds in [0,1] and ordered, symmetry (`wilson(n−x,n)` mirrors `wilson(x,n)`),
width shrinks as n grows at fixed rate; a `@pytest.mark.slow` Monte-Carlo coverage simulation
asserting empirical coverage lands in 0.93–0.98 for nominal 95%.

## P2-T4 — [Depends: P2-T3] Two-gate significance and rolling averages
**Problem:** Without gating, most week-over-week movement is noise reported as news — the fastest way
to destroy credibility in a weekly product. `trend.py:is_real_move()` uses a single noise-floor
threshold and isn't wired into the report.

**Change:**
1. **Compare via the CI of the *difference*, not CI overlap.** Non-overlapping CIs is a conservative
   but invalid test (effectively ~√2 too wide). Implement **Newcombe's hybrid score interval** for
   `p1 − p2` and check whether it excludes zero. This replaces `is_real_move`'s single threshold and
   self-adjusts to each cell's actual n.
2. **Two gates, both must pass:** statistical (Newcombe CI excludes 0) **and** practical (magnitude
   ≥ a business floor).
3. **Replace the fixed 15pp threshold with a computed MDE:**
   `MDE = (z_{α/2} + z_β)·√(2·p̄(1−p̄)/n_eff)` at 80% power. Compute per cell so a well-sampled engine
   gets a more sensitive test than a thin one.
4. **Multiple comparisons: Benjamini–Hochberg FDR, not Bonferroni.** ~20+ simultaneous tests per
   report (6 surfaces × buckets); for an exploratory weekly scan where under-flagging real movement is
   worse than a self-correcting false positive, controlling false *discovery* rate is correct.
5. Compare **3–4 week rolling averages**, not raw consecutive points.
6. Everything else renders **"Flat" — and Flat is a claim, not a blank**:
   *"Held steady at 8 of 12 runs on ChatGPT for the 3rd straight week."*

**Do not implement** McNemar's test (per-run verdicts are themselves noisy aggregates; the ICC
correction already captures the correlation), change-point detection (CUSUM/BOCPD need far more data
than a weekly series has), or a from-scratch Laney p′-chart (reuse DEFF to inflate control limits if
a p-chart is wanted at all).

**Test:** table-driven over `(before, after, n)` asserting the label. Explicitly assert a 12%→50%
swing at n=12 does **not** earn an "Up" label but the same swing at n=240 does.

## P2-T5 — [Depends: P2-T2, P2-T4] "What changed" section and the accountability line
**Problem:** No delta anywhere. A recurring report with no comparison is a status update.
**Change:** New section, placed immediately after the exec summary and before Scorecard. Contains:
(a) the **accountability line** — *"3 of 7 findings from last cycle are resolved, 1 regressed, 4
still open. 19 resolved since we started."*; (b) significance-gated delta chips per engine; (c) top
3 movers up and down. When `comparison_blocked_reason` is set (P2-T1), render the honest explanation
instead of a fake comparison.
**Test:** render tests for all four states — improved, regressed, flat, no-prior-run — asserting the
accountability line arithmetic matches the lifecycle counts exactly.

## P2-T6 — [Depends: P2-T5] Chart overhaul
**Problem:** `ShareDonut` (`charts.tsx`) compares six brands by arc angle — a known perceptual weak
point; Semrush's own design system caps donuts at 5 segments and says never use them to compare value
sets. Nothing shows per-engine variation, though engine divergence is the most decision-relevant
split in the data.
**Change:** In `web/components/charts.tsx`:
- **Delete `ShareDonut`**; replace with a 100% stacked horizontal bar.
- **Add `EngineHeatmap`** — brand × engine, single-hue sequential ramp, **numbers inside every cell**
  (color to scan, digits to verify, and color-alone fails accessibility), fixed engine column order,
  client row pinned and bordered, one-line "how to read this" caption. Highest-value single addition.
- **Add `FunnelEngineHeatmap`** — client-only rows, intent × engine. Do **not** build a 3D
  brand×intent×engine grid; ship two 2D grids.
- **Pair `LeaderboardChart`** with prior-cycle values (paired bars, not replacement).
- **Add `BumpChart`** for competitive rank over cycles — inverted rank axis, ≤5 lines, direct labels,
  no legend. Hand-rolled SVG; recharts is already the heaviest dependency, do not add another.
- **Convert `SourcesChart`** to a Pareto (descending bars + cumulative % line) — answers "are we
  dependent on 2 sources or 20," which the current chart cannot.
- Add delta pills + sparklines to `MetricCard` (`report-view.tsx:63`); in a recurring report the
  **delta is the second-largest element on the tile**, after the value.
**Test:** render tests per chart with an empty dataset, a single-row dataset, and a full one (the
existing charts have no such coverage — add it while you are in there). Assert `ShareDonut` is gone
from the module exports.

## P2-T7 — [Depends: P0-T1] Evidence bundle per finding
**Problem:** A client will re-run a prompt, get a different answer, and doubt the whole report. LLM
outputs are non-deterministically served — at temperature 0, 1,000 samples of one prompt produced 80
distinct completions in published research. The report currently offers no verbatim prompt, no
timestamp, no session context, and no honest reproducibility framing.
**Change:** Extend `FindingGroup` with an `evidence` object: verbatim prompt, engine + pinned model
id (`src/engines/model_pins.py` already has these — use it), session/surface context (parametric vs
search — the `--surface` distinction), UTC timestamp, verbatim model excerpt, ground truth + dated
fact-sheet source, and `occurrence` as "observed in N of M runs across [dates]." Render it in an
expandable block on Critical/High cards. Include the standing non-reproducibility disclosure — exact
copy is in the skill file, **use it verbatim, do not paraphrase**.
**Test:** payload test that every Critical/High group has a non-empty verbatim prompt, a resolvable
model id, and a timestamp; render test that the disclosure string appears exactly once per report.

---

# Phase 3 — Layer the delivery

## P3-T1 — [Depends: P2-T7] Raw-answer drill-down
**Problem:** The full model answer behind a finding is only reachable by downloading `answers.md`
(`report-view.tsx:245`). Research is unambiguous that this is load-bearing: *"if your tool can't
preserve the evidence trail, it's hard to improve citation confidence systematically."*
**Change:** New endpoint `GET /audits/{id}/answers/{query_id}/{engine}/{run_index}` in
`src/api/app.py`; expandable inline panel on each finding card showing the full answer with the
flagged claim highlighted. Answers are already stored — this is retrieval and presentation only.
**Test:** API test for the endpoint including a 404 path; render test that expanding a card fetches
once and caches.

## P3-T2 — [Depends: P3-T1] Filter by engine and intent
**Change:** Client-side filter controls on the findings and losing-queries sections. No new payload.
**Test:** render test that filtering to one engine reduces both sections consistently and that the
counts in the severity summary bar update with the filter.

## P3-T3 — [Depends: P2-T5] Weekly digest generation
**Problem:** The deliverable requires opening a page. Client format preference is 35% calls / 35%
static / 27% dashboards, and clients cite "clear visual representation" (84%) far above
comprehensiveness — which is what the 41-page PDF optimizes for.
**Change:** New `src/api/digest.py` producing a plain-text + HTML digest from the same payload:
subject line encodes the delta (*"Fort mentioned in 6/10 ChatGPT runs this week (+2)"* — not "Your
Weekly GEO Report"), then HEADLINE / WHAT CHANGED (≤5 bullets) / WHY IT MOVED / WHAT WE'RE DOING
(≤3 bullets) / two links. **Every digest must have a "what we're doing" line even when the answer is
"nothing needed, holding steady"** — recurring reports lose readers precisely when no action can be
derived from them. Delivery transport is out of scope; generate and expose it.
**Test:** golden-file tests for improved / flat / regressed / no-prior-run; assert the subject line
contains a number and a delta in all four.

## P3-T4 — [Depends: P3-T3] Shareable links
**Change:** Signed, expiring, optionally password-protected read-only report URLs. A login wall is
what kills forwardability, and forwardability is the one thing a PDF has over a dashboard.
Revocable. Follow the existing `GEO_API_KEY` auth conventions in `src/api/app.py`; secrets only via
`src/config/settings.py`.
**Test:** API tests for valid, expired, revoked, and wrong-password paths.

## P3-T5 — [Depends: P1-T7, P3-T4] Server-side PDF export
**Problem:** The PDF is currently produced by a human pressing `window.print()`
(`report-view.tsx:255`) — not reproducible, not schedulable.
**Change:** Server-side render of the same route via headless Chromium. Chromium is already a
dependency (`teaser/src/render/audit/pdf.ts` uses Playwright — reuse the launch/fallback pattern
there, but **do not** reuse the teaser template). Two-pass render if TOC page numbers are wanted;
note `page.pdf()` does not generate PDF bookmarks from headings — post-process with `pdf-lib` or
accept their absence.
**Test:** an integration test that the endpoint returns a PDF of expected page-count band for a
fixture, and that it degrades to print-ready HTML when Chromium is unavailable (existing convention).

## P3-T6 — [Depends: P1-T4] Fix-pack export
**Change:** Per-finding structured brief — problem, evidence, correct fact, fix channel, owner,
effort, verification step — exportable as markdown, copy-pasteable into whatever tracker the client
uses. **Do not** build Jira/Linear integrations or in-app task assignment; that is rebuilding a
tracker for ~5% of the benefit.
**Test:** golden-file test of the brief for one Critical finding.

---

# Phase 4 — Operations

## P4-T1 — Calibration set and published agreement rate
**Problem:** "The judge said so" cannot be the evidentiary standard for a Critical finding shown to a
CMO. Adversarial benchmarks show frontier judges failing over half of bias probes.

**Change:** Extend `src/pipeline/calibration.py` / `grade_calibration.py` / `scripts/run_calibration.py`
to a findings-level gold set.

1. **Size the gold set by the rare class, not the total.** At a ~6% Critical/High base rate, 50 traces
   gives ~3 minority examples (useless). For ~20 stable minority examples you need roughly
   `20 / base_rate` total. Stratify deliberately across "judge said Critical/High", "judge said
   no-flag", and boundary cases — random sampling under-represents exactly what breaks judges.
2. **Report Gwet's AC1 as the headline metric, not Cohen's kappa.** Kappa penalizes agreement in
   proportion to class imbalance; with rare Criticals it reads as mediocre at near-perfect real
   agreement (a documented case: 97.5% raw agreement → kappa 0.747, AC1 0.972). Report AC1 **alongside**
   raw agreement, kappa, and the full confusion matrix — never one number alone. Use `irrCAC`.
3. **The production gate is per-class recall on Critical/High, not aggregate accuracy.** A judge that
   answers "no flag" to everything scores 95%+ against a 5%-prevalence set with zero recall on the
   class that matters. Gate at ≥0.90 recall for both tiers.
4. **Blind independent labelling before reconciliation.** Record both labels and route disagreements
   to a documented tie-break — for a client-facing product, escalate to Critical when in doubt.
5. Record every override durably with the `prompt_fingerprint` at judge time, so "the judge feels off
   lately" becomes a queryable regression.
6. Publish the agreement rate in the report's methodology section.

> ⚠ Calibration keeps using the held-constant API judge with `isolated_cache()` — never
> subscription/prejudge verdicts, never the shared Supabase cache. Existing hard invariant.

**Test:** severity-stratified confusion matrix; a gate test that an all-negative judge **fails** the
Critical/High recall floor despite high aggregate accuracy.

## P4-T2 — [Depends: P4-T1] QA sampling queue
**Change:** A review queue implementing the sampling policy: **100% of Critical/High**, 100% of
anything whose lifecycle status changed, a stratified 15–20% of everything else, and a random 5% of
"no issue found" cells to catch false negatives. Record reviewer overrides as first-class rows
(create-only, per storage rules) so agreement can be measured over time.
**Test:** sampler unit tests asserting the coverage guarantees hold across 100 randomized inputs.

## P4-T3 — Engine drift canaries
**Problem:** No GEO vendor documents how they handle engine model-version changes. Silent model
updates make trend lines lie.
**Change:** Extend `src/verification/canary.py` to run fixed probe queries each cycle and fingerprint
structural properties (length distribution, refusal patterns, citation-count distribution). On a
material shift, flag `possible_engine_update` on the run and **annotate the trend chart for that
cycle** — never silently re-baseline, never retroactively adjust history. Maintain a public
"Engine & methodology changes" log rendered in the methodology section.
**Test:** synthetic before/after distributions → flag raised; stable distributions → not raised.

## P4-T4 — [Depends: P4-T1] Grounded narrative generation
**Problem:** Writing the summary by hand does not scale past a handful of clients, but a naive LLM
summary pass introduces a **second hallucination surface** — in a product whose entire pitch is
catching hallucinations.
**Change:** Template-constrained generation: the LLM fills a fixed skeleton from already-QA'd
structured fields and **may not invent findings or re-interpret severity**. It never sees raw
ungraded engine output. Then a **deterministic post-check**: every quantitative claim in the
generated narrative must match a value in the findings table, or the render fails loudly. Human
sign-off required on Critical/High narrative sentences.
**Test:** an adversarial test where the generator emits a number absent from the source data → the
post-check rejects it. This test is the point of the task; do not weaken it.

## P4-T5 — Query-set versioning policy
**Problem:** Weekly reporting frequency is being conflated with weekly instrument-change frequency.
Change the query set ad hoc and the trend line becomes meaningless — which silently invalidates
P2-T1's comparability guard.
**Change:** Formalize a **frozen core (~75%)** that cannot change within a quarter and drives the
trend, plus a **rotating discovery slice (~25%)** refreshed each cycle. Fixed quarterly rebalance
dates. When the core must change, **bridge**: run old and new in parallel for one full cycle before
cutover. Dated changelog rendered in the methodology section. Extend `src/prompts/query_set.py` and
`csv_loader.py` with the version/tier fields.
**Test:** loader tests that a core change without a bridge run is rejected; that discovery-slice
churn does not bump the comparability version.

## P4-T6 — Per-client config as versioned data
**Change:** Fact sheet, query set version, engine list, competitor set, SLA parameters — one
versioned record per client per cycle, so any run is reproducible and diffable. Storage stays
create-only. The fact sheet already lives on `audit_runs.fact_sheet` (and the judge cache key
depends on it) — extend that pattern rather than inventing a parallel store, or you will break
cache-key honesty.
**Test:** a round-trip test that a stored config reproduces an identical judge cache key.

---

# Phase 5 — Commercialize

## P5-T1 — Free "how wrong is AI about you" scan
**Change:** 10–15 prompts × 2 engines (ChatGPT + Perplexity — cheapest and most recognizable),
one-time. Shows the **count** ("AI got something wrong about you in 6 of 15 checks") and one
competitor comparison; gates *which* errors behind signup, routing to the existing manual lead queue
(`leads` table). Respect `MAX_AUDIT_COST_USD` — add a separate, much lower cap for free scans.
**Test:** cost-gate test that a free scan cannot exceed its cap; payload test that specific claims
are absent from the ungated response.

## P5-T2 — Fact sheet as a client-facing signed artifact
**Problem:** The fact sheet is the ground truth for every finding and is invisible to the customer.
Research on LLM judges is clear that a human-written reference is the single most effective
reliability mitigation — and hidden, every finding is only as credible as a black box.
**Change:** Render "Brand Fact Sheet v1.0" as a client-readable document with a changelog; require
written sign-off before the first run; changes go through a request channel, never silent edits.
Templates already exist (`docs/fact-sheet-template.md`, `fact-sheet-fort.md`).
> ⚠ The fact sheet is **in the judge cache key**. Any edit invalidates cached verdicts for that
> client — correct behavior, but the UI must warn before saving, and the flow must keep CLI/UI/
> prejudge all keyed off `audit_runs.fact_sheet`.

**Test:** a test that editing the sheet produces a different cache key and surfaces the warning.

## P5-T3 — White-label configuration
**Change:** Client-facing brand (name, logo, accent color, "powered by" on/off) behind **one config
object** read by cover, header, footer and chart highlight color. Build it now; retrofitting a
hardcoded brand later is expensive.
**Test:** render test with two different brand configs producing correspondingly different output and
no leaked default.

## P5-T4 — Reference brand panel
**Problem:** Benchmark context normally requires many paying clients. Here it does not — model
outputs to structured prompts are producible for **any** brand, client or not.
**Change:** Run the same taxonomy against a fixed panel of 15–30 well-known brands per vertical on
the same cadence; render P25/P50/P75 bands (never a mean — outlier-distorted at low n) with `n` and
date range disclosed inline. **Label it "reference panel" or "market context," never "peer
benchmark"** — famous brands show systematically higher rates than a median client, and blending the
two would be dishonest. Enforce suppression at the product layer: no segment band below n=5,
prefer n≥10.
**Test:** suppression test that a segment with n=4 renders no band at all, and that the label string
never contains "benchmark."

## P5-T5 — Tier enforcement
**Change:** Meter on **prompts × engines × competitors**. **Do not meter cadence** — it is a
cost-to-you metric masquerading as a value metric, every competitor gives daily refresh away, and it
creates the trap where a flat week reads as wasted money. Seats unlimited at every tier.
**Test:** limit-enforcement tests per tier dimension; an explicit test that no code path gates on
refresh frequency.

---

## Global acceptance

### Two standing rules added 2026-08-02

**1. Structure is code; content is data.** The point of this work is that the *shape* of the report
stops changing once it is built, so the *content* can change weekly without touching components. That
means: severity triggers, theme rules, priority weights, significance thresholds, copy strings and
section templates all live in data or config, never hardcoded in a component. If changing a sentence
requires editing `report-view.tsx`, the abstraction is wrong.

**2. One counting unit per view.** Page 1 mixes units at your peril: an accountability strip counting
individual findings beside a tile counting themes invites a client to do the subtraction and catch a
contradiction — after which every number on the page is suspect. **Client-facing counts are themes.**
`instance_count` (individual observations) may appear as a secondary figure inside a theme, never as a
headline. The accountability arithmetic must close exactly:
`opening = resolved + still_open` and `closing = still_open + new + regressed`. P2-T5's test asserts
this; do not ship a view that violates it.


- **Order:** ~~P0-T0~~ (done) → **P0-T1** → P0-T2/T3 → **P0-T4** → Phase 1 → Phase 2 → Phase 3.
  P0-T1 is the keystone (nothing downstream works without stable finding identity) and **P0-T4
  blocks every render task** — do not start P1-T2/T5/T6 before tokens and fonts exist, or an
  agent will invent near-miss colours you then have to unpick. Phases 4 and 5 are independent
  of each other and can interleave once Phase 2 lands. P1-T3 (verbatim queries) is independent and
  worth doing first for morale — it is a one-session, visibly large win.
- **One task per session.** Each ends with `mypy src/` → `ruff check src/` → `pytest tests/` green
  (plus `npm run typecheck` for web tasks) and one regression test added.
- **`docs/build-log.md` is append-only** — one entry per completed task, most recent first. Do not
  edit old entries.
- **Do not touch `teaser/`.** Out of scope for this spec.
- **Do not touch judge prompts, the tool schema, or the message layout** unless a task explicitly
  says to. If a task seems to require it, re-read it — the intended implementation almost certainly
  derives the data in Python instead. If it genuinely requires it: bump `_PROMPT_LAYOUT`, keep
  `tests/test_judge.py` parity green, and tell the user stored runs need re-prejudging.
- **Storage stays create-only.** New columns and new rows, never deletes, never in-place mutation of
  a prior cycle's numbers.
- **`docs/audit-deliverable-fix-plan.md` is a separate, older, unstarted plan** targeting `teaser/`.
  It is not superseded by this file and is not part of this work. Do not merge the two.

## Definition of done for the whole spec

The Phase 1–2 slice is done when a second run of the same client produces a report that:
1. Opens with one sentence a CMO can act on.
2. States what changed since the prior cycle, with noise-gated deltas and an explicit resolved/
   regressed/open count.
3. Shows ≤15 themed findings with instance counts instead of 235 cards.
4. Ranks 3–7 concrete actions with an owner and an effort estimate.
5. Quotes the verbatim query and verbatim model text behind every Critical/High finding, with a
   timestamp, a pinned model id, and an honest "observed in N of M runs" statement.
6. Contains **no letter grade and no composite score at all** — every headline number is counted
   (findings, resolved, cycles open) or measured (sampled rate, share of model) — and no bare
   percentage without its denominator.
8. Uses **one counting unit** in client-facing views (themes), with the accountability arithmetic
   closing exactly: `opening = resolved + still_open`, `closing = still_open + new + regressed`.
7. Fits in roughly 13–18 pages with the appendix moved to CSV.
