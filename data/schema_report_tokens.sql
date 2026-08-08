-- LIC-T17 — report share links become ROWS, not just signatures.
--
-- WHY THIS TABLE EXISTS. Design §3.6 weighed four options for delivering a
-- confidential report to someone with no account, and rejected the stateless
-- HMAC precisely because it is revocable only by rotating the signing secret —
-- which kills every outstanding link at once. What shipped in P3-T4 was that
-- rejected option, with a `revoked_share_tokens` deny list bolted on to
-- compensate. The deny list works, but it can only ever answer "is this token
-- dead"; it cannot answer "which links exist for this client", "who has opened
-- this report", or "stop this client's links now that they have been
-- offboarded", because a stateless token carries a `run_id` and nothing else.
--
-- WHAT IS KEPT. The signature, the TTL, the optional password and per-token
-- revocation surviving a deploy all still work exactly as before — this is
-- additive. A token minted before this migration carries a valid signature and
-- no row, and is still honoured (see `sharing.verify_share_token` and the
-- legacy path in `app.shared_report`). That is deliberate: every client report
-- link already in an inbox has to keep working, the same requirement LIC-T11
-- had for the signing-secret split.
--
-- WHAT IS NEW. `company_id` on the row. That single column is what makes "this
-- client's links stop working when their membership is deactivated" expressible
-- at all — it cannot be reconciled against a token whose entire payload is a run
-- id. `first_viewed_at` and `view_count` give the access log the design asked
-- for, and answer the question every agency asks first: did they read it.

-- ---------------------------------------------------------------------------
-- report_share_tokens
-- ---------------------------------------------------------------------------
create table if not exists public.report_share_tokens (
    -- The token's id (its jti), NOT the token. Same rule as
    -- `revoked_share_tokens`: storing the signed token would put a working
    -- credential in the table, and this table is readable by every agency
    -- staffer who can reach the company. The signature stays in the client's
    -- inbox and nowhere else.
    token_id text primary key,

    run_id uuid not null references public.audit_runs (id) on delete cascade,

    -- The tenant. NOT NULL, unlike the retrofitted `company_id` columns
    -- elsewhere: this table is new, so every row it will ever hold is written by
    -- code that already knows the tenant. A share link that cannot name the
    -- client it belongs to is the exact gap this task exists to close.
    company_id uuid not null references public.companies (id),

    expires_at timestamptz not null,

    -- sha256 of the share password, or '' for an unprotected link. Mirrors what
    -- the signed payload carries so the row alone is enough to verify; the
    -- password itself is never stored or transmitted.
    password_hash text not null default '',

    -- Who minted it. Nullable: links minted on the shared-key path (the founders
    -- running a manual audit) have no user behind them by construction.
    created_by uuid references public.users (id),
    created_at timestamptz not null default now(),

    -- Revocation is a timestamp, not a boolean: "when was this withdrawn" is the
    -- question you actually ask when a client says a link leaked.
    revoked_at timestamptz,
    revoked_reason text not null default '',

    -- The access log. `first_viewed_at` is stamped once and never overwritten —
    -- "when did it first land" and "how many times since" are different
    -- questions, and one column cannot answer both.
    first_viewed_at timestamptz,
    view_count integer not null default 0
);

-- The agency console lists links per client; the report route looks them up by
-- run. Both are index scans, not sequential ones.
create index if not exists idx_report_share_tokens_company
    on public.report_share_tokens (company_id);
create index if not exists idx_report_share_tokens_run
    on public.report_share_tokens (run_id);
-- Expired rows can be swept: past its own expiry the signature check rejects the
-- token anyway, so a live row only has to cover the window before that.
create index if not exists idx_report_share_tokens_expiry
    on public.report_share_tokens (expires_at);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
-- FORCE, not just ENABLE: the table owner bypasses RLS without it, which is the
-- failure mode that makes a policy look applied while doing nothing.
alter table public.report_share_tokens enable row level security;
alter table public.report_share_tokens force row level security;

-- One permissive policy, FOR ALL, TO authenticated — the same shape as every
-- other tenant table (LIC-T10). Both `using` and `with check` carry the same
-- predicate: `using` governs which links are visible, `with check` stops a
-- member of tenant A minting a link stamped with tenant B's company_id, which
-- would be writing INTO another tenant rather than reading from it.
drop policy if exists report_share_tokens_tenant on public.report_share_tokens;
create policy report_share_tokens_tenant on public.report_share_tokens
    for all
    to authenticated
    using (private.has_company_access(company_id))
    with check (private.has_company_access(company_id));

-- NOTE: the anonymous visitor holding a valid link satisfies NO policy here, and
-- must not — they have no `auth.uid()`. That read runs through the service-role
-- client, scoped to the single token id the visitor presented, and is named in
-- the allowlist in `src/storage/db.py::_execute`. It must never widen into a
-- general service-role read path: the token row IS the authorisation.
