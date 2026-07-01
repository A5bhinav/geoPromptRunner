---
name: prejudge
description: Pre-fill the judge cache for a stored audit run using the Claude subscription (free) instead of the API, so a later `judge` pass is 100% cache hits. Use when the user wants to judge a run without spending API credit — e.g. "prejudge <run_id>", "judge run X on the subscription", "warm the judge cache for X". Requires a session logged into the Max subscription (not an API-key-billed session).
---

# Prejudge a run on the subscription

Judge a stored run's answers using **subscription** subagents (a Workflow), writing
the verdicts into the same `data/judge_cache.sqlite` the CLI and UI judge read. The
later judge step then finds every verdict already cached → **$0 API**. Background:
`docs/subscription-judge-plan.md`.

This only works in a session running on the **Max subscription**. If this session is
billed via `ANTHROPIC_API_KEY`, the subagents spend credit and there is no saving —
say so and stop.

## Inputs

- `<run_id>` (required) — the stored audit run to judge. If the user doesn't have
  one, run `python -m src.cli runs` to list recent runs and their ids.
- `--fact-sheet <path>` (optional) — **rarely needed**. By default `dump` uses the
  fact sheet stored on the run row (`audit_runs.fact_sheet`), which is exactly what
  the CLI/UI judge keys off — so the cache keys match automatically. Only pass this
  to deliberately judge against a *different* sheet; a path that differs from the
  stored one produces keys the real judge never looks up.

## Scope

This replicates the **single judge** (`Judge()` with no cascade/verify), the default
config. The `dump` step refuses to run if `JUDGE_CASCADE`/`JUDGE_VERIFY` are set,
because those use a different cache keyspace the Workflow's verdicts would never be
read from. Do not work around that error.

## How it scales (and stays cheap on tokens)

Two things keep the token cost down on big runs:

1. The answer text (a real run is multiple MB) NEVER passes through the Workflow's
   args or return — it stays in the on-disk `in.json` the dump writes. The args carry
   only `{repo, in_path, start, limit, batch}`.
2. Answers are judged in **batches**: one subagent judges up to `batch` answers (default
   8) in a single call, fetching them off disk via the `batch` subcommand. The large
   judging rubric (brand rules + accuracy block + fact sheet — identical for every
   answer in a run) is sent **once per batch** instead of once per answer, and there
   are ~`batch`× fewer subagents to spin up. Fanning out one subagent per answer used
   to pay both of those costs N times; batching is the fix.

Each subagent returns only its small verdicts (tagged with each answer's item index),
so the return value stays tiny. This is why it works on 500+ answer runs.

## Steps

Run these in order. Use the session scratchpad for the intermediate JSON files, and
always use ABSOLUTE paths (subagents run from the repo root via the venv python).

1. **Dump** the input file (DB pull + cache-key computation; skips already-cached
   answers):
   ```
   python -m scripts.judge_via_workflow dump <run_id> --out <SCRATCH>/<run>.in.json
   ```
   (The fact sheet is taken from the run row automatically; add `--fact-sheet <path>`
   only to override it. The command prints which fact sheet it used and the item count.)
   If it prints "Nothing to judge", the cache is already warm — stop and tell the user.

2. **Plan** the batches — group answers into token-balanced batches (long answers get
   small batches, short ones get packed), so no subagent gets an oversized context:
   ```
   python -m scripts.judge_via_workflow plan <SCRATCH>/<run>.in.json --budget 10000 --max-items 16
   ```
   It prints `{"batches": [{"start","count","tokens"}, ...], ...}`. `--budget` is the
   max per-answer token estimate per batch; `--max-items` caps answers per batch (so a
   run of tiny answers can't make one giant batch). Capture the `batches` array.

3. **Judge** via the Workflow — one subscription subagent per batch, run in waves so the
   subscription isn't rate-limited:
   ```
   Workflow({ scriptPath: "scripts/prejudge_workflow.js",
              args: { repo: "<abs repo root>", in_path: "<abs SCRATCH>/<run>.in.json",
                      batches: <batches array from plan>, concurrency: 4 } })
   ```
   `concurrency` (default 4) is the max subagents in flight at once — lower it if you
   still see throttling. It returns `{ start, raws: [ {brands, client_accuracy_flags} |
   null, ... ] }` — one verdict per item in index order over the planned range (null =
   not judged; harmless, re-judged later). `start` is the first item index covered; use
   it as `--offset` when injecting.
   (Fallback: omit `batches` and pass `start`, `limit`, `batch` for fixed-size chunking.)

4. **Write** the Workflow's returned object verbatim to `<SCRATCH>/<run>.raws.json`.

5. **Inject** the verdicts into the cache (keys are taken from the in file by index, so
   they always match what the real judge looks up). Use the `start` the Workflow
   returned as `--offset`:
   ```
   python -m scripts.judge_via_workflow inject <SCRATCH>/<run>.in.json <SCRATCH>/<run>.raws.json --offset <start>
   ```

6. **Report**: how many verdicts were injected, and that the user can now run
   `python -m src.cli judge <run_id>` or click **Judge** in the UI — free cache hits.
   The "API judge passover" runs but never calls the API.

## Part 2 — also warm the on-site content checks (if the run was crawled)

The site audit's subjective Cat 3/4 checks (`ContentJudge`) have their own notebook
(`content_judge_cache`). If this run has crawled pages, warm them too so a later
`run_site_audit` / report is also free. Same shape, a sibling script + workflow:

1. **Dump** the crawled pages (reads `site_audit_page` from Supabase, skips cached):
   ```
   python -m scripts.content_judge_via_workflow dump <run_id> --out <SCRATCH>/<run>.content.in.json
   ```
   If it prints "Nothing to judge", the content cache is warm (or nothing was crawled) — skip.
2. **Count** the pages (for the Workflow arg):
   ```
   python -m scripts.content_judge_via_workflow header <SCRATCH>/<run>.content.in.json
   ```
3. **Judge** via the content Workflow — one subscription subagent per page, in waves:
   ```
   Workflow({ scriptPath: "scripts/content_prejudge_workflow.js",
              args: { repo: "<abs repo root>", in_path: "<abs SCRATCH>/<run>.content.in.json",
                      page_count: <page_count from header>, concurrency: 4 } })
   ```
   It returns `{ pages: [ {page_index, verdicts:[...]} | null, ... ] }`.
4. **Write** that object to `<SCRATCH>/<run>.content.raws.json`, then **inject**:
   ```
   python -m scripts.content_judge_via_workflow inject <SCRATCH>/<run>.content.in.json <SCRATCH>/<run>.content.raws.json
   ```
   Now the site audit's content checks are warm — `run_site_audit` reuses them for $0.
   (Offsite research stays on the API by design — it's a live, non-deterministic agent.)

## Notes

- These verdicts are for **dev/testing iteration only**. They come from a different
  model (Opus, not temp-0 Sonnet) and must **never** feed calibration/gold labeling —
  that path keeps the held-constant API judge. (See `docs/subscription-judge-plan.md`.)
- Engine queries (collecting the answers) still cost real API money; only the judge
  layer moves onto the subscription. So the normal flow is: run the audit with the
  judge **off** to collect answers → `/prejudge <run_id>` → judge for free.
