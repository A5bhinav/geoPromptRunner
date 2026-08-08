-- GEO Audit — tenancy, part 3: the access function every policy calls (LIC-T3).
--
-- Apply with:  python -m scripts.apply_schema data/schema_tenancy_access.sql
-- Requires data/schema_memberships.sql.
--
-- This file writes NO policies. It writes the two functions LIC-T10's policies
-- will call, and the indexes that make them fast. Split out because getting these
-- wrong is not a slow query, it is a 178,000ms one.

create schema if not exists private;

-- ---------------------------------------------------------------------------
-- is_platform_admin — the founders' bypass
-- ---------------------------------------------------------------------------
-- A flag on the user row, never a placeholder "founders agency" tenant.
create or replace function private.is_platform_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.users u
        where u.id = (select auth.uid())
          and u.is_platform_admin
          and u.deactivated_at is null
    );
$$;

-- ---------------------------------------------------------------------------
-- has_company_access — the predicate in every business-table policy
-- ---------------------------------------------------------------------------
-- Three ways in, and all three are required:
--   1. platform admin (the founders)
--   2. a direct membership on that company (the client's own people)
--   3. the agency-managed path, through companies.managing_agency_id
--
-- WHY `security definer` IS NOT OPTIONAL. Without it, a policy on `audit_runs`
-- that consults `memberships` triggers RLS evaluation ON `memberships` for every
-- row of `audit_runs`, compounding per row. Supabase's own troubleshooting doc
-- measures that at 178,000ms vs 12ms. `security definer` runs the lookup once,
-- plain and indexed, with no recursive policy evaluation.
--
-- WHY `set search_path = ''` IS NOT OPTIONAL EITHER. A `security definer`
-- function runs with the DEFINER's rights; without a pinned search_path a caller
-- who can create objects in a schema earlier on the path can shadow `memberships`
-- and make this function answer true. Every reference below is schema-qualified
-- for the same reason.
--
-- WHY IT FILTERS ON user_id FIRST. Starting from `company_id` scans memberships
-- by tenant; starting from `(select auth.uid())` hits idx_memberships_user and
-- yields a handful of rows. The design measures that direction change at
-- 9,000ms -> 20ms. Note `(select auth.uid())` rather than a bare `auth.uid()`:
-- the subquery form is evaluated once as an InitPlan instead of per row
-- (179ms -> 9ms).
--
-- DEPARTURE FROM docs/licensing-implementation.md §1.2, deliberate: both branches
-- also require `accepted_at is not null`. The design checks only
-- `deactivated_at is null`, which would grant a PENDING invitee full access to a
-- company the moment the row is written and before they have proved they control
-- the invited mailbox. LIC-T14 writes `accepted_at` in the same transaction as
-- the identity on confirm, so the invite flow is unaffected; what this closes is
-- the agency console (LIC-T19) inviting staff, where the row necessarily exists
-- before the person has confirmed anything.
create or replace function private.has_company_access(target_company_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select
        private.is_platform_admin()
        or exists (                              -- direct company membership
            select 1 from public.memberships m
            where m.user_id = (select auth.uid())
              and m.company_id = target_company_id
              and m.deactivated_at is null
              and m.accepted_at is not null
        )
        or exists (                              -- agency-managed path
            select 1
            from public.memberships m
            join public.companies c on c.managing_agency_id = m.organization_id
            where m.user_id = (select auth.uid())
              and c.id = target_company_id
              and m.deactivated_at is null
              and m.accepted_at is not null
        );
$$;

-- `authenticated` only. An anonymous caller has no membership by construction,
-- and the one anonymous read path in the product — a share link — is authorised
-- by its token row (LIC-T17), not by this function.
grant usage on schema private to authenticated;
grant execute on function private.is_platform_admin() to authenticated;
grant execute on function private.has_company_access(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- The indexes these functions live or die by
-- ---------------------------------------------------------------------------
-- Declared in schema_memberships.sql / schema_tenancy.sql and repeated here
-- (idempotently) so this file is self-sufficient: indexing the columns used in
-- policies is the >100x line in the design's performance table, and an access
-- function applied without them is the slow-query incident it was written to
-- prevent.
create index if not exists idx_memberships_user on public.memberships (user_id);
create index if not exists idx_memberships_org on public.memberships (organization_id);
create index if not exists idx_memberships_company on public.memberships (company_id);
create index if not exists idx_companies_managing_agency
    on public.companies (managing_agency_id);
