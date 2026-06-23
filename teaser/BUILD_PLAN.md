# GEO Teaser Auto — Technical Build Plan

**Status:** Draft v0.2 — rewritten after reviewing the `geoPromptRunner` platform
**Owner:** Josh + co-founder
**Last updated:** 2026-06-20

> **What changed in v0.2:** The "prompt runner" turned out to be a near-complete **GEO measurement platform** (`github.com/A5bhinav/geoPromptRunner`) — it already runs queries across all engines, runs an LLM-judge detection layer, computes mention/citation/share-of-voice metrics, **already computes the losing-queries list and the wrong-claim accuracy flags**, grades A–F, stores to Supabase, and exposes an HTTP API plus a Next.js report UI. teaserAuto is therefore **not** a from-scratch pipeline — it's a thin layer that (1) turns a URL into a valid audit input, (2) calls the platform's API, (3) selects the lead finding, and (4) renders + reviews a PDF. Most of §3–§5 of the old plan collapsed.

---

## 0. Purpose & framing

Build a system that turns **one input (a prospect's website URL)** into **one sendable teaser PDF** proving, with real AI-engine answers, that engines recommend a competitor and leave the prospect out on the questions their buyers ask.

**The deliverable is a PDF file.** No hosted page, no link the prospect clicks. teaserAuto does **no sending and has no email-tool integration** — you review, download the PDF, and email it yourself. Nothing auto-sends; every teaser passes a human gate.

### Decisions locked from the clarifying round

| Question | Answer | Consequence |
|---|---|---|
| Engine execution | **Co-founder's runner** | It's the `geoPromptRunner` platform. We integrate via its **HTTP API** (§4a). |
| Stack (the new layer) | **My recommendation** | TypeScript/Next.js for teaserAuto's UI + render; the engine stays Python (it already is). Justified in §2. |
| Volume | **≤20/day, quality-first** | Lean. No queue/anti-bot infra. Human reviews every teaser. |
| Proof realism | **Derived from genuine answers; live screenshots not required** | Proof = a branded re-render of the platform's **verbatim captured answer** (from `/answers.md` / `/results.csv`). |
| Output | **PDF only** | No email copy, no sending, no email-tool integration. |

### What already exists (the `geoPromptRunner` platform)

This is the single most important input to the plan. The platform already provides, as a running service:

- **Engine execution** across `openai` (ChatGPT), `anthropic` (Claude), `gemini`, `perplexity`, and `ai_overviews` (Google AI Overviews via SearchApi.io), with **search/grounded variants** and a `mock` engine for keyless demos. Each query runs **multiple times per cycle** (`runs_per_query`) to average out nondeterminism; runs aggregate to one verdict per `(query, engine)` **cell**. Concurrent fan-out, resumable, cost-guarded.
- **Detection layer** — an **LLM judge** producing per-brand `present` / `prominence` (`recommended_first → mid_pack → buried → also_ran → absent`) / `framing` (`positive/neutral/negative`), plus a **regex mention fallback** when the judge can't run. Calibrated against a hand-labeled **gold set** (the labeling infra, gold sets, and calibration guide already exist in the repo).
- **The exact teaser findings, already computed** in the report:
  - **`losing_queries`** — the `(query, engine)` cells where the **client is absent but a competitor is present**. This *is* the teaser's lead finding + pattern table.
  - **`accuracy_flags`** — the **wrong-claim branch**: typed (`wrong_pricing`, `missing_or_invented_feature`, `competitor_confusion`, `identity`, `stale`), with `severity` and `claim`/`reality`. Requires a per-client **fact sheet**.
  - **`scorecard`** — A–F visibility grade, client share-of-model, top competitor + their share, client vs. competitor mention rate, citation rate.
  - **`leaderboard`**, **`by_bucket`** (mention/citation rate per funnel bucket), **`sources`** (top cited domains).
- **Storage** in Supabase, **resumable** runs, spend guards (`MAX_AUDIT_COST_USD`, etc.).
- **HTTP API** (FastAPI, `X-API-Key` auth) — see §4a for the exact endpoints.
- **An existing Next.js report UI** (Upload → Preview → Progress → Report). The Report screen is the reference design for our PDF layout.

**Implication:** teaserAuto does **not** rebuild query execution, detection, metrics, losing-query logic, or storage. It consumes them. See §1.

### What teaserAuto still has to build (the actual scope)

1. **Resolver + query-set generator** — URL → company profile (name, category, competitors, domains) → a **teaser-grade, valid audit input** (the platform's CSV format). *This is the one genuinely new hard part* (§4b), because the platform expects a **human-approved, locked** query set and we want to generate one from a URL at volume.
2. **Lead-finding selector** — rank the platform's `losing_queries` (and optionally `accuracy_flags`) to pick the hero finding + 2 for the pattern table (§4c).
3. **Proof card renderer** — join the chosen losing cell back to the **verbatim query + answer text** and render an annotated card.
4. **Teaser PDF renderer** — fill the one-pager template → PDF.
5. **Review + download UI** — the human gate.

---

## 1. System architecture

### 1.1 Component overview

```
   URL
    │
    ▼
┌─────────────────────────────────────────────┐
│ teaserAuto — the NEW layer (TypeScript/Next) │
│                                              │
│  1. Resolver        URL → company profile    │   Firecrawl/Jina + Claude
│     (name, category, competitors, domains)   │
│        │                                     │
│        ▼                                     │
│  2. Query-Set Gen   profile → audit-input    │   methodology (query-generation-plan.md)
│     CSV (config + query rows [+ fact rows])  │   → teaser-grade, human-confirmable
│        │                                     │
│        ▼                                     │
│  ┌───── calls the platform HTTP API ──────┐  │
│  │  POST /audits  (multipart CSV)         │──┼──▶ ┌──────────────────────────────┐
│  │  GET  /audits/{id}/status  (poll)      │◀─┼─── │   geoPromptRunner PLATFORM    │
│  │  GET  /audits/{id}/report  → payload   │◀─┼─── │   (co-founder's, Python)      │
│  │  GET  /audits/{id}/answers.md|results  │◀─┼─── │   engines · judge · metrics · │
│  └────────────────────────────────────────┘  │   │   losing_queries · flags ·    │
│        │ ReportPayload + verbatim answers     │   │   scorecard · Supabase        │
│        ▼                                      │   └──────────────────────────────┘
│  3. Finding Selector  rank losing_queries     │
│     → lead + 2 table rows                      │
│        │                                       │
│        ▼                                       │
│  4. Proof Renderer    verbatim answer → card   │
│        │                                       │
│        ▼                                       │
│  5. Teaser Renderer   template → PDF file      │   internal HTML→PDF (Playwright)
│        │                                       │
│        ▼                                       │
│  ╔═══════════════════════════════════════════╗ │
│  ║ HUMAN GATE — Review UI: approve/edit/reject ║ │
│  ╚═══════════════════════════════════════════╝ │
│        │ approved                               │
│        ▼                                        │
│  6. Export            download approved PDF      │   NO sending — you email it
└─────────────────────────────────────────────────┘
```

### 1.2 Where each step lives

- **teaserAuto** is its own small Next.js app (Vercel + Supabase). It owns the resolver, query-set generator, selector, proof/PDF renderers, and the review UI.
- **The platform** runs as a separate Python service (it already does), reachable over HTTP with an `X-API-Key`. teaserAuto treats it as a black-box audit engine: *submit an audit input, poll, read the report + answers.*
- **Adapter seam:** all platform calls go through one `PlatformClient` module. A `MockPlatformClient` returns fixture report payloads (lifted from the repo's `data/*_gold.json` and the `build_report` `__main__` sample) so the whole teaserAuto flow can be built and demoed **before the platform is deployed/keyed**.
- **Rendering:** the teaser is an internal HTML/React template (never publicly served) printed to a **PDF** via Playwright/Puppeteer, stored in Supabase Storage. The review dashboard shows an embedded PDF preview.
- **Export:** the system's job ends at a downloadable PDF. No sending, no email copy, no email-tool integration.

### 1.3 teaserAuto run lifecycle

```
queued → resolving → generating_queryset → awaiting_input_confirm (optional human check)
       → submitted → running (poll platform) → report_ready
       → selecting → rendering → awaiting_review → approved → exported
                                              ↘ rejected (reason)
       ↘ failed (step + error)
```

The optional `awaiting_input_confirm` gate lets a human eyeball the auto-generated competitors + query set before paying for an audit (cheap insurance against a wrong competitor poisoning the whole teaser). Defaultable on/off per Open Decision §7.

---

## 2. Tech stack recommendation

**teaserAuto: TypeScript / Next.js on Vercel + Supabase. The platform stays Python (unchanged).**

- The engine is already Python with its own deploy; we don't touch it beyond the API. teaserAuto is a thin UI + render + orchestration layer where TS shines: React PDF templates, a small review dashboard, LLM calls for the resolver. Matches your connected Vercel/Supabase tooling and the platform's *own* frontend (also Next.js), so the two UIs could even share components later.
- **Supabase:** teaserAuto gets its own tables (prospects, generated query sets, findings, teasers, review state). It can use the **same Supabase project** as the platform (project_ref `hohveqgemavghcpfjdiy`) or a separate one — see Open Decision §7. It does **not** duplicate the platform's `audit_runs`/results/judgments tables; it references a run by `run_id`.
- **One exception worth weighing:** the **query-set generator** encodes the *shared methodology* (`query-generation-plan.md`) that arguably belongs in the platform repo (Python), so the co-founder's audits and your teasers generate query sets the same way. Options in Open Decision §7 (#2).

---

## 3. Data model

teaserAuto stores only what the platform doesn't. The platform owns engine answers, judgments, and the report; we reference its `run_id` and cache the report payload.

### 3.1 `prospects`
```
id, url (unique), name, category,
competitors        jsonb   -- [{name, aliases[], confirmed:bool}]
client_domains     text[]  -- for citation matching
product_claims     jsonb   -- [{claim, source_url}]  (optional; seeds a fact sheet if we do wrong-claim)
source_pages       jsonb   -- [{url, type, fetched_at}]
resolved_at, resolver_model, created_at
```

### 3.2 `query_sets` (what we generated + sent to the platform)
```
id, prospect_id,
version            text    -- e.g. "teaser-2026-06-20"
queries            jsonb   -- [{query_id, text, intent, weight, persona}]  (platform Query shape)
fact_sheet         text|null  -- markdown, only if doing the wrong-claim branch
input_csv          text    -- the exact CSV submitted (provenance)
confirmed_by       text|null  -- human who eyeballed it (if the confirm gate is on)
created_at
```

### 3.3 `audit_refs` (pointer to a platform run)
```
id, prospect_id, query_set_id,
platform_run_id    text    -- the platform's run_id
engines            text[]  -- which engines were run
surface            text    -- "parametric" | "search"
status             text    -- mirrors platform status: queued|running|done|failed|cancelled
report_payload     jsonb   -- cached GET /report response (ReportPayload)
report_fetched_at  timestamptz
created_at
```
> We cache `ReportPayload` so the teaser is reproducible even as the platform/engines drift. The shape (from `src/api/reports.py`): `scorecard`, `leaderboard`, `by_bucket`, `accuracy_flags`, `sources`, **`losing_queries`**, plus `detection: "judge"|"regex"`, engines, competitors, run_date, query_set_version.

### 3.4 `findings` (our selection over the report)
```
id, prospect_id, audit_ref_id,
role               text    -- lead | table
source             text    -- losing_query | accuracy_flag
query_id, engine_name, intent, competitor    -- from the losing_queries row
verbatim_query     text    -- joined from answers (the platform `prompt`)
verbatim_answer    text    -- joined from answers (the platform `response`) — feeds the proof card
rank_score         numeric
created_at
```
> `losing_queries` rows carry only `{query_id, intent, engine_name, competitor}`. The **verbatim query + answer text** for the proof card are joined in from `GET /audits/{id}/answers.md` (or `/results.csv`, or the platform's `get_query_results`) by matching `query_id` + `engine_name`.

### 3.5 `teasers`
```
id, prospect_id, audit_ref_id,
lead_finding_id, table_finding_ids uuid[],
headline, lead_sentence,
headline_number    jsonb   -- {company:"0/8", competitor:"8/8", n:8}  (derived from losing_queries / leaderboard)
stakes_line, cta,
proof_asset_ids    uuid[],
pdf_url            text    -- Supabase Storage url of the generated PDF (THE deliverable)
status             text    -- draft | approved | rejected | exported
shelf_life_expires_at timestamptz,
baseline_snapshot  jsonb   -- frozen ReportPayload subset for the 90-day re-run
approved_by, reviewed_at, reject_reason, created_at
```

### 3.6 `assets`
```
id, prospect_id, kind (proof_card|pdf), storage_path, meta jsonb, created_at
```

### 3.7 Reference data already in the platform repo (reuse, don't recreate)
- **Query methodology + question-set schema** → `docs/query-generation-plan.md`, `docs/oura-query-set-v1-draft.md`, `data/*_queries*.json`, `src/prompts/intent.py` (the 5 funnel buckets). Drives §4b.
- **Answer-analysis schema (objective primitives → judge → scoring)** → already implemented in `src/pipeline/{judge,metrics,judge_metrics}.py`. We consume its output.
- **Fact sheet + truth table** → `docs/fact-sheet-template.md`, `fact-sheet-fort.md`, `fact-sheet-example-oura.md`. Drives the (manual) wrong-claim branch.
- **Gold set + labeling/calibration** → `docs/labeling-guide.md`, `grade-calibration-guide.md`, `data/*_gold.json`. This is our **detection eval set — already built** (§4c).

---

## 4. The hard parts — options & tradeoffs

### (a) Platform integration (was: "build the runner") — now mostly settled

The platform exposes exactly the seam we need. The work is integration + deployment, not building.

**The API (from `src/api/app.py`):**
| Endpoint | Purpose |
|---|---|
| `POST /audits` (multipart CSV files) | Start an audit → `{run_id}`. 422 on invalid input (with structured errors), 402 if over spend cap, 413 over size/query/engine caps. |
| `GET /audits/{run_id}/status` | Progress + per-engine state. |
| `GET /audits/{run_id}/report` | **`ReportPayload`** — the teaser's primary input. |
| `GET /audits/{run_id}/answers.md` / `/results.csv` | Verbatim query + every answer + judge verdict — for the **proof card**. |
| `POST /audits/{run_id}/cancel`, `GET /audits`, `GET /template.csv` | Manage / list / template. |

Auth: `X-API-Key` header. Caps: `MAX_QUERIES=200`, `MAX_ENGINES=8`, `MAX_RUNS_PER_QUERY=5`, per-audit + cumulative USD spend guards.

**Input format (CSV, from `src/prompts/csv_loader.py`):** rows of `block,key,value,intent,persona` where `block ∈ {config, fact, query}`. `config` carries `client_name`, `category`, `competitors`, `client_domains`, `engines`, `runs_per_query`, `judge`. `fact` rows build the fact sheet (wrong-claim branch). `query` rows are the buyer queries with their `intent` bucket + `persona`. teaserAuto's job (§4b) is to *generate this CSV*.

**Integration options:**
| Option | Approach | Verdict |
|---|---|---|
| **A. Separate consumer** *(recommended)* | teaserAuto is its own app; calls the platform's HTTP API. The platform stays the co-founder's, deployed independently and keyed. | **Recommended.** Clean ownership boundary; the API is already exactly right; decouples your teaser product from the audit engine's roadmap. |
| **B. Extend the platform repo** | Add teaser endpoints to its FastAPI app + teaser screens to its Next.js frontend. | Tighter reuse (Supabase, report payload, answers in one place) but couples your product to the co-founder's codebase and release cadence. |
| **C. Import as a library** | Vendor the Python pipeline into a shared service. | Most coupling; only if you merge the two products. |

**Recommendation: A**, with a `MockPlatformClient` so teaserAuto is built before the platform is deployed. The one shared concern — **query-set generation** — see §7 #2.

**Open questions for the co-founder:** Is the API deployed somewhere (URL), or only local (`run-api.sh` on :8000)? Is a `GEO_API_KEY` set? Does it run the **search surface** by default (the teaser needs live-retrieval engines, not parametric memory — `--surface search`)? Which Supabase project should teaserAuto use? Are the B2C-consumer query examples a problem for **B2B-SaaS** prospects (see §7 #4)?

### (b) URL → teaser-grade query set — *the actual new hard part*

The platform expects a **locked, versioned, human-approved** query set built per the methodology (5 funnel buckets: `problem_aware`, `category`, `comparison`, `brand`, `adjacent_authority`; weighted; hard composition rules; a *read-aloud approval gate*). That process is designed for a paid audit, not volume cold outreach. teaserAuto needs to generate a **good-enough teaser instrument** from a URL — accepting it's a thin slice, not the full locked audit set.

**Options:**
| Option | Approach | Pros / Cons |
|---|---|---|
| **A. LLM-generate the full bucketed set, human-confirm** *(recommended)* | Resolver → Claude generates ~6–8 queries weighted to `category`/`comparison` buckets (where teasers land), following the methodology's hard rules (≥2 comparison queries leave the client unnamed; competitors named; verbatim buyer language). Human eyeballs competitors + queries at the `awaiting_input_confirm` gate. | Fast, cheap, on-method. The confirm gate catches the expensive errors. Not the full 45-query instrument — fine for a teaser. |
| **B. Template/library of category query patterns** | Maintain reusable query templates per vertical; fill in `{company}`/`{competitor}`/`{category}`. | More deterministic, less LLM variance; needs a growing template library; weaker on novel categories. |
| **C. Full methodology automation** | Reproduce the entire locked-set process automatically. | Overkill for a teaser; the read-aloud gate doesn't scale to 20/day. |

**Recommendation: A**, reusing the methodology rules from `query-generation-plan.md` as the generation spec, with the human confirm gate **on** by default at this volume. The competitor list is the highest-risk output — confirm it (Open Decision §7 #5).

**Wrong-claim branch:** stays **manual and off the auto-path**, exactly as you wanted — *and the platform already supports it*: provide `fact` rows (a fact sheet) and the judge emits `accuracy_flags`. So a human-curated fact sheet upload is all that's needed to light up the wrong-claim findings for a specific prospect. We don't auto-generate fact sheets in the MVP.

### (c) Detection accuracy — mostly *reuse*, not build

The detection layer (judge + metrics + losing-query logic) already exists and is **already calibrated against a gold set**. Our job is to *consume it correctly and gate on it*, not re-implement it.

- **Trust the judge, but gate.** The calibration notes say the **judge over-flags**; the platform already treats human labels as truth. So: every teaser passes the human review gate, and every printed claim traces to a **verbatim answer span** the reviewer sees. This is the same asymmetric-error policy as before — the expensive error is a false "client absent / competitor recommended," and the human catches it.
- **Run the judge, not regex.** `losing_queries` and `accuracy_flags` are far stronger on the **judge** path (`detection: "judge"`); the regex fallback gives mention-only with no grade/accuracy. teaserAuto should require the judge ran (i.e., the platform had `OPENAI_API_KEY` + `judge=true`) before trusting a finding; flag `detection: "regex"` reports as "needs manual proof."
- **Eval set already exists.** `data/*_gold.json` + the labeling/calibration guides are the labeled set my v0.1 plan said to build. **Reuse it.** Before trusting auto-selected findings at volume, run the platform's calibration against the gold set and confirm the judge's losing-query precision on the **client-absent** verdict meets a bar (e.g. ≥0.95 precision on printed claims). Sample shipped teasers back into the gold set over time.
- **What we *do* build:** the confidence→`needs_review` gating in our selector, and a thin "show me the verbatim answer behind this claim" view in the review UI.

### (d) Proof rendering — unchanged, and easy here

Proof = a branded re-render of the **verbatim captured answer** (your locked choice). The platform hands us the exact answer text via `/answers.md` / `/results.csv` (`prompt` = the query, `response` = the verbatim answer). The `ProofRenderer` is a module behind an interface:
- **MVP:** `BrandedCardRenderer` — render the verbatim answer with the competitor highlighted, the client's absence annotated, engine + query + `run_date` + citations attributed.
- **Later / hero engine:** if the platform ever captures real screenshots, slot a `ScreenshotAnnotator` for the hero engine; cards stay for the table. No other code changes.
- **Hero engine:** prefer **Perplexity or Google AI Overviews** (clean, citation-rich, re-renders authoritatively); cite ChatGPT/Gemini/Claude in the text pattern table.

---

## 5. Build vs. buy / reuse

| Capability | Decision | Notes |
|---|---|---|
| Engine execution, detection (judge), metrics, **losing_queries**, **accuracy_flags**, grading, storage | **REUSE** | The `geoPromptRunner` platform. This is the bulk of the old "build" list — already built. |
| Gold set / detection calibration | **REUSE** | `data/*_gold.json` + labeling/calibration guides already in the repo. |
| Cold-email send + sequencing | **OUT OF SCOPE** | No sending, no integration. You email the PDF yourself. |
| Clean web extraction (URL → markdown) | **BUY** | Firecrawl or Jina Reader, for the resolver. |
| LLM (resolve, query-set generation) | **BUY** | Anthropic **Claude**. |
| Database / auth / storage (teaserAuto's own tables) | **BUY** | Supabase (same project as the platform, or separate — §7 #3). |
| Hosting (teaserAuto dashboard + render functions) | **BUY** | Vercel. No public teaser pages. |
| PDF generation | **BUY (lib)** | HTML/React template → PDF via Playwright/Puppeteer. |
| **URL → teaser-grade query set** | **BUILD** | The one genuinely new hard part (§4b). |
| **Lead-finding selector** | **BUILD** | Rank `losing_queries` (+ optional `accuracy_flags`). |
| **Proof card + teaser PDF template** | **BUILD** | The artifact is the product. |
| **Review/download dashboard** | **BUILD (thin)** | The human gate + export. |

---

## 6. Phased roadmap

Effort is rough (solo-dev-days equivalent). The platform existing collapses the early phases.

### Phase 0 — Wire up the platform + contracts *(1–2 days)*
- Confirm the platform's **deployment + API key + Supabase project** (Open Decision §7, co-founder questions in §4a).
- Build the `PlatformClient` (submit CSV, poll status, fetch report + answers) and a `MockPlatformClient` seeded from `data/*_gold.json` and the `build_report` sample.
- Stand up teaserAuto's Supabase tables (§3) + Next.js scaffold.
- *Exit:* teaserAuto can submit a hand-written CSV to the (mock or real) platform and read back a `ReportPayload` + answers.

### Phase 1 — Lean MVP: one reviewable teaser PDF, end-to-end *(4–6 days)*
- **Resolver:** URL → Firecrawl → Claude → company profile (name, category, competitors, domains).
- **Query-set generator (§4b option A):** profile → audit-input CSV (config + 6–8 query rows). Human confirm gate on.
- **Submit → poll → fetch report** via `PlatformClient` (judge surface, search engines).
- **Selector:** rank `losing_queries`, pick lead + 2; join verbatim query/answer from `/answers.md`. (Manual override available in the UI.)
- **Proof renderer:** `BrandedCardRenderer` from the verbatim answer.
- **Teaser renderer:** template → **PDF**.
- **Review UI:** list, embedded PDF preview + the verbatim answer behind each claim, edit fields, Approve/Reject → **download PDF.** No sending.
- *Exit:* **one real teaser PDF from a real URL, reviewed, downloaded ready to send.**

### Phase 2 — Trust the auto-selection *(2–3 days)*
- Run the platform's **gold-set calibration**; confirm judge precision on the client-absent verdict meets the bar before trusting auto-picked leads.
- Selector confidence → `needs_review`; require `detection: "judge"` (not regex) for a printable finding.
- Mature competitor-alias handling in the resolver.
- *Exit:* the auto-selected lead finding is a trustworthy default, not just a suggestion.

### Phase 3 — Proof & query-set polish *(2–3 days)*
- Annotation quality on the branded card (highlight competitor, mark absence, clean attribution + citations + `run_date`).
- Tighten query-set generation against the methodology hard-rules; per-vertical tuning (esp. **B2B-SaaS** vs the platform's B2C examples — §7 #4).
- *Exit:* proof reads as unmistakably "this is what the engine actually said"; query sets feel on-category.

### Phase 4 — Throughput & review UX *(2–3 days)*
- Batch URL intake; durable orchestration for the resolve→submit→poll→render chain (Inngest/Trigger.dev or a simple status worker).
- **Cost-per-teaser** tracking (resolver LLM + platform spend via its estimate).
- Dashboard ergonomics: bulk review, keyboard approve, batch PDF download.
- *Exit:* comfortably handle the top of the ≤20/day band with low human time per teaser.

### Phase 5 — Freshness, baseline, wrong-claim *(2–3 days)*
- **Shelf-life:** teasers expire; stale ones flagged for re-run before you send.
- **90-day baseline re-run:** re-submit the same query set, diff `ReportPayload` vs `baseline_snapshot` → quantify movement (retainer-value proof). The platform already supports cadence comparison (`compare`).
- **Wrong-claim (assisted-manual):** human uploads a fact sheet for a prospect → platform emits `accuracy_flags` → surface high-severity ones in the review UI for human verification. Never auto-shipped.
- *Exit:* retainer-value loop closed; second finding type available under human control.

**Critical path:** Phase 0 → 1 gives a reviewed, download-ready teaser PDF fast — because the measurement engine already exists. Phase 2 makes the auto-selection trustworthy. 3–5 are polish, scale, and the wrong-claim surface.

---

## 7. Open decisions — with my recommendation

| # | Decision | My recommendation |
|---|---|---|
| 1 | **Integration model** (separate consumer vs extend the platform repo) | **Separate consumer (A).** The API is exactly the right seam; keeps your teaser product decoupled from the co-founder's engine. |
| 2 | **Where query-set generation lives** (teaserAuto in TS, or contributed to the platform in Python as shared methodology) | Lean **teaserAuto/TS** for speed now; if the co-founder wants audits and teasers to generate sets identically, promote it into the platform later. Encode the methodology rules either way. |
| 3 | **Supabase project** (share the platform's vs a separate teaserAuto project) | **Separate teaserAuto project**, referencing platform runs by `run_id`. Avoids coupling schemas; the platform's data stays the co-founder's. |
| 4 | **B2C-vs-B2B mismatch** — the platform's README niche + query examples are B2C consumer; your GTM is B2B SaaS | Engine is category-agnostic, but **tune query-set generation + fact-sheet examples for B2B SaaS.** Validate the first few teasers on real SaaS prospects before volume. |
| 5 | **Competitor sourcing** | **LLM-proposes, human-confirms** at the input gate. A wrong competitor poisons the whole teaser. |
| 6 | **Engines for the teaser** | Run the **search surface** (live retrieval) across `perplexity` + `ai_overviews` as hero candidates; include `openai`/`anthropic`/`gemini` search for the pattern table. Confirm the platform defaults to search, not parametric. |
| 7 | **Input confirm gate on/off** | **On** at ≤20/day — cheap insurance before paying for an audit. Make it a per-run toggle for later. |
| 8 | **Selection rubric weights** (intent × absence × competitor strength × engine credibility) | Config, not code. Start: highest-intent (`comparison`/`category`) losing cell, named competitor, on the hero engine; tune after Phase 2 against the gold set. |

---

## 8. Risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Judge over-flags → false claim in a teaser | **High (reputational)** | Mandatory human gate; every claim traces to a verbatim answer span; require `detection: "judge"`; calibrate vs the existing gold set; asymmetric precision bar on client-absent. |
| Platform not deployed / no API key / local-only | High (blocking) | `MockPlatformClient` from `data/*_gold.json`; confirm deployment + key in Phase 0. |
| Auto-generated query set is off-category (esp. B2B) | Medium | Human confirm gate; methodology hard-rules; per-vertical tuning (§7 #4). |
| Wrong competitor resolved | Medium | Human-confirmed competitor list (§7 #5). |
| Engine answers drift week-to-week | Medium | Cache `ReportPayload` + verbatim answers on the teaser; shelf-life; 90-day re-run diff (platform `compare`). |
| Proof reads as "not a real screenshot" | Medium | Verbatim answer + unambiguous engine/query/date attribution + citations; upgrade hero to real screenshot if the platform adds capture. |
| Platform cost per audit (judge + multi-run + search) | Low now / Medium later | Platform spend guards already exist; teaserAuto tracks cost-per-teaser; tune `runs_per_query` + engine count for teasers. |

---

## 9. What I need from you / the co-founder to start

1. **Platform access:** API base URL (or confirm local `run-api.sh` on :8000), the `GEO_API_KEY`, and which **Supabase project** teaserAuto should use. Whether the judge runs by default (needs `OPENAI_API_KEY`) and whether the **search surface** is the default.
2. **Confirm the integration model** (§7 #1) and where query-set generation should live (§7 #2).
3. **A target vertical + 2–3 real B2B-SaaS prospect URLs** to validate the resolver + query-set generator against (the platform's examples are B2C).
4. Sign-off (or edits) on the **stack** (§2) and **Phase 0→1 scope**.

With platform access + a couple of test URLs, Phase 0 (wire-up + `MockPlatformClient`) can start immediately and Phase 1 produces the first real teaser PDF.
