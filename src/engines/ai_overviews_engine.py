from __future__ import annotations

import contextlib
import logging
from typing import Any, TypedDict

import httpx

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["AIOverviewsEngine", "LocalEntity"]


class LocalEntity(TypedDict):
    """One business from Google's local pack, as SearchApi returns it (W1.6).

    This is the ONLY sanctioned source of local competitor candidates. Claude does
    not reliably know the plumbers in a given city, and a fabricated rival printed in
    a teaser emailed to a real shop owner is the unrecoverable failure for this
    product — so local rivals are seeded from captured entities or not at all.
    """

    name: str
    address: str
    # Google's own category string ("Plumber", "Barber shop") — the trade as Google
    # classifies it, which is what local queries are actually resolved against.
    category: str
    rating: float | None
    reviews: int | None
    # Google's stable location id; the join key if we ever enrich an entity later.
    ludocid: str | None
    position: int | None

logger = logging.getLogger(__name__)

SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"
TIMEOUT_SECONDS = 45.0


class AIOverviewsEngine(BaseEngine):
    """Google AI Overviews surface, captured via SearchApi.io.

    Google exposes no official AI-Overviews API, so this reads the ``ai_overview``
    block from a SearchApi.io Google result. Requires ``SEARCHAPI_API_KEY``;
    without it the engine is skipped like any unconfigured engine.
    ``query_with_citations`` returns the AI-Overview text and its reference
    links. Never raises. (AI Overviews don't appear for every query — those
    return ``None``/``[]``.)
    """

    ENGINE_NAME: str = "google_ai_overviews"
    # SERP capture, not a model API — there is no model string to pin. Variance
    # here is the live Google surface itself (isolation plan, L5).
    MODEL_ID: str = ""

    def __init__(self, location: str | None = None) -> None:
        """``location`` is SearchApi's canonical location NAME, e.g.
        ``"Berkeley,California,US"`` (W1.3).

        Verified against SearchApi's Google-engine docs (2026-07): the ``location``
        param takes a canonical name and SearchApi builds the ``uule`` encoding
        itself — the two are mutually exclusive, so we send ``location`` only.

        Injected at construction, not per call, because the pipeline fans out through
        the uniform ``BaseEngine.query(prompt)`` contract; a per-call argument would
        break that for every other engine. One engine instance measures one market.

        Leave it ``None`` for nationally-marketed products: SearchApi then uses its
        own default locale, which is exactly today's behaviour. **A local query run
        without a location is not a valid local measurement** — it answers "what does
        Google show somebody, somewhere", not "what does it show a customer in this
        city".
        """
        if not settings.SEARCHAPI_API_KEY:
            raise ValueError(
                "SEARCHAPI_API_KEY is not set; Google AI Overviews capture is unavailable "
                "(see .env.example)."
            )
        self._api_key = settings.SEARCHAPI_API_KEY
        self._location = (location or "").strip() or None
        self._client = httpx.Client(timeout=TIMEOUT_SECONDS)

    def close(self) -> None:
        self._client.close()

    def __del__(self) -> None:
        client = getattr(self, "_client", None)
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def _fetch(self, prompt: str) -> dict[str, Any] | None:
        """One isolated GET; returns the parsed body, or None on any failure.

        The query string plus the location when this engine is measuring a specific
        market. Params are built ONCE and both recorded and sent as that same dict, so
        the audit log can never drift from the real request (Test E). record_payload
        scrubs api_key at any depth, so it is never logged.
        """
        params: dict[str, Any] = {"engine": "google", "q": prompt, "api_key": self._api_key}
        if self._location is not None:
            params["location"] = self._location
        record_payload(self.ENGINE_NAME, params)
        try:
            response = self._client.get(SEARCHAPI_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("SearchApi request error: %s", type(exc).__name__)
            return None
        # A 200 with a non-JSON body (an error/challenge page served at 200) makes
        # .json() raise — which would escape and break the "engines never raise"
        # contract, so it is caught here rather than at each call site.
        try:
            data = response.json()
        except ValueError as exc:
            logger.warning("SearchApi response parse error: %s", type(exc).__name__)
            return None
        return data if isinstance(data, dict) else None

    def query_local_entities(self, prompt: str) -> list[LocalEntity]:
        """Businesses from Google's local pack for ``prompt`` (W1.6).

        The sanctioned source of local competitor candidates — see ``LocalEntity``.
        Returns ``[]`` when the query surfaced no local pack, when the request failed,
        or when this engine has no location (a local pack from an unpinned locale
        names businesses in the wrong metro, which is worse than none).

        Never raises, matching the engine contract.
        """
        if self._location is None:
            logger.warning(
                "query_local_entities called with no location; refusing to return "
                "local-pack entities from an unpinned locale"
            )
            return []
        data = self._fetch(prompt)
        if data is None:
            return []
        try:
            return _parse_local_entities(data)
        except Exception as exc:  # a malformed body must not crash the caller
            logger.warning("SearchApi local_results parse error: %s", type(exc).__name__)
            return []

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        data = self._fetch(prompt)
        if data is None:
            return None, []

        # Shaping stays inside a guard too: malformed JSON can trip the extraction,
        # and that would break the "engines never raise" contract.
        try:
            overview = data.get("ai_overview")
            if not isinstance(overview, dict):
                return None, []  # no AI Overview surfaced for this query
            text = overview.get("markdown") or _extract_text(overview)
            urls = [
                str(ref["link"])
                for ref in overview.get("reference_links", []) or []
                if isinstance(ref, dict) and ref.get("link")
            ]
        except Exception as exc:  # never let a bad response body crash the pipeline
            logger.warning("SearchApi response parse error: %s", type(exc).__name__)
            return None, []
        return (text or None), urls


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_local_entities(data: dict[str, Any]) -> list[LocalEntity]:
    """Shape SearchApi's ``local_results`` into typed entities. Pure.

    Drops entries with no name (nothing downstream can use one) and entries flagged
    ``is_closed`` — recommending a shut-down business is the local equivalent of the
    defunct-brand bug the consumer path already guards against (DEFUNCT_BRANDS).
    """
    entities: list[LocalEntity] = []
    for item in data.get("local_results", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("is_closed"):
            continue
        name = str(item.get("title") or "").strip()
        if not name:
            continue
        entities.append(
            LocalEntity(
                name=name,
                address=str(item.get("address") or "").strip(),
                category=str(item.get("type") or "").strip(),
                rating=_coerce_float(item.get("rating")),
                reviews=_coerce_int(item.get("reviews")),
                ludocid=(str(item["ludocid"]) if item.get("ludocid") else None),
                position=_coerce_int(item.get("position")),
            )
        )
    return entities


def _extract_text(overview: dict[str, Any]) -> str:
    """Fallback text extraction from text_blocks when ``markdown`` is absent."""
    parts: list[str] = []
    for block in overview.get("text_blocks", []) or []:
        if not isinstance(block, dict):
            continue
        if block.get("answer"):
            parts.append(str(block["answer"]))
        for item in block.get("list", []) or []:
            if isinstance(item, dict) and item.get("answer"):
                parts.append(str(item["answer"]))
    return " ".join(parts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        engine = AIOverviewsEngine()
    except ValueError as exc:
        print(f"Cannot run AI Overviews engine test: {exc}")
        raise SystemExit(0) from None

    answer, urls = engine.query_with_citations("best budgeting app for college students")
    print(f"[{AIOverviewsEngine.ENGINE_NAME}] response: {(answer or '')[:200]}")
    print(f"[{AIOverviewsEngine.ENGINE_NAME}] citations ({len(urls)}): {urls}")
