-- GEO Measurement Platform — rubric score capture (Step-6 roadmap inputs).
-- Stores the human Pass/Partial/Fail judgments per rubric check so report §4
-- (Cat 1-6 rollup) and §5 (prioritized roadmap) can be rendered. Automation of
-- the scoring is deliberately deferred; this is the data capture only.

create table if not exists public.rubric_scores (
    id uuid primary key default gen_random_uuid(),
    run_id uuid references public.audit_runs (id) on delete cascade,
    subject text not null,          -- client or a competitor name
    category text not null,         -- RubricCategory value
    check_name text not null,
    status text not null,           -- pass / partial / fail
    weight numeric not null default 1,
    note text,
    created_at timestamptz not null default now()
);

create index if not exists idx_rubric_scores_run_id on public.rubric_scores (run_id);
alter table public.rubric_scores enable row level security;
