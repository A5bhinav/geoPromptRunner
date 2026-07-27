# Build Log

Append-only. Most recent chunk at the top. One entry per chunk, written only after every acceptance criterion passes.

---

## SMB pivot W1.6 + Phase 2 — local-pack entity capture, local query sets and teaser — Completed 2026-07-27

Closed the W2.4 data-source gap flagged in the previous entry, then executed Phase 2
(W2.1-W2.7). The consumer ICP is unchanged throughout; every divergence is selected by
`business_kind`.

### What was built

- **W1.6 — local-pack entity capture (NEW work item; added to the plan).** W2.4
  requires competitors "seeded from captured local-pack entities" and forbids LLM
  recall, but no original Phase 1 item built that capture — W2.4 as specified had no
  data source. Added `LocalEntity` + `AIOverviewsEngine.query_local_entities()`
  (SearchApi's `local_results`, verified against its Google-engine docs) and a
  `GET /api/local-entities` endpoint so the TypeScript teaser reaches it without a
  second SearchApi credential. Refuses to run without a location; drops closed
  businesses (the local twin of `DEFUNCT_BRANDS`).
- **W2.1 — local intent buckets.** `IntentBucket` gains `LOCAL_INTENT`/`HYBRID`/
  `INFORMATIONAL`; `BRAND` is shared. `BUCKET_ALLOCATION` was FORKED, not rebalanced.
  The real break was `_TEASER_BUCKETS`, hardcoded to `(CATEGORY, COMPARISON)`: a local
  set intersects it in ZERO queries. Now `teaser_buckets(business_kind)`, and
  `run_teaser` RAISES on an empty selection instead of reporting "you appear nowhere"
  from no measurement.
- **W2.2 — per-trade query templates.** `data/queries_{hvac,plumbing,barbershop}.json`
  (29/29/28 queries) with `{city}`/`{brand}` slots, plus `src/prompts/local_templates.py`.
  `build_template_csv()` is now parameterized — no-arg returns the Oura consumer CSV
  byte-for-byte (the plan's "replace it" would have been a consumer regression).
- **W2.3 — kind-selected query generation.** Local fallback templates that are
  geo-anchored and NEVER name a competitor. The stale B2B-SaaS phrasing ("for a
  growing startup", "scales with my needs") was fixed rather than deleted, so the
  consumer branch still has a correct fallback.
- **W2.4 — local resolver path.** `LOCAL_SERVICE_PATH_READY` flipped to `true`. The
  anti-fabrication guarantee is now STRUCTURAL, not prompt discipline: `buildProfile`
  discards the model's competitors wholesale for a local site, and only
  `attachLocalCompetitors()` — which requires captured entities — can name a rival. It
  drops the client from its own list and throws rather than emit a rival-less teaser.
  `MockPlatformClient.getLocalEntities()` throws by design: every other mock method
  fabricates, but a fake local rival is the one failure that survives human review.
- **W2.5 — service-area overlap.** New `ServiceAreaVerdict`; a same-trade
  different-metro rival now drops with `serviceAreaMismatch` provenance. Recall-safe
  (only an explicit `different_area` drops) and gated to local: the prompt block is
  APPENDED for local clients, so the consumer prompt is byte-identical.
- **W2.6 — local copy.** `localHeadline`/`localLeadSentence`/`localStakesLine`/
  `localCtaLine` + `LOCAL_SOURCE_CHECKLIST` (GBP, Yelp, BBB, Angi, Thumbtack,
  Facebook, Bing Places, Reddit). "buyers" → "customers"; **no aggregate appearance
  ratio** on the local path (the denominator is a set we chose, so it reads as a
  visibility rate and is not one). Every claim-fidelity guard is inherited, not
  reimplemented — local verbs still grade off judged prominence.
- **W2.7 — forked discovery prompt.** `_LOCAL_EXTRACT_PROMPT` alongside the untouched
  consumer `_EXTRACT_PROMPT`, selected by `extract_prompt_for(business_kind)`.
- **Cross-boundary:** the TypeScript `IntentBucket` union was extended to match the
  Python enum. That surfaced five `Record<IntentBucket, …>` ranking/label tables
  needing local values (weights, bucket labels, two intent priorities, lead priority);
  each got a deliberate local entry rather than a default.

### Acceptance criteria — all passed

- ✅ Local entities: typed and filtered; `[]` on no pack / malformed body / transport
  error; refuses without a location; endpoint 422s on a missing location, 503s when
  the engine can't build
- ✅ Consumer teaser still selects exactly `(category, comparison)`; local selects
  `(local_intent, hybrid)`; empty selection raises
- ✅ All three trade sets load, use only local buckets, 25-40 queries, unique ids,
  slots substitute, unfilled slots fail loudly
- ✅ A local profile is built with NO competitors; `attachLocalCompetitors` sources
  only from captured entities, drops the client, caps at 4, and throws on none
- ✅ Same-metro rival kept, unknown kept, different-metro dropped with provenance;
  consumer competitor sets unaffected
- ✅ Local copy is prominence-graded and prints no ratio
- ✅ Gate: mypy clean (77 files), ruff clean, pytest 301 passed / 1 skipped
  (was 283), `tsc --noEmit` clean, npm test 161 passed (was 143)

### Deviations, and one deliberate test change

- **Two W0.1 tests were rewritten, not deleted.** They pinned "local is refused",
  which W2.4 legitimately changes. They now pin the replacement contract: local
  ROUTES, and a local profile carries no extraction-sourced competitors. This is the
  W0.1 → W2.4 transition the plan describes, not a weakened guard.
- **The consumer-path regression lock never had to be touched.** All 20 assertions
  passed unchanged through every Phase 2 work item — including the judge fingerprint,
  which Phase 2 does not go near.

### Up next — Phase 3 (W3.1-W3.4): judge and fact sheet

The cache-invalidating phase: one `_PROMPT_LAYOUT` bump, one commit. Note W3.4 needs a
hand-labeled local gold set and held-constant API-judge calibration runs — real spend
and human labeling, not something the build can complete on its own.

---

## SMB pivot Phases 0-1 — regression lock, businessKind classifier, location plumbing — Completed 2026-07-27

Executed `docs/smb-pivot-build-plan.md` Phase 0 (W0.1-W0.4) and Phase 1 (W1.1-W1.4).
The pivot ADDS the local-service ICP; the consumer-product ICP stays live and
unchanged. Every change is additive and selected by business kind.

### What was built

- **W0.4 — consumer-path regression lock (built FIRST, as the hard gate).**
  `tests/test_consumer_path_regression.py` (9 tests) + `teaser/tests/consumerPathRegression.test.ts`
  (11 tests). Pins today's consumer behaviour across the six shared symbols Phases 1-4
  touch: `build_template_csv()`, `_TEASER_BUCKETS`, `_EXTRACT_PROMPT`,
  `REVIEW_PLATFORMS`, the teaser resolver/copy path, and `_single_fingerprint()`.
  Designed to fail loudly on an in-place edit; the fix is to fork by business kind,
  never to relax an assertion. The judge-fingerprint pin
  (`5e8caed0…b13b3d`) is the ONE assertion that may change, and only in W3.3.
- **W0.1 — `businessKind` classifier.** `teaser/src/types/domain.ts` gains the
  `BusinessKind` type — the single selector for every consumer/local divergence.
  `profileExtraction.ts` gains the field in the extraction schema (required +
  enumerated) and prompt, `businessKindOf()` (the one canonical default),
  `LOCAL_SERVICE_PATH_READY = false`, and `assertSupportedBusinessKind()`, which
  REFUSES a local-service site until the local path exists. Checked before any other
  field is normalized, because on a local site every downstream field was extracted by
  consumer-shaped instructions and is untrustworthy. Becomes the W2.4 router.
- **W0.2/W0.3 — docs.** `teaser/README.md`: corrected the default engine list to
  `perplexity, openai_search, gemini_grounded` (was three wrong names), corrected
  `pdf.ts` from "documented stub" to the real Playwright renderer it is, and
  documented the `--engines google_ai_overviews` flag WITH the unpinned-locale caveat
  (valid for consumer prospects, not for any local query until W1.3).
- **W1.1 — location on the profile.** `BusinessLocation` + `canonicalLocation()` in
  `domain.ts`; optional `location?` on `CompanyProfile` and mirrored onto `TeaserDraft`
  (with `businessKind`) for regeneration parity — the `clientAliases` precedent, so a
  regenerated local teaser can't silently revert to consumer-shaped.
- **W1.2 — resolver extracts NAP.** `location` added to the extraction schema
  (required, nullable) and prompt, sourced from the site's own NAP block/contact
  page/schema.org `LocalBusiness`, with an explicit "do NOT infer from the brand name
  or area code" clause. `normalizeLocation()` keeps a location only when
  city+region+country are ALL present — a partial one resolves at SearchApi to "the
  most popular match", i.e. a different metro, silently measuring the wrong market.
- **W1.3 — AI Overviews accepts a location.** `AIOverviewsEngine(location=...)`,
  constructor-injected so the uniform `BaseEngine.query(prompt)` fan-out contract is
  untouched. Param name VERIFIED against SearchApi's Google-engine docs (2026-07):
  `location` takes a canonical NAME and SearchApi builds `uule` itself; the two are
  mutually exclusive, so only `location` is sent. The recorded and sent params are now
  literally the same dict, so the audit log cannot drift from the request (Test E).
- **W1.4 — location through the audit contract.** `config,location` row emitted by
  `teaser/src/platform/csv.ts` (only when a location exists), parsed into
  `RunConfig.location` by `csv_loader.py`, threaded through `build_engines(location=)`
  — which passes it ONLY to `google_ai_overviews`, the one surface with a locale knob —
  and through both `runner.py` call sites. Persisted on `audit_runs.location`
  (`data/schema_ui.sql`, idempotent `add column if not exists`) and restored on resume,
  so an interrupted local run cannot finish un-localized and mix two markets.

### Acceptance criteria — all passed

- ✅ W0.4 green at the pre-pivot baseline before any shared symbol was touched
- ✅ A local-service fixture throws with an actionable message; a consumer-product
  fixture still resolves unchanged; the blank/`"product"` category guard still fires
- ✅ Location: complete → kept; partial → dropped, never guessed; product → never acquires one
- ✅ AI Overviews with no location produces today's payload key-for-key
  (`{engine, q, api_key}`); with one, sends `location` and never `uule`; error paths
  still return `None`
- ✅ A CSV with no `location` row parses exactly as before (`location is None`, not `""`)
- ✅ CSV round-trip: `config,location` → `RunConfig.location` → engine
- ✅ `tests/test_isolation.py` updated narrowly (14 → 21); no matcher loosened
- ✅ Gate: mypy clean (76 files), ruff clean, pytest 283 passed / 1 skipped
  (was 264), `tsc --noEmit` clean, npm test 143 passed (was 118)

### Deviations from the plan, and why

- **W2.2's "replace the Oura starter template" was NOT done** — it is a consumer
  regression (`build_template_csv()` is served at `GET /api/template.csv`). The plan
  was amended to parameterize instead; W0.4 pins the no-arg output.
- **`_PROMPT_LAYOUT` deliberately untouched.** Nothing in Phases 0-1 goes near a judge
  prompt, so no cached verdict was invalidated.
- **Schema migration is written but NOT applied.** `audit_runs.location` exists in
  `data/schema_ui.sql`; it still needs running against Supabase. Until then a resumed
  run reads `None` and behaves as today.

### Up next — Phase 2 (W2.1-W2.7): local query sets and the teaser

Blocked on one unresolved plan dependency: **W2.4 requires competitors "seeded from
local-pack / directory entities captured in Phase 1", but no Phase 1 work item builds
that capture.** W1.3 localizes the AI Overviews request; it does not persist the
local-pack entities W2.4 needs, and the plan is explicit that LLM recall must never
supply local rivals. Phase 2 needs an entity-capture work item added before W2.4 can
be built as specified.

---

## Research-validation fixes — rubric evidence alignment (llms.txt note-only, schema hygiene framing, doc corrections) — Completed 2026-07-21

Applied the geoPromptRunner-flagged items from the 2026-07-21 deep-research
validation run (site/roadmap evidence base; adversarially verified claims).

### What was built

- **`src/audit/synthesize.py`** — dropped `llms_txt` from `_CHECK_MAP`: the
  check still runs and shows in the raw Cat-1 table, but a missing llms.txt can
  no longer synthesize into a rubric score or roadmap gap (no engine confirms
  consuming it; ~300k-domain analyses show zero correlation with AI citations).
  Renamed the `schema_valid` check to "schema.org markup valid and matching
  visible content (hygiene)" — controlled studies (Ahrefs matched-control) show
  no citation lift from JSON-LD, so the name must not imply visibility impact.
- **`src/audit/rubric.py`** — `DEFAULT_CHECKLIST`: removed "llms.txt present"
  from Cat 1; reworded Cat 5 to hygiene/entity-clarity framing and added
  "entity identifiers consistent across the web".
- **`tests/test_synthesize.py`** — new
  `test_llms_txt_is_note_only_never_a_roadmap_gap` guard; updated the schema
  check-name assertion.
- **`docs/smb-pivot-plan.md`** — corrected the Foundation/AirOps attribution
  (the ~60% home-services third-party figure is from a different study; the
  claimed Perplexity–Yelp API deal didn't verify and was dropped; added the
  verified 62.1% Perplexity share). Replaced the conflated "65–81% turnover"
  volatility phrasing with the verified "~80% of URLs / >60% of domains" from
  SE Ranking's AI Mode volatility test; Ahrefs CTR claim tightened to 34.5%
  (dropped the unsubstantiated –58% bound); run-rate example aligned to n/5.
- **`docs/website-plan.md`** — fixed the Whitespark stat tile (68% is the
  *local-business* average; 92% informational — the old wording mismatched the
  number); aligned mention-rate examples to `RUNS_PER_QUERY=5` and recorded the
  run-count-language decision (copy states what the instrument does; bump
  config before copy if we want a bigger-K story).

### Acceptance criteria — all passed

- ✅ `mypy src/` clean (76 files)
- ✅ `ruff check src/` clean
- ✅ `pytest tests/` — 264 passed, 1 skipped (includes the new llms.txt guard)

---

## Isolation & Determinism — Engine isolation proven, pinned, and guarded (docs/isolation-determinism-plan.md) — Completed 2026-06-11

Converted the implicit "every call is fresh" property into a proven, guarded
one, per the plan's five build items. No measurement behavior changed — the
calls were already stateless; this adds the proof, the anti-regression guard,
and the model/seed pins that keep two measurement cycles comparable.

### What was built

- **`src/engines/base.py`** — the Layer-2 statelessness code rule is now part of
  the `BaseEngine` contract docstring (one user message, no system prompt, no
  state params, clients are pools not conversations), plus a `MODEL_ID` class
  attribute: the exact model string sent to the provider, recorded per run.
- **Dated model snapshots (Layer 3)** — `openai` pinned to `gpt-4o-2024-08-06`,
  `openai_search` to `gpt-4o-search-preview-2025-03-11` (both confirmed live);
  Anthropic ids were already dated; Gemini GA names and Perplexity `sonar` have
  no dated variants — documented as the firmest pins those providers offer.
- **`seed` (Layer 4)** — new `ENGINE_SEED` setting (default 42), sent on the
  OpenAI and Gemini parametric engines (the providers that accept one).
- **`src/engines/payload_log.py` (Test E)** — `record_payload()` logs every
  outgoing request body at DEBUG and, when `PAYLOAD_LOG_PATH` is set, appends
  it as JSONL (timestamp, engine, payload; secret keys scrubbed; never raises).
  Wired into all 8 engine adapters; where possible the recorded dict *is* the
  dict sent, so log and request can't drift.
- **`engine_models` run metadata (Layer 3)** — new jsonb column on
  `audit_runs` (Supabase migration `add_engine_models_to_audit_runs`),
  populated by both run paths (`orchestrator.run_audit`, `api/runner.start_run`)
  via the new `orchestrator.engine_models()` helper; round-trip verified.
- **`src/verification/`** — the live probes:
  - `canary.py` (Test A): two-call memory probe with an unguessable marker;
    `leaked`/`isolated`/`inconclusive` verdicts (conservative: a failed setup
    call can't produce a clean verdict).
  - `determinism.py` (Test D): K fresh repeats → agreement profile
    (`unique_answers`, `modal_agreement`, `identical`) + `suggest_runs_per_query`
    bands calibrating whether K=3 is enough.
  - `shuffle.py` (Test C): full set forward then reversed, per-query
    normalized comparison — order must not matter beyond the Test D noise band.
- **`geo verify {canary,determinism,shuffle}`** CLI subcommand (`src/cli.py`)
  with `--surface/--query/--k/--query-set`.
- **`tests/test_isolation.py` (Test B — the anti-regression guard)** — 14 tests
  capturing every engine's outgoing payload at the client boundary: exactly one
  user message, no system prompt, no state params (`store`,
  `previous_response_id`, thread/conversation/session ids, ...), constant
  inputs across calls, dated-snapshot model ids, second call carries nothing of
  the first (Josh's smart-ring → Oura scenario, asserted directly), MODEL_ID
  declared on every registered engine, payload-log JSONL + secret scrubbing.
- **`tests/test_verification.py`** — 20 tests proving both probe verdict paths
  with stateless/stateful/dead fake engines, plus the agreement math and
  shuffle comparison logic.
- **`.env.example`** — documents `ENGINE_SEED` and `PAYLOAD_LOG_PATH`.

### Acceptance criteria — all passed

- ✅ Full suite green: 99 passed (65 pre-existing + 34 new)
- ✅ Guard verified to bite: with the engine changes reverted (stashed) the new
  payload tests fail (8 failures) — a regression cannot pass silently
- ✅ mypy (strict) clean on `src/` and both new test files; ruff check + format clean
- ✅ Live canary run (Test A): openai, anthropic, gemini, perplexity,
  openai_search, anthropic_search all `isolated` — no engine could recall the
  prior call. gemini_grounded inconclusive (provider 500s during the run, not
  an isolation finding); google_ai_overviews inconclusive (SERP surface returns
  no overview for the probe — it has no chat state to leak)
- ✅ Dated snapshots resolve on the live APIs (both OpenAI pins answered)
- ✅ `engine_models` migration applied; write + read-back verified against
  Supabase (smoke row soft-archived, never hard-deleted)
- ✅ Keyless `__main__`/probe smoke: payload_log, orchestrator teaser, and all
  three probes run against the mock engine

---

## UI — CSV-Upload Audit UI (docs/ui-plan.md, Phases A–E) — Completed 2026-06-03

Built the full front door from `docs/ui-plan.md`: drop CSV(s) → preview the
merged audit → run across engines → read the report. Additive only — the API
layer imports and calls the existing pipeline (`run_query_set`, the engine
adapters, `metrics`, `judge_metrics`, the judge, `db`); no working module was
rewritten. The two pre-existing source edits are purely additive (a `judge`
field on `RunConfig`, unchanged elsewhere). All 65 existing tests still pass.

### What was built

- **`src/prompts/csv_loader.py`** (Phase A) — parses one or more CSVs on the
  fixed `block,key,value,intent,persona` schema, merges them by block (queries
  accumulate, facts concatenate, config keys merge with conflict detection),
  and validates the merged result (required config keys, valid intents, unique
  query ids across files, known engines, runs_per_query). Returns a `PreviewData`
  that always renders (with per-file provenance + per-row validity) plus a
  run-ready `ParsedAudit` when clean. Ships `build_template_csv()`.
- **`tests/test_csv_loader.py`** — 15 tests: clean single file, split-file merge,
  order-independence, duplicate-id / conflicting-config / bad-intent /
  missing-required / no-queries / unknown-engine / bad-runs errors, template
  round-trip.
- **`src/api/`** (Phase B, FastAPI):
  - `engine_registry.py` — name→adapter map + a keyless deterministic
    `MockEngine` so the whole UI runs without API keys (`engines=mock`).
  - `reports.py` — assembles the structured report the UI renders (scorecard,
    leaderboard, by-bucket, accuracy flags, sources, losing queries); judge-aware
    with regex fallback. Pure.
  - `runner.py` — in-memory run registry + background thread per run; loops
    `run_query_set` query-by-query for live progress; best-effort Supabase
    persistence and best-effort judge (skipped, not fatal, when unconfigured).
  - `app.py` — `GET /template.csv`, `POST /audits/preview`, `POST /audits`
    (422 + structured errors on invalid), `GET /audits`, `GET /audits/{id}/status`,
    `GET /audits/{id}/report`, `POST /audits/{id}/cancel`; CORS for the dev front end.
- **`web/`** (Phases C–E) — Next.js App Router + TypeScript + Tailwind +
  shadcn-style components + Recharts. Upload (multi-file drag-drop, file chips,
  template link, recent audits), Preview (Config/Fact/Queries tabs with
  provenance + inline errors, run gated on a clean set), Progress (live counter,
  per-engine chips, elapsed, cancel), Report (scorecard cards, leaderboard bars,
  per-bucket + accuracy, sources, losing queries, print/JSON export).
- **`requirements.txt`** — added `fastapi`, `uvicorn[standard]`, `python-multipart`.

### Acceptance criteria — all passed

- ✅ CSV loader: mypy (strict) + ruff clean; `__main__` runs; 15 unit tests pass
- ✅ API: mypy (strict) + ruff clean; `__main__` blocks run
- ✅ End-to-end over HTTP (uvicorn): preview, create+run, status→done, report,
  list, template, and 422-on-invalid all verified with the mock engine
- ✅ "not assessed" degradation confirmed: no fact sheet → accuracy not assessed,
  no client domain → citation not assessed, no judge → regex grade/visibility
- ✅ Front end: `next build` compiles with no type errors; all routes serve
- ✅ Full existing suite still green (65 passed)

---

## Maintenance — Code-Review Follow-up Fixes — 2026-05-31

Applied fixes for findings from the high-effort code review of the hardening
pass. All 18 src files still pass mypy (strict) + ruff; every `__main__` runs;
parser verified behavior-identical across 3,500 randomized cases; never-raise
invariant re-confirmed; no-leak logging confirmed (a simulated sensitive value
did not reach the logs).

- **`src/storage/db.py`** — added a single `_execute(op_label, operation)` helper
  that owns the storage try/except, logs only `type(exc).__name__`, and raises
  `StorageError`. All four writes **and the read path** (`_select_rows`) now route
  through it. Fixes the read-path leak (it previously still logged the raw
  exception) and removes the 4× copy-pasted error blocks.
- **`src/config/settings.py`** — added `ENGINE_TIMEOUT_SECONDS` (default 60s, was a
  per-engine 30s) and `ENGINE_MAX_RETRIES`, env-overridable. The three engine
  files now import these instead of duplicating constants — one home for the
  bounded-run policy. The 60s default reduces spurious timeouts on slow-but-valid
  generations while still preventing a stall.
- **`src/engines/perplexity_engine.py`** — added `close()` and a best-effort
  `__del__` so the persistent `httpx.Client` releases its pooled connection
  instead of leaking it.
- **`src/pipeline/parser.py`** — extracted `_classify(present, recommended)` shared
  by `detect_mention` and `extract_competitor_mentions`, removing the duplicated
  classification ladder while preserving the once-per-response scan optimization
  and the present-gated short-circuit.

Not changed: the "cached broken Supabase client" finding was re-examined and
dropped — credentials come from module-level `settings.*` read once at import, so
the old per-call `create_client` used the same static values; caching introduces
no regression and the "recover after credential rotation" path is unreachable here.

---

## Maintenance — Efficiency & Security Hardening Pass — 2026-05-31

Cross-cutting pass (not a chunk). No new features; scope locks respected — the
pipeline stays **synchronous** (async remains a non-goal) and no API key is
logged. All 18 src files pass mypy (strict) + ruff; every `__main__` block runs;
invariant #1 (engines never raise) re-verified with dummy keys.

### Efficiency

- `src/pipeline/parser.py` — precompiled the recommendation-term regex once at
  import; cache compiled per-brand patterns via `lru_cache`;
  `extract_competitor_mentions` now scans for recommendation language once per
  response instead of once per competitor (≈5k→≈k regex ops for k competitors).
  Verified behavior-identical to per-brand `detect_mention`.
- `src/engines/perplexity_engine.py` — reuse one persistent pooled `httpx.Client`
  across all prompts instead of a fresh TCP/TLS handshake per call.
- `src/storage/db.py` — cache the Supabase client (lazy singleton) instead of
  reconstructing it on every read/write.
- `src/engines/openai_engine.py`, `anthropic_engine.py` — explicit 30s timeout +
  2 bounded retries so one hung request can't stall the synchronous run.
- `src/audit/report.py` — sort the share-of-model rows once, not twice.

### Security / leak prevention

- `.gitignore` — now ignores all `.env*` variants (keeps `.env.example`) plus
  `*.pem/*.key/secrets.*/service-account*.json/.netrc`, venvs, caches, logs, and
  local output dirs. Verified with `git check-ignore`: secrets ignored,
  committable files not.
- `src/storage/db.py` — write-failure logs now record the exception **type** only
  (Postgres errors can echo back inserted row values); full detail still chains
  to the caller via `StorageError`.
- `src/pipeline/parser.py` — empty/whitespace brand now returns `NOT_MENTIONED`
  (previously an empty pattern could false-positive as a mention).

### Recommendation (not applied)

- `requirements.txt` uses `>=` lower bounds. Consider a pinned lockfile
  (`pip-compile`/`uv lock`) for reproducible, supply-chain-safe installs. Left
  as-is to avoid changing install behavior without sign-off.

---

## Chunk 11 — Technical accessibility checker — Completed 2026-05-31

### What was built

- Built `src/audit/technical_check.py` — `check_robots_txt`, `check_llms_txt`, `check_sitemap`, `check_rendering`, each returning a `CheckResult` TypedDict (`status: Literal["pass","partial","fail"]`, `details: str`). All HTTP via `httpx` with a 10s timeout; transport errors caught and returned as a `fail` result (never raised).

### Acceptance criteria — all passed

- ✅ `check_robots_txt`, `check_llms_txt`, `check_sitemap`, `check_rendering` implemented
- ✅ `CheckResult` TypedDict with the required `status`/`details` shape
- ✅ All requests use `httpx` with a 10-second timeout
- ✅ Test block runs all 4 checks against a real domain (`example.com`); verified against `nytimes.com` that blocked AI crawlers are correctly reported as `partial` (6 of 7 blocked)

### Up next — Chunk 12: Dry run (integration)

Run the full pipeline end-to-end against one real client domain. Requires live API keys and Supabase credentials.

---

## Chunk 10 — Report generator — Completed 2026-05-31

### What was built

- Built `src/audit/report.py` — `generate_report(run_id: str) -> str` (assembles data from storage and renders) plus a pure `render_report(data: ReportData) -> str`.
- Extended `src/storage/db.py` with read helpers (`get_run`, `get_results`, `get_mentions`, `get_citations`) needed to assemble a report from a stored run.
- `ReportData` TypedDict added to `src/storage/models.py`.

### Acceptance criteria — all passed

- ✅ `generate_report(run_id: str) -> str` returns a markdown string
- ✅ Report includes client name, date stamp, mention rate per engine, competitor share-of-model table, top cited domains, and a summary of findings
- ✅ Test block renders a report from mock data and prints it (deterministic — invariant #7)

---

## Chunk 9 — Supabase storage — Completed 2026-05-31

### What was built

- Built `src/storage/db.py` — `create_run`, `save_results`, `save_mentions`, `save_citations` (+ read helpers), targeting tables `prompt_runs`, `prompt_results`, `brand_mentions`, `citations`. All writes wrapped in try/except and raise `StorageError` on failure; soft-delete via `archived_at` (no hard deletes). All primary keys use `uuid.uuid4()`.
- Extended `src/storage/models.py` with `PromptRun`, `BrandMention`, `Citation` TypedDicts.
- Installed `supabase` into `.venv`.

### Acceptance criteria — passed (live-DB step pending credentials)

- ✅ Tables `prompt_runs`, `prompt_results`, `brand_mentions`, `citations` modeled
- ✅ `create_run(client_name, prompt_count) -> run_id` returns a generated run id
- ✅ `save_results`, `save_mentions`, `save_citations` implemented
- ✅ All writes in try/except, raise `StorageError` on failure
- ⚠️ Test block saves mock data and confirms rows in Supabase — **code validated (typecheck/lint/graceful-skip)**, but the live "rows exist" confirmation requires `SUPABASE_URL`/`SUPABASE_KEY`, which are not configured. The test block degrades gracefully and exits 0 with a clear message when creds are absent. To be re-run during Chunk 12 with real credentials.

---

## Chunk 8 — Competitor extractor — Completed 2026-05-31

### What was built

- Extended `src/pipeline/parser.py` with `extract_competitors(competitors, response) -> list[str]` and `extract_competitor_mentions(competitors, response) -> dict[str, MentionType]`.

### Acceptance criteria — all passed

- ✅ `extract_competitors` returns competitors present in the response
- ✅ `extract_competitor_mentions` maps each competitor to a `MentionType`
- ✅ Both case-insensitive (word-boundary matching)

---

## Chunk 7 — Brand mention detector — Completed 2026-05-31

### What was built

- Built `src/pipeline/parser.py` — `MentionType` enum (`recommended | mentioned | not_mentioned`) and pure `detect_mention(brand, response) -> MentionType`.

### Acceptance criteria — all passed

- ✅ `MentionType` enum with the three values
- ✅ `detect_mention(brand, response) -> MentionType`
- ✅ Case-insensitive matching
- ✅ `recommended` requires explicit language ("best", "recommend", "suggest", "top choice")
- ✅ Test block runs 5 sample responses and prints correct verdicts (all 5 OK)

---

## Chunk 6 — Prompt runner — Completed 2026-05-31

### What was built

- Built `src/pipeline/prompt_runner.py` — `run_prompts(prompts: list[str], engines: list[BaseEngine]) -> list[PromptResult]`, synchronous and order-stable.
- Built `src/storage/models.py` with the `PromptResult` TypedDict (`prompt`, `engine_name`, `response`, `timestamp`).
- Created package prerequisites: `src/pipeline/__init__.py`, `src/storage/__init__.py`, `src/audit/__init__.py`.

### Acceptance criteria — all passed

- ✅ Accepts `prompts: list[str]` and `engines: list[BaseEngine]`
- ✅ Returns `list[PromptResult]` with `prompt`, `engine_name`, `response`, `timestamp`
- ✅ `PromptResult` defined as a TypedDict in `src/storage/models.py`
- ✅ Test block runs 3 sample prompts across available engines and prints the result count (real engines skipped without keys; a keyless echo engine demonstrates the runner)

### Validation (Chunks 6–11)

- ✅ mypy (strict): `Success: no issues found in 18 source files`
- ✅ ruff check: `All checks passed!` — ruff format: `18 files already formatted`
- ✅ `python -m src.pipeline.prompt_runner` → 3 results collected
- ✅ `python -m src.pipeline.parser` → 5/5 verdicts correct, competitor extraction correct
- ✅ `python -m src.audit.report` → full markdown report with all required sections
- ✅ `python -m src.audit.technical_check` → 4 checks run live against `example.com`
- ⚠️ `python -m src.storage.db` → graceful skip (no Supabase credentials configured)

---

## Chunk 5 — Gemini engine — Completed 2026-05-31

### What was built

- Built `src/engines/gemini_engine.py` — `GeminiEngine(BaseEngine)` using `gemini-1.5-pro` via `google-generativeai`.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `GEMINI_API_KEY`, raises `ValueError` if missing
- ✅ Uses `gemini-1.5-pro`
- ✅ `ResourceExhausted` (rate limit), `DeadlineExceeded` (timeout), `GoogleAPIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

Note: documented `# type: ignore[attr-defined]` on `genai.configure`/`genai.GenerativeModel` — the deprecated `google-generativeai` package ships incomplete re-exports; names exist at runtime.

### Up next — Chunk 6: Prompt runner

Build `src/pipeline/prompt_runner.py` to send a list of prompts to all four engines and collect `list[PromptResult]` (TypedDict in `src/storage/models.py`).

---

## Chunk 4 — Perplexity engine — Completed 2026-05-31

### What was built

- Built `src/engines/perplexity_engine.py` — `PerplexityEngine(BaseEngine)` calling the Perplexity REST API (`model="sonar"`) via `httpx`, with citation extraction.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ `query()` returns response text
- ✅ `query_with_citations()` returns `tuple[str | None, list[str]]`
- ✅ Citations extracted from the response's `citations` field
- ✅ Test block prints both response and list of citation URLs
- ✅ On error returns `(None, [])`; never raises. mypy (strict) and ruff pass

---

## Chunk 3 — Anthropic engine — Completed 2026-05-31

### What was built

- Built `src/engines/anthropic_engine.py` — `AnthropicEngine(BaseEngine)` using `claude-3-5-sonnet-20241022`; extracts text from `TextBlock` content blocks.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `ANTHROPIC_API_KEY`, raises `ValueError` if missing
- ✅ Uses `claude-3-5-sonnet-20241022`
- ✅ `RateLimitError`, `APITimeoutError`, `APIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

---

## Chunk 2 — OpenAI engine — Completed 2026-05-31

### What was built

- Built `src/engines/openai_engine.py` — `OpenAIEngine(BaseEngine)` using `gpt-4o`.
- Created prerequisite `src/config/settings.py` + `src/config/__init__.py` — the single place that reads env vars (via `python-dotenv`); all engines load their keys from here, never `os.getenv` directly (§5 convention).
- Installed engine SDKs into `.venv`: `openai`, `anthropic`, `google-generativeai`, `httpx`, `python-dotenv`.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `OPENAI_API_KEY`, raises `ValueError` if missing
- ✅ Uses `gpt-4o`
- ✅ `RateLimitError`, `APITimeoutError`, `APIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

### Validation (Chunks 2–5)

- ✅ mypy (strict): `Success: no issues found in 9 source files`
- ✅ ruff check: `All checks passed!` — ruff format: `9 files already formatted`
- ✅ Each `python -m src.engines.<name>` runs without crashing (graceful `ValueError` skip when key absent)
- ✅ Invariant #1 verified: with dummy keys set, every `query()` returns `None` on auth/network failure and never raises; all four are `BaseEngine` instances

---

## Chunk 1 — Base engine interface — Completed 2026-05-31

### What was built

- Built `src/engines/base.py` — `BaseEngine` abstract base class defining the uniform engine contract (`query(prompt: str) -> str | None`, `ENGINE_NAME` class attribute).
- Built `src/engines/__init__.py` — re-exports `BaseEngine` for clean imports.
- Built `src/__init__.py` — makes `src` an importable package.
- Created prerequisite project files: `requirements.txt`, `.env.example`, `pyproject.toml` (ruff + mypy strict config), `.gitignore`.

### Acceptance criteria — all passed

- ✅ `BaseEngine` abstract class with abstract `query(prompt: str) -> str | None`
- ✅ `ENGINE_NAME` class attribute defined (default `"base"`, subclasses override)
- ✅ Docstring explains contract: returns response text or `None` on error, never raises
- ✅ Clean import from other modules (`from src.engines import BaseEngine` and `from src.engines.base import BaseEngine` resolve to the same class)

### Validation

- ✅ mypy (strict): `Success: no issues found in 3 source files`
- ✅ ruff check: `All checks passed!`
- ✅ ruff format --check: `3 files already formatted`
- ✅ Runtime: abstract base is non-instantiable; concrete subclass `query()` returns `str | None` as declared

---

### Up next — Chunk 2: OpenAI engine

Implement `src/engines/openai_engine.py` subclassing `BaseEngine`, loading `OPENAI_API_KEY`, using `gpt-4o`, catching rate-limit/timeout/API errors and returning `None`.
