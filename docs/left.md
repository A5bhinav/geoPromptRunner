# What's Left

**As of 2026-06-03; front-end item updated 2026-06-06.** The engine build order from `design-and-decisions.md` §8 (items 1–11)
is effectively done: LLM judge, cross-engine citations + AI Overviews, losing-queries view,
teaser mode, orchestrator + dry run, cadence comparison, rubric capture + roadmap rollup,
WAF/UA technical check, and a test suite all exist. The main audit report is now unified on
the judge with regex as fallback.

What remains falls into four buckets: **small code gaps** (cheap, derive from data we already
produce), **process/product work** (needs real inputs or a separate build), **deferred-by-design**
(explicit Phase-1 non-goals), and **operational** (a secrets rotation the user owns).

---

## 1 · Small code gaps (cheap, unblock report cells)

- **✅ §1 AI Visibility Grade (A–F).** Done — `judge_metrics.visibility_grade()` rolls the
  client's prominence-weighted visibility, discounted by severity-weighted accuracy flags, into
  an A–F letter; rendered at the top of `judge_sections` (so it appears in both the standalone
  judge report and the unified audit report).
- **✅ Persona / modifier field on `Query`.** Done — optional `persona` field on `Query`, read by
  the query-set loader, and rendered as the §6.1 Query Set appendix (Persona/modifier column) via
  `render_audit_report(query_set=…)`. Sample query set populated with personas.
- **✅ Trend column in the unified report.** Done — `render_audit_report(previous=…, previous_label=…)`
  renders a "Trend vs <run>" per-brand mention-rate delta section (results-based, so it works on
  either detection path). Wired into the CLI as `report --previous <run_id>` and
  `audit --compare <run_id>`.
- **Competitor-as-subject runs (optional, NOT built).** The §3 leaderboard is real today because
  the judge scores all brands in one pass (prominence is relative within an answer). Running the
  full query set independently with each *competitor* as the subject — to characterize their own
  answers — is not built. Decide whether it's actually needed before building it.

## 2 · Process / product work (needs real inputs or a separate build)

- **Real proxy audit.** Run the full pipeline live against a real company (Oura is the
  standing candidate) to produce the first real answer corpus. Ready to execute on demand.
- **Real gold set.** `data/sample_gold.json` holds **3** placeholder items. Calibration is only
  meaningful with ~20–40 hand-labeled real answers. This is the honest "can we trust the judge?"
  check and it's currently unfounded.
- **Real client fact sheet.** Only the template (`docs/fact-sheet-template.md`) and Oura example
  exist. A real audit needs a real fact sheet so the judge's accuracy flags mean something.
- **✅ Front-end app.** Done (2026-06-03, after this doc was first written) — the CSV-upload
  web app per `docs/ui-plan.md`: Next.js (`web/`) + FastAPI (`src/api/`), multi-file CSV merge,
  preview/validate, background runs with live progress + cancel, chart-rich report, durable runs
  in Supabase with auto-resume of interrupted runs. Still open within it: auth/multi-user and
  hosting/deploy (deliberately deferred until a client touches it).
- **Schema normalization.** Storage is run-scoped tables only (`save_results`,
  `save_query_results`, `save_judgments`, `save_rubric_scores`, …). No first-class
  `clients` / `competitors` / locked-versioned `query_sets` tables with per-query persona/weight
  columns. Needed before multi-client and clean cross-run trending at scale.

## 3 · Deferred by design (Phase-1 non-goals — do not build yet)

Per `CLAUDE.md` §11. Listed so they're not mistaken for omissions.

- Async / concurrent pipeline (synchronous-first is an explicit non-goal).
- Real-time monitoring / scheduled cadence auto-runs. `due_for_rerun` is a helper only — there's
  no scheduler firing re-runs.
- Client-facing dashboard, auth / multi-user, content generation, outreach automation, CMS.

## 4 · Hardening & quality (opportunistic)

- **✅ Rendering check is coarse.** Done — `check_rendering` now measures *visible* text
  (script/style/tags stripped via `_visible_text`) instead of raw HTML length, and flags SPA
  shells (framework mount point + little server-rendered text) — the React/Next hydration-only
  case. Verdict logic split into the pure `_classify_rendering` for unit testing.
- **✅ Test coverage gaps (engines + orchestrator).** Done — added `tests/test_engines.py`
  (BaseEngine citation default, abstractness, the never-raise invariant via a mocked OpenAI
  client, missing-key ValueError) and `tests/test_orchestrator.py` (`run_audit` result count,
  `run_teaser` bucket trimming, `max_cost` abort). Suite is now **50 tests**. Calibration coverage
  is still thin (one remaining gap).

## 5 · Operational (user action)

- **Rotate the shared secrets.** The OpenAI, Anthropic, Gemini, Perplexity, and SearchApi keys,
  plus the Supabase DB password, were all pasted in plaintext in chat. Rotate them in their
  consoles. `.env` stays gitignored; keys are never logged.
- **Reconcile Supabase state.** The auto-memory note still says "tables not yet created," but
  judgments now persist and re-read live — that note is stale. Confirm the full `schema_v5.sql`
  set is migrated and the memory is updated.

---

### Suggested next order

1. The three §1/§3/§6 report cells in bucket 1 (grade, persona, trend column) — a day's work,
   and they complete the deliverable spec.
2. Real proxy audit → real gold set → real fact sheet (bucket 2) — turns the judge from
   "plausible" into "calibrated."
3. The front-end app (bucket 2) — the next real build once 1–2 prove the loop end-to-end.
