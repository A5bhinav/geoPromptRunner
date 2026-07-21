# SMB pivot plan — local service businesses (HVAC, plumbing, barbershops)

Status: proposed (2026-07-12). Audience pivot #2: B2C consumer startups (Berkeley/SV) →
local service SMBs. Google AI Overviews / AI Mode becomes the flagship surface.
Companion to the geo-dev skill; supersedes nothing — the measurement engine stays.

---

## 1. Why this pivot works, per the research

The market timing is real, and the data supports the exact pitch Josh wants to make:

- **45% of US consumers used AI tools for local business recommendations in the past
  year, up from 6% the year before** (BrightLocal Local Consumer Review Survey 2026,
  n≈1,000). AI is now the #3 local discovery channel behind Google and Facebook —
  already ahead of Yelp. ChatGPT 31%, Google AI Mode 23%.
- **AI Overviews appear on ~68% of local-business Google searches** overall, but the
  split by intent is the key design fact: **15% of pure local-intent queries** ("best
  plumber in Berkeley"), **92% of informational**, **97% of hybrid cost/decision
  queries** ("average cost of AC replacement in Phoenix") — while local packs show the
  inverse (93/6/17%). (Whitespark, 540-query study, 2025.)
- **AI compresses the winners' circle ~3×**: across 322 markets, AI local answers
  surfaced ~5,900 unique businesses where legacy 3-packs surfaced ~18,300 (Sterling
  Sky / Places Scout). Most local businesses really are invisible in AI — the teaser
  claim is factually defensible.
- **The economics work**: HVAC customer LTV ≈ $15,340, blended cost-per-lead ≈ $153,
  marketing spend 7–12% of revenue. Local SEO retainers run $300–1,500/mo; one-time AI
  audits are being sold at ~$400. Influencing one job a quarter justifies the retainer.
- **The citation graph is small and known**: Yelp dominates — 3.4× the next source
  across 28M+ AI responses, 72.5% of directory citations on Google AI Mode, 62.1%
  share on Perplexity (Foundation Marketing + AirOps, Q4 2025) — then BBB, Angi,
  Thumbtack, HomeAdvisor, Facebook, Reddit (r/hvacadvice is the top home-services
  subreddit). Nextdoor underperforms its hype. (Local Dominator 267k-citation
  corpus corroborates the directory skew.) The "~60% of home-services AI citations
  go to third parties" figure is from a *different* AI-Overviews citation study,
  not Foundation/AirOps — pin its source before using it in client copy. A claimed
  formal Perplexity–Yelp API deal did not verify against the cited source; dropped.
- **The query space is tiny**: ~24–75 high-intent phrasings cover a whole trade+city.
  Per-audit cost is low, which is what makes a scan-a-whole-city outbound teaser motion
  affordable.
- **Nobody does judged answer quality for local.** Enterprise GEO tools (Profound
  $99–5k/mo, Peec, Otterly, Semrush-now-Adobe) don't do geo or GBP; local tools (Local
  Falcon, BrightLocal, Yext Scout) do geo-grids but only mention/no-mention counting.
  Our prominence/framing/accuracy judge against a fact sheet is the differentiator.

Two hard warnings from the research that shape the plan:

- **Volatility is severe.** Same-city repeat runs of "near me"-style queries in AI Mode
  swap out ~80% of URLs and >60% of domains; explicit-city phrasings roughly double
  stability (SE Ranking AI Mode volatility test, 5,000 keywords × 15 runs each).
  Google also dials AIO coverage fleet-wide (6.5% → 25% → 16% of keywords within
  2025). A single fetch is a coin flip. We must report sampled rates ("mentioned in
  4/5 runs"), never point-in-time ranks.
- **FTC exposure is real** (Operation AI Comply; Air AI suit over deceptive AI growth
  claims to small businesses). Never guarantee placement. Honest uncertainty bands are
  both the legal posture and the differentiator against "AI domination" agencies.

## 2. What stays and what changes

The measurement engine is audience-neutral and stays untouched: cell aggregation
(query × engine, K runs, majority verdict), SOV/prominence math (`src/pipeline/metrics.py`,
`judge_metrics.py`), isolation/determinism design, judge caching machinery, Cat 1
technical checks, Cat 2 SSR check (worth *more* for Wix/Squarespace SMB sites),
storage, orchestrator, API/UI plumbing.

The audience coupling is concentrated in five places, all assuming a nationally
marketed consumer product with a substitute set and no geography:

1. `src/engines/ai_overviews_engine.py` — sends no location at all (`{"engine":
   "google", "q": prompt}` only). Our flagship surface currently runs every query from
   SearchApi's unpinned default locale. **Worst gap, cheapest fix.**
2. Cat 6 offsite (`src/audit/offsite/`) — `REVIEW_PLATFORMS = (trustpilot.com,
   apps.apple.com, play.google.com)`; agent prompt hunts Reddit/listicles/press. No
   GBP, Yelp, Angi, BBB, Thumbtack, HomeAdvisor anywhere in the repo.
3. Judge accuracy flags (`src/pipeline/judge.py`) — `wrong_pricing`, `stale`,
   `missing_or_invented_feature`, etc. are product-attribute flags. Local accuracy is
   hours, service area, phone, licensing, emergency availability.
4. Teaser (`teaser/`) — profile resolver requires a consumer product category and
   product-substitute competitors (hard-fails otherwise); query-gen fallbacks emit
   "best X for a growing startup"; no location field on `CompanyProfile`.
5. Data artifacts — fact-sheet template ("B2C consumer", SKU/version pricing), sample
   query sets (budgeting apps, smart rings), and the Oura/Fort gold sets that all
   calibration numbers (judge agreement 96/88/93, grade bands) were measured on.

## 3. Refactor plan

Ordered so each phase ships something sellable. Every change passes the standard gate
(`mypy src/ && ruff check src/ && pytest tests/`) and gets a `docs/build-log.md` entry.

### Phase 1 — Location plumbing (unblocks everything)

The system has no concept of geography anywhere. Introduce it once, thread it through.

- **Query schema** (`src/prompts/query_set.py`, `csv_loader.py`): add optional
  `location: str | None` to `QuerySet` (one service area per set — a locked set is
  per-client per-cycle, and a client has one service area; per-query override only if
  multi-location clients appear later). Add the column to the CSV template/`_COLUMNS`.
  Serialization is additive, so existing stored sets still load.
- **Settings** (`src/config/settings.py`): `DEFAULT_SERP_LOCATION`, `SERP_GL`/`SERP_HL`
  (default `us`/`en`). Keep the "changing determinism knobs changes what a run means"
  discipline: location becomes part of run metadata, persisted on `audit_runs`.
- **AI Overviews engine**: send `location` (SearchApi accepts city-level names) plus
  `gl`/`hl`. City-level is adequate for AI surfaces — Local Falcon's 60k-simulation
  whitepaper found AIO inclusion only mildly proximity-sensitive (72.0% vs 68.5%
  within 4 miles); rank inside the AIO tracks authority/reviews, not distance. Skip
  geo-grids for now; that's Local Falcon's game, not ours.
- **Engine contract**: `BaseEngine` sends "the query text and nothing else" — keep
  that. Location enters as an engine *constructor/config* parameter for SERP engines
  (it's part of the instrument, like temperature), never injected into the prompt for
  chat engines. Chat engines (ChatGPT, Claude, Perplexity, Gemini) get location only
  via query text ("furnace repair in Berkeley"), which mirrors real user behavior and
  is the only honest emulation available for them anyway.
- **Capture more than the `ai_overview` block.** The engine currently discards the
  local pack and can't see the new **AI local pack** (mobile, 1–2 businesses, ~8% of
  tracked local keywords and rising — Sterling Sky's warning: "most tracking software
  can't see AI Local Packs yet, so you look fine on paper"). Persist the raw SERP JSON
  (payload log already exists) and extract: AIO present/absent, AIO text + citations,
  local-pack entities, AI-local-pack entities if the API exposes the element. Verify
  SearchApi actually parses it; if not, evaluate DataForSEO/SerpApi for this engine.
- **New engine: `google_ai_mode`** (SerpApi `google_ai_mode` engine or DataForSEO
  `serp/google/ai_mode` at $0.004/page). AI Mode and AIO share only ~11–16% of cited
  sources — one is not a proxy for the other, and AI Mode is the surface consumers
  named second (23%) in BrightLocal's survey. Same `BaseEngine` contract: return
  `None` on error, never raise. Note `MAX_ENGINES = 8` needs bumping to 9, or retire
  a parametric chat engine (candidate: `anthropic` — every citation study finds Claude
  negligible for local queries; keep it configured but out of the default engine list
  to save judge budget).

Deliverable: a location-pinned AIO + AI Mode measurement for one real Berkeley HVAC
or plumbing company, runs stored and judgeable.

### Phase 2 — Local query sets and the teaser (Josh's outbound weapon)

- **Intent buckets** (`src/prompts/intent.py`): the funnel buckets (category /
  comparison / brand / problem_aware / adjacent_authority) don't map to local. Replace
  or extend with the three-way split the trigger data demands, because the *surfaces*
  are near-disjoint per intent: `local_intent` ("best plumber in Berkeley", "plumber
  near me") → local pack + AI local pack territory; `hybrid` ("average cost of AC
  replacement in Berkeley") → 97% AIO; `informational` ("how often should a furnace be
  serviced") → 92% AIO, generic advice + citations; keep `brand` ("Is X Plumbing
  legit"). Rebalance `BUCKET_ALLOCATION` accordingly. Prefer explicit-city phrasings;
  tag "near me" variants as a separate, noisier cohort (they're ~2× less stable and an
  API can only approximate them).
- **Per-trade query templates**: build `data/queries_hvac.json`,
  `data/queries_plumbing.json`, `data/queries_barbershop.json` with `{city}` /
  `{brand}` slots — 25–40 queries each covers the trade (the query space really is
  that small). Replace the Oura starter template in `csv_loader.build_template_csv()`.
- **Teaser profile resolver** (`teaser/resolver/profileExtraction.ts`): accept local
  businesses — extract trade category, city/service area (from the site's NAP), and
  competitors as *other local businesses in the same trade+city* (resolvable from the
  local pack / directory results for the trade's head queries, not from LLM knowledge
  of product substitutes). Remove the hard-fail on non-consumer-product categories.
- **Teaser query gen** (`ClaudeQuerySetGenerator.ts`): local templates; kill the
  "growing startup" / "scales with my needs" fallbacks.
- **Teaser copy** (`render/copy.ts`): "buyers" → "customers"/"homeowners". The
  converting format per practitioner evidence, one page: (a) verbatim excerpts of what
  AI Mode/ChatGPT said for "best {trade} in {city}"; (b) the competitors named instead
  of them, by name; (c) red/yellow/green checklist of the 8–10 sources AI actually
  cites (GBP, Yelp, BBB, Angi, Thumbtack, Facebook, Bing Places, Reddit); (d) dollar
  framing ("each HVAC customer is worth ~$15k; 45% of consumers now ask AI"). Skip SOV
  charts and sentiment scores — owners respond to named competitors and phone-call
  economics, not dashboards.
- **Competitor discovery** (`src/pipeline/discovery.py`): `_EXTRACT_PROMPT` says
  "software products, tools, or companies" — reprompt for local business names, and
  seed candidates from the captured local-pack entities (Phase 1) rather than LLM
  recall.

Deliverable: `npm run teaser -- <plumber-url>` produces a credible local teaser;
Josh can scan a city vertical and send each shop its own gap report.

### Phase 3 — Judge and fact sheet (cache-invalidating; do in one bump)

This is the one place the hard invariants bite. Batch every prompt change into a
single `_PROMPT_LAYOUT` bump so the cache is invalidated once, not repeatedly.

- **Accuracy flags**: extend `AccuracyFlagType` with local failure modes —
  `wrong_service_area`, `wrong_hours_or_availability`, `wrong_contact`,
  `wrong_licensing_or_credentials`, keep `identity` and `competitor_confusion`
  (AI Mode has been caught asserting a business's pet policy from the *previous
  tenant* of the address — identity confusion is a documented local hazard, and
  "AI says you don't do emergency calls when you do" is a sellable finding).
  Reword `_ACCURACY_BLOCK` examples from Oura pricing to local facts; severity
  `high` = "would change whether a customer calls."
- **Prominence/framing**: unchanged — the definitions are audience-neutral.
- **Discipline** (per geo-dev skill): bump `_PROMPT_LAYOUT`, keep the HEAD/RUBRIC
  split markers intact so `tests/test_judge.py` parity guards pass, keep
  `scripts/judge_via_workflow.py` in sync, expect every cached verdict to miss, and
  re-warm via `/prejudge` (free on subscription). Old startup-client runs stay
  comparable to themselves only — note it in the report if ever re-judged.
- **Fact sheet template** (`docs/fact-sheet-template.md`): new local variant —
  identity (legal name, DBA, trade, GBP listing URL); service area (cities/ZIPs,
  emergency coverage); hours; services offered / NOT offered; licensing & insurance
  (license #, bonded); reviews snapshot (GBP/Yelp count + rating); pricing only as
  "service-call fee / free-estimate policy" (trades quote per-job — drop the SKU
  section); known-inaccuracy watch-list (old address, previous tenant confusion,
  wrong service area).
- **New measurement dimension — entity presence.** For local-intent queries the
  recommendation mostly is *not* prose: it's the business appearing in place cards /
  local pack / AI local pack. The judge only reads answer text. Add a deterministic
  `entity_presence` check per cell (name-match against captured pack entities from
  Phase 1 — pure parsing, no LLM, no cache-key impact) and report it alongside judged
  prose mentions. Without this, we'd tell a plumber "you're absent" while they sit in
  the AI local pack — the report would be wrong in the embarrassing direction.
- **New gold set + recalibration.** Every calibration number was measured on
  Oura/Fort consumer answers. Build a local-services gold set (~50 labeled answers
  from real Phase 1 runs across 2–3 trades), label per `docs/labeling-guide.md`, rerun
  `scripts/run_calibration.py` (isolated cache, held-constant API judge — never
  prejudge/Opus verdicts) and re-derive grade bands. Until this is done, don't put
  letter grades in client deliverables — use mention/presence rates.

### Phase 4 — Site audit for local (Cat 5, Cat 6, Cat 3/4)

- **Cat 6 offsite — the biggest rework.** Replace the consumer-startup channel list:
  - `offsite/tools.py` `REVIEW_PLATFORMS` → `yelp.com`, `bbb.org`, `angi.com`,
    `thumbtack.com`, `homeadvisor.com`, `facebook.com`, plus GBP and Bing Places
    (Whitespark: Facebook is the #1 review source in Bing Places, and ChatGPT rides
    Bing's local stack).
  - `offsite/agent.py` `_SYSTEM` → hunt: GBP completeness/review velocity, Yelp
    profile + best-of lists, BBB/Angi/Thumbtack presence, Reddit + local subreddits
    (r/hvacadvice, r/{city}), NAP consistency across listings. Drop App Store /
    Trustpilot / creator coverage.
  - `offsite/models.py` `FindingType` → add `directory_listing`, `gbp`,
    `nap_consistency`.
  - Report framing: "you're absent from Yelp/Angi, which received X% of AI citations
    for your query set" — the citation-gap map is the concrete, sellable action item.
  - Watch-out: Yelp/GBP anti-bot is aggressive (the "B2C startup sites are
    cooperative" assumption in project-queue §2 no longer holds). Prefer official
    APIs/DataForSEO endpoints over scraping.
- **Cat 5 schema** (`checks/schema.py`): `_CATEGORY_EXPECTED["homepage"]` →
  `{LocalBusiness}` (validator already grades LocalBusiness; it just never *expects*
  it). Content-match address/phone/hours against visible text. Keep it honest in
  client copy: controlled evidence says schema does not drive AI citations —
  Ahrefs' matched-control study found no citation lift (AIO slightly *negative*)
  and its retrieval experiment showed AI fetchers read visible HTML, ignoring
  JSON-LD entirely; Search Atlas found no correlation ("only Bing confirms use"
  still needs its own source before repeating it). It's cheap hygiene and entity
  clarity, not a headline promise. Same for llms.txt: Google has said outright it
  doesn't and won't use it, and SE Ranking's ~300k-domain analysis found zero
  correlation with AI citations — never sell llms.txt work; it is now note-only
  in the rubric (dropped as a scored check).
- **Cat 3/4 content**: reframe "consumer question space" checks around service pages +
  location pages + conversational FAQs (Whitespark's AI-visibility factor survey puts
  on-page content first at 24% for AI surfaces, vs GBP-dominated pack ranking; Google's
  Search Console AI report confirms service/location pages are what surfaces). The
  blog/E-E-A-T `ContentJudge` checks (`original_data`, `expert_commentary`) mostly
  don't apply to a 5-page plumber site — make them N/A-able rather than auto-fail.
  Content-judge rubric changes bump `CONTENT_RUBRIC_VERSION` (own cache, same
  discipline).

### Phase 5 — Metrics, report, sampling

- **Segment everything by intent bucket.** Surfaces are near-disjoint per intent; a
  blended visibility score whipsaws when Google shifts the mix and is meaningless to
  boot. Report per-bucket: local-intent (pack/AI-pack presence), hybrid+informational
  (AIO citation/mention), per-engine.
- **Three tracked states for AIO cells**: no-AIO-for-query / AIO-present-brand-absent /
  AIO-present-brand-cited. Report absence as a time series; never let a Google-side
  AIO pullback read as "you lost your recommendation" in `compare` deltas
  (`src/pipeline/trend.py`).
- **Sampling**: `RUNS_PER_QUERY = 5` already exists for chat-engine wobble — apply the
  same K to SERP engines (currently effectively 1 fetch) given ~80% URL run-to-run
  turnover. Score presence as a rate ("in 4/5 samples"), which is also exactly the
  honest-marketing posture. Cost: ~40 queries × 3 SERP surfaces × 5 samples ≈ 600
  fetches ≈ single-digit dollars per audit at SERP-API rates — well inside
  `MAX_AUDIT_COST_USD = 25`; judge spend still dominates and prejudge keeps it free.
- **Report copy** (`src/api/reports.py`, teaser): pair visibility with the behavior
  facts — AIO presence cuts top-result CTR ~34.5% (Ahrefs, 300k keywords), only ~1% click AIO
  sources (Pew), 88% of AI users verify on review platforms (BrightLocal), GBP
  call-clicks decaying (Sterling Sky). Narrative: "AI decides the shortlist; your
  reviews close the deal; your phone rings less unless you're on the shortlist."

### Sequencing and effort

Phase 1 → 2 gets a sellable teaser fastest and touches no caches. Phase 3 is one
coordinated cache-invalidating change. Phase 4/5 complete the paid audit. Rough
order of effort: Phase 2 teaser resolver ≈ Phase 4 offsite rework > Phase 3 judge+
gold set > Phase 1 plumbing > Phase 5 metrics.

## 4. Invariants this plan respects (checked against CLAUDE.md / geo-dev)

- Engines return `None`, never raise; new AI Mode engine subclasses `BaseEngine`.
- All judge-prompt changes in one `_PROMPT_LAYOUT` bump; parity tests stay; prejudge
  re-warms; `judge_via_workflow.py` HEAD/RUBRIC split kept in sync.
- Calibration uses the held-constant API judge with `isolated_cache()`; prejudge/Opus
  verdicts never feed gold labels.
- Storage stays create-only; new fields are additive columns/JSON, no schema breaks.
- Secrets via `settings.py` only; new keys (SerpApi or DataForSEO if adopted) follow.
- Cost gates respected; SERP sampling is cheap, judge spend rides the prejudge flow.

## 5. What we deliberately do NOT build

- Geo-grid rank tracking (Local Falcon's moat; city-level uule suffices for AI
  surfaces per the proximity data).
- llms.txt tooling or "AI-optimized content rewriting" services (no evidence; ~80% of
  GEO is repackaged SEO fundamentals per Digiday's expert panel — our value is the
  *measurement*, judged answer quality, and the citation-gap map).
- Placement guarantees, "rank #1 in ChatGPT" claims, or single-fetch "rankings"
  (volatility + FTC posture; report sampled rates with uncertainty).
- Claude as a paid-audit engine for local (negligible in every local citation study;
  keep for completeness runs only).

## 6. Key sources

Consumer behavior: BrightLocal LCRS 2026 (brightlocal.com/research/lcrs-ai-trust/) ·
Yelp/Morning Consult via PPC Land · GatherUp Q3 2025. Trigger/surface data: Whitespark
AIO prevalence study + AI Mode guide + 2026 Local Search Ranking Factors (whitespark.ca)
· Sterling Sky State of Local SEO 2026 + AI local packs (sterlingsky.ca) · Semrush AIO
study · BrightEdge. Volatility: SE Ranking AI Mode volatility test + AI Mode research
(seranking.com). Citations: Foundation Marketing + AirOps via ppc.land · Local
Dominator citations report · Whitespark Bing/ChatGPT review-site study. Proximity:
Local Falcon AIO whitepaper. CTR: Pew (July 2025) · Ahrefs (2025 + Feb 2026 update).
APIs: SerpApi google_ai_overview / google_ai_mode · SearchApi.io AI Overview docs ·
DataForSEO AI Mode. Economics: WhatConverts HVAC CPL/LTV · BDR · Arc4 / GoodFirms SEO
pricing. Market: Digiday GEO-skepticism pieces · tryprofound.com/pricing · Surmado
tool roundup. Risk: FTC Operation AI Comply + FTC v. Air AI · Google on llms.txt
(seroundtable.com).
