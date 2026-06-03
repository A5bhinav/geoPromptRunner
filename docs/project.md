# GEO Measurement Platform — Project Document

## What You Are Building

**GEO Measurement Platform** is a data pipeline and audit tool that measures how often a company appears in AI-generated answers across ChatGPT, Claude, Gemini, and Perplexity.

GEO stands for Generative Engine Optimization — the practice of optimizing a brand's visibility in AI-generated answers, analogous to SEO for Google.

This tool powers a manual audit service sold to early-stage **B2C consumer startups in the Berkeley / Silicon Valley ecosystem**. The service finds why competitors are being recommended by AI systems instead of the client, and tells the client exactly what to fix.

The software starts as internal tooling. It becomes a standalone SaaS product once the service proves what clients actually need.

---

## The Business Context

**Founders:**
- Abhi — technical founder, building the software and audit pipeline
- Josh — business founder (Haas), running sales and client relationships

**Target customer:** Founder or growth lead at an early-stage B2C consumer startup who is losing visibility in AI-generated consumer recommendations and has no way to measure or fix it.

**The problem they feel:** When their customers ask ChatGPT or Perplexity "best app for X," competitors show up and they don't. They have no analytics for this. They don't know why it's happening. They don't know if their fixes are working.

**What this tool does for the business:**
1. Runs the audit pipeline automatically instead of manually
2. Produces a structured before/after report for each client
3. Tracks visibility changes over time
4. Eventually becomes the product clients pay for directly

**Niche:** Berkeley/SV ecosystem, early-stage B2C consumer startups. Entry point is through one accelerator or VC portfolio for warm distribution.

---

## How GEO Actually Works (Domain Knowledge)

AI systems recommend brands based on:

1. **Training data frequency** — brands mentioned often and positively in the data the model was trained on get baked into its memory. For consumer products, Reddit, YouTube, TikTok, App Store / Play Store, Amazon, Trustpilot, "best [category] app" listicles, and lifestyle/consumer media are disproportionately represented.

2. **Retrieval (for live-search models)** — Perplexity, Bing Copilot, and Google AI Mode fetch pages at query time. They retrieve content, extract relevant passages, and synthesize an answer. Citations appear because a specific page was retrieved and used.

3. **Content extractability** — AI systems favor pages with clear definitions, comparison tables, FAQ sections, and direct answers. Vague marketing copy is ignored.

4. **Co-occurrence with category terms** — if a brand consistently appears alongside "best budgeting app for students," the model learns that association.

5. **Source authority** — a mention on a trusted domain carries more weight than a random site.

**What moves visibility:**
- Adding statistics and data to content
- Citing authoritative sources inside your own content
- Building comparison pages ("X vs Y")
- Building alternative pages ("best alternatives to X")
- Building use-case specific pages
- Earning presence on Reddit / consumer forums, and strong App Store / Play Store reviews
- Getting creator coverage (YouTube, TikTok, influencers) and named in "best [category] app" listicles
- Writing clear, question-answering content with direct answers first

---

## The Audit Methodology (7 Steps)

Every client audit follows this exact sequence:

**Step 1 — Baseline measurement**
Run the full prompt set across all engines for the client and their top 2-3 competitors. Capture: mention rate, share-of-model, accuracy of brand description, and which pages/sources are cited. Output: a date-stamped before-snapshot.

**Step 2 — Technical accessibility**
Check whether AI crawlers can even reach the site. This often explains a bad Step 1 result immediately. Check: robots.txt crawler permissions, WAF/Cloudflare blocking, server-side rendering vs JS-only, llms.txt presence, sitemap validity, gated content.

**Step 3 — On-site audit**
Score the client's website across: content coverage and question-space mapping, content structure and extractability, content substance and E-E-A-T, structured data and schema.

**Step 4 — Off-site audit**
Score the client's external presence: brand entity consistency, community presence (Reddit, consumer forums), App Store / Play Store reviews, Trustpilot, creator/influencer coverage (YouTube, TikTok), "best [category] app" listicles that name the client, and third-party citations/press.

**Step 5 — Competitive benchmark**
Run the same rubric categories on competitors. Produce a "here's where they beat you" gap map. Absolute scores persuade no one — gaps against a rival they're losing to do.

**Step 6 — Synthesize into a prioritized roadmap**
Roll up scores, weight them, sequence fixes (accessibility before content before off-site), tag each gap with rough impact and effort. This is the deliverable and the scope of the retainer.

**Step 7 — Deliver and convert**
Present leading with the Step 1/5 demo (the visceral competitive gap), walk the roadmap, propose the retainer to close the gaps that need sustained work.

---

## The Technique Checklist (Audit Rubric)

Each item is scored Pass / Partial / Fail.

### Category 1 — Technical Accessibility
- robots.txt allows AI crawlers: GPTBot, ChatGPT-User, OAI-SearchBot, ClaudeBot, PerplexityBot, Google-Extended, Bingbot
- Not blocked at CDN/WAF layer — especially Cloudflare which defaults to blocking AI bots
- Core content is server-rendered or static, not locked behind client-side JS
- llms.txt present and valid, pointing to key pages
- XML sitemap present and current, clean URL structure
- Target content is not gated behind login, paywall, or forms

### Category 2 — Content Coverage / Question-Space Mapping
- Topic-cluster audit: pillar content plus supporting pages map buyer question space across awareness → consideration → decision
- Internal linking that establishes topical authority

### Category 3 — Content Structure and Extractability
- Answer-first: each page/section opens with a direct 40-60 word answer before elaborating
- Headings written as real questions matching how buyers phrase queries
- Self-contained chunks: each section makes sense on its own
- Definition-first sentences for key terms ("X is …")
- Scannable formatting: short paragraphs, lists, tables
- TL;DR / direct-answer block near top of long pages
- Transcripts/alt text for video or podcast content

### Category 4 — Content Substance and Credibility (E-E-A-T)
- Fact density: concrete statistics and numbers roughly every 150-200 words
- Citations to authoritative external sources inside the content
- Expert quotes and original commentary
- Original data, first-hand experience, or real case studies
- Named authors with credible bios and credentials
- Visible last-updated date; core pages on a quarterly refresh cycle
- On-site comparison content: "X vs Y", "X alternatives", "best X for [use case]"

### Category 5 — Structured Data / Schema
- Schema.org markup present and valid
- Relevant types implemented: Organization, Product/SoftwareApplication, Article, FAQPage, HowTo, Speakable
- Schema matches visible content, no mismatch or keyword stuffing
- Entity identifiers consistent: sameAs links to official profiles, consistent brand name and description

### Category 6 — Offsite Authority and Entity Consensus
- Brand entity consistent across the web: same name, description, and category everywhere
- Presence on community sources models lean on: Reddit, consumer forums, Q&A threads
- App Store / Play Store ratings & reviews; reviews on Trustpilot; YouTube/TikTok/influencer coverage
- Third-party citations, press, co-citations from credible consumer/lifestyle outlets
- Wikipedia/Wikidata entity where the brand legitimately qualifies
- "Best [category] app" listicles / roundups exist naming the client

### Category 7 — Baseline Measurement
- Representative buyer-query set built for their category
- Current mention/citation rate recorded across engines
- Competitor presence mapped on same queries
- Currently-cited pages identified
- Baseline share-of-model recorded with date stamp
- Accuracy of model's current understanding verified
- Downstream attribution tracking: AI-referral traffic and conversions tracked in GA4

---

## Project Structure

```
geo-measurement-platform/
  src/
    engines/
      __init__.py
      openai_engine.py       # OpenAI API connection
      anthropic_engine.py    # Anthropic API connection
      perplexity_engine.py   # Perplexity API + citation extraction
      gemini_engine.py       # Gemini API connection
      base.py                # Shared interface all engines implement
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
      models.py              # Table schemas: runs, prompts, responses, citations
    prompts/
      __init__.py
      generator.py           # Builds prompt sets from client context
      templates/             # Prompt templates by category and intent
    config/
      __init__.py
      settings.py            # API keys from env, engine config
  tests/
    test_engines.py
    test_parser.py
    test_pipeline.py
  data/
    sample_prompts.json      # Sample buyer-intent prompts for testing
    checklist.json           # The 7-category rubric as structured data
  .env.example
  requirements.txt
  README.md
```

---

## Tech Stack

- **Language:** Python
- **APIs:** OpenAI (GPT-4o), Anthropic (Claude), Perplexity, Google Gemini
- **Storage:** Supabase (Postgres)
- **Output:** Structured JSON + Markdown reports
- **Environment:** python-dotenv for API key management
- **Testing:** pytest

---

## Domain Model

### PromptRun
A single execution of the full prompt set against all engines for one client.
- id, client_id, created_at, prompt_count, engines_tested

### PromptResult
One engine's response to one prompt in a run.
- id, run_id, prompt_text, engine (openai/anthropic/perplexity/gemini), response_text, created_at

### BrandMention
Extracted mention from a PromptResult.
- id, result_id, brand_name, mention_type (mentioned/recommended/not_mentioned), context_snippet

### Citation
URL cited by Perplexity in a PromptResult.
- id, result_id, url, domain, title

### AuditReport
Generated report for a client run.
- id, run_id, client_name, mention_rate, competitor_mention_rates (JSON), top_cited_domains (JSON), gap_summary, recommendations, created_at

---

## Status Values

**MentionType:**
- `recommended` — explicitly suggested as a top choice
- `mentioned` — named but not recommended
- `not_mentioned` — does not appear

**RunStatus:**
- `pending` — created, not started
- `running` — in progress
- `completed` — all engines responded
- `failed` — one or more engines errored out

---

## Coding Rules

**Before coding:**
1. Inspect existing files before adding new ones
2. Identify the smallest set of files needed for the task
3. State a brief implementation plan
4. Do not rewrite unrelated files

**While coding:**
1. Keep changes small and chunked — one executable unit per session
2. Use explicit Python type hints throughout
3. Keep engine logic inside the engines/ directory, not scattered in pipeline code
4. Prefer deterministic mock responses before adding live API calls
5. Each engine module must implement the base engine interface
6. Load all API keys from environment variables, never hardcode
7. Handle rate limits and timeouts gracefully — log and return None, do not raise
8. Every module gets a simple `if __name__ == "__main__"` test block

**After coding:**
1. Run the module's test block and confirm it works
2. Report files changed
3. Report anything unfinished
4. State the suggested next chunk
5. Do not claim success if the test block fails

---

## Scope Locks (Never Violate These)

- Do not build a client-facing UI in Phase 1
- Do not add async logic until the synchronous pipeline is stable
- Do not add real API calls until mock responses are working end-to-end
- Do not touch authentication or multi-user logic
- Do not build content generation, page builder, or outreach features
- Do not refactor a working module while adding a new one
- Do not introduce new dependencies without stating why
- Do not change the storage schema mid-build without migrating existing data
- Preserve the base engine interface — all engines must implement it identically

---

## Phase 1 Roadmap — Executable Build Chunks

Work through these in order. Do not start a chunk until the previous one passes its acceptance criteria.

### Chunk 1 — Base engine interface
**Goal:** Define the shared interface all engine modules must implement.
**File:** `src/engines/base.py`
**Acceptance criteria:**
- `BaseEngine` abstract class defined with `query(prompt: str) -> str | None` method
- Docstring explains what each engine must return
- Import works cleanly from other modules

### Chunk 2 — OpenAI engine
**Goal:** Connect to OpenAI API and return a response for a given prompt.
**File:** `src/engines/openai_engine.py`
**Acceptance criteria:**
- Implements BaseEngine interface
- Loads API key from `OPENAI_API_KEY` env var
- Uses GPT-4o
- Rate limit and timeout errors caught, logged, return None
- Test block sends one prompt and prints response

### Chunk 3 — Anthropic engine
**Goal:** Connect to Anthropic API.
**File:** `src/engines/anthropic_engine.py`
**Acceptance criteria:** Same pattern as Chunk 2 using `ANTHROPIC_API_KEY`

### Chunk 4 — Perplexity engine
**Goal:** Connect to Perplexity API and extract citation URLs.
**File:** `src/engines/perplexity_engine.py`
**Acceptance criteria:**
- Implements BaseEngine
- Returns response text AND list of citation URLs
- `query()` returns response text; `query_with_citations()` returns (text, [urls])
- Test block prints both response and citations

### Chunk 5 — Gemini engine
**Goal:** Connect to Gemini API.
**File:** `src/engines/gemini_engine.py`
**Acceptance criteria:** Same pattern as Chunk 2 using `GEMINI_API_KEY`

### Chunk 6 — Prompt runner
**Goal:** Send a list of prompts to all 4 engines and collect results.
**File:** `src/pipeline/prompt_runner.py`
**Acceptance criteria:**
- Accepts a list of prompt strings and a list of engine instances
- Returns a list of PromptResult dicts (prompt, engine, response, timestamp)
- Test block runs 3 sample prompts across all engines and prints result count

### Chunk 7 — Brand mention detector
**Goal:** Detect whether a brand is mentioned and whether it is recommended.
**File:** `src/pipeline/parser.py`
**Acceptance criteria:**
- `detect_mention(brand: str, response: str) -> MentionType` function
- Returns `recommended` / `mentioned` / `not_mentioned`
- Handles case-insensitive matching
- Test block runs against 5 sample responses and prints verdicts

### Chunk 8 — Competitor extractor
**Goal:** Given a list of competitor names and a response, return which appeared.
**File:** `src/pipeline/parser.py` (extend existing)
**Acceptance criteria:**
- `extract_competitors(competitors: list[str], response: str) -> list[str]`
- Returns only the competitors that appear in the response
- Case-insensitive

### Chunk 9 — Supabase storage
**Goal:** Store prompt results to Supabase.
**File:** `src/storage/db.py`, `src/storage/models.py`
**Acceptance criteria:**
- Tables: `prompt_runs`, `prompt_results`, `brand_mentions`, `citations`
- `save_run(results: list[PromptResult]) -> run_id` function
- Test block saves a mock result and confirms row exists

### Chunk 10 — Report generator
**Goal:** Generate a structured markdown audit report from a stored run.
**File:** `src/audit/report.py`
**Acceptance criteria:**
- Takes a run_id, loads results from storage
- Outputs markdown with: mention rate, competitor map, top cited domains, date stamp
- Test block generates a report from mock data and prints it

### Chunk 11 — Technical accessibility checker
**Goal:** Check whether AI crawlers can reach a domain.
**File:** `src/audit/technical_check.py`
**Acceptance criteria:**
- `check_robots_txt(domain: str) -> dict` — returns which AI crawlers are blocked
- `check_llms_txt(domain: str) -> dict` — returns whether llms.txt exists and is valid
- `check_sitemap(domain: str) -> dict` — returns whether sitemap.xml exists
- Test block runs all checks against a real domain and prints results

### Chunk 12 — Dry run
**Goal:** Run the full pipeline end-to-end against one real client domain.
**No new files** — this is integration and debugging.
**Acceptance criteria:**
- 10+ prompts sent to all 4 engines
- Results stored in Supabase
- Brand mentions and competitor appearances extracted
- Technical accessibility checks complete
- Markdown report generated with date stamp
- No unhandled exceptions

---

## Phase 1 Exit Gate — QA Checklist

Do not move to Phase 2 until all of these pass:

- [ ] 10 prompts sent to all 4 engines and responses stored
- [ ] Brand mention detection returns correct result on sample responses
- [ ] Perplexity citations extracted correctly
- [ ] robots.txt checker correctly identifies blocked AI crawlers on a test domain
- [ ] llms.txt checker returns correct result
- [ ] Storage saves and retrieves results without errors
- [ ] Report generates clean markdown with timestamp
- [ ] Full dry run on one real domain produces a readable audit report

---

## How to Use This Document

**Starting a new Cursor/Claude Code session:**
Paste this entire document at the start of the session. Tell it which chunk you are working on. It now has full project context.

**Asking for a build chunk:**
Say: "I am working on Chunk [N]. Follow the coding rules and scope locks. Build only this chunk. Report back files changed, test output, and suggested next chunk."

**After a Cursor session:**
Log what changed, what files were touched, whether acceptance criteria passed, and any errors hit. This becomes your build attempt record.

**When something breaks:**
Paste the error log and say: "Analyze this error in the context of the GEO Measurement Platform. Identify the category, suggest a fix, and write a repair prompt."

**When moving to Phase 2:**
Phase 2 begins after the dry run passes. The Phase 2 focus is: real client audits, case study generation, and converting the pipeline output into a client-facing report format. Do not plan Phase 2 until Phase 1 QA checklist is complete.