"""Google AI Mode via DataForSEO — the Google surface that answers *every* intent.

The problem this solves: ``google_ai_overviews`` is absent by construction on the
queries that matter most to a local client. Google shows an AI Overview on ~15% of
local-intent SERPs, and 0 of 5 in run e186c524 — which is why ``engine_routing`` stops
asking it those queries at all. That leaves the Google *answer* surface unmeasured for
the buying moment; only the local pack covers it, and a pack is a business list, not an
answer.

**AI Mode is Google's conversational answer surface**, and unlike AI Overviews it
responds to whatever it is asked. So it needs no routing skip and reports ~100% coverage
across all four local buckets, where AI Overviews reports ~10%.

Priced per SERP with no monthly floor: $0.0012 standard queue / $0.0024 priority /
$0.004 live. This uses **live**, because the pipeline is synchronous — the queued tiers
return a task id to poll for, which the ``BaseEngine.query`` contract has nowhere to put.

Verified against a live response (2026-07-28, "best plumber in Berkeley"); the captured
body is pinned at ``tests/fixtures/dataforseo_ai_mode.json``. ``location_name`` is
REQUIRED — the same request with ``location_code`` came back with zero tasks, and with no
location at all it was rejected outright.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Literal

import httpx

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.dataforseo_ai_overviews import _status_message, parse_ai_overview
from src.engines.payload_log import record_payload

__all__ = ["DataForSEOAIModeEngine", "DATAFORSEO_AI_MODE_URL", "parse_ai_mode"]

logger = logging.getLogger(__name__)

DATAFORSEO_AI_MODE_URL = "https://api.dataforseo.com/v3/serp/google/ai_mode/live/advanced"
TIMEOUT_SECONDS = 60.0


def parse_ai_mode(data: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Extract (answer text, citation urls) from a DataForSEO AI Mode body.

    Delegates to ``parse_ai_overview``: the two endpoints return the **same element
    shape**. Verified live on 2026-07-28 — the AI Mode result's item is literally
    ``"type": "ai_overview"``, carrying the whole answer in top-level ``markdown``, the
    same prose re-split across ``items`` (``ai_overview_element``, plus
    ``ai_overview_table_element`` for the ranked tables AI Mode likes to emit), and a
    top-level ``references`` array.

    Kept as a named function rather than an alias so the AI Mode engine reads clearly and
    so this comment has somewhere to live. Sharing one parser means the double-counting
    fix — the first version returned 8,778 characters where the real answer is 2,835 —
    can only ever be made once.
    """
    return parse_ai_overview(data)


class DataForSEOAIModeEngine(BaseEngine):
    """Google AI Mode, captured via DataForSEO's live endpoint."""

    ENGINE_NAME: str = "google_ai_mode"
    # SERP capture: no model parameter, so it is excluded from run metadata by
    # `orchestrator.engine_models` and exempt from the dated-pin rule.
    MODEL_ID: str = ""
    # SERP capture: Google's surface, not a model we sample — nothing to pin.
    SAMPLING: Literal["pinned", "default", "none"] = "none"

    def __init__(self, location: str | None = None) -> None:
        """``location`` is a DataForSEO ``location_name`` — "Berkeley,California,United States".

        Same string the rest of the stack already stores. One engine instance measures
        one market; ``None`` means an unpinned locale, which is not a local measurement.
        """
        if not (settings.DATAFORSEO_LOGIN and settings.DATAFORSEO_PASSWORD):
            raise ValueError(
                "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD are not set; the Google AI Mode "
                "capture is unavailable (see .env.example)."
            )
        token = base64.b64encode(
            f"{settings.DATAFORSEO_LOGIN}:{settings.DATAFORSEO_PASSWORD}".encode()
        ).decode()
        self._auth = f"Basic {token}"
        self._location = (location or "").strip() or None
        self._client = httpx.Client(timeout=TIMEOUT_SECONDS)

    def close(self) -> None:
        self._client.close()

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def _task(self, prompt: str) -> dict[str, Any]:
        task: dict[str, Any] = {
            "keyword": prompt,
            "language_code": "en",
            "device": "desktop",
        }
        if self._location is not None:
            task["location_name"] = self._location
        return task

    def _fetch(self, prompt: str) -> dict[str, Any] | None:
        payload = [self._task(prompt)]
        record_payload(self.ENGINE_NAME, {"endpoint": DATAFORSEO_AI_MODE_URL, "tasks": payload})
        try:
            response = self._client.post(
                DATAFORSEO_AI_MODE_URL,
                headers={"Authorization": self._auth, "Content-Type": "application/json"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.warning("DataForSEO AI Mode request error: %s", type(exc).__name__)
            return None
        # Surface the vendor's own reason (unverified account, empty balance, bad
        # location) rather than an opaque HTTPStatusError — see the AI Overviews engine.
        if response.status_code >= 400:
            detail = _status_message(response) or "(no status_message in body)"
            # Carried on the instance so preflight can record the vendor's actual reason
            # on the run, not just in a log line nobody reads after the fact.
            self.last_error = f"HTTP {response.status_code} {detail}"
            logger.warning("DataForSEO AI Mode HTTP %s: %s", response.status_code, detail)
            return None
        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("DataForSEO AI Mode response parse error: %s", type(exc).__name__)
            return None
        if not isinstance(data, dict):
            return None
        # 200 with a per-task error code: an auth failure or exhausted balance looks like
        # a healthy response, and reading it as "no answer" would turn a billing problem
        # into a measured absence.
        status = data.get("status_code")
        if status is not None and int(status) >= 40000:
            logger.warning("DataForSEO AI Mode task error status_code=%s", status)
            return None
        return data

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        data = self._fetch(prompt)
        if data is None:
            return None, []
        return parse_ai_mode(data)

    def probe(self, prompt: str) -> tuple[bool, int, int]:
        """Alive when the request succeeds — see ``DataForSEOAIOverviewsEngine.probe`` for
        why a SERP capture must not define liveness as "returned text"."""
        data = self._fetch(prompt)
        if data is None:
            return False, 0, 0
        text, urls = parse_ai_mode(data)
        return True, len(text.strip()) if text else 0, len(urls)


if __name__ == "__main__":
    engine = DataForSEOAIModeEngine(location="Berkeley,California,United States")
    for q in ("best plumber in Berkeley", "why is my water pressure suddenly low?"):
        answer, cites = engine.query_with_citations(q)
        print(f"\n{q!r} -> {len(answer) if answer else 0} chars, {len(cites)} citations")
        if answer:
            print(f"  {answer[:300]}")
