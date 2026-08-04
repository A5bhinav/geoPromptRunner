-- GEO Audit — the durable findings registry (audit-packaging-spec.md P0-T1).
--
--   python -m scripts.apply_schema data/schema_findings_registry.sql
--
-- Idempotent: `create ... if not exists` throughout. Safe to re-run.
--
-- WHY. `finding_id.assign_clusters` gives every accuracy claim a `cluster_id`,
-- and the only registry that ever existed was `InMemoryRegistry` — this process,
-- this run. Within one report that is enough, because near-duplicates are
-- unioned before the registry is consulted. Across CYCLES it is not: a model
-- that says "the Fort band costs $349" one week and "Fort retails at $349" the
-- next produces two `cluster_id`s for one finding.
--
-- That has not been urgent because the report's cards are keyed on THEME, which
-- is stable by construction, so the lifecycle state machine and the
-- accountability arithmetic have always been correct. What was missing is
-- per-CLAIM tracking: "this exact wrong statement has been live for five
-- cycles" is a different, sharper sentence than "the pricing theme is open", and
-- the fix-pack export wants the former.
--
-- SHAPE. One row per (client, cluster). Not per observation — observations live
-- on `judgments` and are re-derived on every render. This table holds only what
-- cannot be re-derived: which historical id a piece of text belongs to.

create table if not exists public.findings_registry (
    id uuid primary key default gen_random_uuid(),

    -- Scoped per client, always. Two clients can produce byte-identical claims
    -- ("does not offer a free trial") that are unrelated findings about
    -- unrelated companies, and a shared keyspace would merge them — which is
    -- both wrong and a cross-tenant leak of one client's text into another's
    -- report.
    client_name text not null,

    -- The id `assign_clusters` minted (uuid5 over the canonical text) or matched.
    cluster_id uuid not null,

    -- `finding_id.normalize()` output: lowercased, punctuation-folded, the text
    -- similarity is actually computed over. Stored rather than recomputed so a
    -- change to `normalize()` is visible as a miss rather than as a silent
    -- re-clustering of history.
    normalized text not null,

    -- The medoid — the phrasing a card shows. Kept so a registry hit can render
    -- without re-reading the run that produced it.
    representative text not null,

    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

-- One row per distinct normalized text per client. `remember()` is called once
-- per component per render, and a report re-render must not grow the table.
create unique index if not exists idx_findings_registry_text
    on public.findings_registry (client_name, normalized);

-- The lookup path: candidates for one client, most recent first.
create index if not exists idx_findings_registry_client
    on public.findings_registry (client_name, last_seen_at desc);

-- Trigram matching, so `lookup` can return genuine near-misses instead of "the
-- most recent N rows and hope". The caller re-scores every candidate with
-- rapidfuzz and applies DUP_THRESHOLD itself, so the index only has to be
-- RECALL-oriented: a near-miss returned costs one comparison, a near-miss missed
-- is a silent split that shows up as a resolved finding and a new one.
create extension if not exists pg_trgm;
create index if not exists idx_findings_registry_trgm
    on public.findings_registry using gin (normalized gin_trgm_ops);

-- Deliberately NO foreign key to audit_runs and no run_id column. A cluster's
-- identity outlives the run that first saw it — that is the entire point — and
-- project deletion (the one hard-delete path) removes runs, not history of what
-- a model once said. Rows here are scrubbed by client name if a client is
-- offboarded; see `db.forget_findings_for_client`.
