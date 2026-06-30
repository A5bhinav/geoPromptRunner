# Running the Judge on the Claude Subscription (instead of the API)

**Status:** BUILT (2026-06-29). Single-judge path shipped end-to-end.
**Date:** 2026-06-28 (decided) / 2026-06-29 (built)

## What shipped (2026-06-29)

- `scripts/judge_via_workflow.py` — `dump` (DB pull + exact cache-key computation,
  fact sheet taken from `audit_runs.fact_sheet` by default, skips already-cached
  answers) and `inject` (writes the workflow's verdicts into `judge_cache.sqlite`).
  Refuses cascade/verify (different keyspace) loudly.
- `scripts/prejudge_workflow.js` — the Workflow: one subscription subagent per
  unique answer, forced to the `record_judgment` schema; returns verdicts.
- `.claude/skills/prejudge/SKILL.md` — `/prejudge <run_id>` chains dump → Workflow
  → inject.
- `src/cli.py` — `runs` now lists ALL recent runs (no client arg) so you can find a
  run_id; shows id/date/client/query-set/[fact-sheet].
- `src/api/runner.py` + `app.py` — `rejudge_run()` and `POST /audits/{id}/judge`:
  re-judge a stored run through the (now-warm) cache for $0, invalidating the
  report cache. Works in-memory or from storage.
- `web/` — a "Judge" / "Re-judge" button on the report with a "pre-judge on the
  subscription first" hint.

Key invariant verified: the keys `dump` emits are byte-identical to what a live
`Judge()` computes (single-judge, with the stored fact sheet), so the UI/CLI judge
hits them. Scope is the single judge only (the default config).

## The problem

Iterating on the pipeline burns real API credit fast (~$40 spent on testing alone).
Most of that spend falls into two buckets that should be treated differently:

1. **Engine queries** (`openai_engine`, `gemini_engine`, `perplexity_engine`, and the
   Anthropic *measurement* engines) — these MUST hit the real APIs. Asking "does
   Claude/GPT/Gemini recommend my client?" means querying the actual model. This is
   the measurement itself; it cannot move off the API.
2. **The evaluation layer** — `judge.py`, plus `content_judge.py`, `offsite/agent.py`,
   and teaser/audit generation. These are *our* calls using Claude as a tool, not
   measuring it. This layer CAN run on the Max subscription instead of the API.

## The decision

**Scope:** Just the judge (`src/pipeline/judge.py`) first. Biggest, cleanest single win.

**Calibration:** Testing only. These subscription-produced verdicts are for dev/testing
iteration. The held-constant judge model does NOT matter here, so we maximize savings.
**Do not** let these verdicts feed calibration / gold-labeling work — that path keeps
using the held-constant API judge (`claude-sonnet-4-5`, `temperature=0`).

## Why the judge is the ideal candidate

The judge is already architected as a **separate offline pass over stored answers** with
a **persistent, content-addressed cache** (`data/judge_cache.sqlite`). The cache key is a
deterministic hash of `(model, prompt_fingerprint, client, competitors, fact_sheet,
prompt, answer)` — see `src/pipeline/judge_cache.py:51`.

The pipeline already checks the cache first and only calls the API on a miss
(`src/pipeline/judge.py:429`). So:

> If we pre-fill `judge_cache.sqlite` with verdicts produced on the **Max subscription**
> (via a Claude Code workflow), then a normal `python -m src.cli judge <run_id>` becomes
> **100% cache hits → $0 API**. No pipeline change required.

## The plan (the "workflow")

1. A script pulls the unique `(prompt, answer)` pairs for a run from the DB, plus the
   client / competitors / fact-sheet.
2. A **Workflow** fans out subagents — one per unique answer — each judging with the
   *exact same* system prompt + `record_judgment` tool schema and accuracy rules from
   `judge.py`, returning structured JSON. These agents run on the subscription, not the API.
3. The script computes the real cache key (reproducing `prompt_fingerprint` and
   `JUDGE_MODEL` exactly) and writes each verdict into `judge_cache.sqlite`.
4. Run `judge` as normal → all cache hits → free.

Likely shape: a `scripts/judge_via_workflow.py` (DB pull + cache injection) plus the
workflow itself, scoped to the judge only.

## Caveats (accepted for the testing-only scope)

- **Not byte-identical to the Sonnet temp-0 judge.** The API judge is held constant at
  `temperature=0` on `claude-sonnet-4-5`. Subscription subagents run a different model
  (Opus) and aren't temp-0-pinnable. Fine for dev iteration (often *higher* quality);
  NOT for calibration/gold, where a held-constant judge is the whole point.
- **Batch/offline, not inline.** Good for the testing loop, not for live customer latency.
- **ToS / scale.** Fine for internal development and testing. For *paid client
  deliverables*, the API is the supported path and is a real cost-of-goods to price in.
  Subscription for iteration, API for the final billable run.

## Alternative considered (not chosen)

A judge backend that shells out to the `claude` CLI (Agent SDK, uses subscription login)
so it works inline. Rejected for now: slower and worse at forced structured output than
the batch-workflow approach.

## Out of scope (for now)

- `content_judge.py` (site-audit content scoring)
- `offsite/agent.py` (offsite authority agent)
- teaser / audit generation

These could be routed the same way later, but they're more integrated. Judge first.
