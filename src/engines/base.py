from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["BaseEngine"]


class BaseEngine(ABC):
    """Abstract base class that every AI engine adapter must implement.

    An engine wraps a single AI provider (OpenAI, Anthropic, Perplexity,
    Gemini) behind one uniform interface so the pipeline can treat every
    provider identically.

    Contract
    --------
    - ``query(prompt)`` returns the model's response text as a ``str`` on
      success, or ``None`` on any error (rate limit, timeout, API failure,
      empty response).
    - ``query`` must **never raise**. Errors are caught, logged with
      ``logging.warning``, and surfaced as ``None``. This invariant lets the
      pipeline keep running even when one provider fails.
    - Subclasses must override the ``ENGINE_NAME`` class attribute with the
      provider's short identifier (e.g. ``"openai"``).

    Subclasses load their API key from the environment in ``__init__`` and
    raise ``ValueError`` if the key is missing. No API key is ever logged.
    """

    # Short provider identifier. Subclasses MUST override this.
    ENGINE_NAME: str = "base"

    @abstractmethod
    def query(self, prompt: str) -> str | None:
        """Send ``prompt`` to the engine and return the response text.

        Returns the response text on success, or ``None`` on any error.
        Implementations must never raise: catch provider errors, log them
        with ``logging.warning``, and return ``None``.
        """
        raise NotImplementedError(
            "not implemented: BaseEngine.query must be overridden by subclasses"
        )

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        """Return the response text plus any citation URLs the engine surfaced.

        Default implementation returns no citations, so the pipeline can call
        this uniformly on every engine. Engines that expose citations (e.g.
        Perplexity) override this. Like ``query``, it must never raise.
        """
        return self.query(prompt), []
