-- GEO Audit — Phase 4 operations tables (audit-packaging-spec.md P4-T1/T3/T6).
--
--   python -m scripts.apply_schema data/schema_operations.sql
--
-- Idempotent: `create ... if not exists` throughout. Safe to re-run.
--
-- WHY. Three Phase-4 mechanisms were built, tested and correct, and all three
-- computed a result and threw it away: QA review records, engine drift
-- fingerprints, and per-client config. Each of them is only useful as HISTORY —
-- "the reviewers disagreed more this month", "Perplexity's answers got 40%
-- shorter in June", "this client's core question set last changed in May" are
-- all questions about a series, and none of them can be asked of a value that
-- exists for the length of one render.
--
-- A fourth table follows the same logic for share-link revocation, which lived
-- in a process-local set and forgot everything on restart — a revoked link
-- coming back to life after a deploy is the one failure mode a revocation
-- mechanism may not have.

-- 1. QA review records (P4-T1/T2).
--
-- Append-only, and that is load-bearing: this is the audit trail behind every
-- overridden judge verdict. BOTH reviewer labels are stored even when they
-- agree, because recording only the reconciled answer throws away the
-- disagreement RATE — the number that says whether the labels themselves are
-- trustworthy.
create table if not exists public.review_records (
    id uuid primary key default gen_random_uuid(),
    run_id uuid,
    client_name text not null,

    cell_id text not null,
    stratum text not null,
    judge_label text not null,
    reviewer_a text not null,
    reviewer_b text not null,
    final_label text not null,
    -- agreed | overridden | escalated
    outcome text not null,

    -- The judge prompt in force WHEN THE CELL WAS JUDGED. Without it, "the judge
    -- feels off lately" cannot become a queryable regression: you cannot separate
    -- a prompt change from a model change from noise.
    prompt_fingerprint text not null,

    reviewed_at timestamptz not null,
    note text not null default '',
    created_at timestamptz not null default now()
);

-- One reconciliation per cell per prompt fingerprint. Re-reviewing the same cell
-- after a prompt change is a NEW record (the judge being reviewed is a different
-- judge); re-submitting the same reconciliation is not.
create unique index if not exists idx_review_records_cell
    on public.review_records (cell_id, prompt_fingerprint);

create index if not exists idx_review_records_client
    on public.review_records (client_name, reviewed_at desc);

-- 2. Engine drift fingerprints (P4-T3).
--
-- One row per (run, surface). Deliberately SHALLOW columns: anything deeper
-- starts encoding what the model said, and a fingerprint that moves when the
-- client's visibility moves cannot tell the two apart.
create table if not exists public.engine_fingerprints (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null,
    client_name text not null,
    run_date date not null,

    engine_name text not null,
    -- The pin as recorded at run time. A change here is a CERTAINTY that the
    -- instrument moved, not an inference from the distribution.
    model_id text not null default '',

    n_cells integer not null,
    n_answered integer not null,
    median_length double precision not null,
    mean_citations double precision not null,

    created_at timestamptz not null default now()
);

create unique index if not exists idx_engine_fingerprints_cell
    on public.engine_fingerprints (run_id, engine_name);

create index if not exists idx_engine_fingerprints_series
    on public.engine_fingerprints (client_name, engine_name, run_date desc);

-- 3. Per-client config as versioned data (P4-T6).
--
-- Create-only, like everything else here: a config CHANGE is a new row, never an
-- update. The fingerprint is what makes two cycles comparable, so overwriting a
-- config would silently rewrite the answer to "were these two runs measured the
-- same way".
create table if not exists public.client_configs (
    id uuid primary key default gen_random_uuid(),
    client_name text not null,

    -- `versioning.config_fingerprint()` over the whole config. Two runs with the
    -- same fingerprint were measured by the same instrument.
    fingerprint text not null,

    -- The config itself, as stored. JSON rather than columns because the shape is
    -- still moving and a migration per field would be the tail wagging the dog.
    config jsonb not null,

    -- Who/what wrote it, and why. A config change with no reason attached is the
    -- thing that makes an unexplained trend break unexplainable a year later.
    reason text not null default '',
    created_at timestamptz not null default now()
);

create unique index if not exists idx_client_configs_fingerprint
    on public.client_configs (client_name, fingerprint);

create index if not exists idx_client_configs_client
    on public.client_configs (client_name, created_at desc);

-- 4. Share-link revocation (P3-T4).
--
-- Revocation is a DENY LIST, not a delete: the token itself is stateless and
-- signed, so there is nothing to delete — the only way to stop honouring one is
-- to remember that we no longer do. Which means this table must outlive the
-- process, or a revoked link returns after the next deploy.
create table if not exists public.revoked_share_tokens (
    -- The token's jti (its unique id), not the token. Storing the signed token
    -- would put a working credential in a table whose whole purpose is that the
    -- credential no longer works.
    jti text primary key,
    run_id uuid,
    revoked_at timestamptz not null default now(),
    reason text not null default ''
);

-- Expired entries can be swept: once a token is past its own expiry the
-- signature check rejects it anyway, so the deny list only has to cover the
-- window between revocation and expiry.
create index if not exists idx_revoked_share_tokens_swept
    on public.revoked_share_tokens (revoked_at);
