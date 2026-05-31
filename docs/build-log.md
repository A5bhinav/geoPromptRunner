# Build Log

Append-only. Most recent chunk at the top. One entry per chunk, written only after every acceptance criterion passes.

---

## Chunk 5 — Gemini engine — Completed 2026-05-31

### What was built

- Built `src/engines/gemini_engine.py` — `GeminiEngine(BaseEngine)` using `gemini-1.5-pro` via `google-generativeai`.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `GEMINI_API_KEY`, raises `ValueError` if missing
- ✅ Uses `gemini-1.5-pro`
- ✅ `ResourceExhausted` (rate limit), `DeadlineExceeded` (timeout), `GoogleAPIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

Note: documented `# type: ignore[attr-defined]` on `genai.configure`/`genai.GenerativeModel` — the deprecated `google-generativeai` package ships incomplete re-exports; names exist at runtime.

### Up next — Chunk 6: Prompt runner

Build `src/pipeline/prompt_runner.py` to send a list of prompts to all four engines and collect `list[PromptResult]` (TypedDict in `src/storage/models.py`).

---

## Chunk 4 — Perplexity engine — Completed 2026-05-31

### What was built

- Built `src/engines/perplexity_engine.py` — `PerplexityEngine(BaseEngine)` calling the Perplexity REST API (`model="sonar"`) via `httpx`, with citation extraction.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ `query()` returns response text
- ✅ `query_with_citations()` returns `tuple[str | None, list[str]]`
- ✅ Citations extracted from the response's `citations` field
- ✅ Test block prints both response and list of citation URLs
- ✅ On error returns `(None, [])`; never raises. mypy (strict) and ruff pass

---

## Chunk 3 — Anthropic engine — Completed 2026-05-31

### What was built

- Built `src/engines/anthropic_engine.py` — `AnthropicEngine(BaseEngine)` using `claude-3-5-sonnet-20241022`; extracts text from `TextBlock` content blocks.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `ANTHROPIC_API_KEY`, raises `ValueError` if missing
- ✅ Uses `claude-3-5-sonnet-20241022`
- ✅ `RateLimitError`, `APITimeoutError`, `APIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

---

## Chunk 2 — OpenAI engine — Completed 2026-05-31

### What was built

- Built `src/engines/openai_engine.py` — `OpenAIEngine(BaseEngine)` using `gpt-4o`.
- Created prerequisite `src/config/settings.py` + `src/config/__init__.py` — the single place that reads env vars (via `python-dotenv`); all engines load their keys from here, never `os.getenv` directly (§5 convention).
- Installed engine SDKs into `.venv`: `openai`, `anthropic`, `google-generativeai`, `httpx`, `python-dotenv`.

### Acceptance criteria — all passed

- ✅ Subclasses `BaseEngine`
- ✅ Loads API key from `OPENAI_API_KEY`, raises `ValueError` if missing
- ✅ Uses `gpt-4o`
- ✅ `RateLimitError`, `APITimeoutError`, `APIError` caught, logged, return `None`
- ✅ `if __name__ == "__main__"` block sends one prompt and prints response
- ✅ mypy (strict) and ruff pass

### Validation (Chunks 2–5)

- ✅ mypy (strict): `Success: no issues found in 9 source files`
- ✅ ruff check: `All checks passed!` — ruff format: `9 files already formatted`
- ✅ Each `python -m src.engines.<name>` runs without crashing (graceful `ValueError` skip when key absent)
- ✅ Invariant #1 verified: with dummy keys set, every `query()` returns `None` on auth/network failure and never raises; all four are `BaseEngine` instances

---

## Chunk 1 — Base engine interface — Completed 2026-05-31

### What was built

- Built `src/engines/base.py` — `BaseEngine` abstract base class defining the uniform engine contract (`query(prompt: str) -> str | None`, `ENGINE_NAME` class attribute).
- Built `src/engines/__init__.py` — re-exports `BaseEngine` for clean imports.
- Built `src/__init__.py` — makes `src` an importable package.
- Created prerequisite project files: `requirements.txt`, `.env.example`, `pyproject.toml` (ruff + mypy strict config), `.gitignore`.

### Acceptance criteria — all passed

- ✅ `BaseEngine` abstract class with abstract `query(prompt: str) -> str | None`
- ✅ `ENGINE_NAME` class attribute defined (default `"base"`, subclasses override)
- ✅ Docstring explains contract: returns response text or `None` on error, never raises
- ✅ Clean import from other modules (`from src.engines import BaseEngine` and `from src.engines.base import BaseEngine` resolve to the same class)

### Validation

- ✅ mypy (strict): `Success: no issues found in 3 source files`
- ✅ ruff check: `All checks passed!`
- ✅ ruff format --check: `3 files already formatted`
- ✅ Runtime: abstract base is non-instantiable; concrete subclass `query()` returns `str | None` as declared

---

### Up next — Chunk 2: OpenAI engine

Implement `src/engines/openai_engine.py` subclassing `BaseEngine`, loading `OPENAI_API_KEY`, using `gpt-4o`, catching rate-limit/timeout/API errors and returning `None`.
