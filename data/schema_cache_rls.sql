-- GEO Audit — enable RLS on the two cache tables that never got it.
--
--   python -m scripts.apply_schema data/schema_cache_rls.sql
--
-- WHAT THIS FIXES. Every table in this project runs RLS with no policies, so
-- only the service_role (which bypasses RLS) can reach it — schema_ui.sql:152-156,
-- schema_site_audit.sql:73-75, schema_audits.sql:50, schema_teasers.sql:45.
-- Two tables are the exception: `judge_cache` and `content_judge_cache` mention
-- RLS only in a COMMENT (schema_judge_cache.sql:19, schema_content_judge_cache.sql:19)
-- and never enable it. They are the single gap in an otherwise uniform posture.
--
-- HOW BAD IS IT TODAY. Not a live leak: this project's Supabase key never
-- reaches a browser — `web/` talks only to the FastAPI, and there is no
-- NEXT_PUBLIC_SUPABASE_* anywhere in the bundle. Reaching these tables requires
-- possessing SUPABASE_KEY, which lives only in .env on the server. This is
-- defense in depth, not an incident.
--
-- WHY IT IS SAFE TO TURN ON. Supabase's stock pg_default_acl grants ALL to
-- `anon` and `authenticated` on every new object, so without RLS these two
-- tables are protected only by that key staying private. And the app cannot
-- break: every other table already enforces RLS with zero policies and the app
-- works, which means the key it connects with bypasses RLS. Enabling RLS here
-- changes nothing for the app and closes the gap for everyone else.
--
-- WHAT IS IN THEM. Cached judge verdicts keyed by a content hash. Read access
-- leaks captured engine answers; WRITE access is the sharper one — a writable
-- verdict cache is a way to poison what the report says without touching the
-- judge.

alter table public.judge_cache enable row level security;
alter table public.content_judge_cache enable row level security;

-- Belt-and-braces against pg_default_acl, matching the posture of
-- data/schema_factsheets.sql. RLS with no policies is already a deny for anon;
-- revoking the inherited grant means a future permissive policy cannot silently
-- reopen the table on its own.
revoke all on public.judge_cache from anon, authenticated;
revoke all on public.content_judge_cache from anon, authenticated;

-- Verify (as the service role, which bypasses RLS — expect rowsecurity = true):
--   select relname, relrowsecurity from pg_class
--   where relname in ('judge_cache','content_judge_cache');
