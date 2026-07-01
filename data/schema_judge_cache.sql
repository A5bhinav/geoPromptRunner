-- The shared judge notebook (content-addressed verdict cache).
--
-- One row per judged answer, keyed by a sha256 of everything that determines the
-- verdict (judge model, client + competitors, fact sheet, prompt, answer). The
-- subscription pre-judge writes here (via scripts/judge_via_workflow.py inject) and
-- the CLI/UI judge reads here, so they share one notebook across machines. See
-- src/pipeline/judge_cache.py (SupabaseJudgeCache) and docs/subscription-judge-plan.md.

create table if not exists public.judge_cache (
  key        text primary key,        -- the content-address hash (never guessed/enumerated)
  value      jsonb not null,          -- {brands:[...], flags:[...], assessed: bool}
  created_at timestamptz not null default now()
);

-- RLS: match your OTHER app tables' posture.
--   * If the app connects with the SERVICE-ROLE key (which bypasses RLS), enable RLS
--     with no policies so anon/authenticated clients can't read or write verdicts:
--
--       alter table public.judge_cache enable row level security;
--
--   * If your existing tables (audit_runs, query_results, ...) run WITHOUT RLS, leave
--     this table the same so the app keeps working. (Verdicts aren't secret, but the
--     table shouldn't be world-writable — prefer the service-role + RLS setup.)
