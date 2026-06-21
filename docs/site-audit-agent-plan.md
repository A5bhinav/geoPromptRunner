# Site Audit Agent — Design & Feasibility Plan

_Automating the GEO/AEO technique checklist (Categories 1–6). Companion to the
audit method in `docs/project.md` and the answer-analysis discipline already
proven in `src/pipeline/`._

---

## 1. The goal, restated

Today, a client audit splits cleanly into two halves:

- **Automated (the runner):** Category 7, Baseline Measurement — already built
  in `src/engines/*` and `src/pipeline/*`. We run the query set across engines,
  judge the answers, and roll up mention/citation/share-of-model.
- **Manual (the analyst):** Categories 1–6 — the on-site and off-site inspection
  the method doc explicitly tags as analyst work (Steps 2–5). This is the slow,
  human-labor part we want to cut down.

This document scopes the second half: what it takes to make the technique
checklist run itself, how feasible each category is, and the architecture to
build it on top of what already exists.

## 2. Bottom line up front

**Feasibility: yes, and most of the foundation already exists.** Two of the
seven categories are effectively done. The remaining work is well-defined and
maps cleanly onto patterns already in the repo.

**Key framing — this is mostly a *pipeline*, not one autonomous agent.** The
same reproducibility discipline the answer-analysis schema insists on
(objective primitives → deterministic rubric → calibrate against a hand-labeled
gold set) applies here. Building Categories 3–5 as an autonomous free-roaming
agent would reintroduce exactly the nondeterminism that schema works to kill.
The right design is:

- **Deterministic checkers** wherever a verdict can be measured from bytes.
- **An LLM-judge layer** (cloned from `judge.py`) where judgment is irreducible,
  always evidence-backed and calibrated to a gold set.
- **A bounded web-research agent** for the one genuinely agentic part —
  Category 6, the open web.

## 3. Current state in the codebase

_Updated after commit `fb3e7a2` ("Add Site Audit pipeline") — the pipeline below is
now **built and tested**, not just planned. Remaining work is the build-out backlog
in §11 plus the gold-set calibration in §7._

| Category | Status | Where |
|---|---|---|
| 1 · Technical Accessibility | **Built** (fidelity gaps — §11) | `src/audit/technical_check.py` |
| 2 · Content Coverage / Internal Linking | **Built** (minor enhancement — §11) | `src/audit/checks/links.py` |
| 3 · Content Structure & Extractability | **Built**, LLM judge **gated** on gold set | `checks/content_judge.py`, `content_primitives.py` |
| 4 · Content Substance / E-E-A-T | **Built**, LLM judge **gated** on gold set | `checks/content_judge.py`, `content_primitives.py` |
| 5 · Structured Data / Schema | **Built** (gaps — §11) | `src/audit/checks/schema.py` |
| 6 · Offsite Authority & Entity Consensus | **Built** (minor enhancement — §11) | `src/audit/offsite/agent.py`, `tools.py` |
| 7 · Baseline Measurement | **Built** | `src/engines/*`, `src/pipeline/*` |

Orchestration lives in `src/audit/site_audit.py`; it runs as a concurrent best-effort
phase in `src/api/runner.py` (the §6 design) and persists to `site_audit_*` Supabase
tables (`data/schema_site_audit.sql`). The original Category-1 curl recipes (Comments
1–6) became `fn(domain) -> CheckResult{status, details}` functions — the template the
rest follows. A fidelity audit against those recipes found the gaps tracked in §11.

## 4. Per-category automation map

Each checklist item is tagged by method:
**[D]** deterministic · **[J]** LLM judge · **[W]** web-research agent ·
**[B]** buy (commodity API, not worth building).

### Category 1 — Technical Accessibility — DONE (with two evidence-driven upgrades)
All six checks exist. Research (§9) flags two upgrades worth making:

- **SSR-vs-CSR is the single highest-value finding in the whole audit**, because
  major AI crawlers (GPTBot, ClaudeBot, PerplexityBot, OAI-SearchBot, CCBot) do
  **not execute JavaScript** — only Google/Gemini and AppleBot render (§9.1).
  Strengthen the check: compare `trafilatura`-extracted text from raw vs rendered
  HTML by ratio, not raw byte length, and explicitly test whether the SPA shell
  is *empty* (the `id="root"` marker alone is **not** proof of CSR — modern
  Next.js SSR uses it too).
- **Swap the robots.txt matcher.** The current code uses Python's
  `urllib.robotparser`, which is subtly non-compliant (first-match instead of
  RFC 9309 longest-match + Allow-precedence) and only fixed on very recent Python
  patch releases. Move to **Protego** (the Scrapy default, Google-compatible).
  The crawler-access UA-probe also has a false-positive trap — see §9.3.

- robots.txt AI crawlers **[D]** — built
- CDN/WAF UA block **[D]** — built (`check_crawler_access`)
- Server-rendered vs JS **[D]**, upgrade with headless confirm — built
- llms.txt **[D]** — built
- XML sitemap present/current **[D]** — built
- Target content not gated **[D]** — built (heuristic)

### Category 2 — Content Coverage / Question-Space Mapping
- Topic-cluster / question-space coverage — **[D]** crawl + **[J]** map pages to
  funnel stages and find holes against the client's query set + personas
- Internal linking / topical authority — **[D]** build the link graph: pull
  `href`s per page (Comments 7/8), classify nav/footer vs in-content, detect
  orphans against the sitemap, score anchor-text descriptiveness **[J]**

Verdict: an in-house mini-Screaming-Frog (already mused about in Comment 7),
plus one LLM pass for the coverage judgment.

### Category 3 — Content Structure & Extractability
- Answer-first 40–60 word lead — **[J]**
- Headings written as questions — **[D]** regex/heuristic + **[J]**
- Self-contained chunks — **[J]**
- Definition-first sentences ("X is …") — **[D]** + **[J]**
- Scannable formatting (para length, lists, tables) — **[D]**
- TL;DR / direct-answer block — **[D]** + **[J]**
- Transcripts / alt text — **[D]**

Verdict: an LLM judge over fetched page text, in the exact mold of `judge.py`.
Comments 22–27 are already hand-labeled gold for Fort.

### Category 4 — Content Substance & Credibility (E-E-A-T)
- Fact density (stats per 150–200 words) — **[D]** number/stat regex + **[J]**
- Citations to authoritative external sources — **[D]** outbound-link analysis + **[J]**
- Expert quotes / original commentary — **[J]**
- Original data / first-hand / case studies — **[J]**
- Named authors with bios/credentials — **[D]** byline/Person-schema + **[J]**
- Visible last-updated date + refresh cycle — **[D]** (`dateModified`, visible dates)
- On-site comparison content ("X vs Y", "alternatives", "best X for …") — **[D]** URL/title patterns + **[J]**

Verdict: same LLM judge. Subjective but tractable when evidence is required and
the judge is calibrated.

### Category 5 — Structured Data / Schema
- Schema present & valid — **[D]** extract JSON-LD + validate **in-house** (JSON
  syntax + per-type required/recommended props). No public validation API exists —
  see §9.2; don't depend on validator.schema.org / Rich Results Test.
- Relevant types implemented — **[D]** map features→types (Comment 11 is a
  decision table → code), list `@type`s, diff to a should-have set
- Schema matches visible content — **[J]** compare schema field values to page
  text (Comment 12); flags fabricated ratings / stuffing
- Entity identifiers consistent (sameAs) — **[D]** extract + resolve sameAs links,
  + **[J]** name/description consistency (Comment 13)

Verdict: mostly deterministic, high signal, a good early win.

### Category 6 — Offsite Authority & Entity Consensus
- Brand entity consistent across web — **[W]** SERP/Knowledge Graph + **[J]**
- Community presence (Reddit, forums, Q&A) — **[W]** SERP `site:reddit.com` search +
  the **official Reddit API** (§9.4 supersedes the `.json` trick in Comment 15)
- Review platforms (App Store / Play Store / Trustpilot) — **[W]/[B]** scrape or API (brittle)
- Third-party citations / press / backlinks — **[B]** Ahrefs/Semrush/Moz API at
  scale; **[W]** Google News for the press sweep (you already concluded the
  backlink layer isn't worth building — Comment 14)
- Wikipedia / Wikidata entity — **[D]** Wikidata API + Wikipedia search (Comment 18)
- "Best [category]" listicles naming the client — **[W]** search + **[J]**

Verdict: the only genuinely agentic category. Start with the cheap, reliable
pieces (Wikidata, Reddit, SERP); buy the commodity backlink/review data later.
Cross-reference findings against the runner's "sources behind the category."

### Category 7 — Baseline Measurement — DONE (the runner)

## 5. Proposed architecture

> **Implementation detail lives in `site-audit-implementation-guide.md`** — the
> code-level how-to for each tier below (library calls, concrete thresholds,
> production gotchas, and ideal-vs-practical verdicts), backed by a second research
> pass.

A **Site Audit pipeline** under `src/audit/`, one orchestrator over four tiers:

```
                    ┌─────────────────────────┐
                    │   Site Audit Orchestrator│
                    └───────────┬─────────────┘
                                │
   ┌────────────┬───────────────┼───────────────┬──────────────┐
   ▼            ▼               ▼               ▼              ▼
Fetch &     Deterministic   LLM-Judge       Web-Research    Roadmap
Cache       Checkers        Layer           Agent (Cat 6)   Synthesizer
(crawler)   (Cat 1,5,2,     (Cat 3,4,        (search/fetch/  (rubric.py →
            3/4 primitives)  parts 2/5)       Reddit/Wikidata) §4/§5 + report)
```

**1. Fetch & cache layer.** A two-tier crawler (evidence-backed in §9): **raw
HTTP via `httpx` first, headless `Playwright` render only when needed.** It pulls
the priority page set (homepage + sitemap-derived: pricing, product, docs, blog,
comparison pages) and for each page stores: raw HTML, headless-rendered HTML,
extracted main-content text via **`trafilatura`** (top-benchmarked extractor),
and parsed JSON-LD via **`extruct`**. Everything downstream reads this cache — no
check re-fetches. Reuse the existing `net_guard` SSRF protection. Storing raw +
rendered both is not wasteful: their diff *is* the SSR-vs-CSR signal (§9.1), and
it powers the Cat 5 "schema matches visible content" check for free.

**2. Deterministic checkers.** Extend the existing `fn(domain) -> CheckResult`
pattern. Cat 1 (done), Cat 5 parsing, Cat 2 link-graph/orphans, the Cat 3/4
primitives. Pure functions, unit-testable, reproducible.

**3. LLM-judge layer.** Clone the `judge.py` discipline exactly: structured
output, **mandatory evidence span**, `confidence` + `needs_review`, versioned
rubric/vocab, one judge per check family. The label is computed from a rule the
same way the answer schema computes prominence — not a gestalt call.

**4. Web-research agent (Cat 6 only).** A bounded tool-using loop: web search,
page fetch, **official Reddit API**, Wikidata `wbsearchentities`, and
DataForSEO/Ahrefs for backlinks (per §9.4). Returns structured findings, not prose.

**5. Roadmap synthesizer.** Feed all results into the existing `rubric.py` →
roadmap → report machinery (§4/§5 tables, impact/effort/controllable tagging).
Cross-reference Cat 6 cited sources with the runner's category-source ranking.

## 6. Integration: one linear run, not a separate tool

The site audit should ride the **existing CSV-upload flow**, not become a second
tool an analyst has to run and then hand-merge. This works because the input it
needs is already there: `RunConfig.client_domains` is parsed from the uploaded
CSV at preview time. The moment someone uploads, we already know both the query
set to run *and* the domain to scrape — no second input, no jumping between
sites, no manual data transfer.

**Current flow (unchanged for the user):**

```
upload CSV → /audits/preview (parse + validate) → /audits → start_run() → _execute_run() → report
```

**Where the site audit plugs in.** `_execute_run()` in `src/api/runner.py` is the
single orchestration point. Today it runs two phases on its background thread:
the engine fan-out (`run_query_set`) then the answer judge (`_run_judge`), then
builds the report. Add the site audit as a **third phase in the same function**:

1. Carry its output on `_RunState` alongside `results` and `judgments` (e.g. a
   `site_audit` field).
2. Run it as a phase in `_execute_run` — **concurrently** with the engine
   fan-out, since the two are independent (the scrape doesn't need the answers
   and vice versa). Parallelizing means "linear for the user" doesn't mean
   "slower under the hood": both finish before the report step.
3. Fold the results into the report in `build_report` (`src/api/reports.py`), so
   the §4 technical / §4.2 on-site / §4.3 off-site tables populate from the site
   audit instead of from hand-entered `RubricScore` rows.

The result: **one `run_id`, one progress bar, one report object.** The UI
conceptually doesn't change.

**Follow the "best-effort, never blocks" pattern already in the code.** Note how
`_run_judge` is wrapped so a run still completes (with a report) if the judge
can't build. Apply the same per site-audit phase, because they have very
different reliability profiles: Cat 1 checks are fast HTTP and almost always
succeed; the Cat 3/4/5 LLM site-judge is slower; Cat 6 (offsite web research) is
slowest and flakiest. Making each phase additive and degrade-gracefully means
the report always renders even when the web-research part times out — instead of
one slow scrape blocking the whole audit.

**One small status-model extension.** Today `total_calls` and the per-engine bars
are counted in engine calls (`RunStatus` / `EngineStatus`). Either add the
site-check steps into that denominator, or — cleaner — add a small parallel
status block (e.g. `site_checks: 4/6`) to `RunStatus`. This is the one place the
status model has to grow.

**Touch points summary:** `RunConfig.client_domains` (input, already parsed) →
`_execute_run` (new third phase) → `_RunState.site_audit` (carry results) →
`build_report` (merge into §4) → `RunStatus` (progress).

## 7. The non-negotiable: a site gold set

Replicate the gold-set discipline already used for answers. Hand-label Fort
(Comments 22–27 are the seed) plus one or two more sites, freeze and date-stamp
it, and grade the on-site/E-E-A-T judge against it before trusting any verdict
in front of a client. Calibrate the "partial" thresholds the same way
`W_ENGAGE` / `S_MID` were calibrated. Without this, the subjective categories
drift and the report loses credibility.

## 8. Build sequence

1. **Fetch/cache + headless render layer** — unlocks everything; strengthens the
   Cat 1 rendering verdict.
2. **Cat 5 schema checker** — mostly deterministic, high signal, quick win.
3. **Cat 3 + 4 LLM judge** — built and calibrated against a Fort-seeded gold set.
4. **Cat 2 crawl / link-graph / orphans.**
5. **Cat 6 research agent** — Wikidata + Reddit + SERP first; buy backlinks/reviews later.
6. **Wire all results into the rubric → roadmap → report.**
7. **Fold into the linear run** (§6) — add the site-audit phase to `_execute_run`
   so a single CSV upload drives engines + scrape + checks into one report.
   (Can land incrementally: wire Cat 1 in first since it's already built, then
   add phases as each category lands.)

## 9. Evidence review — what the research validated, refined, or changed

A deep, adversarial research pass (multi-source, claims cross-checked) was run on
every method choice in this plan. Each decision below carries a verdict —
**KEEP** (validated), **REFINE** (mostly right, sharpened), or **CHANGE** (the
evidence moved us) — with the key sources. Bottom line: the architecture held up
well; the meaningful changes are a better extractor library, a correct robots.txt
parser, a documented false-positive in the bot-block check, and switching Reddit
from scraping to the official API.

### 9.1 Crawling, rendering & SSR detection — KEEP + REFINE
- **Two-tier httpx → Playwright is correct.** Playwright is the best Python
  headless option (native Python; faster than Selenium; Puppeteer has no Python).
  Hosted APIs (Firecrawl/ScrapingBee/Apify) are a fallback only — recurring cost,
  output drift hurts reproducibility; if used, self-host Firecrawl. Screaming Frog
  has a real CLI for breadth but isn't a clean library dependency.
- **REFINE — use `trafilatura` for main-content extraction.** It is the
  top-ranked extractor in both its own and independent academic benchmarks
  (F1 ≈ 0.91), beating readability-lxml, boilerpy3, newspaper3k; some of those
  even error on real-world HTML. ([Trafilatura eval](https://trafilatura.readthedocs.io/en/latest/evaluation.html), [Bevendorff 2023, ACM](https://dl.acm.org/doi/pdf/10.1145/3539618.3591920))
- **KEY EVIDENCE — AI crawlers don't run JavaScript.** Vercel + MERJ analyzed 1B+
  fetches (Dec 2024): GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot,
  PerplexityBot, Bytespider, CCBot render **no** JS. Only Google/Gemini (via
  Googlebot) and AppleBot render. This is *why* the SSR check is the highest-value
  finding: JS-injected content is invisible to most AI engines regardless of
  robots.txt. (A circulating claim that "ClaudeBot executes JS" is **false** per
  the primary data.) ([Vercel/MERJ](https://vercel.com/blog/the-rise-of-the-ai-crawler))
- **REFINE — SSR detection method.** Compare `trafilatura`-extracted *main text*
  from raw vs rendered HTML as a ratio; ~1.0 = SSR, ~0 = CSR. Do **not** use raw
  byte length (rendered DOM is always bigger). The `id="root"`/`__next` marker is
  **not** proof of CSR — test whether the shell is *empty*. Also: content in the
  initial HTML byte stream (inline JSON, `__NEXT_DATA__`) *is* ingested, so
  "server-rendered" means "present in raw HTML," not "rendered by a browser."

### 9.2 Schema extraction & validation — KEEP, with a framing correction
- **`extruct` is the right extractor** (still maintained, v0.18.0 Nov 2024;
  covers JSON-LD + Microdata + RDFa). BeautifulSoup is a JSON-LD-only fallback.
- **No official validation API exists — confirmed by the schema.org project lead.**
  Neither validator.schema.org nor Google's Rich Results Test has a public API
  ([schema.org issue #3262](https://github.com/schemaorg/schemaorg/issues/3262)).
  Build validation in-house (JSON syntax + per-type required/recommended
  properties), optionally hardened with **pySHACL/Schemarama**; use the GSC URL
  Inspection API only for spot-checking already-indexed pages.
- **CORRECTION to framing.** Independent testing found ChatGPT/Perplexity treat
  schema markup as *plain text*, with no privileged channel; vendor "2.5×
  citations" claims are marketing. So sell schema in the report as
  "machine-legibility + Google rich-result eligibility," **not** a proven direct
  AI-citation boost. ([SE Roundtable](https://www.seroundtable.com/chatgpt-perplexity-structured-data-text-40862.html))

### 9.3 robots.txt & bot-blocking — CHANGE (two real fixes)
- **CHANGE — replace `urllib.robotparser` with Protego.** The stdlib parser uses
  source-order first-match, violating RFC 9309's longest-match + Allow-precedence
  (e.g. it wrongly blocks `/admin/public/` when an `Allow` should win). It's an
  acknowledged CPython bug fixed only on recent 3.13/3.14 patch builds. The repo's
  `requires-python` is **3.11**, so the buggy parser is in scope and the fix can't be
  relied on — Protego (the Scrapy default, Google-compatible) is the right call. ([CPython #138907](https://github.com/python/cpython/issues/138907), [Protego](https://pypi.org/project/Protego/))
- **REFINE — `-Extended` tokens aren't fetchable UAs.** `Google-Extended` and
  `Applebot-Extended` are robots.txt *opt-out directives*, not crawlers that send
  requests. Check them in the robots.txt parse, but **don't** include them in the
  UA-probe loop.
- **CHANGE — the crawler-access check has a documented false-positive.** WAFs
  verify bot identity by UA **and source IP** (FCrDNS). Spoofing "GPTBot" from our
  own server IP looks like a *fake* bot, so a 403 may not mean the real GPTBot
  (from OpenAI's verified ranges) is blocked. Label results as "reachability from
  an unverified IP," not "the real bot is blocked," and corroborate with client
  server logs where ground truth matters. ([Cloudflare fake-bot rules](https://developers.cloudflare.com/waf/troubleshooting/fake-bot-managed-rules/))
- **REFINE — Cloudflare claim.** Its default AI-bot block applies to **new**
  domains onboarded after Jul 1 2025 (plus a one-click toggle), **not**
  retroactively to all existing sites. Report a Cloudflare block without
  over-asserting the owner's intent. ([Cloudflare, Jul 1 2025](https://www.cloudflare.com/press/press-releases/2025/cloudflare-just-changed-how-ai-crawlers-scrape-the-internet-at-large/))

### 9.4 Offsite data sources — REFINE + one CHANGE
- **CHANGE — drop the Reddit `.json` trick for the official API.** The `.json`
  endpoint still responds but is throttled (~10 req/min unauth) and violates ToS;
  Pushshift is now moderator-only. Use the official Reddit Data API via OAuth
  (100 QPM free tier; paid for commercial volume). This supersedes the transcript's
  Comment 15 note. ([Reddit API controversy](https://en.wikipedia.org/wiki/Reddit_API_controversy))
- **REFINE — Wikidata.** Use the `wbsearchentities` API as the primary
  entity-presence check (not SPARQL/WDQS, which is rate-limited and under load).
  Google Knowledge Graph API still works but pruned ~3B entities in 2025 — treat
  presence as positive signal, absence as non-authoritative.
- **KEEP — buy backlinks, don't build.** Ahrefs indexes ~35T links crawling ~6B
  pages/day; replicating it is infeasible. Buy from Ahrefs/Semrush/Moz/DataForSEO;
  OpenPageRank/Common Crawl are free directional fallbacks. ([how Ahrefs gets data](https://shahidshahmiri.com/how-does-ahrefs-get-its-data/))
- **REFINE — reviews: prefer official APIs + licensed aggregators.** Use Trustpilot
  Business / App Store Connect / Google Play Developer APIs for own-brand, and
  aggregators (Appbot, AppFollow) for competitor coverage. Scraping G2/Capterra is
  the highest-risk path (no API). Legal backdrop is favorable for logged-out public
  data (*Meta v. Bright Data* 2024) but risk concentrates on login/ToS/copyright.

### 9.5 LLM-as-judge — KEEP (well-founded), with three refinements
- The plan's discipline — deterministic primitives, LLM only for subjective calls,
  evidence spans, confidence/`needs_review`, gold-set calibration — **matches
  current best practice** (Anthropic eval guidance; Braintrust/Evidently hybrid
  consensus). Few-shot gold calibration is the best-evidenced lever (raised judge
  consistency 65%→77.5% in Zheng et al.). ([Building effective evals — Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), [Zheng et al.](https://arxiv.org/abs/2306.05685))
- **REFINE 1 — reasoning-first ordering.** Forcing the label out first in a rigid
  JSON schema can degrade reasoning ("Let Me Speak Freely?"). Emit the evidence
  span + reasoning *then* the label. ([Tam et al. 2024](https://arxiv.org/abs/2408.02442))
- **REFINE 2 — sample borderline items multiple times.** LLM judges are
  self-inconsistent even at temperature 0 ("Rating Roulette"); aggregate a few
  passes and route disagreement to `needs_review`. (This mirrors the answer
  schema's existing K=3 self-consistency.) ([Rating Roulette](https://aclanthology.org/2025.findings-emnlp.1361/))
- **REFINE 3 — set expectations / consider a classifier.** Target ~80%+ aggregate
  agreement with gold; graded scoring is harder than pairwise. For any *stable,
  high-volume* subjective check, a fine-tuned DeBERTa/RoBERTa classifier can match
  the LLM judge at lower cost and full reproducibility once enough gold labels
  exist.

### 9.6 Architecture & llms.txt — KEEP (strongly validated)
- **Pipeline-for-on-site / agent-only-for-offsite is exactly right.** Anthropic's
  "Building Effective Agents" and the broader 2024-25 consensus: constrain to a
  fixed workflow for repeatable, auditable, same-input-same-output tasks; reserve
  open-ended agency for genuinely open tasks like web research. Keep even the
  in-pipeline LLM calls constrained and schema-validated. ([Anthropic](https://www.anthropic.com/research/building-effective-agents))
- **llms.txt low-severity is CONFIRMED, arguably informational-only.** An Ahrefs
  study of 137,210 domains found 97% of llms.txt files got **zero** requests; AI
  *retrieval* bots were ~1.1% of traffic; Google says it's unnecessary and no
  major engine consumes it. A missing llms.txt has near-zero AI-visibility impact
  today (its only real use is coding-agent doc parsing; a stale one is a mild
  prompt-injection risk). ([Ahrefs llms.txt study](https://ahrefs.com/blog/llmstxt-study/))
- **Strategic note (competitive landscape).** Funded incumbents (Profound, Peec,
  Otterly, Scrunch) are overwhelmingly *off-site mention-trackers*; rigorous,
  reproducible *on-site technical auditing* is under-served. The plan's
  deterministic on-site pipeline + agentic off-site layer occupies a defensible,
  differentiated middle ground.

## 10. Honest caveats & risks

- Google Rich Results Test has no public API — validate schema via the schema.org
  validator endpoint or headless render.
- Reddit / review-platform scraping is brittle and carries ToS friction.
- E-E-A-T judgments are irreducibly subjective — always surface evidence, never a
  bare score; calibrate to the gold set.
- Some Cat 6 data (Ahrefs-grade backlinks) is genuinely not worth building — buy
  the API.
- "Partial" thresholds across the judge need calibration, exactly like the answer
  schema's numeric thresholds.
- **Browser runs self-hosted, never a third-party hosted browser** (Browserbase/
  Browserless-cloud/etc.) for client crawls — that would make the vendor a GDPR
  sub-processor (DPA + client disclosure). Subprocess-per-crawl gives isolation while
  keeping client content in our perimeter. See implementation guide §6.5 (locked
  decisions) for the full browser-memory mitigation ladder.

## 11. Build-out backlog (post-build gaps) — CLOSED

A fidelity audit of the shipped pipeline against the transcript's 27 curl-recipe
comments found checks that dropped a recipe step or measured a generic client view
instead of the GPTBot view. **All P1–P3 items are now closed** (post-`fb3e7a2`
follow-up); full per-item detail of what shipped is in **implementation guide §9**.

**P1 — correctness/fidelity:** ✅
- Robots → **Protego** matcher (+ crawler honors Disallow/Crawl-delay via `crawl/robots.py`).
- llms.txt **Content-Type check** — `200 + text/html` app-shell → absent (C4).
- Gated content **real recipe** — GPTBot UA, walk priority pages, detect redirect-to-login /
  401-403 / login stub (C6).
- WAF: **Cloudflare challenge body at 200** detected; **OAI-SearchBot** added to the probe (C2).

**P2 — completeness:** ✅
- **GPTBot UA** on rendering/sitemap/llms.txt/gated checks (C3/C5/C6).
- Sitemap **Content-Type check + `<loc>` count** (C5).
- Schema **features→types should-have inference** (C11) + **sameAs extraction/classification**
  (C13; offline — live profile resolution deferred to the offsite layer).

**P3 — enhancement:** ✅
- Links: sitemap-coverage evidence (`sitemap_not_internally_linked`) from the full
  discovered sitemap (C7).
- Per-competitor on-site **"X vs {competitor}" comparison coverage** check (C19).

**Separate from the backlog — the gold set (§7).** The Cat 3/4 LLM judge
(`content_judge.py`) is built but gated until a hand-labeled page gold set reaches
κ ≥ 0.6. That's a human labeling task, not a coding task, and it's the critical path to
a *complete* audit (P1–P3 above are about making the already-live checks faithful).

---

_Maps to the existing repo: extends `src/audit/`, mirrors `src/pipeline/judge.py`
and the answer-analysis gold-set methodology, and outputs into the established
`rubric.py` roadmap/report._
