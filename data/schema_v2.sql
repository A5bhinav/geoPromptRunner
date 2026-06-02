-- GEO Measurement Platform — query-level audit schema (Tier 1.2/1.3).
-- Stores the intent-aware QueryResult model with stable run identity and the
-- locked query-set version, so trend / versioning / per-bucket queries are
-- possible. Run once (Dashboard SQL Editor or psycopg). Additive — does not
-- touch the Chunk-9 tables.

create table if not exists public.audit_runs (
    id uuid primary key default gen_random_uuid(),
    client_name text not null,
    client_domains jsonb not null default '[]'::jsonb,
    competitors jsonb not null default '[]'::jsonb,
    category text,
    query_set_version text not null,
    query_set_locked_at text,
    runs_per_query integer not null,
    created_at timestamptz not null default now(),
    archived_at timestamptz
);

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

create table if not exists public.query_citations (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    query_id text not null,
    engine_name text not null,
    url text not null,
    domain text not null
);

create index if not exists idx_query_results_run_id on public.query_results (run_id);
create index if not exists idx_query_results_run_intent on public.query_results (run_id, intent);
create index if not exists idx_query_citations_run_id on public.query_citations (run_id);
create index if not exists idx_audit_runs_client on public.audit_runs (client_name, created_at);

alter table public.audit_runs enable row level security;
alter table public.query_results enable row level security;
alter table public.query_citations enable row level security;
