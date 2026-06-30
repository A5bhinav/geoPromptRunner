# GEO Teaser Auto

Turns a prospect's **website URL** into a reviewable **teaser** showing that AI engines
recommend a competitor and leave the prospect out on their buyers' questions.

This is a thin layer over the **geoPromptRunner** measurement platform (which runs the
queries, judges the answers, and computes the losing-queries / accuracy findings). See
[BUILD_PLAN.md](./BUILD_PLAN.md) for the full architecture and roadmap.

> **Status.** Every external service is behind an interface with a **Mock**, so
> the whole flow runs **with zero credentials** (synthetic findings). All
> real adapters are now **wired** behind env gates: the **platform adapter**
> (`GEO_PLATFORM_URL`), the **resolver** (direct HTTP fetch + Claude with just
> `ANTHROPIC_API_KEY` — no Docker; or crawl4ai for JS-heavy sites when
> `CRAWL4AI_BASE_URL` is set), and the **query-set generator** (Claude —
> `ANTHROPIC_API_KEY`). Unset env falls back to the mock for each (see *Swapping
> in real adapters*).

## Requirements

- Node ≥ 22 (developed on 25). TypeScript runs directly — no build step.

## Run

```bash
npm install
npm run teaser -- https://www.example.com          # writes out/<slug>.html + .json
npm run teaser -- https://www.example.com --out dir # custom output dir
npm test                                            # unit + end-to-end (mock) tests
npm run typecheck
```

Open the generated `out/<slug>.html` to review the draft teaser. (PDF export is the
next step — `src/render/pdf.ts` is a documented stub.)

## Connecting to the real platform

By default the teaser uses `MockPlatformClient` (offline, synthetic findings).
Point it at a running geoPromptRunner API to run **real audits** instead:

```bash
# 1. Start the platform API (from the repo root):
./run-api.sh                         # serves http://localhost:8000

# 2. Run the teaser against it:
GEO_PLATFORM_URL=http://localhost:8000 npm run teaser -- https://www.example.com
```

When `GEO_PLATFORM_URL` is set, `config.ts` selects `HttpPlatformClient`, which
calls `POST /audits` (uploads the audit CSV), polls `GET /audits/{id}/status`,
then fetches `GET /audits/{id}/report` and `GET /audits/{id}/answers`.

- `GEO_PLATFORM_API_KEY` *(optional)* — sent as `X-API-Key`. Required when the
  platform has `GEO_API_KEY` configured (it returns 401 on data routes otherwise).
- `GEO_PLATFORM_TIMEOUT_MS` *(optional)* — per-request HTTP timeout (default: none).
- A printable finding needs **judge** detection, so the platform must have the
  engine + judge API keys configured (`OPENAI_API_KEY`, etc.); the teaser refuses
  to render from `regex`-mode reports. Default engines are
  `perplexity`, `google_ai_overviews`, `openai`.

## What it does (pipeline)

`URL → resolve company → generate query set → submit to platform → poll → fetch
report + verbatim answers → select lead finding + 2 → assemble draft teaser.`

Lifecycle and component detail: [BUILD_PLAN.md §1](./BUILD_PLAN.md).

## Layout

```
src/
  types/        platform.ts (mirrors geoPromptRunner's ReportPayload/answers), domain.ts
  llm/          claude.ts (thin @anthropic-ai/sdk wrapper: json_schema structured extraction)
  resolver/     Resolver + MockResolver + Crawl4aiClient + Crawl4aiClaudeResolver (URL → profile)
  queryset/     QuerySetGenerator + Mock + ClaudeQuerySetGenerator (profile → buyer queries)
  platform/     PlatformClient interface + MockPlatformClient + csv.ts (audit input)
  select/       selectFindings.ts (REAL ranking logic) + entity.ts
  render/       copy.ts, proofCard.ts, template.ts (HTML one-pager), pdf.ts (stub)
  pipeline.ts   orchestration (deps injected)
  config.ts     wires Mock or real adapters per env gate
  cli.ts        URL → draft teaser on disk
tests/          selectFindings + pipeline + querySetGenerator + resolver (all pure, no network)
```

## Swapping in real adapters

Each Mock implements the same interface as its real counterpart. The real
resolver and query-set generator are now **wired** in `src/config.ts`, gated by
env vars — nothing else changes:

| Mock | Real | Trigger |
|---|---|---|
| `MockPlatformClient` | `HttpPlatformClient` ✅ wired (calls the FastAPI `/audits` endpoints) | `GEO_PLATFORM_URL` (+ `GEO_PLATFORM_API_KEY` if the platform sets `GEO_API_KEY`) |
| `MockResolver` | `FetchClaudeResolver` ✅ wired (direct HTTP fetch → Claude extraction, no Docker) | `ANTHROPIC_API_KEY` |
| `MockResolver` | `Crawl4aiClaudeResolver` ✅ wired (crawl4ai markdown → Claude extraction; better for JS-heavy sites) | `CRAWL4AI_BASE_URL` (or `CRAWL4AI_API_TOKEN`) **and** `ANTHROPIC_API_KEY` |
| `MockQuerySetGenerator` | `ClaudeQuerySetGenerator` ✅ wired (Claude, with the methodology hard rules + deterministic repair) | `ANTHROPIC_API_KEY` |
| `renderPdf` stub | Playwright/Puppeteer print-to-PDF | install `playwright` |

The selector, copy, proof card, template, and pipeline are real and adapter-agnostic.

### Real resolver + query-set generator (crawl4ai + Claude)

```bash
# Self-hosted crawl4ai (image series 0.8.x), default port 11235:
docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:0.8.6

# Run the teaser with the real resolver + query generator:
CRAWL4AI_BASE_URL=http://localhost:11235 \
ANTHROPIC_API_KEY=sk-ant-...               \
npm run teaser -- https://www.example.com
```

Environment variables:

- `ANTHROPIC_API_KEY` *(required for both real adapters)* — the **same** key the
  platform uses; no separate key var is introduced. The resolver uses Claude to
  extract a `CompanyProfile` from the crawled markdown; the query-set generator
  uses Claude to draft the buyer queries. **The CLI auto-loads the repo-root
  `.env`** (`src/env.ts`), so the existing `ANTHROPIC_API_KEY` is picked up
  without exporting it or duplicating the secret — an already-exported value (or
  one injected by the web route's parent process) still takes precedence. A
  `teaser/.env`, if present, overrides the repo-root one.
- `TEASER_CLAUDE_MODEL` *(optional)* — the Claude model id, **separately
  configurable** from the key (default `claude-haiku-4-5`). Lets you point the
  teaser at a different model without touching the platform's own model config.
- `CRAWL4AI_BASE_URL` *(default `http://localhost:11235`)* — the self-hosted
  crawl4ai REST server. Its presence (with a Claude key) selects the real resolver.
- `CRAWL4AI_API_TOKEN` *(optional)* — sent as `Authorization: Bearer` **only when
  set** (the server binds loopback-only and needs no auth otherwise).

The resolver crawls the homepage (and best-effort one discovered pricing/
comparison page) for clean `fit_markdown`, then Claude extracts the name,
category, competitors (always returned **unconfirmed** — the human input gate
confirms them), client domains, and product claims. The query-set generator
prompts Claude with the methodology hard rules, then **validates and repairs the
output deterministically** (≥2 comparison queries that don't name the client;
client named only in the brand query; competitors named in comparison queries),
falling back to a template set if the LLM output is unusable.
