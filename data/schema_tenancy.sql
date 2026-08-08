-- GEO Audit — tenancy, part 1: companies become real rows (LIC-T1).
--
-- Apply with:  python -m scripts.apply_schema data/schema_tenancy.sql
-- Idempotent, and additive only: no existing column is altered or dropped, and
-- every new column is NULLABLE with no default. LIC-T9 is what tightens them to
-- NOT NULL, after the backfill in `scripts/backfill_companies.py` has run and
-- been verified.
--
-- WHY THIS FILE EXISTS AT ALL. Until now a "company" was not a row — it was a
-- GROUP BY. `src/api/projects.py:_collect()` derived projects per request by
-- bucketing `audit_runs` and `teasers` on registrable domain, with a name-slug
-- fallback. A membership, a slot count and an RLS predicate cannot reference a
-- groupby, so every later task in docs/licensing-spec.md is blocked on this one.
--
-- WHY ORGANIZATIONS AND COMPANIES SHIP TOGETHER. `companies.managing_agency_id`
-- references `organizations(id)`, so creating either alone leaves a dangling
-- reference. They are one migration, not two.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- organizations — agencies. Absent for a company that buys direct.
-- ---------------------------------------------------------------------------
-- LIC-T2 adds `plan_id` and `entitlement_overrides` here; this file deliberately
-- stops at identity so the keystone can land without waiting on entitlements.
create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now(),
    -- Soft-deactivate, never delete: storage is create-only (CLAUDE.md), and an
    -- agency's audit history has to outlive the agency's contract.
    deactivated_at timestamptz
);

-- ---------------------------------------------------------------------------
-- companies — the audited brand, and the paying tenant.
-- ---------------------------------------------------------------------------
create table if not exists public.companies (
    id uuid primary key default gen_random_uuid(),

    -- The label the UI shows. Today that is the DOMAIN when we know one and the
    -- client name when we do not, because that is exactly what `_key_for()`
    -- returns as its label — and the LIC-T1 acceptance criterion is that
    -- `list_projects()` comes back byte-identical. Storing anything prettier
    -- here would change a response shape the web UI already renders.
    name text not null,

    -- The project key, verbatim: either the registrable domain ("fort.cx") or
    -- "name:<slug>" ("name:oura") when a run carries no domain. This IS the
    -- string in today's `/projects/{key}` URLs, so keeping it as the slug keeps
    -- every existing link working and makes the migration observable — a
    -- company row and a project key are the same identifier.
    slug text unique not null,

    -- The registrable domain when we have one, NULL for a name-keyed company.
    -- Denormalised out of `slug` rather than parsed back out of it: `fact_sheets`,
    -- `factsheet_intake_sessions` and the crawler all key on domain, so the
    -- backfill needs to join on it, and re-deriving "is this slug a domain or a
    -- name: key" at every join site is how the two representations drift.
    domain text,

    -- NULLABLE and REASSIGNABLE, and that is the point: a client leaving its
    -- agency to go direct is one UPDATE, not a migration. AgencyAnalytics (the
    -- market leader) cannot do this — their docs say transferring a client means
    -- manually recreating dashboards, reports and users.
    -- Access is COMPUTED from this column at query time (LIC-T3), never copied
    -- into per-company grant rows.
    managing_agency_id uuid references public.organizations(id),

    created_at timestamptz not null default now()
);

create index if not exists idx_companies_managing_agency
    on public.companies (managing_agency_id);
-- The backfill and the fact-sheet/intake joins both look a company up by domain.
create index if not exists idx_companies_domain on public.companies (domain);

-- ---------------------------------------------------------------------------
-- company_id on every table that holds customer data.
-- ---------------------------------------------------------------------------
-- NULLABLE, NO DEFAULT, deliberately (design §2 step 2): existing rows have no
-- tenant, and NOT NULL with a function default would force a full table rewrite.
--
-- THE FOUR RUN-CHILD TABLES GET THE COLUMN TOO, rather than reaching their tenant
-- through a join to `audit_runs`. `query_results`, `query_citations`, `judgments`
-- and `local_pack_entities` are the highest-volume tables in the system (~1,500
-- rows per run; `query_citations` is already at 8,969) and are exactly the tables
-- that already have RLS enabled. A policy that joins back to `audit_runs` to find
-- the tenant re-introduces the per-row recursion that `security definer` exists to
-- avoid, on the worst possible tables. Denormalise, backfill from the parent run,
-- and let the policy read one indexed column.
--
-- Guarded by `to_regclass` because several of these tables are DECLARED in
-- data/*.sql but were never applied to the live project (`client_configs`,
-- `findings_registry`), and `alter table ... add column if not exists` still
-- errors on a table that does not exist. A schema file that half-applies is worse
-- than one that did not run.
do $$
declare
    t text;
    tenant_tables text[] := array[
        -- The run and its children.
        'audit_runs',
        'query_results',
        'query_citations',
        'judgments',
        'local_pack_entities',
        -- Site audit, all keyed by run_id.
        'site_audit_page',
        'site_audit_check',
        'site_audit_offsite_finding',
        -- Prospect-facing and client-facing artifacts.
        'teasers',
        'audit_deliverables',
        -- Fact sheets and the intake conversation that produces them.
        'fact_sheets',
        'fact_claims',
        'factsheet_intake_sessions',
        -- Per-client operational records.
        'client_configs',
        'findings_registry'
    ];
begin
    foreach t in array tenant_tables loop
        if to_regclass('public.' || t) is not null then
            execute format(
                'alter table public.%I add column if not exists company_id uuid '
                'references public.companies(id)', t);
            -- Indexed because every RLS policy written in LIC-T10 filters on it,
            -- and indexing the policy column is the >100x line in the design's
            -- performance table.
            execute format(
                'create index if not exists %I on public.%I (company_id)',
                'idx_' || t || '_company', t);
        else
            raise notice 'skipping %: table does not exist in this project', t;
        end if;
    end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Deliberately NOT given a company_id
-- ---------------------------------------------------------------------------
-- `judge_cache` / `content_judge_cache` — content-addressed caches, not customer
--   data. A verdict is keyed by (model, prompt, answer); two clients asking the
--   same question of the same engine SHOULD share the cached verdict, and
--   tenanting the cache would silently halve its hit rate and double judge spend.
-- `engine_fingerprints` — system provenance about our own engine pins.
-- `factsheet_jobs` — the generation QUEUE. It carries `lead_ref` and a spend
--   counter, is written by the worker under the service role, and holds no
--   client-readable content; the sheet it produces is tenanted instead.
-- `revoked_share_tokens` — a deny list. LIC-T17 replaces it with a token table
--   that DOES carry company_id.
-- `review_records` — internal review lifecycle, ours not the client's.
-- The Phase-1 legacy tables (`prompt_runs`, `prompt_results`, `brand_mentions`,
--   `citations`, `rubric_scores`) hold zero rows and are superseded by
--   audit_runs/query_results; they are not in the list above because giving a
--   tenant column to a dead table invites someone to start writing to it again.
