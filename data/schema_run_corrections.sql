-- GEO Audit — correction runs (audit-packaging-implementation.md §5.5).
--
--   python -m scripts.apply_schema data/schema_run_corrections.sql
--
-- Idempotent: every statement is `add column if not exists`. Safe to re-run.
--
-- WHY. A run that FINISHES with dead engines is terminal — `list_resumable_runs`
-- only picks up `running`/`queued`, and `done_cells` treats an attempted-but-
-- unanswered cell as complete. Albert Nahman's 2026-07-28 cycle shows the cost
-- of that: four full runs (30, 25, 35, 40 cells) because there was no way to top
-- up the broken one, only to re-run the whole thing.
--
-- A correction is a NEW immutable run that reuses the parent's good answers and
-- pays only for the cells that failed. It is not an edit. Filling a stored
-- `response: NULL` in place would mutate a run someone may already have been
-- shown, which both the create-only storage rule (CLAUDE.md) and the
-- "never silently rewrite history" packaging rule forbid. The original stays
-- exactly as it was; the corrected measurement is a separate row that says what
-- it supersedes.

-- 1. What kind of run this is.
--
--    'baseline'   — a normal run. The default, so every existing row is correct
--                   without a backfill.
--    'correction' — a re-measurement of an earlier run's failed cells. Carries
--                   the parent's answered cells verbatim plus the newly-filled
--                   ones, so it renders standalone with no join.
alter table public.audit_runs
    add column if not exists run_kind text not null default 'baseline';

-- Deliberately a CHECK and not an enum: adding a value to a Postgres enum needs
-- a migration and a lock, while widening a check constraint does not.
do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'audit_runs_run_kind_check'
    ) then
        alter table public.audit_runs
            add constraint audit_runs_run_kind_check
            check (run_kind in ('baseline', 'correction'));
    end if;
end $$;

-- 2. Which run this one corrects. NULL on a baseline.
--
--    NOT a foreign key, matching `fact_sheet_id` above it: a run's lineage should
--    survive the deletion of the project it belonged to, and a dangling id is a
--    better record than a nulled one.
--
--    This column is also what stops a correction being mistaken for a new CYCLE.
--    The prior-run resolver skips any run that something supersedes, so a
--    corrected week compares against the previous WEEK rather than against its
--    own broken first attempt — which would report the repair as client progress.
alter table public.audit_runs add column if not exists supersedes_run_id uuid;

-- The reverse lookup ("has this run been superseded?") runs once per report, per
-- candidate prior run. Partial, because the vast majority of rows are baselines
-- with a NULL here.
create index if not exists idx_audit_runs_supersedes
    on public.audit_runs (supersedes_run_id)
    where supersedes_run_id is not null;
