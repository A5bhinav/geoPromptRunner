-- The on-site content notebook (content-addressed ContentJudge verdict cache).
--
-- One row per (page-text × rubric check) judged, keyed by a sha256 of everything
-- that determines the verdict (content-judge model, prompt/rubric fingerprint, the
-- check's definition, the page text). Kept SEPARATE from judge_cache (the query-
-- answer notebook) because the value shape and keyspace differ. The subscription
-- pre-judge writes here; the site audit reads here. See
-- src/audit/checks/content_judge_cache.py and docs/subscription-judge-plan.md.

create table if not exists public.content_judge_cache (
  key        text primary key,        -- the content-address hash
  value      jsonb not null,          -- a serialized CheckVerdict
  created_at timestamptz not null default now()
);

-- Match the other app tables' RLS posture (the app connects with the service-role
-- key, which bypasses RLS). Enable RLS with no policies so anon/authenticated
-- clients cannot read or write verdicts:
--   alter table public.content_judge_cache enable row level security;
