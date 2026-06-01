-- GEO Measurement Platform — Chunk 9 storage schema.
-- Run once against your Supabase project (Dashboard -> SQL Editor -> Run),
-- or via a pooler connection string. Column names match src/storage/db.py.

create table if not exists public.prompt_runs (
    id uuid primary key default gen_random_uuid(),
    client_name text not null,
    prompt_count integer not null,
    created_at timestamptz not null default now(),
    archived_at timestamptz
);

create table if not exists public.prompt_results (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.prompt_runs (id) on delete cascade,
    prompt text not null,
    engine_name text not null,
    response text,
    "timestamp" timestamptz not null
);

create table if not exists public.brand_mentions (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.prompt_runs (id) on delete cascade,
    brand text not null,
    engine_name text not null,
    prompt text not null,
    mention_type text not null
);

create table if not exists public.citations (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.prompt_runs (id) on delete cascade,
    url text not null,
    engine_name text not null,
    prompt text not null
);

create index if not exists idx_prompt_results_run_id on public.prompt_results (run_id);
create index if not exists idx_brand_mentions_run_id on public.brand_mentions (run_id);
create index if not exists idx_citations_run_id on public.citations (run_id);

-- Lock down: RLS on, no policies. The service_role (secret) key the pipeline
-- uses bypasses RLS; the publishable/anon key gets no access.
alter table public.prompt_runs enable row level security;
alter table public.prompt_results enable row level security;
alter table public.brand_mentions enable row level security;
alter table public.citations enable row level security;
