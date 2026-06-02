from __future__ import annotations

import logging
import re
from collections import Counter

from src.engines.base import BaseEngine
from src.storage.models import QueryResult

__all__ = ["discover_competitors"]

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Extract the names of software products, tools, or companies mentioned in the "
    "text below. Return ONLY the names, one per line, with no numbering, commentary, "
    "or extra words. If none, return nothing.\n\nTEXT:\n{response}"
)

# Lines that clearly aren't product names (model preamble / refusals).
_NOISE = re.compile(r"^(here|none|no |the following|sure|products?:|tools?:)\b", re.IGNORECASE)


def _normalize(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().strip("•-*.,\"'").strip()


def _parse_names(text: str | None) -> list[str]:
    if not text:
        return []
    names: list[str] = []
    for line in text.splitlines():
        candidate = _normalize(line)
        if not candidate or len(candidate) > 60 or _NOISE.match(candidate):
            continue
        names.append(candidate)
    return names


def discover_competitors(
    results: list[QueryResult],
    known: list[str],
    extractor: BaseEngine,
    limit: int = 15,
) -> list[tuple[str, int]]:
    """Find brands/products that appear in answers but weren't in ``known``.

    Uses ``extractor`` (any engine) as an LLM NER pass over each distinct
    response, then drops the client + named competitors and ranks the rest by
    how many distinct responses mention them. Surfaces rivals you didn't name —
    e.g. a newcomer dominating answers. Counts once per distinct response.
    """
    known_lower = {k.strip().lower() for k in known if k.strip()}
    seen_responses: set[str] = set()
    counts: Counter[str] = Counter()

    for r in results:
        response = r["response"]
        if not response or response in seen_responses:
            continue
        seen_responses.add(response)
        extracted = extractor.query(_EXTRACT_PROMPT.format(response=response))
        for name in _parse_names(extracted):
            if name.lower() in known_lower:
                continue
            counts[name] += 1

    return counts.most_common(limit)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    class _StubExtractor(BaseEngine):
        ENGINE_NAME = "stub"

        def query(self, prompt: str) -> str | None:
            # Pretend the model extracted these names from the response.
            return "Salesforce\nClose\nFolk\nAttio"

    results = [
        QueryResult(
            query_id="q1",
            intent="category",
            prompt="best CRM?",
            engine_name="openai",
            run_index=0,
            response="Salesforce, Close, Folk, and Attio are popular.",
            citations=[],
            timestamp="t",
        )
    ]
    discovered = discover_competitors(
        results, known=["Salesforce", "Acme"], extractor=_StubExtractor()
    )
    print("discovered (excluding known):", discovered)
