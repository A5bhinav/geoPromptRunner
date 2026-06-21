# Site Audit — Implementation Guide

_Companion to `site-audit-agent-plan.md`. That doc decides **what** to build and
**which** tools to use; this one decides **how** to build each piece, with the
code-level patterns, concrete thresholds, library/version calls, and — most
importantly — where the textbook-ideal approach breaks in production and what the
pragmatic compromise is. Every recommendation is backed by research (sources per
section)._

Reading order: this guide is organized by the same tiers as the plan's §5
architecture — fetch/cache, SSR detection, deterministic checkers, LLM judge,
offsite agent, runner integration.

---

## 0. The one cross-cutting principle the research kept surfacing

**Ideal is almost always "always render / always sample / full formal rigor."
Practical is "do the cheap deterministic thing first, escalate only the residue."**
This shows up in every tier: render only thin pages, K-sample only borderline
judgments, curate a requirements dict instead of a SHACL engine, run a
deterministic pre-pass before the agent loop. Build the cheap path first; spend
the expensive path only where the cheap path is genuinely insufficient.

---

## 1. Fetch & cache layer

### 1.1 Conditional rendering (don't always use Playwright)
A headless render is ~10–50× the cost of an httpx GET, so **fetch raw with httpx
first, escalate to Playwright only when the raw fetch is insufficient.** Trigger
escalation if any of: extracted main text is thin (`< ~200–500` chars);
`trafilatura.is_probably_readerable(html)` returns `False` (cleanest off-the-shelf
gate, ported from Mozilla Readability); a small body contains an empty SPA mount
point (`<div id="root|app|__next">`) with a high script-to-text ratio. **Optimization:**
once a domain's homepage escalates, memo the whole domain as "render-required" and
skip the wasted httpx-first probe on its other pages. Short-circuit the other way
too: if content is already in an inline JSON/`__NEXT_DATA__` payload, skip the
browser entirely (parse the payload). *Ideal (always render) is impractical at
volume; the conditional ladder is the standard.*

### 1.2 Playwright in production
- **One long-lived browser + `new_context()` per page**, closed in a `finally`.
  Leaked contexts are the #1 cause of the gradual RAM climb.
- **Bound concurrency with an `asyncio.Semaphore`** — start at **5–10 concurrent
  renders per browser, ~1 GB RAM budgeted per slot**; scale by measuring, not guessing.
- **Recycle the browser every ~200–500 pages** — Chromium accumulates memory that
  `context.close()` doesn't reclaim.
- **Reap zombies:** in Docker use `--init` (or `tini`); PID 1 otherwise won't reap
  `chrome_crashpad` children → eventual OOM.
- **Block images/media/fonts** via `page.route` (8.4s→1.3s for 10 URLs in one
  benchmark). Do *not* blanket-block stylesheets if any check needs layout.
- **`wait_until="domcontentloaded"`**, never `networkidle` (Playwright marks it
  DISCOURAGED — modern apps never go idle, so it hangs to timeout).
- **Docker:** `--ipc=host` (preferred) or `--disable-dev-shm-usage` (default
  `/dev/shm` is 64 MB → silent Chromium crashes); use the official
  `mcr.microsoft.com/playwright/python` image so browser libs match.

### 1.3 Driving async Playwright from the thread-based runner
The runner spawns a plain worker thread with **no** event loop, which is the easy
case. **Use `asyncio.run(crawl_domain(...))` inside that worker thread** — it
creates a fresh loop, runs the async crawler, tears down. Critical rules:
- **Launch *and* close the browser inside the same coroutine/loop** — never share a
  browser object across loops (the documented cause of a hang-forever bug,
  playwright-python #2444).
- **Never** call `asyncio.run()` or the Playwright **sync** API from the uvicorn
  request coroutine (that thread already has a running loop → raises). Always in the
  worker thread.
- Instantiate Playwright per thread; don't reuse one global object across threads.
- Graduate to a **dedicated long-lived event-loop thread** + `run_coroutine_threadsafe`
  only if per-job browser relaunch becomes the bottleneck (keeps one browser warm).

### 1.4 Page-priority selection from the sitemap
Use **`advertools.sitemap_to_df()`** — it transparently recurses sitemap *index*
files and handles gzipped sitemaps, returning `loc` + `lastmod`. (Trafilatura's
`sitemaps.sitemap_search()` is a lighter built-in alternative.) Then score URLs by
path pattern and cap hard:

```python
CATEGORY_PATTERNS = {
    "pricing":    (r"/pricing|/plans?|/cost", 10),
    "comparison": (r"/(vs|versus|compare|alternative)", 9),
    "product":    (r"/product|/features?|/solutions?|/platform", 8),
    "docs":       (r"/docs?|/documentation|/guide|/api", 6),
    "blog":       (r"/blog|/articles?|/resources|/news", 4),
}
```
Homepage always included; per-category caps (pricing/comparison ≤ 3, docs/blog ≤ 5
newest by `lastmod`); **global cap ~15–25 pages/domain**; prefer shallow paths; drop
pagination/`/tag/`/`/author/`/locale dupes. No sitemap → parse homepage nav links
and apply the same scorer.

### 1.5 Politeness & robustness
Per-host `Semaphore(1–2)` (near-serial per host — you only pull ~15–25 pages, so
this costs little and avoids rate-limit trips). Honor `Crawl-delay` (use **Protego**,
which supports it; stdlib `robotparser` ignores it — and per the plan's §9.3,
Protego is also the correct *matcher*). Retry with **tenacity** exponential backoff,
but **respect `Retry-After`** on 429/503 instead of blind backoff. Distinct httpx
connect/read timeouts. On a Cloudflare challenge (`cf-mitigated` header / `Server:
cloudflare` + challenge body), **record the page as "blocked" and move on** — don't
try to bypass it (off-mission, brittle).

### 1.6 Cache design
Key by `(normalized_url, crawl_id)`; normalize URLs (lowercase host, strip
fragments + tracking params, trailing-slash policy) and store a `content_sha256`
for dedup/change-detection. Per page store: raw bytes (pre-parse) + status +
headers; rendered DOM via `page.content()` **only if escalated** (+ `was_rendered`
flag); trafilatura `extracted_text`; `json_ld`; `fetch_meta`. **Tiering:** small
queryable artifacts (extracted_text, json_ld→`jsonb`, fetch_meta) in
Postgres/Supabase; **large HTML blobs gzipped in Supabase Storage** (object store),
not Postgres rows (bytea bloats the table/vacuum) — store a `storage_path` +
`content_sha256` pointer. Stamp each crawl with `crawl_id` + UTC time + tool
versions; downstream checks read the cache, never the live web (that's what makes
runs reproducible).

### 1.7 trafilatura + extruct usage
```python
text = trafilatura.extract(html, url=url, output_format="json", with_metadata=True,
                           include_comments=False, include_tables=True,
                           favor_recall=True)   # recall > precision for audits
data = extruct.extract(html, base_url=url, uniform=True,
                       syntaxes=["json-ld", "microdata", "opengraph", "rdfa"])
```
Use **`favor_recall=True`** (missing a pricing table is worse than including some
boilerplate). Use **extruct, not trafilatura, for the authoritative JSON-LD graph**
(trafilatura's metadata is article-centric). Run extruct on the **rendered** HTML
when you escalated (some sites inject JSON-LD via JS). Call
`trafilatura.meta.reset_caches()` between domains (it leaks in long-running procs).

**Sources:** [Vercel/MERJ AI-crawler study](https://vercel.com/blog/the-rise-of-the-ai-crawler) ·
[ZenRows Playwright contexts](https://www.zenrows.com/blog/playwright-browsercontext) ·
[playwright-python #2444 (threading hang)](https://github.com/microsoft/playwright-python/issues/2444) ·
[Playwright resource blocking — ScrapingBee](https://www.scrapingbee.com/webscraping-questions/playwright/how-to-block-resources-in-playwright/) ·
[advertools sitemaps](https://advertools.readthedocs.io/en/master/advertools.sitemaps.html) ·
[Trafilatura Python usage](https://trafilatura.readthedocs.io/en/latest/usage-python.html) ·
[Bug0 Playwright in Docker](https://bug0.com/knowledge-base/playwright-docker)

---

## 2. SSR-vs-CSR detection (the highest-value check)

### 2.1 The metric — word-count ratio on extracted text
Extract main text from **both** raw and rendered HTML with trafilatura
(`favor_precision=True` here), then compare **word counts** (not char counts — those
are inflated by inline SVG/CSS-in-JS; not semantic similarity — wrong question):
```python
ratio = effective_raw_words / rendered_words   # effective_raw includes inline payloads (§2.3)
```
Treat trafilatura returning `None` on raw HTML as `raw_words = 0` — that *is* the
CSR signal, not an error.

### 2.2 Thresholds (calibrate, but start here)
| ratio | class | note |
|---|---|---|
| **≥ 0.90** | PASS (SSR/SSG) | crawler sees ~everything |
| **0.10 – 0.90** | PARTIAL | hybrid/hydration/lazy-load; run guards before finalizing |
| **< 0.10 AND empty shell** | FAIL (CSR) | content only in rendered DOM |

**Never emit FAIL from the ratio alone** — confirm with the empty-shell test, and
let the inline-payload credit upgrade borderline pages. (Reference points: SoberAI,
an open-source AI-crawler auditor, uses an 80% retention line; Screaming Frog ships
a `JS Word Count %` column — the industry standardized on word-count delta.)

### 2.3 Credit inline-HTML payloads (the fix naive classifiers miss)
AI crawlers ingest text in the raw byte stream even without running JS. So count
`__NEXT_DATA__`, other `application/json` scripts, JSON-LD `articleBody`/`description`,
and `og:`/meta — otherwise you wrongly FAIL Next.js sites whose content is in
`__NEXT_DATA__`. Walk the JSON and count only **prose-like strings** (`len > 40` and
contains a space) to avoid counting GUIDs/URLs. **Hard case:** RSC streaming pushes
content in later `self.__next_f.push([...])` chunks — ensure httpx reads the *full*
body, regex-fallback those chunks, and flag low-confidence rather than hard-fail.

### 2.4 Empty-shell test (avoid the `id="root"` false positive)
Modern Next.js/Nuxt SSR also use `#__next`/`#root` but **fill** them — so measure the
text *inside* the mount node, using **selectolax** (lexbor, ~5–30× BeautifulSoup):
```python
node = tree.css_first("#__next, #__nuxt, #root, #app, [data-reactroot]")
for n in node.css("script,noscript,template"): n.decompose()  # strip "enable JS" noise
is_empty_shell = len((node.text(deep=True) or "").split()) < 5
```
A *filled* mount node **vetoes** a false CSR call; `mount_found=False` means "no
known shell — defer to the ratio." Use this as a confirmer/vetoer, never the sole
classifier.

### 2.5 Render waiting & false-positive traps
`domcontentloaded` + a **content-stabilization poll** (loop until
`document.body.innerText.length` stops growing, ~5 s cap, 20 s hard nav timeout); on
timeout, capture what rendered and mark low-confidence. **Do not auto-scroll** — it
inflates `rendered_words` and makes good SSR sites look CSR. Keep JS *on* for the
rendered pass (you already have true raw via httpx). **Fetch raw HTML with GPTBot's
real UA** so you measure what GPTBot sees (and can flag cloaking by double-fetching
with a Chrome UA and comparing). Consent/auth walls → mark **UNGRADEABLE**, not
pass/fail.

### 2.6 Calibration
Assemble ~80–150 labeled URLs across SSR / CSR / hybrid, **including deliberate
traps** (≥10 `__NEXT_DATA__`-heavy pages that must *not* FAIL; a few cookie-wall
sites that must be UNGRADEABLE). Metrics: per-class precision/recall + confusion
matrix. **Minimize the false-FAIL cell hardest** — telling a client to rebuild a
working site is the expensive error. Tune cutoffs on an 80% train split; re-run
quarterly (framework rendering defaults drift).

**Sources:** [Vercel/MERJ](https://vercel.com/blog/the-rise-of-the-ai-crawler) ·
[SoberAI (open-source AI-crawler auditor)](https://github.com/nitishagar/sober-ai) ·
[Screaming Frog JS crawl (Word Count %)](https://www.screamingfrog.co.uk/seo-spider/tutorials/crawl-javascript-seo/) ·
[Next.js #87723 (RSC streaming hides JSON-LD)](https://github.com/vercel/next.js/discussions/87723) ·
[selectolax vs lxml benchmark](https://rushter.com/blog/python-fast-html-parser/) ·
[Why teams avoid networkidle](https://medium.com/@gunashekarr11/why-top-automation-teams-avoid-networkidle-and-what-they-use-instead-c0d1e9439dc4)

---

## 3. Deterministic checkers

### 3.1 Schema / structured data (Cat 5)
**Extract** with extruct, then flatten `@graph` + nested entities with a recursive
walk (emit every node with an `@type`; coerce `@type` to a set since it can be a
list; wrap per-block parsing in try/except so one malformed block doesn't kill the
page). **Validate in-house** — there is **no machine-readable source of Google's
required properties** (schema.org's vocabulary deliberately marks nothing required;
Google's per-feature requirements live only in human-readable docs). So maintain a
**curated, versioned requirements dict** (~15–20 rich-result types):
```python
GOOGLE_REQUIREMENTS = {
  "Product": {"required": {"name","image","offers"},
              "one_of": [{"offers","review","aggregateRating"}],
              "recommended": {"brand","sku","gtin","description"}},
  "Article": {"required": {"headline"}, "recommended": {"image","datePublished","author"}},
  "FAQPage": {"required": {"mainEntity"}},
  "Organization": {"required": {"name","url"}, "recommended": {"logo","sameAs"}},
}
```
**Skip pySHACL** — it's the clearest "ideal is overkill" call in the tool: it needs a
SHACL shape file per type (same maintenance as the dict, in verbose RDF) plus
JSON-LD→RDF conversion, and required-field presence is a one-line `set` check.
Reserve SHACL only if constraints later become genuinely relational. **Schema-vs-
visible-content** (catches fabricated ratings / price drift): normalized substring +
`rapidfuzz` token-set ratio (~85–90) for text fields; regex+`Decimal` for prices;
require rating values to appear in the visible text — and compare against
trafilatura's **main text**, not raw HTML (else the value matches itself inside the
`<script>`).

### 3.2 Link graph / internal linking (Cat 2)
Extract `href`s with selectolax, resolve with `urljoin`, **canonicalize with
`w3lib.canonicalize_url`** (don't hand-roll — percent-encoding/IDN/query-sort is
where bugs hide), classify same-site via `tldextract` eTLD+1. **Boilerplate vs
in-content — use both signals:** DOM ancestry (`<nav>/<header>/<footer>`, role/class
heuristics) as a fast first pass, then **cross-page repetition** (a link on >80–90%
of pages is chrome regardless of markup) as the robust confirmer. Build a
`networkx.DiGraph` of **in-content** links only; **orphans** = sitemap URLs with
`in_degree == 0` (exclude homepage and boilerplate-only inbound). Free high-value
extras: `nx.pagerank` (internal authority) and click-depth from homepage
(`single_source_shortest_path_length`). Anchor-text quality = rule-based (penalize
"click here"/bare-URL/empty; reward descriptive multi-word).

### 3.3 Content primitives (Cat 3/4)
All deterministic. Run **DOM-structural** checks on rendered HTML via selectolax
(headings + question-phrasing regex `^(who|what|when|where|why|how|which|can|do|does|is|are|should)`
or `endswith("?")`; `<ul>/<ol>/<li>` + `<table>` counts/density; `<img>` alt-text
coverage, excluding decorative `alt=""`/1px pixels). Run **text-statistical** checks
on trafilatura text (paragraph-length distribution; fact-density = numeric tokens per
100 words). **Dates:** use **`htmldate`** (by trafilatura's author) for robust
original/updated extraction, plus JSON-LD `dateModified` and a visible
"last updated" regex — and flag divergence between them.

### 3.4 Parser choice
**selectolax (lexbor) as the default hot-path parser** — ~5–30× faster than
BeautifulSoup, ~2× faster than lxml (one case: 150–200 ms → 30–40 ms/page). lxml only
where you need XPath (e.g. ancestor-axis boilerplate tests); BeautifulSoup only as a
narrow fallback for pathologically broken HTML. At audit volume the parser is a real
bottleneck, so don't default to BeautifulSoup "for robustness."

**Sources:** [extruct](https://github.com/scrapinghub/extruct) ·
[schema.org for developers (vocabulary)](https://schema.org/docs/developers.html) ·
[Google structured-data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies) ·
[pySHACL](https://github.com/RDFLib/pySHACL) ·
[w3lib canonicalize_url](https://w3lib.readthedocs.io/en/latest/_modules/w3lib/url.html) ·
[networkx internal-link analysis](https://www.danielherediamejias.com/seo-internal-linking-analysis-with-python-and-networkx/) ·
[htmldate](https://pypi.org/project/htmldate/) ·
[selectolax benchmark](https://rushter.com/blog/python-fast-html-parser/)

---

## 4. LLM-judge layer

### 4.1 Structured output + reasoning-first ordering
Use **`instructor`** wrapping the provider's native structured-output mode (OpenAI
`strict` / Anthropic structured outputs) — you get Pydantic models, automatic
validation + retry (needed for §4.3), and provider portability. **Reasoning-first is
a schema-design problem, not a library one.** Critical gotcha: **Anthropic emits
`required` properties before optional ones regardless of declared order**, so make
**all fields required** and put the label enum **last in the class body**:
```python
class CheckResult(BaseModel):
    reasoning: str        # emitted first → model thinks before deciding
    evidence_quote: str
    label: Verdict        # PASS|PARTIAL|FAIL|UNKNOWN, decided last
    model_config = {"extra": "forbid"}
```
This sidesteps the "JSON-mode degrades reasoning" effect (Tam et al.) — validate it
holds on your own gold set rather than trusting it blindly.

### 4.2 Decompose into atomic yes/no — don't ask for a holistic grade
Research is strong here: ask 3–6 binary `yes/no/unknown` sub-questions per check
(each with its own reasoning + evidence), then map to pass/partial/fail in **Python**
(all-yes→pass, all-no→fail, mixed→partial, any-unknown→unknown). The truth-table is
the rubric's contract — version it with the prompt.

### 4.3 Evidence enforcement (anti-hallucination)
Require a verbatim span and **validate in code that it appears in the source**
(normalize whitespace + case + Unicode NFC); reject and retry (instructor auto-retry,
or manual N=2) then fall back to `unknown`/`needs_review`. Hard substring check is
the safe default; allow `rapidfuzz` partial-ratio > 95 only as a last resort.

### 4.4 Multi-sample only where it pays
**Single pass at temperature 0 by default.** Compute a cheap confidence signal
(`partial` outcome, any `unknown` sub-answer, evidence near the match boundary).
**Only re-sample the ~10–20% borderline/low-confidence items at K=3** (raise temp to
~0.7 *only* for these so samples differ), majority-vote per field,
`agreement_rate < 0.67 → needs_review`. Run the K calls concurrently so latency ≈ one
call. Reserve K=5 / multi-model juries for offline calibration, not production —
K-sampling everything is the expensive-and-wasteful ideal.

### 4.5 Gold-set calibration harness
Start at **~50 examples** (range 30–200), **2–3 annotators each**, check
inter-annotator agreement *first* (if humans disagree, fix the rubric, not the
judge). Score with **quadratic-weighted Cohen's kappa**
(`sklearn.metrics.cohen_kappa_score(..., weights="quadratic")` — partial-vs-fail
should cost less than pass-vs-fail). **Block ship if judge-vs-human κ < 0.6**;
re-run monthly for drift. Iterate: auto-flag every judge≠human disagreement (worst =
high-confidence-wrong), triage rubric-ambiguity vs prompt-bias vs bad-label, hold out
3–5 examples as few-shot (**never** score κ on those — leakage).

### 4.6 Prompt + cost
Stable system prompt (role + atomic rubric + controlled vocab + abstain rule), 2–4
few-shots *after* the rubric *before* the page (include a `partial` and an `unknown`
example). Temp 0 default. **Cost levers:** model tiering (Haiku/4o-mini for clear-cut
checks, Sonnet/4-class for hard judgments + disagreement re-sampling); **verdict
cache** keyed on `hash(model + prompt_version + rubric_version + normalized_page_text
+ check_id)` (mirror the existing `judge.py` cache — bump the key on rubric changes);
**prompt-cache** the static rubric/few-shot prefix (Anthropic `cache_control` ~90%
off reads; OpenAI auto prefix caching — keep the prefix byte-identical, variable page
text last); **batch API** (50% off) for full-site sweeps.

**Sources:** [Tam et al. "Let Me Speak Freely?"](https://arxiv.org/abs/2408.02442) ·
[Anthropic structured outputs (required-first ordering)](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) ·
[instructor](https://python.useinstructor.com/) ·
[Rethinking Atomic Decomposition for LLM Judges](https://arxiv.org/pdf/2603.28005) ·
[Galtea LLM-as-judge rubrics](https://galtea.ai/blog/llm-as-a-judge-prompts-templates-rubrics-and-best-practices) ·
[Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

---

## 5. Offsite research agent (the one agentic part)

### 5.1 Framework — hand-rolled loop, or Pydantic-AI
For a *bounded, auditable* loop, a **hand-rolled tool-calling loop** over the
Anthropic/OpenAI APIs gives the most control (~120 lines): `for step in
range(MAX_STEPS)`, model must finish by calling a terminal `submit_findings(...)`
tool whose JSON Schema *is* your Pydantic findings model; stop on that call or on
budget. **Pydantic-AI** is the strong ergonomic second (`output_type=` enforces the
schema, `all_messages()` is the audit log). **Avoid** LangGraph (overkill for one
loop) and **smolagents** (code-execution = a sandboxing surface you don't want in an
audit tool). **Critical:** no framework's usage limits bound *tool-call count* —
enforce **per-tool quotas in your own dispatcher**.

### 5.2 Budget, audit log, reproducibility
`MAX_STEPS` hard stop (return partial on exhaustion); per-tool quotas
(`{"reddit":3,"serp":5,"wikidata":1,"backlinks":1}`); token cap; `asyncio.timeout`
wall-clock. Log every tool call as JSONL (`step, tool, args, latency, status,
response_hash`). **Reproducibility:** temp 0, pinned model IDs, and **cache tool
results** keyed by `(tool, normalized_args)` (the external data is the main
nondeterminism source). Best of all: run a **deterministic pre-pass** (Wikidata,
DataForSEO summary, SERP presence — no LLM) and hand the agent only the genuinely
open-ended part (which community threads matter). *Full agentic autonomy over every
sub-question is the impractical ideal.*

### 5.3 Concrete tool implementations
- **Reddit:** raw **httpx OAuth2** (`client_credentials`, POST to
  `/api/v1/access_token` with Basic auth), then `GET oauth.reddit.com/search?q=<brand>`.
  Free tier **100 QPM/client_id**, descriptive `User-Agent` **mandatory**; budget for
  Reddit's **2025 app pre-approval**. Prefer httpx over PRAW (PRAW is sync; you don't
  need comment trees).
- **Wikidata:** `wbsearchentities` → `wbgetentities` via httpx (mandatory descriptive
  UA, no key). Resolve = top label match **AND** a discriminating claim (`P856`
  official website matching the audited domain, or `P31` ∈ {business, org, brand}).
  Corroborate with Google KG legacy endpoint (`kgsearch.googleapis.com`).
- **Backlinks:** **DataForSEO `backlinks/summary/live`** (Basic auth, ~$0.02/call,
  $100/mo min) → `referring_domains` + `rank`. One call, headline numbers. Ahrefs/
  Semrush APIs are enterprise-priced alternatives only.
- **Reviews:** **SERP-based presence detection** is lowest-risk — query
  `site:trustpilot.com|g2.com|apps.apple.com "<brand>"` and read the rich-snippet
  `aggregateRating`. Don't scrape G2/Trustpilot directly (ToS). Official review APIs
  are own-app-only.
- **Search:** **Serper.dev** ($1/1k, Google data + rich snippets) as the agent's
  search tool; Brave Search API for legal certainty/Google-independence. Avoid SerpApi
  (cost + Dec-2025 Google lawsuit) and Bing (deprecated).

**Sources:** [Pydantic-AI](https://github.com/pydantic/pydantic-ai) ·
[Pydantic-AI #2593 (limits don't bound tool calls)](https://github.com/pydantic/pydantic-ai/issues/2593) ·
[Reddit API guide](https://apidog.com/blog/reddit-api-guide/) ·
[Wikidata API](https://www.mediawiki.org/wiki/Wikibase/API/en) ·
[DataForSEO backlinks summary](https://docs.dataforseo.com/v3/backlinks-summary-live/) ·
[SERP API comparison (Serper/Brave/SerpApi)](https://scrapfly.io/blog/posts/google-serp-api-and-alternatives)

---

## 6. Runner integration & orchestration

### 6.1 Async crawl from the threaded runner
`asyncio.run(_site_audit_async(...))` inside the audit worker thread (the thread has
no loop — the safe case). Never call it from the uvicorn request coroutine. Treat
shared run-status as cross-thread state (lock or per-phase keys).

### 6.2 Playwright + uvicorn pitfalls
`reload=False` (the reloader breaks Playwright's subprocess/signal handling — the most
common fix); on Windows set `WindowsProactorEventLoopPolicy`; launch flags
`--disable-dev-shm-usage --no-sandbox`; bound concurrency; close in `finally`. The
honest verdict: **the browser is the one component that most wants its own process
boundary** (Chromium's unbounded memory + zombies + subprocess fragility sitting in
the same process as your status API is the documented production risk).

### 6.3 Concurrent phases, best-effort
Submit the engine fan-out and the site audit to a `ThreadPoolExecutor(max_workers=2)`,
join with **`wait([...])`** (not `as_completed` with an early raise), and pull each
result through a `_safe_result` wrapper that swallows per-phase exceptions — exactly
mirroring the existing best-effort judge phase, so a crawl failure never kills the
engine phase or the run.

### 6.4 Progress, persistence, report merge
- **Progress:** add an **additive** namespace (`phases.site_audit: {done, total,
  state}`); keep the existing `progress` semantics unchanged so old status consumers
  don't break; lock the shared status dict.
- **Persistence:** child tables keyed on `run_id` — `site_audit_phase` (resumability
  anchor), `site_audit_check` (`unique(run_id, check_key, page_url)` for idempotent
  re-runs), `site_audit_page`, `site_audit_offsite_finding`; `jsonb` for variable
  payloads. Postgres-as-source-of-truth means a restart resumes by skipping completed
  `check_key`s.
- **Report merge:** in `build_report`, union the existing answer report with whatever
  site-audit rows exist; render even if the audit is `partial`/`absent` (best-effort,
  read from DB so a retried/late audit is picked up next build).

### 6.5 Mitigating the browser-memory caveat — staged
The risk (Chromium destabilizing the API process) is **real but bounded** at our scale
(~15–25 pages/audit, low concurrency) — it is *not* fundamental. A long-lived context
that navigates thousands of URLs is what leaks; a short, discrete per-audit crawl is
not. Two reframes from the research drive everything below:

- **The single highest-leverage fix is recycling the browser per audit job + a hard
  container memory limit.** A browser launched at job start and `close()`d in `finally`
  at job end means Chromium's memory creep can never survive across jobs; a cgroup/
  container memory cap means an OOM is scoped to the container and the kernel kills
  Chromium, not the host. Together these convert the worst case from "OOM corrupts the
  API and run-status" into "one audit fails and retries."
- **It's not in-process-vs-out-of-process as a binary.** There's a ladder; pick the rung
  that matches current load and climb only when load pulls you.

**Layer 0 — In-process hardening (do this regardless, even under a subprocess).**
Browser recycled per audit job; context-per-page closed in `finally`; bounded
concurrency (`asyncio.Semaphore` 2–3); block images/media/fonts (fine — we audit the
client's *own* site); capped viewport + lean launch args; **per-render nav + wall-clock
timeouts** (Playwright can *hang*, not just crash, on OOM — a hung `goto` is how a small
job becomes unbounded). Budget **~700 MB–1 GB resident per browser**; at concurrency 2
size the container **3–4 GB**. Skip the theater: `--single-process`/`--no-zygote` trade
away crash isolation for little gain, and `gc.collect()` won't touch a C++-side leak.

**Layer 1 — Container/OS guardrails (where "safe enough" is actually won).**
Hard `--memory` limit (cgroup OOM-killer scopes the kill to the container); `/dev/shm`
fix via **`--ipc=host`** (Playwright's recommended) or `--shm-size=2g` (not the weaker
`--disable-dev-shm-usage`); **`--init`/tini** to reap zombie `chrome_crashpad` children;
run non-root + seccomp; `--restart=on-failure`. Note: `oom_score_adj` is largely ignored
under a cgroup limit, so the robust pattern is **don't co-locate** the browser with the
API in the same cgroup — which is exactly Layer 2.

**Layer 2 — Subprocess per crawl (THE RECOMMENDATION for now).** Run the crawl phase in
a separate OS process — `multiprocessing` with **`spawn`/`forkserver`** (never `fork`;
forking a process that already has threads/an event loop deadlocks), or a
`subprocess.run([sys.executable, "crawl.py", run_id, domain])`. The child runs
`asyncio.run(crawl(...))`, **writes artifacts straight to Supabase keyed by `run_id`**
(not pickled back over a pipe — pass references, not payloads), and exits. On exit the OS
reclaims 100% of Chromium's memory including the high-watermark, and a browser crash/OOM
of the child leaves the API untouched (you just see a non-zero exit code). This is
**~80% of the benefit for ~20% of the work** vs a queue/microservice: zero new infra
(no broker, no worker fleet, no second service), and it drops cleanly behind the single
`run_site_audit_blocking(run_id, domain)` call §6.1 already defines. Add a `psutil` RSS
watchdog + a liveness probe as backstops (the probe catches *hangs* that a memory check
misses) — but if the watchdog fires routinely, your per-job recycling is misconfigured.

**Layer 3 — Job-queue worker pool (only when crawls become continuous).** A Redis-backed
worker tier (**RQ** simplest for a 2-person team; **Dramatiq** if you want more headroom;
**Celery** is the only one with built-in `worker_max_memory_per_child`/
`worker_max_tasks_per_child` recycling but the heaviest to operate). Worker recycling
bounds memory creep automatically. Key point: process-recycling (`max-requests`,
`max_tasks_per_child`) is the *wrong* tool while the crawl shares the API process —
recycling would kill the API — so it only becomes clean once the crawl lives in a
separate worker. Adopt when volume forces it, not before.

**Layer 4 — Hosted / self-hosted-isolated browser (mostly later, with one caveat now).**
A separate **self-hosted browser container** (Steel — open-source, cleanest license; or
Browserless — has audit-handy Lighthouse/PDF endpoints but an ambiguous SSPL license)
that the runner connects to over CDP (`connect_over_cdp`) gives the strongest isolation
*and* keeps client data on your infra. Fully **hosted** services (Browserbase/Browserless
cloud/Steel cloud) are worth it only when you hit anti-bot/Cloudflare walls or need real
parallel concurrency — and watch the metering (per browser-minute/unit/GB balloons on
slow sites; proxies/captcha billed separately). **Plain AWS Lambda is a poor fit**
(cold starts + 15-min cap + size limits fight a multi-page crawl); use **Fargate** if you
go AWS-native.

> **Data-perimeter flag (matters because you're an *agency*).** Routing a client's
> domain/content through a *third-party hosted* browser makes that vendor a GDPR
> sub-processor — you'd need a signed DPA and client disclosure, and it's a real
> compliance surface, especially if an audit ever logs into a client system.
> **Self-hosting the browser (Layer 2's subprocess, or Layer 4's self-hosted container)
> avoids this entirely** — client content never leaves your perimeter. This is the
> single strongest reason to prefer self-hosted over any hosted service.

**Recommendation:** ship **Layer 0 + Layer 1 + Layer 2 (subprocess-per-crawl writing to
Supabase by `run_id`)**. That gives crash isolation and automatic memory reclamation with
no new infrastructure, fits the existing thread-based runner, and sidesteps the data-
perimeter issue. Design the crawl as a self-contained callable now so the later lift to a
queue worker (Layer 3) is trivial. The most conservative v1 remains running the crawl as
a **sequential pre-step** before the engine fan-out — combine that with subprocess
isolation and the API is never in the browser's blast radius.

> **Locked decisions (don't relitigate at build time):**
> 1. **Anti-patterns — do NOT use:** `gc.collect()` as a leak fix (the leak is C++-side,
>    so it does nothing), and `--single-process` / `--no-zygote` launch flags (they trade
>    away Chromium's crash isolation for negligible memory gain). The real levers are
>    per-job browser recycling + a container memory cap.
> 2. **Every render MUST have a per-render nav + wall-clock timeout, AND the run needs a
>    liveness probe** — not just a memory watchdog. Playwright can *hang* (not only crash)
>    on OOM, and a memory check never catches a hang; a hung `goto` is the main way a
>    bounded job turns unbounded.
> 3. **Self-hosted browser only — no third-party *hosted* browser for client crawls.**
>    Routing a client's site through Browserbase/Browserless-cloud/etc. makes that vendor
>    a GDPR sub-processor (DPA + client disclosure required). Subprocess-per-crawl (Layer
>    2) and a self-hosted container (Layer 4) both keep client content inside our
>    perimeter. Revisit only with an explicit DPA + client sign-off.

**Sources:** [Playwright Docker docs (--init, --ipc=host, non-root)](https://playwright.dev/python/docs/docker) ·
[Playwright #17602 (recycle context for long jobs — maintainer)](https://github.com/microsoft/playwright/issues/17602) ·
[Playwright-python #1847 (hangs on OOM)](https://github.com/microsoft/playwright-python/issues/1847) ·
[Playwright in Production post-mortem](https://medium.com/@onurmaciit/8gb-was-a-lie-playwright-in-production-c2bdbe4429d6) ·
[Celery worker recycling (max_memory_per_child)](https://docs.celeryq.dev/en/stable/userguide/optimizing.html) ·
[multiprocessing in FastAPI (spawn/forkserver)](https://miketarpey.medium.com/troubleshooting-usage-of-pythons-multiprocessing-module-in-a-fastapi-app-f1c368673686) ·
[Python task queues compared (RQ/Dramatiq/Celery)](https://devproportal.com/languages/python/python-background-tasks-celery-rq-dramatiq-comparison-2025/) ·
[Steel (open-source self-hostable browser)](https://github.com/steel-dev/steel-browser) ·
[GDPR third-party data processors](https://www.dqmgrc.com/blog/guide-to-gdpr-and-third-party-data-processors)

---

## 7. MCP servers worth connecting

**The key distinction — and a caveat.** MCP servers are an *agent-interaction*
protocol. They shine in two places for this project: (a) **dev/ops time**, helping
us build, deploy, and debug the tool faster, and (b) the **one genuinely agentic
component** — the offsite research agent (§5) — where an MCP toolset is a natural
fit. They are **not** the right layer for the deterministic hot path: the crawler,
the deterministic checkers, and the high-volume judge should call libraries/REST
APIs directly (httpx, the Playwright *library*, DataForSEO REST), because the batch
pipeline runs hundreds of calls per cycle and needs reproducibility, throughput, and
version control that an MCP indirection layer works against. So: connect MCPs to
*accelerate building and operating* the tool, and optionally to *power the research
agent* — don't bake them into the deterministic pipeline.

Connection status below is from the live registry in this workspace
(✅ already connected · ⬇️ available to connect · 🌐 exists in the wider MCP
ecosystem — verify before relying).

### 7.1 Dev / ops-time (highest value, lowest risk)
- **Supabase MCP ✅ (already connected).** The repo already uses Supabase. Use it to
  apply the new `site_audit_*` migrations (§6.4), inspect tables, run ad-hoc SQL while
  building, and check advisors — exactly the schema work this build needs. Lets us
  iterate the data model conversationally instead of hand-writing every migration.
- **Vercel MCP ✅ (already connected).** `fort.cx` and the `web/` Next.js frontend
  fit Vercel. Use it to deploy the audit/teaser hosted pages, pull build + runtime
  logs, and debug deploys. (Also relevant to the teaser pipeline's "hosted page" output.)
- **GitHub MCP 🌐 (official, verify).** Manage the repo, PRs, issues, and CI from the
  agent — useful for the multi-phase build itself. Not in this workspace's registry
  results; install from the official MCP list.
- **Playwright MCP 🌐 (official Microsoft `@playwright/mcp`, verify).** A *driving*
  tool, not the production crawler. Invaluable for **interactively debugging a crawl**
  — open a stubborn client site, watch what renders, inspect the DOM/console, and
  calibrate the SSR thresholds (§2) against real pages. Use it to build/validate the
  crawler; ship the Playwright *library* for the actual pipeline.

### 7.2 Offsite-research data sources (can power the §5 agent, or be a build-vs-buy call)
- **Ahrefs MCP ⬇️ (available to connect).** Directly covers two plan needs: **backlinks
  / authority** (the "buy don't build" call in plan §9.4) *and* **Brand Radar** — AI
  responses, cited domains/pages, mention history across AI engines. That overlaps with
  your own runner (Category 7), so it's worth a build-vs-buy look: Ahrefs MCP could be a
  cheap cross-check or even a data source for offsite authority + AI-visibility instead
  of building every offsite tool from scratch.
- **Semrush MCP ⬇️ (available to connect).** `backlink_research`, `siteaudit_research`,
  `keyword_research`, `organic_research`. Overlaps the offsite-authority layer and even
  parts of the on-site technical audit — another build-vs-buy reference point, and a way
  to sanity-check your own checkers against an established tool's output.
- **Tavily MCP ⬇️ (available to connect).** `search` / `extract` / `crawl` / `map` /
  `research` — a clean web-search + extraction toolset for the agent's community /
  listicle / press discovery (§5). A managed alternative to wiring Serper/Brave + a
  scraper yourself for the MVP.
- **Nimble MCP ⬇️ (available to connect).** Real-time web search + structured extraction
  + crawl. Same role as Tavily — an option for the agent's search/extract tool.
- **DataForSEO MCP 🌐 (verify).** The plan picks DataForSEO as the cheapest backlinks
  source (§5.3). An MCP wrapper exists; for the *agent* it could replace the hand-rolled
  REST calls, though the deterministic pre-pass should still call the REST API directly.
- **Firecrawl MCP 🌐 (verify).** Maps to the "hosted scraping escape hatch" (plan §9.1)
  for JS-heavy/anti-bot sites your own Playwright tier fails on. Self-hostable; useful as
  the agent's fallback fetch tool, not the primary crawler.

### 7.2a Cost (connecting an MCP is free — you pay for the service behind it)
The MCP server itself never costs anything to connect; billing is on your own account
with the vendor, not through Claude. Free to start: **Supabase** (free tier),
**Vercel** (Hobby), **GitHub**, **Playwright MCP** (open source), **Firecrawl**
(self-host / free credits). Paid sit behind the *data* MCPs:
- **DataForSEO** — pay-as-you-go, no monthly fee, $50 min deposit; calls ~$0.0006–$0.002
  each (pennies per audit). Cheapest backlink source by far.
- **Tavily** — 1,000 free credits/month, then $0.008/credit (up to $500/mo plans).
  Free at MVP scale.
- **Ahrefs** — needs a paid plan; MCP unlocks from **Lite (~$129/mo)**, full depth
  ~$999+/mo Enterprise.
- **Semrush** — needs Semrush One, **Starter ~$199/mo** and up (50k API units for MCP).

The only real spend decision is the offsite-authority layer: **DataForSEO (pennies,
pay-per-use) vs Ahrefs/Semrush ($129–549/mo subscriptions)** — pay the subscription
premium only for their polished Brand Radar / AI-visibility dashboards, which overlap
your own runner. Prices move; confirm on each vendor's page before committing.

### 7.3 Install the free MCPs (do this before starting the build)
All free, all worth having connected before we write code. Two install paths: **remote**
MCPs connect through the Cowork/Claude Desktop connector directory (Settings →
Connectors → Add); **local (stdio)** MCPs run on your machine via `npx` and are added in
Claude Code (or Claude Desktop's config). Prereqs: **Node.js** (for the `npx` ones) and a
free **Firecrawl API key** from <https://www.firecrawl.dev/app/api-keys>.

| MCP | Type | Install |
|---|---|---|
| **Supabase** | remote | ✅ already connected (Settings → Connectors if you ever need to re-add) |
| **Vercel** | remote | ✅ already connected |
| **GitHub** | remote (http) | `claude mcp add --transport http github https://api.githubcopilot.com/mcp/` then complete OAuth — or in Cowork, Settings → Connectors → add GitHub |
| **Playwright** | local (stdio) | `claude mcp add playwright -- npx @playwright/mcp@latest` |
| **Firecrawl** | local (stdio) | `claude mcp add --env FIRECRAWL_API_KEY=fc-YOUR_KEY firecrawl -- npx -y firecrawl-mcp` |

After adding, run `claude mcp list` to confirm each shows connected. (Quote rule: all
flags like `--transport`/`--env` go **before** the server name; the `--` separates the
name from the launch command for stdio servers.) Sources:
[Playwright MCP](https://github.com/microsoft/playwright-mcp) ·
[GitHub MCP (remote)](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md) ·
[Firecrawl MCP](https://github.com/firecrawl/firecrawl-mcp-server) ·
[Claude Code MCP docs](https://code.claude.com/docs/en/mcp).

### 7.4 Recommended priority (which to actually use first)
Use now: **Supabase** (✅, drive the migrations), **Vercel** (✅, deploy hosted pages),
and **Playwright MCP** (debug/calibrate the crawler). Evaluate **Ahrefs *or* Semrush**
as a build-vs-buy decision for the offsite-authority + backlink layer before building it
from scratch — connecting one for a week of exploration is far cheaper than building the
wrong thing. Defer Tavily/Nimble/Firecrawl-as-a-data-source until the §5 agent is the
active workstream, then pick one search/extract MCP rather than wiring raw APIs for the
MVP. (Firecrawl is in the free-install table above so it's ready when you get there.)

> Strategic note: Ahrefs Brand Radar and Semrush's AI toolkit *already* measure
> AI-answer brand visibility — the same job as your runner (Category 7). That's not a
> reason to abandon the runner (you want control + the per-answer schema), but it is a
> reason to connect one briefly and decide which offsite/measurement pieces are cheaper
> to buy than build.

---

## 8. Pinned dependency set (implied by the above)

`httpx`, `playwright`, `trafilatura` (+ `htmldate`), `extruct`, `selectolax`,
`protego`, `advertools` (or trafilatura sitemaps), `w3lib`, `tldextract`,
`networkx`, `tenacity`, `rapidfuzz`, `instructor` (+ OpenAI/Anthropic SDKs),
`pydantic`, `scikit-learn` (calibration kappa). Optional/under-load: `hishel` or
`diskcache` (tool-result cache), Browserless (hosted browser).

---

## 9. Build-out backlog (gaps found auditing the shipped pipeline vs. the transcript recipes)

A fidelity audit against the 27 curl-recipe comments found places where a check dropped
a step the recipe specifies, or measured a *generic* client view instead of the *GPTBot*
view the recipe assumes. **All P1–P3 items below are now CLOSED** (post-`fb3e7a2`
follow-up); each is annotated with what shipped and where. Priority: **P1** =
correctness/fidelity, **P2** = completeness, **P3** = enhancement.

### Cat 1 — Technical accessibility (`src/audit/technical_check.py`)
- **[P1] ✅ Robots matcher → Protego.** `urllib.robotparser` removed; `check_robots_txt`
  now uses `Protego.parse(...).can_fetch(url, ua)` (RFC 9309-compliant). The crawler
  also gained `crawl/robots.py` (honors Disallow + Crawl-delay). (Plan §9.3.)
- **[P1] ✅ llms.txt Content-Type check.** `check_llms_txt` fetches as GPTBot; a
  `200 + text/html` (or HTML body) app-shell response now scores **fail/absent**, only
  `text/plain`/markdown passes.
- **[P1] ✅ Gated content real recipe.** `check_gated_content` walks homepage + priority
  pages (via `page_select`) **as GPTBot** and flags 401/403, a redirect that lands on
  `/login|/signup|/auth|/subscribe`, or a thin login/paywall stub. Gated homepage → fail.
- **[P1] ✅ WAF challenge body at 200.** `check_crawler_access` flags a Cloudflare
  "Just a moment…" challenge served at 200 (new `_is_challenge`), and **OAI-SearchBot**
  is in the `AI_CRAWLER_UAS` probe.
- **[P2] ✅ Sitemap Content-Type + `<loc>` count.** `check_sitemap` catches the HTML
  app-shell trap and reports the `<loc>` count (and flags an empty sitemap).
- **[P2] ✅ UA fidelity.** `check_rendering`/`check_sitemap`/`check_llms_txt`/
  `check_gated_content` all fetch with the GPTBot UA now.

### Cat 5 — Schema (`src/audit/checks/schema.py`)
- **[P2] ✅ features→types "should-have" inference.** `_should_have_types` infers expected
  types from page category + content (pricing → `Product`/`Offer`, FAQ → `FAQPage`,
  about/team → `Person`, blog → `Article`); a missing expected type downgrades to PARTIAL
  and is listed in `evidence.missing_expected_types`.
- **[P2] ✅ sameAs analysis.** `_sameas_analysis` extracts entity `sameAs` links and
  classifies them by identity platform (`evidence.same_as`). *Offline* (extraction +
  platform classification); live HEAD-resolution to confirm each profile is brand-owned
  is intentionally left to the offsite layer to keep the deterministic checker network-free.

### Cat 2 — Internal linking (`src/audit/checks/links.py`) — P3 ✅
- `analyze_link_graph` accepts the full discovered sitemap (now captured on
  `CrawlResult.sitemap_urls`) and reports `sitemap_size` / `sitemap_linked_in_content` /
  `sitemap_not_internally_linked` (evidence, not a hard fail — a capped crawl can't see
  links from uncrawled pages). Explicit pillar→cluster judgment remains implicit in
  PageRank/click-depth (intentional).

### Cat 6 — Offsite / on-site comparison — P3 ✅
- **Per-competitor comparison coverage.** New site-level `comparison_coverage` check in
  `site_audit.py` (`_run_comparison_coverage`): competitors are threaded from the runner,
  and each is matched against crawled pages for "X vs {competitor}" / alternatives
  content; a missing one is a named gap that flows into the roadmap.

### Not gaps (verified — don't "fix" these)
- **Cat 3/4 content judge** (`content_judge.py`) is built but intentionally **gated**
  until the page gold set hits κ ≥ 0.6 (plan §7). Wiring it live before calibration is
  the wrong move, not a gap.
- **Cat 4 last-updated date** is implemented in `content_primitives.py` (htmldate +
  JSON-LD `dateModified` + visible regex) — already faithful to Comment 26.
- **SSR** (`ssr.py`) deliberately uses a raw-vs-rendered word-count ratio instead of
  Comment 3's grep-a-phrase — an intentional upgrade (§2), not a regression.

---

_This guide is the implementation layer under `site-audit-agent-plan.md` §5. Each
section's "ideal vs. practical" calls are the parts most likely to bite if skipped —
they are deliberately called out rather than buried._
