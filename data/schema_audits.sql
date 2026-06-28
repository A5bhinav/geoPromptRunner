-- GEO Audit — Audit Deliverables schema (the paid AI Visibility Audit + review).
-- One row per generated audit deliverable, plus its review lifecycle
-- (draft → approved/rejected/exported, or an edited copy saved back). Run in the
-- project's SQL editor (Supabase Dashboard → SQL Editor). Idempotent: safe on a
-- fresh project or an existing one. Mirrors data/schema_teasers.sql — uuid PKs,
-- jsonb for variable payloads, RLS enabled with no policies (server-side
-- service_role access only; the anon/publishable key cannot read/write).
--
-- The audit generator (teaser/, `npm run audit`) returns {draft, html}; the API
-- persists the full AuditDraft as jsonb (plus a few denormalized columns the list
-- view reads) so the UI can re-open a saved audit, then approve / edit / reject
-- it. Reviewer edits to the narrative (headline / verdict / engagement copy) are
-- kept in edited_fields rather than mutating the original draft, so the original
-- audit output stays auditable next to the human-reviewed version.
--
-- The SOURCE measurement data stays in audit_runs / query_results / judgments /
-- site_audit_* — this table holds the rendered deliverable + review state + the
-- cached draft for reproducibility (doc §11).

create table if not exists public.audit_deliverables (
    id uuid primary key default gen_random_uuid(),
    run_id uuid,                         -- the source run (audit_runs.id)
    client_name text,
    client_domains jsonb not null default '[]'::jsonb,
    category text,
    run_date text,
    -- Denormalized grade so the list view doesn't unpack `draft`.
    grade_letter text,
    grade_score numeric,
    headline jsonb not null default '{}'::jsonb,
    scorecard jsonb not null default '{}'::jsonb,
    -- The full AuditDraft as returned by the audit generator.
    draft jsonb not null default '{}'::jsonb,
    html text,
    status text not null default 'draft'
        check (status in ('draft', 'approved', 'rejected', 'exported')),
    -- Reviewer overrides for the narrative (headline / verdict / engagement copy)
    -- — kept separate from `draft` so the original stays intact.
    edited_fields jsonb not null default '{}'::jsonb,
    reject_reason text,
    reviewed_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_audit_deliverables_run on public.audit_deliverables (run_id);
create index if not exists idx_audit_deliverables_status on public.audit_deliverables (status);
create index if not exists idx_audit_deliverables_created on public.audit_deliverables (created_at desc);

alter table public.audit_deliverables enable row level security;
