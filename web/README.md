# GEO Audit — Web UI

Next.js front end for the GEO audit pipeline. Upload one or more CSVs → preview
the merged audit → run it across the engines → read the report.

## Stack

- Next.js (App Router) + TypeScript
- Tailwind CSS + hand-rolled shadcn-style components
- Recharts for the leaderboard bars

## Run it

You need the **API** running first (it lives in `../src/api`):

```bash
# from the repo root, using the PROJECT venv (not conda base) — it has the deps:
.venv/bin/python -m uvicorn src.api.app:app --reload --port 8000
# or: source .venv/bin/activate && uvicorn src.api.app:app --reload --port 8000
```

> Running with the wrong interpreter (e.g. conda base) fails with
> `ImportError: cannot import name 'genai'` — that env is missing the engine
> SDKs. The API now skips an engine whose SDK is absent rather than crashing,
> but you still want the venv so the real engines are available.

Then the front end:

```bash
cd web
npm install
cp .env.local.example .env.local   # optional; defaults to http://localhost:8000
npm run dev                         # http://localhost:3000
```

`NEXT_PUBLIC_API_URL` points the UI at the API (default `http://localhost:8000`).

## The flow

1. **Upload** (`/`) — drag in one combined CSV, or split files (config / facts /
   queries). They merge into one audit; each file shows what it contributed.
2. **Preview** — Config / Fact sheet / Queries tabs with per-file provenance and
   inline validation. "Run audit" stays disabled until the merged set is clean.
3. **Progress** (`/audits/[id]`) — live call counter, per-engine chips, elapsed
   time, cancel.
4. **Report** — scorecard (grade, share-of-model, mention/citation rate,
   accuracy), per-bucket table, competitive leaderboard, sources, losing
   queries. Export to print/PDF or download the JSON.

## Demo without API keys

Set `engines` to `mock` in your CSV (`config,engines,mock,,`) to run the whole
flow against a keyless mock engine — no real API calls, deterministic output.

## CSV format

See the downloadable template (the "Download template" link on the upload
screen, served by the API at `/template.csv`). One schema for every file:

```
block,key,value,intent,persona
```

- `config` rows → run settings (`client_name`, `category`, `competitors`,
  `engines`, `runs_per_query`, `client_domains`, `judge`)
- `fact` rows → fact-sheet content (concatenated for the judge)
- `query` rows → `key` = id, `value` = text, plus `intent` and `persona`

Lists inside a cell use `;` so commas stay the delimiter.
