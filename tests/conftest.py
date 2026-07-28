"""Shared pytest configuration.

Force the network-free in-process judge notebook for the whole suite, so tests
never reach for Supabase (the production default backend). Reads of
``settings.JUDGE_CACHE_BACKEND`` happen at call time in ``make_judge_cache()``,
so mutating it here — before any test runs — is enough. Tests that need to
exercise a specific backend construct it directly.
"""

from __future__ import annotations

from src.config import settings

settings.JUDGE_CACHE_BACKEND = "memory"
# The subjective on-site judge makes live API calls; keep it off by default so
# run_site_audit tests stay offline. Tests that exercise it inject a fake judge.
settings.RUN_CONTENT_JUDGE = False
# The engine preflight probe sends one real query per engine. Off by default so a
# stub engine's recorded calls are measurement cells only — several tests assert on
# exactly which prompts an engine was asked. Tests that exercise the probe re-enable
# it explicitly (see tests/test_engine_liveness.py).
settings.ENGINE_PREFLIGHT = False
