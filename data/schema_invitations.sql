-- LIC-T14 — provisioning an agency, and binding an invitation to a membership.
--
-- THE GAP THIS CLOSES. LIC-T2 added the `memberships` columns, LIC-T12/T13 build
-- email transport, LIC-T19 covers an EXISTING owner inviting staff. Nothing
-- creates the first organization or the first membership in it. Without this,
-- every other piece of the licence works and no agency can ever be onboarded.
--
-- WHY AN INVITATIONS TABLE AND NOT JUST A PENDING MEMBERSHIP ROW. `memberships`
-- references `public.users(id)`, which mirrors `auth.users` — and an invited
-- person has no identity until they confirm. A "pending membership" would need a
-- nullable `user_id`, which then has to be excluded from every access check
-- forever. The invitation is keyed by EMAIL precisely because that is the only
-- thing we know about them yet.
--
-- The critical property is atomicity. The skill's rule: "a confirmed email with
-- no membership is a broken product" — the user signs in and sees nothing. So
-- accepting is a single `security definer` function, not three round trips from
-- the API, because supabase-py speaks PostgREST and cannot open a transaction
-- across statements.

create table if not exists public.invitations (
    id uuid primary key default gen_random_uuid(),

    -- Lowercased on write. An invitation matched case-sensitively against the
    -- address Supabase Auth reports back is an invitation that silently never
    -- binds, and the symptom is the exact "logged in, sees nothing" failure the
    -- atomic accept exists to prevent.
    email text not null,

    -- EXACTLY ONE, mirroring `memberships`. An org invitation makes agency staff;
    -- a company invitation makes one client's own user.
    organization_id uuid references public.organizations (id),
    company_id uuid references public.companies (id),

    role public.membership_role not null,
    invited_by uuid references public.users (id),

    -- The sha256 of the invite token, never the token. Same rule as
    -- `revoked_share_tokens` and `report_share_tokens`: a readable table holding
    -- a working credential is a table that grants what it is meant to record.
    token_hash text not null unique,

    expires_at timestamptz not null,
    accepted_at timestamptz,
    accepted_user_id uuid references public.users (id),
    created_at timestamptz not null default now(),

    constraint invitations_exactly_one_scope check (
        (organization_id is not null and company_id is null)
        or (organization_id is null and company_id is not null)
    )
);

create index if not exists idx_invitations_email on public.invitations (lower(email));
create index if not exists idx_invitations_org on public.invitations (organization_id);

-- One PENDING invitation per (email, scope). Partial on `accepted_at is null` so
-- re-inviting someone who has since left is allowed, while double-sending does
-- not create two rows that both bind on confirm.
create unique index if not exists uq_invitations_pending_org
    on public.invitations (lower(email), organization_id)
    where accepted_at is null and organization_id is not null;
create unique index if not exists uq_invitations_pending_company
    on public.invitations (lower(email), company_id)
    where accepted_at is null and company_id is not null;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.invitations enable row level security;
alter table public.invitations force row level security;

-- Read-only, and narrow. An agency owner sees the invitations they have issued
-- into their own organization — that is the console's "pending invites" list.
-- Nobody reads by email: an invitee has no membership yet, so there is no
-- authenticated identity for whom this table is the right answer. Accepting goes
-- through the function below, which is `security definer` and does not consult
-- this policy at all.
--
-- No INSERT policy on purpose. Issuing an invitation is a platform-admin action
-- (a new agency) or a console action bounded by an entitlement check (staff),
-- and both run through code that enforces those rules before writing. A policy
-- permitting `authenticated` to insert here would be a second, weaker path to
-- the same privilege.
drop policy if exists invitations_issuer_read on public.invitations;
create policy invitations_issuer_read on public.invitations
    for select
    to authenticated
    using (
        organization_id is not null
        and private.is_org_member(organization_id)
    );

-- ---------------------------------------------------------------------------
-- accept_invitation — the whole point of the table
-- ---------------------------------------------------------------------------
-- ONE statement-scoped transaction that stamps the invitation and writes the
-- membership together. Either the user lands with a working tenant or nothing
-- happened; there is no interleaving that leaves an identity with no membership.
--
-- **Idempotent, because it has to be.** Supabase does not support multi-redemption
-- of a `token_hash`, and LIC-T13's interstitial exists precisely because corporate
-- scanners replay these URLs. A second call returns the same membership rather
-- than raising or writing a duplicate — enforced belt-and-braces by the
-- `on conflict do nothing` and by the `accepted_at is null` guard.
--
-- `security definer` because the caller is, by construction, a user with no
-- membership yet: they can satisfy no policy on `memberships`. The function is
-- the authorisation, and it is tightly bounded — it writes exactly the scope and
-- role the invitation row already named, and takes no other input.
create or replace function public.accept_invitation(
    invite_token_hash text,
    accepting_user_id uuid,
    accepting_email text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
    invite public.invitations%rowtype;
    membership_id uuid;
begin
    select * into invite
    from public.invitations
    where token_hash = invite_token_hash
    for update;

    if not found then
        raise exception 'invitation not found' using errcode = 'no_data_found';
    end if;

    -- Already redeemed. Return the membership that redemption created, so a
    -- replay is a success with the same answer rather than an error the user
    -- cannot act on. Matched on scope rather than remembered by id, so it stays
    -- correct even if the membership was recreated by hand.
    if invite.accepted_at is not null then
        select m.id into membership_id
        from public.memberships m
        where m.user_id = invite.accepted_user_id
          and m.organization_id is not distinct from invite.organization_id
          and m.company_id is not distinct from invite.company_id;
        return membership_id;
    end if;

    if invite.expires_at <= now() then
        raise exception 'invitation expired' using errcode = 'check_violation';
    end if;

    -- The address that confirmed must be the address invited. Without this, a
    -- token leaked out of an inbox would bind a membership to whoever redeemed
    -- it — which is the whole privilege the invitation is carrying.
    if lower(invite.email) <> lower(accepting_email) then
        raise exception 'invitation was issued to a different address'
            using errcode = 'check_violation';
    end if;

    insert into public.memberships
        (user_id, organization_id, company_id, role, invited_by, accepted_at)
    values
        (accepting_user_id, invite.organization_id, invite.company_id,
         invite.role, invite.invited_by, now())
    on conflict do nothing
    returning id into membership_id;

    if membership_id is null then
        -- The unique index caught a membership that already existed for this
        -- (user, scope). Adopt it rather than failing: the outcome the caller
        -- asked for is already true.
        select m.id into membership_id
        from public.memberships m
        where m.user_id = accepting_user_id
          and m.organization_id is not distinct from invite.organization_id
          and m.company_id is not distinct from invite.company_id;
    end if;

    update public.invitations
       set accepted_at = now(),
           accepted_user_id = accepting_user_id
     where id = invite.id;

    return membership_id;
end;
$$;

-- Not granted to `authenticated`. The accept runs on the server, from the
-- confirm handler, on the service-role client — the caller supplies a token hash
-- they got from an email, and the API is what establishes which user is
-- confirming. Exposing this to `authenticated` would let any signed-in user
-- redeem any invitation whose token they could guess or obtain.
revoke all on function public.accept_invitation(text, uuid, text) from public, authenticated;
