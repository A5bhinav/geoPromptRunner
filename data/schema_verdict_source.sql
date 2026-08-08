-- GEO Audit — verdict provenance (LIC-T20).
--
-- Apply with:  python -m scripts.apply_schema data/schema_verdict_source.sql
--
-- WHAT THIS CLOSES. The prejudge flow writes verdicts into the PRODUCTION cache
-- keyspace — that is exactly what makes "warm on the subscription, then judge for
-- $0" work across machines. The cost is that a subscription-judged verdict and an
-- API-judged verdict were byte-identical downstream: same table, same shape, same
-- report. `verdict_source` appeared nowhere in src/ or data/ before this file.
--
-- That is fine while the only readers are the two founders, who know what they
-- warmed. It stops being fine the moment an agency triggers a run: the agency is
-- paying for output from the held-constant temp-0 API judge that calibration was
-- measured against, and had no way to check it got that.
--
-- NOT PART OF ANY CACHE KEY. `judge_cache.key` is a content address over (model,
-- prompt fingerprint, client, competitors, fact sheet, prompt, answer). Adding
-- provenance to it would split the keyspace and break the prejudge flow outright.
-- This is metadata ABOUT the row. No `_PROMPT_LAYOUT` bump is needed or wanted.

-- ---------------------------------------------------------------------------
-- The notebook: which judge wrote each cached verdict
-- ---------------------------------------------------------------------------
-- No DEFAULT, deliberately. A default of 'api' would silently retag every
-- pre-existing row — including the many that came from the subscription — as the
-- one value that is sellable. NULL reads back as 'unknown' and is refused for
-- delivery, which is the safe direction and is cheaply fixed by re-judging.
alter table public.judge_cache add column if not exists verdict_source text;

alter table public.judge_cache drop constraint if exists judge_cache_verdict_source_check;
alter table public.judge_cache add constraint judge_cache_verdict_source_check
    check (verdict_source is null
           or verdict_source in ('api', 'prejudge', 'opus_dev', 'unknown'));

-- ---------------------------------------------------------------------------
-- Per-judged-answer, and the per-run rollup
-- ---------------------------------------------------------------------------
-- Per JUDGMENT, not just per run, because a single run is routinely MIXED: a
-- partly-warm notebook means some answers come back from the subscription and the
-- rest are judged live. The gate has to see the mixture.
alter table public.judgments add column if not exists verdict_source text;

alter table public.judgments drop constraint if exists judgments_verdict_source_check;
alter table public.judgments add constraint judgments_verdict_source_check
    check (verdict_source is null
           or verdict_source in ('api', 'prejudge', 'opus_dev', 'unknown'));

-- The rollup the delivery gate reads: the DISTINCT sorted set of sources present
-- in this run's verdicts, e.g. ["api"] or ["api", "prejudge"]. Written by
-- `db.save_judgments` at the same moment as `judge_model`, and for the same
-- reason — a run is routinely judged later than it is created, so run-creation
-- time knows nothing about this.
alter table public.audit_runs add column if not exists verdict_sources jsonb;

-- Finding the runs that are not deliverable is a maintenance question we will
-- actually ask ("which stored runs would fail the gate?"), so it gets an index.
create index if not exists idx_judgments_verdict_source
    on public.judgments (verdict_source);
