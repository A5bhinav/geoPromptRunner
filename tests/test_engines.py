from __future__ import annotations

from typing import Any

import pytest

from src.engines.base import BaseEngine


class _Echo(BaseEngine):
    ENGINE_NAME = "echo"

    def query(self, prompt: str) -> str | None:
        return f"echo: {prompt}"


class _Boom(BaseEngine):
    """An engine whose query returns None (the never-raise failure surface)."""

    ENGINE_NAME = "boom"

    def query(self, prompt: str) -> str | None:
        return None


def test_query_with_citations_default_delegates_to_query() -> None:
    # The base default returns the query() text plus an empty citation list, so
    # the pipeline can call it uniformly on every engine.
    assert _Echo().query_with_citations("hi") == ("echo: hi", [])
    assert _Boom().query_with_citations("hi") == (None, [])


def test_base_engine_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseEngine()  # type: ignore[abstract]


def test_openai_engine_never_raises_on_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # The never-raise invariant: a provider exception becomes None, not a crash.
    import openai

    from src.config import settings
    from src.engines import openai_engine

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")

    class _RaisingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.chat = self

        @property
        def completions(self) -> _RaisingClient:
            return self

        def create(self, *args: Any, **kwargs: Any) -> Any:
            raise openai.APIError("boom", request=None, body=None)  # type: ignore[arg-type]

    monkeypatch.setattr(openai_engine, "OpenAI", _RaisingClient)
    engine = openai_engine.OpenAIEngine()
    assert engine.query("anything") is None


def test_openai_engine_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import settings
    from src.engines import openai_engine

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        openai_engine.OpenAIEngine()
