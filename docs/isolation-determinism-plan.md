# Engine Isolation & Determinism Plan

*Plan to guarantee — and prove — that every engine is tested **fresh** (no cross-query memory) with **constant inputs**, so outputs are as consistent and comparable as the medium allows. Prompted by the question: when a program calls an LLM API, is each call a new chat state, or does it build on itself?*

---

## The headline answer

**An API call is a new chat state every time — unless your code makes it stateful.** A chat-completions call is stateless by construction: the model only sees what you put in the `messages` you send. It "builds on itself" only if you (a) resend prior turns in `messages`, (b) use a stateful endpoint (OpenAI Assistants/threads, the Responses API with `previous_response_id`, `store=true`), or (c) reuse a chat object that accumulates history. **Account-level memory is a consumer-app feature (chatgpt.com); the API does not have it.** So Josh's concern — "best smart ring" → "is Oura worth it" raising Oura's share on the later query — is real in the chat apps and *not* present on the API path, as long as the code stays clean.

**Current state (verified in code):** clean. Every engine sends exactly one user message and nothing else; the runner issues each (query × engine × run) as an independent call. No history, no thread, no `store`, no `previous_response_id`. The isolation we want already holds — it's just implicit and untested. This plan makes it explicit, tested, and guarded, and adds the determinism controls.

---

## The control layers

### Layer 1 — Call isolation (statelessness)
**Rule:** each API call carries only the single query as one user message; no prior queries, no shared conversation/thread/session id, no server-side memory flag.
**Status:** ✅ true today (`messages=[{"role":"user","content": prompt}]` in every engine; runner loops independently).
**Guard:** a unit test per engine that mocks the client and asserts the outgoing payload has exactly one `user` message and no state params — so a future refactor can't silently reintroduce carryover.

### Layer 2 — No account / server-side memory
**Rule:** never opt into statefulness. No Assistants/threads, no `previous_response_id`, `store` left false/unset, no reused stateful chat object (the SDK/httpx clients we reuse are connection pools, not conversations — safe).
**Status:** ✅ none in use.
**Guard:** a written code rule + the Layer 1 payload test covers the observable surface.

### Layer 3 — Constant inputs
**Rule:** the instrument is held fixed.
- Identical query text sent to every engine (no per-engine tuning — the schema's "never tune per engine").
- No system prompt on the measured engines (only the *judge* has one). If one is ever added, it's identical across the whole set.
- `temperature = 0` (already pinned via `ENGINE_TEMPERATURE`).
- Model pinned — and ideally pinned to a **dated snapshot** (e.g. `gpt-4o-2024-08-06`) rather than a floating alias, so a provider's silent model update doesn't move your baseline between cycles.
- `max_tokens` held constant *within* each engine across the whole set.
**Status:** ⚠️ mostly — temperature pinned; models pinned to names but some are floating aliases, not dated snapshots.
**Build:** switch to dated model snapshots where the provider offers them; record the exact model string in each run's metadata.
*Honesty:* you can't equalize inputs *across* providers (different models, different param semantics) — and you shouldn't try. The goal is constant inputs **per engine across the query set and across cycles**, so within-engine comparisons and trends are valid. Cross-engine numbers are read side-by-side, never as if produced by one machine.

### Layer 4 — Independent repeats + aggregation
**Rule:** run each query K times per engine as separate fresh calls, then aggregate (majority label / mean score) to wash out run-to-run randomness.
**Status:** ✅ `runs_per_query=3` default; each run is its own isolated call; metrics aggregate.
**Build:** set `seed` where the provider supports it (OpenAI) for extra best-effort reproducibility; keep K configurable. Note this is the *runner's* K (engine randomness) — distinct from the analyzer's K-pass self-consistency (analyzer reproducibility). Different stage, different purpose; don't conflate.

### Layer 5 — Acknowledge irreducible variance (retrieval surfaces)
**Reality:** the live-search/grounded surfaces (ChatGPT-with-search, Gemini grounding, Perplexity, AI Overviews) fetch the web at call time, so they vary run-to-run **even at temperature 0** — the web changes and retrieval is nondeterministic. This is not a bug to eliminate; it's the surface behaving as a buyer would see it.
**Controls:** run the whole set in one tight time window so web state is ~constant across queries; record a timestamp per call; lean on Layer-4 aggregation; report parametric and retrieval surfaces separately so their different variance profiles are visible. **We promise constant inputs and measured variance — not identical outputs — for retrieval surfaces.**

---

## Verification suite (how we prove it, not just claim it)

| Test | What it proves | Method |
|---|---|---|
| **A · Memory-probe canary** | Statelessness, empirically | Call query A; then in a *separate* call ask "what did I just ask you?" A stateless API can't answer. If it can, isolation is broken. Run per engine. |
| **B · Payload assertion** | No state params leave the process | Mock each engine's client, inspect call args: exactly one user message, no `store`/thread/`previous_response_id`. |
| **C · Order-shuffle** | No cross-query leakage | Run the set in order, then reversed; per-query results show no systematic shift beyond random variance. |
| **D · Determinism baseline** | How much variance to expect | Run one query K=10× at temp 0 on a parametric engine; record agreement rate. Calibrates the right K and sets the "normal noise" band. |
| **E · Payload logging** | Auditability | Log/store the exact outgoing request (minus secrets) per call, so any run is reconstructable. |

Tests A and B are the load-bearing ones — they directly answer "is each call fresh?" with evidence. They become part of the suite so the guarantee can't silently rot.

---

## What's already done vs. to build

**Already true:** stateless calls, single-message payloads, independent per-query/per-run loop, temperature 0, 3-run aggregation. The core guarantee Josh is asking for **already holds** on the API path.

**To build (small, ordered):**
1. **Layer-1 payload test + Layer-2 code rule** — lock the statelessness in so it can't regress.
2. **Memory-probe canary test (A)** — the empirical proof, per engine.
3. **Dated model snapshots + per-run metadata** (Layer 3) — pin the model so baselines don't drift between cycles.
4. **`seed` where supported + determinism baseline (D)** — quantify residual noise, confirm K=3 is enough (or raise it).
5. **Order-shuffle + payload logging (C, E)** — defense-in-depth + auditability.

None of these change results; they convert an implicit property into a proven, guarded one.

---

## One-line confirmation for the team

On the API, each query is already a clean-room: one isolated call, one message, no memory of the queries before it — the opposite of the chat-app context web. What this plan adds is the *proof* (the canary + payload tests), the *anti-regression guard*, and the model/seed pins that keep two measurement cycles comparable. The only variance we can't remove is the live web itself on the retrieval surfaces — and that we handle by running tight in time and aggregating, not by pretending it's zero.

---

## Determinism baseline result (2026-06-19) — K is set

Ran `scripts/run_determinism.py --surface both` (probe: *"best smart ring for sleep tracking"*, client Oura, k=5) across the parametric + retrieval surfaces:

| Engine | Surface | Text agreement | **Label agreement** (min / mean) | Suggested K |
|---|---|---|---|---|
| openai | memory · parametric | 20% (5/5 unique) | **100% / 100%** | **3** |
| anthropic | memory · parametric | 20% (5/5 unique) | **100% / 100%** | **3** |
| gemini | memory · parametric | 80% (2 unique) | **60% / 92%** | **5** |
| perplexity | memory · retrieval | 20% (5/5 unique) | **60% / 88%** | **5** |
| gemini_grounded | search · retrieval | 20% (5/5 unique) | **40% / 68%** | **10** |

**The finding:** text agreement is ~20% (answers are verbatim-unique at temp 0) and would *spuriously* suggest K=10 — but the **label-level** read is what the audit measures, and it splits cleanly by surface:

- **Memory parametric (openai, anthropic): 100% stable → K=3.** Rock-solid.
- **Gemini (memory parametric): 60% min / 92% mean → K=5.** One brand wobbles; gemini is noisier than the OpenAI/Anthropic pair even off-retrieval.
- **Retrieval surfaces (perplexity → K=5, gemini_grounded → K=10):** they re-rank brands run-to-run as the live web shifts — expected, not a defect.

**K decision:** **K=3** if an audit uses only openai+anthropic; **K=5** for the standard *memory-surface* audit (the Oura/Fort path — openai/anthropic/gemini/perplexity), to stabilize gemini + perplexity; **K=10** for retrieval-heavy audits that include `gemini_grounded`. The current CLI default is 3 — **bump it to 5 for any audit that includes gemini or perplexity** (both are in the standard memory set).

**Trend noise floor is surface-dependent — do not use one global value.** Memory parametric ≈ ±0–8 pts; gemini/perplexity ≈ ±10–15 pts (mean) or up to ±40 (worst single brand, small k=5 sample); gemini_grounded ≈ ±30–60 pts. The harness's single global floor (1 − worst, here ±60) is too blunt across mixed surfaces — set the trend `--noise-floor` **per surface** (memory ≈ 0.10–0.15; retrieval ≈ 0.40). A fuller run (higher K, several probe queries) will tighten these.
