# GEO Teaser Auto

Turns a prospect's **website URL** into a reviewable **teaser** showing that AI engines
recommend a competitor and leave the prospect out on their buyers' questions.

This is a thin layer over the **geoPromptRunner** measurement platform (which runs the
queries, judges the answers, and computes the losing-queries / accuracy findings). See
[BUILD_PLAN.md](./BUILD_PLAN.md) for the full architecture and roadmap.

> **Status.** Every external service is behind an interface with a **Mock**, so
> the whole flow runs **with zero credentials** (synthetic findings). The
> **platform adapter is now wired**: set `GEO_PLATFORM_URL` and the teaser runs
> real audits against geoPromptRunner (see *Connecting to the real platform*).
> The resolver and query-set generator are still mocks — drop their real adapters
> in the same way (see *Swapping in real adapters*).

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
  resolver/     Resolver interface + MockResolver           (URL → company profile)
  queryset/     QuerySetGenerator interface + Mock          (profile → buyer queries)
  platform/     PlatformClient interface + MockPlatformClient + csv.ts (audit input)
  select/       selectFindings.ts (REAL ranking logic) + entity.ts
  render/       copy.ts, proofCard.ts, template.ts (HTML one-pager), pdf.ts (stub)
  pipeline.ts   orchestration (deps injected)
  config.ts     wires Mock adapters today; real adapters drop in here
  cli.ts        URL → draft teaser on disk
tests/          selectFindings + end-to-end pipeline (all mock, no network)
```

## Swapping in real adapters

Each Mock implements the same interface as its eventual real counterpart. Wire the
real one in `src/config.ts`, gated by an env var — nothing else changes:

| Mock | Real (later) | Trigger |
|---|---|---|
| `MockPlatformClient` | `HttpPlatformClient` ✅ wired (calls the FastAPI `/audits` endpoints) | `GEO_PLATFORM_URL` (+ `GEO_PLATFORM_API_KEY` if the platform sets `GEO_API_KEY`) |
| `MockResolver` | Firecrawl/Jina + Claude | `FIRECRAWL_API_KEY` + `ANTHROPIC_API_KEY` |
| `MockQuerySetGenerator` | Claude, using the methodology rules as the spec | `ANTHROPIC_API_KEY` |
| `renderPdf` stub | Playwright/Puppeteer print-to-PDF | install `playwright` |

The selector, copy, proof card, template, and pipeline are real and adapter-agnostic.
