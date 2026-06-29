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
| **1 — Engine-answer judge** | LLM reading of engine answers (present / prominence / framing + accuracy flags) | `src/pipeline/judge_metrics.py`, gold sets `data/oura_gold.json` / `data/fort_gold.json`; `scripts/run_calibration.py` | ✅ **Done** — re-confirmed 2026-06-28 under the B2C/consumer judge prompt (Sonnet, temp 0, dedup, gold sets web-verified). Agreement: present 96% · prominence 88% · framing 93% · **flag recall 95%** (was 100% pre-B2C — one of 21 gold flags now missed) · binary flag agreement 89%. **Known issue: low flag precision ~42% (28 FP / 20 TP) — judge over-flags, concentrated in `wrong_pricing` (17 vs 7 gold) and `missing_or_invented_feature` (13 vs 2 gold). Tracked as queue #9.** |
| **2 — Grade formula** | A–F penalty weights (−high/−med/−low) + letter bands → analyst gut grades | `src/pipeline/grade_calibration.py`, `data/grade_situations.json`, `docs/grade-calibration-guide.md` | ✅ **Calibrated 2026-06-28 (Abhi's pass — Josh pass waived by owner)** — 10 situations graded; fitted policy clears the bar: **held-out leave-one-out 100% within-one** (60% exact; in-sample 70%/100%). Fitted: penalties high −0.05 · med −0.03 · low 0.00; bands A≥0.70·B≥0.50·C≥0.30·D≥0.15 |
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
| **1** | Layer 2 — grade calibration | ✅ Calibrated 2026-06-28 (held-out 100% within-one, Abhi's pass) | Gated Audit Generator §1 (the grade) — now **unblocked** |
| **2** | Layer 3 — content judge | 🟡 Built + tests green; needs content-page gold set + κ≥0.6 run | Unblocked (scraper locked); gates Audit §6 |
| **3** | Scraper decision | ✅ Locked — keep homegrown | Optional future: Firecrawl for rendered-view/off-site only |
| **4** | Audit Generator | ✅ **Built (Phases 0–3), 2026-06-25** | In `teaser/` (`npm run audit -- <run_id>`): synthesis + 8-section render + PDF + `/audit-deliverables` API + `/audit` web page. All tests green; PDF visually verified. Schema applied to Supabase 2026-06-25 (db round-trip verified). Outstanding: Phase 4 polish |
| **5** | Fact-sheet-per-run requirement | 🔴 New standing rule (auditGenerator §15.5, §4 always-on) | Upstream of every full audit; ties to L1 accuracy flags |
| **6** | B2C niche reorientation | ✅ **Done (2026-06-24)** | Full codebase sweep: removed g2.com from off-site platforms; buyer→consumer in judge/rubric; B2B demo/test data → consumer budgeting apps; teaser B2B sample domains/category → B2C. All 202 src + 28 teaser tests green. NOTE: judge-prompt edit invalidated the L1 judge cache; **L1 re-run 2026-06-28 confirmed parity** — present/prominence/framing identical (96/88/93%), flag layer within ~1 item (recall 100%→95%, binary agreement 85%→89%). The "buyer→consumer" swap did not move detection |
| **7** | Real-client dry run (orig Chunk 12) | ⚪ Never marked done in build log | Final end-to-end validation |
| **8** | Teaser resolver check | ⚪ Minor | Confirm it uses Firecrawl/Jina or was built in-house |
| **9** | Judge flag **precision** (over-flagging) | ✅ **Solved 2026-06-28** | Baseline 42% precision / 95% recall (28 FP). Two layers: **(a) prompt delete-gate** in `_ACCURACY_BLOCK` (omission/confirmation/sheet-silent, keyed to the cited line) — on by default, 42%→44%, recall held. **(b) adversarial verifier** (`--verify` / `JUDGE_VERIFY`, `_verify_flags`): one focused keep/drop call per flag, recall-safe (keeps on failure), defaults to the Sonnet model (Haiku over-drops → 76% recall). Final on 80-item gold: **precision 80% · recall 95% · 5 FP / 20 TP / 1 FN** (binary agreement 98%). Precision ~doubled with ZERO true positives lost. Verifier is opt-in; recommend `--verify` for client deliverables (adds ~1 Sonnet call per flag). Held-constant base judge unchanged for calibration/gold |
| **10** | Two-tier **cascade judge** | ✅ **Built & validated 2026-06-28** | Haiku structural reads + Sonnet accuracy block (`docs/judge-accuracy-plan.md` §4.1). Ship gate met: **flag recall 100%**, structural κ non-regressing (present 96 / prom 89 / framing 94). Visibility-only runs (no fact sheet) go pure-Haiku (~3× cheaper). Opt-in: `--cascade` / `JUDGE_CASCADE=1`; default stays single-Sonnet for calibration/gold/paid. Follow-on: B1/B2 (few-shot + reasoning-first) to lift standalone Haiku flag recall. Precision dip → #9 |

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
