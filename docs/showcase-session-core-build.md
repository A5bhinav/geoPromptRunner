# Coding-Agent Session — Building the GEO Measurement Platform from an empty repo

> **Curated transcript.** Distilled from a real Claude Code session
> (`94c080b2`, May 31 – Jun 4 2026 · 1,032 assistant turns · 525 tool calls),
> model **Claude Opus**. Prompts and the agent's prose are quoted verbatim;
> repetitive tool I/O is condensed for readability. Secrets that appeared in the
> raw log have been removed.

---

## Why I'm proud of this one

This is the session that took the project from an **empty repository** (docs +
README only) to a fully typed, tested, hardened measurement platform — four LLM
engines, a scoring pipeline, Supabase storage, and an audit reporter — and then
turned the agent on its *own* work for an efficiency/security pass and a
recall-biased code review.

What makes it worth uploading isn't the volume of code. It's the **discipline of
the loop**: every unit of work was built against an explicit spec, run through
the same `format → mypy --strict → ruff → execute → verify-invariants` gate, and
**only logged as done after every acceptance criterion actually passed** — with
the proof shown, not asserted. The agent refused scope creep, dropped two of its
own proposed changes when they didn't survive scrutiny, and proved
behaviour-equivalence with **3,500 randomized cases** rather than claiming it.

---

## Setup: the working contract

The repo shipped with a `CLAUDE.md` development guide defining **chunks**, **scope
locks**, and a **validation loop**. The session's whole character comes from the
agent treating that contract as binding:

- **Scope locks** — build *only* the requested chunk + its hard prerequisites.
- **Non-goals are non-negotiable** — the pipeline stays **synchronous**; async is
  off the table no matter how tempting.
- **Invariant #1** — engines must **return `None` on error, never raise**.
- **No API key, ever, in a log line.**
- **Build log is append-only**, written *after* acceptance, most-recent-first.

---

## Act 1 — Chunk 1: the base engine interface

> **User:** *"I am working on Chunk 1 — Base engine interface. Follow the coding
> rules and scope locks in this document. Build only this chunk. Report back
> files changed, test output, and confirm all acceptance criteria pass. Make sure
> to create all of the necessary prerequisite files."*

The agent oriented before writing a line:

> **Claude:** "The project is essentially empty (only docs + README)… This is the
> first chunk — no build log exists yet, and the repo has no source tree or
> tooling."

It then scoped prerequisites precisely — `requirements.txt`, `.env.example`,
`pyproject.toml` (so the validation loop is *runnable*), `.gitignore` — built the
`BaseEngine` ABC, and ran the gate:

> **Claude:** "mypy (strict) and ruff both pass. Now Step 4/5 — verify clean
> import and the abstract-class contract (Chunk 1's acceptance criteria)."
>
> "Chunk 1 is complete. Per the scope lock, I built only this chunk plus its
> prerequisites — **no engine implementations, pipeline, or storage.**"

The first build-log entry was written only after the criteria passed.

---

## Act 2 — Chunks 2–5: the four engines

> **User:** *"Complete chunk 2–5 under the same rules"*

The agent's standout move here was **not trusting its own memory of SDK
surfaces**:

> **Claude:** "Let me verify the exact error-class and type names in these
> installed versions before writing the engines."

It built `OpenAIEngine`, `AnthropicEngine`, `PerplexityEngine` (raw `httpx` +
`query_with_citations()`), and `GeminiEngine`, fixed a documented `type: ignore`
for the deprecated Gemini lib's missing re-exports, then ran the invariant test
that matters most:

> **Claude:** "Now the critical invariant test (§12 #1): with keys present,
> `query()` must **return `None` on error, never raise**. I'll set dummy keys and
> confirm each engine instantiates and `query()` returns `None` on an auth/network
> failure."
>
> "All four run cleanly… All acceptance criteria pass for Chunks 2–5. Per the
> scope lock I built only these four engines plus the one required prerequisite
> (`config/settings.py`) — **no pipeline, parser, storage, or audit code.**"

---

## Act 3 — Chunks 6–11: pipeline, storage, audit

> **User:** *"Build out chunks 6–11 in the same style"*

Built in dependency order (models/types → pipeline → storage → audit): the
order-stable synchronous `run_prompts`, the pure case-insensitive
word-boundary `parser` (`detect_mention` / `extract_competitors`), the Supabase
`db` layer (uuid4 PKs, `archived_at` soft-delete, **every write in a try/except**),
the report renderer, and the technical-accessibility checker.

Then it verified against the **live network**, not a mock:

> **Claude:** "`parser` verdicts all correct… `technical_check` ran live against
> example.com… the robots checker correctly flags blocked AI crawlers (**NYT
> blocks 6 of 7**)."

Eleven chunks in, 18 source files, all green under mypy-strict + ruff.

---

## Act 4 — Self-directed efficiency & security hardening

> **User:** *"Go through the entire codebase and make everything more efficient…
> Harden all of the security as well. Make sure that there are no leaks. Make sure
> that everything is efficient when we put prompts in as well."*

This is where the session gets interesting — an open-ended ask, answered with a
**concrete, justified plan** that explicitly honoured the scope locks:

> **Claude:** "…concrete, justified changes only, respecting the scope locks (the
> pipeline stays **synchronous** per the non-goals, no new features)."

The changes targeted *real* hot paths, not vibes:

- **`parser.py`** (runs over *every* response): precompile the recommendation
  regex once at import; `lru_cache` compiled brand patterns; check recommendation
  language **once per response instead of once per competitor** — turning
  **~5k regex ops into ~k** for *k* competitors.
- **`perplexity_engine.py`**: one persistent pooled `httpx.Client` reused across
  prompts instead of a fresh TCP/TLS handshake per call.
- **`db.py`**: lazy-singleton Supabase client; **write-failure logs record the
  exception *type* only** — "Postgres errors can echo back the row values being
  inserted."
- **engines**: explicit timeout + bounded retries so one hung request can't stall
  a synchronous run.
- **`.gitignore`**: comprehensive secret coverage (`.env*`, `*.pem/*.key`,
  `service-account*.json`, `.netrc`, …).

And it *proved* the security claim instead of asserting it:

> **Claude:** "All correct: every secret variant is ignored, while `.env.example`,
> requirements, source, and `data/` files remain committable… (`!!` = `.venv`, all
> caches, all `__pycache__`)."
>
> "All edge cases pass, the optimized batch path is **provably identical** to
> per-brand, and the empty-brand leak/false-positive is fixed… All four engines
> still honor the never-raise invariant after the client changes."

---

## Act 5 — A recall-biased, multi-agent code review of its own work

> **User (review harness):** *"high effort → 3+4 angles × 6 candidates → 1-vote
> verify (recall-biased) → ≤10 findings. You are reviewing for **recall**… catch
> every real bug a careful reviewer would catch in one sitting."*

The agent gathered the diff, checked for dangling references to removed symbols
first, then **fanned out finder angles in parallel** (correctness A/B/C, cleanup,
efficiency, altitude) via subagents — and then did the thing that separates a
good review from a checkbox one: it **verified the standout finding against the
actual source** before reporting it.

> **Claude:** "Confirmed findings: **db.py:163** — the read path (`_select_rows`)
> still logs the raw `exc`, while all 5 write/connect sites were changed to
> `type(exc).__name__`. **The commit's own security fix is applied
> inconsistently.**"

Crucially, it also **refuted** a plausible-sounding finding:

> **Claude:** "No threading/async anywhere → the db cached-client *race* is not
> realistically reachable in this synchronous codebase, so I'm **dropping it
> (REFUTED for this scope).**"

The review caught a leak the *hardening pass itself had missed* on the read path —
exactly the bug a recall-biased review exists to find.

---

## Act 6 — Apply the fixes, prove nothing regressed

> **User:** *"apply the fixes"*

Before touching anything, the agent dropped a *second* finding under re-scrutiny —
and explained why rather than quietly adding complexity:

> **Claude:** "I'm **dropping finding #4** (db cached-but-broken client) —
> credentials come from module-level `settings.*` read once at import and never
> change mid-run… Caching introduces no regression there… I'll explain that in the
> summary rather than add complexity for no benefit."

It then applied 6 of 7 findings as *consolidations*, not patches — e.g. a single
`_execute(op_label, operation)` helper in `db.py` that owns the try/except, logs
only the exception type, and routes **all writes *and* the read path** through it,
closing the leak and deleting the 4× copy-pasted blocks in one move.

The verification is the part I'd point a skeptic to:

> **Claude:** "All verifications pass: parser is behavior-identical across
> **3,500 randomized cases** (including the edge cases), engines honor never-raise
> with the centralized 60s/2-retry settings, Perplexity `close()`/`__del__` work,
> and **the simulated sensitive value (`SSN-123`) did *not* leak to logs** —
> `_execute` logged only `save_results for run abc failed: RuntimeError`."

| # | Finding | Fix |
|---|---------|-----|
| 1 + 6 | Read path still logged raw exceptions; 4× copy-pasted write blocks | One `_execute()` helper; type-only logging; all 6 sites routed through it |
| 2 + 5 | 30s timeout could drop slow-but-valid generations; constants triplicated | Centralized in `settings.py`; default raised to a safer **60s** |
| 3 | Perplexity `httpx.Client` connection leak | `close()` + best-effort `__del__` |
| 7 | Duplicated classification ladder in `parser.py` | Extracted shared `_classify(present, recommended)` |
| 4 | "Cached broken Supabase client" | **Dropped — refuted**, with reasoning recorded |

---

## What the session went on to do

The same loop carried the project much further over the following days (all in
this one session): wiring the engine end-to-end on the `QueryResult` model,
intent-tagged multi-run metrics, gap-analysis fixes, **live browsing/grounding
surfaces + Google AI Overviews**, cross-engine citations, a B2C
(Berkeley/Silicon-Valley) niche pivot across content and docs, and the
**LLM-judge** with a gold-set calibration harness and Supabase persistence —
each chunk gated the same way and logged only on green.

---

## Takeaways — why this is a model session

1. **A spec the agent actually obeys beats a clever agent.** Scope locks and a
   named validation loop turned 1,000 turns into a *consistent* process instead of
   a thousand independent guesses.
2. **Proof over assertion.** "Behaviour-identical" meant 3,500 cases; "no leak"
   meant a planted `SSN-123` that didn't appear. Claims were demonstrated.
3. **The agent argued with itself — and won the right arguments.** It dropped two
   of its own proposed changes when they didn't survive scrutiny, and recorded
   *why*.
4. **Security was a property, not a feature.** Type-only error logging, a
   `git check-ignore` audit, and the never-raise invariant were re-verified after
   every change that could touch them.

---

*Produced from the real session transcript on disk. The raw `.jsonl` contains
live API credentials that were pasted into prompts during the session — redact or
rotate those before sharing the raw file. This curated version contains none.*
