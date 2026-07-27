# SMB pivot — executable build plan

Status: ready to build (2026-07-27). Companion to **`smb-pivot-plan.md`**, which holds the
market research and the strategic case. That document is the *why*; this one is the *what*,
scoped so an agent can execute it work-item by work-item without further design decisions.

Baseline verified against commit `907d447`. Every file path and line reference below was
checked against working-tree code, not against the plan. Where something is inferred rather
than verified it is marked **[verify]**.

---

## 0. Read this before starting

### 0.1 The validation gate is non-negotiable

Python: `mypy src/ && ruff check src/ && pytest tests/`
Teaser: `cd teaser && npm run typecheck && npm test`

Every work item ships green. No work item is "done" until its own tests exist and pass.

### 0.2 Hard invariants this plan must not break

From `CLAUDE.md`. An agent that violates any of these has failed the item regardless of
whether tests pass:

- **Engines return `None` on error, never raise.** All engines subclass `BaseEngine`. The
  pipeline never crashes because one engine failed.
- **Judge cache keys are sacred.** Any change to judge prompts, tool schema, or prompt layout
  bumps `_PROMPT_LAYOUT` in `src/pipeline/judge.py`, keeps HEAD/RUBRIC split parity with
  `scripts/judge_via_workflow.py`, and invalidates every cached verdict. Parity tests in
  `tests/test_judge.py` guard this. **Never weaken them.**
- **Core-data writes go through `src/storage/db.py`.** Storage is create-only.
- **Secrets only via `src/config/settings.py`.** `os.getenv` nowhere else.
- Type hints on all signatures, `from __future__ import annotations`, no swallowed
  exceptions, no `# type: ignore` without a same-line reason.
- `docs/build-log.md` is append-only, most recent first, one entry per completed phase.

### 0.3 Three things the strategy doc gets wrong

**Correction 1 — the resolver does not hard-fail on non-consumer categories.**
`smb-pivot-plan.md §2` item 4 says the teaser profile resolver "hard-fails otherwise" on
non-consumer-product categories. It does not. The only hard failure
(`teaser/src/resolver/profileExtraction.ts:188`) triggers on a **blank** category or the
literal string `"product"`. A category like `"plumbing service"` passes.

Consequence: pointing the teaser at a local business today does not error. It emits a
confident, plausible, **wrong** teaser — the resolver prompt
(`profileExtraction.ts:120-121`) asks Claude for "2-5 REAL, CURRENTLY-OPERATING rival
brands... use real, well-known names", which for a local trade yields national franchises
or invented locals rather than the businesses across town. For a cold-outreach artifact,
silent-and-wrong is materially worse than crashing. **W0.1 exists to close this first.**

**Correction 2 — engines and run count are already CLI flags.**
`teaser/src/cli.ts:83-85` implements `--engines <csv>`; `--runs <n>` also exists (default 3).
The `smb-pivot-plan.md` framing implies a code change. It is a flag. See W0.2.

**Correction 3 — intent does NOT reach the judge prompt or the judge cache key.**
W2.1 previously carried an open ⚠️ asking whether adding intent buckets would force the work
into the cache-invalidating phase. **Resolved: it does not.** Verified at `907d447`:

- The cache key (`_single_fingerprint`, `judge.py:282-296`) hashes exactly
  `_SYSTEM + _BASE_INSTRUCTIONS + _ACCURACY_BLOCK + _NO_ACCURACY_BLOCK + _PROMPT_LAYOUT +
  json.dumps(tool)`. Intent is not a term.
- The single occurrence of intent in `judge.py` is `:923`, copying `r["intent"]` onto the
  output `AnswerJudgment` record after judging. It never enters a prompt.

**Consequence:** adding local intent buckets is cache-safe and **stays in Phase 2**. Phase 3
remains a single coordinated `_PROMPT_LAYOUT` bump. Re-verify this grep before building W2.1;
if intent ever becomes a prompt input, this conclusion dies with it.

### 0.4 Verified baseline — what exists today

| Capability | State | Evidence |
|---|---|---|
| Any geographic primitive | **None repo-wide.** `grep -rlniE "service_area\|serviceArea\|\bcity\b\|local_intent\|geo_scope" src/ teaser/src/ data/` returns no files | verified |
| Location on profile | No field | `teaser/src/types/domain.ts` `CompanyProfile` |
| Resolver category prompt | Consumer-product coded | `profileExtraction.ts:120-121` |
| Competitor validation | Product-category only, no geography | `relationshipCheck.ts:89-91` |
| Query-gen fallbacks | "for a growing startup", "scales with my needs" | `ClaudeQuerySetGenerator.ts:295,300`; `MockQuerySetGenerator.ts:38,59` |
| AI Overviews location | Sends `{"engine":"google","q":prompt}` only. `query()` takes `prompt` alone | `src/engines/ai_overviews_engine.py:62,66` |
| Review platforms | `trustpilot.com, apps.apple.com, play.google.com` | `src/audit/offsite/tools.py:49-53` |
| Teaser default engines | `["perplexity","openai_search","gemini_grounded"]`, `runsPerQuery: 3` | `teaser/src/pipeline.ts:65,71` |
| Intent → judge cache key | **Not a term.** Key = system+instructions+accuracy blocks+layout+tool schema | `judge.py:282-296`; only use is `:923` (record field) |
| `BUCKET_ALLOCATION` | Exported, **never consumed** in `src/`, `tests/`, `scripts/` — a documented sanity constant only | `intent.py:25`; grep returns only `__init__.py` re-export |
| `bucket_counts()` | Same — only caller is `query_set.py:107` inside its own `__main__` block | `query_set.py:94` |
| Teaser bucket selection | **Hardcoded** `(CATEGORY, COMPARISON)`; filters the query set at `:174` | `src/pipeline/orchestrator.py:32,174` |
| `build_template_csv()` | **User-facing** — served as a download at `GET /api/template.csv` | `src/api/app.py:223`; `csv_loader.py:461` |

### 0.5 Re-verify before you build

Every claim above was true at `907d447`. This repo moves fast and two items in this plan's
research phase turned out to be already-fixed when checked (`accessProbeUnreliable`,
`llms_txt` note-only). **Before starting each phase, re-run that phase's greps.** If reality
disagrees with this document, reality wins — update the plan in the same commit.

### 0.6 The additive rule — this pivot ADDS an ICP, it does not swap one

**Both ICPs stay live and shipping.** The consumer-product path is not legacy, is not being
migrated away from, and is not allowed to degrade. This is the governing constraint of the
whole plan, and it is stronger than "don't delete the consumer code" — it is a rule about
*how* every shared symbol gets touched.

**The spine: one `business_kind` selector.**

W0.1 builds a classifier producing `businessKind: "product" | "local_service"`. That value is
**the single selector for every divergence in this plan.** W2.4 flips it from a throw to a
route. Every item below that says "for local" means "selected on `business_kind`," never
"changed globally."

Thread it as far as it needs to go: it is not only a teaser-resolver concern. It must reach
the query-set layer, discovery, the offsite platform list, and the audit CSV contract.

**Fork, don't edit in place.**

> **RULE.** A shared constant, prompt, or default that the consumer path reads is **forked
> into a kind-keyed pair**, never rewritten. If you find yourself editing the body of a
> string the consumer path also uses, stop — that is a failed work item, even if tests pass.

Concretely, the shared symbols this plan touches and how each must be handled:

| Shared symbol | Location | Plan originally said | Correct treatment |
|---|---|---|---|
| `_TEASER_BUCKETS` | `orchestrator.py:32` | (unaddressed) | Fork by kind — see W2.1 |
| `build_template_csv()` | `csv_loader.py:461` | "replace the Oura starter" | Parameterize — see W2.2 |
| Query-gen fallbacks | `ClaudeQuerySetGenerator.ts:295,300` | "delete" | Kind-select — see W2.3 |
| `_EXTRACT_PROMPT` | `discovery.py:14` | "reprompt for local" | Fork by kind — see W2.7 |
| `REVIEW_PLATFORMS` | `offsite/tools.py:49` | "keep both, select by kind" ✅ | Already correct |
| `_PROMPT_LAYOUT` + accuracy block | `judge.py:219` | local flags added | **Unavoidably global** — see W3.4 |

Only the last row is genuinely global. Everything else is fork-able, and where the plan said
otherwise the plan was wrong.

**The one unavoidable cost to the existing path** is the Phase 3 judge change. It invalidates
consumer cached verdicts (cheap — prejudge re-warms free) *and* means the shipped judge is no
longer byte-identical to the one the consumer calibration figures were measured on. That is a
real bill against the consumer ICP and W3.4 now budgets it explicitly.

---

## Phase 0 — Stop-ship guard and free config

Small, immediate, no dependencies. Do this even if the rest of the pivot is deferred.

### W0.1 — Refuse local businesses until the local path exists

**Problem:** §0.3 Correction 1. The teaser silently produces a wrong artifact for a local
business.

**Files:** `teaser/src/resolver/profileExtraction.ts`

**Change:** extend the existing post-extraction validation (currently at ~`:182-193`) with a
service-area-business check. Add a `businessKind: "product" | "local_service"` field to the
Claude extraction schema (`:70-110`) and prompt, then:

- `local_service` + no local support compiled in → throw with a message naming the reason,
  in the same style as the existing blank-category throw.
- Keep the existing blank/`"product"` guard unchanged.

**Why a throw and not a fallback:** the teaser CLI already refuses to run on mock adapters by
default "so a sent teaser is never fabricated" (`cli.ts` header). Same principle.

**Forward compatibility:** this classifier becomes the **router** in W2.4 — `local_service`
stops throwing and selects the local resolver path instead. Build it as a classifier that
currently throws, not as a bespoke rejection.

**Acceptance:**
- A local-service fixture URL throws with an actionable message
- A consumer-product fixture still resolves unchanged
- `npm run typecheck && npm test` green

**Tests:** `teaser/tests/resolver.test.ts` — one case per branch. Pure, no network.

### W0.2 — Point a run at AI Overviews (config only, no code)

No code change. Document in the build-log entry that the flagship surface is reachable today:

```bash
npm run teaser -- <url> --engines google_ai_overviews,openai_search,perplexity --runs 5
```

**Caveat that must be recorded:** until W1.3 lands, `google_ai_overviews` runs every query
from SearchApi's unpinned default locale. Useful for consumer prospects; **not valid for any
local query.** Do not ship a local teaser on this flag alone.

### W0.3 — Fix stale docs

`teaser/README.md` states default engines are `perplexity`, `google_ai_overviews`, `openai`.
Actual defaults are `perplexity`, `openai_search`, `gemini_grounded` (`pipeline.ts:65`).
It also calls `src/render/pdf.ts` a "documented stub" while `out/*.pdf` exist. **[verify]**
both, correct both.

### W0.4 — Consumer-path regression lock (build this BEFORE Phase 1)

**Problem:** this plan declares a consumer-path regression a failed work item but ships no
mechanism that would *detect* one. Every guard listed in §0.2 protects an invariant; none
protects the consumer ICP's behavior. Phases 1–4 touch six shared symbols. Without a lock,
"additive" is an intention, not a property.

**This is the enforcement arm of §0.6 and must land before the first shared symbol is
touched.** It is cheap now and unbuildable later — once local code is interleaved you can no
longer capture a clean consumer baseline.

**Files:** new `tests/test_consumer_path_regression.py`; new
`teaser/tests/consumerPathRegression.test.ts`

**Change:** golden-output tests pinning today's consumer behavior. Pure, no network, no API
spend — fixtures only.

- `build_template_csv()` output pinned byte-for-byte (guards W2.2)
- A consumer query set's selected teaser queries pinned (guards `_TEASER_BUCKETS`, W2.1)
- `_EXTRACT_PROMPT` applied to a fixture response yields today's extracted names (guards W2.7)
- `REVIEW_PLATFORMS` for a product-kind audit is exactly the current three (guards W4.1)
- A consumer-product fixture URL resolves to today's profile, competitors, and copy
  (guards W0.1, W2.3, W2.5, W2.6)
- `_single_fingerprint()` pinned to its current hash, with a comment stating that changing it
  is legitimate **only** in the W3.3 commit and must be updated in the same commit

**Deliberate design:** these tests are *meant* to fail loudly when a shared symbol is edited
in place. A failure is the signal working. The fix is to fork the symbol by `business_kind`
and restore the consumer assertion unchanged — **never** to relax the assertion to accommodate
local behavior. The only assertion in this file that may legitimately change is the
fingerprint pin, in W3.3, deliberately.

**Acceptance:**
- All assertions green at `907d447` before any pivot code lands
- Each of the six shared symbols in the §0.6 table has at least one pinning assertion
- `mypy`/`ruff`/`pytest` green; `npm run typecheck && npm test` green

---

## Phase 1 — Location plumbing

Unblocks everything downstream. Touches no judge prompts, invalidates no caches.

### W1.1 — `location` on the profile

**Files:** `teaser/src/types/domain.ts`

Add to `CompanyProfile`:

```ts
/** Service-area business location. Absent for nationally-marketed products. */
location?: {
  city: string;
  region: string;         // state / province
  country: string;        // ISO-3166 alpha-2
  serviceArea?: string[]; // additional named towns/neighborhoods
};
```

**Optional by design** so every existing consumer-path call site compiles untouched. Mirror
onto `TeaserDraft` for regeneration parity — see the `clientAliases` precedent at
`domain.ts:104-113`, which exists because a regenerated teaser went alias-blind.

**Acceptance:** `npm run typecheck` green with no changes to existing call sites.

### W1.2 — Resolver extracts NAP

**Files:** `teaser/src/resolver/profileExtraction.ts`, `FetchClaudeResolver.ts`,
`Crawl4aiClaudeResolver.ts`

Add `location` to the extraction JSON schema and prompt. Source it from the site's NAP block
(footer, contact page, schema.org `LocalBusiness` if present). Return `undefined` when the
business is not service-area-bound.

**Determinism:** both Claude calls are pinned to `temperature: 0` (`llm/claude.ts`, from the
quality-audit P0 fix). Do not introduce a call that isn't.

**Acceptance:** local fixture yields a populated `location`; product fixture yields
`undefined`; both deterministic across repeat runs.

### W1.3 — AI Overviews engine accepts a location

**Files:** `src/engines/ai_overviews_engine.py`, `tests/test_isolation.py`

Currently `query()` / `query_with_citations()` take `prompt` only and send
`{"engine":"google","q":prompt,"api_key":...}` (`:62,66`). Add an optional location that
maps to SearchApi's location parameter **[verify the exact param name against SearchApi's
current Google-engine docs before implementing — do not guess]**.

**Constraints:**
- Must not raise. `BaseEngine` contract: return `None` on error.
- `record_payload()` must log the location-bearing payload, and the recorded dict should
  *be* the dict sent so log and request cannot drift (the Test E design).
- **`tests/test_isolation.py` has 14 tests capturing every engine's outgoing payload.**
  Adding a field changes AI Overviews' payload and will fail them. Update those assertions
  **deliberately and narrowly** — this guard is the anti-regression net for engine isolation.
  Never loosen a matcher to make it pass.
- Preserve `MODEL_ID` / dated-pin conventions from the isolation work.

**Acceptance:** location-bearing payload asserted in `test_isolation.py`; absent location
produces today's exact payload byte-for-byte; error paths still return `None`.

### W1.4 — Thread location through the audit contract

**Files:** `teaser/src/platform/csv.ts`, `src/prompts/csv_loader.py`, `src/api/runner.py`

`buildAuditCsv` emits a `config` block (`csv.ts:41-49`). Add a `location` config row using
the existing `;` in-cell separator convention. Parse it in `csv_loader.py` into `RunConfig`,
thread to `runner.py` (`:184,228`) and into `build_engines` so the engine receives it.

**Backwards compatibility:** a CSV with no `location` row must parse exactly as today. Add a
regression test asserting that.

**Acceptance:** round-trip test — CSV in, `RunConfig.location` out, engine receives it.
`mypy`/`ruff`/`pytest` green.

### W1.6 — Local-pack entity capture (ADDED 2026-07-27 — W2.4 has no data source without it)

**Why this exists.** W2.4 requires local competitors "seeded from local-pack / directory
entities captured in Phase 1", and is emphatic that LLM recall must never supply them —
Claude does not reliably know the plumbers in a given city, and inventing one is the
unrecoverable failure mode for this product. **But no original Phase 1 item built that
capture.** W1.3 localizes the AI Overviews *request*; it does not persist the entities
W2.4 consumes. Built as specified, W2.4 would be a resolver that always fails loudly.

**Files:** `src/engines/ai_overviews_engine.py`, `src/api/app.py`

**Change:** SearchApi's Google response carries a `local_results` array alongside
`ai_overview` — verified against SearchApi's Google-engine docs (2026-07). Each entry
has `position`, `title`, `address`, `rating`, `reviews`, `type`, `ludocid`, `is_closed`.
Capture it into a typed `LocalEntity` and expose it two ways:

- `AIOverviewsEngine.query_local_entities(prompt)` — same client, same key, same
  never-raise contract as every other engine method.
- A read-only API endpoint so the TypeScript teaser can reach it without a second
  SearchApi credential. `SEARCHAPI_API_KEY` stays in `settings.py` (hard invariant:
  `os.getenv` nowhere else), so the teaser must NOT call SearchApi directly.

**Not part of the audit fan-out.** This is a discrete lookup the *resolver* makes at
profile time ("who are the plumbers in Berkeley?"), not a per-query measurement. Keeping
it off the `BaseEngine.query()` path means no per-run cost change and no state stored on
an engine instance — engine isolation is unaffected.

**Acceptance:** a `local_results`-bearing response yields typed entities; a response with
none yields `[]`; a malformed/error response yields `[]` and never raises; closed
businesses are dropped; the endpoint refuses to run without a location.

### W1.5 — Phase 1 exit criterion

`npm run teaser -- <local-url> --engines google_ai_overviews --runs 5` reaches the platform
with a location and the AI Overviews engine issues a localized request. The teaser output is
still not sendable (queries and competitors are wrong until Phase 2) — that is expected.

---

## Phase 2 — Local query sets and the teaser

The sellable deliverable. Largest phase.

### W2.1 — Local intent buckets

**Files:** `src/prompts/intent.py`, `src/pipeline/orchestrator.py`

The current funnel buckets (`category`/`comparison`/`brand`/`problem_aware`/
`adjacent_authority`) do not map to local, and the surfaces are near-disjoint by intent.
Add, per `smb-pivot-plan.md §3 Phase 2`:

- `local_intent` — "best plumber in Berkeley", "plumber near me" → local pack / AI local pack
- `hybrid` — "average cost of AC replacement in Berkeley" → ~97% AIO
- `informational` — "how often should a furnace be serviced" → ~92% AIO
- keep `brand` — "is X Plumbing legit"

Prefer explicit-city phrasings. Tag "near me" variants as a separate, noisier cohort:
SE Ranking measured them roughly 2× less stable.

**✅ Cache question resolved — see §0.3 Correction 3.** Intent is not a term in the judge
cache key and never enters a prompt. This item is cache-safe and stays in Phase 2. Re-run the
grep before building; if it ever changes, this item moves to Phase 3.

**Adding enum members is safe. The hardcoded selector is not.**

- `IntentBucket` is a `StrEnum`; adding members is backward-compatible. `query_set.py:65-67`
  validates loaded intent strings against the enum, so existing consumer sets keep parsing.
- `BUCKET_ALLOCATION` (`intent.py:25`) and `bucket_counts()` (`query_set.py:94`) are
  **exported but never consumed** outside `query_set.py`'s own `__main__` block. Adding local
  buckets does not break a live consumer. Do not spend effort rebalancing the allocation dict
  to sum to 1.0 — nothing reads it. If you add local entries, add them as a **separate
  kind-keyed profile**, not by mutating the consumer dict.
- **The actual break: `_TEASER_BUCKETS` (`orchestrator.py:32`) is hardcoded to
  `(CATEGORY, COMPARISON)` and filters the query set at `:174`.** A local query set built from
  `local_intent`/`hybrid`/`informational` intersects it in **zero queries** — the local teaser
  would silently produce an empty run rather than error.

**Change:** replace the module constant with a kind-keyed mapping — consumer keeps
`(CATEGORY, COMPARISON)` byte-for-byte; local gets `(LOCAL_INTENT, HYBRID)` **[verify the
local pair against which surfaces actually show a competitor set — the teaser's job is the
"here's who ChatGPT names instead of you" moment, so pick the buckets that produce rival
names, not the informational ones]**. Select on `business_kind` per §0.6.

**Acceptance:** consumer teaser selects exactly today's queries (W0.4 assertion unchanged); a
local set selects a non-empty local bucket set; an empty selection raises rather than running.

### W2.2 — Per-trade query templates

**Files:** new `data/queries_hvac.json`, `data/queries_plumbing.json`,
`data/queries_barbershop.json`; `src/prompts/csv_loader.py` `build_template_csv()`

25–40 queries per trade with `{city}` and `{brand}` slots. The query space genuinely is that
small.

**Do NOT replace the Oura starter template.** The earlier draft of this item said "replace the
Oura starter template in `build_template_csv()`". That is a consumer regression:
`build_template_csv()` is **user-facing**, served as a download at `GET /api/template.csv`
(`src/api/app.py:223`) and pinned by `tests/test_csv_loader.py:199`. Replacing it changes what
every consumer prospect downloads.

**Change:** parameterize instead — `build_template_csv(trade: str | None = None) -> str`. The
no-argument call returns today's Oura CSV **byte-for-byte**; a trade argument returns that
trade's local starter. Add the query-param plumbing at the API endpoint so the local template
is reachable without changing the default response.

**Acceptance:** each file validates against the existing query-set schema; slot substitution
tested; `build_template_csv()` with no argument is byte-identical to today (W0.4 assertion
passes unchanged); `build_template_csv("hvac")` emits the local template;
`GET /api/template.csv` with no query param returns today's bytes.

### W2.3 — Teaser query generation for local

**Files:** `teaser/src/queryset/ClaudeQuerySetGenerator.ts`,
`teaser/src/queryset/MockQuerySetGenerator.ts`

Add local fallback templates keyed on trade + city, **selected on `business_kind`** — do not
replace the existing fallbacks with local-only ones.

**On the "delete the startup fallbacks" instruction.** The strings at
`ClaudeQuerySetGenerator.ts:295,300` and `MockQuerySetGenerator.ts:38,59` — "for a growing
startup", "scales with my needs" — are **B2B-SaaS-era leftovers that are already wrong for the
current consumer ICP**, which is B2C consumer products, not startups. So deleting them costs
the consumer path nothing and is a genuine improvement.

But delete is not the same as replace. Rewriting them into local-only templates leaves the
consumer path with no correct fallback at all. Two options, in preference order:

1. **Preferred:** fix the consumer fallbacks to B2C consumer phrasing *and* add local ones,
   both kind-selected. Small extra effort, leaves both ICPs correct.
2. **Acceptable:** kind-select, leaving the stale consumer strings untouched for now, and file
   the B2C fallback fix as a separate item. Do not silently leave the consumer path pointing
   at local templates.

Either way the consumer branch must still resolve to *something* consumer-shaped.

**Preserve the deterministic repair layer.** `validateAndRepair` enforces the methodology
hard rules and falls back to a template set when LLM output is unusable. Extend its rules for
local (city present in local_intent queries; client named only in the brand query); do not
bypass it.

**Acceptance:** generated local sets contain no startup phrasing; repair path covered by
tests; deterministic across runs.

### W2.4 — Local resolver path

**Files:** `teaser/src/resolver/profileExtraction.ts`

Flip W0.1's classifier from throw to route. On `local_service`: extract trade category, city
and service area; extract competitors as **other local businesses in the same trade and
city**.

**Competitor sourcing is the hard part and must not come from LLM recall.** Claude does not
reliably know the plumbers in a given city, and inventing one is the unrecoverable failure
mode for this product. Seed candidates from local-pack / directory entities captured in
Phase 1. If no captured entities are available, the resolver must **fail loudly**, not guess.

**Acceptance:** local fixture returns trade + location + competitors sourced from captured
entities; missing entities produce a clear failure, never a fabricated rival.

### W2.5 — Geographic dimension in competitor validation

**Files:** `teaser/src/resolver/relationshipCheck.ts`

`CategoryVerdict` (`:36`) is `same_category | different_category | unknown` with no
geography. A Phoenix plumber and a Boston plumber are `same_category` and pass today.

Add a service-area overlap judgment. **Keep the recall-safe posture** documented at `:34` —
only a clear negative drops a competitor; `unknown` is kept and the human confirm gate
catches the rest.

**Must be gated on `business_kind`.** A nationally-marketed consumer product has no service
area; running an overlap judgment on it would drop legitimate competitors on a dimension that
does not apply. The geographic check runs **only** on `local_service`. On `product` the
verdict path is unchanged and the W0.4 consumer-resolution assertion must still pass.

**Acceptance:** same-trade different-metro competitor is dropped with
`categoryMismatch`-style provenance; same-metro rival is kept; unknown is kept; a consumer
product's competitor set is byte-identical to today.

### W2.6 — Local teaser copy

**Files:** `teaser/src/render/copy.ts`, `teaser/src/render/template.ts`

- "buyers" → "customers" / "homeowners"
- **Drop the share-of-voice chart on the local path.** `smb-pivot-plan.md`: *"owners respond
  to named competitors and phone-call economics, not dashboards."*
- Replace with a red/yellow/green checklist of the 8–10 sources AI actually cites for local:
  GBP, Yelp, BBB, Angi, Thumbtack, Facebook, Bing Places, Reddit
- Add dollar framing sourced from `lib/stats.ts`-style constants, never hardcoded

**Preserve every claim-fidelity guard.** `copy.ts` grades its verbs by judge prominence
(`competitorVerb`, `competitorProminenceWord`) and `reproNote` only prints at
`runsObserved >= 2 && runsConfirming === runsObserved`. The local path inherits all of it.
No new copy may assert more than was measured.

**Also on the local path:** do not print an aggregate appearance ratio ("appears in X of N").
The denominator is a query set we chose, so it reads as a visibility rate and is not one.
Prefer the reproducible per-query claim.

### W2.7 — Local competitor discovery

**Files:** `src/pipeline/discovery.py`

`_EXTRACT_PROMPT` (`:14`) is a single module-level constant reading "software products, tools,
or companies", consumed at `:62`. **Do not reprompt it in place** — the consumer path reads
the same constant, and rewriting it for local business names degrades consumer discovery
silently (extraction quality has no loud failure mode).

**Change:** fork into a kind-keyed pair per §0.6. Consumer keeps today's string byte-for-byte;
local gets a business-name prompt. Select on `business_kind` at the `:62` call site. Seed local
candidates from captured local-pack entities rather than LLM recall — same anti-fabrication
posture as W2.4.

Note `_NOISE` (`:21`) also carries product-shaped stopwords (`products?:`, `tools?:`). Extend
it for local rather than rewriting it; the patterns are additive and harmless to the consumer
path.

**Acceptance:** consumer extraction on a fixture response returns today's names exactly (W0.4
assertion passes unchanged); local extraction returns business names; neither path can return
a name absent from the captured entity set.

### W2.8 — Phase 2 exit criterion

`npm run teaser -- <plumber-url>` produces a credible local teaser: verbatim excerpts for
"best {trade} in {city}", the local competitors named, the local source checklist. Josh can
scan a city vertical and send each shop its own report.

---

## Phase 3 — Judge and fact sheet (cache-invalidating — one bump, one commit)

**This is the phase where the hard invariants bite. Batch every prompt change into a single
`_PROMPT_LAYOUT` bump so the cache is invalidated exactly once.**

### W3.1 — Local accuracy flags

**Files:** `src/pipeline/judge.py`

Current flags (`wrong_pricing`, `stale`, `missing_or_invented_feature`) are product
attributes. Local accuracy is **hours, service area, phone number, licensing, emergency
availability**.

### W3.2 — Local fact-sheet template

**Files:** `docs/fact-sheet-template.md`, plus a new local variant

### W3.3 — The cache bump

Bump `_PROMPT_LAYOUT`. Maintain HEAD/RUBRIC split parity with
`scripts/judge_via_workflow.py`. Keep every parity assertion in `tests/test_judge.py` — do
not weaken them to accommodate new flags; extend them.

Use the `prejudge` skill to re-warm cached verdicts for free after invalidation.

**This is the one change in the plan that is unavoidably global** (§0.6). It invalidates
consumer cached verdicts as well as local ones. Update the `_single_fingerprint()` pin in
`tests/test_consumer_path_regression.py` (W0.4) **in this same commit** — that pin exists to
make an accidental fingerprint change loud, and this is the one commit where changing it is
legitimate.

### W3.4 — Local gold set and recalibration

**This is the cost the strategy doc understates.** Every calibration number the product
quotes — judge agreement 96/88/93, the grade bands — was measured on the Oura and Fort
consumer gold sets. A local teaser built on Phases 1–2 runs an **uncalibrated judge**.

Build a local gold set per `docs/labeling-guide.md` and `docs/grade-calibration-guide.md`.
Calibration uses the held-constant API judge with `isolated_cache()` — never the shared
Supabase cache, never subscription/Opus verdicts.

**Until W3.4 completes, no local teaser may quote an accuracy or agreement figure.**

**The consumer path is billed too — budget it here.** W3.1 edits `_ACCURACY_BLOCK` and the
tool schema, which the consumer path also runs. After the bump, the shipped judge is no longer
the judge the consumer figures (96/88/93, the grade bands) were measured on. Those numbers
were measured on Oura and Fort against the *pre-bump* prompt, so strictly they no longer
describe what ships.

Two acceptable resolutions — pick one deliberately, do not let it slide:

1. **Re-run the existing consumer gold sets** against the post-bump judge and confirm the
   agreement figures still hold. Cheapest if the local flags are purely additive and don't
   fire on consumer content — likely, but *likely* is not *measured*. This is the default.
2. If agreement moves, re-derive the consumer figures and update every artifact that quotes
   them before the next consumer teaser goes out.

**Design W3.1 to make option 1 cheap:** add local accuracy flags so they are inert on product
content — no rewording of existing flag definitions, no change to the shared instruction
preamble beyond appending. The more surgical W3.1 is, the less likely consumer agreement
moves.

**Gate:** until the consumer re-run in option 1 passes, no *consumer* teaser may quote an
accuracy or agreement figure either. This gate is symmetric — the bump is global, so the
freeze is global.

---

## Phase 4 — Site audit for local

### W4.1 — Local review platforms

**Files:** `src/audit/offsite/tools.py:49-53`

`REVIEW_PLATFORMS` is `trustpilot.com, apps.apple.com, play.google.com`. For local:
GBP, `yelp.com`, `bbb.org`, `angi.com`, `thumbtack.com`, `homeadvisor.com`, `facebook.com`,
Bing Places, Reddit. Yelp dominates — 3.4× the next source, 72.5% of directory citations on
Google AI Mode.

**Keep both sets and select by business kind.** Do not replace the consumer set; the consumer
ICP is still live.

### W4.2 — Offsite agent prompt

Currently hunts Reddit / listicles / press. Add directory-presence and NAP-consistency checks.

### W4.3 — Local Cat 5 / Cat 6 checks

GBP presence and completeness, NAP consistency across directories, category selection.

**Precedent to follow:** `llms_txt` is deliberately unmapped in
`src/audit/synthesize.py:67` — it runs and shows in the raw Cat-1 table but can never
synthesize into a rubric score or roadmap gap, because no engine confirms consuming it.
Guarded by `test_llms_txt_is_note_only_never_a_roadmap_gap`. **Any new local check must clear
the same bar: evidence that it affects citations, or it ships note-only.**

---

## Phase 5 — Metrics, report, sampling

Lighter. Per-trade sampling bands, local report template, cadence comparison for local.

**Sampling note:** SE Ranking measured ~80% of URLs and >60% of domains swapping between
repeat runs of "near me" queries. `RUNS_PER_QUERY` defaults to 5 and `MAX_RUNS_PER_QUERY` is
5 (`src/config/settings.py:65,70`). Use `geo verify determinism` — it reports an agreement
profile and a `suggest_runs_per_query` band — to set K empirically per trade rather than by
assumption. If local needs K > 5, raise `MAX_RUNS_PER_QUERY` deliberately and record the cost.

---

## Sequencing

```
W0.1 ─┐
W0.2  ├─ Phase 0   (hours; do regardless)
W0.3 ─┘
   │
W0.4 ──────────────── REGRESSION LOCK — hard gate, nothing below starts until it is green
   │
W1.1 → W1.2 → W1.4 ─┐
W1.3 ───────────────┴─ Phase 1   (unblocks everything, no cache impact)
   │
W2.1 → W2.2 → W2.3 ─┐
W2.4 → W2.5 → W2.7  ├─ Phase 2   (sellable teaser)
W2.6 ───────────────┘
   │
W3.1 + W3.2 + W3.3 + W3.4 ── Phase 3   (ONE commit, cache-invalidating + consumer re-run)
   │
W4.1 → W4.2 → W4.3 ── Phase 4
   │
Phase 5
```

**W0.4 is a hard gate, not a Phase 0 nicety.** It captures the consumer baseline while one
still exists to capture. Every phase below it edits at least one shared symbol; run the full
consumer regression suite at the end of each phase, not just at the end of the plan.

Phase 1 → 2 gets a sellable teaser fastest and touches no caches. Phase 3 is one coordinated
cache-invalidating change. Effort order from the strategy doc: Phase 2 teaser resolver ≈
Phase 4 offsite rework > Phase 3 judge + gold set > Phase 1 plumbing > Phase 5 metrics.
Add W0.4 at the front — hours, and it is the only thing making "additive" verifiable.

---

## Definition of done, per phase

Each phase ends with an appended `docs/build-log.md` entry — most recent at top, written only
after every acceptance criterion passes — listing what was built, the file paths, and the
gate results (`mypy` clean, `ruff` clean, `pytest` N passed, `npm test` N passed).

---

## Out of scope

Per `smb-pivot-plan.md §5`, and unchanged here: no geo-grid rank tracking, no GBP posting
automation, no review-generation tooling, no local-pack rank product. The differentiator is
judged answer quality against a fact sheet. Stay on it.

**Also out of scope:** removing the consumer-product path. Both ICPs stay live. Every change
in this plan is additive and selected by business kind — a regression on the consumer path is
a failed work item.

That sentence is now enforced rather than asserted: §0.6 gives the rule (fork by
`business_kind`, never edit a shared symbol in place) and W0.4 gives the mechanism that
detects a violation. The single acknowledged exception is the Phase 3 judge bump, whose cost
to the consumer path is budgeted in W3.4.

**Also out of scope:** migrating the consumer ICP to the local code paths later. The forks
introduced here are permanent by design. If the consumer path is ever retired, that is its own
decision and its own plan — not a side effect of this one.
