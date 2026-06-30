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

## Steps

Run these in order. Use the session scratchpad for the intermediate JSON files.

1. **Dump** the Workflow input (DB pull + cache-key computation; skips answers already
   cached):
   ```
   python -m scripts.judge_via_workflow dump <run_id> --out <SCRATCH>/prejudge_<run_id>.in.json
   ```
   (The fact sheet is taken from the run row automatically; add `--fact-sheet <path>`
   only to override it. The command prints which fact sheet it used.)
   If it prints "Nothing to judge", the cache is already warm — stop here and tell the
   user the run is ready to judge for free.

2. **Read** `<SCRATCH>/prejudge_<run_id>.in.json` and invoke the Workflow, passing the
   parsed JSON object as `args` (not a string):
   ```
   Workflow({ scriptPath: "scripts/prejudge_workflow.js", args: <the parsed JSON object> })
   ```
   The Workflow fans out one subscription subagent per answer and returns
   `{ run_id, client, competitors, has_fact_sheet, items: [{ key, raw }] }`.

3. **Write** the Workflow's returned object verbatim to
   `<SCRATCH>/prejudge_<run_id>.out.json`.

4. **Inject** the verdicts into the cache:
   ```
   python -m scripts.judge_via_workflow inject <SCRATCH>/prejudge_<run_id>.out.json
   ```

5. **Report**: tell the user how many verdicts were injected and that they can now run
   `python -m src.cli judge <run_id>` (or the UI judge step) — it will be free cache
   hits. The "API judge passover" runs but never calls the API.

## Notes

- These verdicts are for **dev/testing iteration only**. They come from a different
  model (Opus, not temp-0 Sonnet) and must **never** feed calibration/gold labeling —
  that path keeps the held-constant API judge. (See `docs/subscription-judge-plan.md`.)
- Engine queries (collecting the answers) still cost real API money; only the judge
  layer moves onto the subscription. So the normal flow is: run the audit with the
  judge **off** to collect answers → `/prejudge <run_id>` → judge for free.
