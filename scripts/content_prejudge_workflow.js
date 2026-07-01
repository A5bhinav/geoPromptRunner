// Pre-judge a run's on-site content checks on the Claude subscription.
//
// The site-audit sibling of prejudge_workflow.js. One subagent per PAGE: it fetches
// its page's combined judging prompt off disk (page text + all not-yet-cached checks,
// rendered once by `content_judge_via_workflow.py page`), judges every check, and
// returns one verdict per check. Page text never flows through args/return.
//
// Input (args):
//   { repo, in_path, page_count, concurrency }
//     repo        — absolute repo root
//     in_path     — the dump's in.json (absolute)
//     page_count  — number of pages in the dump (from `header`)
//     concurrency — max subagents in flight at once (default 4; waves pace the run)
//
// Output (fed to `content_judge_via_workflow.py inject`):
//   { pages: [ {page_index, verdicts: [{check_id, sub_answers:[...]}]} | null, ... ] }

export const meta = {
  name: 'content-prejudge',
  description: 'Judge stored crawled pages on the subscription to fill the content notebook',
  phases: [{ title: 'Judge', detail: 'one subagent per page' }],
}

// Forced output shape per page subagent — mirrors _output_schema() in
// content_judge_via_workflow.py (one entry per check, with its sub-answers).
const SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          check_id: { type: 'string' },
          sub_answers: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                key: { type: 'string' },
                reasoning: { type: 'string' },
                evidence_quote: { type: 'string' },
                answer: { type: 'string', enum: ['yes', 'no', 'unknown'] },
              },
              required: ['key', 'reasoning', 'evidence_quote', 'answer'],
            },
          },
        },
        required: ['check_id', 'sub_answers'],
      },
    },
  },
  required: ['verdicts'],
}

const A = typeof args === 'string' ? JSON.parse(args) : args || {}
const repo = A.repo
const inPath = A.in_path
const pageCount = Math.max(0, Number(A.page_count ?? 0))
const concurrency = Math.max(1, Number(A.concurrency ?? 4))
const schema = SCHEMA

const idxs = []
for (let i = 0; i < pageCount; i++) idxs.push(i)

phase('Judge')
log(`Judging ${pageCount} page(s) of ${inPath}, ${concurrency} at a time on the subscription`)

// One judging subagent for page `i`. Retries on a null/empty result (transient
// subscription throttle); the wave concurrency cap below is what mostly prevents it.
const MAX_TRIES = 3
const judgePage = async (i) => {
  for (let t = 0; t < MAX_TRIES; t++) {
    const r = await agent(
      `You are a strict content evaluator scoring ONE web page against several rubric ` +
        `checks, running on the Claude subscription.\n\n` +
        `STEP 1 — fetch your page by running this command EXACTLY (from the repo root, ` +
        `project venv python):\n` +
        `  cd ${repo} && .venv/bin/python -m scripts.content_judge_via_workflow page ${inPath} ${i}\n` +
        `It prints {"prompt": "...", "check_ids": [...]}.\n\n` +
        `STEP 2 — the "prompt" field is a complete, self-contained instruction: a system ` +
        `preamble, the page text, and several "===== CHECK: <id> — <title> =====" blocks, ` +
        `each with sub-questions. Judge EACH check using ONLY the page text.\n\n` +
        `STEP 3 — return the structured output: a "verdicts" array with exactly ONE entry ` +
        `per CHECK shown, each carrying that check's "check_id" and a "sub_answers" entry ` +
        `for every sub-question (key / reasoning / a VERBATIM evidence_quote for any 'yes' / ` +
        `answer). Do not skip or merge checks.`,
      { label: t === 0 ? `content:${i}` : `content:${i}#retry${t}`, phase: 'Judge', schema },
    )
    if (r && Array.isArray(r.verdicts)) return { page_index: i, verdicts: r.verdicts }
  }
  return null
}

// Waves of `concurrency` so at most that many subagents are ever in flight.
const pages = new Array(pageCount).fill(null)
for (let w = 0; w < idxs.length; w += concurrency) {
  const wave = idxs.slice(w, w + concurrency)
  const results = await parallel(wave.map((i) => () => judgePage(i)))
  for (const res of results) {
    if (res) pages[res.page_index] = res
  }
  log(
    `Wave ${w / concurrency + 1}/${Math.ceil(idxs.length / concurrency)} done — ` +
      `${pages.filter(Boolean).length}/${pageCount} pages judged`,
  )
}

return { pages }
