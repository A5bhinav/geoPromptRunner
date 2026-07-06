---
name: geo-dev
description: Development guide for the geoPromptRunner GEO measurement platform. Load this before developing, extending, debugging, refactoring, or reviewing ANY part of this repo — engines, pipeline, judge, caches, site audit, crawler, calibration, storage, API, web UI, teaser generator, or scripts. Also load it when planning a feature, fixing a bug, writing tests, touching judge prompts or cache keys, adding an engine, changing the report, or answering questions about how this project works. It contains the current architecture map, judge cache-key discipline, cost model, config reference, and docs map — the stale docs/claude.md does NOT.
---

# Developing geoPromptRunner

The platform measures brand visibility in AI-generated answers and turns it
into a sellable audit. Three facts shape almost every decision here:

1. **Engine answers are the measurement.** They must come from real APIs, with
   pinned determinism knobs, or the numbers mean nothing.
2. **Judging is re-derivable.** Verdicts are content-addressed and cached, so
   judging can be re-run, pre-warmed on the subscription, or invalidated — as
   long as cache keys stay honest.
3. **Every run costs real money.** Budget gates exist; the prejudge flow exists
   so iteration doesn't burn API credit.

Vocabulary used everywhere: **Cat 1–7** (the audit rubric categories),
**prominence** (`recommended_first|mid_pack|buried|also_ran|absent`),
**framing** (`positive|neutral|negative`), **accuracy flags**
(`wrong_pricing|stale|missing_or_invented_feature|identity|competitor_confusion`,
severity `high|med|low`), **fact sheet** (per-client ground truth, stored on
the run row), **surface** (parametric memory vs live search).

## Architecture

```
query set (versioned, intent-tagged)          data/*.json, src/prompts/
  → engines (×8, incl. search surfaces)       src/engines/
  → orchestrator (cost gate, resume, persist) src/pipeline/orchestrator.py
  → Supabase (audit_runs, query_results, …)   src/storage/
  → judge (cached verdicts)                   src/pipeline/judge.py + judge_cache.py
  → metrics / report                          src/pipeline/*metrics*, src/api/reports.py
  → API → web UI                              src/api/app.py → web/app/
site audit: crawl → deterministic checks → content judge (cached)
            → offsite agent (live) → roadmap  src/audit/
teaser/audit deliverable (TypeScript)         teaser/
```

### Key files

| Area | File | Purpose |
|---|---|---|
| Engines | `src/engines/base.py` | `BaseEngine` contract: `query()` returns text or `None`, never raises |
| | `openai/anthropic/gemini/perplexity_engine.py` | parametric-memory adapters |
| | `*_search_engine.py`, `gemini_grounded_engine.py`, `ai_overviews_engine.py` | live-search surfaces (`--surface search`) |
| | `payload_log.py` | raw request/response capture (`PAYLOAD_LOG_PATH`) |
| Pipeline | `orchestrator.py` | `run_audit()` — cost estimate/abort, per-cell resume, incremental persist |
| | `prompt_runner.py` | concurrent fan-out with per-provider rate gates |
| | `parser.py` | pure text→mention functions |
| | `judge.py` | the LLM judge (see below) |
| | `judge_cache.py` | content-addressed verdict cache; backends supabase/memory/none |
| | `metrics.py`, `judge_metrics.py` | mention/SOV vs judge-derived grades |
| | `calibration.py`, `grade_calibration.py` | gold-set agreement measurement |
| | `discovery.py`, `trend.py`, `cost.py` | competitor discovery, cadence diff, spend estimation |
| Audit | `site_audit.py` | `run_site_audit()` orchestration |
| | `crawl/` | fetcher, robots, page selection, DOM extraction, cache |
| | `checks/ssr.py`, `schema.py`, `links.py` | deterministic Cat 1/2/5 checks |
| | `checks/content_judge.py` (+ `_cache.py`) | LLM Cat 3/4 checks, evidence-quoted, own cache |
| | `offsite/agent.py` | Cat 6 live research agent (never cached, by design) |
| | `synthesize.py` | roadmap rollup |
| | `technical_audit.py`, `technical_check.py` | Cat 1 accessibility checks |
| Storage | `db.py` | all core writes; `_execute` owns try/except → `StorageError` |
| | `models.py` | typed rows and enums |
| API/UI | `api/app.py`, `api/runner.py` | FastAPI; `rejudge_run()`, `judge_status()` |
| | `web/app/` | Next.js: projects, audits, teaser pages |
| Scripts | `judge_via_workflow.py` + `prejudge_workflow.js` | subscription prejudge, Part A |
| | `content_judge_via_workflow.py` + `content_prejudge_workflow.js` | prejudge, Part B |
| | `run_calibration.py`, `build_*_sheet.py`, `parse_*_sheet.py` | gold-label tooling |
| Verification | `src/verification/` | determinism, canary, shuffle guards |
| | `src/net_guard.py` | network isolation guard |

## The judge layer (highest-risk area — read before touching)

`Judge()` (single mode, the default) makes one forced-tool call per unique
(prompt, answer) pair: a **cached system block** (rules + brand list + accuracy
block + fact sheet — the RUBRIC) plus a small per-answer user message (the
HEAD). Two opt-in modes exist — `JUDGE_CASCADE` (cheap structural pass + strong
accuracy pass) and `JUDGE_VERIFY` (per-flag adversarial verifier) — and each
gets its **own cache keyspace** via the cache model id.

**Cache key** = hash of schema version + model + prompt fingerprint + client +
sorted competitors + fact sheet + prompt + answer. Consequences:

- Editing judge prompt text, tool schema, or layout changes
  `_prompt_fingerprint` → every cached verdict misses. That's correct behavior,
  not a bug. Bump `_PROMPT_LAYOUT` when the message *structure* changes, tell
  the user existing runs need re-prejudging, and keep `tests/test_judge.py`
  parity guards passing — they verify the HEAD/RUBRIC split reassembles
  byte-identically and that `judge_via_workflow.py dump` computes the same keys
  a live `Judge()` does. If a prompt edit breaks the split markers the parity
  test depends on, fix the split, don't delete the test.
- The fact sheet is in the key, so the CLI/UI judge and prejudge must key off
  the **same** sheet — that's why both default to `audit_runs.fact_sheet`
  (the run row), and why hand-passing `--fact-sheet` paths is almost always
  wrong.
- Cascade/verify write different keyspaces; the prejudge tooling refuses them
  loudly. Don't work around that refusal.

The content judge (`content_judge.py`) mirrors this: versioned rubric
(`CONTENT_RUBRIC_VERSION`), key = model + check id + version + page text,
verdicts carry verbatim evidence quotes that are validated (normalize +
rapidfuzz ≥95) — invalid evidence downgrades to unknown, never silently passes.

## Cost model and the standard workflows

What spends money: engine queries (always — that's the product), the offsite
agent (always — live research), and judging **on a cache miss**. What's free:
anything cached, all reports, re-judging a warm run. Guardrails:
`MAX_AUDIT_COST_USD` (default 25, per run) and `MAX_TOTAL_SPEND_USD` (200);
the orchestrator estimates and aborts before spending.

**Iterating on judging (the normal dev loop):**
1. Run the audit with judging off — collect answers on the API.
2. `/prejudge <run_id>` — warm `judge_cache` (+ `content_judge_cache` if
   crawled) using subscription subagents. See `.claude/skills/prejudge/SKILL.md`
   for the full procedure; don't duplicate it here.
3. `python -m src.cli judge <run_id>` or the UI Judge button — 100% cache hits,
   $0. Re-run site audit with `RUN_CONTENT_JUDGE=1` for the free content scores.

Prejudge verdicts come from a different model (Opus, not the held-constant
temp-0 Sonnet). They are for dev iteration only — never let them feed
calibration or gold labels. `scripts/run_calibration.py` uses
`isolated_cache()` (in-memory) precisely so the shared Supabase cache can't
contaminate a calibration run.

**Client audit (the sold service)** follows the 7-step methodology:
baseline measurement → technical accessibility → on-site audit → off-site
audit → competitive benchmark → prioritized roadmap → deliver. The rubric
categories: Cat 1 technical accessibility (robots/WAF/SSR/llms.txt/sitemap/
gating), Cat 2 content coverage, Cat 3 structure/extractability, Cat 4
substance/E-E-A-T, Cat 5 schema, Cat 6 offsite authority (the B2C
battleground: Reddit, App Store/Play Store, creators, listicles, Trustpilot),
Cat 7 baseline measurement. Statuses: pass/partial/fail (+ ungradeable/unknown
in the content judge).

## CLI

```
python -m src.cli audit <queries.json> --domains <d>   # full audit (add --surface search)
python -m src.cli teaser <queries.json>                # fast demo, no persist
python -m src.cli judge <run_id>                       # judge a stored run (run-row fact sheet)
python -m src.cli report <run_id>                      # render a stored run
python -m src.cli runs [client]                        # list stored runs
python -m src.cli compare <before> <after>             # cadence diff
python -m src.cli discover <run_id>                    # unnamed-competitor discovery
python -m src.cli technical <domain>                   # Cat 1 checks
python -m src.cli roadmap <rubric.json> --brand X      # §4/§5 rollup
python -m src.cli calibrate <gold.json>                # judge vs gold set (isolated cache)
python -m src.cli verify <canary|determinism|shuffle>  # isolation/determinism probes
python -m src.cli due <client>                         # cadence re-run check
```

API: `./run-api.sh`; key endpoints `POST /audits`, `GET /audits/{id}/report`,
`POST /audits/{id}/judge` (re-judge through the cache), `GET
/audits/{id}/judge-status` (warm counts). Web: `cd web && npm run dev`.
Teaser/audit deliverable: `cd teaser && npm run audit -- <run_id>` (see
`docs/auditGenerator.md`).

## Configuration (src/config/settings.py — the only os.getenv site)

- **Keys:** `OPENAI/ANTHROPIC/PERPLEXITY/GEMINI_API_KEY`, `SUPABASE_URL/KEY`,
  `SEARCHAPI_API_KEY` (AI Overviews), `SERPER_API_KEY`, `REDDIT_CLIENT_ID/
  SECRET`, `DATAFORSEO_LOGIN/PASSWORD` (offsite research).
- **Engine determinism/throughput:** `ENGINE_TEMPERATURE=0`, `ENGINE_SEED=42`,
  `ENGINE_TIMEOUT_SECONDS=60`, `ENGINE_MAX_RETRIES=2`, `ENGINE_CONCURRENCY=12`,
  `ENGINE_PROVIDER_CONCURRENCY=4`, `RUNS_PER_QUERY=5`, `PAYLOAD_LOG_PATH`.
  Changing determinism knobs changes what a "run" means — don't, casually.
- **Judge:** `JUDGE_MODEL` (held-constant Sonnet — changing it invalidates the
  cache and breaks comparability with prior runs), `JUDGE_CASCADE`,
  `JUDGE_VERIFY`, `JUDGE_STRUCTURAL/ACCURACY/VERIFIER_MODEL`,
  `JUDGE_CACHE_BACKEND` (supabase|memory|none), `RUN_CONTENT_JUDGE` (default
  off), `OFFSITE_AGENT_MODEL`.
- **Budget/API limits:** `MAX_AUDIT_COST_USD=25`, `MAX_TOTAL_SPEND_USD=200`,
  `MAX_QUERIES=200`, `MAX_ENGINES=8`, `MAX_RUNS_PER_QUERY=5`,
  `GEO_API_KEY`, `GEO_CORS_ORIGINS`.

## Storage rules

Create-only lifecycle: audits/teasers never delete rows. The one hard-delete
path is explicit project deletion — delete the gzipped HTML blobs in the
`site-audit-html` bucket first (rows still point at them), then the rows
(children cascade). No soft delete exists; `archived_at` is a vestigial no-op
filter — don't build on it. SQL schemas live in `data/schema_*.sql`.

## Docs map (docs/ — trust levels)

**Live references:** `subscription-judge-plan.md` (prejudge design, shipped),
`auditGenerator.md` (paid deliverable, built), `judge-accuracy-plan.md`
(cascade/verify, built), `fact-sheet-template.md` + `labeling-guide.md` +
`grade-calibration-guide.md` (how client sheets and gold labels get made),
`project-queue.md` (living what's-left snapshot), `build-log.md` (append-only
history; has drifted — resume it with milestone entries).

**Historical / superseded — read for context, don't follow:** `claude.md` (the
original Phase-1 build guide; its file map and 12-chunk plan no longer match
the code), `left.md`, `ui-plan.md`, `site-audit-*-plan/guide.md`,
`isolation-determinism-plan.md`, `query-generation-plan.md`,
`showcase-session-core-build.md` (curated transcript).

**Per-client artifacts:** `fact-sheet-*.md`, `*-labeling-sheet.md`,
`grade-sheet-*.md`, `fort-competitors.md`, `answers.md`, `report.md` (Oura
run exports).

## Code conventions and the validation loop

Every change passes: `mypy src/` (strict) → `ruff check src/` → run it →
`pytest tests/`. Conventions: type hints on all signatures, `from __future__
import annotations`, TypedDicts/dataclasses across boundaries, named imports,
no swallowed exceptions (log or re-raise), loud `NotImplementedError` over dead
branches, no `# type: ignore` without a same-line reason, never log secrets or
row values (log exception types). Tests are `tests/test_<module>.py`; when you
change judge prompts or the workflow scripts, run `tests/test_judge.py` and
the prejudge tests first — they're the tripwire for the cache-key invariants.
