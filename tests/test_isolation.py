"""Payload-assertion tests (isolation plan, Test B) — the anti-regression guard.

Every engine's outgoing request is captured at the client boundary and checked
against the statelessness rule on ``BaseEngine``: exactly one user message (the
bare query), no system prompt, and no state params that would let a call build
on a previous one. If a refactor reintroduces carryover, these tests fail —
the guarantee can't silently rot.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from typing import Any

import pytest

from src.config import settings

# Params that would make a call stateful or carry identity across calls. None
# may ever appear in an outgoing payload (Layers 1-2 of the isolation plan).
FORBIDDEN_STATE_PARAMS = {
    "store",
    "previous_response_id",
    "response_id",
    "conversation",
    "conversation_id",
    "thread_id",
    "session_id",
    "memory",
    "user",
    "metadata",
}

# Dated model snapshot: id ends in a YYYY-MM-DD-style date (e.g.
# gpt-4o-2024-08-06, claude-sonnet-4-5-20250929, ...-preview-2025-03-11).
DATED_MODEL = re.compile(r"\d{4}-?\d{2}-?\d{2}$")


def _assert_isolated_chat_payload(payload: dict[str, Any], prompt: str) -> None:
    """The core Test B assertion for chat-completions-shaped payloads."""
    messages = payload["messages"]
    assert len(messages) == 1, f"expected exactly one message, got {len(messages)}"
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == prompt
    forbidden = FORBIDDEN_STATE_PARAMS & set(payload)
    assert not forbidden, f"stateful params in outgoing payload: {forbidden}"


# --- OpenAI (parametric) ------------------------------------------------------


class _CapturingOpenAI:
    """Stands in for the OpenAI client; records every create() kwargs."""

    captured: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> Any:
        _CapturingOpenAI.captured.append(kwargs)
        message = SimpleNamespace(content="ok", annotations=[])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture()
def openai_engine(monkeypatch: pytest.MonkeyPatch) -> Any:
    from src.engines import openai_engine as mod

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod, "OpenAI", _CapturingOpenAI)
    _CapturingOpenAI.captured = []
    return mod.OpenAIEngine()


def test_openai_payload_is_one_isolated_user_message(openai_engine: Any) -> None:
    assert openai_engine.query("best smart ring") == "ok"
    (payload,) = _CapturingOpenAI.captured
    _assert_isolated_chat_payload(payload, "best smart ring")
    assert payload["temperature"] == settings.ENGINE_TEMPERATURE
    assert payload["seed"] == settings.ENGINE_SEED


def test_openai_model_is_dated_snapshot(openai_engine: Any) -> None:
    openai_engine.query("hi")
    (payload,) = _CapturingOpenAI.captured
    assert DATED_MODEL.search(payload["model"]), f"not a dated snapshot: {payload['model']}"


def test_openai_second_call_carries_no_history(openai_engine: Any) -> None:
    # Josh's scenario: "best smart ring" then "is Oura worth it" — the second
    # call's payload must contain only the second query, nothing of the first.
    openai_engine.query("best smart ring")
    openai_engine.query("is the Oura Ring worth it")
    first, second = _CapturingOpenAI.captured
    _assert_isolated_chat_payload(second, "is the Oura Ring worth it")
    assert "smart ring" not in json.dumps(second)
    # Constant inputs: everything except the query text is identical.
    assert {k: v for k, v in first.items() if k != "messages"} == {
        k: v for k, v in second.items() if k != "messages"
    }


# --- OpenAI search (retrieval) ------------------------------------------------


def test_openai_search_payload_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engines import openai_search_engine as mod

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod, "OpenAI", _CapturingOpenAI)
    _CapturingOpenAI.captured = []
    engine = mod.OpenAISearchEngine()
    text, urls = engine.query_with_citations("best budgeting app")
    assert text == "ok" and urls == []
    (payload,) = _CapturingOpenAI.captured
    _assert_isolated_chat_payload(payload, "best budgeting app")
    assert DATED_MODEL.search(payload["model"])


# --- Anthropic (parametric) ----------------------------------------------------


class _CapturingAnthropic:
    captured: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        from anthropic.types import TextBlock

        _CapturingAnthropic.captured.append(kwargs)
        return SimpleNamespace(content=[TextBlock(type="text", text="ok")])


def test_anthropic_payload_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engines import anthropic_engine as mod

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(mod, "Anthropic", _CapturingAnthropic)
    _CapturingAnthropic.captured = []
    engine = mod.AnthropicEngine()
    assert engine.query("best smart ring") == "ok"
    (payload,) = _CapturingAnthropic.captured
    _assert_isolated_chat_payload(payload, "best smart ring")
    assert "system" not in payload, "measured engines must not carry a system prompt"
    assert payload["temperature"] == settings.ENGINE_TEMPERATURE
    assert DATED_MODEL.search(payload["model"])


# --- Anthropic search (retrieval) ----------------------------------------------


class _CapturingAnthropicSearch:
    captured: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        _CapturingAnthropicSearch.captured.append(kwargs)
        block = SimpleNamespace(type="text", text="ok", citations=[])
        return SimpleNamespace(content=[block])


def test_anthropic_search_payload_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engines import anthropic_search_engine as mod

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(mod, "Anthropic", _CapturingAnthropicSearch)
    _CapturingAnthropicSearch.captured = []
    engine = mod.AnthropicSearchEngine()
    text, _ = engine.query_with_citations("best smart ring")
    assert text == "ok"
    (payload,) = _CapturingAnthropicSearch.captured
    _assert_isolated_chat_payload(payload, "best smart ring")
    assert "system" not in payload
    # The web-search server tool is the only extra — and it holds no state.
    assert [t["type"] for t in payload["tools"]] == ["web_search_20250305"]


# --- Perplexity -----------------------------------------------------------------


class _CapturingHttpResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "ok"}}], "citations": []}


class _CapturingHttpClient:
    def __init__(self) -> None:
        self.captured: list[dict[str, Any]] = []

    def post(self, endpoint: str, json: dict[str, Any]) -> _CapturingHttpResponse:
        self.captured.append(json)
        return _CapturingHttpResponse()

    def close(self) -> None:
        return None


def test_perplexity_payload_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engines import perplexity_engine as mod

    monkeypatch.setattr(settings, "PERPLEXITY_API_KEY", "test-key")
    engine = mod.PerplexityEngine()
    fake = _CapturingHttpClient()
    engine._client = fake  # type: ignore[assignment]
    text, _ = engine.query_with_citations("best smart ring")
    assert text == "ok"
    (payload,) = fake.captured
    _assert_isolated_chat_payload(payload, "best smart ring")
    assert payload["temperature"] == settings.ENGINE_TEMPERATURE


# --- Gemini (parametric + grounded) ---------------------------------------------


class _CapturingGenAIModels:
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def generate_content(self, **kwargs: Any) -> Any:
        self._sink.append(kwargs)
        return SimpleNamespace(text="ok", candidates=[])


class _CapturingGenAIClient:
    captured: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.models = _CapturingGenAIModels(_CapturingGenAIClient.captured)


def test_gemini_payload_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from google import genai

    from src.engines import gemini_engine as mod

    # The engine module holds a reference to the same google.genai module
    # object, so patching Client here patches what its __init__ resolves.
    monkeypatch.setattr(genai, "Client", _CapturingGenAIClient)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    _CapturingGenAIClient.captured = []
    engine = mod.GeminiEngine()
    assert engine.query("best smart ring") == "ok"
    (call,) = _CapturingGenAIClient.captured
    # contents is the bare query string — a single user turn, never a history.
    assert call["contents"] == "best smart ring"
    assert call["config"].temperature == settings.ENGINE_TEMPERATURE
    assert call["config"].seed == settings.ENGINE_SEED
    forbidden = FORBIDDEN_STATE_PARAMS & set(call)
    assert not forbidden


def test_gemini_grounded_payload_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from google import genai

    from src.engines import gemini_grounded_engine as mod

    monkeypatch.setattr(genai, "Client", _CapturingGenAIClient)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    _CapturingGenAIClient.captured = []
    engine = mod.GeminiGroundedEngine()
    text, urls = engine.query_with_citations("best smart ring")
    assert text == "ok" and urls == []
    (call,) = _CapturingGenAIClient.captured
    assert call["contents"] == "best smart ring"
    assert call["config"].tools, "grounded engine must request the google_search tool"
    forbidden = FORBIDDEN_STATE_PARAMS & set(call)
    assert not forbidden


# --- AI Overviews (SERP capture) -------------------------------------------------


class _CapturingSerpResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {}  # no ai_overview for this query


class _CapturingSerpClient:
    def __init__(self) -> None:
        self.captured: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any]) -> _CapturingSerpResponse:
        self.captured.append(params)
        return _CapturingSerpResponse()

    def close(self) -> None:
        return None


def test_ai_overviews_request_is_bare_query(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engines import ai_overviews_engine as mod

    monkeypatch.setattr(settings, "SEARCHAPI_API_KEY", "test-key")
    engine = mod.AIOverviewsEngine()
    fake = _CapturingSerpClient()
    engine._client = fake  # type: ignore[assignment]
    text, urls = engine.query_with_citations("best smart ring")
    assert text is None and urls == []
    (params,) = fake.captured
    assert params["q"] == "best smart ring"
    forbidden = FORBIDDEN_STATE_PARAMS & set(params)
    assert not forbidden


# --- Run metadata (Layer 3) -------------------------------------------------------


def test_every_registered_engine_declares_model_id() -> None:
    # MODEL_ID is what gets recorded per run; every adapter must declare it
    # explicitly (empty only for SERP capture, which has no model parameter).
    from src.api.engine_registry import ENGINE_SOURCES, _load_class

    for name in ENGINE_SOURCES:
        cls = _load_class(name)
        assert cls is not None, f"engine class for {name} failed to import"
        assert "MODEL_ID" in vars(cls), f"{name} does not declare MODEL_ID"
        if name != "google_ai_overviews":
            assert cls.MODEL_ID, f"{name} has an empty MODEL_ID"


def test_engine_models_maps_name_to_model_and_skips_modelless() -> None:
    from src.engines.base import BaseEngine
    from src.pipeline.orchestrator import engine_models

    class _Pinned(BaseEngine):
        ENGINE_NAME = "pinned"
        MODEL_ID = "model-2026-01-01"

        def query(self, prompt: str) -> str | None:
            return None

    class _Serp(BaseEngine):
        ENGINE_NAME = "serp"
        MODEL_ID = ""

        def query(self, prompt: str) -> str | None:
            return None

    assert engine_models([_Pinned(), _Serp()]) == {"pinned": "model-2026-01-01"}


# --- Payload audit log (Test E) ----------------------------------------------------


def test_record_payload_writes_jsonl_and_scrubs_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from src.engines.payload_log import record_payload

    log_file = tmp_path / "payloads.jsonl"
    monkeypatch.setattr(settings, "PAYLOAD_LOG_PATH", str(log_file))
    record_payload("demo", {"model": "m", "q": "best smart ring", "api_key": "sk-secret"})
    record_payload("demo", {"model": "m", "q": "second"})
    lines = log_file.read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["engine"] == "demo"
    assert first["payload"]["q"] == "best smart ring"
    assert first["payload"]["api_key"] == "[redacted]"
    assert "sk-secret" not in lines[0]


def test_record_payload_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engines.payload_log import record_payload

    # Unwritable path: logged as a warning, never an exception (an audit-log
    # failure must not break a measurement call).
    monkeypatch.setattr(settings, "PAYLOAD_LOG_PATH", "/nonexistent-dir/payloads.jsonl")
    record_payload("demo", {"model": "m"})
    # Unserializable payload: also swallowed.
    monkeypatch.setattr(settings, "PAYLOAD_LOG_PATH", None)
    record_payload("demo", {"bad": object()})
