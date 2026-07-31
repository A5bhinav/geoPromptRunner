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
P0-T1 (flag identity + provenance)  ──┬── P0-T2 (4-level severity)
                                      ├── P0-T3 (root-cause taxonomy)
                                      └── P2-T1 (prior-run resolution)
   P0-T2 + P0-T3 ──► P1-T1 (theme dedup) ──► P1-T2 (severity bar / collapse)
                                          └► P1-T4 (priority) ──► P1-T5 (exec summary)
   P1-T3 (verbatim queries) — independent, do early, high visible win
   P1-T6 (grade split) — independent
   P1-T7 (print CSS) — independent, do last in Phase 1
   P2-T1 ──► P2-T2 (lifecycle) ──► P2-T5 (what changed)
   P2-T3 (Wilson CIs) ──► P2-T4 (significance gating) ──► P2-T5
   P0-T1 ──► P2-T7 (evidence bundle) ──► P3-T1 (drill-down)
   Phase 3 needs Phase 2 complete. Phases 4 and 5 are independent of each other.
```

---

# Phase 0 — Foundation

## P0-T0 — [BLOCKER, no code] Confirm which API surface the pipeline queries
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

## P0-T1 — [KEYSTONE] Give accuracy flags identity and provenance
**Problem:** `AccuracyFlag` = `{type, claim, reality, severity}`. It is not addressable. Two
identical Fitbit-confusion flags from different engines are indistinguishable from one flag counted
twice; nothing can be tracked, cited, or closed.
**Change:**
1. Extend `AccuracyFlag` (`src/storage/models.py`) with: `finding_id: str` (stable content
   fingerprint — see below), `query_id: str`, `engine_name: str`, `intent: str`, `run_index: int`,
   `observed_at: str` (ISO-8601 UTC).
2. **Fingerprint rule:** `finding_id = sha256(client + flag_type + normalized_claim_stem)[:12]`,
   where `normalized_claim_stem` is lowercased, whitespace-collapsed, punctuation-stripped, and
   truncated to the first 12 tokens. It must be **stable across runs for the same underlying error**
   and **independent of engine and run_index** — that is what makes lifecycle tracking possible.
   Put this in a new `src/pipeline/finding_id.py` as a pure function with its own unit tests.
3. `AnswerJudgment` already carries `query_id`/`engine_name`/`intent`/`run_index`
   (`models.py:185`) — populate the flag fields from the parent judgment at construction time in
   `src/pipeline/judge.py`. **Do not ask the judge model for these fields**; derive them in code.
4. Update `flag_to_dict` / `flag_from_dict` (`models.py:221`) with defensive defaults so legacy rows
   still parse (existing convention — keep it).
5. Storage: add the columns in `data/schema_*.sql`, write them in `src/storage/db.py`. Create-only;
   no migration deletes anything.
6. Surface them: `src/api/reports.py` → `FlagRow` in `web/lib/api.ts`.

> ⚠ **Judge invariant.** If — and only if — you change judge prompt text, the tool schema, or the
> message layout, you must bump `_PROMPT_LAYOUT` in `src/pipeline/judge.py`, keep the HEAD/RUBRIC
> parity with `scripts/judge_via_workflow.py`, keep `tests/test_judge.py` green, and tell the user
> stored runs need re-prejudging. **The intended implementation does NOT touch the judge prompt** —
> these fields are derived in Python from data the judge already returns. If you find yourself
> editing the tool schema, you have taken a wrong turn; re-read this task.

**Test:** `tests/test_finding_id.py` — same claim from two engines → same `finding_id`; a materially
different claim → different id; punctuation/casing/whitespace variants collapse. Plus a
`tests/test_judge.py` case asserting flags inherit the parent judgment's query/engine/intent/run.
Plus a round-trip test through `flag_to_dict`/`flag_from_dict` including a legacy dict with the new
keys absent.

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
one-shot SQL update. `SeverityBadge` (`web/components/badges.tsx`) needs a 4th variant — **icon +
label on every chip, never color alone**, and reserve the red family for Critical only.
**Test:** classifier unit tests over the mapping matrix; a `badges.tsx` render test that every
severity renders a distinct icon+label pair and that Medium/Low do not use the destructive color.

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

# Phase 1 — Restructure the deliverable

## P1-T1 — [Depends: P0-T1,T3] Collapse findings into themed groups
**Problem:** `report.accuracy_flags.map(...)` (`report-view.tsx:461`) renders one card per flag —
235 cards, ~30 pages, no hierarchy.
**Change:** In `src/api/reports.py`, group flags by `(theme, finding_id)` and emit a new
`finding_groups: FindingGroup[]` alongside the raw list (**keep `accuracy_flags` in the payload** —
the CSV/JSON export and the appendix still need it). Each group carries: `theme`, `title` (human,
~8 words, generated deterministically from the theme + dominant claim — no LLM), `severity` (max of
members), `instance_count`, `engines: string[]`, `intents: string[]`, `occurrence: {observed: int,
total: int}` (how many of the sampled cells produced it), `representative_claims: string[]` (2–3
verbatim), `reality: string`, `member_finding_ids: string[]`.
**Test:** fixture with the real Fort flag set → assert ≤15 groups, that every input flag lands in
exactly one group, that `instance_count` sums to the input length, and that the Fitbit/pickleball/
"not a recognized brand" flags all land in `identity_disambiguation`.

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

## P1-T6 — [Independent] Split the grade; never render a bare F
**Problem:** `gradeColor` (`report-view.tsx:98`) puts a large red **F** at the top of the report for
a pre-launch startup. The grade is structurally unearnable (Fort hasn't shipped) and therefore
unactionable — the Moz DA / Nutri-Score / HubSpot Grader failure mode. Credit bureaus distinguish
"thin file" from "bad score" for exactly this reason.
**Change:** Replace the single `visibility_grade` tile with two:
- **Foundation Readiness** — graded from the site audit and fact-sheet/schema/PR signals already
  computed in `src/audit/` (`rubric.py`, `synthesize.py`). Winnable today, pre-launch or not.
- **Current AI Visibility** — the existing measurement, but when the client has no market presence
  yet, render the label **"Baseline"** with the sampled rate, not a letter.

Add a `is_baseline: boolean` to the scorecard payload, set when the client is pre-launch (drive it
from a fact-sheet field, not a heuristic). Keep `visibility_grade` in the payload for
back-compat.
**Test:** payload+render test — a pre-launch fixture renders "Baseline" and no letter grade
anywhere; a shipped-client fixture still renders a letter; `gradeColor` is never called with a
baseline client.

## P1-T7 — [Independent, last in phase] Print CSS for headless Chromium
**Problem:** The PDF is produced by printing the browser page. Chromium strips backgrounds by
default, cards break across pages, table headers don't repeat, and any `position: fixed` header
appears once rather than per page.
**Change:** In the web print stylesheet: `print-color-adjust: exact` (and `-webkit-` prefix);
`break-inside: avoid` on cards, chart containers and table rows; `break-before: page` on section
dividers; `thead { display: table-header-group }`; `orphans/widows: 3`; `@page` margins; running
header/footer via `position: running()` + `@top-center`/`@bottom-right` — **not** `position: fixed`.
Keep the existing `.no-print` class working.
**Test:** a Playwright test that prints a fixture report to PDF and asserts page count is within an
expected band and that no finding card is split across a page boundary (assert via the PDF text
extraction that no card's title and its body land on different pages).

---

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
**Problem:** Every edition would restate the same 235 findings from scratch. There is no way to say
what got fixed — which is the question that determines renewal.
**Change:** New `src/pipeline/lifecycle.py`. Given current and prior `finding_id` sets, assign each
finding one of: `new` (absent prior, present now), `persisting` (present both — carry `first_seen`
and an age in cycles), `resolved` (present prior, absent now), `regressed` (resolved in an earlier
cycle, present again — requires walking back more than one run, so resolve the full history chain,
not just N-1). Add `status`, `first_seen`, `cycles_open` to `FindingGroup`. Regressed must be
visually distinct and rank above a same-severity new finding in P1-T4 ordering.
**Test:** `tests/test_lifecycle.py` over a synthetic 4-cycle history exercising all four states,
including the regression case that requires looking back 3 cycles. Assert resolved findings do not
appear in the active card list but do count toward the accountability line.

## P2-T3 — [Independent within phase] Wilson intervals and sampled-rate copy
**Problem:** `pct()` renders bare percentages from tiny samples. At 3 runs × 4 engines = 12 samples,
a 50% mention rate has a Wilson 95% CI of roughly 25–75%. The report currently presents that as
"50%".
**Change:** Add Wilson score interval (not Wald — it is unreliable near 0/100% at small n) to
`src/pipeline/metrics.py`. Add `n` (denominator) to every rate in the payload. In the UI, render
rates as **"7 of 12 runs"** with the percentage secondary, and expose the interval on hover/in the
methodology block. Note `RUNS_PER_QUERY` defaults to 5 (`settings.py`) though the Fort run used 3 —
the copy must read the actual denominator, never assume.
**Test:** `tests/test_metrics.py` — Wilson bounds against known reference values; a render test that
no rate is displayed without its denominator.

## P2-T4 — [Depends: P2-T3] Two-gate significance and rolling averages
**Problem:** Without gating, most week-over-week movement is noise reported as news — the fastest way
to destroy credibility in a weekly product. `trend.py:is_real_move()` exists but uses a single
noise-floor threshold and isn't wired into the report.
**Change:** Extend `is_real_move` into a two-gate test: label a delta Up/Down only if it clears
**both** (a) statistical significance — non-overlapping Wilson intervals per engine, or a
two-proportion z-test at p<.05 on the all-engine aggregate — **and** (b) a minimum absolute
threshold: ~15pp per-engine at n≈12, ~5pp on the aggregate. Compare **3–4 week rolling averages**,
not raw consecutive points. Everything else renders **"Flat"** — and Flat is a claim, not a blank:
*"Held steady at 8 of 12 runs on ChatGPT for the 3rd straight week."*
**Test:** table-driven test over (before, after, n) tuples asserting the label; explicitly assert
that a 12→50% swing at n=12 does **not** earn an Up label but the same swing at n=240 does.

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
CMO. Adversarial benchmarks show frontier judges failing over half of bias probes; the honest
ceiling is MT-Bench's finding that strong judges reach ~80% agreement with humans — the same level as
human-human agreement.
**Change:** Extend the existing calibration tooling (`src/pipeline/calibration.py`,
`grade_calibration.py`, `scripts/run_calibration.py`, `docs/grade-calibration-guide.md`) to a
findings-level gold set of 50–100 hand-labeled (query, answer, verdict) triples. Report accuracy,
precision, recall, a confusion matrix **by severity**, and Cohen's κ. Publish the agreement rate in
the report's methodology section.
> ⚠ Calibration must keep using the held-constant API judge with `isolated_cache()` — never
> subscription/prejudge verdicts, never the shared Supabase cache. This is an existing hard
> invariant; do not relax it for convenience.

**Test:** extend existing calibration tests with the severity-stratified confusion matrix.

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

- **Order:** P0-T0 → P0-T1 → P0-T2/T3 → Phase 1 → Phase 2 → Phase 3. Phases 4 and 5 are independent
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
6. Contains no bare percentage without a denominator, and no letter grade a pre-launch client cannot
   earn.
7. Fits in roughly 13–18 pages with the appendix moved to CSV.
