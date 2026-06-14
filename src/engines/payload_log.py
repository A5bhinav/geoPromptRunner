from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.config import settings

__all__ = ["record_payload"]

logger = logging.getLogger(__name__)

# Keys that must never appear in a recorded payload. Engines only pass request
# *bodies* (auth lives in headers/clients), but scrub defensively anyway —
# SearchApi puts its key in query params, and a future engine might too.
_SECRET_KEYS = frozenset({"api_key", "apikey", "key", "token", "authorization"})


def _scrub(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` with secret-bearing keys redacted, at any
    depth — a key buried in a nested dict/list (e.g. a query-param object) is
    redacted too, not just at the top level."""

    def scrub_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: ("[redacted]" if k.lower() in _SECRET_KEYS else scrub_value(v))
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [scrub_value(v) for v in value]
        return value

    return scrub_value(payload)  # type: ignore[no-any-return]


def record_payload(engine_name: str, payload: dict[str, Any]) -> None:
    """Record the exact outgoing request body for one engine call (Test E).

    Auditability hook from the isolation/determinism plan: every call's payload
    is logged at DEBUG, and — when ``PAYLOAD_LOG_PATH`` is set — appended as one
    JSON line (timestamp, engine, payload) so any run is reconstructable.

    Contract: callers pass the request *body* only, never auth headers; secret
    keys are scrubbed defensively regardless. This function never raises — a
    logging failure must not break a measurement call.
    """
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "engine": engine_name,
        "payload": _scrub(payload),
    }
    try:
        line = json.dumps(record, default=str)
    except (TypeError, ValueError) as exc:
        logger.warning("Payload for %s not JSON-serializable: %s", engine_name, exc)
        return

    logger.debug("outgoing payload %s", line)
    if not settings.PAYLOAD_LOG_PATH:
        return
    try:
        with open(settings.PAYLOAD_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        logger.warning("Could not append to payload log: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    record_payload(
        "demo",
        {"model": "demo-model", "messages": [{"role": "user", "content": "hi"}], "api_key": "x"},
    )
    print("record_payload ran (set PAYLOAD_LOG_PATH to also write a JSONL file)")
