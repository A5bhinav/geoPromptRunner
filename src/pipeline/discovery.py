from __future__ import annotations

import logging
import re
from collections import Counter

from src.engines.base import BaseEngine
from src.storage.models import QueryResult

__all__ = ["discover_competitors", "extract_prompt_for"]

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Extract the names of software products, tools, or companies mentioned in the "
    "text below. Return ONLY the names, one per line, with no numbering, commentary, "
    "or extra words. If none, return nothing.\n\nTEXT:\n{response}"
)

# FORKED, not rewritten (pivot §0.6). The consumer prompt above still reads
# "software products, tools, or companies"; reprompting it in place for local would
# degrade consumer discovery SILENTLY, because extraction quality has no loud failure
# mode — you just get slightly worse competitor lists forever.
_LOCAL_EXTRACT_PROMPT = (
    "Extract the names of local businesses mentioned in the text below — the kind of "
    "service business a customer would call or visit (contractors, shops, salons, "
    "restaurants, trades). Include the business name only, not the city, the street "
    "address, or a description. Return ONLY the names, one per line, with no "
    "numbering, commentary, or extra words. If none, return nothing.\n\nTEXT:\n{response}"
)

# Lines that clearly aren't product names (model preamble / refusals). Additive for
# local: the local-shaped preambles are harmless to the consumer path.
_NOISE = re.compile(
    r"^(here|none|no |the following|sure|products?:|tools?:|businesses?:|companies:)\b",
    re.IGNORECASE,
)


def extract_prompt_for(business_kind: str = "product") -> str:
    """The extraction prompt for one business kind. Unknown kinds → consumer."""
    return _LOCAL_EXTRACT_PROMPT if business_kind == "local_service" else _EXTRACT_PROMPT


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
    business_kind: str = "product",
) -> list[tuple[str, int]]:
    """Find brands/products that appear in answers but weren't in ``known``.

    Uses ``extractor`` (any engine) as an LLM NER pass over each distinct
    response, then drops the client + named competitors and ranks the rest by
    how many distinct responses mention them. Surfaces rivals you didn't name —
    e.g. a newcomer dominating answers. Counts once per distinct response.

    ``business_kind`` selects the extraction prompt; it defaults to ``"product"``, so
    every existing consumer caller is unchanged.

    Note this discovers rivals *from measured answers*, which is a different job from
    seeding a local competitor SET — that must come from captured local-pack entities
    (W1.6), never from LLM recall.
    """
    prompt_template = extract_prompt_for(business_kind)
    known_lower = {k.strip().lower() for k in known if k.strip()}
    seen_responses: set[str] = set()
    counts: Counter[str] = Counter()

    for r in results:
        response = r["response"]
        if not response or response in seen_responses:
            continue
        seen_responses.add(response)
        extracted = extractor.query(prompt_template.format(response=response))
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
            return "YNAB\nMonarch Money\nRocket Money\nCopilot"

    results = [
        QueryResult(
            query_id="q1",
            intent="category",
            prompt="best budgeting app?",
            engine_name="openai",
            run_index=0,
            response="YNAB, Monarch Money, Rocket Money, and Copilot are popular.",
            citations=[],
            timestamp="t",
        )
    ]
    discovered = discover_competitors(
        results, known=["YNAB", "Acme"], extractor=_StubExtractor()
    )
    print("discovered (excluding known):", discovered)
