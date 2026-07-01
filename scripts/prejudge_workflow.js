// Pre-judge an audit run on the Claude subscription.
//
// Scales to runs with hundreds of long answers on two axes:
//   1. The answer text never flows through args or the return value — it lives in
//      an on-disk file the Python helper wrote (`judge_via_workflow.py dump`).
//   2. Answers are judged in BATCHES: one subagent judges up to `batch` answers in
//      a single call, and the large judging rubric (brand rules + accuracy block +
//      fact sheet — identical for every answer in a run) is sent ONCE per batch
//      instead of once per answer. That cuts both the per-subagent scaffolding
//      (fewer subagents) and the repeated-rubric tokens (one copy per batch), which
//      is what made one-subagent-per-answer so expensive.
//
// Input (args):
//   { repo, in_path, start, limit, batch }
//     repo    — absolute repo root (so subagents run the script from the right cwd)
//     in_path — the dump's in.json on disk (absolute)
//     start   — first item index this run judges
//     limit   — how many items to judge (start .. start+limit-1)
//     batch   — answers per subagent (default 8). Bigger = fewer tokens but longer
//               per-subagent context; keep moderate so items don't bleed together.
//
// Output (return value, fed to `judge_via_workflow.py inject --offset <start>`):
//   { start, raws: [ {brands, client_accuracy_flags} | null, ... ] }
//   One entry per item in index order over [start, start+limit) (null = not judged).
//   `inject` re-attaches the cache key from in.json by index, so subagents never
//   touch keys. Verdicts come back tagged with their global ITEM index and are
//   scattered into this dense array by that index — robust to a batch reordering.
//
// The subagents run on the session's auth (the Max subscription), so this whole
// pass costs subscription quota, not API credit. See docs/subscription-judge-plan.md.

export const meta = {
  name: 'prejudge',
  description: 'Judge stored audit answers on the subscription to pre-fill the judge cache',
  phases: [{ title: 'Judge', detail: 'one subagent per batch of answers' }],
}

// The forced output shape for each judging subagent: a `verdicts` array (one entry
// per ITEM in the batch), each entry the record_judgment shape from
// src/pipeline/judge.py (_judgment_tool) PLUS the ITEM `index`. Hardcoded so the
// Workflow args stay tiny; keep the enums in sync with the Python Prominence /
// Framing / AccuracyFlagType / Severity types if those ever change. (This mirrors
// judge_via_workflow.py `_batch_schema()`, which wraps the same tool schema.)
const VERDICT_PROPS = {
  index: { type: 'integer' },
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
}
const SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: { type: 'object', properties: VERDICT_PROPS, required: ['index', 'brands', 'client_accuracy_flags'] },
    },
  },
  required: ['verdicts'],
}

// args may arrive already-parsed (an object) or as a JSON string depending on how
// the Workflow was invoked — accept both.
const A = typeof args === 'string' ? JSON.parse(args) : args || {}
const repo = A.repo
const inPath = A.in_path
const start = Number(A.start ?? 0)
const limit = Number(A.limit ?? 0)
const batchSize = Math.max(1, Number(A.batch ?? 8))
const schema = SCHEMA

// Split [start, start+limit) into contiguous batches of `batchSize`.
const chunks = []
for (let s = start; s < start + limit; s += batchSize) {
  chunks.push({ s, n: Math.min(batchSize, start + limit - s) })
}

phase('Judge')
log(
  `Judging items ${start}..${start + limit - 1} of ${inPath} in ${chunks.length} batch(es) ` +
    `of up to ${batchSize} on the subscription`,
)

// One judging subagent for a batch of `n` answers starting at global index `s`.
// Retries on a null/empty result (a subagent that died on a transient subscription
// throttle) up to MAX_TRIES; by the time a retry runs the concurrency pool has
// cycled, so the server-side rate limit has usually passed. Returns the verdicts
// array, or null if every try failed (those items stay un-cached, re-judged later).
const MAX_TRIES = 3
const judgeBatch = async ({ s, n }) => {
  for (let t = 0; t < MAX_TRIES; t++) {
    const r = await agent(
      `You are a strict evaluator scoring AI answers for a GEO audit, running on the ` +
        `Claude subscription.\n\n` +
        `STEP 1 — fetch your batch by running this command EXACTLY (it must run from ` +
        `the repo root and use the project venv python):\n` +
        `  cd ${repo} && .venv/bin/python -m scripts.judge_via_workflow batch ${inPath} ${s} ${n}\n` +
        `It prints a JSON object {"prompt": "...", "indices": [...]}.\n\n` +
        `STEP 2 — the "prompt" field contains a SHARED RUBRIC followed by ${n} AI ` +
        `answer(s), each under a "===== ITEM <index> =====" header. Judge EACH item ` +
        `INDEPENDENTLY, using ONLY that item's own answer text plus the shared rubric. ` +
        `Use NO outside knowledge about the brands, and never let one item's answer ` +
        `influence another.\n\n` +
        `STEP 3 — return your judgments as the structured output: a "verdicts" array ` +
        `with exactly ONE entry per ITEM shown (there are ${n}). Each entry carries ` +
        `that ITEM's "index" (the number in its header), a "brands" entry for every ` +
        `brand the rubric lists (present / prominence / framing), and ` +
        `"client_accuracy_flags" (an empty list if none apply, or if the rubric ` +
        `included no fact sheet). Do not merge, drop, or skip any item.`,
      { label: t === 0 ? `judge:${s}-${s + n - 1}` : `judge:${s}-${s + n - 1}#retry${t}`, phase: 'Judge', schema },
    )
    if (r && Array.isArray(r.verdicts) && r.verdicts.length) return r.verdicts
  }
  return null
}

const batchResults = await parallel(chunks.map((c) => () => judgeBatch(c)))

// Scatter verdicts into a dense array aligned to items[start .. start+limit): raws[j]
// is the verdict for global item index start+j (null = not judged). Each verdict is
// placed by its own reported ITEM `index`, so a batch that returns items out of order
// still lands correctly; the `index` tag is dropped (inject wants only the raw shape).
const raws = new Array(limit).fill(null)
for (const verdicts of batchResults) {
  if (!verdicts) continue
  for (const v of verdicts) {
    if (!v || typeof v !== 'object') continue
    const gi = Number(v.index)
    const pos = gi - start
    if (!Number.isInteger(gi) || pos < 0 || pos >= limit) continue
    raws[pos] = { brands: v.brands, client_accuracy_flags: v.client_accuracy_flags }
  }
}

log(`Judged ${raws.filter(Boolean).length}/${limit} (nulls stay un-cached, re-judged later)`)

return { start, raws }
