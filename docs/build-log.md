## Phase T — the Track report: sections as data, and the composite is gone — Completed 2026-08-04

The whole of `docs/audit-packaging-spec.md` Phase T (TR-T0 through TR-T11), in
dependency order. The spec called it "mostly presentation and one deletion", and
that is what it was — no new engine call, no new judge pass, nothing on this path
spends money.

### TR-T0 — the deletion

`judge_metrics.visibility_score()` returned a prominence-weighted 0–1 composite
from hardcoded weights (`recommended_first` 1.0 / `mid_pack` 0.6 / `buried` 0.3 /
`also_ran` 0.1) that nothing derived, and **`leaderboard()` sorted by it**. So the
competitor ranking a client read was ordered by an invented number, and the
leaderboard table printed it as a decimal in a column called "Visibility". A
composite that orders a client-facing ranking is a score whether or not its value
shows.

Gone: `_PROM_SCORE`, `visibility_score`, `visibility_grade`, `VisibilityGrade`,
`GradePolicy`, `grade_from`, `grade_penalty_flags`, `ScorecardPayload.visibility_grade`,
`LeaderRow.visibility`, and the TS types behind them. The grade *formula* survives
in `src/pipeline/grade_calibration.py`, which is dev-only and which
`test_no_render_path_imports_the_grade_harness` keeps unreachable from a report.

Prominence now travels two ways: `prominence_distribution()` (counts across the
five levels, in a fixed order, every level present even at zero) and
`median_prominence()` (an ordinal label — "mid-pack" — never a decimal, and on an
even count it takes the WORSE of the two middles so a tie never rounds a client's
position up). `leaderboard()` sorts by mention rate, ties broken on brand name so
the order cannot reshuffle when nothing moved.

The payload field was carried for a whole phase as "back-compat for stored
deliverables". That is exactly how a dead computation stays alive long enough for
the next person to re-render it, so it went too. `teaser/` already treats a
missing grade as null.

### TR-T2 — pp, not %

`src/pipeline/fmt.py` + `web/lib/format.ts`, mirrored. A rate delta is percentage
points (42% → 48% is `+6.0 pp`); a count delta is percent change (120 → 150 is
`+25%`). A first cycle renders "Baseline — no prior cycle", never `0.0 pp` —
"nothing was measured before" and "it did not move" are different claims. A move
that rounds to zero renders in words, because a signed zero reads as movement to a
scanning eye.

### TR-T11 — the registry

`web/lib/report-sections.tsx` is the report. Fourteen entries, each
`{id, title, tier, inToc, render, thinDataFallback, hasData}`, and
`report-view.tsx` iterates it. Reordering a section is reordering an array;
dropping one is a deletion; moving one behind a tier is changing one string. None
of those touches a component, which is the standing rule the old JSX ordering
broke.

Every entry has a non-null `thinDataFallback`, asserted. An empty section reads as
a rendering bug, and a client who thinks the tool is broken stops trusting the
numbers that *did* render.

`tier` is read and nothing more. Everything ships as `track`; no gating is built
beyond the field, because speculative gating is how a tier system becomes
load-bearing before anyone has bought the tier.

### TR-T1, T3–T10 — the sections

`src/api/sections.py` builds nine blocks onto `ReportPayload`;
`web/components/report-contract.tsx` renders them. Highlights of what the honesty
rules forced:

- **§1** six measured tiles and a **neutral** sentence — the BLUF action clause
  opens §8, so a client who distrusts the advice can still trust the measurement.
- **§3** draws no connecting line under four cycles (a line through two points
  asserts a direction the sample cannot support), and excludes cycles that failed
  the coverage gate *saying so* rather than plotting a half-run as a drop.
- **§4** reads the intent-bucket family from the run. Hardcoding the consumer five
  would render an empty section for every local-service client. A bucket whose
  interval is wider than ±15 pp shows its count and interval with the point
  estimate suppressed — and its bar hatched, because drawing the bar is the same
  claim in a different medium.
- **§5** reports attempted vs returned per surface and labels anything under the
  coverage gate instead of averaging it in.
- **§6** gates every brand's move through one `gate_movements` family, so the
  multiple-comparison correction sees every test performed.
- **§7** classifies sources deterministically (owned / earned / directory / social
  / video / competitor — no LLM, or a model reclassifying youtube.com between
  editions manufactures a change) and carries the **Pareto curve**, which closes
  the last open piece of P2-T6: "are we dependent on 2 sources or 20".
- **§10** five slots, each with a published rule and ties broken on
  `(query_id, engine_name, run_index)`. A slot with no qualifying answer says so
  and is **never** filled from another — substituting a strong appearance into the
  "missing" slot makes the section a highlight reel.
- **A1–A6** rows pre-stringified so the renderer stays generic, capped at 400 rows
  with the truncation *stated*, and verbatim answer text is not printed anywhere:
  450 answers inline is 90–150 pages, which is the blob this work exists to kill.

Also unblocked in passing: the **oldest-still-open tile**. It had been `None`
since P1-T6 waiting on the lifecycle engine, which landed in P2-T2 — it now names
the finding and its age, which is the tile that replaced the grade and does its
job better.

### One test-infrastructure fix worth naming

Eight source-scanning tests were pinned to `report-view.tsx` by filename. When the
section content moved to `report-contract.tsx` they went **green-by-absence** —
still scanning a file, but the file no longer held what they were checking, which
is the worst outcome a source-scanning test has. `tests/report_surface.py` now
names the render surface once, and every rule follows it.

### Gate

`mypy src/` · `ruff check src/` · `tsc --noEmit` · 1311 passed, 3 skipped.

---

## Fact-sheet intake — the switch that turns HIGH/CRITICAL findings on — Completed 2026-08-04

Plan phases I1–I3 plus the screen. `docs/factsheet-intake-agent-plan.md` §0 is the
whole argument: `verification_tier` is the WEAKEST verification across a sheet's
claims, `SENDABLE_SEVERITIES[public_source_only]` is `{LOW, MED}`, and every
auto-generated sheet was permanently `public_source_only` because no writer of
`CLIENT_CONFIRMED` existed. HIGH and CRITICAL accuracy findings — the class the
product sells — were structurally unreachable. This is that writer.

### The package (I1) — `src/audit/factsheet/intake/`

`questions.py` the registry · `plan.py` routing and the 18-card ceiling ·
`assertions.py` answer → sentence · `claims.py` sentence → FactClaim.

Inert in the same sense the extractor is: no fetch, no clock, no model. `as_of`
is a parameter, and the one real clock is `_today()` at the API edge. That is why
143 tests over the whole registry cost nothing and run on every commit.

`assertions.py` is the part that matters. The judge quotes `FactClaim.value` and
nothing else, so `hours_sunday: closed` is a form field that leaked into a
document and `after_hours: no` contradicts nothing. Every answer becomes a
sentence that stands alone — *Closed Sunday.* *No after-hours or emergency
service.* *Does not serve Marin County.* One builder per card, because a generic
template engine produces sentences nobody would sign.

**Two decisions the plan left open, and where they landed:**

- **Date stamps.** The plan listed `hours_*` and `presence_*` as volatile. They
  are not stamped. A stamp on all seven day claims is seven pieces of noise on
  the shortest, most-quoted lines of a local sheet, and a profile URL does not go
  stale the way a price does. `pricing_*` and `features_current_*`/`features_recent`
  carry it — the two places a model is systematically behind reality. Hours are
  covered by the claim's own `as_of` column, which is what a human reads.
- **The watch-list produces claims**, in `WATCHLIST`, *and* is available to aim a
  future reverse pass. Both, so neither use has to win.

**Two bugs the tests caught before the UI existed:** branch questions defaulted
to `branch=None` ("asked of everyone"), so a plumber would have been asked about
pricing tiers — now derived by `_branded()` rather than written out 23 times, which
makes the mistake unrepresentable. And `Q-LOC-02` was being trimmed by the
card-budget logic despite being `negative_first`.

### Sessions and the API (I2)

`data/schema_factsheet_intake.sql`, applied. `factsheet_intake_sessions` is
WORKING STATE — mutated on every answer, exactly as `audit_runs` is by
`update_audit_run_progress`. The create-only invariant holds where it matters:
approving WRITES a new sheet row, and abandoning sets a state rather than
deleting. `uq_intake_sessions_live` is a partial unique index, so two people
opening the same sheet in the same minute get handed the SAME session — decided
by Postgres, not by a read-then-write check that loses the race by construction.
Project deletion cascades sessions; they are keyed by domain, so the row cascade
would never have reached them.

`src/api/intake.py`, mounted on the existing `require_api_key` router. The plan
is RECOMPUTED per request rather than stored — Q-ID-01 routes the whole tree, so
a stored plan is the old one the moment someone goes back and changes it.

`approve` refuses with a 409 naming the claims when anything is unconfirmed. That
is the tier rule, and it is a refusal rather than a warning because one
`public_source_only` claim caps the whole sheet and hides every serious finding.

### Query generation (I3)

`src/prompts/generate.py` + `data/query_templates.json`. **No LLM**, per
`docs/query-generation-plan.md` §1b: a generated set IS the instrument, and a
nondeterministic instrument makes two cycles incomparable. Slots are filled only
from confirmed claims and run inputs, and a shape whose slots cannot all be
filled is dropped — a literal `{city}` reaching an engine scores as a loss on a
question nobody asked.

Two constraints are enforced in the generator, not left to the lint: every
competitor gets a comparison question, and at least two comparisons leave the
client UNNAMED (the ones that test unprompted surfacing). When the allocation
cannot fit both, the set GROWS — an off-target allocation is a warning and a
missing competitor is a block.

`src/prompts/lint.py`: 12 checks, `block` disables approve. The last one is the
only one that matters — generate, then parse your own output with the exact
function `POST /audits` uses. Everything above it exists to produce a better
message.

### The screen (6 + 7 as ONE flow)

`web/app/fact-sheets/[id]/intake/page.tsx`. Not two routes: the conversation and
the approve gate are one continuous act, `stage` is state, and the shell and
header persist across it. A navigation between them would cost the context of
everything the owner just typed.

**The assertion preview is a server round trip**, and that was a correction. It
first rendered the owner's raw input ("A local business people call or visit")
instead of the assertion ("Black Propeller is a local business people call or
visit."), which defeats the point of the screen. Fixed with
`POST /intake/{id}/preview` — the same builder that will write the claim,
debounced 400ms because the element is `aria-live`. A TypeScript copy of the
phrasing would have drifted the first time a card was reworded, showing the owner
one sentence and quoting them on another.

Browser-verified end to end: rail advances, the fact lands in the constellation,
"On the record: …" quotes the built sentence, Skip appears only on skippable
cards, and the launcher counts every remaining question rather than the four it
lists.

`/fact-sheets` now has two tabs — Needs review / Active. There is no Rejected tab
and no Reject button: the only exits from the queue are approve and leave it
there, and the way to fix a sheet a reviewer turned down is the intake.

### Still open

- `SheetStatus` (`draft | client_reviewed | signed`) still has no database
  column, so every loaded sheet reports `draft`. A completed intake is precisely
  `client_reviewed`. Deferred: it is not on the path to the tier, which is the
  value here.
- Attachments in the composer are rendered disabled — there is no upload path
  behind them yet, and a control that silently does nothing is worse than one
  that says it is not ready.
- Nothing notifies the owner when their sheet is approved.

Gate: `mypy` clean, `ruff` clean, 1255 passed / 3 skipped, `npm run build` clean.

## Sable audit UI redesign (v3) — five screens rebuilt, recharts retired — Completed 2026-08-04

The design handoff (`# Audit UI redesign.zip` → `design_handoff_sable_audit_ui/`)
is a seven-screen, high-fidelity prototype. This entry covers the five that
already had working code behind them. Screens 6–7 (fact-sheet intake → review)
are a single continuous flow and are in progress against the intake plan.

### The shell

The top navy band became a **240px navy rail** (`components/app-shell.tsx`).
The band cost every screen a 56px stripe and then squeezed the work into
`max-w-6xl`; the report is four full-bleed panels and the run screen is a
two-column workbench, and both were losing ~250px a side to dead margin. The
rail spends the same navy vertically, where it costs nothing horizontally.

Per-page rail content (report sections, live run progress) arrives by **portal**,
not context — the rail is rendered once by the root layout and the page that owns
the content is three levels down, so context would re-render the whole shell on
every page-local state change.

New: `styles/motion.css` (the entire motion vocabulary, eight keyframes and a
required reduced-motion block), `components/page.tsx` (Page / PageHeader / Panel
/ PanelGrid / StatStrip / Chip), `components/marks.tsx` (every data mark).

### Recharts is gone from the report

`components/charts.tsx` is deleted and the dependency is uninstalled. Its five
components are replaced by four hand-rolled panels (`report-panels.tsx`):
headline, competitive, presence, findings. Three reasons, in order of weight:

1. The packaging rules say don't add a charting dependency and hand-roll the SVG.
2. `SourcesChart` was still painting indigo / emerald / amber from a categorical
   palette this brand does not have, and `BucketChart` spent a second hue on the
   citation series. Both were live brand violations, not latent ones.
3. The dynamic-import-versus-print race (a chunk still resolving when the PDF
   capture runs) stops existing when there is no chunk.

The headline panel **is** the scorecard — the four measured tiles survive intact
(AI visibility, share of model, open findings, oldest still open) and there is
still no letter grade. The one place the mock and the packaging rules pulled
against each other was the 76px hero percentage: rule 1 wants the count primary.
Resolved by keeping the count in the same block at 15px/500 navy with the Wilson
interval under it, so "66%" cannot be taken away without "119 of 180" and
"95% CI 58–73%".

The print path keeps its full-bleed navy masthead; the screen gets the app
header. `useIsPrint()` picks. Neither is a fallback for the other.

### The tests moved with the code, and none were weakened

`tests/test_print_pipeline.py` and `tests/test_report_packaging.py` both read
`charts.tsx` directly. Re-targeted rather than relaxed: the ResponsiveContainer
test became "no measurement-dependent chart runtime at all", the
chart-registration test became "no chart arrives through a lazy chunk", the
animation test moved to the stylesheet's reduced-motion block, and the donut and
heatmap tests now read `report-panels.tsx`. `marks.tsx` and `report-panels.tsx`
joined `REPORT_COMPONENTS`, so the voice and off-limits-copy scans cover every
new client-facing string. New: `test_no_report_chart_carries_an_unmarked_svg` —
`check-print-layout.mjs` now measures `svg.report-chart`, and an unmarked chart
is an unchecked chart.

### New API: `GET /projects/{key}/history`

Screen 5's mention-rate trend had no data source. `projects.project_history()`
returns one point per **completed** cycle — counts with denominators, share of
model, open findings, critical — plus `query_set_version`, because a run is
comparable only to a run that asked the same questions. The client draws the line
across the trailing run of cycles sharing the current version and says in the
caption how many earlier ones it dropped and why.

### Intake prerequisites (plan I0)

Two of the five were **already done** and the plan predates them: the fact-sheet
schema is applied, and `db.next_fact_sheet_version` already exists. What landed:

- `db.save_fact_sheet_next_version` — allocate, write, retry once, then fail with
  a reason a human can act on. The unique index is the atomicity; the retry
  covers two approvals for one domain in the same second.
- `extract._GATE_EXEMPT` — the §4.1 substring gate exempts `SourceKind.CLIENT`
  and nothing else. An owner's spoken answer has no page; what makes it
  trustworthy is provenance (`intake://{session}/{question}`), not corroboration
  by a document that does not exist. `__post_init__` still refuses an empty
  quote, so a CLIENT claim with nothing behind it cannot be constructed.
- `SheetSection` gained FEATURES / POSITIONING / WATCHLIST, **appended**. Every
  pre-existing sheet's sections sort before them, so existing `FS-nn` ids are
  byte-identical and no cached verdict is re-keyed.
- `render._RENDER_ORDER` splits document order from claim-ID order — the only
  place the two are allowed to disagree. `to_fact_rows` and `to_csv` are
  unchanged, because that is what the judge reads.

Gate: `mypy` clean, `ruff` clean, 1096 passed / 3 skipped, `npm run build` clean.
Not yet verified: the PDF page-count band (`npm run report-pdf` needs a stored
run with a live API).

## Patch — the report was calling measured work "unmeasured" — Completed 2026-08-02

Asked whether a gold set already existed. It does — `data/fort_gold.json` and
`data/oura_gold.json`, 40 hand-labeled answers each, **already run** on
2026-07-31 against the held-constant judge with `isolated_cache()`. The results
have been sitting in `docs/calibration/fort-2026-07-31.md` the whole time.

Meanwhile the report's methodology section said judge agreement "has not yet been
measured". That was wrong, and wrong in the direction that costs credibility:
94% agreement on 240 brand judgements is a defensible number, and publishing
"unmeasured" beside it understates the work while sounding cautious.

### What the sets actually hold

    fort_gold.json   40 items   1 critical,  0 high,  0 med,  0 low,  39 none
    oura_gold.json   40 items   0 critical,  3 high,  6 med,  5 low,  26 none
    local_gold.json  25 items   zero findings of any kind

The decisive check: run `gate_critical_high_recall` against a **hypothetically
perfect judge** — one that agrees on every item. All three sets still fail.

    fort:  raw 100%, AC1 1.00 -> critical: only 1 example (one item moves recall 100%)
    oura:  raw 100%, AC1 1.00 -> high: only 3 examples (one item moves it 33%)
    local: raw 100%, AC1 1.00 -> no findings at all

A flawless judge cannot pass. That is not the gate being harsh; it is the gate
correctly reporting that these sets cannot measure this thing. Which is the same
conclusion `project-queue.md` reached by hand in June — now reproducible as a
command instead of a note.

### The fix: publish both halves, each with its denominator

`AgreementSummary` (`src/pipeline/calibration.py`) reduces a calibration run to
what the report may publish, and `data/calibration/<client>.json` stores it.
Content as data, per the standing rule — no client wiring, no hardcoded figures
in a component.

The line Fort now carries:

> Judge agreement with a human reviewer, measured 2026-07-31 on 40 hand-labeled
> answers (240 brand judgements): brand mentioned 94%, prominence 86%, framing
> 93%. Accuracy-finding agreement is not quoted: the labeled set contains 3
> findings, too few for a precision or recall figure to be stable. Every finding
> in this report cites the exact prompt, model and date behind it so it can be
> checked directly.

`flags_are_quotable` gates the second half at 20 findings. Fort's 43% precision
is computed on **seven** judge flags; publishing "43%" without the 7 is the
bare-percentage failure the report forbids everywhere else, wearing a different
coat. Oura's 18 is the best-powered set that exists and is still under the bar —
that is the finding, not a gap in the tooling.

The threshold is not a permanent refusal: `test_a_well_powered_flag_sample_would_be_quoted`
pins what changes the moment the strata are filled.

### What is actually left

~60 stratified items — `stratify_gold_candidates`, 20 each from judge-said-severe,
judge-said-nothing, and boundary — drawn from runs already stored. The Fort
`csv-2026-06-13` run alone carries 115 flags across 540 judged cells. Labelling
work, not a new programme, and nothing about it is blocked.

### Gate

`mypy src/` 110 files · `ruff check src/` clean · `pytest tests/` 1094 passed,
3 skipped · verified against run `ff231808`, which now publishes Fort's real
figures.

---

## Patch — Phase 3 was not done when I said it was — Completed 2026-08-02

Asked to confirm, and it wasn't. Three gaps, all the same shape: **the backend
half of a feature built, the half a human touches missing.** Each would have
passed any test I had written, because I had written tests for the half that
existed.

**P3-T1 had an endpoint with no caller.** The spec asks for "an expandable inline
panel on each finding card showing the full answer with the flagged claim
highlighted". The card showed the stored excerpt; nothing fetched the answer.
`AnswerPanel` now does, on expand, cached per cell. Verified in the browser: it
pulls the full 1,924-character answer and highlights *"Batch 1 ships Q3 2026"*
inside it.

Highlighting is a plain substring match, and when it misses — the judge can quote
across a line break — the answer still renders unhighlighted. Showing the
evidence beats refusing to show it because a marker failed.

**P3-T4's link could not be opened.** `/shared/{token}/report` returned JSON;
there was no page. A shareable link nobody can click is not a shareable link.
`web/app/shared/[token]` now renders the report with **no `runId`**, so the
Judge, re-judge and export controls never mount — read-only by construction
rather than by permission, with no privileged action on the page to guard.
Verified: renders 4 cards with no API key in the browser at all, and a tampered
token shows *"this link is not valid"* rather than a stack trace.

**P3-T5 returned 503 where the spec says degrade.** A missing Chromium now
302s to `?mode=print` with an `X-PDF-Fallback` header. The repo's existing
convention (`teaser/render/audit/pdf.ts`) is that a missing browser costs you the
PDF, not the deliverable — a 503 leaves an operator with nothing while a
perfectly good printable page sits one URL away.

### Two test bugs of the same family, again

`"runId" not in source` matched the COMMENT explaining why there is no runId.
Fixed by asserting on the JSX prop (`runId={`) instead of the word. That is the
third time this session a source-level guard matched prose about the rule rather
than the rule — the pattern is now: assert on syntax, never on vocabulary.

### A local-setup consequence worth knowing

Share minting needs `GEO_API_KEY`; the dev UI currently needs none. Setting the
key made the web app 401 mid-verification, because `NEXT_PUBLIC_GEO_API_KEY` in
`web/.env.local` is unset. Set both together or neither.

### Gate

`mypy src/` 110 files · `ruff check src/` clean · `pytest tests/` 1088 passed,
3 skipped · `tsc --noEmit` clean · `next build` clean (`/shared/[token]` listed) ·
shared page and drill-down both verified in a browser.

---

## Sable P0 + the deferred gates — Completed 2026-08-02

Closes the two things the P1–P4 entry below left open: the Python phase, and the
client-facing gates that needed a live API.

### P0 — a CLI run now always reaches a terminal status

`run_audit()`'s measurement loop is wrapped in `try/finally`; the terminal write
is derived from a `completed` flag set *inside* the `try` after the loop, so an
exception from the final iteration cannot mark a run done. The standalone
`status="done"` line is gone. Ctrl-C / crash → **`cancelled`** immediately,
instead of sitting at `running` until the API's next startup scan relabelled it
`interrupted`. Deliberately NOT fixed by storing the CLI's query set — that would
make aborted runs auto-resume at API startup and spend engine money nobody asked
for. Also corrected the stale reason string and docstring in
`resume_interrupted_runs()`, which described legacy pre-resume rows rather than
what actually reaches it.

**The test I wrote first was wrong, and the reason matters.** It raised
`RuntimeError` from a fake engine to simulate an abort — and the run completed
normally. `run_query_set` catches `Exception` and turns a failed cell into a
`None` response; that IS the "engines never raise, the pipeline never crashes
because one engine failed" invariant. So an ordinary engine error can never
exercise this path. The abort that actually propagates is `KeyboardInterrupt`,
a `BaseException` — i.e. the literal Ctrl-C case. Three tests now cover it:
abort → `cancelled` with prior work still counted; loop-completed-then-died →
`done`; and a storage failure in the `finally` must not mask the original
exception. All fake `db`, make no engine calls, cost nothing.

Note `update_audit_run_progress` is now called with `error=`, which broke the
existing resume test's 3-arg fake — widened, not worked around.

### The gates that needed a live API

- **`report-pdf`: 15 pages — inside the 13–18 band.** `print-check` passes
  (cards=5, charts=3, longest table 21 rows). So the `Card` padding/shadow and
  `--radius` changes did not cost the deliverable a page.
- **No valid before/after baseline exists.** I built a HEAD worktree to compare
  page counts; it rendered 1 page of font data. `HEAD` (e9baf3b) predates the
  current report entirely — the working tree carries substantial uncommitted
  report work. The 15-page figure is therefore an absolute check against the
  band, not a delta.
- **The band is unverifiable on most stored runs.** Across all 24 runs in the
  DB, `themes`, `findings` and `accuracy_findings` are **zero everywhere** — no
  stored run exercises the findings-heavy sections. The first run I tried
  produced 8 pages for exactly this reason, not because of any CSS change.

### Two real contrast bugs, both the same trap

Measured in-browser rather than assumed, and the spec's own §10 predicted both:
**Harbour on the Paper ground is 4.14:1 and fails AA.**

- `.label` (the page eyebrow) shipped as Harbour, and every use is on Paper —
  10px failing text on all seven routes. Now `--ink-secondary` (5.59:1), which
  is also correct on white, so the class is safe in both contexts. The report's
  `.sable .label` is more specific and is untouched.
- The back-links on `/audits/[id]` and `/projects/[key]` sit outside any card.
  Same fix.

After both: **0 contrast failures and 0 missing focus rings** across `/`,
`/projects`, `/fact-sheets`, `/teaser`, `/audit`.

### Pre-existing, reported not fixed: the client report fails AA

With the report mounted, 41 elements measure below AA — **all inside `.sable`,
none of them mine.** `sable.css` is untouched (clean in git) and sets both
`.body` and `.sable .label` to Harbour on the Paper report ground: 4.14:1. This
is the paid deliverable, so it is worth a decision, but it belongs to the
audit-packaging spec and to whoever owns the identity guide — the fix is a token
change in `sable.css`, which this spec explicitly forbids touching.

Gate: `mypy` clean · `ruff check src/` clean · **1084 passed, 3 skipped** ·
`npm run typecheck && npm run build` green.

---

## Sable app chrome — P1–P4 — Completed 2026-08-02

`docs/ui-redesign-sable-spec.md` P1–P4. The app chrome now wears Sable at
`:root`; the indigo shadcn theme is retired. **P0 (Python) was deliberately not
done** — the correction-run work is still uncommitted in `orchestrator.py` /
`runner.py` / `cli.py` / `db.py` / `cost.py`, so nothing under `src/` was
touched. Scope was `web/` only.

New: `styles/tokens.css`, `components/plume.tsx`, `components/app-header.tsx`,
`components/notice.tsx`, `lib/ui.ts`. Rewritten: `globals.css`,
`tailwind.config.ts`, `layout.tsx`, `icon.svg`, `ui/{button,card,badge}.tsx`,
`badges.tsx`. Class-level edits across all seven routes and the six
supporting components. Inter deleted; Libre Franklin is the UI face.

### The spec's P1 exit criterion is wrong, and it mattered

The spec says deleting `destructive`/`success`/`warning` from the Tailwind
config makes `npm run build` "fail, loudly," and that the failure list *is* the
P3/P4 worklist. **It does not fail.** Tailwind v3 does not error on unknown
utilities — `text-destructive` simply emits no CSS. The build was green before
a single call site had been migrated, which is the exact silent-success failure
the spec was trying to design against.

The real worklist came from `grep` plus `tsc`: TypeScript *does* catch the
removed `cva` variants, and that caught 14 call sites. Anything expressed as a
bare class string was invisible to both and had to be grepped. If a future
phase relies on "the build will tell me," it won't.

### Two things the spec did not know were in scope

- **`charts.tsx` — declared untouchable (§7.6), actually broken by P1.** It
  reads `hsl(var(--muted-foreground))`, `--border`, `--card`, `--primary`,
  `--secondary`, `--foreground` — the shadcn HSL triplets P1 deletes. Left
  alone, every axis tick, tooltip and bar fill in the **client report** would
  have resolved to an invalid colour. Repointed to `var(--navy)` /
  `var(--harbour)` / `var(--rule)` / `var(--white)`, which are defined in both
  `:root` and `.sable`, so charts render identically in app and PDF.
- **`report-view.tsx` needed six edits, not the sanctioned two (§6.4).** The
  file grew since the spec was written. Lines 419/432 are now 567/580; on top
  of them, two `Badge` variants were hard type errors, and two `text-destructive`
  sites (`split_cells`, the losing-queries `TrendingDown`) are *not* `no-print`
  and would have shipped colourless to a client. Both moved to the monochrome
  navy ramp per the audit-packaging skill.

### Still open

- `charts.tsx` keeps a 7-hue categorical `PALETTE` (indigo/emerald/amber/…) for
  source domains, and a hardcoded `hsl(199 89% 48%)` citation bar. Both are
  pre-existing, both violate "no colours outside the palette," and both are a
  design decision rather than a migration step — **not** changed here.
- `npm run report-pdf` / `print-check` not run: both need a live API and a known
  run id. The 13–18 page band is **unverified**, and P3 changed `Card` padding
  (`p-6` → `p-5 pb-3`) and dropped `shadow-sm`, plus `--radius` 0.75→0.875rem.
  Re-run before the next client send.
- `/audit` still renders `grade {a.grade_letter}` in the saved-audits list,
  which contradicts the packaging skill's no-letter-grade rule. Left alone —
  it is stored data, not styling.

Verified in-browser: three plumes in the header, exactly one Sky in the DOM,
app ground and report ground both `#f2f1ec`, `--sky` undefined in both scopes,
h1 Cormorant at 34px, controls 36px. `npm run typecheck && npm run build` green.

---

## Phases 4 and 3 complete — Completed 2026-08-02

Six operations modules and six delivery surfaces. Live status:
`docs/audit-packaging-status.md`.

    review.py      sampling + reconciliation      drift.py       engine canaries
    narrative.py   the grounding verifier         versioning.py  frozen core + config
    digest.py      the weekly email               sharing.py     signed links
    fixpack.py     pasteable briefs               + 3 new endpoints

### Benjamini-Hochberg's cousin: two more "looks right, does nothing"

**The narrative verifier passed its own honest fixture as a FAILURE.** "Mention
rate fell 8 percentage points" against a fact of −8 was rejected on sign — but
natural prose puts direction in the VERB, and comparing signed values rejects
correct writing. Worse, it would have *passed* "rose −8 percentage points".

Deltas now match on magnitude and direction is checked properly by
`_direction_ok`, which catches the failure a numeric comparison structurally
cannot: **"improved" beside a −8 fact contains no wrong number at all.** That is
the qualitative-overclaim case the implementation guide flags, and it needed its
own check rather than a stricter version of the numeric one.

### The stratum everyone leaves out

The QA queue samples a random 5% of cells where the judge found **nothing**.
Without it the queue can only ever discover over-flagging — and the expensive
error here is the miss. Two more properties that are easy to get wrong:

- **A 5% rate over 12 cells rounds to zero.** A stratum that silently samples
  nothing is a stratum that does not exist, so a non-empty population always
  contributes at least one item.
- **The cap never cuts into a mandatory stratum.** Dropping a Critical from
  review to make room for a routine sample is exactly backwards, and truncation
  is *reported* (`SampleResult.dropped`) because a silently-capped queue reads as
  full coverage.

Coverage guarantees are asserted over 100 randomized inputs, not one fixture.

### Drift says nothing rather than guessing

Three of six surfaces publish no dated model pin at all, so drift there is
invisible in metadata — hence a behavioural fingerprint (length, refusal rate,
citations). Two deliberate silences: a first cycle is **not** drift (otherwise
every new client's first report warns about an engine update that did not
happen), and fewer than five answered cells produces no verdict. A spurious
annotation trains people to ignore annotations.

And it annotates, never re-baselines. The annotation is asserted to contain no
claim about the client — no "improved", no "declined", no "visibility".

### Discovery churn must not break the trend

`comparability_version` is derived from the **frozen core only**. A version over
the whole set would break the trend every single week, which is the opposite of
what tiering is for. A core change with no bridge cycle raises rather than warns:
a warning is ignored exactly once, and then the trend is silently broken for a
quarter.

`config_fingerprint` deliberately excludes `notes` and `revision` — tidying a
comment must not force a spurious incomparability — and includes the fact sheet,
because the judge cache already keys on it.

### Delivery

**The digest subject differs in all four states** and always carries a number.
"Your Weekly GEO Report" trains the reader to skip it, and for a format nobody
has to visit the open rate is the product. **Every digest has a "what we're
doing" line, including when the answer is "nothing"** — that is precisely where
recurring reports lose readers. And it reads every figure from the payload rather
than recomputing: the first thing a client notices is the email disagreeing with
the report.

**Share links** verify signature → revocation → expiry → password, in that order.
Checking expiry first would let a visitor enumerate which run ids exist from the
different error messages. Every failure is 403 with the reason in the body, for
the same reason. Revocation is per-token, or "revoke" would mean "revoke every
link anyone was ever sent". Verified end to end: valid 200, tampered 403,
password-missing 403, password-correct 200, revoked 403 — and the shared route
takes **no API key**, since a login wall is what kills forwardability.

**Filters are `no-print`** and the visible count is stated. A filtered PDF that
looks complete is the same class of bug as a lazy-loaded section that silently
vanishes. The severity bar counts what is VISIBLE, so the bar and the cards below
it cannot disagree.

**The PDF endpoint delegates to the P1-T7 worker** rather than rendering again —
one renderer, and the worker owns every Chromium trap. Exit code 2 (Chromium
missing) becomes a 503 with the install hint, not a 500: an environment problem
must not read as a failed render.

### Verified against the real Fort run

    fix-pack.md   5 findings, worst first, each block self-contained
    digest        "Fort appears in 51 of 180 answers this cycle (new question set)"
    drill-down    the verbatim prompt and full answer for one cell

The fix-pack's ban on outcome promises is scoped to the Fix and How-we'll-check
sections — the standing disclaimer uses "guarantee" in a NEGATION, and a
whole-document scan would have forbidden the sentence that keeps it honest.

### What code cannot finish

**P4-T1 needs a gold SET.** The metrics, sampler, reconciliation and gate are all
built. What is missing is labelled data — ~60 items with the stratified sampler,
or 334 randomly sampled. Until then the report says "not yet measured at a sample
size that would support quoting a figure", which is true.

**P4-T4 has a verifier but no generator**, deliberately and in the safe order:
the guard is what makes a generator safe to switch on. `fallback_narrative` runs
until then.

**Persistence is not wired** for review records, drift fingerprints or
`ClientConfig` — each needs a table before it accrues history. Share revocation
is in-process and forgets on restart.

`GEO_API_KEY` is empty in `.env`, so the API is open (its own startup warning
says so) and share links cannot be signed — `mint_share_token` refuses rather
than signing with an empty key.

### Gate

`mypy src/` 110 files · `ruff check src/` clean · `pytest tests/` 1081 passed,
3 skipped · `tsc --noEmit` clean · `next build` clean · endpoints exercised
against run `ff231808`.

---

## Migration applied; P4-T1 agreement metrics and the production gate — Completed 2026-08-02

### The migration

`data/schema_run_corrections.sql` is live. `supports_run_lineage()` returns True
and `--correct` works against the real database:

    Correcting run e186c524: re-asking 19 cells (~$0.43), carrying 11 answered
    cells forward. Missing by surface: openai_search 10, google_ai_overviews 9.

First attempt rolled back on `invalid sslmode value: "require\`"` — a stray
backtick on the end of `SUPABASE_DB_URL` in `.env`. The whole file runs in one
transaction, so nothing half-applied. Fixed the value (backed up and removed the
backup after verifying); the DSN was never printed unredacted.

### P4-T1 — the metrics half

`src/pipeline/agreement.py`, hand-rolled, no new dependency. `irrCAC` would have
been two functions' worth of import for a dozen lines of closed-form arithmetic —
the same trade already made in `stats.py`.

**Gwet's AC1 is the headline, not Cohen's kappa**, and the module reproduces the
paradox that makes that necessary:

    raw agreement 0.975 -> AC1 0.973 · kappa 0.654

Kappa penalises agreement in proportion to class imbalance, and this data is
nothing but class imbalance — most answers carry no flags. Publishing the kappa
would say the judge is unreliable when it agrees with a human 39 times in 40, and
the natural response to that number is to "fix" a judge that is not broken. AC1,
raw agreement, kappa and the full confusion matrix all ship together; no single
number is honest on its own.

### The gate is recall, and it fails three different ways

A judge answering "no flag" to everything scores **95% aggregate accuracy** on a
5%-prevalence set with **zero recall on the tiers a client acts on**. Aggregate
accuracy cannot see that. `gate_critical_high_recall` can, and it also fails:

- a tier with **no gold examples** — unmeasured must not read as passing;
- a tier that is **under-powered**, even at perfect recall. Three gold flags
  cannot demonstrate 90% recall whatever they score, and the current Fort set has
  exactly three: two identical runs returned recall 67% then 100% on the same
  inputs. That is the sample size talking, not the judge.

`_rate` returns 0.0 for an empty denominator rather than 1.0, deliberately. The
opposite convention flatters precisely the case that matters — a gold set with no
Criticals would report the judge as flawless on Criticals.

### One label per answer, or none of the metrics are defined

AC1, kappa and per-class recall are single-label classification metrics; a
multi-label item has no single "the judge said X". `calibration.severity_label`
collapses an answer's flags to its **worst** severity, because that is what a
reader acts on: an answer carrying a Critical and three Lows is a Critical.

### Published, including when it cannot be

The report's methodology now carries a judge-agreement line, and when no
sufficient gold set exists it says so rather than omitting it. Omission reads as
"not applicable"; the truth is "not measured", and every Critical finding rests
on this. The current state is sharper than unmeasured — it is *unmeasurable at
this sample size*.

`required_items_for_minority(20, 0.06)` = **334 randomly-sampled items** for 20
Criticals, or far fewer with the stratified sampling the spec asks for. Size the
gold set by the rare class, never by the total.

### Still open inside P4-T1

The stratified sampler, blind two-reviewer labelling, and the durable override
record keyed on `prompt_fingerprint`. Tracked in
`docs/audit-packaging-status.md`, which is now the live checklist for the whole
spec.

### Gate

`mypy src/` 103 files · `ruff check src/` clean · `pytest tests/` 913 passed,
3 skipped · `tsc --noEmit` clean.

---

## Phase 2 complete: the report now says what changed — Completed 2026-08-02

Five pieces, in dependency order: theme-rule fingerprinting, the lifecycle state
machine, the what-changed section, significance gating, delta pills and paired
bars. Live status and what's left: `docs/audit-packaging-status.md`.

Rendered against the real Fort `csv-2026-06-13` trio — the only multi-cycle
history with actual findings:

    cycle 1  no_prior_run · 5 findings opened
    cycle 2  "0 of 5 findings from last cycle are resolved, 2 newly opened,
              5 still open"  · 4 surfaces, all "held steady"
    cycle 3  cycles_considered=3 · pricing_offer persisting, open 3 cycles

Those three runs are 11 and 22 minutes apart, and every surface correctly reads
**held steady**. That is the gating working: small-sample jitter between two
attempts at one measurement is exactly what must not render as movement.

### I talked myself out of the thing I proposed

I pitched `comparison_blocked_reason: "theme_rules_changed"` — block the diff
when the classification rules move. Building it showed it was the wrong
mechanism.

The lifecycle classifies **every cycle's raw flags with the current rules at
report time**, so a rule change applies to both sides of the diff identically
and cannot manufacture a resolve. Blocking would discard a comparison that is in
fact valid.

What a rule change really breaks is narrower: the client read last week's edition
under the old rules, so their *memory* of the card list is what moved. So the
fingerprint ships in the payload and the methodology instead — the input a future
edition-diff needs to say "we regrouped these findings; nothing about your brand
moved". `rules_fingerprint()` is computed from the rules rather than
hand-maintained, so it cannot be forgotten, and `tests/test_themes.py` pins it
exactly like the judge prompt fingerprint.

### Benjamini–Hochberg was inert. Twice.

Both versions look correct, which is why they are worth recording.

**First:** rank on a pseudo-p derived from the interval's distance from zero,
capped at 0.05. At rank *m* the BH threshold **is** the FDR, so a p that can
never exceed 0.05 always survives. Replaced with a real two-proportion test on
the effective samples (`stats.two_proportion_p_value`).

**Second, and subtler:** feed BH only the cells that had already passed a
per-cell α≈0.05 gate. Every candidate then has p ≲ 0.05, the step-up finds
k = m, and it rejects all of them. **Filtering before correcting removes the very
comparisons that make the correction bite.**

The family has to be every comparison performed, flat ones included. With 2
strong cells among 18 marginal and 5 flat, `p(20)=0.0496` faces a threshold of
`(20/25)·0.05 = 0.04`, the step-up walks down to k=2, and the 18 marginal cells
are correctly demoted. `test_correcting_over_only_the_significant_cells_would_be_inert`
pins both failure modes directly.

### Exhaustive beats property-based here

The spec asks for Hypothesis. It is not a dependency, and for a state machine
over boolean presence sequences it would be strictly weaker than what replaced
it: **every** sequence up to length 12 is 4,096 cases and runs instantly. So the
invariants — exactly one status per cycle, first fact always NEW, RESOLVED only
after ≥N absences, REGRESSED only immediately after RESOLVED, age resets to 1 on
REGRESSED, `first_seen` never moves — are checked over all of them rather than a
sample.

The case worth naming: `TFT` and `TFFT` differ by one cycle and mean opposite
things. The first never actually resolved, so its return is continuation. The
second reached a confirmed fix that then broke. Collapsing them tells a client a
fix failed when it never landed.

### Both guardrails hold on real data

Albert Nahman's shape — good run, broken run, good run — is a test:
`test_a_broken_run_between_two_good_ones_does_not_break_the_streak`. The 0.37-
coverage run is skipped entirely, so the theme persists across it rather than
appearing to lapse. Filtering happens BEFORE the state machine, not inside it,
which is what makes that free.

### Deliberately not built

**Bump chart.** Needs ≥3 cycles to say anything; an empty state would be
decoration. **Pareto sources** likewise deferred. Both recorded in the status doc
rather than half-built.

### What this does NOT do

Everything here is fixture-correct and **unvalidated against a real cadence**.
Only three stored runs ever carried a fact sheet and they sit on three different
query sets; the one multi-cycle history has cycles minutes apart. The unblock is
one re-run of Fort on `csv-2026-06-14` with the same sheet — relaunchable from
the stored row, ~$10, judging free if prejudged.

The cycle-length decision (weekly vs `trend.py`'s 42 days) is still open, and it
has a live consequence: `_prior_comparable_run` applies no minimum interval, so
those 11-minutes-apart runs render as three cycles. Correct arithmetic, wrong
unit. The agreed fix is a labelling rule, not a blocking one.

### Gate

`mypy src/` 102 files · `ruff check src/` clean · `pytest tests/` 899 passed,
3 skipped · `tsc --noEmit` clean · `next build` clean · rendered end to end
against three real Fort cycles.

---

## Correction runs: top up a broken audit instead of re-running it — Completed 2026-08-02

A run that FINISHES with dead engines was terminal. `list_resumable_runs` only
picks up `running`/`queued`, and `done_cells` is built from row existence — but a
failed call still writes a row (`response: NULL`), so a resume steps over exactly
the cells that need retrying. Albert Nahman's 2026-07-28 cycle is what that cost:

    06:26  30 cells, 11 answered
    07:37  25 cells, 11 answered
    07:41  35 cells, 21 answered
    22:19  40 cells, 40 answered   <- four full runs for one measurement

`geo audit <queries> --correct <run-id>` now re-asks only the failed cells.
Planned against the real rows, no spend:

    e186c524: re-asking 19 cells (~$0.43), carrying 11 forward.
              Missing by surface: openai_search 10, google_ai_overviews 9.
    86b644f0: answered every attempted cell — nothing to correct.

The plan also *diagnoses*: ten `openai_search` misses in every run is a dead
surface, not bad luck — which is exactly what the repin later confirmed.

### A new run, not an edit

Filling a stored `response: NULL` in place would mutate a run someone may already
have been shown. Create-only storage (`CLAUDE.md`) and immutable prior cycles
(the packaging rules) both exist so "what did we tell the client on the 14th"
always has an answer. So a correction is a new immutable row carrying
`run_kind='correction'` and `supersedes_run_id`, holding the parent's answered
cells verbatim plus the newly-filled ones.

Answers are COPIED onto the new run rather than left to a read-time union. A
union puts the join in every reader, and one reader forgetting it is a report
that silently loses most of its data.

### A correction is not a new cycle

This is the half that matters more than the cost saving. `_prior_comparable_run`
now skips any run something supersedes, so a corrected week compares against the
previous **week** — not against its own broken first attempt. Without that skip
the repair of a failed measurement renders as movement in the client's
visibility, which is the same class of false claim as calling model
nondeterminism a fix.

It also means corrections need no exception in whatever cycle rule lands later.
The gap governs *cycles*; corrections govern *completeness*.

### Three decisions worth the words

**`resume` and `correct` are mutually exclusive, and mean opposite things about a
failed cell.** Resume treats attempted-as-done, so a restart cannot start
re-paying for a permanently dead surface; correction treats attempted-and-failed
as the work. Passing both raises.

**Cost is priced per engine, not scaled from the whole-run estimate.** Failures
concentrate on one surface — that IS the failure mode — and the six surfaces
differ ~25x per call. Scaling by "fraction of cells missing" would badly
under-charge a correction whose dead surface is `anthropic_search` (~48% of
engine spend). `estimate_cost_for_cells` sums the actual cells, and it replaces
the whole-run figure in the budget gate, so a $0.43 top-up is not refused as if
it were a $10 audit.

**The lineage write RAISES where the fact-sheet write only warns.** Losing
fact-sheet provenance loses a trace. Losing a correction's lineage leaves an
ordinary-looking extra run for the same client and query set — a phantom cycle
the resolver will compare against. `supports_run_lineage()` is checked BEFORE the
row is created, because the lineage write happens after the insert and finding
the gap then would leave that phantom behind.

### Migration NOT applied

`data/schema_run_corrections.sql` adds `run_kind` (default `'baseline'`, so no
backfill) and `supersedes_run_id`. It is written and tested but **not applied to
the live database** — that is a production schema change and is Abhi's call:

    python -m scripts.apply_schema data/schema_run_corrections.sql

Until then `--correct` refuses with the migration hint rather than creating an
untracked run. Verified against the live database: the probe returns False and
the refusal fires.

### Not wired

The API and web UI have no correction path — recovery is CLI-only for now. Runs
are started from the UI, so a broken run is noticed there and fixed at the
terminal. Worth a button eventually; not worth blocking this on.

### Gate

`mypy src/` 100 files · `ruff check src/` clean · `pytest tests/` 845 passed,
3 skipped · planner verified against all four real Albert Nahman runs.

---

## P1-T7 + P1-T8: the PDF is reproducible, and 15 pages shorter — Completed 2026-08-02

The client PDF was a human pressing `window.print()`. It is now
`npm run report-pdf <run-id>` — headless Chromium, one margin source, real
running headers and page numbers, gated on a readiness signal the app raises
itself. Verified against run `ff231808` end to end.

    32 pages  ->  17 pages   (the spec's 13-18 band)
    Page 1 of 17 · running header · both disclosures · verbatim prompts
    every finding card's title and its Fix line on the SAME page

### One flag, because three bugs are really one bug

`web/lib/render-mode.tsx` holds a single `screen | print` context set from
`?mode=print`. Print never scrolls the viewport, so `IntersectionObserver` never
fires — a spec-level property of paged media, not a Chromium bug — and the
consequences all look identical from the live page, which is perfect:
`loading="lazy"` images blank, `ssr:false` sections gone, a windowed table
emitting 20 of 200 rows. One flag makes a missed fork greppable instead of
something a client finds.

`ResponsiveContainer` fails differently and needs its own fix: it sizes through
`ResizeObserver`, which print never triggers, so charts print at whatever the
last on-screen size was. `ChartFrame` swaps it for a fixed box matching the
`@page` content width when printing.

### The readiness gate is quiescence, not a chart count

`networkidle` only means HTTP quiesced; client-rendered SVG finishes on later
animation frames. The gate requires three things: no chart still laying out,
`document.fonts.ready` (font metrics decide axis-label layout, and both Sable
faces are metrically unlike system-ui), and **two frames with no new
registration** — so a chart whose `next/dynamic` chunk resolves late cannot let
the counter transiently hit zero and declare the page done.

Quiescence rather than an expected-chart count on purpose. A count couples the
gate to how many charts the report happens to render today and would fail
*silently, as ready-too-early*, the first time someone adds one.

### 16 of the first PDF's 32 pages were one finding's evidence

The lifecycle finding printed all **94** of its observations. That is the
235-identical-cards blob rebuilt one level down, inside a card.

Evidence is now capped at four per finding, chosen **one per surface first**:
four excerpts from four engines show the error is not one model's quirk, which is
the question a reader actually has; four from one engine show nothing extra.
`evidence_total` carries the real count and the card says "Showing 4 of 94
observations, one per surface" rather than implying it showed everything. The
full set stays in `accuracy_flags` and the answers export.

That one change is the whole 32 -> 17.

### Two checks that were confidently wrong before they were right

`check-print-layout.mjs` reported **"2 of 5 charts have no size"** on its first
real run. Both were recharts *legend icons* — recharts reuses the
`recharts-surface` class for the 14x14 SVG inside each legend item. Selector
tightened to `.recharts-wrapper > svg.recharts-surface`.

Then it reported **three cards straddling a page boundary**, also wrong, and this
one matters more because it is a limit of the technique rather than a typo:
`emulateMedia({media:'print'})` applies print STYLES but does not paginate.
Layout stays continuous, so `getBoundingClientRect()` reports where a card would
fall under naive slicing and cannot see Chromium honouring `break-inside: avoid`
at actual print time. The heuristic the implementation guide recommends is only
valid for elements that are *taller than a page* — which genuinely cannot honour
the rule — so that is what it checks now. Real pagination is verified against the
produced PDF, where it is real: the three Critical cards each have their title
and their Fix line on one page.

### The traps that fail silently, all guarded

`@page { margin: 0 }` with the real margins in `page.pdf()` — mixing the two is
an open Playwright bug whose usual symptom is a clipped header. Templates are
ignored entirely without `displayHeaderFooter: true`, render in an isolated
iframe (no stylesheet, no relative webfont, images must be base64), and default
to an effectively-zero font size. `printBackground: true`, or the severity ramp
prints as four identical empty chips — Sable has no alert hue, so tone is the
only thing carrying the tiers.

`position: running()` and `string-set()` are **not implemented in Chromium** and
are not coming, so a section-aware running header ("Findings — continued") is
impossible here in any mode. The header is static, and the file says so.

### Tests

`tests/test_print_pipeline.py` — 14 always-on source assertions for the invariants
that fail silently, plus an opt-in end-to-end pass
(`RUN_PRINT_CHECK=1 PRINT_CHECK_RUN_ID=<id>`) that prints a stored run and reads
the PDF back: page-count band, running header, page numbers, both disclosures.
The margin assertion strips CSS comments first — the file necessarily quotes
`@page { margin: 0 }` in the prose explaining the rule, and matching the
explanation is how a source guard passes while the rule is wrong.

### Gate

`mypy src/` 99 files · `ruff check src/` clean · `pytest tests/` 829 passed,
3 skipped · `tsc --noEmit` clean · `next build` clean · e2e print pass green
against `ff231808`.

---

## Patch — flag provenance did not survive storage — Completed 2026-08-02

Found by asking a plain question of the work above: *does a NEW audit get the
full packaging, or only the degraded version the Fort run showed?* The answer was
"neither" — and the Fort run's missing evidence was never a legacy-run problem.

`flag_to_dict` writes four keys on purpose: it is shared with the judge cache,
which is keyed per ANSWER, so a cell's `engine_name` written into it would be
served back to a different cell whose answer text happened to match. Correct. But
`_row_to_judgment` then read those four-key dicts straight through
`flag_from_dict`, which defaults provenance to empty — while the judgments ROW
sitting around them has `query_id`, `engine_name`, `intent` and `run_index` as
actual columns.

So every run **read back from storage** had anonymous flags, permanently,
however it looked live. `build_finding_groups` then did exactly what it was told
and refused to build an evidence bundle without a cell, which stripped the
verbatim prompt, the named model and the date off every card in the report. The
one part of the deliverable that makes a finding checkable rather than
assertable, gone on the only path a client ever sees.

Two stamps, both derivations of data already stored, neither touching the cache:

- `db._row_to_judgment` re-stamps each flag from the row's own columns.
- `reports.build_report` adds `observed_at` from the `query_results` rows, which
  is where the per-cell timestamp lives — the judgments table has none.

Run `ff231808`, unchanged in the database, before and after:

    before   evidence: 0 · engines: (none) · "observed 94 times; predates provenance"
    after    evidence: 94 · 4 surfaces  · "observed in 82 of 104 runs on 2026-06-14"
             anthropic_search / claude-sonnet-4-5-20250929 / 2026-06-14T02:49:35
             prompt: "is the Fort wearable worth it?"

The named models are the **June pins** — `claude-sonnet-4-5-20250929`,
`gemini-2.5-flash` — not the `claude-sonnet-5` / `gemini-3.6-flash` those
surfaces run today. That is `engine_models` off the run row doing its job; a
report that re-derived the pin at render time would have told a client their
answer came from a model that never saw the question.

`test_judgment_row_round_trip` asserted the round trip against an original whose
flags had EMPTY provenance — a shape `judge_results` never produces — so it
passed while the data was being silently narrowed. It now round-trips a
realistic judgment, asserts provenance survives, and separately pins the stored
flag dict at four keys so the cache-safety property stays explicit.

### Gate

`mypy src/` 99 files · `ruff check src/` clean · `pytest tests/` 815 passed,
1 skipped.

---

## Audit packaging Phase 0 + Phase 1: 115 flags become 5 cards — Completed 2026-08-02

The spec's keystone through the end of Phase 1, plus P2-T1 and P2-T3 because the
Phase-1 render needed honest denominators and an honest reason for having no
comparison. Spec: `docs/audit-packaging-spec.md`. Standing rules:
`.claude/skills/audit-packaging/SKILL.md`.

On the real Fort run `ff231808` (115 stored flags, 30 pages of identical cards):

    5 themed findings · 4 Critical · 144 observations
    exec summary a CMO can act on · 4 priority actions with owner + effort
    no letter grade anywhere · every rate as "51 of 180", CI 19-40%

### Adding CRITICAL to `Severity` invalidated the entire judge cache

`judge.py` built its tool schema with `[s.value for s in Severity]`, so appending
a fourth tier changed the prompt fingerprint and every cached verdict became a
miss. `test_judge_prompt_fingerprint_is_pinned` caught it on the first full run.

The fix is a seam, not a revert: `JUDGE_SEVERITIES = ("high", "med", "low")` in
`models.py` is now what the schema reads, frozen and deliberately NOT derived
from the enum. The report has four tiers; the judge keeps its three. `critical`
is derived in `src/pipeline/severity.py` from `(flag_type, claim)` — which is
free, testable, and re-runnable over already-stored runs, none of which is true
of asking the model. `tests/test_judge.py` now pins the prejudge JS to
`JUDGE_SEVERITIES` rather than to `Severity`, so the two can't drift back.

Two downstream tests changed and both got *stronger*: `factsheet/gate.py` gained
a deliberate policy row for `critical` (sendable on a confirmed sheet, suppressed
on `public_source_only`), and the "unrecognised severity is refused" test lost
`critical` from its list but gained an explicit assertion that it is refused on
an unconfirmed sheet. The refuse-by-default that made the transition safe is the
behaviour that test was protecting.

### Cards are THEMES, and that was worth 49 cards

Grouping on `(theme, cluster_id)` as first written produced **54 cards** from the
Fort run — the blob the work exists to remove. The spec's own acceptance settles
it: the Fitbit / pickleball / "not a recognized brand" flags must land in ONE
group, and they cluster apart because they share almost no tokens. So the card is
the theme; `member_cluster_ids` keeps the per-claim identity one level down for
the lifecycle engine. That also fixes the counting unit — the number of cards IS
the number of themes, which is what page 1 counts.

### The similarity threshold is 88, and the numbers in the docstring are measured

`token_set_ratio` alone scored **P=0.57** on `tests/fixtures/labeled_pairs.csv`
(72 hand-labeled pairs): "costs $349" vs "costs $289" share every token but one
and score 93. Two wrong prices are two findings, and merging them hides the
second from the client where they cannot see it happened.

`numeric_discriminators` fixes it — claims whose numbers disagree score 0.0
regardless of how alike they read, worth **+11 points of precision** and costing
no recall by construction. At the precision knee (86 → 88 buys 0.07 of precision
for 0.08 of recall) the shipped numbers are **P=0.800 / R=0.667**, and those are
the numbers in the docstring rather than aspirational ones. Read the precision as
a floor: the fixture's negatives are adversarial minimal pairs, and a real run's
non-duplicates are about different subjects entirely. `test_finding_id.py`
re-runs the sweep as a gate.

The fixture is 72 rows against the spec's 150–300. It should grow from real runs.

### Three bugs the tests didn't find but the real data did

**"The models described Fort accurately"** — on a run with no fact sheet. Zero
findings looks identical whether nothing was checked or everything checked out,
and they are opposite claims. The summary now names the gap.

**"Observed in 4 of 4 runs"** — on legacy flags that carry no provenance at all.
Rounding `total` up to `observed` asserted perfect reproducibility off a run that
recorded no cells. It now says "observed 4 times; this run predates per-answer
provenance", and ranking treats unknown breadth as one surface rather than zero
so a real Critical doesn't sort below a Low.

**A stale ship date filed under "weak sources"** because the sentence said
"according to". The rule set had no ship-date pattern at all — the single most
common lifecycle error the engines make about a pre-launch product — so 94
observations fell through to whichever general rule matched the surrounding
prose. Adding it and moving `source.citation_quality` last dropped the
type-default rate from **0.40 to 0.042**.

### `n_eff`, not raw n — and scale both sides or you get nonsense

`src/pipeline/stats.py` is hand-rolled on `statistics.NormalDist`, zero new
dependencies. The first version deflated `n` by DEFF without deflating the
numerator, which drove `p_hat` above 1 and produced "50% is between 47% and
100%". `wilson_interval` now raises on `successes > n` rather than clamping, and
`newcombe_diff_interval` takes raw counts and applies the correction itself so
the misuse isn't available. At K=3 and ICC 0.68 a 51/180 rate is **19–40%**, not
28%.

### Also landed

`--sky` exists only inside `.on-navy`, verified in the browser: `#7fa6d9` on the
masthead, **the empty string** on paper. The constraint is a missing-variable bug
rather than a design-review argument. Severity is the monochrome navy ramp with
an icon and a label on every tier, which is load-bearing on a single-hue ramp.

`web/app/audits/[id]/page.tsx` read `params.id` directly. Under Next 16 `params`
is a Promise, so `runId` was `undefined`, the page polled `/audits/undefined/status`,
404'd and sat on "Loading…" forever — the report was unreachable in the running
app. `tsc` passed because the annotation asserted the wrong shape; only loading
the page found it.

### Not built, deliberately

**P1-T7/T8 (print pipeline, lazy-load audit)** — needs the Playwright worker;
`break-inside` and the print forks are stubbed in `sable.css` and the evidence
block already renders eagerly under `print:`. **P2-T2 (lifecycle)** — the
"oldest still open" tile renders `—` and says why; `member_cluster_ids` is the
unit it will track. **P2-T5/T6 remainder** — the accountability line, bump chart,
paired bars and Pareto all need a prior comparable cycle, which no stored client
has yet. **Phases 3–5** untouched.

### Gate

`mypy src/` 99 files · `ruff check src/` clean · `pytest tests/` 813 passed,
1 skipped · `tsc --noEmit` clean · `next build` clean · report verified rendering
against run `ff231808` in the browser.

---

## Engine repin: the six-surface search set — Completed 2026-08-01

Three surfaces repinned, one adapter rewritten, `runs_per_query` cut to 3, and the cost
model corrected from measurement rather than estimate. Spec: `docs/engine-repin-spec.md`.
Judge untouched — `JUDGE_MODEL` stays `claude-sonnet-4-5-20250929`.

    anthropic_search  claude-sonnet-4-5-20250929 -> claude-sonnet-5
    openai_search     gpt-5-search-api-2025-10-14 -> gpt-5.6-luna + Responses web_search
    gemini_grounded   gemini-2.5-flash -> gemini-3.6-flash
    perplexity / google_ai_mode / google_ai_overviews   unchanged

### openai_search was a rewrite, not a repin

The old pin was a Chat Completions specialized model capped at **6,000 TPM** on this
account against a ~17,230-token call — it answered **0 of 10 cells, twice**, and was
excluded from the local template because of it. The Responses `web_search` tool bills
against the **calling model's** limits instead: Luna is 500,000 TPM / 500 RPM at Tier 1.

Three things had to land together or the rewrite delivers nothing:
`PROVIDER_CONCURRENCY_OVERRIDES["openai_search"] = 1` removed from `prompt_runner.py`
(it would have kept the surface serialized no matter what model it called), the surface
added back to `local_templates.py` **and** `assemble.DEFAULT_LOCAL_ENGINES` (two copies of
one decision — the spec named only the first), and `test_engine_routing.py`'s
"openai_search is absent on purpose" assertion rewritten, which the spec also missed. That
test now asserts the two engine lists match each other, so the copies can't drift again.

`requirements.txt` moved to `openai>=2.38.0` — the verified floor, not a guessed one;
`1.30.0` predates the Responses API entirely.

### `store: False` is the isolation rule, not a breach of it

`FORBIDDEN_STATE_PARAMS` in `tests/test_isolation.py` contains `store`, written against a
Chat Completions world where the param appearing at all meant "keep this". The Responses
API retains by default, so an explicit `store: False` is how an engine **refuses**
retention. Resolved with a shared `_forbidden_state_params()` helper that discards `store`
only when it is present-and-False — used by **both** assert helpers, so neither is
weakened, and present-and-truthy is still caught. `base.py`'s statelessness docstring now
says `store: true` and explains why the explicit false is the strengthened form.

### The cost model was wrong in the expensive direction

The spec's figures were estimates; this run measured them (n=3, three query shapes, real
API calls) and they came out **~80% higher**:

    surface            spec est.   MEASURED   why
    anthropic_search      0.037      0.064    18,171 in / 1,123 out / 1.7 searches
    openai_search         0.014      0.041    31,098 in / 1,199 out / 3.3 tool calls
    gemini_grounded       0.011      0.016    2,046 billable out (thinking bills as out)
    -----------------------------------------------------------------
    engine spend / audit  $5.52     $10.02    25 queries x K=3 x 6 surfaces

Two estimate errors, both structural rather than arithmetic:

- **The hosted-tool fee is per CALL, not per request.** OpenAI bills "$10.00 / 1k calls"
  and one answer makes 2-5 of them. That fee alone is 81% of `openai_search`'s cost. The
  spec assumed one.
- **The 2026-07-30 `anthropic_search` figure was n=1 and was correctly flagged a floor —
  it was one.** The n=3 mean is 66% higher on input and 2x on output. Repinning to Sonnet 5
  cut the token rate by a third and the real token profile more than ate the saving.

`anthropic_search` **expires 2026-09-01**: Sonnet 5's introductory $2/$10 ends and the same
measured profile costs ~$0.088. `gemini_grounded` is **tiered** — free for the first 5,000
search *queries*/month shared across all Gemini 3.x models, then $14/1k. At the measured
2.7 queries/answer a 75-cell audit burns ~200, i.e. **~25 audits/month** before that line
becomes ~$0.053/call.

### §6 checked: the spend guard is not double-charging prejudged runs

`JUDGE_COST_PER_CALL` 0.003 -> 0.0098 multiplies the full cell count, so on a 450-cell run
the judge component moves $1.35 -> $4.41. Verified where that lands:
`estimate_total_cost_for_queries` has exactly one caller (`api/runner.py:313`) and it
passes `cfg.judge`, which `csv_loader` defaults to **False**. The CLI path uses
`estimate_cost_for_queries`, which has no judge component at all. So a run headed for
prejudge sees $10.02, not $14.43 — **no code change needed**. Both sit under the $25 cap,
but the margin is now 1.7x rather than the 3.6x the spec projected.

### runs_per_query 5 -> 3

Both places, or the two paths disagree: `settings.py` and `local_templates.py`.
`assemble.py` and `csv_loader.py`'s consumer template were already 3.

The K=5 justification comment is rewritten to record a **decision**, not a finding — the
2026-06-19 and 2026-07-28 determinism measurements still argue for K=5 and are kept
verbatim in past tense. What K=3 accepts: this set is entirely retrieval surfaces, where
the noise K exists to average is *higher*, and one flipped run now moves a query 33 points
instead of 20. Taken as a cost/breadth trade — 25 queries x 3 rather than 15 x 5 at
identical cell count. `local_sampling.py`'s module docstring updated to match.

### Liveness — all six surfaces answer

One real query, K=1, every surface returned text:

    anthropic_search  claude-sonnet-5    2458 chars   4 citations
    openai_search     gpt-5.6-luna       3902 chars   6 citations   <- the point of §2
    gemini_grounded   gemini-3.6-flash   4810 chars  10 citations
    perplexity        sonar              1883 chars  20 citations
    google_ai_overviews (DataForSEO)     2113 chars   6 citations
    google_ai_mode      (DataForSEO)     5278 chars  22 citations

`gemini_grounded` still sends `temperature=ENGINE_TEMPERATURE` and 3.6-flash accepted it —
worth knowing, since Google discourages non-default temperature on the 3.x line.

### Watch items

**`anthropic_search` tool version.** Still `web_search_20250305`. Sonnet 5 supports
`web_search_20260209` (dynamic filtering), and `openai_search` likewise has a dated
`web_search_2025_08_26` beside the `web_search` it now uses. Both would change what the
surfaces retrieve — a separate measured decision, not a drive-by edit.
`test_isolation.py:243` pinning the current value is that guard working.

**perplexity/sonar** — unchanged, but its Chat Completions endpoint is deprecated in favour
of the Agent API. Same failure class as the dead OpenAI pin; preflight will catch it.

**Repin timing.** All three landed together, at a cycle boundary. Answers captured under
different pins are not comparable cycle-over-cycle — a client's apparent "movement" across
this date is partly our own churn.

### Gate

`mypy src/` 93 files clean · `ruff check src/` clean · `pytest tests/` 633 passed,
1 skipped · six-surface liveness green · cost figures measured, not estimated.

---

## F4: the fact-sheet gate is reachable — Completed 2026-07-31

Before this, the worker could fill a table nobody could act on. `save_fact_sheet` always
writes `DRAFT`, `activate_fact_sheet` existed, and **nothing called it** — so an automated
generator produced a pile of drafts that no human could approve and no run could use.

### The gate

Four endpoints on `src/api/app.py`, mirroring the `/teasers` lifecycle:

    GET  /fact-sheets?state=&domain=   the queue (rows, not documents)
    GET  /fact-sheets/{id}             one sheet WITH each claim's evidence
    POST /fact-sheets/{id}/approve     DRAFT -> ACTIVE, incumbent demoted
    POST /fact-sheets/{id}/reject      records the verdict; the row stays

Plus `web/app/fact-sheets/page.tsx` and a nav entry.

**The design rule is that a reviewer must be able to CHECK a claim, not just read it.**
Every claim renders its verbatim quote and a link to the page it came from, beside the
assertion it produced. Open questions render first, in their own block, because the §4.3
disagreements are the call list — the reason a human is in the loop at all.

### Three decisions worth recording

**`rejected` is a REVIEWED state, not a delete.** `data/schema_factsheets.sql` (still
unapplied, so this cost nothing) gained `rejected` to the state check plus a
`reject_reason` column. A reviewer saying "these claims are wrong" is the most valuable
signal the extractor gets — it means L1 produced something plausible-but-false on that
domain. Deleting the row teaches nothing and lets the next regeneration repeat the mistake
unobserved.

**An ACTIVE sheet cannot be rejected — 409.** Live runs are judged against it, and pulling
it out from under them leaves their accuracy claims referencing a document that no longer
exists. Activate a replacement instead; `activate_fact_sheet` already demotes the incumbent
in the same operation, because `uq_fact_sheets_active_domain` refuses promote-before-demote.

**An unknown `state` filter is 422, not an empty list.** Silently returning `[]` for a typo
reads as "no sheets need review", which is the wrong answer to put in front of a reviewer.

### A4 is still open, and this was built around it

`audit-packaging-research.md` §9.5 binds the fact sheet and the competitor set into one
governance artifact; this plan has no competitor-set plan, and the decision changes what
the queue gates. Built to gate the SHEET only, with the second artifact additive rather
than a rewrite — but if §9.5 is adopted, this screen gains a second panel and the approve
action gains a second subject.

### Gate

`mypy src/` 91 files · `ruff check src/` clean · `pytest tests/` 563 passed, 1 skipped ·
`tsc --noEmit` clean · `next build` compiles `/fact-sheets`.

---

## The fact-sheet cue: an invariant amended, a worker built — Completed 2026-07-31

The fact-sheet queue had no producer and no consumer. `enqueue_factsheet_job`,
`claim_factsheet_job` and `finish_factsheet_job` all existed in `db.py`, and grep found
exactly one file mentioning any of them: `db.py`. A sheet existed only if someone typed
the CLI command.

### The invariant came first, deliberately

`geoWebsite/CLAUDE.md` said *"No auto-triggering of the teaser pipeline."* Plan §0 is
explicit that Tier-1 auto-generation is *"arguably inside that prohibition"* and needs an
**explicit amendment in the same commit**, not a silent reading that fact-sheet generation
is not "the teaser pipeline." So the amendment is written, and it is narrow:

- The teaser prohibition is **unchanged**. Only Tier 1 is carved out.
- Tier 1 crawls the lead's OWN site and parses it. No model, no engine spend, and the
  output is a `draft` nothing may send until a human reviews it. The rule the invariant
  protects — nothing reaches a prospect without a person deciding — is untouched, because
  a fact sheet reaches no prospect.
- Tier 2 (which does call models and does spend) is **explicitly not covered** and needs
  its own amendment.

### Why a worker and not a trigger

Not a preference — a fact about the deployment. `leads` lives in the website's Supabase
project, `factsheet_jobs` in the platform's. **Different databases**, so the existing
`AFTER INSERT` trigger physically cannot enqueue. The `pg_net` alternative needs the
platform API hosted and `run-api.sh` is localhost. Polling is the only bridge that works
today (§12.1/§12.3).

### `src/audit/factsheet/worker.py`

`geo factsheet-worker [--limit N] [--max-jobs N]` — one pass per invocation, so scheduling
stays outside the process. A daemon owning its own clock is harder to stop, and this reads
a queue of real prospects.

Read leads → enqueue Tier 1 → claim → crawl → extract → store DRAFT → finish.

**No prospect PII crosses projects.** The SELECT names five columns and `email`/`phone` are
not among them — the cheapest guarantee is never loading them. `LeadRow` has nowhere to put
them either, so widening it would be a deliberate act rather than an accident of a wider
query. Two tests assert both.

**Every job reaches a terminal state**, the skips included. A job neither run nor recorded
is a spend decision nobody can audit, and it never releases its domain — the in-flight
unique index only covers `queued`/`running`. Thin text is `SKIPPED_UNUSABLE`, not `FAILED`:
refusing it is the extractor working (§4.6), and filing it as failure would make a healthy
worker look broken and bury the real ones. Crawl errors log the exception TYPE only; an
error message can echo page content and this runs unattended against a stranger's site.

`LEADS_DB_URL` uses the SELECT-only `leads_reader` role from
`geoWebsite/scripts/leads-visibility.sql` — never the superuser, never the service_role key.
Unset raises rather than reporting "no leads": an unattended worker that looks healthy while
doing nothing is the failure mode to design against. psycopg stays an optional extra with an
install hint, matching `apply_schema.py`.

### Also landed this session

**Migration applied.** `python -m scripts.apply_schema data/schema_run_provenance.sql` —
`fact_sheet_id`, `fact_sheet_version`, plus `judge_model` and `location`, which had been
backed up and unapplied since 2026-07-28. Verified readable.

**P0-T1 provenance, cache-free.** `AccuracyFlag` gained `query_id`/`engine_name`/`intent`/
`run_index`, stamped per-cell at the join in `judge_results`. The trap: verdicts dedup by
`(prompt, answer)`, so one flag list is shared across every cell whose answer text matched —
stamping upstream would attribute a Gemini error to Perplexity. `flag_to_dict` still emits
four keys, so **no cached verdict was invalidated and no judge prompt moved.**

**F3.** `selectAccuracyFindings` behind three gates: send permission by sheet tier
(`factsheet/gate.py`, §8), provenance present, and a verbatim answer to quote. The
`"accuracy_flag"` arm of `Finding.source` is no longer dead. The teaser's OUTPUT is
unchanged — nothing renders `accuracyFindings` and nothing populates
`fact_sheet_verification` yet, both of which are F2.

### Still not built

- **F4 — SHIPPED, see the entry above this one.**
- **F2** — the run→sheet join, so `fact_sheet_verification` stops being null. Until then F3 returns [].
- **A renderer** for accuracy findings, plus its copy.
- **`data/schema_factsheets.sql` is unapplied** — the worker's tables do not exist yet in the live database.
- **A2** (JSON-LD coverage across ~10 real trade sites) is still Josh's run.

### Gate

`mypy src/` 91 files · `ruff check src/` clean · `pytest tests/` 553 passed, 1 skipped ·
teaser 194 tests, `tsc --noEmit` clean.

---

## Fact-sheet generation is reachable: F1 gets an entry point — Completed 2026-07-31

F0 (the `FactClaim` contract + both renderers) and F1 (L0 lead-form + L1 JSON-LD/NAP
extraction, `build_sheet`) were both written, tested and **unreachable**. Nothing in the
CLI, the API or the teaser called `build_sheet`. The plan's F1 acceptance — *"on 8-10 real
trade sites, produce a sheet with zero LLM calls"* — could not be attempted, because there
was no way to run it on one site.

### What was wrong

**The package said it did less than it did.** `src/audit/factsheet/__init__.py` still
described itself as *"the contract ... and nothing else"* and re-exported only `models` and
`render`. `extract.py` — 1,000 lines including the orchestrator — was in the package but
absent from `__all__`, so `build_sheet` was reachable only by importing the submodule.

**A test asserted the opposite of the code.** `test_provenance_cells_survive_a_quote_containing_a_pipe`
counted raw `|` characters and expected 6. `render._cell` escapes pipes by design, so the
one input the test exists for — a quote containing `|` — produces 7 and failed. The
escaping was right and the proxy was wrong: the test now counts *unescaped* delimiters
via `(?<!\\)\|` and additionally asserts the escape is present.

**A type error was masked.** Adding the extract re-export brought `extract.py` into mypy's
graph and surfaced `derive_negative_claims` rebinding the loop variable `claim`
(`FactClaim`) to `_claim(...)`'s `FactClaim | None`. Renamed to `negative`; the guard was
already correct, only the name was.

### The entry point

`geo factsheet <website> --business NAME [--area] [--description] [--kind] [--out] [--csv]`

Crawls the domain, runs L0+L1, renders markdown and/or platform CSV fact rows. No model is
called and none may be added. A `ThinTextError` is reported as a refusal with exit 1 — a
sheet built from a Cloudflare interstitial asserts things no page ever said, and refusing
is the feature (§4.6). Output is labelled DRAFT and every claim renders UNCONFIRMED, because
a fact sheet is what the judge measures answers against: a wrong line is not a missing
finding, it is a false accusation in a document we send a stranger.

**`crawl_domain` / `run_site_audit_blocking` gained `persist: bool = True`.** A standalone
sheet has no parent `audit_runs` row, so every `cache.save_page` would fail its foreign key,
land in `save_errors` and log a warning — a crawl that was never meant to be stored reading
as a broken one. The pages are returned either way; only the write is skipped.

### Verified live

`geo factsheet fort.cx --business Fort --kind product` — 3 pages fetched, 3 usable, 0
errors; 3 claims (2 L0, 1 `mailto:` via L1), 0 questions, weakest verification
`public_source_only`; provenance appendix cites `urn:geo:lead-form` and `https://fort.cx/`.
Thin for a pre-launch product site with no `LocalBusiness` markup — which is what §13.2
predicts and what the unmeasured JSON-LD coverage question (A2) is about.

### Still blocked, not built

- **A2** — JSON-LD coverage across ~10 real trade sites is unmeasured. `scripts/measure_jsonld_coverage.py` exists; the run is Josh's.
- **A3** — does F3 happen (`selectFindings` reading `accuracy_flags`)? Undecided. Without it F2 changes nothing a client sees.
- **A4** — competitor-set governance is unplanned, and it changes what the F4 queue screen gates.

F2 (teaser CSV emitter + `TeaserDraft` persistence) is unblocked by decision but pointless
before A3 resolves. F4 waits on A4.

### Gate

`mypy src/` 89 files clean · `ruff check src/` clean · `pytest tests/` 516 passed, 1 skipped.

---

## Report provenance: the methodology section now describes the run — Completed 2026-07-28

`scripts/render_report_md.py` hand-typed the two facts a client is most entitled to trust:

    "every answer scored by one held-constant `gpt-4o` judge"
    "Determinism. Temperature pinned to 0; 1 run per query this cycle"

By 2026-07-28 all three claims were false. JUDGE_MODEL had been `claude-sonnet-4-5` for
months; `openai` is pinned to a model that *rejects* `temperature`; and RUNS_PER_QUERY
defaults to 5. Nothing calls that script today, so nothing had caught it — but it is the
renderer for a client deliverable, and a wrong methodology section is worse than none.

The fix is not a string swap. Every one of those facts now comes from the stored run.

### Where each fact now lives

**Sampling → the engine that owns it.** `BaseEngine.SAMPLING` is `"pinned"` (sends
ENGINE_TEMPERATURE) / `"default"` (sends none — the provider rejects it, or this adapter
never sent one) / `"none"` (SERP capture, no model to sample). `tests/test_isolation.py`
asserts the declared label against each engine's **real captured payload**, so the label
can only ever be as wrong as the request itself.

Declaring it surfaced a fact nobody had written down: `anthropic_search` sends no
temperature either. Not a repin casualty — that adapter never sent one. It was an
unpinned surface with no written reason, and now it has one.

**Judge → recorded when the verdicts are saved.** New `judge_model` column on
`audit_runs`, written by `db.save_judgments` from `Judge.identity`. Three deliberate
choices:

- *Identity, not model.* Cascade and verifier configs change the verdict, so they are
  part of who judged. It is the same id the cache keys on.
- *At save time, not run creation.* A run is routinely judged later (`geo judge <run_id>`)
  by a different model than was configured when it started.
- *`None` never overwrites.* `scripts/judge_new_gemini.py` saves a MIXED set — verdicts
  from two judges — so it passes nothing rather than stamping one identity over both.

The write is the only place in `db.py` that degrades instead of raising: the verdicts are
already committed, so failing there would report a successful save as a failure. It also
fails cleanly on a database predating the column — losing provenance (recoverable) rather
than the run (not).

**Report → says "not recorded" when it doesn't know.** `build_detailed_report` emits a
`provenance` block read off the run row; `render_report_md` renders it and never reads
`settings`. Settings describe the machine now; a report describes one measurement then.

The sharpest case is a repin. `sampling_for(engine, run_model)` returns None when the
stored model differs from the adapter's current pin — the regime *then* cannot be
asserted from the adapter *now*. Rendering the stored Oura run:

```
- `openai` — `gpt-4o-2024-08-06`; sampling regime not determinable — this engine has
  been repinned since the run, so today's setting may not describe it
- **Judge.** One held-constant judge (**model not recorded for this run** — JUDGE_MODEL
  is configurable, so it cannot be inferred after the fact)
```

That is the correct output. Substituting today's config would have re-created the exact
bug being fixed, one layer deeper and much harder to notice.

Also fixed while in there: `**Engines:** ... (4)` hardcoded the count, and a
`.capitalize()` was quietly lowercasing `JUDGE_MODEL` to `judge_model` mid-sentence
(`sentence_case` now uppercases the first character only).

### Requires one migration

`data/schema_ui.sql` gained `alter table public.audit_runs add column if not exists
judge_model text`. **It has not been applied** — the Supabase MCP is authed to a different
account than this project's, and `.env` carries no direct Postgres credential, only the
REST key (which cannot run DDL). Until someone runs that line, new runs log a warning
naming it and every report reads "judge model not recorded". Nothing else breaks.

### Gate

mypy clean (84 files) · ruff clean (`src/`, `scripts/`) · pytest **418 passed, 1 skipped**
(14 new) · `tsc --noEmit` clean.

---

## Verdict stability + a re-measured noise band — Completed 2026-07-28

Follow-up to the model repin. `openai` is now pinned to a model that rejects
`temperature` outright, so one surface in every run samples at its default while the
rest hold ENGINE_TEMPERATURE=0. Two things needed checking: whether the K=5 default
still holds, and whether the report can even tell a stable verdict from a coin flip.

### The noise band was stale — and the measurement falsified half of it

`settings.DEFAULT_RUNS_PER_QUERY` and `local_sampling`'s docstring both cited the
2026-06-19 baseline: *"the brand READ is 100% stable on openai/anthropic"* — measured on
gpt-4o at temperature 0, an engine no longer in the run. Re-measured with
`scripts/run_determinism.py --k 5 --engines openai,anthropic` (one category query):

```
text-level    openai  unique=5/5  modal-agreement=20%   anthropic  unique=4/5  40%
label-level   openai  min=60% mean=80%                  anthropic  min=60% mean=92%
              -> both suggest runs_per_query=5
```

**K=5 survives.** But "100% stable" did not reproduce for *either* engine: both floor at
60% worst-brand. Anthropic is still at temperature 0 and shows the same floor, so the
wobble is **not** an artifact of the repin — the original figure was optimistic. The
repin's measurable cost is the mean (80% vs 92%), not the floor.

The text-level numbers are the reminder of why label agreement is the metric: the temp-0
engine scored 40% and the temp-1 engine 20%, which would have "shown" a catastrophe where
the brand read moved barely at all. `determinism.suggest_runs_per_query` already carries
that warning in its docstring; this is the run that demonstrates it.

Caveat written into the comment, not just here: one query at k=5 is a probe, not a
baseline. Do not quote 60% as the noise band until it is run across the query set.

### The report could not distinguish 5-of-5 from 3-of-5

`metrics.CellVerdict` had carried `hit_runs` / `answered_runs` since the cell aggregation
was written, and **nothing in `src/` ever read them** — every consumer took the collapsed
majority `hit`. On the judge path it was worse: `BrandCell` discarded the run counts
during the collapse, so the evidence did not survive at all. A cell the client won 3 times
out of 5 rendered identically to one it won 5 times out of 5.

Now: `metrics.stability_from` is the shared pure core, with `metrics.stability` /
`stability_by_engine` on the regex path and `judge_metrics.stability` /
`stability_by_engine` / `split_cells` on the judge path — same scale, so the two can
never disagree. `BrandCell` gained `runs` / `agree_runs`, counting agreement on the whole
(present, prominence, framing) label: a cell can agree on presence while its prominence
wobbles, and the report shows prominence, so that is a split read.

Surfaced in all three places a run is read: `ReportPayload.stability` (per engine), a
"Verdict Stability" section in the judge markdown report listing the split cells worst
first, and a card in the web report view.

**Per engine, deliberately.** The engines no longer share a sampling regime, so one
run-wide agreement figure would average a deterministic surface against a sampling one and
describe neither.

The Coverage lesson is re-applied throughout: a cell with one answered run *looks*
unanimous while comparing nothing, so cells below `MIN_RUNS_FOR_STABILITY` are excluded
from the denominator and `is_measured` goes False. An engine with no repeated cells emits
no row at all rather than a row of zeros — absent means "not repeated", never "stable".
Unanswered runs are excluded too: an engine failure is missing data, not disagreement.

### Gate

mypy clean (84 files) · ruff clean (`src/`) · pytest **404 passed, 1 skipped** (10 new) ·
`tsc --noEmit` clean.

Known-stale, not fixed here: `scripts/render_report_md.py` still hardcodes "one
held-constant `gpt-4o` judge" (JUDGE_MODEL has been `claude-sonnet-4-5` for some time) and
"Temperature pinned to 0", which is no longer true of `openai`. Nothing calls that script
today, but both lines are client-facing methodology copy and should be read from the data
blob rather than retyped.

---

## Crawl politeness + Cat 3/4 judged checks finally produce verdicts — Completed 2026-07-28

The follow-through on the classification fork: re-run the audit, turn on the content
judge. The re-run immediately exposed a second bug the fork had been masking.

### 2 pages -> 20 pages -> 14 of them ungradeable

The classification fix worked (2 -> 20 pages, 21 -> 147 checks) and then 14 of the 20
came back `ungradeable` on schema, headings, alt-text and fact-density. A site audit
reporting nothing about two thirds of the site is not an improvement, so it got chased
rather than written up as a win.

Cause, at `crawl.py`:

    gate = asyncio.Semaphore(1 if delay else cfg.max_render_concurrency)

`max_render_concurrency` is a MEMORY bound for headless Chromium (~1GB/slot) and was
being reused as the HTTP request-rate bound. No pause applied at all unless robots.txt
specified a Crawl-delay, which this site does not. So a 20-page crawl hammered a small
WP Engine host, it returned 429, and the 1.1 KB error body scored as "ungradeable".

At 2 pages this never surfaced. The fork is what made the crawl big enough to trip it.

### Measured before changing anything

| configuration | pages HTTP 200 |
|---|---|
| 3 concurrent, no delay | 6/20 |
| 2 concurrent, 0.75s pause (~2.7 req/s) | 6/20 |
| serial at ~2s spacing (targeted probe) | 3/3 |

Also checked whether it was AI-crawler discrimination — it is **not**. The same URLs
behaved identically under a browser UA, so it is a pure rate limit and the fix is to go
slower rather than to disguise ourselves.

`fetch_concurrency` (default 1) split from `max_render_concurrency`; `polite_delay_s`
(1.5s) applies with or without a robots Crawl-delay; `rate_limit_floor_s` (2.5s) so a 429
with no Retry-After stops retrying on the generic 0.5s curve, which was an immediate
second 429 that burned the retry for nothing.

Verified on hosts NOT used for diagnosis: **Afterglow 15/15 pages with usable text (45s),
Plumbing Care 10/10 (31s)**. `albertnahmanplumbing.com` still 429s, but that host absorbed
100+ requests during diagnosis today, so its current state is not a clean read on the new
defaults — recorded rather than glossed. The flip side is worth selling: a site that
rate-limits this hard IS a Cat 1 accessibility finding, because GPTBot cannot read it in
one pass either.

Cost: an audit crawl goes from ~10s to ~45s. Correctness over speed for a bot that
identifies itself as GPTBot.

### Cat 3/4 judged checks, first real verdicts

`RUN_CONTENT_JUDGE=1` against the clean 15-page crawl produced **90 verdicts**:

| check | verdicts |
|---|---|
| `answer_first_lead` | 6 pass · 6 partial · 3 fail |
| `self_contained_chunks` | 13 pass · 1 fail · 1 unknown |
| `definition_first` | 12 fail · 3 pass |
| `expert_commentary` | 10 fail · 5 partial |
| `original_data` | 10 partial · 5 fail |
| `external_citations` | 12 fail · 3 unknown |

Cat 3's judged half (first three) and Cat 4's (last three) both populate for the first
time. ~$1 on the API; the re-run cost $0 because the content-judge cache is
content-addressed. The `/prejudge` subscription path remains available for iteration.

**These numbers are internal-only.** The judge has still never passed the κ>=0.6 gate
(`content_calibration.py` is built; no gold set is labeled), so the distributions are
plausible but unvalidated. That is now the single remaining blocker on Cat 3, and it needs
human labeling rather than code.

`RUN_CONTENT_JUDGE` stays `False` by default — enabling it is a spend decision.

### The ordering this validated

Fix coverage -> judge -> calibrate. Had the judge been switched on before the
classification fork, it would have scored a homepage and a blog index; had the gold set
been labeled then, the κ gate would have certified the judge against a sample
unrepresentative of the sites it scores.

### Gate

mypy clean (84 files) · ruff clean · pytest **390 passed, 1 skipped** · teaser 168 ·
`tsc --noEmit` clean.

---

## Local URL classification — Cat 3/4 were auditing 9% of a trade site — Completed 2026-07-28

Chasing "how do we fix Cat 3" found the answer was neither the feature flag nor the
calibration gold set. It was the crawler.

### The measurement

Probed all 20 businesses captured from Berkeley's local pack. Access is NOT the problem:
GPTBot gets a 200 from 18 of 20, and only 2 are hard-blocked. `albertnahmanplumbing.com`
— which an earlier note recorded as edge-blocked — returns 200 and discovers **83 nav
links**. That earlier reading came from a curl with a browser UA, not the crawler's.

The real bottleneck was classification. Across 8 sites, **210 of 221 discovered URLs
classified as OTHER and were dropped** before the page cap ever applied:

```
/hvac/cooling/ac-repair-maintenance/             -> other  (dropped)
/hvac/heating/furnace-installation-replacement/  -> other  (dropped)
/areas-served/berkeley/                          -> other  (dropped)
```

`CATEGORY_PATTERNS` is entirely B2C-SaaS-shaped — /pricing, /vs, /features, /docs, /blog.
A trade site has none of those. So `GLOBAL_PAGE_CAP` is 20 and we were using 1-2 of it,
and Cat 3/4 were judging a homepage and a blog index. **The dropped service pages are
exactly what Cat 3 exists to read**: "is the lead answer-first on your water-heater-repair
page?"

### What was built

`LOCAL_CATEGORY_PATTERNS` / `LOCAL_CATEGORY_CAPS`, FORKED from the consumer set rather
than merged (§0.6) — merging would change which pages a CONSUMER audit crawls, which is
the one thing that rule exists to prevent. New `PageCategory.SERVICE` and `SERVICE_AREA`;
reviews/testimonials map to COMPARISON as the local trust surface. `business_kind` threads
`run_site_audit -> run_site_audit_blocking -> crawl_domain -> select_pages -> classify_url`,
defaulting to today's consumer behaviour everywhere.

A consumer-path regression test asserts `CATEGORY_PATTERNS` and `CATEGORY_CAPS` are
byte-identical and that a trade-shaped path still classifies as OTHER by default.

### The fix's own regression, caught by re-measuring

First cut made one site WORSE: Berkeley Plumbing 9 -> 6. Its site is nearly all
`/articles-about-*`, so it hit the local BLOG cap of 3 and stopped at 5 pages while 8
auditable ones sat unused. The caps were doing their job as priority but leaking budget.

Added a local-only backfill: once the capped pass finishes under `GLOBAL_PAGE_CAP`,
remaining candidates fill the rest in the same priority order. Deliberately NOT applied to
the consumer path — that would change how many pages an existing consumer audit crawls,
and therefore its cost, which is a decision to take rather than a side effect.

### Result

```
site                   before   after
Albert Nahman               2      20
Afterglow                   1      15
Plumbing Care               2      10
Berkeley Plumbing           9       9   (regression fixed)
EO Plumbing                 1       7
Pipe Spy                    2       9
TOTAL                      19      72   3.8x, no site worse than before
```

Green Eagle and J J Rooter stay at 1: their sites genuinely have 8-11 discoverable links
and almost no service URLs. That is a real property of those sites, not a classifier gap.

### Why this had to come first

Turning on `RUN_CONTENT_JUDGE` or labeling the Cat 3 gold set would both have calibrated
against a homepage and a blog index. The ordering is: fix coverage, then judge, then
calibrate — otherwise the κ≥0.6 gate certifies a judge against a sample that is not
representative of the sites it will score.

### Gate

mypy clean (84 files) · ruff clean · pytest **390 passed, 1 skipped** · teaser 168 ·
`tsc --noEmit` clean.

---

## Local report renderer + teaser local path wired — Completed 2026-07-28

The two gaps between "everything measures correctly" and "there is something to sell".

### The local report exists as code now

`docs/report-template-local.md` was a spec with no renderer — `reports.py` and
`query_report.py` had no local variant at all, so the `local_pack` payload was captured,
persisted and served while nothing displayed it. `src/audit/local_report.py` renders the
template's six sections, and the six hard rules are enforced in code with a test each,
because a comment is not enforcement:

1. **No aggregate appearance ratio** — the module never computes one; a test asserts no
   `%` appears anywhere in the output.
2. **Never claim more than the judge measured** — `_competitor_verb` grades every verb
   off judged prominence, mirroring `competitorVerb` in `copy.ts`. Parametrised over all
   four prominence values, asserting "recommends" cannot appear below
   `recommended_first`.
3. **Never name an uncaptured competitor** — `_rival_is_captured` gates every rival name
   against the local pack. Tested from both sides: a judged-but-uncaptured rival is
   dropped, and a longer Google listing ("LemonTree Plumbing, Heating & Drain") still
   matches the shorter name an engine said.
4. **No accuracy FIGURE until W3.4** — the flags render with their verbatim evidence
   (that is the point of §4) but no rate appears and the section says it is uncalibrated.
5. **No reproducibility claim without the runs** — printed only when every observed run
   confirms, and always beside `sampling_note(trade)`, which currently says the band is
   not established.
6. **Print the location, always** — `render_local_report` RAISES without one rather than
   describing the wrong market.

Selection is on the stored `location`, which is set only for service-area businesses.
The consumer path is untouched and pinned by a test.

### What it produces on the real Berkeley run

```
Asked "top rated drain cleaning in Berkeley", perplexity recommends
J J Rooter & Plumbing — and does not mention Albert Nahman Plumbing.
...
- "top rated drain cleaning in Berkeley" — Albert Nahman Plumbing ranks #2
```

Second in the map pack for that query, absent from the AI answer built beside it. J J
Rooter passed the rule-3 gate as a captured entity. That contrast is the product, and it
is now one `geo report <run_id>` away.

### The teaser's local path is wired

`attachLocalCompetitors` and `getLocalEntities` were built, tested, and had **no
production caller** — so `LOCAL_SERVICE_PATH_READY = true` advertised a capability that
did not run, and a local business flowed down the consumer path where the resolver names
rivals from model recall. For a local trade that yields national franchises or
inventions, and a fabricated rival in a teaser emailed to a shop owner is the one failure
that survives human review.

`runTeaserPipeline` now sources local competitors from the captured pack before the
relationship guard, so the human confirm gate reviews the real list. Three tests pin it:
a captured business is the named rival; a local business with no readable location is
refused at the resolve stage rather than captured un-pinned; an empty capture throws
rather than falling back to recall.

### Two things caught by running it

The heading read "looking for a **plumbing** in Berkeley" (trade slug printed raw), and
then "looking for a **local** in Berkeley" — trade inference only read the query-set
version, which a CSV-uploaded run does not stamp. Both fixed: a display-noun map, and
inference from version *or* category with the category as fallback.

### Gate

mypy clean (84 files) · ruff clean · pytest **383 passed, 1 skipped** · teaser **168
passed** · `tsc --noEmit` clean.

### Up next

W3.4 calibration (unfreezes §4 figures) · populate SAMPLING_BANDS from determinism runs ·
`docs/project-queue.md` is a pre-pivot snapshot and should be rewritten or retired.

---

# Build Log

Append-only. Most recent chunk at the top. One entry per chunk, written only after every acceptance criterion passes.

---

## DataForSEO verified live — both parsers were wrong — Completed 2026-07-28

Account verified, both engines captured against real responses, both fixtures pinned.
The verification step was not a formality: **both parsers, written from documentation,
were wrong**, and every unit test passed while they were.

### What the live capture found

`ai_overview` carries the whole answer in top-level `markdown` **and repeats it** split
across `items` (`ai_overview_element`, plus `ai_overview_table_element`). Both parsers
walked every node and concatenated both copies:

| | parsed | actual | error |
|---|---|---|---|
| AI Overviews | 5,601 chars | 2,665 | **2.1×** |
| AI Mode | 8,778 chars | 2,835 | **3.1×** |

An engine answer inflated 2–3× flows straight into mention detection, the judge, and
every rate built on them. Fixed by taking the authoritative top-level `markdown` and
assembling from `items` only when it is absent. Both now match byte-for-byte, with
citations deduped across the overview-level and element-level `references` arrays.

**AI Mode returns the same element shape** — its item is literally `"type":
"ai_overview"` — so `parse_ai_mode` now delegates to `parse_ai_overview`. One verified
parser, so the fix can only ever be made once.

Also learned: AI Mode **requires `location_name`**. The same request with `location_code`
returned zero tasks, and with no location it was rejected outright.

### The swap is justified by measurement now, not argument

AI Mode answered **5 of 5 local-intent queries** and named the client in 4 of them —
the surface AI Overviews returned nothing on, twice (0 of 5, 0 of 5):

```
loc-01 best plumber in Berkeley            4237 chars   client named
loc-02 who is the most reliable plumber…   9159 chars   client named
loc-03 emergency plumber in Berkeley       3285 chars   client named
loc-04 24 hour plumbing service Berkeley   2931 chars   client named
loc-05 top rated drain cleaning…           4344 chars   absent
```

### End-to-end on the recommended stack

Run `86b644f0`, `gemini_grounded · perplexity · google_ai_mode · openai`:

```
cells        : 40 / 40 answered      dead_engines: []
local_intent : mention 20%   coverage 20/20
brand        : mention 100%  coverage 12/12
local pack   : serper_places  client ranks 1,1,3,2,2
engine_models: openai=gpt-5.6-luna  perplexity=sonar  gemini_grounded=gemini-2.5-flash
```

**Every engine answered every cell.** The first run in this sequence (`e186c524`)
answered 11 of 30 with one surface silently dead. Total DataForSEO spend to verify and
run: well under $0.10 of the $1 signup credit.

### One more fix the credentials exposed

`/local-entities` asserted the AI Overviews engine was the SearchApi class. Once that
surface gained a second vendor, the assert became a 500 the moment DataForSEO credentials
existed — DataForSEO captures Overviews but has no local-pack method. The endpoint now
goes through `local_pack.fetch_local_pack`, where it belonged since Phase 5: the two
surfaces were never the same thing, and it gains Serper's richer data.

Engines also now carry `BaseEngine.last_error`, so a provider's own explanation reaches
the run record. The difference in what gets stored when an account is unverified:
*"liveness probe returned no answer (model deprecated, key rejected, or provider down)"*
— three guesses — versus *"HTTP 403 [40104] Please verify your account before using the
API"*, which is an instruction.

### Gate

mypy clean (84 files) · ruff clean · pytest **378 passed, 1 skipped** · teaser 165 ·
`tsc --noEmit` clean.

---

## Model repin + Google AI Mode + Isolation L5 labelling — Completed 2026-07-28

Implements the recommendations in `geo-engine-cost-comparison.html` (28 Jul 2026) and the
considerations listed in its §7. Two of them turned out to be wrong or incomplete once
run against the live API — recorded below, because both change the decision.

### The recommended models

**`openai`: `gpt-4o-2024-08-06` → `gpt-5.6-luna`.** Sunsetting model, ~3.3× the price
($0.0050 → $0.0015/call). Verified live before pinning.

**`google_ai_mode` (new, `src/engines/dataforseo_ai_mode.py`).** The reason for the swap:
AI Overviews is absent from ~85% of local-intent SERPs (0 of 5 measured), so
`engine_routing` skips it there and the Google *answer* surface goes unmeasured at the
buying moment. AI Mode answers every intent → no routing skip, ~100% coverage. The trade
template is now `gemini_grounded;perplexity;google_ai_mode;openai` — 580 cells, ~$3.12
engines-only at runs=5, and **no routed-out cells at all**.

### Two things the cost document got wrong

**1. `gpt-5.6-luna` cannot take `temperature`.** Not "prefers not to" — the API rejects
it: *"Unsupported value: 'temperature' does not support 0 with this model. Only the
default (1)."* Sending `ENGINE_TEMPERATURE` would 400 every call and silently zero the
surface, which is exactly how run e186c524 lost an engine. The payload now omits it and
`tests/test_isolation.py` asserts its **absence**, so a well-meaning "restore the
determinism knob" edit fails in CI rather than in production.

Measured what that costs (5 runs of one category query): gpt-4o at temperature 0 produced
**5/5 distinct answers**; luna at its fixed temperature 1 produced **3/5**, and both named
a stable brand set. **The temperature pin was not buying textual determinism in the first
place.** The real noise control is RUNS_PER_QUERY plus the majority-vote collapse in
`metrics._verdicts`, and that is untouched.

**2. There is no drift control to switch to.** §7 says adopting a 5.6 model "means
finding a different drift control — preflight.py and canary.py are the existing
candidates." Neither works: the canary tests cross-call isolation, not model identity, and
`preflight` records the same alias string across a model change. gpt-5.6-luna also returns
`system_fingerprint: None`, so OpenAI's own backend-change signal is unavailable.
**Drift on this surface is currently undetectable**, and that is written into the pin
comment rather than glossed. Re-pin the moment OpenAI publishes a dated id.

Rather than weaken the L3 guard, undated pins now need a reviewed entry in
`src/engines/model_pins.py` carrying the reason and the loss. The test fails for any
engine that is neither dated nor registered — which also made three pre-existing undated
pins (gemini, gemini_grounded, perplexity) explicit for the first time.

### Considerations from §7, addressed

- **cost.py stale in three places** — all fixed: `openai` 0.01 → 0.0015 (~7× off);
  `openai_search` 0.03 described a dead model; the judge comment said "Haiku-tier" when
  `JUDGE_MODEL` is Sonnet 4.5 and deliberately so (43% vs 95% flag recall — that line
  cannot be cheapened). Two tests that hardcoded prices now read them from
  `ROUGH_COST_PER_CALL`, so a repricing can't break arithmetic tests again.
- **Two teaser defaults disagreed** (`pipeline.ts` vs `teaser/page.tsx`) — a ~2× cost
  spread and *different measured surfaces* depending on which door a prospect came
  through. Both are now `perplexity · openai · google_ai_mode`, with a comment in each
  pointing at the other.
- **AI Mode's three registry entries** — `engineLabel`, `engineColor`,
  `ENGINE_CREDIBILITY` (5, matching AI Overviews), pinned by a test. Without them it
  printed as "Google Ai Mode" in black and scored as undefined.
- **Isolation Layer 5, finally implemented.** `reproNote` promised a prospect "asked N
  times, it held every time" for *any* surface. For a parametric engine that is
  misleading — re-asking mostly re-measures a frozen training snapshot. Added
  `engineSurface()` / `isParametric()` and gated the claim. Chose this over relabelling
  `openai` → "ChatGPT (from memory)", which would have mangled the prose
  ("Ask ChatGPT (from memory) …") while fixing less.

### Not done, deliberately

- **Neither DataForSEO engine is verified against a live response.** Both carry a loud
  UNVERIFIED warning; the `ai_overview` / AI Mode element layouts are undocumented, so
  both parsers walk defensively rather than asserting a schema nobody has seen. Blocked
  on credentials. Until then `google_ai_mode` lands in `skipped_engines` — visible, not
  silent.
- **The audit template's missing judge row.** §7 calls it "possibly unintended". It costs
  real money and changes what a run produces, so it is a decision to take, not a default
  to flip quietly.

### Gate

mypy clean (84 files) · ruff clean · pytest **372 passed, 1 skipped** · teaser **165
passed** · `tsc --noEmit` clean.

---

## Local-pack capture + Serper consolidation (Phases 4–5) — Completed 2026-07-28

Completes the plan whose first half is in the entry below. Phase 3 stopped paying AI
Overviews for local-intent queries; this measures them with the surface that actually
answers them. `SERPER_API_KEY` is now set, which also unblocks Cat 6 —
`configured_tools()` reports `serper: True`, so `reviews_presence()` and the local
report's review-platform checklist can run for the first time.

### Serper vs SearchApi, probed live before a line of parser was written

The 2026-07-27 entry below is why: that bug came from writing a format from vendor docs
and unit-testing our own wrong string. So both vendors were called first, same query,
same market:

| | Serper `/places` | SearchApi `local_results` |
|---|---|---|
| businesses returned | **10** | 3 |
| street addresses | yes | mostly absent |
| phone / website | **yes** | no |
| stable id | `cid` | `ludocid` — **same value** |
| closed flag | **none exposed** | `is_closed` |
| price | ~$0.001/query (2,500 free) | ~$0.02, finite credits |

Serper accepts the location string the repo already stores (`"Berkeley,California,United
States"`, no spaces) **and** the spaced variant. Location binds hard: probing "plumber"
across Berkeley / Oakland / Austin returned three disjoint business sets, so the
wrong-metro failure the W4.2 brief warns about is caught by passing it.

`cid == ludocid` for the same business, so entities join across vendors and the
SearchApi fallback is a real substitute rather than a parallel universe. `LocalEntity`
gained `phone`/`website` (None on the SearchApi path) — both are NAP inputs, and a
listing whose phone disagrees with the fact sheet is a Cat 6 finding.

**The one honest regression:** Serper exposes no closed-business field, so the
`is_closed` guard cannot be enforced on Serper data — the field does not exist to check.
Recorded in the module docstring as a known gap rather than papered over; recommending a
shut-down business is the local twin of `DEFUNCT_BRANDS`.

### What was built

- `src/engines/local_pack.py` — `fetch_local_pack(query, location) -> (entities, source)`,
  Serper first with SearchApi fallback. `None` from a vendor means *failed* (fall back);
  `[]` means *answered, no pack* (don't). Confusing those would pay SearchApi for every
  query that legitimately has no pack, so a test pins it.
- `_run_local_pack_phase` in `src/api/runner.py`, a best-effort daemon thread beside the
  site audit. `_join_site_audit` became variadic `_join_phases` so adding a phase can't
  mean forgetting to join it at one of the three exit paths. Captures each local-intent
  query **once**, not `runs_per_query` — a SERP listing has no sampling noise to average.
- `local_pack_entities` table (applied) + `db.save_local_pack_entities` /
  `get_local_pack_entities` through `_execute`. `on delete cascade` keeps the project
  hard-delete path correct with no code change.
- `LocalPackPayload` on the report, with `client_positions` — *does this shop appear in
  its own city's pack, and where* — plus the TypeScript mirror.
- **Explicit non-goal, tested:** the pack never touches `mention_rate`,
  `share_of_model`, `by_bucket` or the grade. A ranked business list is not an answer;
  feeding it through the answer path would have the judge scoring prominence on a SERP
  listing. `test_the_local_pack_never_moves_a_visibility_metric` asserts every
  visibility figure is byte-identical with and without the payload.
- Client matching is substring containment either way, not exact equality: a Google
  listing is routinely longer than the name on the shop's own site ("Albert Nahman
  Plumbing, Heating, and Cooling" vs "Albert Nahman Plumbing"). Deliberately not fuzzy —
  a fuzzy match would eventually call a rival the client.

### openai_search is unusable on this account, and the numbers say so

The repin in the entry below made the model work — a single call returns 4,107 chars /
11 citations. A real run still lost **0 of 10** cells, twice. Measured cause:

- OpenAI caps search-class models at **6,000 tokens/minute** on this account
  (`x-ratelimit-limit-tokens`, read live).
- One `openai_search` answer consumes **17,227 tokens** — 16,455 of them retrieved web
  context. **One call is ~3x the entire minute budget.**
- Sustainable rate: 0.3 calls/min. ~29 min for a 10-query set, **~7 h** for the plumbing
  template at runs=5. `gpt-4o-search-preview` carries the same 6k cap, so this is
  account tier, not model choice.

Serializing the surface (`PROVIDER_CONCURRENCY_OVERRIDES`, added) prevents a 429
stampede but cannot fix a token budget, and that comment says so rather than implying a
fix. `openai_search` is therefore **out of the local template's default engines**, pinned
by a test with the reasoning attached; `--surface search` still includes it for anyone on
a higher tier. Raising the OpenAI tier is the real fix.

Worth noting what this validates: the Phase-1 accounting turned a run that would have
read `done 35/35` into `dead_engines: ["openai_search"]`, `21/35 cells answered`. The
honest-accounting work paid for itself on its first real run.

### Verified end-to-end

Live run `9d436a20`, Berkeley plumbing, through `POST /audits`:

```
engines measured : ['gemini_grounded', 'google_ai_overviews', 'perplexity']
dead_engines     : ['openai_search']
cells            : 21 / 35
local_pack       : serper_places, 5 queries, 50 businesses
CLIENT RANK      : loc-01:1  loc-02:1  loc-03:2  loc-04:1  loc-05:6
```

50 rows persisted (50 with phone, 40 with website), and the report rebuilds byte-identically
from storage alone in a fresh process. The interesting finding is the split itself: the
client is **#1 in Berkeley's local pack** yet mentioned in **0%** of local-intent AI
answers — it owns the map and is invisible in the answers built beside it. That is
exactly the gap a shop owner is paying to be told, and no single number could express it.

Note `google_ai_overviews` answered 1 of 5 even after routing — AIO is thin on this
trade's hybrid/brand queries too. That is the follow-up measurement the routing table's
rationale already flags (brand was 0 of 3 twice now, still n too small to encode).

### Gate

mypy clean (81 files) · ruff clean · pytest **359 passed, 1 skipped** · `tsc --noEmit`
clean · teaser 162 green.

### Up next

Raise the OpenAI tier or leave `openai_search` out. Gather enough observations to decide
AIO on `brand`. Render the new `local_pack` block in the local report template (§3's
checklist can now be produced, since Serper is configured).

---

## Engine health + intent-scoped routing (Phases 0–3, 6) — Completed 2026-07-28

Found by running a real local audit (run `e186c524`, Berkeley plumbing, 10 queries ×
3 engines). It finished `done 30/30` and produced a report — while measuring almost
nothing. Same failure class as the 2026-07-27 SearchApi entry below, which predicted
exactly this: "the run would have completed with that surface simply empty."

### The two findings

**1. `openai_search` answered 0 of 10 cells.** Its pin,
`gpt-4o-search-preview-2025-03-11`, is 404 deprecated. The engine honored its contract
(`None`, never raised), so nothing crashed — and nothing warned. The run status read
`openai_search 10/10`, ten empty rows persisted, and `reports.py` listed the surface
among the engines that had measured the client, because that list was built from **row
existence, not answer existence**. One third of the run's cells had no data behind
them and the artifact could not say so.

Two things worth carrying forward: `models.list` **still returns the dead id**, so no
listing check could have caught this — only a real invocation; and the *undated*
`gpt-4o-search-preview` alias is alive but was deliberately rejected, because
`tests/test_isolation.py` requires a dated snapshot. Now pinned to
`gpt-5-search-api-2025-10-14` (dated, live, same `annotations[].url_citation` shape,
4107 chars / 11 citations on verification).

**2. AI Overviews is the wrong instrument for `local_intent`.** AIO returned content
for 1 of 10 queries — the single `informational` one. 0 of 5 `local_intent`, 0 of 3
`brand`. Industry data agrees: local-intent SERPs show a Local Pack ~93% of the time
and an AI Overview ~15% (~7% for "near me"), versus ~92% informational / ~97% hybrid.
Google serves the local pack there, not an Overview.

`src/prompts/intent.py` already documented those percentages on `HYBRID` and
`INFORMATIONAL` — the query-set layer knew; the runner never acted on it. Meanwhile
`LOCAL_BUCKET_ALLOCATION` gives `local_intent` the plurality (0.45), so most of a local
audit's finite SearchApi credits were being spent where the surface structurally isn't.

### What was built

- **Phase 0** — repinned `openai_search`; comment records the 404, the `models.list`
  trap, and why the undated alias was refused.
- **Phase 1** — `metrics.Coverage` + `coverage`/`coverage_by_bucket`/`coverage_by_engine`
  (additive; `_rate` and every existing rate function untouched). `reports.py` now
  splits `engines` (answered ≥1) from `dead_engines`, and `BucketRow` carries
  `answered_cells`/`total_cells` so a bucket nothing answered renders "—" not "0%" — a
  brand cannot be absent from an answer that never existed. `runner.py` tracks
  `engine_answered` beside `engine_completed`, marks a 0-answer surface `failed` with a
  reason on a terminal run, and `_status_from_db` now derives per-engine counts from
  stored rows instead of splitting totals evenly (an even split hid the failure on
  restart).
- **Phase 2** — `src/pipeline/preflight.py`: one real throwaway query per engine before
  the fan-out, retried once so a transient 429 can't condemn a working surface; dead
  engines move into `skipped_engines` and write no rows. Wired into both the API runner
  and `orchestrator.run_audit` (the CLI path that produced `e186c524`), gated by
  `ENGINE_PREFLIGHT` (off in tests). Persisted to a new `audit_runs.engine_probe` jsonb
  column so a report can explain *why* a surface is absent.
- **Phase 3** — `src/pipeline/engine_routing.py`: `ENGINE_POLICY` with exactly one
  entry, `google_ai_overviews` skipping `LOCAL_INTENT`, carrying its evidence in a
  `rationale` string. Policies are **denylists on purpose**: `BRAND` is shared between
  both ICP families, so an allowlist of "informational + hybrid" would have stripped AIO
  from consumer `CATEGORY`/`COMPARISON` queries while looking like a local-only change.
  `prompt_runner` builds its work-list from `routed_cells`, and the cost estimate and
  per-engine progress denominators come from the same function so they cannot disagree.
- **Phase 6** — `cost.py`: fixed the `google_ai_overviews` comment naming the wrong
  vendor (SerpApi → SearchApi), added `PREFLIGHT_COST_PER_ENGINE` and
  `OFFSITE_RUN_COST_USD` (derived from `MAX_STEPS = 8` and the agent's tool quota, not
  guessed). The Cat 6 agent always spent and the budget guard had never counted it.

Effect on the real plumbing template at runs=5: 435 → 370 calls, $8.12 → $6.82, and
**SearchApi credits 145 → 80**.

### The preflight's own bug, caught the same way

The first version defined liveness as "returned answer text" for every engine. Run
against the real engine set it **dropped `google_ai_overviews`** — a healthy surface —
because the probe query happened to have no AI Overview. Google shows none for most
queries and always for local-intent ones, which is the entire premise of Phase 3: an
empty capture there is *data*, not a failure.

Fixed by adding `BaseEngine.probe(prompt) -> (alive, chars, citations)` to the engine
contract. The default is unchanged behaviour for model engines; `AIOverviewsEngine`
overrides it so liveness means **the SERP request succeeded** (a 401, an exhausted
credit balance or an outage still fail). It now reads `alive=True, chars=0`.
`tests/test_engine_liveness.py` pins both directions — success-with-no-Overview is
alive, transport error is dead — because this is precisely the distinction that gets
collapsed again by anyone "simplifying" the probe.

Worth noting: the probe costs one SearchApi credit per run, since checking that the
request works means making one.

### Deliberately not done

- **AIO on local `brand` queries.** Our run saw 0 of 3, which suggests skipping it. n=3
  with no external corroboration, so it stays a measurement to make rather than a guess
  to ship — same discipline as `SAMPLING_BANDS` shipping empty.
- **A new `"degraded"` run state.** Degradation is surfaced additively instead; a new
  terminal state would need the `web/lib/api.ts` union and the poller's terminal set,
  and an unknown state polls forever.

### Also fixed on the way past

`ruff check src/` was failing on `main` (the `cf041f7` message claims otherwise). The
Supabase CLI's gitignored `supabase/` directory (added in `078eda5`) makes ruff's isort
classify the `supabase` *package* as first-party and demand the import move — so the
gate passed or failed depending on whether someone had run the CLI locally. Fixed in
config (`known-third-party = ["supabase"]`) rather than by moving the import, which
would have oscillated.

### Gate

mypy clean (80 files) · ruff clean · pytest **348 passed, 1 skipped** (was 321) ·
`tsc --noEmit` clean for `web/` and `teaser/` · teaser 162 tests green. Verified against
the real run: `engines: ["google_ai_overviews", "perplexity"]`,
`dead_engines: ["openai_search"]`, 11 of 30 cells answered.

### Up next

Phase 4 (capture the local pack as a measured surface — it is the 93% surface and
`query_local_entities` still has no production caller) and Phase 5 (Serper as the
local-pack vendor). Phase 5 needs `SERPER_API_KEY`, which is unset — that also leaves
Cat 6 offsite degraded to its deterministic pre-pass, so the local report's
review-platform checklist cannot currently be produced at all.

---

## SMB pivot patch — SearchApi location format was wrong (caught by running it) — Completed 2026-07-27

### The bug

W1.1-W1.4 specified `BusinessLocation.country` as **ISO-3166 alpha-2** and serialized
`"Berkeley,California,US"`. SearchApi rejects that outright:

    400  {"error": "Location was not found. Double check location parameter."}

It wants the country's **full name** — `"Berkeley,California,United States"` resolves
and returns a local pack. Verified live 2026-07-27 against the real API; SearchApi also
accepts `"Berkeley,CA,United States"` and `"Berkeley,California"` (it normalizes both),
but never a bare ISO country code.

This was written from the docs (which say a "canonical location name" without spelling
out the country form) and was never exercised against the live API until now. Every
unit test passed the whole time — they asserted our own wrong string.

**Impact had it shipped:** every local run would have failed the AI Overviews call.
Because `BaseEngine` contracts engines to return `None` rather than raise, the run
would have completed with that surface simply empty — a local audit reporting "you
don't appear" from a request that was never accepted.

### Fixed

- `BusinessLocation.country` is now the SearchApi country NAME, documented as such
- `normalizeLocation()` no longer uppercases the country, and **rejects any ≤2-char
  country** — an ISO code now drops the location rather than producing an unresolvable
  one, the same safe direction as the partial-location rule
- Corrected the resolver prompt, the trade starter CSV placeholder, the local
  fact-sheet template, the local gold template, and every docstring/test carrying the
  bad example

### Verified live, not just in tests

    AIOverviewsEngine(location="Berkeley,California,United States")
      .query_local_entities("best plumber in Berkeley")
    -> 3 entities:
       1. Albert Nahman Plumbing, Heating, and Cooling   HVAC contractor  4.7 (3400)
       2. LemonTree Plumbing                             Plumber          5.0 (30)
       3. J J Rooter & Plumbing                          Plumber          4.9 (94)

**W1.6's entity capture works end to end against the real API.** This is the first
real-money confirmation that the local path produces genuine local competitors.

### Gate

mypy clean (78 files), ruff clean, pytest 321 passed / 1 skipped, tsc clean,
npm test 162 passed (+1: the ISO-rejection guard).

### Lesson recorded

A format taken from documentation and covered only by tests asserting our own output
is not verified. The determinism/isolation work already had this instinct (Test E
records the payload actually sent); location needed the same and didn't get it until a
live call was made.

---

## SMB pivot Phase 5 — sampling bands, local report template, cadence guard — Completed 2026-07-27

The last plan phase. Small, and mostly about refusing to invent numbers.

### What was built

- **W5.1 — per-trade sampling bands** (`src/pipeline/local_sampling.py`).
  `TradeSamplingBand` carries `runs_per_query` PLUS `measured_on` / `measured_note`,
  so a band can never become a folk number nobody can trace. **`SAMPLING_BANDS` ships
  EMPTY** — the plan says set K empirically via `geo verify determinism`, and inventing
  per-trade values would launder a guess into the report as a methodology figure.
  Unmeasured trades fall back to the global default with `is_measured=False`, and
  `sampling_note()` says so out loud. `exceeds_cap` surfaces a measured band above
  `MAX_RUNS_PER_QUERY` as a real finding (local too unstable to measure at the current
  ceiling) rather than clamping it away silently.
- **W5.3 — the cadence guard.** Found a live trap: `trend.render_comparison` with
  `noise_floor=None` tags NOTHING as within-noise, so every delta reads as a real move.
  Survivable on the consumer path (measured baseline, stable engines); not on local,
  where SE Ranking saw ~80% of URLs churn between repeats — a month-on-month
  "improvement" would more likely be jitter, reported to a shop owner as progress.
  `local_cadence_warning(trade)` returns the banner that must accompany an unmeasured
  local comparison, and returns None once a band exists.
- **W5.2 — local report template** (`docs/report-template-local.md`). Section order,
  the consumer→local diff table, and six hard rules (no aggregate ratio, no unmeasured
  claim, no uncaptured competitor, no accuracy figure until W3.4, no cadence delta
  without a noise floor, always print the location).

### The number we refused to invent

Dollar framing. The strategy doc calls for phone-call economics, but **we do not have
any given shop's job value**, so a dollar figure would be fabricated — the same class
of error as an unmeasured prominence verb. The template records what it would take to
add one honestly (cited industry average, labelled as such, never multiplied by our own
query-set denominator to manufacture a "lost revenue" total).

### Acceptance criteria — all passed

- ✅ No trade band exists without a `measured_on` date (guarded by a test that fails if
  someone adds one)
- ✅ Unmeasured trades fall back to the default and the note says "not established"
- ✅ Cap overflow stays visible via `exceeds_cap`
- ✅ "near me" cohort identified; each trade set leans on at most one such query
- ✅ Cadence warning fires when unmeasured, clears when measured
- ✅ Gate: mypy clean (78 files), ruff clean, pytest 321 passed / 1 skipped (was 314),
  tsc clean, npm test 161 passed

### Plan status: Phases 0-5 complete

Remaining work is operational, not build: apply the `audit_runs.location` migration,
re-warm the judge cache after the Phase-3 bump, populate `SAMPLING_BANDS` from real
determinism runs, and complete W3.4 calibration (local gold set + consumer re-run).

---

## SMB pivot Phase 4 — site audit for local (directories, NAP, Cat 5/6) — Completed 2026-07-27

Local Cat 5/6, with the `llms_txt` evidence bar applied to every candidate check —
including one we declined to score.

### What was built

- **W4.1 — local directories.** `LOCAL_REVIEW_PLATFORMS` (yelp, google.com/maps,
  bbb, angi, thumbtack, homeadvisor, facebook, nextdoor) forked from the consumer
  tuple, selected by `review_platforms_for(business_kind)`. The two sets are disjoint
  by design — a plumber has no App Store presence, a phone app has no BBB page.
  `google.com/maps` is the deterministic stand-in for GBP: a Maps listing is the
  SERP-visible surface of the profile, reachable with the same `site:` probe (no
  scraping, no Places API).
- **W4.2 — local research brief.** `_LOCAL_SYSTEM` forked from `_SYSTEM`; the consumer
  brief still hunts Reddit threads, listicles and press, unchanged. What "offsite
  presence" MEANS differs for local: nobody writes a listicle about a Berkeley
  plumber, so the local brief leads with NAP consistency and directory presence, and
  explicitly warns about same-name confusion across metros (the #1 local research
  error) — it must confirm the city matches before reporting a listing. The client's
  city is threaded in when known.
- **W4.3 — local Cat 6 scoring.** GBP is pulled out of the directory tally and scored
  SEPARATELY at weight 3.0, matching SSR: the local pack and the AI answers built on
  it are generated FROM the GBP entity, so no profile means structurally absent, and
  averaging that away inside a "3 of 8 directories" pass would hide it. The remaining
  directories score 2.5. `ENTITY_CONSISTENCY` on the local path becomes the NAP check
  at 2.5 (up from the generic 1.5) — an inconsistent NAP splits the entity, so no
  single listing accumulates enough authority to be cited at all.

### The check we deliberately did NOT score

`LocalBusiness` schema on a local homepage is a real gap, and W4.3 adds the
expectation (`_LOCAL_CATEGORY_EXPECTED`) so it feeds the existing `schema_valid`
check. But it is **hygiene-only and never a roadmap item**: controlled studies show no
AI-citation lift from JSON-LD because retrieval reads visible HTML, so elevating it
would fail the same evidence bar that keeps `llms_txt` note-only. The visible NAP
block on the page is what matters; the markup is tidy-up. Guarded by
`test_local_business_schema_is_never_a_roadmap_gap`.

### Acceptance criteria — all passed

- ✅ Platform sets forked, disjoint, consumer tuple byte-identical, unknown kinds fall
  back to consumer
- ✅ Consumer research brief unchanged; local brief leads with NAP + directories and
  carries the city; a location never leaks onto the consumer brief
- ✅ GBP scored separately at 3.0; directories at 2.5; NAP at 2.5; consumer offsite
  scoring (labels AND weights) untouched
- ✅ Local schema never becomes a scored gap
- ✅ Gate: mypy clean (77 files), ruff clean, pytest 314 passed / 1 skipped (was 305),
  tsc clean, npm test 161 passed

### Deviation

Two `tests/test_offsite.py` stubs needed their arity widened (`reviews_presence` and
`_deterministic_prepass` both take a business kind now). Signature churn only — no
assertion was changed or relaxed.

### Up next — Phase 5: metrics, report, sampling

Per-trade sampling bands, local report template, cadence comparison. Use
`geo verify determinism` to set K empirically per trade rather than by assumption —
SE Ranking measured ~80% of URLs swapping between repeat runs of "near me" queries,
and `MAX_RUNS_PER_QUERY` is currently 5. If local needs K > 5, raise it deliberately
and record the cost.

---

## SMB pivot Phase 3 — local accuracy flags, local fact sheet, the cache bump — Completed 2026-07-27

The cache-invalidating phase, in ONE commit and ONE `_PROMPT_LAYOUT` bump as the plan
requires. W3.4 is PARTIAL by necessity — see below.

### What was built

- **W3.1 — local accuracy flags.** `AccuracyFlagType` gains `wrong_hours`,
  `wrong_service_area`, `wrong_contact`, `licensing`. A product's accuracy is
  pricing/features/model; a local business's is "can I get them, where, and are they
  legitimate". Deliberately **append-only**: no existing rule reworded, no existing
  flag renamed, so a product answer should judge identically.
  They are **structurally inert on the consumer path** rather than gated — every flag
  needs a VERBATIM contradicting fact-sheet line, and a product sheet has no
  hours/service-area/licence lines to cite. Nothing has to remember to switch them off.
- **W3.2 — local fact-sheet template.** `docs/fact-sheet-template-local.md`, organised
  around contact / hours / service area / licensing (mapped to the four new flags)
  rather than pricing/features/versions. Emphasises that the NEGATIVE lines ("Closed
  Sunday", "No after-hours service", "Does not serve Marin") are what make an
  over-claiming answer flaggable at all.
- **W3.3 — the cache bump.** `_PROMPT_LAYOUT` →
  `single:rubric-in-cached-system:v2-local-accuracy`. Fingerprint
  `5e8caed0…b13b3d` → `c9e86fca…01d10`. The W0.4 pin was updated in THIS commit, which
  is the one sanctioned change to that constant. All 15 `tests/test_judge.py` parity
  assertions pass unweakened; the HEAD/RUBRIC split still reassembles byte-identically.
- **Bug found and fixed while bumping:** `scripts/prejudge_workflow.js` **hardcodes**
  the `record_judgment` enums to keep Workflow args small, and still listed only the
  original five flag types. A prejudged LOCAL run would have come back with zero local
  accuracy flags and **looked clean** — the worst failure mode for an accuracy check.
  Synced, and pinned by a new `test_prejudge_workflow_js_enums_match_the_python_types`
  so all four enums (prominence/framing/flag types/severity) can never drift again.
- **W3.4 — gold-set scaffolding (see limits).** `data/local_gold_template.json`
  (verified to load through the real `calibration.load_gold_set`, new flag types
  parsing correctly), plus local labeling traps, and `docs/gold-set-template.json`
  updated to name the local flag types and to state that ICPs are never mixed in one
  gold file.
- **Append-only verification.** Three new tests pin that the five consumer flag values
  are unchanged, that every consumer per-type rule is byte-identical, that the delete
  gate / verbatim gate / omission rule are unsoftened, and that each local rule still
  requires a contradicting sheet line. These are what make W3.4's CHEAP resolution
  (re-run the consumer gold sets, confirm agreement holds) legitimate rather than
  hopeful.

### Acceptance criteria — passed

- ✅ One `_PROMPT_LAYOUT` bump, one commit; parity tests pass unweakened (15)
- ✅ Prejudge JS enums match the Python types, now guarded
- ✅ Local gold template loads through the real loader with local flags parsed
- ✅ Consumer rules byte-identical; local rules structurally inert on product sheets
- ✅ Gate: mypy clean (77 files), ruff clean, pytest 305 passed / 1 skipped
  (was 301), tsc clean, npm test 161 passed

### W3.4 is NOT complete, and cannot be completed by the build

Two things remain, both requiring humans and real spend:

1. **Label a local gold set.** 25-40 real answers from a real local audit run,
   hand-labeled. Models must not label their own gold set — independence is the point.
2. **Run calibration twice.** The new local set, AND a re-run of the existing consumer
   sets (Oura, Fort) to confirm 96/88/93 still describe the post-bump judge. Uses the
   held-constant API judge with `isolated_cache()` — never the shared cache, never
   subscription/Opus verdicts.

**Standing gate until both pass: NO report of either ICP may quote an accuracy or
agreement figure.** The bump was global, so the freeze is global. Mention, prominence
and framing are unaffected and remain quotable.

### Also outstanding

- Every cached verdict is now a MISS. Re-warm with the `prejudge` skill (free) rather
  than paying to re-judge on the API.
- The `audit_runs.location` migration (`data/schema_ui.sql`, from Phase 1) still needs
  applying to Supabase.

### Up next — Phase 4 (W4.1-W4.3): site audit for local

Local review platforms (keep BOTH sets, select by kind), offsite agent NAP/directory
checks, GBP/NAP Cat 5-6 checks. Every new local check must clear the `llms_txt` bar:
evidence it affects citations, or it ships note-only.

---

## SMB pivot W1.6 + Phase 2 — local-pack entity capture, local query sets and teaser — Completed 2026-07-27

Closed the W2.4 data-source gap flagged in the previous entry, then executed Phase 2
(W2.1-W2.7). The consumer ICP is unchanged throughout; every divergence is selected by
`business_kind`.

### What was built

- **W1.6 — local-pack entity capture (NEW work item; added to the plan).** W2.4
  requires competitors "seeded from captured local-pack entities" and forbids LLM
  recall, but no original Phase 1 item built that capture — W2.4 as specified had no
  data source. Added `LocalEntity` + `AIOverviewsEngine.query_local_entities()`
  (SearchApi's `local_results`, verified against its Google-engine docs) and a
  `GET /api/local-entities` endpoint so the TypeScript teaser reaches it without a
  second SearchApi credential. Refuses to run without a location; drops closed
  businesses (the local twin of `DEFUNCT_BRANDS`).
- **W2.1 — local intent buckets.** `IntentBucket` gains `LOCAL_INTENT`/`HYBRID`/
  `INFORMATIONAL`; `BRAND` is shared. `BUCKET_ALLOCATION` was FORKED, not rebalanced.
  The real break was `_TEASER_BUCKETS`, hardcoded to `(CATEGORY, COMPARISON)`: a local
  set intersects it in ZERO queries. Now `teaser_buckets(business_kind)`, and
  `run_teaser` RAISES on an empty selection instead of reporting "you appear nowhere"
  from no measurement.
- **W2.2 — per-trade query templates.** `data/queries_{hvac,plumbing,barbershop}.json`
  (29/29/28 queries) with `{city}`/`{brand}` slots, plus `src/prompts/local_templates.py`.
  `build_template_csv()` is now parameterized — no-arg returns the Oura consumer CSV
  byte-for-byte (the plan's "replace it" would have been a consumer regression).
- **W2.3 — kind-selected query generation.** Local fallback templates that are
  geo-anchored and NEVER name a competitor. The stale B2B-SaaS phrasing ("for a
  growing startup", "scales with my needs") was fixed rather than deleted, so the
  consumer branch still has a correct fallback.
- **W2.4 — local resolver path.** `LOCAL_SERVICE_PATH_READY` flipped to `true`. The
  anti-fabrication guarantee is now STRUCTURAL, not prompt discipline: `buildProfile`
  discards the model's competitors wholesale for a local site, and only
  `attachLocalCompetitors()` — which requires captured entities — can name a rival. It
  drops the client from its own list and throws rather than emit a rival-less teaser.
  `MockPlatformClient.getLocalEntities()` throws by design: every other mock method
  fabricates, but a fake local rival is the one failure that survives human review.
- **W2.5 — service-area overlap.** New `ServiceAreaVerdict`; a same-trade
  different-metro rival now drops with `serviceAreaMismatch` provenance. Recall-safe
  (only an explicit `different_area` drops) and gated to local: the prompt block is
  APPENDED for local clients, so the consumer prompt is byte-identical.
- **W2.6 — local copy.** `localHeadline`/`localLeadSentence`/`localStakesLine`/
  `localCtaLine` + `LOCAL_SOURCE_CHECKLIST` (GBP, Yelp, BBB, Angi, Thumbtack,
  Facebook, Bing Places, Reddit). "buyers" → "customers"; **no aggregate appearance
  ratio** on the local path (the denominator is a set we chose, so it reads as a
  visibility rate and is not one). Every claim-fidelity guard is inherited, not
  reimplemented — local verbs still grade off judged prominence.
- **W2.7 — forked discovery prompt.** `_LOCAL_EXTRACT_PROMPT` alongside the untouched
  consumer `_EXTRACT_PROMPT`, selected by `extract_prompt_for(business_kind)`.
- **Cross-boundary:** the TypeScript `IntentBucket` union was extended to match the
  Python enum. That surfaced five `Record<IntentBucket, …>` ranking/label tables
  needing local values (weights, bucket labels, two intent priorities, lead priority);
  each got a deliberate local entry rather than a default.

### Acceptance criteria — all passed

- ✅ Local entities: typed and filtered; `[]` on no pack / malformed body / transport
  error; refuses without a location; endpoint 422s on a missing location, 503s when
  the engine can't build
- ✅ Consumer teaser still selects exactly `(category, comparison)`; local selects
  `(local_intent, hybrid)`; empty selection raises
- ✅ All three trade sets load, use only local buckets, 25-40 queries, unique ids,
  slots substitute, unfilled slots fail loudly
- ✅ A local profile is built with NO competitors; `attachLocalCompetitors` sources
  only from captured entities, drops the client, caps at 4, and throws on none
- ✅ Same-metro rival kept, unknown kept, different-metro dropped with provenance;
  consumer competitor sets unaffected
- ✅ Local copy is prominence-graded and prints no ratio
- ✅ Gate: mypy clean (77 files), ruff clean, pytest 301 passed / 1 skipped
  (was 283), `tsc --noEmit` clean, npm test 161 passed (was 143)

### Deviations, and one deliberate test change

- **Two W0.1 tests were rewritten, not deleted.** They pinned "local is refused",
  which W2.4 legitimately changes. They now pin the replacement contract: local
  ROUTES, and a local profile carries no extraction-sourced competitors. This is the
  W0.1 → W2.4 transition the plan describes, not a weakened guard.
- **The consumer-path regression lock never had to be touched.** All 20 assertions
  passed unchanged through every Phase 2 work item — including the judge fingerprint,
  which Phase 2 does not go near.

### Up next — Phase 3 (W3.1-W3.4): judge and fact sheet

The cache-invalidating phase: one `_PROMPT_LAYOUT` bump, one commit. Note W3.4 needs a
hand-labeled local gold set and held-constant API-judge calibration runs — real spend
and human labeling, not something the build can complete on its own.

---

## SMB pivot Phases 0-1 — regression lock, businessKind classifier, location plumbing — Completed 2026-07-27

Executed `docs/smb-pivot-build-plan.md` Phase 0 (W0.1-W0.4) and Phase 1 (W1.1-W1.4).
The pivot ADDS the local-service ICP; the consumer-product ICP stays live and
unchanged. Every change is additive and selected by business kind.

### What was built

- **W0.4 — consumer-path regression lock (built FIRST, as the hard gate).**
  `tests/test_consumer_path_regression.py` (9 tests) + `teaser/tests/consumerPathRegression.test.ts`
  (11 tests). Pins today's consumer behaviour across the six shared symbols Phases 1-4
  touch: `build_template_csv()`, `_TEASER_BUCKETS`, `_EXTRACT_PROMPT`,
  `REVIEW_PLATFORMS`, the teaser resolver/copy path, and `_single_fingerprint()`.
  Designed to fail loudly on an in-place edit; the fix is to fork by business kind,
  never to relax an assertion. The judge-fingerprint pin
  (`5e8caed0…b13b3d`) is the ONE assertion that may change, and only in W3.3.
- **W0.1 — `businessKind` classifier.** `teaser/src/types/domain.ts` gains the
  `BusinessKind` type — the single selector for every consumer/local divergence.
  `profileExtraction.ts` gains the field in the extraction schema (required +
  enumerated) and prompt, `businessKindOf()` (the one canonical default),
  `LOCAL_SERVICE_PATH_READY = false`, and `assertSupportedBusinessKind()`, which
  REFUSES a local-service site until the local path exists. Checked before any other
  field is normalized, because on a local site every downstream field was extracted by
  consumer-shaped instructions and is untrustworthy. Becomes the W2.4 router.
- **W0.2/W0.3 — docs.** `teaser/README.md`: corrected the default engine list to
  `perplexity, openai_search, gemini_grounded` (was three wrong names), corrected
  `pdf.ts` from "documented stub" to the real Playwright renderer it is, and
  documented the `--engines google_ai_overviews` flag WITH the unpinned-locale caveat
  (valid for consumer prospects, not for any local query until W1.3).
- **W1.1 — location on the profile.** `BusinessLocation` + `canonicalLocation()` in
  `domain.ts`; optional `location?` on `CompanyProfile` and mirrored onto `TeaserDraft`
  (with `businessKind`) for regeneration parity — the `clientAliases` precedent, so a
  regenerated local teaser can't silently revert to consumer-shaped.
- **W1.2 — resolver extracts NAP.** `location` added to the extraction schema
  (required, nullable) and prompt, sourced from the site's own NAP block/contact
  page/schema.org `LocalBusiness`, with an explicit "do NOT infer from the brand name
  or area code" clause. `normalizeLocation()` keeps a location only when
  city+region+country are ALL present — a partial one resolves at SearchApi to "the
  most popular match", i.e. a different metro, silently measuring the wrong market.
- **W1.3 — AI Overviews accepts a location.** `AIOverviewsEngine(location=...)`,
  constructor-injected so the uniform `BaseEngine.query(prompt)` fan-out contract is
  untouched. Param name VERIFIED against SearchApi's Google-engine docs (2026-07):
  `location` takes a canonical NAME and SearchApi builds `uule` itself; the two are
  mutually exclusive, so only `location` is sent. The recorded and sent params are now
  literally the same dict, so the audit log cannot drift from the request (Test E).
- **W1.4 — location through the audit contract.** `config,location` row emitted by
  `teaser/src/platform/csv.ts` (only when a location exists), parsed into
  `RunConfig.location` by `csv_loader.py`, threaded through `build_engines(location=)`
  — which passes it ONLY to `google_ai_overviews`, the one surface with a locale knob —
  and through both `runner.py` call sites. Persisted on `audit_runs.location`
  (`data/schema_ui.sql`, idempotent `add column if not exists`) and restored on resume,
  so an interrupted local run cannot finish un-localized and mix two markets.

### Acceptance criteria — all passed

- ✅ W0.4 green at the pre-pivot baseline before any shared symbol was touched
- ✅ A local-service fixture throws with an actionable message; a consumer-product
  fixture still resolves unchanged; the blank/`"product"` category guard still fires
- ✅ Location: complete → kept; partial → dropped, never guessed; product → never acquires one
- ✅ AI Overviews with no location produces today's payload key-for-key
  (`{engine, q, api_key}`); with one, sends `location` and never `uule`; error paths
  still return `None`
- ✅ A CSV with no `location` row parses exactly as before (`location is None`, not `""`)
- ✅ CSV round-trip: `config,location` → `RunConfig.location` → engine
- ✅ `tests/test_isolation.py` updated narrowly (14 → 21); no matcher loosened
- ✅ Gate: mypy clean (76 files), ruff clean, pytest 283 passed / 1 skipped
  (was 264), `tsc --noEmit` clean, npm test 143 passed (was 118)

### Deviations from the plan, and why

- **W2.2's "replace the Oura starter template" was NOT done** — it is a consumer
  regression (`build_template_csv()` is served at `GET /api/template.csv`). The plan
  was amended to parameterize instead; W0.4 pins the no-arg output.
- **`_PROMPT_LAYOUT` deliberately untouched.** Nothing in Phases 0-1 goes near a judge
  prompt, so no cached verdict was invalidated.
- **Schema migration is written but NOT applied.** `audit_runs.location` exists in
  `data/schema_ui.sql`; it still needs running against Supabase. Until then a resumed
  run reads `None` and behaves as today.

### Up next — Phase 2 (W2.1-W2.7): local query sets and the teaser

Blocked on one unresolved plan dependency: **W2.4 requires competitors "seeded from
local-pack / directory entities captured in Phase 1", but no Phase 1 work item builds
that capture.** W1.3 localizes the AI Overviews request; it does not persist the
local-pack entities W2.4 needs, and the plan is explicit that LLM recall must never
supply local rivals. Phase 2 needs an entity-capture work item added before W2.4 can
be built as specified.

---

## Research-validation fixes — rubric evidence alignment (llms.txt note-only, schema hygiene framing, doc corrections) — Completed 2026-07-21

Applied the geoPromptRunner-flagged items from the 2026-07-21 deep-research
validation run (site/roadmap evidence base; adversarially verified claims).

### What was built

- **`src/audit/synthesize.py`** — dropped `llms_txt` from `_CHECK_MAP`: the
  check still runs and shows in the raw Cat-1 table, but a missing llms.txt can
  no longer synthesize into a rubric score or roadmap gap (no engine confirms
  consuming it; ~300k-domain analyses show zero correlation with AI citations).
  Renamed the `schema_valid` check to "schema.org markup valid and matching
  visible content (hygiene)" — controlled studies (Ahrefs matched-control) show
  no citation lift from JSON-LD, so the name must not imply visibility impact.
- **`src/audit/rubric.py`** — `DEFAULT_CHECKLIST`: removed "llms.txt present"
  from Cat 1; reworded Cat 5 to hygiene/entity-clarity framing and added
  "entity identifiers consistent across the web".
- **`tests/test_synthesize.py`** — new
  `test_llms_txt_is_note_only_never_a_roadmap_gap` guard; updated the schema
  check-name assertion.
- **`docs/smb-pivot-plan.md`** — corrected the Foundation/AirOps attribution
  (the ~60% home-services third-party figure is from a different study; the
  claimed Perplexity–Yelp API deal didn't verify and was dropped; added the
  verified 62.1% Perplexity share). Replaced the conflated "65–81% turnover"
  volatility phrasing with the verified "~80% of URLs / >60% of domains" from
  SE Ranking's AI Mode volatility test; Ahrefs CTR claim tightened to 34.5%
  (dropped the unsubstantiated –58% bound); run-rate example aligned to n/5.
- **`docs/website-plan.md`** — fixed the Whitespark stat tile (68% is the
  *local-business* average; 92% informational — the old wording mismatched the
  number); aligned mention-rate examples to `RUNS_PER_QUERY=5` and recorded the
  run-count-language decision (copy states what the instrument does; bump
  config before copy if we want a bigger-K story).

### Acceptance criteria — all passed

- ✅ `mypy src/` clean (76 files)
- ✅ `ruff check src/` clean
- ✅ `pytest tests/` — 264 passed, 1 skipped (includes the new llms.txt guard)

---

## Isolation & Determinism — Engine isolation proven, pinned, and guarded (docs/isolation-determinism-plan.md) — Completed 2026-06-11

Converted the implicit "every call is fresh" property into a proven, guarded
one, per the plan's five build items. No measurement behavior changed — the
calls were already stateless; this adds the proof, the anti-regression guard,
and the model/seed pins that keep two measurement cycles comparable.

### What was built

- **`src/engines/base.py`** — the Layer-2 statelessness code rule is now part of
  the `BaseEngine` contract docstring (one user message, no system prompt, no
  state params, clients are pools not conversations), plus a `MODEL_ID` class
  attribute: the exact model string sent to the provider, recorded per run.
- **Dated model snapshots (Layer 3)** — `openai` pinned to `gpt-4o-2024-08-06`,
  `openai_search` to `gpt-4o-search-preview-2025-03-11` (both confirmed live);
  Anthropic ids were already dated; Gemini GA names and Perplexity `sonar` have
  no dated variants — documented as the firmest pins those providers offer.
- **`seed` (Layer 4)** — new `ENGINE_SEED` setting (default 42), sent on the
  OpenAI and Gemini parametric engines (the providers that accept one).
- **`src/engines/payload_log.py` (Test E)** — `record_payload()` logs every
  outgoing request body at DEBUG and, when `PAYLOAD_LOG_PATH` is set, appends
  it as JSONL (timestamp, engine, payload; secret keys scrubbed; never raises).
  Wired into all 8 engine adapters; where possible the recorded dict *is* the
  dict sent, so log and request can't drift.
- **`engine_models` run metadata (Layer 3)** — new jsonb column on
  `audit_runs` (Supabase migration `add_engine_models_to_audit_runs`),
  populated by both run paths (`orchestrator.run_audit`, `api/runner.start_run`)
  via the new `orchestrator.engine_models()` helper; round-trip verified.
- **`src/verification/`** — the live probes:
  - `canary.py` (Test A): two-call memory probe with an unguessable marker;
    `leaked`/`isolated`/`inconclusive` verdicts (conservative: a failed setup
    call can't produce a clean verdict).
  - `determinism.py` (Test D): K fresh repeats → agreement profile
    (`unique_answers`, `modal_agreement`, `identical`) + `suggest_runs_per_query`
    bands calibrating whether K=3 is enough.
  - `shuffle.py` (Test C): full set forward then reversed, per-query
    normalized comparison — order must not matter beyond the Test D noise band.
- **`geo verify {canary,determinism,shuffle}`** CLI subcommand (`src/cli.py`)
  with `--surface/--query/--k/--query-set`.
- **`tests/test_isolation.py` (Test B — the anti-regression guard)** — 14 tests
  capturing every engine's outgoing payload at the client boundary: exactly one
  user message, no system prompt, no state params (`store`,
  `previous_response_id`, thread/conversation/session ids, ...), constant
  inputs across calls, dated-snapshot model ids, second call carries nothing of
  the first (Josh's smart-ring → Oura scenario, asserted directly), MODEL_ID
  declared on every registered engine, payload-log JSONL + secret scrubbing.
- **`tests/test_verification.py`** — 20 tests proving both probe verdict paths
  with stateless/stateful/dead fake engines, plus the agreement math and
  shuffle comparison logic.
- **`.env.example`** — documents `ENGINE_SEED` and `PAYLOAD_LOG_PATH`.

### Acceptance criteria — all passed

- ✅ Full suite green: 99 passed (65 pre-existing + 34 new)
- ✅ Guard verified to bite: with the engine changes reverted (stashed) the new
  payload tests fail (8 failures) — a regression cannot pass silently
- ✅ mypy (strict) clean on `src/` and both new test files; ruff check + format clean
- ✅ Live canary run (Test A): openai, anthropic, gemini, perplexity,
  openai_search, anthropic_search all `isolated` — no engine could recall the
  prior call. gemini_grounded inconclusive (provider 500s during the run, not
  an isolation finding); google_ai_overviews inconclusive (SERP surface returns
  no overview for the probe — it has no chat state to leak)
- ✅ Dated snapshots resolve on the live APIs (both OpenAI pins answered)
- ✅ `engine_models` migration applied; write + read-back verified against
  Supabase (smoke row soft-archived, never hard-deleted)
- ✅ Keyless `__main__`/probe smoke: payload_log, orchestrator teaser, and all
  three probes run against the mock engine

---

## UI — CSV-Upload Audit UI (docs/ui-plan.md, Phases A–E) — Completed 2026-06-03

Built the full front door from `docs/ui-plan.md`: drop CSV(s) → preview the
merged audit → run across engines → read the report. Additive only — the API
layer imports and calls the existing pipeline (`run_query_set`, the engine
adapters, `metrics`, `judge_metrics`, the judge, `db`); no working module was
rewritten. The two pre-existing source edits are purely additive (a `judge`
field on `RunConfig`, unchanged elsewhere). All 65 existing tests still pass.

### What was built

- **`src/prompts/csv_loader.py`** (Phase A) — parses one or more CSVs on the
  fixed `block,key,value,intent,persona` schema, merges them by block (queries
  accumulate, facts concatenate, config keys merge with conflict detection),
  and validates the merged result (required config keys, valid intents, unique
  query ids across files, known engines, runs_per_query). Returns a `PreviewData`
  that always renders (with per-file provenance + per-row validity) plus a
  run-ready `ParsedAudit` when clean. Ships `build_template_csv()`.
- **`tests/test_csv_loader.py`** — 15 tests: clean single file, split-file merge,
  order-independence, duplicate-id / conflicting-config / bad-intent /
  missing-required / no-queries / unknown-engine / bad-runs errors, template
  round-trip.
- **`src/api/`** (Phase B, FastAPI):
  - `engine_registry.py` — name→adapter map + a keyless deterministic
    `MockEngine` so the whole UI runs without API keys (`engines=mock`).
  - `reports.py` — assembles the structured report the UI renders (scorecard,
    leaderboard, by-bucket, accuracy flags, sources, losing queries); judge-aware
    with regex fallback. Pure.
  - `runner.py` — in-memory run registry + background thread per run; loops
    `run_query_set` query-by-query for live progress; best-effort Supabase
    persistence and best-effort judge (skipped, not fatal, when unconfigured).
  - `app.py` — `GET /template.csv`, `POST /audits/preview`, `POST /audits`
    (422 + structured errors on invalid), `GET /audits`, `GET /audits/{id}/status`,
    `GET /audits/{id}/report`, `POST /audits/{id}/cancel`; CORS for the dev front end.
- **`web/`** (Phases C–E) — Next.js App Router + TypeScript + Tailwind +
  shadcn-style components + Recharts. Upload (multi-file drag-drop, file chips,
  template link, recent audits), Preview (Config/Fact/Queries tabs with
  provenance + inline errors, run gated on a clean set), Progress (live counter,
  per-engine chips, elapsed, cancel), Report (scorecard cards, leaderboard bars,
  per-bucket + accuracy, sources, losing queries, print/JSON export).
- **`requirements.txt`** — added `fastapi`, `uvicorn[standard]`, `python-multipart`.

### Acceptance criteria — all passed

- ✅ CSV loader: mypy (strict) + ruff clean; `__main__` runs; 15 unit tests pass
- ✅ API: mypy (strict) + ruff clean; `__main__` blocks run
- ✅ End-to-end over HTTP (uvicorn): preview, create+run, status→done, report,
  list, template, and 422-on-invalid all verified with the mock engine
- ✅ "not assessed" degradation confirmed: no fact sheet → accuracy not assessed,
  no client domain → citation not assessed, no judge → regex grade/visibility
- ✅ Front end: `next build` compiles with no type errors; all routes serve
- ✅ Full existing suite still green (65 passed)

---

## Maintenance — Code-Review Follow-up Fixes — 2026-05-31

Applied fixes for findings from the high-effort code review of the hardening
pass. All 18 src files still pass mypy (strict) + ruff; every `__main__` runs;
parser verified behavior-identical across 3,500 randomized cases; never-raise
invariant re-confirmed; no-leak logging confirmed (a simulated sensitive value
did not reach the logs).

- **`src/storage/db.py`** — added a single `_execute(op_label, operation)` helper
  that owns the storage try/except, logs only `type(exc).__name__`, and raises
  `StorageError`. All four writes **and the read path** (`_select_rows`) now route
  through it. Fixes the read-path leak (it previously still logged the raw
  exception) and removes the 4× copy-pasted error blocks.
- **`src/config/settings.py`** — added `ENGINE_TIMEOUT_SECONDS` (default 60s, was a
  per-engine 30s) and `ENGINE_MAX_RETRIES`, env-overridable. The three engine
  files now import these instead of duplicating constants — one home for the
  bounded-run policy. The 60s default reduces spurious timeouts on slow-but-valid
  generations while still preventing a stall.
- **`src/engines/perplexity_engine.py`** — added `close()` and a best-effort
  `__del__` so the persistent `httpx.Client` releases its pooled connection
  instead of leaking it.
- **`src/pipeline/parser.py`** — extracted `_classify(present, recommended)` shared
  by `detect_mention` and `extract_competitor_mentions`, removing the duplicated
  classification ladder while preserving the once-per-response scan optimization
  and the present-gated short-circuit.

Not changed: the "cached broken Supabase client" finding was re-examined and
dropped — credentials come from module-level `settings.*` read once at import, so
the old per-call `create_client` used the same static values; caching introduces
no regression and the "recover after credential rotation" path is unreachable here.

---

## Maintenance — Efficiency & Security Hardening Pass — 2026-05-31

Cross-cutting pass (not a chunk). No new features; scope locks respected — the
pipeline stays **synchronous** (async remains a non-goal) and no API key is
logged. All 18 src files pass mypy (strict) + ruff; every `__main__` block runs;
invariant #1 (engines never raise) re-verified with dummy keys.

### Efficiency

- `src/pipeline/parser.py` — precompiled the recommendation-term regex once at
  import; cache compiled per-brand patterns via `lru_cache`;
  `extract_competitor_mentions` now scans for recommendation language once per
  response instead of once per competitor (≈5k→≈k regex ops for k competitors).
  Verified behavior-identical to per-brand `detect_mention`.
- `src/engines/perplexity_engine.py` — reuse one persistent pooled `httpx.Client`
  across all prompts instead of a fresh TCP/TLS handshake per call.
- `src/storage/db.py` — cache the Supabase client (lazy singleton) instead of
  reconstructing it on every read/write.
- `src/engines/openai_engine.py`, `anthropic_engine.py` — explicit 30s timeout +
  2 bounded retries so one hung request can't stall the synchronous run.
- `src/audit/report.py` — sort the share-of-model rows once, not twice.

### Security / leak prevention

- `.gitignore` — now ignores all `.env*` variants (keeps `.env.example`) plus
  `*.pem/*.key/secrets.*/service-account*.json/.netrc`, venvs, caches, logs, and
  local output dirs. Verified with `git check-ignore`: secrets ignored,
  committable files not.
- `src/storage/db.py` — write-failure logs now record the exception **type** only
  (Postgres errors can echo back inserted row values); full detail still chains
  to the caller via `StorageError`.
- `src/pipeline/parser.py` — empty/whitespace brand now returns `NOT_MENTIONED`
  (previously an empty pattern could false-positive as a mention).

### Recommendation (not applied)

- `requirements.txt` uses `>=` lower bounds. Consider a pinned lockfile
  (`pip-compile`/`uv lock`) for reproducible, supply-chain-safe installs. Left
  as-is to avoid changing install behavior without sign-off.

---

## Chunk 11 — Technical accessibility checker — Completed 2026-05-31

### What was built

- Built `src/audit/technical_check.py` — `check_robots_txt`, `check_llms_txt`, `check_sitemap`, `check_rendering`, each returning a `CheckResult` TypedDict (`status: Literal["pass","partial","fail"]`, `details: str`). All HTTP via `httpx` with a 10s timeout; transport errors caught and returned as a `fail` result (never raised).

### Acceptance criteria — all passed

- ✅ `check_robots_txt`, `check_llms_txt`, `check_sitemap`, `check_rendering` implemented
- ✅ `CheckResult` TypedDict with the required `status`/`details` shape
- ✅ All requests use `httpx` with a 10-second timeout
- ✅ Test block runs all 4 checks against a real domain (`example.com`); verified against `nytimes.com` that blocked AI crawlers are correctly reported as `partial` (6 of 7 blocked)

### Up next — Chunk 12: Dry run (integration)

Run the full pipeline end-to-end against one real client domain. Requires live API keys and Supabase credentials.

---

## Chunk 10 — Report generator — Completed 2026-05-31

### What was built

- Built `src/audit/report.py` — `generate_report(run_id: str) -> str` (assembles data from storage and renders) plus a pure `render_report(data: ReportData) -> str`.
- Extended `src/storage/db.py` with read helpers (`get_run`, `get_results`, `get_mentions`, `get_citations`) needed to assemble a report from a stored run.
- `ReportData` TypedDict added to `src/storage/models.py`.

### Acceptance criteria — all passed

- ✅ `generate_report(run_id: str) -> str` returns a markdown string
- ✅ Report includes client name, date stamp, mention rate per engine, competitor share-of-model table, top cited domains, and a summary of findings
- ✅ Test block renders a report from mock data and prints it (deterministic — invariant #7)

---

## Chunk 9 — Supabase storage — Completed 2026-05-31

### What was built

- Built `src/storage/db.py` — `create_run`, `save_results`, `save_mentions`, `save_citations` (+ read helpers), targeting tables `prompt_runs`, `prompt_results`, `brand_mentions`, `citations`. All writes wrapped in try/except and raise `StorageError` on failure; soft-delete via `archived_at` (no hard deletes). All primary keys use `uuid.uuid4()`.
- Extended `src/storage/models.py` with `PromptRun`, `BrandMention`, `Citation` TypedDicts.
- Installed `supabase` into `.venv`.

### Acceptance criteria — passed (live-DB step pending credentials)

- ✅ Tables `prompt_runs`, `prompt_results`, `brand_mentions`, `citations` modeled
- ✅ `create_run(client_name, prompt_count) -> run_id` returns a generated run id
- ✅ `save_results`, `save_mentions`, `save_citations` implemented
- ✅ All writes in try/except, raise `StorageError` on failure
- ⚠️ Test block saves mock data and confirms rows in Supabase — **code validated (typecheck/lint/graceful-skip)**, but the live "rows exist" confirmation requires `SUPABASE_URL`/`SUPABASE_KEY`, which are not configured. The test block degrades gracefully and exits 0 with a clear message when creds are absent. To be re-run during Chunk 12 with real credentials.

---

## Chunk 8 — Competitor extractor — Completed 2026-05-31

### What was built

- Extended `src/pipeline/parser.py` with `extract_competitors(competitors, response) -> list[str]` and `extract_competitor_mentions(competitors, response) -> dict[str, MentionType]`.

### Acceptance criteria — all passed

- ✅ `extract_competitors` returns competitors present in the response
- ✅ `extract_competitor_mentions` maps each competitor to a `MentionType`
- ✅ Both case-insensitive (word-boundary matching)

---

## Chunk 7 — Brand mention detector — Completed 2026-05-31

### What was built

- Built `src/pipeline/parser.py` — `MentionType` enum (`recommended | mentioned | not_mentioned`) and pure `detect_mention(brand, response) -> MentionType`.

### Acceptance criteria — all passed

- ✅ `MentionType` enum with the three values
- ✅ `detect_mention(brand, response) -> MentionType`
- ✅ Case-insensitive matching
- ✅ `recommended` requires explicit language ("best", "recommend", "suggest", "top choice")
- ✅ Test block runs 5 sample responses and prints correct verdicts (all 5 OK)

---

## Chunk 6 — Prompt runner — Completed 2026-05-31

### What was built

- Built `src/pipeline/prompt_runner.py` — `run_prompts(prompts: list[str], engines: list[BaseEngine]) -> list[PromptResult]`, synchronous and order-stable.
- Built `src/storage/models.py` with the `PromptResult` TypedDict (`prompt`, `engine_name`, `response`, `timestamp`).
- Created package prerequisites: `src/pipeline/__init__.py`, `src/storage/__init__.py`, `src/audit/__init__.py`.

### Acceptance criteria — all passed

- ✅ Accepts `prompts: list[str]` and `engines: list[BaseEngine]`
- ✅ Returns `list[PromptResult]` with `prompt`, `engine_name`, `response`, `timestamp`
- ✅ `PromptResult` defined as a TypedDict in `src/storage/models.py`
- ✅ Test block runs 3 sample prompts across available engines and prints the result count (real engines skipped without keys; a keyless echo engine demonstrates the runner)

### Validation (Chunks 6–11)

- ✅ mypy (strict): `Success: no issues found in 18 source files`
- ✅ ruff check: `All checks passed!` — ruff format: `18 files already formatted`
- ✅ `python -m src.pipeline.prompt_runner` → 3 results collected
- ✅ `python -m src.pipeline.parser` → 5/5 verdicts correct, competitor extraction correct
- ✅ `python -m src.audit.report` → full markdown report with all required sections
- ✅ `python -m src.audit.technical_check` → 4 checks run live against `example.com`
- ⚠️ `python -m src.storage.db` → graceful skip (no Supabase credentials configured)

---

## Chunk 5 — Gemini engine — Completed 2026-05-31

### What was built

- Built `src/engines/gemini_engine.py` — `GeminiEngine(BaseEngine)` using `gemini-1.5-pro` via `google-generativeai`.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `GEMINI_API_KEY`, raises `ValueError` if missing
- ✅ Uses `gemini-1.5-pro`
- ✅ `ResourceExhausted` (rate limit), `DeadlineExceeded` (timeout), `GoogleAPIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

Note: documented `# type: ignore[attr-defined]` on `genai.configure`/`genai.GenerativeModel` — the deprecated `google-generativeai` package ships incomplete re-exports; names exist at runtime.

### Up next — Chunk 6: Prompt runner

Build `src/pipeline/prompt_runner.py` to send a list of prompts to all four engines and collect `list[PromptResult]` (TypedDict in `src/storage/models.py`).

---

## Chunk 4 — Perplexity engine — Completed 2026-05-31

### What was built

- Built `src/engines/perplexity_engine.py` — `PerplexityEngine(BaseEngine)` calling the Perplexity REST API (`model="sonar"`) via `httpx`, with citation extraction.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ `query()` returns response text
- ✅ `query_with_citations()` returns `tuple[str | None, list[str]]`
- ✅ Citations extracted from the response's `citations` field
- ✅ Test block prints both response and list of citation URLs
- ✅ On error returns `(None, [])`; never raises. mypy (strict) and ruff pass

---

## Chunk 3 — Anthropic engine — Completed 2026-05-31

### What was built

- Built `src/engines/anthropic_engine.py` — `AnthropicEngine(BaseEngine)` using `claude-3-5-sonnet-20241022`; extracts text from `TextBlock` content blocks.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `ANTHROPIC_API_KEY`, raises `ValueError` if missing
- ✅ Uses `claude-3-5-sonnet-20241022`
- ✅ `RateLimitError`, `APITimeoutError`, `APIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

---

## Chunk 2 — OpenAI engine — Completed 2026-05-31

### What was built

- Built `src/engines/openai_engine.py` — `OpenAIEngine(BaseEngine)` using `gpt-4o`.
- Created prerequisite `src/config/settings.py` + `src/config/__init__.py` — the single place that reads env vars (via `python-dotenv`); all engines load their keys from here, never `os.getenv` directly (§5 convention).
- Installed engine SDKs into `.venv`: `openai`, `anthropic`, `google-generativeai`, `httpx`, `python-dotenv`.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `OPENAI_API_KEY`, raises `ValueError` if missing
- ✅ Uses `gpt-4o`
- ✅ `RateLimitError`, `APITimeoutError`, `APIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

### Validation (Chunks 2–5)

- ✅ mypy (strict): `Success: no issues found in 9 source files`
- ✅ ruff check: `All checks passed!` — ruff format: `9 files already formatted`
- ✅ Each `python -m src.engines.<name>` runs without crashing (graceful `ValueError` skip when key absent)
- ✅ Invariant #1 verified: with dummy keys set, every `query()` returns `None` on auth/network failure and never raises; all four are `BaseEngine` instances

---

## Chunk 1 — Base engine interface — Completed 2026-05-31

### What was built

- Built `src/engines/base.py` — `BaseEngine` abstract base class defining the uniform engine contract (`query(prompt: str) -> str | None`, `ENGINE_NAME` class attribute).
- Built `src/engines/__init__.py` — re-exports `BaseEngine` for clean imports.
- Built `src/__init__.py` — makes `src` an importable package.
- Created prerequisite project files: `requirements.txt`, `.env.example`, `pyproject.toml` (ruff + mypy strict config), `.gitignore`.

### Acceptance criteria — all passed

- ✅ `BaseEngine` abstract class with abstract `query(prompt: str) -> str | None`
- ✅ `ENGINE_NAME` class attribute defined (default `"base"`, subclasses override)
- ✅ Docstring explains contract: returns response text or `None` on error, never raises
- ✅ Clean import from other modules (`from src.engines import BaseEngine` and `from src.engines.base import BaseEngine` resolve to the same class)

### Validation

- ✅ mypy (strict): `Success: no issues found in 3 source files`
- ✅ ruff check: `All checks passed!`
- ✅ ruff format --check: `3 files already formatted`
- ✅ Runtime: abstract base is non-instantiable; concrete subclass `query()` returns `str | None` as declared

---

### Up next — Chunk 2: OpenAI engine

Implement `src/engines/openai_engine.py` subclassing `BaseEngine`, loading `OPENAI_API_KEY`, using `gpt-4o`, catching rate-limit/timeout/API errors and returning `None`.
