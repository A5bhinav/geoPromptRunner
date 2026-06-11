# Query Generation Plan (Question-Set Schema v1)

*Plan for how the queries get generated, before any run. Built to satisfy **Question-Set Schema v1** and to hand the run's answers cleanly to **Answer-Analysis Schema v2**. Plan only — execution waits on the inputs in §9.*

---

## 0 · Scope & parameters

- **Worked instantiation:** Oura (smart-ring category), competitors Whoop / Ultrahuman / Samsung Galaxy Ring / RingConn. The process below is company-agnostic; Oura is the example because its fact sheet already exists.
- **Set size:** schema target 40–50. Two modes:
  - **Full instrument (default, N=45):** the real schema allocation. Doubles as a proper audit dry-run.
  - **Gold-set trim (N≈15–18):** a proportional cut weighted toward buckets 2+3 (which produce the multi-brand answers that exercise the judge's prominence ladder). Use this if the only goal right now is calibration corpus, not a full baseline.
- **Engines:** one set, run identically across all four (+ AI Overviews). Never tuned per engine.
- **Lock id:** `v1` + ISO date, recorded in the audit appendix. No mid-cycle edits after lock.

## 1 · Inputs I assemble (the §1 required inputs)

**a. Fact sheet → analyzer-ready form.** The Oura sheet exists, but v2's analyzer needs two derived artifacts, so I prepare them alongside the queries:
- **Brand roster with `name_variants`** — e.g. Oura → ["Oura", "Oura Ring", "Ōura", "Oura Ring 5"]; Whoop → ["Whoop", "WHOOP", "Whoop band"]; Ultrahuman → ["Ultrahuman", "Ring Air"]; Samsung → ["Samsung Galaxy Ring", "Galaxy Ring"]; RingConn → ["RingConn"]. This is what powers variant matching in §2 of the analyzer.
- **Claim-ID'd fact sheet** — each falsifiable fact tagged `FS-01`, `FS-02`… (price tiers, the required $5.99/mo membership, current model = Ring 5 / 2026-05-28, flagship sleep tracking, platforms). The analyzer scores accuracy *only* against these claim_ids.

**b. Buyer-language sourcing (the part that keeps me honest).** The schema requires real phrasing and ≥1/3 verbatim/near-verbatim queries — and the methodology forbids LLM-*originated* queries. Since a proxy has no sales calls or support tickets, I source **public** buyer language via web search: Reddit (r/ouraring, r/smartrings, r/whoop), review-site language (Best Buy, Amazon, Wirecutter comments), community forums, and "people also ask" boxes. I collect real phrasings **with provenance** (URL + verbatim snippet) so each sourced query can be marked verbatim/near-verbatim/constructed. My role is **source → draft → format**, never originate from imagination, and a human validates before lock (§6).

## 2 · Allocation plan (the §3 table, at N=45)

| Bucket | Count | Share | Floor rule |
|---|---|---|---|
| 1 · Problem-aware | 8 | ~18% | — |
| 2 · Category / solution-aware | 14 | ~31% | **2+3 together ≥ 55%** |
| 3 · Comparison | 12 | ~27% | (held even when trimming) |
| 4 · Brand / bottom-funnel | 7 | ~15% | kept small deliberately |
| 5 · Adjacent-authority | 4 | ~9% | — |

Trim mode scales these proportionally but never lets 2+3 drop below 55% and never drops comparison coverage of a competitor (see §3.3).

## 3 · Drafting procedure, per bucket

Each query: fill `{slots}` only from the fact sheet + sourced language; obey the bucket's specific rules; tag exactly one intent.

**3.1 Problem-aware (8).** First-person buyer voice; **never** name category, client, or any brand. Anchor heavily to verbatim Reddit/forum pain posts. Oura-world example shape: *"why do I wake up exhausted even after a full night's sleep?"* (the pain, no "smart ring" anywhere).

**3.2 Category / solution-aware (14).** One head query (*"best smart ring"*); every other carries a **qualifier drawn from the fact sheet's real segments** — sleep tracking, recovery/athletes, battery life, no-subscription, women's health, budget. Year-stamp 2–3 here (*"best smart ring 2026"*, *"newest smart ring 2026"*) to bait the Ring 5 freshness/staleness behavior.

**3.3 Comparison (12).** Hard constraints from the schema: **every competitor appears in ≥1 comparison query**, and **≥2 queries leave the client (Oura) unnamed** (e.g. *"Whoop vs Ultrahuman for recovery"*, *"best alternative to the Samsung Galaxy Ring"*) — these test unprompted surfacing. Mix named head-to-heads (*"Oura vs Whoop"*) with "alternatives to {competitor}".

**3.4 Brand / bottom-funnel (7).** Probe the **claims most damaging if wrong** — for Oura: current price/tiers, the required membership, the flagship sleep capability, and the current model. Shapes: *"is the Oura Ring worth it?"*, *"how much does the Oura Ring cost?"*, *"does the Oura Ring need a subscription?"*, *"what's the newest Oura Ring?"*. This bucket is where accuracy flags surface.

**3.5 Adjacent-authority (4).** No brand named; topic must map to expertise Oura could plausibly own (sleep science, HRV, recovery). Shape: *"how should I use HRV to guide my training?"*

## 4 · Phrasing pass (the §5 cross-bucket rules)

Sweep the whole draft against: write like a buyer talks to a chatbot (not keywords); one question per query, no compound asks; mix head and long-tail within each bucket; no leading queries that embed the answer; 2–3 deliberate year-stamps; slot fills only from fact sheet + sourced language.

## 5 · QA gate (run before lock — the §6 checklist)

Counts match the allocation table · every query has exactly one intent tag · no unfilled `{slots}` · every competitor named in ≥1 query · client named only in bucket 4 + client-named comparisons · ≥2 comparison queries leave the client unnamed · read-aloud test passes on each · near-duplicate sweep · ≥1/3 of the set is verbatim/near-verbatim (checked against the provenance tags from §1b).

## 6 · Human validation + lock (non-delegable)

Before lock, you + Abhi run the **read-aloud / "would a real buyer say this?"** pass and approve. This is the same independence gate as the gold-set labels: I draft from sourced language, a human signs off that it reflects real buyers. On approval: stamp `v1` + date, record in the appendix, freeze.

## 7 · Output & handoff

Primary artifact — the runner-ready query set in the existing `sample_queries.json` shape:

```json
{ "version": "v1", "locked_at": "<date>", "category": "smart ring",
  "client": "Oura", "competitors": ["Whoop","Ultrahuman","Samsung Galaxy Ring","RingConn"],
  "queries": [ { "query_id": "pa-01", "intent": "problem_aware", "text": "...", "weight": 1.0, "persona": "..." } ] }
```

Plus three sidecars: the **brand roster + name_variants**, the **claim-ID'd fact sheet**, and a **provenance/verbatim-flag table** (query_id → source URL + verbatim?), so the §6 ≥1/3 check is auditable and the analyzer has its inputs.

## 8 · How this feeds the rest

Queries → runner (3 runs × 4 engines, nondeterminism handled there) → answers → **Answer-Analysis Schema v2** (the roster + claim-IDs I prepped here are exactly its inputs) → those same answers become the **gold-set corpus** for your labeling session. So this one query set serves the audit *and* the calibration in a single run.

## 9 · To execute, I need from you

1. **Confirm the company** (Oura, or swap) — determines roster + fact sheet.
2. **Pick the mode** — full N=45 instrument, or the ~15–18 gold-set trim.
3. **Reserve the validation slot** — the §6 human read-aloud/lock pass (~15 min) before I freeze and run.

Then I execute §1–§5 (source buyer language, draft, phrasing pass, QA), hand you the candidate set + provenance for the §6 approval, and on your lock I format and pass it to the runner.
