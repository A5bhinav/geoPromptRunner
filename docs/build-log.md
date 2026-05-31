# Build Log

Append-only. Most recent chunk at the top. One entry per chunk, written only after every acceptance criterion passes.

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
