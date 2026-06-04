-- GEO Measurement Platform — LLM judge output storage.
-- One row per judged answer (AnswerJudgment); brands and accuracy_flags are
-- JSONB so a row round-trips to the in-memory dataclass without joins. Lets you
-- re-render the judge report without re-paying the judge (re-judge on demand).

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

create index if not exists idx_judgments_run_id on public.judgments (run_id);
alter table public.judgments enable row level security;
