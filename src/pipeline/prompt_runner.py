from __future__ import annotations

import logging
from datetime import UTC, datetime

from src.engines.base import BaseEngine
from src.storage.models import PromptResult

__all__ = ["run_prompts"]

logger = logging.getLogger(__name__)


def run_prompts(prompts: list[str], engines: list[BaseEngine]) -> list[PromptResult]:
    """Send every prompt to every engine and collect the results.

    Synchronous and order-stable: iterates prompts in order, and within each
    prompt iterates engines in order. Because every engine returns ``None``
    rather than raising on error, one failing engine never aborts the run.
    """
    results: list[PromptResult] = []
    for prompt in prompts:
        for engine in engines:
            response = engine.query(prompt)
            results.append(
                PromptResult(
                    prompt=prompt,
                    engine_name=engine.ENGINE_NAME,
                    response=response,
                    timestamp=datetime.now(UTC).isoformat(),
                )
            )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # A keyless echo engine so the runner is demonstrable without API keys.
    class _EchoEngine(BaseEngine):
        ENGINE_NAME = "echo"

        def query(self, prompt: str) -> str | None:
            return f"echo: {prompt}"

    engines: list[BaseEngine] = [_EchoEngine()]

    # Add any real engines whose API keys happen to be configured.
    from src.engines.anthropic_engine import AnthropicEngine
    from src.engines.gemini_engine import GeminiEngine
    from src.engines.openai_engine import OpenAIEngine
    from src.engines.perplexity_engine import PerplexityEngine

    for cls in (OpenAIEngine, AnthropicEngine, PerplexityEngine, GeminiEngine):
        try:
            engines.append(cls())
        except ValueError as exc:
            print(f"Skipping {cls.__name__}: {exc}")

    sample_prompts = [
        "What is the best CRM for early-stage B2B SaaS startups?",
        "Which project management tool do developers recommend?",
        "Name a good analytics platform for product teams.",
    ]

    run_results = run_prompts(sample_prompts, engines)
    print(f"Ran {len(sample_prompts)} prompts across {len(engines)} engine(s).")
    print(f"Collected {len(run_results)} results.")
