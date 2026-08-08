from __future__ import annotations

import os

from dotenv import load_dotenv

# Load variables from a local .env file if present. Real values live in `.env`
# (gitignored); `.env.example` documents the required keys.
load_dotenv()

# This module is the ONLY place allowed to call os.getenv. Every other module
# imports these names from here. Never log these values.
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
PERPLEXITY_API_KEY: str | None = os.getenv("PERPLEXITY_API_KEY")
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str | None = os.getenv("SUPABASE_KEY")
# The ANON (publishable) key. Unlike SUPABASE_KEY — which is the service-role key
# and bypasses RLS entirely — a connection made with this one is SUBJECT to RLS,
# which is the whole point: per-user reads carry the caller's access token on top
# of it so `auth.uid()` resolves and the policies apply (LIC-T7,
# src/storage/db._user_client). Using the service key with a user's token attached
# would still be service-role, and would look authenticated while bypassing every
# policy.
# Unset means per-user database access REFUSES rather than falling back — a
# fallback would silently restore the bypass on every request.
SUPABASE_ANON_KEY: str | None = os.getenv("SUPABASE_ANON_KEY")
# Direct Postgres connection, used ONLY to apply the DDL in data/*.sql — SUPABASE_KEY is
# a REST key and PostgREST cannot run `alter table`. Nothing in the runtime path reads
# this: every application read/write goes through the Supabase client in
# src/storage/db.py. Optional; unset simply means migrations are applied by hand.
# Like every other secret here it is read once, in this module, and never logged.
SUPABASE_DB_URL: str | None = os.getenv("SUPABASE_DB_URL")

# The WEBSITE's Supabase project (leads), which is a DIFFERENT database from the
# platform one above — see docs/factsheet-autogen-plan.md §12.1. Read by the
# fact-sheet worker only, and read-only: it polls `leads` for businesses that need
# a Tier-1 sheet.
#
# Use the `leads_reader` role from geoWebsite/scripts/leads-visibility.sql, never
# the postgres superuser and never the service_role key. That role is SELECT-only
# and RLS-scoped, which is what makes an automated reader of a prospect queue
# defensible. Unset simply means the worker does not run.
#
# The worker carries `leads.id` across as `lead_ref` and NOTHING else — no email,
# no phone (data/schema_factsheets.sql, "NO PROSPECT PII CROSSES OVER").
LEADS_DB_URL: str | None = os.getenv("LEADS_DB_URL")

# Google AI Overviews has no official API; capture it via a SERP provider
# (DataForSEO — see DATAFORSEO_LOGIN/PASSWORD below). SearchApi.io served this surface
# until 2026-07-28 and was removed: same data, $40/month floor instead of pay-as-you-go.

# --- Engine request tuning (shared by every engine adapter) ---
# Centralized here so the bounded-run policy lives in one place instead of being
# duplicated per engine. Generous enough not to time out legitimate slow
# generations, but far below the SDK defaults (~10 min) so one stuck request
# cannot stall the synchronous pipeline run. Overridable via env for tuning.
ENGINE_TIMEOUT_SECONDS: float = float(os.getenv("ENGINE_TIMEOUT_SECONDS", "60"))
ENGINE_MAX_RETRIES: int = int(os.getenv("ENGINE_MAX_RETRIES", "2"))
# Concurrency for the prompt runner. Each (query, engine, run) cell is an
# independent, I/O-bound API call, so the runner fans them out across threads
# instead of blocking on each in turn. ENGINE_CONCURRENCY caps total in-flight
# calls; ENGINE_PROVIDER_CONCURRENCY caps calls to any single provider so we
# parallelize across providers without tripping one provider's rate limit. Set
# ENGINE_CONCURRENCY=1 to restore fully-sequential behavior.
ENGINE_CONCURRENCY: int = int(os.getenv("ENGINE_CONCURRENCY", "12"))
ENGINE_PROVIDER_CONCURRENCY: int = int(os.getenv("ENGINE_PROVIDER_CONCURRENCY", "4"))
# Send one real throwaway query per engine before the fan-out and drop any surface
# that can't answer (src/pipeline/preflight.py). On by default because the failure it
# catches is silent and expensive: a deprecated model returns 404 on every call while
# the run still reports success. A provider listing cannot substitute — OpenAI's
# models.list still advertises ids that 404 on use. Set 0 to skip (tests, teaser).
ENGINE_PREFLIGHT: bool = os.getenv("ENGINE_PREFLIGHT", "1") not in ("0", "false", "False")
# Pin sampling low so repeated runs of the same query are reproducible — the
# methodology runs each query multiple times to average noise, not to amplify it.
ENGINE_TEMPERATURE: float = float(os.getenv("ENGINE_TEMPERATURE", "0"))
# Best-effort reproducibility seed, sent to providers that accept one (OpenAI,
# Gemini). Held constant across the query set and across cycles so two
# measurement runs differ only by what the model/web changed, not our sampling.
ENGINE_SEED: int = int(os.getenv("ENGINE_SEED", "42"))

# Payload audit log (isolation plan, Test E). When set, every outgoing engine
# request body (never auth headers or keys) is appended as one JSON line to this
# file so any run is reconstructable. Unset = debug logging only.
PAYLOAD_LOG_PATH: str | None = os.getenv("PAYLOAD_LOG_PATH")

# --- API security / abuse limits (the FastAPI layer) ---
# Shared API key required on every endpoint via the X-API-Key header. Unset =
# auth disabled (local dev only) — set GEO_API_KEY before exposing the API.
GEO_API_KEY: str | None = os.getenv("GEO_API_KEY")
# HMAC secret for share links (src/api/sharing.py). SEPARATE from GEO_API_KEY
# since LIC-T11, and the split is the whole point: those were one value doing two
# unrelated jobs — the API authentication credential AND the signature on every
# outstanding client report link. Retiring GEO_API_KEY as auth (LIC-T10) while
# they were the same value would have silently invalidated every link a client
# had been sent.
#
# Unset falls back to GEO_API_KEY, so the split is a no-op on existing
# deployments: links minted before it keep verifying and nothing has to be re-sent.
# The fallback is applied at CALL time in `sharing._secret()`, not seeded here —
# seeding at import would freeze whatever GEO_API_KEY happened to be when this
# module was first imported, which is both wrong after a key rotation and wrong in
# any test that swaps the credential.
SHARE_SIGNING_KEY: str | None = os.getenv("SHARE_SIGNING_KEY")
# Whether a token signed with the OLD secret (GEO_API_KEY) is still honoured on
# verify. On by default: this is the deprecation window that lets links minted
# before the split keep working. Set to 0 to close it — after which any link
# still signed with the old secret stops verifying, which is the intended final
# state and must be a deliberate act, not a side effect of a deploy.
SHARE_ACCEPT_LEGACY_SIGNATURE: bool = os.getenv(
    "SHARE_ACCEPT_LEGACY_SIGNATURE", "1"
).strip().lower() in ("1", "true", "yes")
# --- Per-user auth (LIC-T6). Migration is per ROUTE, on purpose. ---
# Comma-separated path prefixes whose routes require a verified Supabase JWT
# instead of GEO_API_KEY. Empty (the default) = nothing has migrated and the API
# behaves exactly as it did before.
#
# Per-route rather than a global switch because this is where every "assumed
# there is one tenant" bug surfaces, and it should surface loudly on one endpoint
# at a time rather than silently across all of them at once. A migrated route
# REFUSES the shared key and an unmigrated one refuses a JWT — no route accepts
# both, so there is never an ambiguous "which credential authorised this".
#
# Example: JWT_MIGRATED_ROUTES=/projects,/companies
JWT_MIGRATED_ROUTES: str = os.getenv("JWT_MIGRATED_ROUTES", "")
# How long a fetched JWKS key set is reused before re-fetching. Bounded so a
# ROTATED signing key is picked up without a redeploy — which is the reason keys
# are published at a discovery endpoint at all. 10 minutes.
JWKS_CACHE_SECONDS: int = int(os.getenv("JWKS_CACHE_SECONDS", "600"))
# Comma-separated allowed CORS origins for the browser frontend. Default is the
# local Next.js dev origin; set GEO_CORS_ORIGINS to your deployed frontend URL(s).
# Never "*" in production — combined with the API key, only known origins script it.
GEO_CORS_ORIGINS: str = os.getenv("GEO_CORS_ORIGINS", "http://localhost:3000")
# --- Cloudflare Turnstile (LIC-T15, the cheapest abuse gate) ---
# The site key is PUBLIC — it ships in the browser bundle, and the frontend reads
# its own copy from NEXT_PUBLIC_TURNSTILE_SITE_KEY (web/.env.local). It lives here
# too so the backend can serve it to a server-rendered form without a second
# source of truth.
# The SECRET key is server-side only: it is the credential for the siteverify call
# and must never reach the browser, a response body or a log line.
#
# Both unset = the gate is OFF, which is correct for local dev and for any
# environment that hasn't wired the widget yet. It must be SET before the public
# lead form is exposed, since Turnstile is the check that runs before the per-IP
# limits and the confirm-gated enqueue — i.e. before anything that costs money.
#
# For local testing use Cloudflare's dummy keys, which pass on any hostname and
# consume no real challenge volume: site 1x00000000000000000000AA with secret
# 1x0000000000000000000000000000000AA (always passes), or 2x00000000000000000000AB
# with 2x0000000000000000000000000000000AA (always fails).
TURNSTILE_SITE_KEY: str | None = os.getenv("TURNSTILE_SITE_KEY")
TURNSTILE_SECRET_KEY: str | None = os.getenv("TURNSTILE_SECRET_KEY")

# --- Redis (LIC-T15 rate limits + LIC-T16 job queue) ---
# ONE instance serves both: the per-IP/per-domain sliding window that runs after
# Turnstile and before anything that spends tokens, and the arq queue that moves a
# multi-minute audit off the request thread.
#
# This MUST be the TCP endpoint (`rediss://…:6379`), not Upstash's REST URL/token
# pair — arq speaks the Redis wire protocol and cannot use the HTTP API. Upstash
# exposes both on every plan; they are separate credentials, not two spellings of
# one.
#
# Unset = both features off, which is the current state (neither is built yet).
# Note this holds NOTHING durable: rate-limit counters expire by design and a
# queued job is transient. The system of record is always Postgres.
REDIS_URL: str | None = os.getenv("REDIS_URL")

# Hard ceilings on a single uploaded audit, enforced before any LLM call, so an
# upload can't run an unbounded bill or OOM the server (financial/DoS guard).
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))  # 5 MB
MAX_QUERIES: int = int(os.getenv("MAX_QUERIES", "200"))
MAX_ENGINES: int = int(os.getenv("MAX_ENGINES", "8"))
MAX_RUNS_PER_QUERY: int = int(os.getenv("MAX_RUNS_PER_QUERY", "5"))
# Default repeats per (query, engine), to average out nondeterminism.
#
# K=5 as of 2026-08-01. This restores the value the measurements actually argue for,
# reversing a same-day K=3 cost/breadth trade (kept below, since the trade is still the
# thing being weighed and may be taken again). The measurements:
#   - 2026-06-19 determinism baseline (docs/isolation-determinism-plan.md): the brand
#     READ is 100% stable on openai/anthropic but wobbles to ~60% worst-brand on
#     gemini + perplexity.
#   - RE-MEASURED 2026-07-28 after `openai` was repinned to a model that cannot take a
#     temperature (see openai_engine.MODEL), same probe (`scripts/run_determinism.py`,
#     k=5, one category query): label agreement openai min 60% / mean 80%, anthropic
#     min 60% / mean 92%. Both suggested K=5 — and the "100% stable on openai/anthropic"
#     half of the 2026-06 finding is FALSIFIED. anthropic is still at temperature 0 and
#     shows the same 60% worst-brand floor, so the wobble is not an artifact of the
#     repin. One query is a probe, not a baseline.
#
# Why K=5 and not K=3. The six-surface set is entirely RETRIEVAL surfaces, where the
# retrieved document set varies run to run independently of the model — so the noise K
# exists to average is higher here, not lower. At K=3 one flipped run moves a query's
# reading by 33 points instead of 20, and 2-of-3 vs 3-of-3 is not meaningfully
# distinguishable. The K=3 argument was a cost/breadth trade — 25 queries x 3 rather
# than 15 x 5 at an identical cell count, on the view that question coverage buys more
# than a third repeat. That trade is real but was not taken: a 60% worst-brand floor
# means a 3-run reading can be wrong, and breadth does not fix a per-query reading that
# is noise. Revisit against a widened determinism run, not against intuition.
#
# Note K=5 sits AT ``MAX_RUNS_PER_QUERY`` (5), so there is no headroom left for a
# measured local band above it — such a band will clamp and set ``exceeds_cap``
# (see ``pipeline/local_sampling.runs_for_trade``).
DEFAULT_RUNS_PER_QUERY: int = int(os.getenv("RUNS_PER_QUERY", "5"))
# Spend guard (rough estimated USD, engines + judge). A single audit estimated
# above MAX_AUDIT_COST_USD is rejected; once the running total of accepted audits
# this process would exceed MAX_TOTAL_SPEND_USD, further audits are rejected.
# The cumulative total resets when the API process restarts. Set either to 0 to
# disable that check. These are the hard guard against burning through credits.
MAX_AUDIT_COST_USD: float = float(os.getenv("MAX_AUDIT_COST_USD", "25"))
MAX_TOTAL_SPEND_USD: float = float(os.getenv("MAX_TOTAL_SPEND_USD", "200"))

# The LLM judge — ONE held-constant model scores every answer from every engine,
# so cross-engine comparisons stay valid. Held constant > which model. Uses the
# Anthropic API (ANTHROPIC_API_KEY). The judge runs once per unique answer
# (cached), so on a multi-engine/multi-run audit it is the dominant Anthropic
# cost. Sonnet 4.5 is the default: calibration (2026-06, Oura+Fort gold sets)
# showed it gives 100% accuracy-flag recall — it never misses a real client error
# — vs Haiku's ~67%, at equal present/prominence/framing agreement. Haiku 4.5 is
# ~3x cheaper ($1/$5 vs $3/$15 per MTok) and fine for the reading layer, but
# misses real flags; set JUDGE_MODEL=claude-haiku-4-5 only if cost dominates and
# flag recall doesn't matter.
# Note: Claude is itself a measured surface — for neutrality use a non-measured model.
JUDGE_MODEL: str = os.getenv("JUDGE_MODEL", "claude-sonnet-4-5-20250929")

# --- Two-tier cascade judge (opt-in; dev/iteration cost-saver) ---
# Action A (docs/judge-accuracy-plan.md §3.1) measured Haiku ≈ Sonnet on the
# structural reads (present/prominence/framing, within ~2pp) but with disqualifying
# flag recall (43% vs Sonnet's 95%). The cascade splits the work accordingly:
# Haiku does the cheap structural reads, Sonnet does the accuracy block (only when a
# fact sheet exists). OFF by default — the held-constant single-Sonnet judge stays
# the path for calibration/gold and paid deliverables (plan §5 guardrail). Enable
# per-run with `--cascade` or globally with JUDGE_CASCADE=1.
JUDGE_CASCADE: bool = os.getenv("JUDGE_CASCADE", "0").strip().lower() in ("1", "true", "yes")
# Cheap model for the structural pass (present/prominence/framing).
JUDGE_STRUCTURAL_MODEL: str = os.getenv("JUDGE_STRUCTURAL_MODEL", "claude-haiku-4-5")
# Accurate model for the accuracy-flag pass (verbatim fact-sheet contradictions).
JUDGE_ACCURACY_MODEL: str = os.getenv("JUDGE_ACCURACY_MODEL", JUDGE_MODEL)

# --- Adversarial flag verifier (opt-in; precision fix for queue #9) ---
# The judge over-flags (low precision): it raises omission/confirmation/sheet-silent
# "flags" its own prompt forbids. A prose gate only partly fixes this. The verifier
# reviews EACH proposed flag in isolation ("real contradiction? keep/drop") — a
# focused yes/no the model honours far better than a global instruction. It only
# removes flags (recall-safe: on any uncertainty or call failure it KEEPS), so it
# raises precision without lowering recall. Verification is a narrow judgment, so
# Haiku handles it well (unlike open-ended flag detection). Enable with `--verify`
# or JUDGE_VERIFY=1.
# DEFAULT ON since 2026-07-31. It was "0", and the only reason the accurate
# path shipped was a line in .env -- so any environment without that file
# (a fresh clone, CI, a container) silently produced the low-precision
# verdicts, and produced them looking exactly like the good ones. Failing
# toward the expensive-but-correct path is the right default for something
# whose output accuses a client of an error. Cost is one focused call per
# PROPOSED FLAG, so a clean answer pays nothing.
# Note: the `prejudge` skill refuses to dump while this is set -- pass
# JUDGE_VERIFY=0 explicitly for that step. A loud refusal beats the silent
# wrong default it replaces.
JUDGE_VERIFY: bool = os.getenv("JUDGE_VERIFY", "1").strip().lower() in ("1", "true", "yes")
# Verifier defaults to the accurate model: a Haiku verifier over-drops real flags
# (76% recall on gold — same gun-shy bias Action A found), so it would trade the
# protected recall for precision. Sonnet keeps the real contradictions.
JUDGE_VERIFIER_MODEL: str = os.getenv("JUDGE_VERIFIER_MODEL", JUDGE_MODEL)

# Run the Cat 3/4 subjective on-site checks (the LLM ContentJudge) during a site
# audit. OFF by default so an audit never surprise-spends ~6×pages of API — mirrors
# the query judge (collect answers first, then judge). The flow to get content
# scores for $0: run the audit (pages are crawled + stored regardless), warm the
# content notebook on the subscription with `/prejudge <run_id>`, then set
# RUN_CONTENT_JUDGE=1 — the judging is then all cache hits. Set =1 without a prewarm
# to just pay the API inline.
_run_content = os.getenv("RUN_CONTENT_JUDGE", "0").strip().lower()
RUN_CONTENT_JUDGE: bool = _run_content in ("1", "true", "yes")

# --- Grounded narrative generation (P4-T4) ---
# The ONE sanctioned LLM in the report layer, and it is OFF by default.
#
# A naive summary pass introduces a second hallucination surface in a product
# whose entire pitch is catching hallucinations. What makes it safe is not the
# generation step but `narrative.verify()`, a deterministic post-check that every
# number in the prose matches an enumerated fact — so the generator can only ever
# be as trustworthy as that guard, and the guard runs on every render whether or
# not this is on.
#
# Off by default because a report is meant to be free to re-render. With this on,
# every uncached render costs one small model call; with it off, the fallback
# writes wooden, provably-correct prose from the same facts.
_run_narrative = os.getenv("RUN_NARRATIVE", "0").strip().lower()
RUN_NARRATIVE: bool = _run_narrative in ("1", "true", "yes")
# A small, cheap model is right here: the task is filling a fixed skeleton from
# an enumerated fact list, not reasoning. Capability buys nothing when the output
# is verified against a closed set anyway.
NARRATIVE_MODEL: str = os.getenv("NARRATIVE_MODEL", "claude-haiku-4-5-20251001")

# Persistent judge cache ("the notebook"). A verdict is fully determined by (judge
# model, client, competitors, fact sheet, prompt, answer), so once an answer is
# judged it never needs re-judging — across resumes, re-runs, or cadence re-checks.
# Backend (see src/pipeline/judge_cache.py):
#   "supabase" (default) — shared table, so the subscription pre-judge (one machine)
#                          and the UI/report step (the server) share one notebook.
#   "memory"             — in-process dict, for tests (no network).
#   "none" / ""          — disabled: force a fresh judge pass.
JUDGE_CACHE_BACKEND: str = os.getenv("JUDGE_CACHE_BACKEND", "supabase")

# --- Cat 6 offsite research agent (all optional) ---
# Each offsite tool degrades gracefully to "unavailable" when its key is unset, so
# the agent runs with whatever data sources are configured (Wikidata needs none).
# Serper.dev — Google SERP data ($1/1k) used for the agent's search + review/
# listicle presence detection.
SERPER_API_KEY: str | None = os.getenv("SERPER_API_KEY")
# Reddit Data API (OAuth2 client-credentials) for community-presence search. A
# descriptive User-Agent is mandatory per Reddit's API rules.
REDDIT_CLIENT_ID: str | None = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET: str | None = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "geo-audit/0.1 (offsite research)")
# DataForSEO (HTTP Basic auth) — cheapest backlinks summary source (~$0.02/call).
DATAFORSEO_LOGIN: str | None = os.getenv("DATAFORSEO_LOGIN")
DATAFORSEO_PASSWORD: str | None = os.getenv("DATAFORSEO_PASSWORD")
# Agent model (reuses the judge model by default — a non-measured, capable model).
OFFSITE_AGENT_MODEL: str = os.getenv("OFFSITE_AGENT_MODEL", JUDGE_MODEL)
