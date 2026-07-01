// Pre-judge an audit run on the Claude subscription.
//
// Scales to runs with hundreds of long answers: the answer text never flows
// through args or the return value — it lives in an on-disk file that the Python
// helper wrote (`judge_via_workflow.py dump`). Each subagent fetches ONLY its own
// item from that file by index, so args stays tiny.
//
// Input (args):
//   { repo, in_path, start, limit }
//     repo    — absolute repo root (so subagents run the script from the right cwd)
//     in_path — the dump's in.json on disk (absolute)
//     start   — first item index this run judges
//     limit   — how many items to judge (start .. start+limit-1)
//
// Output (return value, fed to `judge_via_workflow.py inject --offset <start>`):
//   { start, raws: [ {brands, client_accuracy_flags} | null, ... ] }
//   One entry per item in index order (null = that subagent failed). `inject`
//   re-attaches the cache key from in.json by index, so subagents never touch keys.
//
// The subagents run on the session's auth (the Max subscription), so this whole
// pass costs subscription quota, not API credit. See docs/subscription-judge-plan.md.

export const meta = {
  name: 'prejudge',
  description: 'Judge stored audit answers on the subscription to pre-fill the judge cache',
  phases: [{ title: 'Judge', detail: 'one subagent per unique answer' }],
}

// The forced output shape for each judging subagent — the record_judgment tool's
// input schema from src/pipeline/judge.py (_judgment_tool). Hardcoded so the
// Workflow args stay tiny; keep the enums in sync with the Python Prominence /
// Framing / AccuracyFlagType / Severity types if those ever change.
const SCHEMA = {
  type: 'object',
  properties: {
    brands: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          brand: { type: 'string' },
          present: { type: 'boolean' },
          prominence: {
            type: 'string',
            enum: ['recommended_first', 'mid_pack', 'buried', 'also_ran', 'absent'],
          },
          framing: { type: 'string', enum: ['positive', 'neutral', 'negative'] },
        },
        required: ['brand', 'present', 'prominence', 'framing'],
      },
    },
    client_accuracy_flags: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          type: {
            type: 'string',
            enum: ['wrong_pricing', 'missing_or_invented_feature', 'competitor_confusion', 'identity', 'stale'],
          },
          claim: { type: 'string' },
          reality: { type: 'string' },
          severity: { type: 'string', enum: ['high', 'med', 'low'] },
        },
        required: ['type', 'claim', 'reality', 'severity'],
      },
    },
  },
  required: ['brands', 'client_accuracy_flags'],
}

// args may arrive already-parsed (an object) or as a JSON string depending on how
// the Workflow was invoked — accept both.
const A = typeof args === 'string' ? JSON.parse(args) : args || {}
const repo = A.repo
const inPath = A.in_path
const start = Number(A.start ?? 0)
const limit = Number(A.limit ?? 0)
const schema = SCHEMA

const idxs = []
for (let i = start; i < start + limit; i++) idxs.push(i)

phase('Judge')
log(`Judging items ${start}..${start + limit - 1} of ${inPath} on the subscription`)

// One judging subagent for item `i`. Retries on a null result (a subagent that
// died on a transient subscription throttle) up to MAX_TRIES; by the time a retry
// runs the concurrency pool has cycled, so the server-side rate limit has usually
// passed. A persistent null (all tries failed) stays null and is re-judged on a
// later pass.
const MAX_TRIES = 3
const judgeItem = async (i) => {
  for (let t = 0; t < MAX_TRIES; t++) {
    const r = await agent(
      `You are a strict evaluator scoring ONE AI answer for a GEO audit, running on ` +
        `the Claude subscription.\n\n` +
        `STEP 1 — fetch your task by running this command EXACTLY (it must run from ` +
        `the repo root and use the project venv python):\n` +
        `  cd ${repo} && .venv/bin/python -m scripts.judge_via_workflow item ${inPath} ${i}\n` +
        `It prints a JSON object {"prompt": "..."}.\n\n` +
        `STEP 2 — the "prompt" field is a complete, self-contained judging ` +
        `instruction (a system preamble, the question, the AI answer, the brands to ` +
        `score, and — if present — a client fact sheet with strict accuracy rules). ` +
        `Read it and follow it EXACTLY. Use NO outside knowledge about the brands.\n\n` +
        `STEP 3 — return your judgment as the structured output: a "brands" entry for ` +
        `every brand the prompt lists (present / prominence / framing) and ` +
        `"client_accuracy_flags" (an empty list if none apply, or if the prompt ` +
        `included no fact sheet).`,
      { label: t === 0 ? `judge:${i}` : `judge:${i}#retry${t}`, phase: 'Judge', schema },
    )
    if (r) return r
  }
  return null
}

const raws = await parallel(idxs.map((i) => () => judgeItem(i)))

// parallel() preserves input order and yields null for any failed subagent, so
// raws[j] lines up with idxs[j] = start + j — exactly what inject expects.
log(`Judged ${raws.filter(Boolean).length}/${idxs.length} (nulls stay un-cached, re-judged later)`)

return { start, raws }
