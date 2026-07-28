"""Google AI Overviews via DataForSEO.

Google publishes no AI Overviews API, so this surface is always a SERP-scraping purchase.
DataForSEO is pay-as-you-go with **no monthly fee** — $0.002/SERP live, $0.0006 queued.
It replaced SearchApi.io on 2026-07-28, which billed a $40/month floor for volume an audit
never approaches (a routed local audit uses ~80 searches, i.e. $0.32 of a $40 commitment).

``ENGINE_NAME`` is **"google_ai_overviews"** — the SURFACE, not the vendor. The routing
policy (``engine_routing.ENGINE_POLICY``), the cost table, the teaser's engine labels,
colours and credibility weights, and every stored run's ``engine_name`` all key on that
string, which is why swapping the vendor underneath required no change to any of them.

Request contract verified against DataForSEO's docs (2026-07-28):
  POST https://api.dataforseo.com/v3/serp/google/organic/live/advanced
  Basic auth, body is an ARRAY of task objects (not a single object).
  ``location_name`` takes Google's comma-separated, no-space hierarchy —
  "Berkeley,California,United States" — the same string this repo already stores.
  ``ai_overview`` appears in ``tasks[].result[].items[]`` whenever Google showed one.

Verified against a live response on 2026-07-28 ("why is my water pressure suddenly low?",
$0.002), pinned at ``tests/fixtures/dataforseo_ai_overview.json``. Verifying was not a
formality — the docs-written parser was **2.1x wrong**, returning 5,601 characters where
the real answer is 2,665, because the element carries the whole overview in ``markdown``
AND repeats it split across ``items``. That inflated text would have gone straight into
mention detection and the judge. See ``parse_ai_overview`` for the shape.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["DataForSEOAIOverviewsEngine", "DATAFORSEO_SERP_URL", "parse_ai_overview"]

logger = logging.getLogger(__name__)

DATAFORSEO_SERP_URL = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
TIMEOUT_SECONDS = 60.0


def _status_message(response: httpx.Response) -> str:
    """DataForSEO's own explanation of a failure, or "" if the body has none.

    Shared by both DataForSEO engines. Never raises — this runs on an error path, and an
    exception here would replace a useful message with a useless one.
    """
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    message = body.get("status_message")
    code = body.get("status_code")
    if isinstance(message, str) and message.strip():
        return f"[{code}] {message.strip()}" if code is not None else message.strip()
    return ""


def _text_of(node: Any) -> str:
    """Best-effort text out of one AI-Overview element.

    DataForSEO nests the Overview as typed sub-items rather than one string, and which
    key carries the prose varies by element type. Checked in priority order, and unknown
    shapes contribute nothing rather than a stringified dict.
    """
    if isinstance(node, str):
        return node.strip()
    if not isinstance(node, dict):
        return ""
    for key in ("markdown", "text", "description", "title"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _reference_urls(node: dict[str, Any]) -> list[str]:
    """Citation URLs from one element's ``references`` array."""
    out: list[str] = []
    for ref in node.get("references") or []:
        if not isinstance(ref, dict):
            continue
        url = ref.get("url")
        if isinstance(url, str) and url.startswith("http"):
            out.append(url)
    return out


def parse_ai_overview(data: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Extract (overview text, citation urls) from a DataForSEO SERP body.

    Returns ``(None, [])`` when Google showed no AI Overview for the query — the common
    case, and NOT an error: an Overview appears on a minority of SERPs (and on
    essentially no local-intent ones). Never raises.

    Verified against a live response (2026-07-28, "why is my water pressure suddenly
    low?"); the captured body is pinned at ``tests/fixtures/dataforseo_ai_overview.json``.
    The real shape is::

        {"type": "ai_overview",
         "markdown": "<the WHOLE overview>",          # <- authoritative text
         "asynchronous_ai_overview": false,
         "items":      [{"type": "ai_overview_element",
                         "title": ..., "text": ..., "markdown": ...,   # <- the SAME prose
                         "references": [...]}],
         "references": [{"type": "ai_overview_reference", "url", "domain",
                         "source", "title", "text"}]}

    The element carries the full overview in ``markdown`` **and** repeats it split across
    ``items``. The first version of this function walked every node and concatenated both,
    producing 5,601 characters where the real answer is 2,665 — a 2.1x inflation of an
    engine answer, which would have flowed straight into mention detection and the judge.
    So: take the top-level ``markdown``, and only fall back to assembling ``items`` when
    it is missing.
    """
    try:
        tasks = data.get("tasks") or []
        if not tasks:
            return None, []
        results = tasks[0].get("result") or []
        if not results:
            return None, []
        items = results[0].get("items") or []
        overview = next(
            (i for i in items if isinstance(i, dict) and i.get("type") == "ai_overview"), None
        )
        if overview is None:
            return None, []

        elements = [e for e in (overview.get("items") or []) if isinstance(e, dict)]

        # Authoritative text first; assemble from the parts only if it is absent.
        body = _text_of({"markdown": overview.get("markdown")})
        if not body:
            body = "\n\n".join(
                dict.fromkeys(t for t in (_text_of(e) for e in elements) if t)
            )

        # References appear both on the overview and on individual elements, with
        # overlap. Dedupe while preserving order — citation rank is signal.
        urls = _reference_urls(overview)
        for element in elements:
            urls.extend(_reference_urls(element))
        return (body or None), list(dict.fromkeys(urls))
    except Exception as exc:  # a malformed body must never break the engine contract
        logger.warning("DataForSEO response parse error: %s", type(exc).__name__)
        return None, []


class DataForSEOAIOverviewsEngine(BaseEngine):
    """Google AI Overviews captured via DataForSEO's live SERP endpoint."""

    ENGINE_NAME: str = "google_ai_overviews"
    # No model parameter — this is a SERP capture, not a model call. Excluded
    # from run metadata by `orchestrator.engine_models`, which drops empty MODEL_IDs.
    MODEL_ID: str = ""

    def __init__(self, location: str | None = None) -> None:
        """``location`` is a DataForSEO ``location_name`` — "Berkeley,California,United States".

        Google's canonical comma-separated hierarchy — the same string this repo already
        stores, so a run persisted before the vendor change needs no translation.
        Injected at construction, not per call, because the pipeline fans out through the
        uniform ``BaseEngine.query`` contract: one engine instance measures one market.

        Leave ``None`` for nationally-marketed products. **A local query run without a
        location is not a local measurement** — it answers "what does Google show
        somebody, somewhere".
        """
        if not (settings.DATAFORSEO_LOGIN and settings.DATAFORSEO_PASSWORD):
            raise ValueError(
                "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD are not set; the DataForSEO "
                "AI Overviews capture is unavailable (see .env.example)."
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
        """The single task object sent for ``prompt``.

        ``load_async_ai_overview`` is on because Google serves many Overviews
        asynchronously; without it the capture silently misses them and the run would
        under-report the surface. It costs ~$0.0006 extra and is refunded when only
        cached data was needed. ``expand_ai_overview`` is free and returns the full text
        rather than a truncated preview.
        """
        task: dict[str, Any] = {
            "keyword": prompt,
            "language_code": "en",
            "device": "desktop",
            "load_async_ai_overview": True,
            "expand_ai_overview": True,
        }
        if self._location is not None:
            task["location_name"] = self._location
        return task

    def _fetch(self, prompt: str) -> dict[str, Any] | None:
        """One isolated request; returns the parsed body, or None on any failure.

        The body is built ONCE and both recorded and sent as that same object, so the
        audit log can never drift from the real request. ``record_payload`` scrubs
        credentials at any depth, and the Basic token lives in a header, never the body.
        """
        payload = [self._task(prompt)]
        record_payload(self.ENGINE_NAME, {"endpoint": DATAFORSEO_SERP_URL, "tasks": payload})
        try:
            response = self._client.post(
                DATAFORSEO_SERP_URL,
                headers={"Authorization": self._auth, "Content-Type": "application/json"},
                json=payload,
            )
        except httpx.HTTPError as exc:
            logger.warning("DataForSEO request error: %s", type(exc).__name__)
            return None
        # DataForSEO puts a genuinely actionable reason in the body of a 4xx — an
        # unverified account, an exhausted balance, a bad location string. Bare
        # raise_for_status() throws that away and leaves an operator staring at
        # "HTTPStatusError", so read it out before giving up. status_message is vendor
        # diagnostic text, never row data, so logging it leaks nothing.
        if response.status_code >= 400:
            detail = _status_message(response) or "(no status_message in body)"
            # Carried on the instance so preflight can record the vendor's actual reason
            # on the run, not just in a log line nobody reads after the fact.
            self.last_error = f"HTTP {response.status_code} {detail}"
            logger.warning("DataForSEO HTTP %s: %s", response.status_code, detail)
            return None
        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("DataForSEO response parse error: %s", type(exc).__name__)
            return None
        if not isinstance(data, dict):
            return None
        # DataForSEO returns HTTP 200 with a per-task status code, so a 200 alone is not
        # success — an auth failure or exhausted balance arrives looking like a fine
        # response. 20000 is their OK code.
        status = data.get("status_code")
        if status is not None and int(status) >= 40000:
            logger.warning("DataForSEO task error status_code=%s", status)
            return None
        return data

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        data = self._fetch(prompt)
        if data is None:
            return None, []
        return parse_ai_overview(data)

    def probe(self, prompt: str) -> tuple[bool, int, int]:
        """Alive when the SERP request SUCCEEDS, not when an Overview happens to exist.

        Same distinction as ``AIOverviewsEngine.probe`` and for the same hard-won reason:
        Google shows no Overview for most queries, so a text-based liveness test drops a
        perfectly healthy surface (it did exactly that on 2026-07-28).
        """
        data = self._fetch(prompt)
        if data is None:
            return False, 0, 0
        text, urls = parse_ai_overview(data)
        return True, len(text.strip()) if text else 0, len(urls)


if __name__ == "__main__":
    engine = DataForSEOAIOverviewsEngine(location="Berkeley,California,United States")
    for q in ("why is my water pressure suddenly low?", "best plumber in Berkeley"):
        answer, cites = engine.query_with_citations(q)
        print(f"\n{q!r}")
        print(f"  -> {len(answer) if answer else 0} chars, {len(cites)} citations")
        if answer:
            print(f"  {answer[:300]}")
