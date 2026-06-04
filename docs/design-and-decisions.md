# GEO Engine — Design & Decisions

*Single reference for what we've decided about the audit engine: where it stands, the LLM judge design, the fact-sheet model, the testing plan, and what's next. Pulls together the working conversation so it's not scattered. Companion docs are linked inline.*

**Related docs in this folder**
- `engine-gap-analysis.md` — full gap analysis of the engine vs. the roadmap + deliverable
- `fact-sheet-template.md` — the blank client fact sheet
- `fact-sheet-example-oura.md` — a filled B2C example (Oura)
- `project.md` — the original build spec / chunk plan

---

## 1 · What this is

The engine is the **measurement layer** behind the GEO audit service: it asks the AI answer engines (ChatGPT, Perplexity, Google AI Overviews, Claude, Gemini) the questions a client's buyers actually ask, and measures how the client shows up versus competitors. The audit method has 8 steps; **the software powers Step 1 (baseline measurement) and Step 5 (competitive benchmark)** — the visceral "here's what ChatGPT says about you vs. your competitor" demo that books meetings. Steps 2–4 and 6–8 (on-site/off-site rubric scoring, roadmap synthesis) are **analyst work for now**, not automated.

The audit **report is the engine's real spec.** If a cell is in the report, the engine has to be able to produce it. That framing drives everything below.

---

## 2 · Where the engine stands today

Clean, well-built skeleton; roughly **the second half of the build is missing**, and the half that exists has accuracy problems. Full detail in `engine-gap-analysis.md`; the headline conclusions:

- **It isn't wired end-to-end.** Four engine adapters, a query/intent model, metrics, a technical checker, storage, and a report renderer all exist — but nothing runs them together as one pipeline. The dry run (Chunk 12) was never built.
- **The good analysis is disconnected.** The intent-aware result type (`QueryResult`) that the methodology needs can't be stored or reported — storage and the report only understand the older flat shape.
- **Detection is regex.** Today mention/recommendation is keyword matching, which can't produce prominence, framing, or accuracy — the columns that make the report persuasive. **This is what the LLM judge fixes** (Section 4).
- **The engine can't fully fill a single section of the deliverable yet.** The gaps cluster on three builds: the **LLM judge**, **cross-engine citations**, and **storage/versioning**.

**API keys configured:** OpenAI, Anthropic, Gemini, Supabase — all set. **Perplexity is the only missing key.** It gates only live Perplexity calls; everything else can be built and tested with what's there. (Note: Perplexity is currently the *only* engine wired to return citations, so until that key arrives or the other engines' source-capture is built, citation features have no live data.)

---

## 3 · The deliverable, and what the engine must produce

The report's engine-powered cells live in Sections 1, 2, 3, 4.4, and 6. The recurring asks the engine doesn't yet meet:

- **Prominence / rank** per brand per query (recommended-first / mid-pack / buried / absent) → §2.2, §3
- **Framing** (positive / neutral / negative) → so "avoid X" stops counting as a win
- **Accuracy** of what's said about the client + typed hallucination flags → §1, §2.3 (the most visceral material)
- **"Losing queries"** view — the exact queries where the client is absent and a competitor is cited #1 (the report's core "symptom → cause" principle)
- **Cross-engine citations** — "sources behind the category," which also *routes* the off-site audit
- **Trend over time** on a locked, versioned query set — the proof loop, described as "the entire moat"

The first three all come from the **judge**. The rest are storage/versioning and citation work tracked in the gap analysis.

---

## 4 · The LLM judge (design — not yet built)

### What it is
The judge replaces the regex detection. The runner collects raw answers (it already does this); the **judge reads each answer and turns it into structured fields**; metrics aggregate those fields instead of grepping text. It's the "missing brain" that turns raw model output into real report numbers.

Kept as its **own pass**, separate from the runner — the runner stays a dumb collector, the judge is the brain, and you can re-judge stored answers without re-querying the engines.

### Inputs
One answer + the query it came from + the brand list (client + competitors) + an **optional** fact sheet (passed as text).

### Outputs — per brand
- **present?** — mentioned at all
- **prominence** — recommended-first / mid-pack / buried / also-ran / absent
- **framing** — positive / neutral / negative
- **accuracy flags** — *client only, only if a fact sheet is provided*: typed flags (wrong pricing / missing-or-invented feature / competitor-confusion / identity / stale), each with a claim, the reality, and a severity (high / med / low)

### Design rules (locked)
- **One held-constant judge model** across all engines — same instrument for every answer, so cross-engine comparisons are valid. Don't let each engine grade itself.
- **Judge the whole answer once, scoring all brands together** — prominence and the leaderboard are inherently *relative* ("who got named first"), so the judge must see all brands in one pass. Also halves call volume.
- **Low temperature + forced JSON output** — the judge is itself an LLM; pin down its nondeterminism.
- **Never-raise** — a failed judge call degrades to "not assessed," never crashes a run (matches the engine adapters' contract).
- **"Don't use outside knowledge"** — accuracy is checked *only* against the fact sheet, so the judge can't hallucinate accuracy from its own (stale) memory.
- **Fact-sheet-optional** — see Section 5.

### Accuracy is asymmetric — client only
The report's accuracy findings are about the **client** ("is what AI says about *you* correct"). So the judge fact-checks accuracy **only for the client.** Competitors are judged on present / prominence / framing only — none of which need a fact sheet. **Consequence: you only ever build ONE fact sheet per audit, the client's.** No competitor fact sheets, ever. Even "the model confused you with Competitor X" is caught from the *client's* sheet (its "most often confused with" field), not a competitor sheet.

### Validation
Before trusting it, check the judge's output against a small **hand-labeled gold set** (~20–40 real answers labeled by hand). This both seeds few-shot examples and is the honest answer to "how do I trust an AI grading other AIs?" — "it matches our human labels X% of the time."

### Build status
Designed, not built. Will be built **fact-sheet-optional from the start** so the proxy test runs immediately; adding the fact sheet later is purely additive (no rewrite). **Blocked on:** the fact-sheet structure Josh will provide (the judge consumes it as text, so the structure is for human/app convenience, not the judge's parsing).

---

## 5 · The fact sheet

### What it is and why
The fact sheet is the **ground truth the judge checks AI answers against.** It's the only way to score accuracy — to say "ChatGPT claims you start at $20/seat, which is wrong," the judge needs to know the real price. Without it, the judge would fall back on its own stale training memory, which defeats the purpose. Accuracy/hallucination flags are the **most visceral demo material**, so the fact sheet powers the highest-converting part of the report.

It feeds **only the accuracy cells** (§1 accuracy, §2.3 flags). Mention, prominence, and framing need no fact sheet.

### Key properties (decided)
- **One per company, client only** (see Section 4) — not reusable across clients, but you never need a competitor's.
- **Optional / never a blocker.** No fact sheet → the judge still does present/prominence/framing for every brand; accuracy just renders "not assessed." So you can run the engine and demo the leaderboard with zero fact sheets. It's an upgrade layer, not a gate.
- **Made during Step 0 intake** ideally (the client hands you the facts and confirms they're current); for testing, built from public info.
- **Blank is safe** — the judge only checks facts that are present, so an empty field never produces a false flag. A thin first pass is fine.
- **Falsifiable facts only** — checkable claims (price, feature, founding year), never marketing language.
- **Front-loaded cost** — ~30–60 min the first time per company, then only updated when pricing/features change (which is also when you'd re-run the audit).

### Structure
Five sections, each mapping to a category of error a model makes: **A** Identity, **B** Pricing, **C** Features, **D** Positioning & competitors, **E** Known-inaccuracy watch-list (a table mirroring the report's §2.3, the demo-driving section). Full template in `fact-sheet-template.md`; worked B2C example in `fact-sheet-example-oura.md`.

The Oura example is a good illustration of the mechanism: because the Ring 5 launched days ago, a typical answer ("Ring 4 is newest, $349, no subscription") trips three flags at once — stale model, wrong price, missed mandatory fee — which is exactly what a demo opens with.

---

## 6 · Testing plan (no clients needed)

The fact sheet, schema, and label taxonomy are **outputs of one manual test run**, not prerequisites. The plan:

1. **Pick a proxy company** — a real, established company in a category with 3–5 clear competitors (established = the models have lots of stale opinions = real signal). A mid-tier player, not the leader, so the picture looks like a real client's ("we're getting buried"). Oura is the worked example.
2. **Build a v0 fact sheet** from public info (designing the template through use).
3. **Write ~10–15 queries** across intent buckets (the existing `data/sample_queries.json` is a starting shape — swap brand/competitors).
4. **Run the engine** against the three live engines (OpenAI, Anthropic, Gemini — no Perplexity needed). Real answers.
5. **Hand-label the answers** (present / prominence / framing / accuracy). This designs the label taxonomy, proves accuracy-checking is tractable, and *becomes the gold set*.
6. **Then build the judge** and check it against the hand labels.

Storage is irrelevant to this — the runner returns results in memory; dump to JSON/CSV and label in a spreadsheet. Decouple testing from the database entirely.

---

## 7 · Front end

**There is none today.** Prompts live in a hand-authored JSON file (`data/sample_queries.json`) loaded by `query_set.py`. No web app, no form, no UI, not even a real CLI — just per-module test blocks. Entering prompts today = editing JSON by hand.

That's fine for testing now. The "app" (where you'd type prompts and paste the fact sheet) is a **separate, meaningful build** that should come *after* the judge/runner loop is proven, once the fact-sheet structure and query set have defined exactly what fields it must collect.

---

## 8 · Build order (engine)

Re-prioritized around the deliverable (full rationale in `engine-gap-analysis.md`). The demo (§2/§3) first, then persistence/versioning, then the rest:

1. **LLM judge** — prominence, framing, accuracy + typed flags. Lights up cells across four report sections. *(highest leverage)*
2. **Cross-engine citations** + Google AI Overviews path; also routes the off-site audit.
3. **"Losing queries" view** — symptom → cause; the report's connective tissue.
4. **Run the set for client *and* competitors**, ranked — makes §3 / Step 5 real.
5. **Teaser/demo mode** — client + 1 competitor, ~5 queries, fast §2/§3 render. The meeting-booker.
6. **Schema redesign** — clients, competitors, locked/versioned query sets, per-query weights + persona, unify on `QueryResult`.
7. **Orchestrator + dry run** — wire runner → judge → metrics → storage → report; persist incrementally.
8. **Cadence re-run + comparison (Step 8, "the moat")** — re-run the locked set and diff to show movement.
9. **Rubric data capture + roadmap rollup** — store human Cat 1–6 scores; render §4/§5; add the A–F grade.
10. **WAF/UA technical-check fix.**
11. **Tests** — starting with the parser/judge.

Items 1–5 make the sales demo real; 6–8 make it persistable and trendable; 9 produces the paid deliverable; 10–11 harden it.

---

## 9 · Open / blocked on

- **Fact-sheet structure** — Josh to provide; unblocks building the judge to expect that format.
- **Proxy run** — ready to execute on demand (Oura or another company); produces the first real answers + gold set.
- **Perplexity key** — missing; not blocking, but gates live citation data.
- **Judge spec doc** — optional next step: a `docs/judge-spec.md` with the exact output schema and prompt design to hand to Abhi before coding.

---

## Decisions log (quick reference)

| Decision | Call |
|---|---|
| What the software automates | Steps 1 & 5 (measurement + benchmark); Steps 2–4, 6–8 are analyst work for now |
| Detection method | LLM judge replaces regex |
| Judge model | One held-constant model for all engines; low temp; JSON; never-raise |
| Judge scope per call | All brands in one pass (prominence is relative) |
| Accuracy checking | Client only; competitors get mention/prominence/framing only |
| Fact sheets needed | One per audit (client's); never competitor sheets |
| No fact sheet | Judge degrades gracefully — accuracy = "not assessed," rest works |
| Fact sheet format | Consumed by the judge as text; structure is for human/app convenience |
| Front end | None yet; JSON for now; build after the loop is proven |
| Testing | Proxy company + hand-labeled gold set; no clients required |
