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
