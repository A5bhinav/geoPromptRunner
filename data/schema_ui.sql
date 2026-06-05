-- GEO Audit — UI/API schema.
-- Run once in the project's SQL editor (Supabase Dashboard → SQL Editor).
-- Idempotent: safe to run on a fresh project or one that already has the
-- earlier audit_runs/query_results tables. Creates everything the API needs and
-- adds the run-state/progress columns the UI reads back after a restart.
--
-- Note: RLS is enabled with no policies, so only the service_role key (what the
-- API uses via SUPABASE_KEY) can read/write — the anon/publishable key cannot.
-- That is intentional for a server-side-only backend.

-- --- Audit runs (client identity + locked set + run state/progress) ----------
create table if not exists public.audit_runs (
    id uuid primary key default gen_random_uuid(),
    client_name text not null,
    client_domains jsonb not null default '[]'::jsonb,
    competitors jsonb not null default '[]'::jsonb,
    category text,
    query_set_version text not null,
    query_set_locked_at text,
    runs_per_query integer not null,
    status text not null default 'running',
    completed_calls integer not null default 0,
    total_calls integer not null default 0,
    engines jsonb not null default '[]'::jsonb,
    n_queries integer not null default 0,
    fact_sheet_present boolean not null default false,
    error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    archived_at timestamptz
);

-- If audit_runs already existed (from schema_v2), add the new state columns.
alter table public.audit_runs add column if not exists status text not null default 'running';
alter table public.audit_runs add column if not exists completed_calls integer not null default 0;
alter table public.audit_runs add column if not exists total_calls integer not null default 0;
alter table public.audit_runs add column if not exists engines jsonb not null default '[]'::jsonb;
alter table public.audit_runs add column if not exists n_queries integer not null default 0;
alter table public.audit_runs add column if not exists fact_sheet_present boolean not null default false;
alter table public.audit_runs add column if not exists error text;
alter table public.audit_runs add column if not exists updated_at timestamptz not null default now();

-- --- Per-(query, engine, run) answers ----------------------------------------
create table if not exists public.query_results (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    query_id text not null,
    intent text not null,
    prompt text not null,
    engine_name text not null,
    run_index integer not null,
    response text,
    "timestamp" timestamptz not null
);

-- --- Citation URLs surfaced per (query, engine) ------------------------------
create table if not exists public.query_citations (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    query_id text not null,
    engine_name text not null,
    url text not null,
    domain text not null
);

-- --- LLM-judge output (one row per judged answer) ----------------------------
create table if not exists public.judgments (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    query_id text not null,
    engine_name text not null,
    intent text not null,
    run_index integer not null,
    assessed boolean not null,
    brands jsonb not null default '[]'::jsonb,
    accuracy_flags jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_query_results_run_id on public.query_results (run_id);
create index if not exists idx_query_results_run_intent on public.query_results (run_id, intent);
create index if not exists idx_query_citations_run_id on public.query_citations (run_id);
create index if not exists idx_judgments_run_id on public.judgments (run_id);
create index if not exists idx_audit_runs_created on public.audit_runs (created_at desc);
create index if not exists idx_audit_runs_client on public.audit_runs (client_name, created_at);

alter table public.audit_runs enable row level security;
alter table public.query_results enable row level security;
alter table public.query_citations enable row level security;
alter table public.judgments enable row level security;
