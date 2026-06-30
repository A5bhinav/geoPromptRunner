// Pre-judge an audit run on the Claude subscription.
//
// Input (args, produced by `scripts/judge_via_workflow.py dump`):
//   { run_id, client, competitors, has_fact_sheet, schema, items: [{ key, prompt }] }
// `items[].prompt` is the exact single-judge prompt (system + user) for one answer;
// `schema` is the record_judgment input schema, used to force structured output so
// each subagent returns the same JSON shape the API judge's forced tool would.
//
// Output (return value, fed to `judge_via_workflow.py inject`):
//   { run_id, client, competitors, has_fact_sheet, items: [{ key, raw }] }
// where `raw` is the judged { brands, client_accuracy_flags } object.
//
// The subagents run on the session's auth (the Max subscription), so this whole
// pass costs subscription quota, not API credit. A subagent that fails drops to
// null and is omitted — its answer simply stays un-cached and is re-judged later,
// never written as a bad verdict. See docs/subscription-judge-plan.md.

export const meta = {
  name: 'prejudge',
  description: 'Judge stored audit answers on the subscription to pre-fill the judge cache',
  phases: [{ title: 'Judge', detail: 'one subagent per unique answer' }],
}

const items = Array.isArray(args?.items) ? args.items : []
const schema = args?.schema

phase('Judge')
if (!items.length) {
  log('No answers to judge — cache already warm.')
} else {
  log(`Judging ${items.length} answer(s) on the subscription`)
}

const judged = await parallel(
  items.map((it) => () =>
    agent(it.prompt, { label: `judge:${String(it.key).slice(0, 8)}`, phase: 'Judge', schema })
      .then((raw) => (raw ? { key: it.key, raw } : null))
  )
)

const ok = judged.filter(Boolean)
log(`Judged ${ok.length}/${items.length} (the rest failed and stay un-cached)`)

return {
  run_id: args?.run_id,
  client: args?.client,
  competitors: args?.competitors,
  has_fact_sheet: args?.has_fact_sheet,
  items: ok,
}
