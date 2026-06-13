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

# The LLM judge — ONE held-constant model scores every answer from every engine,
# so cross-engine comparisons stay valid. Held constant > which model. Uses the
# Anthropic API (ANTHROPIC_API_KEY). Sonnet 4.6 is the economical-but-accurate
# default for high-volume runs (~40% cheaper than Opus); set JUDGE_MODEL to
# claude-opus-4-8 for max accuracy or claude-haiku-4-5 for max economy. Note:
# Claude is itself a measured surface — for stricter neutrality use a non-measured model.
JUDGE_MODEL: str = os.getenv("JUDGE_MODEL", "claude-sonnet-4-6")
