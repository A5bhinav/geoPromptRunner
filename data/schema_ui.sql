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
    -- The full run input, stored so an interrupted run can be rebuilt and
    -- resumed (the query texts/intents/personas and fact sheet aren't otherwise
    -- recoverable from the per-result rows alone).
    queries jsonb not null default '[]'::jsonb,
    fact_sheet text,
    judge boolean not null default false,
    -- SearchApi canonical location name for service-area businesses; NULL for
    -- nationally-marketed products. See the alter below for why it is persisted.
    location text,
    error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    archived_at timestamptz
);

-- If audit_runs already existed from an earlier version, add the new state columns.
alter table public.audit_runs add column if not exists status text not null default 'running';
alter table public.audit_runs add column if not exists completed_calls integer not null default 0;
alter table public.audit_runs add column if not exists total_calls integer not null default 0;
alter table public.audit_runs add column if not exists engines jsonb not null default '[]'::jsonb;
alter table public.audit_runs add column if not exists n_queries integer not null default 0;
alter table public.audit_runs add column if not exists fact_sheet_present boolean not null default false;
alter table public.audit_runs add column if not exists error text;
alter table public.audit_runs add column if not exists updated_at timestamptz not null default now();
alter table public.audit_runs add column if not exists queries jsonb not null default '[]'::jsonb;
alter table public.audit_runs add column if not exists fact_sheet text;
alter table public.audit_runs add column if not exists judge boolean not null default false;
-- SearchApi canonical location NAME ("Berkeley,California,US") for a service-area
-- business (W1.4). NULL for nationally-marketed products, which is the pre-pivot
-- default. Persisted because an interrupted LOCAL run rebuilds its RunConfig from
-- this row on resume — without the column, the resumed half would run un-localized
-- and quietly mix two different markets into one measurement.
alter table public.audit_runs add column if not exists location text;
-- What the engine liveness probe saw, per engine, before the fan-out
-- (src/pipeline/preflight.py). Shape: {engine: {model_id, alive, chars, citations,
-- needed_retry}}. Persisted so a report can say WHY a surface is absent from a run
-- instead of silently omitting it — run e186c524 spent a whole audit on a surface
-- whose model had been deprecated, and nothing in the record explained the gap.
alter table public.audit_runs add column if not exists engine_probe jsonb not null default '{}'::jsonb;

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

-- --- Google local pack (the surface that answers local-intent queries) -------
-- Captured per local-intent query, once each — NOT runs_per_query, because a SERP
-- listing has no LLM sampling noise to average out. Kept in its own table rather than
-- in query_results on purpose: a local pack is a ranked entity list, not an answer, and
-- feeding it through the answer path would hand it to the judge and to mention_rate as
-- though it were one (see src/engines/local_pack.py).
create table if not exists public.local_pack_entities (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    query_id text not null,
    prompt text not null,
    position integer,
    name text not null,
    address text,
    category text,
    rating numeric,
    reviews integer,
    -- Google's stable business id. Serper returns it as `cid`, SearchApi as `ludocid`,
    -- and they carry the same value — so this joins across vendors.
    ludocid text,
    phone text,
    website text,
    -- Which vendor produced the capture ('serper_places' | 'searchapi_local_results').
    -- Recorded because the two return different depths (10 businesses vs 3), and a
    -- vendor switch between cycles would otherwise read as real churn in the pack.
    source text not null,
    captured_at timestamptz not null default now()
);

create index if not exists idx_query_results_run_id on public.query_results (run_id);
create index if not exists idx_local_pack_run_id on public.local_pack_entities (run_id);
create index if not exists idx_query_results_run_intent on public.query_results (run_id, intent);
create index if not exists idx_query_citations_run_id on public.query_citations (run_id);
create index if not exists idx_judgments_run_id on public.judgments (run_id);
create index if not exists idx_audit_runs_created on public.audit_runs (created_at desc);
create index if not exists idx_audit_runs_client on public.audit_runs (client_name, created_at);

alter table public.audit_runs enable row level security;
alter table public.query_results enable row level security;
alter table public.query_citations enable row level security;
alter table public.judgments enable row level security;
alter table public.local_pack_entities enable row level security;
