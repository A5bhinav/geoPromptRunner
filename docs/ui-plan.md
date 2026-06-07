# GEO Audit — CSV Upload UI Plan

> ## ✅ STATUS (2026-06-06): IMPLEMENTED
>
> Phases A–E were built (build-log entry 2026-06-03): `src/prompts/csv_loader.py` (the exact `block,key,value,intent,persona` schema with multi-file merge + conflict detection), `src/api/` (FastAPI), and `web/` (Next.js upload → preview → progress → report). Wired to Supabase for durable runs; interrupted runs auto-resume on API startup.
>
> **Deviations from this plan worth knowing:**
> - Extra endpoints: `POST /audits/preview` (parse/validate without running) and `POST /audits/{id}/cancel`.
> - `config,engines` accepts more than planned: `openai_search`, `anthropic_search`, `gemini_grounded`, `google_ai_overviews`, and a keyless **`mock`** engine for end-to-end UI testing without API spend.
> - Extra config keys: `client_domains` (citation matching) and `judge` (run the LLM judge after the audit). Required keys are `client_name` + `category`.
> - Background runs use an in-memory registry + thread per run (the planned v1 simple option), with best-effort Supabase persistence and best-effort judge.
> - Auth/hosting remain open, as planned.
>
> Kept below as the design record; the CSV format section is still the accurate input contract.

*Plan for a front-end where you upload one CSV containing the prompts, the fact sheet, and the run config; the app parses it, runs the audit through the existing backend, and shows the report. Designed to wrap the current Python modules, not replace them.*

---

## 1 · Goal & scope

**Goal:** Drag one CSV into a clean web UI → it's parsed into queries + fact sheet + config → you confirm → the existing pipeline runs across the engines → the report renders in the browser.

**In scope (v1):** CSV upload, parse + validate + preview, kick off a run, live progress, results/report view.
**Out of scope (v1):** auth/multi-user, in-browser editing of the fact sheet, the LLM judge itself (the UI *renders* whatever the backend produces; the judge is a separate track). Auth and direct form-entry come later.

**Hard constraint:** integrate with the existing backend without rewriting working modules (respects the project's scope locks). The UI talks to a thin API layer that *imports and calls* the current `src/` code.

---

## 2 · The CSV format (the crux)

One CSV has to carry three different kinds of data — config, a fact sheet, and a list of queries. The clean way is a **leading `block` column that routes each row**, so one flat file stays human-editable in Excel/Sheets and maps directly onto the backend types.

**Columns:** `block, key, value, intent, persona`

- `block` = one of `config` | `fact` | `query` (routes the row)
- `config` rows → `key`/`value` pairs (run settings)
- `fact` rows → `key`/`value` pairs (fact-sheet content; all `fact` rows are concatenated into the text the judge reads)
- `query` rows → `key` = query id, `value` = the query text, plus `intent` and `persona`

### Example (Oura proxy)

```csv
block,key,value,intent,persona
config,client_name,Oura,,
config,category,smart ring,,
config,competitors,Whoop;Ultrahuman;Samsung Galaxy Ring;RingConn,,
config,engines,openai;anthropic;gemini,,
config,runs_per_query,3,,
fact,identity,"Smart ring for sleep/recovery; founded 2013 in Finland; CEO Tom Hale",,
fact,pricing,"Ring 5 $399 base / $499 premium + required $5.99/mo membership (as of 2026-06-02)",,
fact,features,"Sleep stages, HRV, SpO2, temperature; Ring 5 shipped 2026-06-04, 40% smaller than Ring 4",,
fact,watchlist,"Models often say Ring 4 is newest — wrong, Ring 5 launched 2026-05-28; stale price $349",,
query,q1,best smart ring 2026,category,health-conscious consumer
query,q2,Oura vs Whoop for sleep tracking,comparison,buyer
query,q3,is the Oura Ring worth it,brand,buyer
query,q4,how do I improve my sleep with a wearable,problem_aware,health-conscious consumer
```

### Why this design
- **One file, no nesting** — survives a round-trip through Excel/Google Sheets, which a JSON or multi-file approach doesn't.
- **Maps 1:1 onto existing types:** `query` rows → `Query(query_id, text, intent)` from `src/prompts/query_set.py`; `intent` validated against `IntentBucket`; `persona` is the new per-query modifier the gap analysis flagged. `config` → a run-config object. `fact` rows → a single fact-sheet string handed to the judge (which consumes it as text — exactly as designed).
- **Validation mirrors what already exists** in `load_query_set` (dedupe query ids, validate intents, require core config keys), so errors are caught at upload, not mid-run.
- The UI ships a **downloadable template CSV** so you never start from a blank file.

*Note: separators inside a cell use `;` (e.g., competitors, engines) so commas stay the CSV delimiter.*

### Multiple files (split uploads)

You won't always have everything in one CSV — the fact sheet might live in one file and the config + queries in another. The app accepts **any number of CSVs in a single upload** and treats them as **one audit**: it reads every file, then **merges all rows by `block`** into one combined dataset before validating. Because every file uses the same `block,key,value,intent,persona` schema, a "fact-sheet file" is just a CSV that contains only `fact` rows, a "queries file" contains only `query` rows, and a file can also mix blocks. The batch you upload together *is* the audit — no shared key across files is needed.

**Merge rules:**
- **`query` rows** — accumulated across all files in upload/row order; `query_id` must be unique across the whole batch (a duplicate across two files errors, same as within one file).
- **`fact` rows** — accumulated and concatenated into the single fact-sheet text the judge reads. More files simply add more facts.
- **`config` rows** — merged into one config. Same `key` with the *same* value in two files is fine; the same key with *different* values is a conflict and the upload errors (so a stray second `client_name` can't silently override the first).
- **Validation runs on the merged result**, not per file: required config keys present *somewhere* across the batch, intents valid, query ids unique, at least one query. A file with only `fact` rows and no queries is fine as long as another file supplies them.
- **Order-independent** — it doesn't matter which file is dropped first.

Missing pieces degrade exactly as before: no `fact` rows in any file → accuracy is "not assessed," everything else runs; no `query` rows anywhere → hard error. A single combined CSV is just the one-file case of this same merge, so nothing about the single-file flow changes.

Example split:
- `oura-run.csv` → `config` rows + 12 `query` rows
- `oura-facts.csv` → `fact` rows only

Uploaded together, they produce the identical audit to the single-file version in Section 2.

---

## 3 · Architecture

```
┌─────────────────────────┐        ┌──────────────────────────────┐        ┌────────────────────┐
│   Frontend (Next.js)    │  HTTP  │   API layer (FastAPI)        │ import │  Existing src/      │
│  upload · preview ·     │ ─────► │   NEW, thin wrapper          │ ─────► │  engines/ pipeline/ │
│  progress · report      │ ◄───── │   parse · run · status       │ ◄───── │  prompts/ audit/    │
└─────────────────────────┘  JSON  └──────────────┬───────────────┘        └────────────────────┘
                                                  │
                                                  ▼
                                          ┌───────────────┐
                                          │   Supabase    │  runs · results · verdicts · progress
                                          └───────────────┘
```

**The integration principle:** the FastAPI layer is the *only* new backend code, and it does nothing but parse the CSV, call the existing pipeline functions, and report progress. The current modules (`run_query_set`, the engine adapters, metrics, the report renderer, Supabase storage) are imported and used as-is. No working module gets rewritten — the UI is additive.

### New code introduced
| New piece | Where | Job |
|---|---|---|
| CSV loader | `src/prompts/csv_loader.py` | Parse the CSV → `QuerySet` + fact-sheet string + run config; validate (reuses `IntentBucket`, mirrors `load_query_set`). |
| API service | `src/api/` (FastAPI) | Endpoints; background run; progress; serve results. Imports existing pipeline. |
| Frontend | `web/` (Next.js app) | The UI. Talks to the API over HTTP only. |

### Endpoints (v1)
- `POST /audits` — upload **one or more** CSVs (multipart) → merge all files by `block` → parse + validate the combined set. On success: create a run row, start the pipeline in the background, return `{ run_id }`. On failure: return structured validation errors (with which file each error came from) for the preview.
- `GET /audits/{id}/status` — `{ state, completed, total, per_engine }` for the progress bar.
- `GET /audits/{id}/report` — the structured report data (scorecard, buckets, leaderboard, sources, flags).
- `GET /template.csv` — the downloadable starter CSV.

### Long-running runs
A full run is hundreds of sequential engine calls (minutes). So `POST /audits` returns immediately and the run executes in the background, writing progress to Supabase; the UI polls `GET /status`. (v1: FastAPI background task + a `runs` status row. Later: a real job queue like RQ/Celery if you need concurrency or restarts.) This is also why the storage redesign in the gap analysis matters — the UI needs a run that persists incrementally, not one that only returns at the end.

---

## 4 · UI screens & flow

Four screens, linear flow: **Upload → Preview → Progress → Report.**

**1. Upload.** A centered drag-and-drop card ("Drop your audit CSVs") that accepts **multiple files at once** (drop again or "add file" to append more), a "Download template" link, and below it a list of recent audits (client, date, status) to reopen. As files are added, each appears as a chip showing what it contributed (e.g., "oura-run.csv — config + 12 queries", "oura-facts.csv — fact sheet"), so you can see the batch is complete before continuing.

**2. Preview & validate.** After upload, show the **merged** result (across all files) before anything runs, in three panels/tabs:
- **Config** — client, category, competitors (as chips), engines selected, runs per query.
- **Fact sheet** — the concatenated facts (from every file) rendered readably, grouped by key.
- **Queries** — a table: id · intent (colored chip) · persona · text.
Each panel notes **provenance** (which file supplied it), so a missing fact sheet or query file is obvious. Validation errors render inline and red (bad intent, duplicate id across files, conflicting config key, missing config key), and the **"Run audit" button is disabled until the merged set is clean.** This screen is the safety net — you see exactly what the engine will do, assembled from all your files, before spending API calls.

**3. Progress.** A progress bar with a live counter ("142 / 540 calls"), per-engine status chips (running / done / failed), elapsed time, and a cancel button. Honest, calm, no spinner-theater.

**4. Report.** The deliverable, rendered:
- **§1 scorecard** — big cards: AI Visibility Grade (A–F), share-of-model, mention rate, citation rate, accuracy — client vs. top competitor.
- **§2** — mention/citation/prominence by intent bucket (table), and the accuracy-flags list (severity-colored) when a fact sheet was provided.
- **§3** — the competitive leaderboard with horizontal share-of-voice bars.
- **§4.4** — sources behind the category (ranked domains).
- **Export** — download as the client-facing report.

---

## 5 · Visual design direction ("good looking")

Aim: a modern analytics-tool look — data-dense but breathable, credible enough to put in front of a founder.

- **Stack for polish:** Tailwind CSS + **shadcn/ui** component library (handles the spacing, focus states, and accessibility that make a UI feel finished) + **Recharts** for the bars/charts.
- **Layout:** card-based, generous whitespace, `rounded-xl`, subtle shadows, a left sidebar for nav once there's more than one audit.
- **Type:** Inter (or system) — clear hierarchy, tabular numbers for the metrics.
- **Color:** neutral base (slate/zinc), one accent (indigo/violet) for primary actions; semantic green/amber/red reserved for pass/partial/fail and flag severity, so color always means status.
- **States:** every screen has explicit loading / empty / error states — the thing that separates "looks like a product" from "looks like a script with a webpage."
- Optional dark mode (shadcn gives it nearly free).

I can render an interactive HTML mockup of the upload + report screens so you can see this directly rather than imagine it — say the word.

---

## 6 · Tech stack recommendation

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js + TypeScript + Tailwind + shadcn/ui + Recharts** | Fastest path to a genuinely good-looking UI; component library does the polish; it's a real product UI you won't throw away. |
| API | **FastAPI (Python)** | Same language as the backend — it imports `src/` modules directly, no rewrite. Async-friendly, auto-generated API docs, Pydantic validation. |
| DB | **Supabase** (existing) | Already wired; extend the schema for runs/results/verdicts/progress (the redesign already on the roadmap). |
| Hosting (later) | Frontend on Vercel; API on Render/Fly/Railway | Standard split; decide at deploy time. |

**Alternative considered — Streamlit:** pure-Python, no frontend code, you'd have a working internal tool in a day. **Rejected for v1** because you've said this is heading toward a product; Streamlit caps out on polish and isn't something you'd ship to clients. Worth knowing it exists if you want a throwaway internal version *this week* while the real UI is built. The FastAPI backend works under either, so choosing Streamlit now wouldn't waste the API work.

---

## 7 · Build phases

Each phase is independently testable; the UI can't outrun the backend, so backend-first.

- **A · CSV format + loader** (`src/prompts/csv_loader.py`) — parse + validate; unit-test against the Oura example. No UI. *Unblocks everything.*
- **B · API layer** (`src/api/`) — wrap the existing pipeline; `POST /audits`, `GET /status`, `GET /report`, `GET /template.csv`; background run + Supabase progress.
- **C · Frontend: Upload + Preview** — drag-drop, call the API, render the parsed config/fact/queries with inline validation.
- **D · Progress screen** — poll `/status`, live counter.
- **E · Report screen** — render the structured report; export.

Dependency note: the **accuracy cells** in §1/§2 stay empty until the **LLM judge** exists (separate track), and **citation cells** until cross-engine citations are built. The UI renders whatever's present and shows "not assessed" otherwise — so it's worth building the UI in parallel; it simply lights up more cells as those land.

---

## 8 · Open decisions

- **One CSV vs. multiple files** — *resolved:* multiple files supported (Section 2, "Multiple files"). Upload the fact sheet and the config/queries as separate CSVs or as one combined file; the parser merges them either way.
- **Background runs: simple task vs. job queue** — start simple (FastAPI background task); add a queue only if you need parallel runs or crash recovery.
- **Auth** — none in v1 (internal). Add before any client touches it.
- **Where the run config's `engines` list comes from** — CSV per-audit (planned) vs. a global setting. CSV is more flexible; keep it there.
- **Hosting / deploy targets** — defer to deploy time.

---

## 9 · How this connects to the rest of the project

- The **CSV is the input contract** the gap analysis said was missing (query-set sourcing was fully manual). This formalizes it.
- The **`persona` column** delivers the per-query modifier field the deliverable's §6.1 wants.
- The **progress-persisting run** is the same incremental-storage need the gap analysis flagged for the orchestrator.
- The **report screen** is the deliverable spec (`engine-gap-analysis.md` §"deliverable test") rendered in a browser instead of a doc.

So this UI isn't a side quest — it's the front door to the same pipeline, and it forces three backend improvements that were already on the list.
