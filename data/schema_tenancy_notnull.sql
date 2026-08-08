-- GEO Audit — tenancy, part 4: contract `company_id` to NOT NULL (LIC-T9).
--
-- Apply with:  python -m scripts.apply_schema data/schema_tenancy_notnull.sql
--
-- ORDER MATTERS, AND THIS FILE IS LAST. Three things must already be true:
--   1. data/schema_tenancy.sql applied (the columns exist),
--   2. scripts/backfill_companies.py run to zero NULLs (verified below), and
--   3. the WRITE paths set `company_id` (db.ensure_company / db._stamp_tenant,
--      covered by tests/test_tenanted_writes.py).
-- Without (3) this constraint does not protect data — it breaks the next audit.
-- The backfill only ever tenanted rows that already existed.
--
-- WHY NO `CHECK ... NOT VALID` + `VALIDATE CONSTRAINT` DANCE. LIC-T9 offers that
-- split for large tables, to avoid a long exclusive lock. The LIC-T0 survey found
-- the biggest table here is `query_citations` at 8,969 rows; a plain SET NOT NULL
-- is milliseconds at that size. Re-check before assuming it stays that way — past
-- roughly a million rows the split is worth the extra migration.
--
-- The whole file is one transaction (scripts/apply_schema), so a table that still
-- has a NULL aborts everything and leaves the schema exactly as it was.

-- ---------------------------------------------------------------------------
-- Verify before contracting
-- ---------------------------------------------------------------------------
-- Belt and braces: SET NOT NULL would fail on its own if a NULL remained, but the
-- error names a constraint rather than the problem. This names the table AND the
-- count, which is what an operator actually needs at 2am.
do $$
declare
    t text;
    n bigint;
    tenant_tables text[] := array[
        'audit_runs', 'query_results', 'query_citations', 'judgments',
        'local_pack_entities', 'site_audit_page', 'site_audit_check',
        'site_audit_offsite_finding', 'teasers', 'fact_sheets', 'fact_claims',
        'factsheet_intake_sessions'
    ];
begin
    foreach t in array tenant_tables loop
        if to_regclass('public.' || t) is null then
            raise notice 'skipping %: table does not exist in this project', t;
            continue;
        end if;
        execute format('select count(*) from public.%I where company_id is null', t) into n;
        if n > 0 then
            raise exception
                '% still has % row(s) with a NULL company_id. Run '
                '`python -m scripts.backfill_companies` first; if the rows are '
                'fixture data, remove this table from the list below and record '
                'that decision in docs/build-log.md.', t, n;
        end if;
    end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Contract
-- ---------------------------------------------------------------------------
do $$
declare
    t text;
    tenant_tables text[] := array[
        'audit_runs', 'query_results', 'query_citations', 'judgments',
        'local_pack_entities', 'site_audit_page', 'site_audit_check',
        'site_audit_offsite_finding', 'teasers', 'fact_sheets', 'fact_claims',
        'factsheet_intake_sessions'
    ];
begin
    foreach t in array tenant_tables loop
        if to_regclass('public.' || t) is not null then
            execute format('alter table public.%I alter column company_id set not null', t);
        end if;
    end loop;
end $$;

-- ---------------------------------------------------------------------------
-- Deliberately left NULLABLE
-- ---------------------------------------------------------------------------
-- `audit_deliverables` — `run_id` is itself nullable (a deliverable can be built
--   by hand from no run), so there is no path that can guarantee a tenant. It
--   holds zero rows today; revisit when the paid deliverable is written from the
--   agency console, which will supply one.
-- `client_configs`, `findings_registry` — DECLARED in data/*.sql but never applied
--   to this project, and keyed by `client_name` rather than by run or domain, so a
--   name shared by two companies matches neither. They stay nullable until they
--   exist and their writers can name a tenant.
