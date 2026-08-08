-- LIC-T18/T19 — let an agency actually ADD and RELEASE a client company.
--
-- THE BUG THIS FIXES, found by testing rather than by reading. LIC-T10 gave
-- `companies` one `for all` policy whose `with check` is
-- `private.has_company_access(id)`. For an INSERT that predicate can never be
-- true: `has_company_access` is `stable`, so it runs against the statement's
-- snapshot and cannot see the row being inserted. Verified against the live
-- database — an AGENCY_OWNER inserting a company stamped with their OWN agency
-- id gets `InsufficientPrivilege`, and so does an insert with no agency at all.
--
-- That made two things in the spec impossible as written: LIC-T19's "adding a
-- client is one INSERT with managing_agency_id set", and LIC-T18's intake flow,
-- where an agency onboarding a new client reaches `db.ensure_company()` and has
-- to create the tenant before there is anything to have access to.
--
-- WHY NOT JUST USE THE SERVICE ROLE. Because "access is computed at query time,
-- never copied" is the design's load-bearing rule, and routing client creation
-- through a service-role endpoint moves the authorisation decision out of the
-- database and into whichever handler remembers to make it. The entitlement
-- check (slot limits, LIC-T4) still belongs at the API boundary — the skill is
-- explicit that the frontend gate is UX and the API check is the security
-- boundary — but "may this user create a client under this agency at all" is a
-- tenancy question, and tenancy questions are answered by policies here.

-- ---------------------------------------------------------------------------
-- private.is_org_member — membership in an ORGANIZATION, not reach into a company
-- ---------------------------------------------------------------------------
-- Distinct from `has_company_access`, which answers "can I reach this company".
-- This answers "do I belong to this agency", which is the only question an
-- INSERT can ask: at insert time the company does not exist yet, so the agency
-- named on the incoming row is the only thing there is to check.
--
-- Same disciplines as `has_company_access`, and for the same measured reasons:
-- `security definer` so a policy calling it does not trigger RLS evaluation on
-- `memberships` for every row; `set search_path = ''` so the function body
-- cannot be captured by a caller's search path; `(select auth.uid())` in the
-- subquery form so it is evaluated once as an InitPlan rather than per row; and
-- `accepted_at is not null`, so a pending invitee cannot create clients before
-- proving they control the invited mailbox.
create or replace function private.is_org_member(target_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select
        private.is_platform_admin()
        or exists (
            select 1
            from public.memberships m
            join public.users u on u.id = m.user_id
            where m.user_id = (select auth.uid())
              and m.organization_id = target_organization_id
              and m.deactivated_at is null
              and m.accepted_at is not null
              and u.deactivated_at is null
        );
$$;

grant execute on function private.is_org_member(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Adding a client
-- ---------------------------------------------------------------------------
-- A SECOND permissive policy, not a replacement. Permissive policies of the same
-- command are OR'd, so this widens INSERT only, and every other command still
-- goes through the `has_company_access` policy LIC-T10 wrote.
--
-- `managing_agency_id is not null` is not decoration: without it this policy
-- would let any authenticated user create an unowned company, since
-- `is_org_member(null)` is null and the whole check would collapse to
-- "authenticated". A company created here is always somebody's client.
drop policy if exists companies_agency_insert on public.companies;
create policy companies_agency_insert on public.companies
    for insert
    to authenticated
    with check (
        managing_agency_id is not null
        and private.is_org_member(managing_agency_id)
    );

-- ---------------------------------------------------------------------------
-- SECURITY FIX: LIC-T10's `with check` on `companies` does not constrain UPDATE
-- ---------------------------------------------------------------------------
-- `tenant_access` is one `for all` policy whose `with check` is
-- `has_company_access(id)`. On an UPDATE that predicate is **vacuous**: the
-- function is `stable`, so it reads `companies` from the statement's snapshot —
-- the OLD row — and therefore re-answers `using` rather than testing the new
-- state. Whatever the update sets `managing_agency_id` to, the check passes.
--
-- Measured against the live database: an AGENCY_OWNER could reassign a company
-- it manages to an organization it has no membership in — handing a client (and
-- every audit, report and share link under it) to a third party. `using` still
-- stops it touching a company it does not already manage, so this is "give away
-- your own client", not "steal someone else's". It is still a cross-tenant write
-- that no policy intended to allow.
--
-- The fix cannot be an additional narrower policy, because permissive policies
-- are OR'd and the vacuous one would keep admitting everything. `companies` gets
-- explicit per-command policies instead, and `schema_tenancy_rls.sql` no longer
-- includes it in the loop. Note the asymmetry that makes this work: `using`
-- reads the table by id and is correct precisely BECAUSE it means the old row,
-- while `with check` must test the incoming row's own columns and nothing else.
drop policy if exists tenant_access on public.companies;
drop policy if exists companies_agency_release on public.companies;

drop policy if exists companies_select on public.companies;
create policy companies_select on public.companies
    for select
    to authenticated
    using (private.has_company_access(id));

-- Releasing a client — the client going direct. LIC-T19's acceptance case:
-- reparenting to null removes agency reach on the next call. `using` requires
-- the agency to reach the company BEFORE the update, so it can only release one
-- it already manages; `with check` permits exactly two landing states — unowned,
-- or owned by an agency the caller belongs to (a client moving between two
-- agencies they staff). Handing it to a third party is refused.
drop policy if exists companies_update on public.companies;
create policy companies_update on public.companies
    for update
    to authenticated
    using (private.has_company_access(id))
    with check (
        managing_agency_id is null
        or private.is_org_member(managing_agency_id)
    );

-- Storage is create-only and the one delete path is explicit project deletion,
-- which runs outside a request on the service-role client. This policy exists so
-- the table is not left with DELETE unpoliced rather than because anything uses
-- it.
drop policy if exists companies_delete on public.companies;
create policy companies_delete on public.companies
    for delete
    to authenticated
    using (private.has_company_access(id));
