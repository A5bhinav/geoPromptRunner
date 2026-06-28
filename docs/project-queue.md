# Project Queue & Status

> Snapshot authored 2026-06-24. A living "what's done / what's left" view across
> calibration, the scraper decision, and the Audit Generator build. Update as
> items move. Companion to `docs/build-log.md` (append-only chunk history),
> `docs/auditGenerator.md` (the paid deliverable design), and
> `docs/site-audit-implementation-guide.md` (the crawler).

---

## 1. Calibration — three layers

The platform has **three** distinct calibration layers. The crawler's fetch/extract
itself is **deterministic** (httpx + Playwright + trafilatura + extruct) and the
rule-based checks (SSR ratio, robots.txt, schema validity, links) are thresholds —
**none of those are calibratable.** Only the LLM-judgment layers are.

| Layer | Calibrates | Harness | Status |
|---|---|---|---|
| **1 — Engine-answer judge** | LLM reading of engine answers (present / prominence / framing + accuracy flags) | `src/pipeline/judge_metrics.py`, gold sets `data/oura_gold.json` / `data/fort_gold.json`; `scripts/run_calibration.py` | ✅ **Done** (2026-06-19): Sonnet judge, 100% accuracy-flag recall, temp 0, dedup, gold sets web-verified |
| **2 — Grade formula** | A–F penalty weights (−high/−med/−low) + letter bands → analyst gut grades | `src/pipeline/grade_calibration.py`, `data/grade_situations.json`, `docs/grade-calibration-guide.md` | 🟡 **In progress** — 10 real situations staged; needs Josh + Abhi to independently gut-grade, then fit |
| **3 — Content judge** | LLM scoring of *crawled pages* against the technique checklist (Cat 3 & 4 steps), pass/partial/fail | `src/audit/checks/content_judge.py` (built, 12 unit tests green) + `content_calibration.py` (κ≥0.6 ship gate) | 🟡 **Almost done** — judge logic finished; **no content-page gold set labeled yet** → κ run not done |

### Layer 2 — how to finish
Per `docs/grade-calibration-guide.md`: Josh and Abhi **independently and blind** assign
A/B/C/D/F to the 10 situations *from the numbers, before seeing the formula output*
(no anchor letters on purpose). Independent copies staged at
`data/grade_situations_{abhi,josh}.json`. Then reconcile (talk through any gap > 1
letter) and run:
```bash
python -m src.pipeline.grade_calibration   # reads data/grade_situations.json
```
Bar: **within one letter**. Until it clears, the grade stays "uncalibrated — internal only."

The 10 situations: Oura (pooled + anthropic/gemini/openai/perplexity) and Fort (same
split) — visibility spans 0.00–0.53, flag loads 0–18.

### Layer 3 — what it is and how to finish
The **content judge walks the technique checklist** and scores each subjective step
pass/partial/fail. The deterministic checks cover rubric Categories 1/2/5/6; the LLM
judge covers the **judgment** steps in Categories 3 & 4:

- **Cat 3 (structure / extractability):** `answer_first_lead`, `self_contained_chunks`, `definition_first`
- **Cat 4 (substance / E-E-A-T):** `expert_commentary`, `original_data`, `external_citations`

Each check has sub-questions; the judge emits a `CheckVerdict` (pass/partial/fail/unknown).
**Remaining work:** label a content-page gold set (`page_url` + `text` + per-check
`labels`) — same labeling-sheet workflow used for the engine-answer gold sets — then
run the κ≥0.6 ship gate (`content_calibration.py`) and fix any check under 0.6.
Now safe to label against **trafilatura's** extracted text, since the scraper is staying
put (§2).

---

## 2. Scraper decision — KEEP the homegrown stack (locked 2026-06-24)

**Decision: keep `httpx` + `Playwright` + `trafilatura` + `extruct`. Do NOT adopt
Firecrawl or Crawl4AI.** Based on a deep-research pass (Vercel/MERJ 500M+ fetches +
multiple corroborating sources).

**Are we using Crawl4AI / Firecrawl today? No — not in running code.** Neither is in
`requirements.txt` or imported anywhere. They appear only in:
- `docs/site-audit-implementation-guide.md` §7.5 — Crawl4AI documented as an *optional*
  Docker render/deep-crawl escape hatch; the nav-link discovery it would have provided
  was **closed in-house** (`page_select.discover_nav_links`) without the dependency.
- `teaser/BUILD_PLAN.md` — Firecrawl/Jina referenced for the **teaser resolver**
  (URL → company profile), a *different* component; "BUY" plan, not confirmed wired in
  (worth a quick confirm — see queue #8).
- `web/app/teaser/page.tsx` — the word "crawl4ai" in a config-placeholder warning string.

**Why keep homegrown (the GEO-specific reason):** the audit's job is to measure **what
AI crawlers actually see**. Major AI crawlers (GPTBot, ClaudeBot, PerplexityBot,
OAI-SearchBot, Meta-ExternalAgent) **do not execute JavaScript** — they read raw HTML
only (~69% have no JS execution; only Googlebot→Gemini renders). So the signal the audit
sells is the **raw-vs-rendered diff**. The homegrown stack produces exactly that:
httpx + GPTBot UA = bot's-eye raw view; conditional Playwright escalation = rendered view;
the difference is the finding.

- **Firecrawl is actively wrong here:** managed API that renders JS on every scrape with
  **no documented parameter to force a raw-only fetch** — it would silently mask the exact
  CSR/accessibility gaps the audit must surface. Already paying for it = sunk cost, doesn't
  fix the mismatch.
- **Crawl4AI not worth it:** capable but self-hosted (Docker, ≥4GB RAM, DevOps); buys
  nothing over the existing Playwright stack at a handful of domains, and scored lower on
  reliability (89.7% vs Firecrawl 95.3% on anti-bot sites). B2C startup sites are
  cooperative, so anti-bot isn't the bottleneck.

**When to revisit:** a narrow, additive use — Firecrawl as an *optional rendered-view or
off-site/anti-bot source* while httpx+GPTBot-UA stays the authoritative raw view. Also
revisit if major indexing bots start rendering JS (one projection: ~65% by 2027).

**Caveats from the research:** exact Firecrawl pricing tiers couldn't be pinned (several
pricing claims were refuted in verification — check the live pricing page before
budgeting); findings are a 2024–2026 snapshot.

---

## 3. The Queue

| # | Item | Status | Notes / dependency |
|---|------|--------|--------------------|
| **1** | Layer 2 — grade calibration | 🟡 Set up; waiting on 10 gut grades | Gates Audit Generator §1 (the grade) |
| **2** | Layer 3 — content judge | 🟡 Built + tests green; needs content-page gold set + κ≥0.6 run | Unblocked (scraper locked); gates Audit §6 |
| **3** | Scraper decision | ✅ Locked — keep homegrown | Optional future: Firecrawl for rendered-view/off-site only |
| **4** | Audit Generator | ✅ **Built (Phases 0–3), 2026-06-25** | In `teaser/` (`npm run audit -- <run_id>`): synthesis + 8-section render + PDF + `/audit-deliverables` API + `/audit` web page. All tests green; PDF visually verified. Schema applied to Supabase 2026-06-25 (db round-trip verified). Outstanding: Phase 4 polish |
| **5** | Fact-sheet-per-run requirement | 🔴 New standing rule (auditGenerator §15.5, §4 always-on) | Upstream of every full audit; ties to L1 accuracy flags |
| **6** | B2C niche reorientation | ✅ **Done (2026-06-24)** | Full codebase sweep: removed g2.com from off-site platforms; buyer→consumer in judge/rubric; B2B demo/test data → consumer budgeting apps; teaser B2B sample domains/category → B2C. All 202 src + 28 teaser tests green. NOTE: judge-prompt edit invalidates the L1 judge cache → re-run L1 calibration to confirm parity |
| **7** | Real-client dry run (orig Chunk 12) | ⚪ Never marked done in build log | Final end-to-end validation |
| **8** | Teaser resolver check | ⚪ Minor | Confirm it uses Firecrawl/Jina or was built in-house |

### Recommended order
1. **Finish calibrations #1 + #2 first** — they gate the Audit Generator (cover grade ←
   Layer 2; §6 diagnosis ← Layer 3). Calibrating after building the deliverable means
   reworking the deliverable.
2. **Build the Audit Generator (#4)** — Phase 0 plumbing onward, baking in the
   fact-sheet rule (#5).
3. **Run B2C reorientation (#6) in parallel** — independent of the above.
4. **Dry run (#7)** validates the whole pipeline once the generator exists.

### Immediate, human-only moves
- Josh + Abhi send the **10 gut grades** → fit Layer 2.
- Decide whether to **start the Layer-3 content-page labeling sheet** now (last mile on
  the content judge).
