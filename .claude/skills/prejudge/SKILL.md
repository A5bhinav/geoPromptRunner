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

## How it scales

The answer text (a real run is multiple MB) NEVER passes through the Workflow's args
or return — it stays in the on-disk `in.json` the dump writes. The Workflow's args
carry only `{repo, in_path, start, limit}`; each subagent fetches just its own item
off disk via the `item` subcommand, and returns only its small verdict. This is why
it works on 500+ answer runs.

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

2. **Judge** via the Workflow — fan out one subscription subagent per answer:
   ```
   Workflow({ scriptPath: "scripts/prejudge_workflow.js",
              args: { repo: "<abs repo root>", in_path: "<abs SCRATCH>/<run>.in.json",
                      start: 0, limit: <item count from dump> } })
   ```
   It returns `{ start, raws: [ {brands, client_accuracy_flags} | null, ... ] }` — one
   verdict per item in order (null = that subagent failed; harmless, re-judged later).
   For very large runs you may split into batches by `start`/`limit`; inject each with
   the matching `--offset`.

3. **Write** the Workflow's returned object verbatim to `<SCRATCH>/<run>.raws.json`.

4. **Inject** the verdicts into the cache (keys are taken from the in file by index, so
   they always match what the real judge looks up):
   ```
   python -m scripts.judge_via_workflow inject <SCRATCH>/<run>.in.json <SCRATCH>/<run>.raws.json --offset <start>
   ```

5. **Report**: how many verdicts were injected, and that the user can now run
   `python -m src.cli judge <run_id>` or click **Judge** in the UI — free cache hits.
   The "API judge passover" runs but never calls the API.

## Notes

- These verdicts are for **dev/testing iteration only**. They come from a different
  model (Opus, not temp-0 Sonnet) and must **never** feed calibration/gold labeling —
  that path keeps the held-constant API judge. (See `docs/subscription-judge-plan.md`.)
- Engine queries (collecting the answers) still cost real API money; only the judge
  layer moves onto the subscription. So the normal flow is: run the audit with the
  judge **off** to collect answers → `/prejudge <run_id>` → judge for free.
