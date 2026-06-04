# GEO Measurement Platform

A data pipeline and audit tool that measures how often a brand appears in
AI-generated answers across **ChatGPT, Claude, Gemini, and Perplexity** (plus
Google AI Overviews). GEO = Generative Engine Optimization — the AI-answer
analogue of SEO.

**Niche:** early-stage **B2C consumer startups in the Berkeley / Silicon Valley
ecosystem**. When a consumer asks an AI "best app for X," this measures whether
the client shows up, whether competitors show up instead, and which sources are
driving those recommendations.

## What it does

- Runs a versioned, intent-tagged **query set** across every engine, multiple
  times per cycle (to average out LLM nondeterminism).
- Measures **mention rate** and **citation rate** (overall and per funnel
  bucket), **share-of-voice** vs. named competitors, the **losing queries**
  (where the client is absent but a rival shows), and the **sources behind the
  category** (ranked cited domains).
- Captures **cross-engine citations** from the live-search surfaces.
- Stores runs in Supabase, supports **cadence comparison** (before/after over
  time), a **rubric → prioritized roadmap** (Step-6), **competitor discovery**,
  and **technical accessibility** checks (incl. AI-bot CDN/WAF blocking).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in API keys + Supabase creds
```

## CLI

```bash
python -m src.cli audit data/sample_queries.json --domains example.com   # full audit
python -m src.cli teaser data/sample_queries.json                        # fast demo
python -m src.cli report <run_id>                                        # render a stored run
python -m src.cli compare <before_run_id> <after_run_id>                 # cadence diff
python -m src.cli discover <run_id>                                      # find unnamed competitors
python -m src.cli technical example.com                                  # technical checks
python -m src.cli roadmap data/sample_rubric.json --brand Acme           # §4/§5 roadmap
python -m src.cli runs "<client>"                                        # list stored runs
python -m src.cli due "<client>"                                         # cadence re-run check
```

Add `--surface search` to `audit`/`teaser` to measure the live-retrieval
surfaces (ChatGPT-with-search, Claude-with-search, Gemini grounding, Perplexity,
Google AI Overviews) instead of parametric memory.

## Development

```bash
mypy src/            # strict type checking
ruff check src/      # lint
pytest tests/        # tests
```

See `docs/CLAUDE.md` for the full development guide and methodology.
