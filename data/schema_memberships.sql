-- GEO Audit — tenancy, part 2: identity and membership (LIC-T2).
--
-- Apply with:  python -m scripts.apply_schema data/schema_memberships.sql
-- Requires data/schema_tenancy.sql (organizations, companies) to be applied first.
--
-- THE ONE TABLE THAT COULD NOT WAIT. `memberships` is a join table even though
-- every user in v1 will have exactly one membership. That is the entire insurance
-- policy from the licensing research: a scalar `users.company_id` makes "one user,
-- many client brands" structurally impossible, and retrofitting it later touches
-- auth, session, and every permission check. One extra table now.
--
-- Nothing here is enforced yet. RLS policies come in LIC-T10, and they will be a
-- no-op until LIC-T7 gets the API off the service-role key. This file is shape,
-- not enforcement.

-- ---------------------------------------------------------------------------
-- Roles
-- ---------------------------------------------------------------------------
-- An enum rather than free text: a typo'd role in a text column is a silent
-- permission failure that reads as "the feature is broken for one person".
-- Postgres has no `create type if not exists`, hence the guard.
do $$
begin
    if not exists (select 1 from pg_type where typname = 'membership_role') then
        create type public.membership_role as enum (
            'AGENCY_OWNER',     -- runs the agency: adds clients, invites staff
            'AGENCY_MANAGER',   -- agency staff: reaches every managed company
            'COMPANY_ADMIN',    -- the client's own admin, agency-managed or direct
            'COMPANY_VIEWER',   -- read-only within one company
            'BILLING_ONLY'      -- invoices and slots, no report access
        );
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- users — mirrors auth.users
-- ---------------------------------------------------------------------------
-- Supabase owns `auth.users`; this is the row our own foreign keys point at, kept
-- in sync by the `handle_new_user` trigger below.
create table if not exists public.users (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,

    -- THE FOUNDERS ARE A FLAG, NOT A TENANT. Modelling them as a "founders
    -- agency" organization would put a placeholder tenant into every
    -- agency-level list, chart and invoice, and it would have to be migrated
    -- away from later. `private.is_platform_admin()` reads this column.
    is_platform_admin boolean not null default false,

    created_at timestamptz not null default now(),
    -- Soft-deactivate. Storage is create-only (CLAUDE.md); a departed user's
    -- audit history is still the agency's record.
    deactivated_at timestamptz
);

-- Mirror auth.users -> public.users on signup. `security definer` because the
-- trigger runs as the signing-up user, who has no rights on public.users.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into public.users (id, email)
    values (new.id, new.email)
    on conflict (id) do update set email = excluded.email;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- organizations: plan and entitlements (LIC-T4 reads these)
-- ---------------------------------------------------------------------------
-- `plan_id` names a row in PLAN_ENTITLEMENTS (src/licensing/entitlements.py);
-- `entitlement_overrides` is how a negotiated deal is expressed. A negotiated
-- deal is an OVERRIDE, never a new plan name — inventing `agencyPlus` for one
-- customer means hunting every check that compares plan names.
alter table public.organizations
    add column if not exists plan_id text not null default 'agency';
alter table public.organizations
    add column if not exists entitlement_overrides jsonb;

-- ---------------------------------------------------------------------------
-- memberships — the load-bearing table
-- ---------------------------------------------------------------------------
create table if not exists public.memberships (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id),

    -- EXACTLY ONE of these is set. An org membership means "agency staff" and
    -- reaches every company that agency manages (computed through
    -- companies.managing_agency_id — never copied into per-company rows). A
    -- company membership means "this one client".
    organization_id uuid references public.organizations(id),
    company_id uuid references public.companies(id),

    role public.membership_role not null,

    -- Who issued the invitation, and whether it was ever accepted. `accepted_at`
    -- is written in the SAME transaction as the identity (LIC-T14): a confirmed
    -- email with no membership is a user who logs in and sees nothing, which
    -- reads as a broken product.
    invited_by uuid references public.users(id),
    accepted_at timestamptz,
    deactivated_at timestamptz,
    created_at timestamptz not null default now(),

    constraint memberships_exactly_one_scope check (
        (organization_id is not null and company_id is null)
        or (organization_id is null and company_id is not null)
    )
);

-- One membership per user per scope. Partial, because a NULL scope column must
-- not collide with another NULL: without the WHERE clause Postgres treats NULLs
-- as distinct and the constraint would silently never fire for the other kind.
create unique index if not exists uq_memberships_user_org
    on public.memberships (user_id, organization_id) where organization_id is not null;
create unique index if not exists uq_memberships_user_company
    on public.memberships (user_id, company_id) where company_id is not null;

-- Indexes the access function depends on. `has_company_access` filters on
-- user_id FIRST (design §1.3 measures 9,000ms -> 20ms for reversing the join
-- direction), so this index is not optional decoration.
create index if not exists idx_memberships_user on public.memberships (user_id);
create index if not exists idx_memberships_org on public.memberships (organization_id);
create index if not exists idx_memberships_company on public.memberships (company_id);

-- RLS enabled with no policies, matching every other table here: service-role
-- only until LIC-T10 writes the policies and LIC-T7 takes the API off that key.
alter table public.users enable row level security;
alter table public.organizations enable row level security;
alter table public.companies enable row level security;
alter table public.memberships enable row level security;
