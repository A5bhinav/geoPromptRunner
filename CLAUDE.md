# geoPromptRunner — root guide

GEO (Generative Engine Optimization) measurement platform: measures how often a
client brand appears in AI-generated answers (ChatGPT, Claude, Gemini,
Perplexity, Google AI Overviews), judges each answer for prominence/framing/
accuracy against a fact sheet, audits the client's site, and renders a report.
Powers a manual audit service for early-stage B2C consumer startups
(Berkeley/SV). Founders: Abhi (technical), Josh (sales/clients).

**Before non-trivial work, load the `geo-dev` skill**
(`.claude/skills/geo-dev/SKILL.md`) — it has the full architecture map, judge
cache-key discipline, cost model, config reference, and docs map. For judging
stored runs without API spend, use the `prejudge` skill.

## Commands

```bash
mypy src/ && ruff check src/ && pytest tests/   # gate for every change
python -m src.cli --help                        # audit/teaser/judge/report/runs/...
./run-api.sh                                    # FastAPI backend (src/api/app.py)
cd web && npm run dev                           # Next.js UI
```

## Layout

`src/engines/` (8 engine adapters) · `src/pipeline/` (orchestrator, judge,
caches, metrics, calibration) · `src/audit/` (crawl, checks, content judge,
offsite agent, synthesize) · `src/storage/` (Supabase) · `src/api/` + `web/`
(FastAPI + Next.js) · `teaser/` (TS prospect-teaser/audit generator) ·
`scripts/` (prejudge workflows, calibration, sheet builders) · `data/` (query
sets, gold sets, SQL schemas) · `docs/` (plans + client artifacts — see the
geo-dev skill's docs map; several are historical).

## Hard invariants

- Engines return `None` on error, never raise; all engines subclass
  `BaseEngine`; the pipeline never crashes because one engine failed.
- Core-data writes go through `src/storage/db.py` (`_execute` owns the
  try/except, raises `StorageError`, logs exception *type* only). The judge
  caches are the deliberate exception (pluggable backend, talk to Supabase
  directly).
- Storage is create-only. The only delete path is explicit project deletion
  (hard delete; Storage HTML blobs first, then rows). `archived_at` is
  vestigial — never build on it.
- **Judge cache keys are sacred.** Any change to judge prompts, tool schema, or
  prompt layout must bump `_PROMPT_LAYOUT` in `src/pipeline/judge.py`, keeps
  the HEAD/RUBRIC split parity with `scripts/judge_via_workflow.py`, and
  invalidates every cached verdict (prejudge makes re-warming free). Parity
  tests in `tests/test_judge.py` guard this — never weaken them.
- Subscription (prejudge/Opus) verdicts are dev-only. Calibration and gold
  labeling always use the held-constant API judge with `isolated_cache()` —
  never the shared Supabase cache.
- Secrets only via `src/config/settings.py` (`os.getenv` nowhere else); never
  log key values. Engine calls cost real money — respect `MAX_AUDIT_COST_USD`
  / `MAX_TOTAL_SPEND_USD`, and prefer the prejudge flow when iterating on
  judging.
- Type hints on all signatures; `from __future__ import annotations`; typed
  dicts/dataclasses across function boundaries; no swallowed exceptions; no
  `# type: ignore` without a same-line reason.

## Process

- Validation loop for every change: write → `mypy` → `ruff` → run → tests pass.
- `docs/build-log.md` is append-only, one entry per completed milestone
  (most recent first). Don't edit old entries; patches get their own entry.
- `docs/claude.md` is the **historical** Phase-1 guide — superseded by this
  file + the geo-dev skill. Don't follow its build plan or file map.
