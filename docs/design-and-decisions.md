# GEO Engine — Design & Decisions

*Single reference for the audit engine: what it is, the design decisions behind it, current status, and what's next. **Updated 2026-06-06** to reflect the build sprint — the original build order is now essentially complete, so this doc has shifted from "what to build" to "how it works and what remains."*

**Related docs in this folder**
- `engine-gap-analysis.md` — the original gap analysis (now historical; drove the build)
- `ui-plan.md` — the CSV-upload UI plan (now implemented; see its status banner)
- `left.md` — the team's live "what's left" list
- `build-log.md` — append-only build record
- `fact-sheet-template.md` / `fact-sheet-example-oura.md` — fact sheet template + worked example
- `project.md` — the original build spec / chunk plan

---

## 1 · What this is

The engine is the **measurement layer** behind the GEO audit service: it asks the AI answer engines the questions a client's buyers actually ask and measures how the client shows up versus competitors. The audit method has 8 steps; **the software powers Step 1 (baseline measurement) and Step 5 (competitive benchmark)** — the "here's what ChatGPT says about you vs. your competitor" demo. Steps 2–4 and 6–8 remain analyst work by design.

**Niche (updated):** early-stage **B2C consumer startups** in the Berkeley/SV ecosystem. The sample client throughout the codebase is "Centsible," a budgeting app, benchmarked against YNAB / Copilot / Rocket Money / Monarch Money.

The audit **report is the engine's spec** — that framing drove the build, and the report now renders in both the CLI (markdown) and the web UI (charts).

---

## 2 · Current state (2026-06-06)

The build order from the original version of this doc (items 1–11) is **done**, per `left.md` and the build log:

- **Engines / surfaces:** parametric adapters (openai, anthropic, gemini, perplexity) **plus live-retrieval variants** — `openai_search`, `anthropic_search`, `gemini_grounded`, and **Google AI Overviews via SearchApi.io** (no official API; SERP-provider capture). `--surface search` switches the audit to the retrieval surfaces. Cross-engine citations captured; Gemini grounding redirect URLs resolved to real domains.
- **Detection:** the **LLM judge** (Section 4) replaced regex as the primary path; the unified report runs on judge output with regex as fallback.
- **Pipeline:** `orchestrator.run_audit` — incremental per-query persistence, **resume of interrupted runs**, cost estimation with `max_cost` abort, progress output; `run_teaser` for the fast category/comparison demo. Temperature pinned to 0 across engines.
- **Analysis:** mention/citation rates by bucket, share-of-voice, **losing queries**, sources-behind-the-category, **competitor discovery** (unnamed brands surfaced), **cadence/trend comparison** (`compare <before> <after>`, `report --previous`), rubric capture → **Step-6 prioritized roadmap**, **A–F visibility grade** (prominence-weighted, severity-discounted by accuracy flags), per-query `weight` + `persona`.
- **Storage:** Supabase; run-scoped tables incl. `judgments` (JSONB brands/flags — re-render reports without re-paying the judge). Schema files `schema.sql` … `schema_v5.sql`.
- **Interfaces:** a full **CLI** (`audit`, `teaser`, `report`, `compare`, `discover`, `technical`, `roadmap`, `runs`, `due`) and the **CSV-upload web app** (Next.js + FastAPI; see `ui-plan.md`).
- **Quality:** 50–65 tests (engines, parser, judge, csv-loader, orchestrator, metrics, persistence, unified report); strict mypy/ruff conventions maintained.
- **Keys:** all engine keys are configured, including Perplexity and SearchApi. ⚠️ **All secrets were pasted in plaintext in chat at some point — rotate them** (tracked in `left.md` §5).

What's genuinely open (detail in `left.md`): the **real proxy audit → real gold set → real fact sheet** loop (Section 6), **schema normalization** (first-class clients/competitors/versioned query-set tables — needed for multi-client and clean cross-run trending), optional **competitor-as-subject runs**, and deeper **calibration coverage** (flag *type*-level matching).

---

## 3 · The deliverable, and what the engine produces

The report's engine-powered cells (§1 scorecard incl. grade, §2 by-bucket + accuracy flags, §3 leaderboard + trend, §4.4 sources, §6 appendix incl. persona column) are now all produced by the pipeline — judge-aware with regex fallback. The remaining honesty caveat: **accuracy cells are only as good as the fact sheet** (none real yet), and **trust in the judge is only as good as calibration** (gold set still placeholder).

---

## 4 · The LLM judge (BUILT — `src/pipeline/judge.py`)

### What it is
The judge replaced the regex detection as the report's primary path. The runner collects raw answers; the **judge reads each answer and returns structured fields**; metrics aggregate those. It's a separate pass — stored answers can be **re-judged any time without re-querying the engines** (and the `judgments` table makes re-renders free).

### Implementation facts
- **Model:** one held-constant judge — `gpt-4o` via `OPENAI_API_KEY` (`JUDGE_MODEL` env-overridable). Held-constant matters more than which model; for stricter neutrality it can be set to a model that isn't a measured surface.
- **Determinism:** temperature from `ENGINE_TEMPERATURE` (0), `response_format={"type":"json_object"}` (forced JSON).
- **Never-raise:** a failed call degrades to `assessed=False` ("not assessed"), never crashes a run.
- **No outside knowledge:** the system prompt forbids it; accuracy is judged *only* against the provided fact sheet (consumed as plain text, exactly as designed).
- **One pass, all brands:** client + competitors scored together so prominence stays *relative* ("who got named first"). Brand parsing is name-keyed, case-insensitive, with safe enum coercion.
- **Dedup cache:** identical (query, answer) pairs are judged once — multi-run cycles don't multiply judge spend.
- **Types live in the data layer** (`storage/models.py`): `Prominence` (recommended_first / mid_pack / buried / also_ran / absent), `Framing` (positive / neutral / negative), `AccuracyFlagType` (wrong_pricing / missing_or_invented_feature / competitor_confusion / identity / stale), `Severity` (high / med / low).

### Accuracy is asymmetric — client only (unchanged decision)
Competitors get present/prominence/framing only; accuracy flags are produced **only for the client and only when a fact sheet is supplied**. One fact sheet per audit, never competitor sheets; "confused you with X" is caught from the *client's* sheet.

### Calibration (BUILT — `src/pipeline/calibration.py`)
`load_gold_set` → `calibrate(judge, gold)` → agreement report (present / prominence / framing / flag-detection percentages). **This is the trust mechanism** — and it's currently running on 3 placeholder items, so the judge is *plausible but uncalibrated* until the real gold set exists (Section 6). Known v1 limitation: the flag check is **binary** (flagged-when-expected), not type/severity-level.

---

## 5 · The fact sheet (unchanged design; still no real one)

Ground truth for the judge's accuracy checks only — present/prominence/framing need no sheet. One per audit (client only), optional (no sheet → accuracy "not assessed," everything else runs), built ideally during Step-0 intake, falsifiable facts only, blank-is-safe. Template: `fact-sheet-template.md`; worked B2C example: `fact-sheet-example-oura.md`. In the CSV upload, `fact` rows concatenate into the sheet text; the judge reads it as-is.

---

## 6 · Testing plan → the calibration loop (UPDATED)

The pipeline and harness now exist, so the plan is sharper than the original "manual proxy run":

1. **Run the proxy audit with the real pipeline** — `python -m src.cli audit <queries.json> --domains <domain>` (or the web UI; `--surface search` for retrieval surfaces). Answers persist to Supabase; runs are resumable; cost-estimated upfront.
2. **Build the gold skeleton from stored answers** — each answered result becomes a JSON item with empty labels (mechanical; scriptable).
3. **Hand-label ~20–40 answers** — humans only (independence is the point). Use the implemented vocabulary: `present` bool; `prominence` ∈ recommended_first/mid_pack/buried/also_ran/absent; `framing` ∈ positive/neutral/negative (**no "n/a"** — absent brands get `neutral`); per-item `expect_accuracy_flags` boolean (only meaningful when the item carries a `fact_sheet`). Canonical format: `data/sample_gold.json` / `docs/gold-set-template.json`.
4. **Run calibration** — `python -m src.pipeline.calibration` → the agreement table. That's the number you quote when a founder asks "how do I trust an AI grading AIs?"
5. **Iterate** — disagreements tighten label definitions or the judge prompt; have both founders label an overlap subset to check inter-rater agreement first.

Order per `left.md`: **real proxy audit → real gold set → real fact sheet.** Turns the judge from "plausible" into "calibrated."

---

## 7 · Front end (BUILT)

`web/` (Next.js + Tailwind + shadcn-style components) talking to `src/api/` (FastAPI). Flow: drop one **or many** CSVs (`block,key,value,intent,persona`; multi-file merge with conflict detection) → preview with per-file provenance + inline validation → background run with live progress and cancel → chart-rich report (donut, bars) → recent audits. Durable runs in Supabase; **interrupted runs auto-resume on API startup**; a keyless `mock` engine exercises the whole UI without spending API calls. Endpoints: `GET /template.csv`, `POST /audits/preview`, `POST /audits`, `GET /audits`, `GET /audits/{id}/status`, `GET /audits/{id}/report`, `POST /audits/{id}/cancel`. Deliberately out of scope still: auth/multi-user, hosting/deploy.

---

## 8 · Build order → status

| # | Item | Status |
|---|---|---|
| 1 | LLM judge (prominence/framing/accuracy + typed flags) | ✅ built + persisted + unified into report |
| 2 | Cross-engine citations + AI Overviews | ✅ built (search/grounded variants; SearchApi.io) |
| 3 | Losing-queries view | ✅ built |
| 4 | Client+competitor leaderboard | ✅ real via one-pass judge (competitor-as-subject runs optional, not built — decide if needed) |
| 5 | Teaser/demo mode | ✅ built (CLI + orchestrator) |
| 6 | Schema redesign (clients/competitors/versioned query sets) | ⬜ **open** — run-scoped tables only; needed for multi-client scale |
| 7 | Orchestrator + dry run | ✅ built (incremental persist, resume, cost budget) |
| 8 | Cadence re-run + comparison | ✅ built (`compare`, `--previous`, `due` helper; no auto-scheduler by design) |
| 9 | Rubric capture + roadmap + A–F grade | ✅ built |
| 10 | WAF/UA technical-check fix | ✅ built (incl. SPA-shell rendering check) |
| 11 | Tests | ✅ 50–65 passing; calibration coverage still thin |

---

## 9 · Open / next

1. **Rotate all API secrets** (operational, urgent — they hit chat in plaintext).
2. **Real proxy audit → real gold set → real fact sheet** — the calibration loop (Section 6). The machine is built; this is the labeled data only the founders can produce.
3. **Schema normalization** — first-class clients/competitors/versioned query-set tables.
4. **Calibration depth** — flag type/severity-level agreement; more harness tests.
5. **Competitor-as-subject runs** — optional; decide whether it's needed before building.
6. **Front-end productionization** (auth, hosting) — when a client will touch it.

---

## Decisions log (quick reference)

| Decision | Call |
|---|---|
| What the software automates | Steps 1 & 5; Steps 2–4, 6–8 analyst work |
| Niche | **B2C consumer startups, Berkeley/SV** (pivoted from B2B SaaS) |
| Detection | LLM judge primary, regex fallback |
| Judge model | One held-constant `gpt-4o` (env-overridable), temp 0, forced JSON, never-raise, no outside knowledge |
| Judge scope per call | All brands in one pass (prominence is relative); identical answers judged once |
| Accuracy checking | Client only; competitors get mention/prominence/framing only |
| Fact sheets | One per audit (client's); optional; consumed as text; none real yet |
| Gold set format | **JSON** (`GoldItem` in `calibration.py`); framing has no "n/a" — absent ⇒ neutral; flag expectation binary (v1) |
| AI Overviews | Captured via SearchApi.io (no official API); skipped without key |
| CSV input contract | `block,key,value,intent,persona`; multi-file merge; conflicts error; `mock` engine for keyless testing |
| Front end | Next.js + FastAPI, built; auth/hosting deferred |
| Scheduling | `due` helper only — no auto-scheduler (Phase-1 non-goal) |
