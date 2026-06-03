# GEO Measurement Platform — Claude Development Guide

This file is the authoritative guide for all AI-assisted development on this codebase. Read it fully before writing any code. Follow every protocol exactly.

---

## 1. What You Are Building

**GEO Measurement Platform** is a data pipeline and audit tool that measures how often a company appears in AI-generated answers across ChatGPT, Claude, Gemini, and Perplexity.

GEO = Generative Engine Optimization. When a consumer asks an AI system "best app for X," this platform measures whether the client appears, whether competitors appear instead, and which external sources are driving those recommendations.

This tool powers a manual GEO audit service sold to early-stage **B2C consumer startups in the Berkeley / Silicon Valley ecosystem**. The software starts as internal tooling for two founders running client audits. It becomes a standalone SaaS product once the service proves what clients actually need.

**Founders:**
- Abhi — technical founder, builds the pipeline
- Josh — business founder (Haas), runs sales and client relationships

**Target customer:** Founder or growth lead at an early-stage B2C consumer startup (Berkeley/SV ecosystem) who is losing visibility in AI-generated consumer recommendations and has no way to measure or fix it.

---

## 2. Project Structure

```
geo-measurement-platform/
  src/
    engines/
      __init__.py
      base.py                # Abstract base class all engines must implement
      openai_engine.py       # OpenAI GPT-4o
      anthropic_engine.py    # Anthropic Claude
      perplexity_engine.py   # Perplexity + citation extraction
      gemini_engine.py       # Google Gemini
    pipeline/
      __init__.py
      prompt_runner.py       # Sends prompt list to all engines, stores results
      parser.py              # Brand mention detection, competitor extraction
      citation_extractor.py  # Pulls citation URLs from Perplexity responses
    audit/
      __init__.py
      technical_check.py     # robots.txt, llms.txt, sitemap, rendering checks
      checklist.py           # Loads and scores the 7-category rubric
      report.py              # Generates structured markdown audit report
    storage/
      __init__.py
      db.py                  # Supabase/Postgres connection
      models.py              # Table schemas and typed data classes
    prompts/
      __init__.py
      generator.py           # Builds prompt sets from client context
    config/
      __init__.py
      settings.py            # API keys from env vars, engine config
  tests/
    test_engines.py
    test_parser.py
    test_pipeline.py
    test_technical_check.py
  data/
    sample_prompts.json      # Sample buyer-intent prompts for dry runs
    checklist.json           # 7-category audit rubric as structured data
  docs/
    build-log.md             # Append-only build log (see Section 6)
  .env.example
  requirements.txt
  README.md
```

---

## 3. Tech Stack

- **Language:** Python 3.11+
- **AI Engine APIs:** OpenAI (GPT-4o), Anthropic (Claude 3.5 Sonnet), Perplexity, Google Gemini
- **Storage:** Supabase (Postgres via supabase-py)
- **HTTP requests:** httpx for technical audit checks
- **Output:** Structured JSON + Markdown reports
- **Environment management:** python-dotenv
- **Testing:** pytest
- **Linting/formatting:** ruff
- **Type checking:** mypy

**Required environment variables (see .env.example):**
```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
PERPLEXITY_API_KEY=
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
```

---

## 4. Testing and Validation Loop

**This loop must be followed for every file you write. You do not exit the loop until the code runs without errors and all validation checks pass.**

### The loop

```
WRITE → TYPECHECK → LINT → RUN → VALIDATE → (pass: log + continue) | (fail: fix + restart loop)
```

**Step 1 — Write**
Write the code for the current chunk. Write complete files, not snippets. Do not leave `TODO` comments for logic that must exist for the chunk to work.

**Step 2 — Typecheck**
Run mypy on changed files. Fix all errors before proceeding.

```bash
mypy src/engines/openai_engine.py
# or check the whole src directory:
mypy src/
```

The loop does not advance past this step if there are any type errors.

**Step 3 — Lint**
Run ruff on changed files. Fix all errors.

```bash
ruff check src/
ruff format src/
```

**Step 4 — Run**
Execute the module's `__main__` test block and confirm it runs without crashing.

```bash
python -m src.engines.openai_engine
# or run the full pipeline:
python -m src.pipeline.prompt_runner
```

**Step 5 — Validate**
Run the chunk's acceptance criteria item by item. Each item must explicitly pass. If any item fails, note which one, fix the code, and restart the loop from Step 1.

### Error handling rules

- Never silence type errors with `# type: ignore` unless there is a documented reason in a comment on the same line.
- Never catch exceptions and swallow them silently. Every except block must log the error or re-raise.
- Never leave dead code paths. If a branch is not implemented, raise `NotImplementedError("not implemented: <description>")` so failures are loud.
- All Supabase calls must be inside a try/except that returns a structured error response. Never let database errors bubble uncaught.
- All API calls must handle `RateLimitError`, `APITimeoutError`, and general `APIError` — log and return `None`, do not raise.

### Loop reset rule

If a fix introduces a new type error in a file that was previously clean, that file is added to the current loop's scope and must also pass before the loop exits.

---

## 5. Code Conventions

### Python

- Type hints required on all function signatures. No untyped functions.
- Use `from __future__ import annotations` at the top of every file.
- Dataclasses or TypedDicts for structured data. No bare dicts for anything that crosses a function boundary.
- Named imports only — no `from module import *`.
- Constants in ALL_CAPS at the top of the file or in `config/settings.py`.
- All primary keys use `uuid.uuid4()`.

### Engine modules

- Every engine must subclass `BaseEngine` from `src/engines/base.py`.
- `BaseEngine` defines: `query(prompt: str) -> str | None`
- Perplexity also implements: `query_with_citations(prompt: str) -> tuple[str | None, list[str]]`
- Engine name must be a class attribute: `ENGINE_NAME: str = "openai"`
- API key loaded in `__init__` from environment variable. Raise `ValueError` with a clear message if missing.
- Rate limit and timeout errors: catch, log with `logging.warning`, return `None`.
- Every engine file has an `if __name__ == "__main__"` block that sends one test prompt and prints the response.

### Pipeline modules

- `prompt_runner.py` accepts a list of prompt strings and a list of engine instances. Returns a list of `PromptResult` TypedDicts.
- `parser.py` functions are pure — they take text inputs and return typed outputs. No side effects.
- `MentionType` enum: `recommended | mentioned | not_mentioned`

### Storage

- Never hard-delete any row. Use `archived_at` timestamps for soft deletes.
- All writes go through functions in `db.py`. No direct Supabase calls from pipeline or audit code.
- Supabase calls use try/except. On failure: log the error, raise a custom `StorageError`.

### Technical audit checks

- Each check function in `technical_check.py` returns a `CheckResult` TypedDict with `status: Literal["pass", "partial", "fail"]` and `details: str`.
- Use `httpx` for all HTTP requests. Set a 10-second timeout on all requests.

### File naming

- Source files: `snake_case.py`
- Test files: `test_<module_name>.py`
- Data files: `snake_case.json`

### Environment variables

- All secrets live in `.env` (not committed). `.env.example` documents required keys with placeholder values.
- Load via `python-dotenv` in `config/settings.py`. All other modules import from `settings.py` — never call `os.getenv` directly outside of settings.
- Never log environment variable values, even in debug code.

---

## 6. Build Log Protocol

The build log lives at `docs/build-log.md`. It is append-only. **Update it once and only once per chunk, immediately after that chunk's validation gate fully passes.**

Do not update the build log mid-chunk or speculatively. Only update it when every item on the chunk's acceptance criteria passes.

### Entry format

Append a new section at the TOP of the build log (most recent first):

```markdown
## Chunk N — [Chunk Name] — Completed [YYYY-MM-DD]

### What was built

- Built `src/engines/openai_engine.py` — OpenAI GPT-4o engine implementing BaseEngine
- Extended `src/storage/models.py` with PromptResult and BrandMention types
- [etc.]

### Acceptance criteria — all passed

- ✅ Implements BaseEngine interface
- ✅ Loads API key from OPENAI_API_KEY env var
- ✅ Rate limit errors caught, logged, return None
- ✅ Test block sends one prompt and prints response

---

### Up next — Chunk [N+1]: [Chunk Name]

[One line describing the primary goal of the next chunk]
```

Do not modify previous entries. If a previous chunk was incomplete, create a patch entry labeled `Chunk N.1 — Patch — [date]`.

---

## 7. Working Order Within a Chunk

When starting a new chunk, follow this order:

1. **Read this file** in full.
2. **Read `docs/build-log.md`** to confirm current state and which chunk is next.
3. **List every file you will create or modify** before writing any of them.
4. **Write in dependency order**: base types and interfaces first, then engines, then pipeline, then storage, then audit, then report output.
5. **Run the validation loop** as you complete each file, not just at the end.
6. **Update the build log** only after the full chunk acceptance criteria pass.
7. **Do not start Chunk N+1** until Chunk N's build log entry is written.

---

## 8. Domain Knowledge

> **Niche:** B2C consumer startups in the Berkeley / Silicon Valley ecosystem
> (early-stage, accelerator-adjacent consumer brands and apps). The "buyer" is a
> **consumer** — a person choosing an app/product for themselves — not a B2B
> procurement or growth lead. This reframes which sources matter and how queries
> are phrased; the measurement mechanics are unchanged.

### How AI systems generate recommendations

1. **Training data frequency** — brands mentioned often and positively in training data get baked into the model's memory. For consumer products, **Reddit, YouTube, TikTok, App Store / Play Store, Amazon, Trustpilot, "best [category] app" listicles, and lifestyle/consumer media** appear disproportionately.
2. **Retrieval (live-search models)** — Perplexity, Bing Copilot, and Google AI Mode/Overviews fetch pages at query time. They retrieve content, extract relevant passages, and synthesize an answer. Citations appear because a specific page was retrieved and used.
3. **Content extractability** — AI systems favor pages with clear definitions, comparison tables, FAQ sections, and direct answers. Vague marketing copy is ignored.
4. **Co-occurrence** — if a brand consistently appears alongside "best budgeting app for students," the model learns that association.
5. **Source authority** — a mention on a trusted, high-traffic consumer source (a big subreddit, a popular creator, a major review roundup) carries more weight than a random site.

### What moves visibility

- Earning presence in **Reddit / consumer-forum threads** where buyers ask for recommendations (the single highest-leverage B2C source)
- **App Store / Play Store** rating volume, recency, and review quality (ASO)
- **Creator coverage** — YouTube reviews, TikTok, Instagram, and influencer roundups
- Getting named in **"best [category] app" listicles** and consumer media roundups
- Building comparison pages ("X vs Y") and alternative pages ("best alternatives to X")
- Reviews on **Trustpilot** and other consumer review platforms
- Writing clear, question-answering content with direct answers first
- Ensuring AI crawlers can reach the site (robots.txt, Cloudflare WAF)

### The 7-Step Audit Methodology

Every client audit follows this exact sequence:

**Step 1 — Baseline measurement:** Run the query set across all engines for the client and top 2-3 competitors. Capture mention rate, share-of-voice, brand description accuracy, and cited sources. Output: date-stamped before-snapshot.

**Step 2 — Technical accessibility:** Check crawler access, WAF/Cloudflare blocking, rendering, llms.txt, sitemap, gating. Often explains a bad Step 1 result immediately.

**Step 3 — On-site audit:** Score content coverage, structure and extractability, substance/E-E-A-T, and schema.

**Step 4 — Off-site audit:** Score entity consistency, community presence (Reddit/forums), app-store reviews, creator/influencer coverage, listicle inclusion, and third-party citations — the consumer channels that drive the answers.

**Step 5 — Competitive benchmark:** Run the same rubric on competitors. Produce the gap map. Absolute scores don't persuade — gaps against rivals they're losing to do.

**Step 6 — Synthesize into prioritized roadmap:** Roll up scores, sequence fixes (accessibility before content before off-site), tag each gap with impact and effort.

**Step 7 — Deliver and convert:** Lead with the Step 1/5 competitive demo, walk the roadmap, propose the retainer.

### The 7-Category Technique Checklist (Pass / Partial / Fail)

**Category 1 — Technical Accessibility**
- robots.txt allows: GPTBot, ChatGPT-User, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended, Bingbot
- Not blocked at CDN/WAF (Cloudflare blocks AI bots by default)
- Core content server-rendered or static, not JS-only (consumer marketing sites are often SPA shells)
- llms.txt present and valid
- XML sitemap present and current
- Target content not gated behind sign-up/app-download walls

**Category 2 — Content Coverage / Question-Space Mapping**
- Topic clusters map the consumer journey: problem-aware → comparison → decision
- Internal linking establishes topical authority

**Category 3 — Content Structure and Extractability**
- Answer-first: 40-60 word direct answer before elaborating
- Headings written as real consumer questions
- Self-contained chunks per section
- Definition-first sentences for key terms
- Scannable formatting: short paragraphs, lists, tables
- TL;DR block near top of long pages

**Category 4 — Content Substance and Credibility (E-E-A-T)**
- Fact density: concrete specifics (pricing, features, limits) over vague claims
- Citations to authoritative external sources
- Real user outcomes / testimonials / case studies
- Named authors with credible bios
- Visible last-updated date
- On-site comparison content: "X vs Y", "X alternatives", "best [category] app"

**Category 5 — Structured Data / Schema**
- Schema.org markup present and valid
- Relevant types: Organization, Product, **MobileApplication/SoftwareApplication**, **Review/AggregateRating**, Article, FAQPage, HowTo
- Schema matches visible content
- Entity identifiers consistent across the web

**Category 6 — Offsite Authority and Entity Consensus** (the B2C battleground)
- Brand entity consistent everywhere: name, description, category
- Presence on **Reddit and consumer forums / Q&A threads**
- **App Store / Play Store** ratings & reviews (volume, recency, sentiment)
- **YouTube / TikTok / influencer** coverage
- Reviews on **Trustpilot** and consumer review platforms
- Named in **"best [category] app" listicles** and consumer-media roundups
- Third-party citations and press

**Category 7 — Baseline Measurement**
- Representative consumer-query set built for the category
- Mention/citation rate recorded across all 4 engines
- Competitor presence mapped on the same queries
- Baseline share-of-voice date-stamped
- Accuracy of the model's brand description verified
- AI-referral traffic tracked in GA4

---

## 9. The 12-Chunk Build Plan

Work through chunks in order. Do not start a chunk until the previous one's acceptance criteria fully pass and the build log entry is written.

### Chunk 1 — Base engine interface
**Goal:** Define the shared interface all engine modules must implement.
**Files:** `src/engines/base.py`, `src/engines/__init__.py`
**Acceptance criteria:**
- `BaseEngine` abstract class with abstract `query(prompt: str) -> str | None`
- `ENGINE_NAME` class attribute defined
- Docstring explains contract: returns response text or None on error, never raises
- Clean import from other modules

### Chunk 2 — OpenAI engine
**Goal:** Connect to OpenAI API and return a response for a given prompt.
**File:** `src/engines/openai_engine.py`
**Acceptance criteria:**
- Subclasses `BaseEngine`
- Loads API key from `OPENAI_API_KEY`, raises `ValueError` if missing
- Uses `gpt-4o`
- `RateLimitError`, `APITimeoutError`, `APIError` caught, logged, return `None`
- `if __name__ == "__main__"` block sends one prompt and prints response
- mypy and ruff pass

### Chunk 3 — Anthropic engine
**Goal:** Connect to Anthropic API.
**File:** `src/engines/anthropic_engine.py`
**Acceptance criteria:** Same pattern as Chunk 2 using `ANTHROPIC_API_KEY` and `claude-3-5-sonnet-20241022`

### Chunk 4 — Perplexity engine
**Goal:** Connect to Perplexity API and extract citation URLs.
**File:** `src/engines/perplexity_engine.py`
**Acceptance criteria:**
- Subclasses `BaseEngine`
- `query()` returns response text
- `query_with_citations()` returns `tuple[str | None, list[str]]`
- Citations extracted from response object's `citations` field
- Test block prints both response and list of citation URLs

### Chunk 5 — Gemini engine
**Goal:** Connect to Gemini API.
**File:** `src/engines/gemini_engine.py`
**Acceptance criteria:** Same pattern as Chunk 2 using `GEMINI_API_KEY` and `gemini-1.5-pro`

### Chunk 6 — Prompt runner
**Goal:** Send a list of prompts to all 4 engines and collect results.
**File:** `src/pipeline/prompt_runner.py`
**Acceptance criteria:**
- Accepts `prompts: list[str]` and `engines: list[BaseEngine]`
- Returns `list[PromptResult]` — each has `prompt`, `engine_name`, `response`, `timestamp`
- `PromptResult` defined as TypedDict in `src/storage/models.py`
- Test block runs 3 sample prompts across all engines, prints result count

### Chunk 7 — Brand mention detector
**Goal:** Detect whether a brand is mentioned and whether it is recommended.
**File:** `src/pipeline/parser.py`
**Acceptance criteria:**
- `MentionType` enum: `recommended | mentioned | not_mentioned`
- `detect_mention(brand: str, response: str) -> MentionType`
- Case-insensitive matching
- `recommended` requires explicit language: "best", "recommend", "suggest", "top choice"
- Test block runs 5 sample responses and prints correct verdicts

### Chunk 8 — Competitor extractor
**Goal:** Given a list of competitor names and a response, return which appeared and how.
**File:** `src/pipeline/parser.py` (extend existing)
**Acceptance criteria:**
- `extract_competitors(competitors: list[str], response: str) -> list[str]`
- `extract_competitor_mentions(competitors: list[str], response: str) -> dict[str, MentionType]`
- Both case-insensitive

### Chunk 9 — Supabase storage
**Goal:** Store prompt results, mentions, and citations to Supabase.
**Files:** `src/storage/db.py`, `src/storage/models.py`
**Acceptance criteria:**
- Tables: `prompt_runs`, `prompt_results`, `brand_mentions`, `citations`
- `create_run(client_name: str, prompt_count: int) -> str` returns `run_id`
- `save_results`, `save_mentions`, `save_citations` functions implemented
- All writes in try/except, raise `StorageError` on failure
- Test block saves mock data and confirms rows exist in Supabase

### Chunk 10 — Report generator
**Goal:** Generate a structured markdown audit report from a completed run.
**File:** `src/audit/report.py`
**Acceptance criteria:**
- `generate_report(run_id: str) -> str` returns markdown string
- Report includes: client name, date stamp, mention rate per engine, competitor share-of-model table, top cited domains, summary of findings
- Test block generates a report from mock data and prints it

### Chunk 11 — Technical accessibility checker
**Goal:** Check whether AI crawlers can reach and parse a domain.
**File:** `src/audit/technical_check.py`
**Acceptance criteria:**
- `check_robots_txt(domain: str) -> CheckResult`
- `check_llms_txt(domain: str) -> CheckResult`
- `check_sitemap(domain: str) -> CheckResult`
- `check_rendering(domain: str) -> CheckResult`
- `CheckResult` TypedDict: `status: Literal["pass", "partial", "fail"]`, `details: str`
- All requests use `httpx` with 10-second timeout
- Test block runs all 4 checks against a real domain

### Chunk 12 — Dry run (integration)
**Goal:** Run the full pipeline end-to-end against one real client domain. No new files — integration and debugging only.
**Acceptance criteria:**
- 10+ prompts sent to all 4 engines
- Results stored in Supabase without errors
- Brand mentions and competitor appearances extracted correctly
- Technical accessibility checks complete on a real domain
- Markdown report generated with date stamp and correct data
- No unhandled exceptions across the full run

---

## 10. Phase 1 Exit Gate — QA Checklist

Do not move to Phase 2 until every item passes:

- [ ] 10 prompts sent to all 4 engines and responses stored in Supabase
- [ ] Brand mention detection correct on 5 sample responses
- [ ] Perplexity citations extracted and stored correctly
- [ ] robots.txt checker correctly identifies blocked AI crawlers on a test domain
- [ ] llms.txt checker returns correct pass/fail
- [ ] Storage saves and retrieves without errors
- [ ] Report generates clean markdown with timestamp and all required sections
- [ ] Full dry run on one real domain produces a readable, accurate audit report
- [ ] mypy passes on all src/ files
- [ ] ruff passes on all src/ files

---

## 11. Non-Goals (Do Not Build in Phase 1)

Do not add these even if they seem useful:

- Client-facing dashboard or UI of any kind
- Authentication or multi-user logic
- Content generation or page builder
- Outreach automation
- Async pipeline (synchronous first)
- Real-time monitoring or scheduled jobs
- Any CMS integrations

If a useful idea comes up, note it in `docs/future-ideas.md`. Do not build it until explicitly added to the roadmap.

---

## 12. Invariants That Must Never Break

1. **Every engine returns `None` on error, never raises.** The pipeline must never crash because one engine failed.
2. **Every Supabase write is inside a try/except.** Database errors raise `StorageError` — they never bubble as unhandled exceptions.
3. **No API key is ever logged.** Not in debug, not in error messages, not in test output.
4. **The base engine interface is never bypassed.** All engines subclass `BaseEngine`. Pipeline code only calls methods defined on `BaseEngine`.
5. **The build log is append-only.** Never edit a previous chunk's entry. Patches get their own entry.
6. **No chunk is marked complete until all acceptance criteria pass.**
7. **The dry run is deterministic.** Given the same prompt list and client domain, it produces a structurally consistent report every time.

---

## 13. Quick Reference

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run a single engine test
```bash
python -m src.engines.openai_engine
python -m src.engines.perplexity_engine
```

### Run the full pipeline
```bash
python -m src.pipeline.prompt_runner
```

### Run technical checks on a domain
```bash
python -m src.audit.technical_check
```

### Run all tests
```bash
pytest tests/
```

### Typecheck
```bash
mypy src/
```

### Lint and format
```bash
ruff check src/
ruff format src/
```

### Check current build state
```bash
cat docs/build-log.md
```
