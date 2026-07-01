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
//   { repo, in_path, batches, concurrency, start, limit, batch }
//     repo        — absolute repo root (so subagents run the script from the right cwd)
//     in_path     — the dump's in.json on disk (absolute)
//     batches     — token-balanced batch plan from `judge_via_workflow.py plan`:
//                   [{start, count}, ...]. PREFERRED — one subagent per entry, so long
//                   answers get small batches and short ones get packed together.
//     concurrency — max subagents in flight at once (default 4). Batches run in waves
//                   of this size so a big run doesn't slam the subscription rate limit.
//     start/limit/batch — fallback fixed chunking when `batches` is omitted: judge
//                   items start..start+limit-1 in fixed groups of `batch` (default 8).
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
const concurrency = Math.max(1, Number(A.concurrency ?? 4))
const schema = SCHEMA

// The batches to judge and the item range they cover. Prefer the token-balanced
// plan from `plan`; otherwise fall back to fixed-size chunking of [start, start+limit).
let chunks
let rangeStart
let rangeLen
if (Array.isArray(A.batches) && A.batches.length) {
  chunks = A.batches.map((b) => ({ s: Number(b.start), n: Number(b.count) })).filter((c) => c.n > 0)
  rangeStart = chunks.reduce((mn, c) => Math.min(mn, c.s), chunks[0].s)
  rangeLen = chunks.reduce((mx, c) => Math.max(mx, c.s + c.n), rangeStart) - rangeStart
} else {
  const start = Number(A.start ?? 0)
  const limit = Number(A.limit ?? 0)
  const batchSize = Math.max(1, Number(A.batch ?? 8))
  chunks = []
  for (let s = start; s < start + limit; s += batchSize) {
    chunks.push({ s, n: Math.min(batchSize, start + limit - s) })
  }
  rangeStart = start
  rangeLen = limit
}

phase('Judge')
log(
  `Judging ${rangeLen} answer(s) of ${inPath} in ${chunks.length} batch(es), ` +
    `${concurrency} at a time on the subscription`,
)

// One judging subagent for a batch of `n` answers starting at global index `s`.
// Retries on a null/empty result up to MAX_TRIES — the safety net for a subagent
// that died on a transient subscription throttle (the wave concurrency cap below is
// what mostly PREVENTS throttling; this catches the occasional straggler that slips
// through). Returns the verdicts array, or null if every try failed (those items
// stay un-cached and are re-judged on a later pass).
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

// Scatter verdicts into a dense array aligned to items[rangeStart .. rangeStart+rangeLen):
// raws[j] is the verdict for global item index rangeStart+j (null = not judged). Each
// verdict is placed by its own reported ITEM `index`, so a batch that returns items out
// of order still lands correctly; the `index` tag is dropped (inject wants only the raw
// shape). Any position left null (failed/dropped) stays un-cached and is re-judged later.
const raws = new Array(rangeLen).fill(null)
const scatter = (verdicts) => {
  if (!verdicts) return
  for (const v of verdicts) {
    if (!v || typeof v !== 'object') continue
    const gi = Number(v.index)
    const pos = gi - rangeStart
    if (!Number.isInteger(gi) || pos < 0 || pos >= rangeLen) continue
    raws[pos] = { brands: v.brands, client_accuracy_flags: v.client_accuracy_flags }
  }
}

// Run the batches in WAVES of `concurrency` so at most that many subagents are ever in
// flight — this paces requests so a large run doesn't trip the subscription rate limit.
// (parallel() itself is also capped by the harness, but we throttle below that on purpose.)
for (let w = 0; w < chunks.length; w += concurrency) {
  const wave = chunks.slice(w, w + concurrency)
  const waveResults = await parallel(wave.map((c) => () => judgeBatch(c)))
  waveResults.forEach(scatter)
  log(
    `Wave ${w / concurrency + 1}/${Math.ceil(chunks.length / concurrency)} done — ` +
      `${raws.filter(Boolean).length}/${rangeLen} judged so far`,
  )
}

return { start: rangeStart, raws }
