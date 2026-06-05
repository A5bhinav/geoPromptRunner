#!/usr/bin/env bash
# Launch the GEO Audit API using the PROJECT venv (not conda base).
# The venv has all the dependencies; conda base does not, which is why running
# `python -m uvicorn ...` directly fails with ModuleNotFoundError (supabase,
# google-genai, etc.).
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "No .venv found. Create it and install deps:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

exec .venv/bin/python -m uvicorn src.api.app:app --reload --port "${PORT:-8000}"
