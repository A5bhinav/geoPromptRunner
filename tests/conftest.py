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
