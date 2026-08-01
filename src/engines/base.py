from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

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

    Statelessness rule (isolation plan, Layers 1–2)
    -----------------------------------------------
    Every call is a clean room. Each request carries **exactly one user
    message** — the query text and nothing else — and never opts into
    server-side state:

    - no prior turns resent in ``messages``/``contents``
    - no system prompt on a measured engine (only the judge has one)
    - no stateful endpoint or params: no Assistants/threads, no
      ``previous_response_id``, no ``store: true``, no conversation/session ids.
      An explicit ``store: false`` is the *strengthened* form of this rule, not a
      breach of it — the OpenAI Responses API retains responses unless told not to,
      so on that endpoint stating the refusal is the only way to guarantee it.
      Saying nothing would be the violation.
    - reused SDK/httpx clients are connection pools only, never conversations

    This is what makes per-query results independent and cross-cycle
    comparisons valid. ``tests/test_isolation.py`` asserts the outgoing payload
    of every engine against this rule — if you change how a request is built,
    those tests are the gate.

    Subclasses load their API key from the environment in ``__init__`` and
    raise ``ValueError`` if the key is missing. No API key is ever logged.
    """

    # Short provider identifier. Subclasses MUST override this.
    ENGINE_NAME: str = "base"

    # The exact model string sent to the provider — pinned to a dated snapshot
    # where the provider offers one, so a silent model update can't move the
    # baseline between measurement cycles. Recorded in each run's metadata.
    # Empty for surfaces with no model parameter (e.g. SERP capture).
    MODEL_ID: str = ""

    # How this surface's sampling is controlled — the fact a report's methodology
    # section has to state, kept on the engine that owns it rather than retyped as prose
    # somewhere downstream (which is exactly how docs/report.md came to claim
    # "temperature pinned to 0" for a surface that cannot take one).
    #
    #   "pinned"  the request carries settings.ENGINE_TEMPERATURE
    #   "default" no temperature is sent — the model samples at its own default, either
    #             because the provider rejects the parameter or because this adapter
    #             does not send it. Repeat runs of one query genuinely differ.
    #   "none"    no LLM sampling to control at all (SERP capture surfaces)
    #
    # ``tests/test_isolation.py`` asserts this against each engine's real outgoing
    # payload, so the label cannot drift from what is actually sent.
    SAMPLING: Literal["pinned", "default", "none"] = "pinned"

    # The provider's own explanation of the most recent failure, when it gave one worth
    # repeating ("Please verify your account", "insufficient balance"). Read by
    # src/pipeline/preflight.py so a dropped engine is recorded on the run with the REAL
    # reason instead of a generic guess. Engines that have nothing specific to say leave
    # it None; nothing depends on it being set. Must never contain a credential.
    last_error: str | None = None

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

    def probe(self, prompt: str) -> tuple[bool, int, int]:
        """Liveness check: can this engine still be reached? ``(alive, chars, citations)``.

        Separate from ``query`` because for a **model** engine "answered with text"
        and "is reachable" are the same question, but for a **SERP-capture** engine
        they are not: Google legitimately shows no AI Overview for most queries, so
        an empty capture is normal data, not a broken surface. Those engines override
        this to check that the *request* succeeded instead.

        Getting this wrong is not hypothetical — the first version of the preflight
        used answer text for every engine and dropped a perfectly healthy
        ``google_ai_overviews`` because the probe query happened to have no Overview.

        Must never raise, like everything else on this contract.
        """
        text, citations = self.query_with_citations(prompt)
        alive = text is not None and bool(text.strip())
        return alive, len(text.strip()) if text else 0, len(citations)
