-- GEO Audit — Fact-sheet intake sessions.
--
-- One row per conversation with a business owner. The session is WORKING STATE:
-- it is mutated on every answer, exactly as `audit_runs` is mutated by
-- `update_audit_run_progress`. It is not a core-data artifact and it is not the
-- sheet — approving a session WRITES a new `fact_sheets` row and leaves this one
-- behind as a record of how that sheet came to exist.
--
-- ON THE CREATE-ONLY INVARIANT. CLAUDE.md says core-data writes are create-only
-- and the only delete path is explicit project deletion. A session is working
-- state, not core data, so it is not covered by that rule — but it has two
-- different endings and they are not interchangeable:
--
--   `state = 'abandoned'`  the OWNER stopped answering. Kept, because it is the
--                          only signal we get that a card is too hard or too
--                          invasive, and a deleted row teaches nothing.
--   deleted                an OPERATOR discarding a conversation they opened by
--                          mistake. No drop-off to learn from, and the row is
--                          holding the domain's uq_intake_sessions_live slot.
--
-- The queue offers the second, because the operator is who is looking at it.
-- Project deletion also removes sessions, which is what stops this becoming the
-- orphan surface Storage blobs already are.
--
-- WHICH PROJECT. The PLATFORM project (geoPromptRunner/.env), same as
-- schema_factsheets.sql. RLS on with no policies: service_role only, so the
-- publishable key cannot read a half-finished intake.
--
-- Run: python -m scripts.apply_schema data/schema_factsheet_intake.sql
-- Idempotent: safe on a fresh project or an existing one.

create table if not exists factsheet_intake_sessions (
  id                       uuid primary key default gen_random_uuid(),

  -- The registrable domain, already normalized — same contract as
  -- fact_sheets.domain. It is the identity of the conversation, because a
  -- session exists before any sheet row does.
  domain                   text not null,

  -- The DRAFT sheet this intake started from, when there was one. Nullable: an
  -- intake can be opened for a domain the crawler has never seen, and that is
  -- the case where the owner's answers are the only thing on the sheet.
  fact_sheet_id            uuid references fact_sheets(id) on delete set null,

  business_kind            text not null,

  -- not_started | in_progress | awaiting_review | approved | abandoned.
  -- Deliberately NOT the same machine as fact_sheets.state — one tracks a
  -- conversation, the other tracks a document, and merging them would make
  -- "approved" ambiguous.
  state                    text not null default 'in_progress',

  current_question_id      text,

  -- {"Q-LOC-04": {"value": "no", "raw": "No", "skipped": false, "answered_at": "..."}}
  -- Idempotent per question id: re-answering overwrites, which is what makes
  -- Back and the review screen's inline edits free.
  answers                  jsonb not null default '{}'::jsonb,

  -- key -> {value, source_url, source_kind, confidence} from the draft sheet's
  -- claims. What lets a card be a one-tap confirm instead of a blank field.
  prefill                  jsonb not null default '{}'::jsonb,

  -- Aliases, trade, city, region, competitors. NOT claims — matcher and
  -- query-generator inputs (plan §4.4).
  run_inputs               jsonb not null default '{}'::jsonb,

  query_set                jsonb,
  csv_text                 text,
  lint                     jsonb,

  approved_fact_sheet_id   uuid references fact_sheets(id) on delete set null,

  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  completed_at             timestamptz
);

-- ONE LIVE INTAKE PER DOMAIN, for the same reason uq_factsheet_jobs_inflight
-- exists: two people starting the same sheet in the same minute is ordinary,
-- and the loser should be handed the EXISTING session rather than a second one
-- that will silently diverge. Partial, so a domain can accumulate any number of
-- approved and abandoned sessions.
create unique index if not exists uq_intake_sessions_live
  on factsheet_intake_sessions (domain)
  where state in ('in_progress', 'awaiting_review');

create index if not exists idx_intake_sessions_domain
  on factsheet_intake_sessions (domain, created_at desc);

create index if not exists idx_intake_sessions_state
  on factsheet_intake_sessions (state, updated_at desc);

alter table factsheet_intake_sessions enable row level security;
