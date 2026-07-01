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

# Google AI Overviews has no official API; capture it via a SERP provider
# (SearchApi.io). Without this key the AI-Overviews surface is skipped.
SEARCHAPI_API_KEY: str | None = os.getenv("SEARCHAPI_API_KEY")

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
# Comma-separated allowed CORS origins for the browser frontend. Default is the
# local Next.js dev origin; set GEO_CORS_ORIGINS to your deployed frontend URL(s).
# Never "*" in production — combined with the API key, only known origins script it.
GEO_CORS_ORIGINS: str = os.getenv("GEO_CORS_ORIGINS", "http://localhost:3000")
# Hard ceilings on a single uploaded audit, enforced before any LLM call, so an
# upload can't run an unbounded bill or OOM the server (financial/DoS guard).
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))  # 5 MB
MAX_QUERIES: int = int(os.getenv("MAX_QUERIES", "200"))
MAX_ENGINES: int = int(os.getenv("MAX_ENGINES", "8"))
MAX_RUNS_PER_QUERY: int = int(os.getenv("MAX_RUNS_PER_QUERY", "5"))
# Default repeats per (query, engine). The determinism baseline (2026-06-19,
# docs/isolation-determinism-plan.md) found the brand READ is 100% stable on
# openai/anthropic but wobbles on gemini + perplexity (~60% worst-brand), and the
# standard memory audit includes both — so K=5 is the data-driven default.
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
JUDGE_VERIFY: bool = os.getenv("JUDGE_VERIFY", "0").strip().lower() in ("1", "true", "yes")
# Verifier defaults to the accurate model: a Haiku verifier over-drops real flags
# (76% recall on gold — same gun-shy bias Action A found), so it would trade the
# protected recall for precision. Sonnet keeps the real contradictions.
JUDGE_VERIFIER_MODEL: str = os.getenv("JUDGE_VERIFIER_MODEL", JUDGE_MODEL)

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
