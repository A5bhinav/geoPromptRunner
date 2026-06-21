-- GEO Audit — Site Audit schema (Categories 1–6).
-- Child tables for the site-audit pipeline, all keyed on audit_runs(id) so one
-- CSV upload drives engines + scrape + checks under a single run_id (plan §6).
-- Idempotent: safe to run on a fresh project or an existing one. Mirrors the
-- conventions in schema_ui.sql — uuid PKs, jsonb for variable payloads, RLS
-- enabled with no policies (server-side service_role access only).
--
-- See docs/site-audit-implementation-guide.md §6.4. Large HTML blobs are NOT
-- stored here: they live gzipped in Supabase Storage, referenced by
-- site_audit_page.storage_path + content_sha256. Only the small queryable
-- artifacts (extracted_text, json_ld, fetch_meta) live in Postgres.

-- --- Phase state (resumability anchor) ---------------------------------------
-- One row per (run, phase). A restart resumes by skipping phases already 'done'.
create table if not exists public.site_audit_phase (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    crawl_id uuid,
    phase text not null,                       -- fetch | schema | linkgraph | judge | offsite
    state text not null default 'pending',     -- pending | running | done | partial | failed
    done integer not null default 0,
    total integer not null default 0,
    detail jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (run_id, phase)
);

-- --- Page cache (the fetch & cache layer writes one row per crawled page) -----
-- Key is (run_id, normalized_url): re-crawling a run upserts rather than
-- duplicating. raw/rendered HTML are not columns — storage_path points at the
-- gzipped blob in Storage; content_sha256 dedups/change-detects.
create table if not exists public.site_audit_page (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    crawl_id uuid not null,
    url text not null,
    normalized_url text not null,
    category text not null,                    -- homepage | pricing | comparison | product | docs | blog | other
    status_code integer,
    final_url text,
    request_ua text,
    was_rendered boolean not null default false,
    render_reason text,
    blocked boolean not null default false,    -- Cloudflare/anti-bot challenge (recorded, not bypassed)
    content_sha256 text not null,
    storage_path text,                         -- pointer to gzipped HTML blob in Supabase Storage
    extracted_text text,                       -- trafilatura main text (queryable)
    json_ld jsonb not null default '[]'::jsonb,
    fetch_meta jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null,
    created_at timestamptz not null default now(),
    unique (run_id, normalized_url)
);

-- --- Deterministic + LLM-judge check verdicts --------------------------------
-- (run_id, check_key, page_url) is unique for idempotent re-runs. page_url is ''
-- (not null) for site-level checks so the unique constraint still dedups them.
create table if not exists public.site_audit_check (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    check_key text not null,
    category integer,                          -- 1..6
    page_url text not null default '',
    status text not null,                      -- pass | partial | fail | unknown | ungradeable
    method text,                               -- deterministic | judge | web
    details jsonb not null default '{}'::jsonb,
    evidence jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (run_id, check_key, page_url)
);

-- --- Offsite research findings (Cat 6) ---------------------------------------
create table if not exists public.site_audit_offsite_finding (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.audit_runs (id) on delete cascade,
    finding_type text not null,                -- reddit | wikidata | backlinks | reviews | listicle | serp
    title text,
    url text,
    confidence text,                           -- high | medium | low
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_site_audit_phase_run_id on public.site_audit_phase (run_id);
create index if not exists idx_site_audit_page_run_id on public.site_audit_page (run_id);
create index if not exists idx_site_audit_check_run_id on public.site_audit_check (run_id);
create index if not exists idx_site_audit_offsite_run_id on public.site_audit_offsite_finding (run_id);

alter table public.site_audit_phase enable row level security;
alter table public.site_audit_page enable row level security;
alter table public.site_audit_check enable row level security;
alter table public.site_audit_offsite_finding enable row level security;
