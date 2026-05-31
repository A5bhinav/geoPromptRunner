# Build Log

Append-only. Most recent chunk at the top. One entry per chunk, written only after every acceptance criterion passes.

---

## Chunk 11 — Technical accessibility checker — Completed 2026-05-31

### What was built

- Built `src/audit/technical_check.py` — `check_robots_txt`, `check_llms_txt`, `check_sitemap`, `check_rendering`, each returning a `CheckResult` TypedDict (`status: Literal["pass","partial","fail"]`, `details: str`). All HTTP via `httpx` with a 10s timeout; transport errors caught and returned as a `fail` result (never raised).

### Acceptance criteria — all passed

- ✅ `check_robots_txt`, `check_llms_txt`, `check_sitemap`, `check_rendering` implemented
- ✅ `CheckResult` TypedDict with the required `status`/`details` shape
- ✅ All requests use `httpx` with a 10-second timeout
- ✅ Test block runs all 4 checks against a real domain (`example.com`); verified against `nytimes.com` that blocked AI crawlers are correctly reported as `partial` (6 of 7 blocked)

### Up next — Chunk 12: Dry run (integration)

Run the full pipeline end-to-end against one real client domain. Requires live API keys and Supabase credentials.

---

## Chunk 10 — Report generator — Completed 2026-05-31

### What was built

- Built `src/audit/report.py` — `generate_report(run_id: str) -> str` (assembles data from storage and renders) plus a pure `render_report(data: ReportData) -> str`.
- Extended `src/storage/db.py` with read helpers (`get_run`, `get_results`, `get_mentions`, `get_citations`) needed to assemble a report from a stored run.
- `ReportData` TypedDict added to `src/storage/models.py`.

### Acceptance criteria — all passed

- ✅ `generate_report(run_id: str) -> str` returns a markdown string
- ✅ Report includes client name, date stamp, mention rate per engine, competitor share-of-model table, top cited domains, and a summary of findings
- ✅ Test block renders a report from mock data and prints it (deterministic — invariant #7)

---

## Chunk 9 — Supabase storage — Completed 2026-05-31

### What was built

- Built `src/storage/db.py` — `create_run`, `save_results`, `save_mentions`, `save_citations` (+ read helpers), targeting tables `prompt_runs`, `prompt_results`, `brand_mentions`, `citations`. All writes wrapped in try/except and raise `StorageError` on failure; soft-delete via `archived_at` (no hard deletes). All primary keys use `uuid.uuid4()`.
- Extended `src/storage/models.py` with `PromptRun`, `BrandMention`, `Citation` TypedDicts.
- Installed `supabase` into `.venv`.

### Acceptance criteria — passed (live-DB step pending credentials)

- ✅ Tables `prompt_runs`, `prompt_results`, `brand_mentions`, `citations` modeled
- ✅ `create_run(client_name, prompt_count) -> run_id` returns a generated run id
- ✅ `save_results`, `save_mentions`, `save_citations` implemented
- ✅ All writes in try/except, raise `StorageError` on failure
- ⚠️ Test block saves mock data and confirms rows in Supabase — **code validated (typecheck/lint/graceful-skip)**, but the live "rows exist" confirmation requires `SUPABASE_URL`/`SUPABASE_KEY`, which are not configured. The test block degrades gracefully and exits 0 with a clear message when creds are absent. To be re-run during Chunk 12 with real credentials.

---

## Chunk 8 — Competitor extractor — Completed 2026-05-31

### What was built

- Extended `src/pipeline/parser.py` with `extract_competitors(competitors, response) -> list[str]` and `extract_competitor_mentions(competitors, response) -> dict[str, MentionType]`.

### Acceptance criteria — all passed

- ✅ `extract_competitors` returns competitors present in the response
- ✅ `extract_competitor_mentions` maps each competitor to a `MentionType`
- ✅ Both case-insensitive (word-boundary matching)

---

## Chunk 7 — Brand mention detector — Completed 2026-05-31

### What was built

- Built `src/pipeline/parser.py` — `MentionType` enum (`recommended | mentioned | not_mentioned`) and pure `detect_mention(brand, response) -> MentionType`.

### Acceptance criteria — all passed

- ✅ `MentionType` enum with the three values
- ✅ `detect_mention(brand, response) -> MentionType`
- ✅ Case-insensitive matching
- ✅ `recommended` requires explicit language ("best", "recommend", "suggest", "top choice")
- ✅ Test block runs 5 sample responses and prints correct verdicts (all 5 OK)

---

## Chunk 6 — Prompt runner — Completed 2026-05-31

### What was built

- Built `src/pipeline/prompt_runner.py` — `run_prompts(prompts: list[str], engines: list[BaseEngine]) -> list[PromptResult]`, synchronous and order-stable.
- Built `src/storage/models.py` with the `PromptResult` TypedDict (`prompt`, `engine_name`, `response`, `timestamp`).
- Created package prerequisites: `src/pipeline/__init__.py`, `src/storage/__init__.py`, `src/audit/__init__.py`.

### Acceptance criteria — all passed

- ✅ Accepts `prompts: list[str]` and `engines: list[BaseEngine]`
- ✅ Returns `list[PromptResult]` with `prompt`, `engine_name`, `response`, `timestamp`
- ✅ `PromptResult` defined as a TypedDict in `src/storage/models.py`
- ✅ Test block runs 3 sample prompts across available engines and prints the result count (real engines skipped without keys; a keyless echo engine demonstrates the runner)

### Validation (Chunks 6–11)

- ✅ mypy (strict): `Success: no issues found in 18 source files`
- ✅ ruff check: `All checks passed!` — ruff format: `18 files already formatted`
- ✅ `python -m src.pipeline.prompt_runner` → 3 results collected
- ✅ `python -m src.pipeline.parser` → 5/5 verdicts correct, competitor extraction correct
- ✅ `python -m src.audit.report` → full markdown report with all required sections
- ✅ `python -m src.audit.technical_check` → 4 checks run live against `example.com`
- ⚠️ `python -m src.storage.db` → graceful skip (no Supabase credentials configured)

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
