-- GEO Audit — run provenance columns (the two that never landed, plus the two
-- the fact-sheet plan needs).
--
--   python -m scripts.apply_schema data/schema_run_provenance.sql
--
-- Idempotent: every statement is `add column if not exists`. Safe to re-run.
--
-- WHY THIS IS A SEPARATE FILE. `data/schema_ui.sql` already declares
-- `judge_model` and `location` in its `alter` block, but the 2026-07-28
-- build-log records them as backed up and unapplied — there was no runner, and
-- the manual SQL-editor step did not happen. Re-running the whole of
-- schema_ui.sql to pick them up would also re-run its create-tables and index
-- statements against a live database, which is a bigger blast radius than the
-- two columns warrant. This file is the narrow catch-up.

-- 1. Which judge produced this run's verdicts. Written by db.save_judgments
--    from Judge.identity. Without it the report prints "model not recorded for
--    this run", which is honest but is a loss of provenance every time.
alter table public.audit_runs add column if not exists judge_model text;

-- 2. SearchApi canonical location NAME ("Berkeley,California,United States") for
--    a service-area business. NULL for nationally-marketed products. An
--    interrupted LOCAL run rebuilds its RunConfig from this row on resume;
--    without the column the resumed half runs un-localized and quietly mixes two
--    markets into one measurement.
alter table public.audit_runs add column if not exists location text;

-- 3-4. Which fact sheet this run was judged against.
--
--    `audit_runs.fact_sheet` already stores the sheet TEXT, and that stays — it
--    is the frozen snapshot, and a run must record what it was judged against
--    even after the sheet is later corrected. These two columns add the pointer
--    BACK to the living record in public.fact_sheets, which the text alone
--    cannot give you: without them nothing can answer "which version was this,
--    and what changed since" (docs/factsheet-autogen-plan.md §6).
--
--    Deliberately NOT a foreign key. fact_sheets may not exist yet (this file
--    must apply on its own), and a run's provenance should survive the deletion
--    of the sheet it referenced — a dangling id is a better record than a
--    nulled one.
alter table public.audit_runs add column if not exists fact_sheet_id uuid;
alter table public.audit_runs add column if not exists fact_sheet_version int;

-- Reporting reads these per run; an index only pays off on the reverse lookup
-- ("every run judged against sheet X"), which is the diff workflow in §6.
create index if not exists idx_audit_runs_fact_sheet on public.audit_runs (fact_sheet_id)
    where fact_sheet_id is not null;
