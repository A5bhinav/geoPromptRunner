# GEO Engine — Gap Analysis (Roadmap vs. Actual Implementation)

**Date:** 2026-05-31
**Scope:** What the AEO/GEO roadmap + methodology require, vs. what the engine in `src/` actually does today — and what still needs building or fixing.

> **Updated** with the strategy/delivery context (the audit method + report template). Key reframe: the audit method states **the software powers only Steps 1 (baseline measurement) and 5 (competitive benchmark)** — Steps 2–4 (on-site/off-site rubric scoring) are explicitly *human judgment for now*. So the engine's real job is the **measurement and demo layer**, and that's exactly where today's gaps bite hardest. The report template is, in effect, the engine's output spec — so the sharpest test is: *can the engine fill the report?*

---

## Executive summary

The engine has a clean, well-disciplined skeleton: four engine adapters, a query-set/intent model, a metrics module, a technical checker, Supabase storage, and a report renderer. Code quality is high (strict mypy, never-raise invariants, leak-safe logging). But measured against the roadmap, **the engine today can only do a fraction of the audit it's meant to power, and the part it does do has accuracy and architecture problems that will produce misleading numbers.**

Three things are true at once:

1. **It isn't wired together.** There is no orchestrator. Every module has a `__main__` demo, but nothing runs query-set → detection → metrics → storage → report as one pipeline. Chunk 12 (the dry run) was never built.
2. **The data model is split-brained.** The newer, intent-aware `QueryResult` (with per-bucket intent, multi-run, citations) — the thing the methodology actually needs — **cannot be stored or reported.** Storage and the report only understand the older, flatter `PromptResult`. The best analysis in the codebase (`metrics.py`) is an island.
3. **Most of the audit rubric doesn't exist.** Of the 7 rubric categories, only Category 1 (technical accessibility) is partially built. Categories 2–6 (content coverage, structure/extractability, E-E-A-T, schema, off-site authority) and the Step-6 prioritized roadmap — the actual deliverable that sells the retainer — have zero code.

Put bluntly: today the engine is an **AI-answer mention tracker with four technical checks**, not the diagnostic audit instrument the roadmap describes. The gap is less "polish" and more "the second half of the build."

---

## The deliverable test: can the engine fill the report?

The report template is the engine's real spec. Sections 2, 3, and 6 are supposed to run on the software, and the audit method says the software powers Steps 1 and 5 (the free teaser is *"essentially Steps 1 and 5 on a handful of queries — the demo that books the meeting"*). So here's the honest scorecard of what the engine can and can't produce **right now**:

| Report element (the spec) | Needs | Engine today |
|---|---|---|
| **§2 Engine column** — ChatGPT, Perplexity, **Google AI Overviews**, Claude, Gemini | 5 named surfaces | ❌ Only 4 adapters, and **none is Google AI Overviews** (the Gemini API ≠ AI Overviews). Two of the five rows can't be produced. |
| **§2 Mention rate** per engine | per-engine mention rate | 🟡 Computable, but inflated by the broken "recommended" logic (Tier 2.1). |
| **§2 "Cited with link?"** per engine | citations from every engine | ❌ Only Perplexity captures citations; the other columns are blank by construction (Tier 2.3). |
| **§2 "Accuracy of how it describes you"** | judge the substance of the answer | ❌ Not captured at all (Tier 2.2). Entire column unfillable. |
| **§3 Competitive matrix** — *absent / cited #1 / mentioned* per query × brand | **prominence/rank** per brand per query | ❌ Engine only has mentioned/recommended/not-mentioned. "Cited #1" (rank) doesn't exist (Tier 2.1). |
| **§3** run for client **and** competitors | competitor-side runs | 🟡 Detects competitor *names* in client answers, but doesn't run the set *for* competitors or rank them (Tier 2.6 / 3.3). |
| **§4 Diagnosis** — Cat 1–6 rollup | rubric scores stored | 🟡 Cat 1 only (4/6 checks); Cat 2–6 are **intentionally human for now** — but there's nowhere to *record* those human scores to render §4. |
| **§5 Prioritized roadmap** — impact/effort, sequenced | gap scoring + weighting | ❌ Not built (Tier 3.2). This is the retainer scope. |
| **§6 Tracking over time** | stable client identity + locked query-set version | ❌ Schema can't do trend or versioning (Tier 1.3). |
| **§6 GA4 attribution** | referral/conversion tracking | ❌ Not built (out of scope today, but it's in the template). |

The takeaway: **the engine cannot currently fill a single section of the report completely.** The two sections it's supposed to own outright — §2 and §3, the visceral "here's what ChatGPT says about you vs. your competitor" demo that is the highest-converting sales move in this whole plan — each have blank or wrong columns. Fixing §2/§3 is the highest-business-value work in the codebase, ahead of automating the rubric.

### The teaser/demo path doesn't exist as a distinct mode

The method leans on a fast, mostly-automated teaser (Steps 1 + 5, a handful of queries) as the meeting-booking demo. The engine has **no shallow/teaser mode**, no "client + one competitor, 5 queries, render the comparison" fast path, and no shareable demo output. That's the single most sales-critical artifact in the plan and it has no dedicated code path today.

### Query-set sourcing is fully manual

The methodology's per-client SOP (Scope → Gather → Map/clean → Modify → Trim → Validate → Lock) and its raw-material sources (client intake, search data, community, competitive, LLM-assisted expansion) have **no tooling**. `load_query_set` reads a hand-authored JSON; building the 40–50-query set per client is entirely manual. Fine for v0, but it's the per-client setup cost that will throttle how many audits you can run, so it's an early productization candidate.

---

## Tier 1 — Structural blockers (fix these before anything else)

### 1.1 No end-to-end orchestration; the dry run was never built

`grep` confirms nothing calls the runner, parser, storage, and report together. `run_query_set` (the good path) is invoked only by its own demo. `detect_mention`/`extract_competitors` are called **only by `metrics.py`** — never by any code that writes `BrandMention` rows. So the entire storage "mentions" path is dead: `save_mentions` exists but nothing ever produces the rows it saves.

There is no CLI, no `main`, no "audit one client" entry point. Chunk 12's acceptance criteria (10+ prompts → all engines → stored → mentions extracted → technical checks → report) is unmet. **This is the first thing to build**, because it's also what exposes every integration bug the unit demos hide.

### 1.2 Two parallel result models, only the weaker one is persistable

- `run_prompts` → `PromptResult` (prompt, engine, response, timestamp) — flat, no intent, no runs, no citations.
- `run_query_set` → `QueryResult` (query_id, intent, run_index, citations, …) — the methodology-aligned shape.

`metrics.py` consumes `QueryResult`. But `db.py` and `schema.sql` only know `PromptResult`/`BrandMention`/`Citation` — **there is no way to store a `QueryResult`.** `report.py` likewise reads `PromptResult`, so it cannot render the per-bucket or share-of-voice analysis that `metrics.py` already computes.

Consequence: the engine's most valuable output (mention rate *by funnel stage*, share-of-voice, multi-run aggregation) can be computed in memory but never saved, never trended, never put in a client report. **Unify on `QueryResult` end-to-end** (runner → metrics → storage → report) and retire `PromptResult`, or treat it as a derived view.

### 1.3 Storage schema can't support trend, versioning, or client identity

`prompt_runs` keys a run only by free-text `client_name`. There is no `clients` table, no `competitors` table, no `query_sets`/version table, and the results tables have no `query_id`, `intent`, or `run_index` columns. The methodology's core promises — **"trend over time," "lock a version per measurement cycle," "keep a change log"** — are structurally impossible on this schema:

- No stable client ID to join runs across time.
- No link from a run to the locked query-set version it used (so "are we comparing the same instrument?" is unanswerable).
- No per-query/intent columns, so per-bucket trend can't be queried.
- `citations` has no `query_id`, no run linkage, and no domain column (domain is recomputed on every read).

This needs a schema redesign before real before/after case studies are possible — and the roadmap's whole sell is before/after with real numbers (Phase 2 exit gate).

---

## Tier 2 — Measurement quality (the numbers will mislead)

### 2.1 Mention/recommendation detection is too crude — false "recommended"

`detect_mention` marks a brand **RECOMMENDED** if the brand appears *and the response anywhere contains* "best / recommend / suggest / top choice." Recommendation is detected at the **response level, not the brand level.** So:

> "The best CRM is Salesforce, but Acme also exists."

classifies **Acme as RECOMMENDED** — because "best" is somewhere in the text. This will systematically inflate the client's (and every competitor's) recommendation rate whenever the answer recommends *anyone*. Other failure modes of pure substring matching:

- Negative mentions ("avoid Acme," "Acme is weak") count as positive mentions.
- No handling of brand-name variants, misspellings, or brands that are common words.
- The methodology's **framing** axis (positive / neutral / negative, **accurate / inaccurate**) is entirely absent.
- The methodology's **prominence** axis (recommended first / mid-pack / buried / also-ran) is entirely absent.

The fix is structured extraction (an LLM-as-judge pass over each answer that returns, per brand: present?, sentiment, accuracy-vs-fact-sheet, rank/prominence), not regex. This is the single highest-leverage measurement upgrade.

### 2.2 "Accuracy of how the brand is described" is never captured

Step 1 and rubric Category 7 both demand checking whether the model's description of the client is *current and on-message*. Nothing in the engine evaluates the substance of what's said — only whether the name appears. Catching "the LLM is saying something wrong about you" is one of the most visceral demo moments in the methodology, and it's unbuilt. Needs a client fact-sheet + judge comparison.

### 2.3 Citations are Perplexity-only

`query_with_citations` is overridden **only** in `PerplexityEngine`; the base returns `[]`. So `citation_rate`, `citation_rate_by_bucket`, and `top_cited_domains` ("the sources behind our category") are effectively **Perplexity-only statistics** presented as if cross-engine. OpenAI (with search), Gemini (grounding), and ChatGPT all surface sources that aren't being captured. This badly skews the "what sources do LLMs cite in our category" finding — arguably the most actionable off-site insight in the report.

### 2.4 The engines measured aren't the surfaces buyers use

The adapters call plain chat models: `gpt-4o` (no browsing via chat completions), `claude-sonnet-4-5` (no browsing), `gemini-2.5-flash` (no grounding configured), `perplexity sonar` (browsing). The positioning is *"every engine your buyers use — measured, not guessed,"* but:

- 3 of 4 adapters measure **parametric/training-data memory**, not live retrieval — a different channel than what a buyer sees in ChatGPT-with-search or Google AI Overviews.
- **Google AI Overviews / AI Mode** — plausibly the highest-traffic surface — isn't covered at all (the Gemini API is not AI Overviews).
- No way to distinguish "invisible because not in training data" from "invisible because not retrieved" — yet that distinction drives completely different fixes (off-site authority vs. on-site extractability).

At minimum, document this as a known fidelity limitation; ideally, add browsing/grounding configs and a real AI-Overviews capture path.

### 2.5 Multi-run nondeterminism isn't actually aggregated; temperature unpinned

`run_query_set` runs each query 3× (good), but `metrics.py` treats every run as an independent row. There is **no per-query aggregation** ("mentioned in 2 of 3 runs"), no variance/stability flag, no confidence. The methodology's reason for 3× runs — *aggregate to avoid single-run noise* — isn't realized; instead noise is amplified into the denominator. Also **no engine sets temperature or seed**, so runs are needlessly noisy and irreproducible. Pin temperature low (or per a documented policy) and aggregate runs into a per-query verdict before rolling up.

### 2.6 Competitors can't be discovered, and share-of-voice double-counts

- The engine only checks a **pre-supplied** competitor list. The methodology wants "which competitors are present (including ones you didn't name) and their prominence." A new rival dominating answers is invisible.
- `share_of_voice` counts an appearance per result row, so a brand mentioned across 3 runs of one query counts 3×, biasing share toward whichever queries/engines happened to answer. De-dup to a per-(query, brand) verdict first.

---

## Tier 3 — Coverage gaps (whole rubric sections missing)

### 3.1 Categories 2–6 of the rubric are unbuilt — but mostly *intentionally*, with one real gap

`project.md` references `audit/checklist.py`; **it does not exist.** Implemented today: Category 1 only (4 of 6 checks). Categories 2–6 (content coverage, structure/extractability, E-E-A-T, schema, off-site authority) have no code.

**Important nuance from the audit method:** Steps 2–4 (the on-site and off-site rubric scoring) are explicitly *human judgment for now* — only Steps 1 and 5 are software. So the *absence of automated Cat 2–6 scoring is by design*, not a bug, and automating it is a later productization signal ("note what you keep doing by hand"), not a current blocker. I'd downgrade my earlier framing here.

The **real** gap that remains is smaller but does block the report: there's **nowhere to record the human rubric scores.** To render report §4 (the Cat 1–6 rollup) and §5 (the prioritized roadmap), the engine needs a place to *store* Pass/Partial/Fail judgments and weights per category — even if a human enters them. Today there's no schema, model, or input path for that. So build the rubric *data capture and rollup* now (cheap, unblocks §4/§5); defer the rubric *automation* until client work tells you which checks are worth scripting.

### 3.2 No Step-6 prioritized roadmap / gap scoring — the actual deliverable

Step 6 ("synthesize into a prioritized roadmap with impact/effort, sequenced accessibility → content → off-site") is *the thing the audit sells*. The report output is a flat snapshot (mention rate per engine, share-of-model, top domains). There is **no score rollup, no weighting, no sequencing, no impact/effort tagging, no gap list.** Without this, the engine produces a measurement, not an audit, and there's nothing to scope a retainer against.

### 3.3 Competitive benchmark (Step 5) isn't a real pass

Step 5 says run the same instrument *for the client and the competitors*, and run the rubric/technical checks against competitor domains for the "here's where they beat you" map. Today the engine only detects competitor *names* inside client-query answers. It does not run competitor-centric queries, score competitors on the rubric, or batch technical checks across client + competitor domains. The competitive throughline that "makes the whole audit land" is missing.

---

## Tier 4 — Technical-check correctness

### 4.1 Blind to the most common real blocker: UA-based CDN/WAF blocking

The rubric explicitly calls out *"Not blocked at the CDN/WAF layer — confirm AI user-agents actually reach the site (especially Cloudflare, which defaults to blocking AI bots)."* But `technical_check` fetches `robots.txt`/homepage with **httpx's default user-agent**, never as `GPTBot`/`ClaudeBot`/`PerplexityBot`. Cloudflare's block is UA-based and returns 403 to bot UAs while serving a normal browser UA. **The engine cannot see the exact failure mode the rubric names.** Fix: re-request key URLs spoofing each AI UA and compare status/byte-length to a baseline UA.

### 4.2 Other check gaps

- **Rendering** is a coarse HTML-length heuristic; it won't reliably catch React/Next hydration-only pages (raw HTML can be large but content-empty). Consider comparing raw vs. rendered text, or flagging known SPA shells.
- **No gated-content detection** (login/paywall/forms) — a Cat 1 item.
- **No sitemap freshness** (`lastmod`) parsing.
- `robots.txt` 404 → "pass" is defensible, but combined with 4.1 it can produce a falsely clean Category 1.

---

## Tier 5 — Engineering & ops

- **No tests.** `pytest` is in `requirements.txt` and `project.md` plans `tests/test_*.py`, but there is **no `tests/` directory.** The correctness-critical parser has only 5 hand-written `__main__` cases. The classification logic (Tier 2.1) is exactly the code that most needs regression tests.
- **No cost / volume controls.** 45 queries × 4 engines × 3 runs = 540 sequential blocking calls per cycle. At a 60s timeout that's a worst case measured in hours. No concurrency (async is correctly scope-locked for now, but it's a real ceiling), no per-run cost estimate, no progress output.
- **No checkpointing / incremental persistence.** Results are returned only after the full nested loop completes; nothing is saved mid-run. A failure on call 500 loses the whole cycle. Persist per result (or per query) so runs are resumable.
- **Failure handling is inconsistent between modules.** `metrics.py` correctly excludes `None` (engine failure) from denominators; `report.py` counts those rows as "prompts," understating mention rate. Two different definitions of the same metric.
- **Duplicated, divergent helpers.** `domain_of` (metrics) vs. `_domain_of` (report) — the report version doesn't lowercase. Centralize.
- **Doc drift.** `AnthropicEngine` docstring says "Claude 3.5 Sonnet" (model is `claude-sonnet-4-5`); `GeminiEngine` says "1.5 Pro" (model is `gemini-2.5-flash`). Minor, but it's the kind of drift that erodes trust in a report.

---

## Suggested build order

Re-prioritized around the deliverable: the engine's job is Steps 1 & 5 (the §2/§3 demo that books meetings), and Steps 2–4 stay human for now. So the order chases *a fillable §2/§3 demo* first, then trend/versioning, then the rest.

1. **Replace regex detection with an LLM-judge extraction** returning, per brand: present? · sentiment · accuracy-vs-fact-sheet · **prominence/rank**. This single change unblocks the §2 "accuracy" column and the §3 "cited #1 / mentioned / absent" matrix — the heart of the demo. Aggregate the 3 runs into one per-query verdict; pin temperature. *(Tier 2.1, 2.2, 2.5, 2.6)*
2. **Fix citations + surfaces**: capture sources from *all* engines (not just Perplexity), add browsing/grounding, and add a real **Google AI Overviews** path (or honestly drop it from the report column until covered). Unblocks §2 "cited with link" and the 5-engine row set. *(Tier 2.3, 2.4)*
3. **Run the set for client *and* competitors** and rank them — makes §3 and Step 5 real, not name-detection. *(Tier 2.6, 3.3)*
4. **Stand up a teaser/demo mode** — client + 1 competitor, ~5 queries, render the §2/§3 comparison fast. This is the highest-converting sales artifact and has no code path today. *(deliverable lens)*
5. **Schema redesign + unify on `QueryResult`** (clients, competitors, query-set versions; query_id/intent/run_index/citation linkage). Unblocks §6 trend + versioning. *(Tier 1.2, 1.3)*
6. **Build the orchestrator + Chunk 12 dry run**, persisting incrementally. Wire runner → judge → metrics → storage → report end-to-end. *(Tier 1.1, 5)*
7. **Rubric data capture + Step-6 roadmap rollup** — store the *human* Cat 1–6 scores and weights, and render §4/§5. Defer rubric *automation*. *(Tier 3.1, 3.2)*
8. **Fix the WAF/UA blind spot** in the technical checker. *(Tier 4.1)*
9. **Add `tests/` with real regression coverage**, starting with the parser/judge. *(Tier 5)*

Items 1–4 make the **sales demo** real and trustworthy (highest business value). 5–6 make it persistable and trendable. 7 produces the paid deliverable's diagnosis/roadmap. 8–9 harden it.

> The thing to internalize: the rubric (Cat 2–6) being unautomated is *fine* — the method says so. What's **not** fine is that the two sections the engine is supposed to own, §2 and §3, can't be filled today. That's where the next sprint should go.
