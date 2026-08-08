-- GEO Audit — tenancy, part 5: the policies, and FORCE (LIC-T10).
--
-- Apply with:  python -m scripts.apply_schema data/schema_tenancy_rls.sql
-- Requires schema_tenancy.sql, schema_memberships.sql, schema_tenancy_access.sql
-- and schema_tenancy_notnull.sql.
--
-- RLS WAS ALREADY ENABLED ON ALL 22 PUBLIC TABLES WITH ZERO POLICIES (the LIC-T0
-- survey; the spec said five, the survey found twenty-two). So this file does not
-- turn anything on. It writes the policies that make the enablement mean
-- something, and adds FORCE.
--
-- AND IT STILL PROVES NOTHING WITHOUT LIC-T7. A policy is evaluated only for a
-- connection that is subject to RLS. The service-role key bypasses all of this;
-- what makes these policies bite is `db._user_client`, which connects with the
-- ANON key and the caller's access token. Both halves are required.
--
-- WHY `FORCE`, NOT JUST `ENABLE`. The table OWNER bypasses RLS by default. If
-- migrations run as `postgres` and anything else ever connects as that role, every
-- policy below is silently skipped. FORCE closes that.
--
-- WHY EVERY POLICY IS `TO authenticated`. Role targeting takes an excluded role
-- from 170ms to <0.1ms because the predicate is never evaluated for them. It also
-- states the intent: `anon` has no membership by construction, and the one
-- anonymous read path in the product — a share link — is authorised by its token
-- row, through a service-role read scoped to a single run (LIC-T17), never by a
-- policy here.
--
-- WHY PERMISSIVE AND NOT RESTRICTIVE. Multiple permissive policies OR together,
-- which is how "add an exception" silently widens access. There is exactly ONE
-- policy per table per command here, so there is nothing to OR with. `AS
-- RESTRICTIVE` is held in reserve for a rule that must AND with everything else;
-- using it as the default would make a later exception impossible to express.

-- ---------------------------------------------------------------------------
-- The tenant tables
-- ---------------------------------------------------------------------------
-- One policy per table, `FOR ALL`, predicate `private.has_company_access(company_id)`.
--
-- `using` governs which rows are VISIBLE; `with check` governs which rows may be
-- WRITTEN. Both are required and both are the same predicate: without `with
-- check`, a member of tenant A could INSERT a row stamped with tenant B's
-- company_id — writing into another tenant rather than reading from it.
do $$
declare
    t text;
    tenant_tables text[] := array[
        -- `companies` is DELIBERATELY ABSENT since LIC-T18. A single `for all`
        -- policy cannot express its write rules: `has_company_access(id)` is
        -- vacuous as a `with check` on UPDATE (a `stable` function reads the OLD
        -- row) and impossible as one on INSERT (it cannot see the row being
        -- inserted at all). Its per-command policies live in
        -- data/schema_agency_client_writes.sql. Re-adding it here would restore
        -- the vacuous policy, which — being permissive — would OR with and
        -- silently defeat the narrower ones.
        'audit_runs',
        'query_results',
        'query_citations',
        'judgments',
        'local_pack_entities',
        'site_audit_page',
        'site_audit_check',
        'site_audit_offsite_finding',
        'teasers',
        'audit_deliverables',
        'fact_sheets',
        'fact_claims',
        'factsheet_intake_sessions',
        'client_configs',
        'findings_registry'
    ];
    key_column text;
begin
    foreach t in array tenant_tables loop
        if to_regclass('public.' || t) is null then
            raise notice 'skipping %: table does not exist in this project', t;
            continue;
        end if;
        -- `companies` IS the tenant, so its own primary key is what gets checked.
        key_column := case when t = 'companies' then 'id' else 'company_id' end;

        execute format('drop policy if exists tenant_access on public.%I', t);
        execute format(
            'create policy tenant_access on public.%I '
            'as permissive for all to authenticated '
            'using (private.has_company_access(%I)) '
            'with check (private.has_company_access(%I))',
            t, key_column, key_column);

        execute format('alter table public.%I enable row level security', t);
        execute format('alter table public.%I force row level security', t);
    end loop;
end $$;

-- ---------------------------------------------------------------------------
-- organizations — an agency's own row
-- ---------------------------------------------------------------------------
-- Visible to a platform admin, and to a member of that organization. Read-only
-- for members: creating and reparenting an organization is a platform-admin
-- action (LIC-T14), performed by the service role, so no `with check` is granted
-- to `authenticated` at all.
drop policy if exists organization_read on public.organizations;
create policy organization_read on public.organizations
    as permissive for select to authenticated
    using (
        private.is_platform_admin()
        or exists (
            select 1 from public.memberships m
            where m.user_id = (select auth.uid())
              and m.organization_id = organizations.id
              and m.deactivated_at is null
              and m.accepted_at is not null
        )
    );
alter table public.organizations enable row level security;
alter table public.organizations force row level security;

-- ---------------------------------------------------------------------------
-- users — yourself, and the platform admins
-- ---------------------------------------------------------------------------
-- Deliberately NOT "everyone in my organization": that would leak the email of
-- every staff member to every client user who happens to share a tenant. The
-- agency console reads its own staff list through the service role, which can
-- scope the query to that organization.
drop policy if exists user_self_read on public.users;
create policy user_self_read on public.users
    as permissive for select to authenticated
    using (id = (select auth.uid()) or private.is_platform_admin());
alter table public.users enable row level security;
alter table public.users force row level security;

-- ---------------------------------------------------------------------------
-- memberships — your own memberships
-- ---------------------------------------------------------------------------
-- Read-only, and only your own. A user needs to know what they belong to; nobody
-- needs to enumerate a tenant's roster through this table. Writes are
-- platform-admin/console actions through the service role.
--
-- NOTE the predicate is a plain column comparison, NOT a call to
-- `has_company_access`. A policy on `memberships` that consulted a function which
-- itself reads `memberships` is the recursion `security definer` exists to break —
-- and here it would be genuinely circular.
drop policy if exists membership_self_read on public.memberships;
create policy membership_self_read on public.memberships
    as permissive for select to authenticated
    using (user_id = (select auth.uid()) or private.is_platform_admin());
alter table public.memberships enable row level security;
alter table public.memberships force row level security;

-- ---------------------------------------------------------------------------
-- Left alone, on purpose
-- ---------------------------------------------------------------------------
-- `judge_cache`, `content_judge_cache`, `engine_fingerprints`, `factsheet_jobs`,
-- `revoked_share_tokens`, `review_records` and the five dead Phase-1 tables keep
-- RLS enabled with NO policy. That is not an oversight — it is the strongest
-- possible setting: no `authenticated` user can read or write them at all, and the
-- only access is the service-role allowlist documented in `db._execute`. Giving
-- them a policy would be strictly weaker.
--
-- Run `supabase db advisors --type security` after applying. Lint 0007 ("RLS
-- enabled, no policy") will still fire for exactly those tables; that is expected,
-- and this comment is the record of why.
