-- GEO Audit — Teasers schema (teaser generator + human review).
-- One row per generated teaser one-pager, plus its review lifecycle
-- (draft → approved/rejected, or an edited copy saved back). Created the same
-- way the other tables exist — run in the project's SQL editor (Supabase
-- Dashboard → SQL Editor). Idempotent: safe on a fresh project or an existing
-- one. Mirrors the conventions in schema_ui.sql / schema_site_audit.sql — uuid
-- PKs, jsonb for variable payloads, RLS enabled with no policies (server-side
-- service_role access only; the anon/publishable key cannot read/write).
--
-- The teaser pipeline (teaser/) returns {draft, html}; the API persists the full
-- TeaserDraft as jsonb (plus a few denormalized columns the list view reads) so
-- the UI can re-open a saved teaser, then approve / edit / reject it. Reviewer
-- edits to the printable copy (headline / lead / CTA / stakes line) are kept in
-- edited_fields rather than mutating the original draft, so the original audit
-- output stays auditable next to the human-reviewed version.

create table if not exists public.teasers (
    id uuid primary key default gen_random_uuid(),
    prospect_url text,
    company_name text,
    category text,
    run_date text,
    hero_engine text,
    -- Denormalized headline + lead so the list/detail views don't unpack `draft`.
    headline_number jsonb not null default '{}'::jsonb,
    lead jsonb not null default '{}'::jsonb,
    table_findings jsonb not null default '[]'::jsonb,
    -- The full TeaserDraft as returned by the teaser pipeline.
    draft jsonb not null default '{}'::jsonb,
    html text,
    status text not null default 'draft'
        check (status in ('draft', 'approved', 'rejected', 'exported')),
    -- Reviewer overrides for the printable copy (headline / leadSentence / cta /
    -- stakesLine, …) — kept separate from `draft` so the original stays intact.
    edited_fields jsonb not null default '{}'::jsonb,
    reject_reason text,
    reviewed_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_teasers_status on public.teasers (status);
create index if not exists idx_teasers_created_at on public.teasers (created_at desc);

alter table public.teasers enable row level security;
