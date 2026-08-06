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

## 0.5 · The set is scoped to THE BUSINESS, not to a template

**Added 2026-08-04, after a set shipped that proved the rest of this document was
being read as optional.** Black Propeller — a B2B paid-media agency — was measured
with:

> `my Digital Marketing Agency keeps breaking, what should I do`
> `is this an emergency or can it wait until Monday`
> `what does a Digital Marketing Agency actually do on a first visit`
> `Black Propeller vs Tinuiti, Directive, KlientBoost, Disruptive Advertising, Power Digital, JumpFly`

Twenty-five questions, 375 calls, $5.14, and not one of them is a question any
buyer of that business has ever typed. The mechanics are post-mortemed in
`docs/build-log.md`; the **rule** that has to survive the fix is this:

> **A query set is generated for a specific business in a specific field. It is
> never a generic bank with the client's category substituted into it.**

Substitution is not scoping. `{category}` is a noun slot with no idea what kind
of noun it holds, so a bank sourced from plumbing buyers produces plumbing
questions about whatever you put in it. A field's buyers have their own
vocabulary (*retainer*, *managed spend*, *ROAS*, *in-housing*), their own
decision (a pitch and a three-month contract, not a call-out), their own
objections and their own comparison set. None of that is reachable by string
substitution, and a set that misses it measures a market the client is not in.

### 0.5.1 · What must be established before a single query is drafted

Four things, all of them from the intake and the fact sheet — never guessed, and
never inferred from the crawl:

| Input | Where it comes from | What it decides |
|---|---|---|
| **Geo-dependence** | `Q-KIND-01` — asked out loud | Whether the set has a local funnel at all. Unanswered means NOT local: a local set is built around a city, and inventing one is what broke this. |
| **The field** | `identity_category` (`Q-WHAT-01`) + what they do (`Q-WHAT-02`) | Which buyer-language bank applies. "Digital marketing agency" and "plumber" are not two values of one variable. |
| **The buyer** | `Q-PROOF-02`'s "who is it for" | Whose language to source. A B2B marketing director and a homeowner with a leak do not phrase the same need remotely alike. |
| **The comparison set** | `Q-PROOF-02` competitors, one name per entry | The head-to-heads, which are the highest-value questions in the instrument. |

If the field cannot be established, the honest output is **no set and a stated
reason** — not a generic set. A set that cannot be built is a five-minute
conversation; a set built from the wrong field is a report that has to be
withdrawn.

### 0.5.2 · One spine, one bank per field

- **Field-independent** — `brand` and `comparison`. "is {client} legit", "how
  much does {client} cost", "{client} vs {competitor}", "best alternative to
  {competitor}". These are the same question for a ring, a rooter and a retainer.
  They stay in the shared bank.
- **Field-specific** — `problem_aware`, `category`, `adjacent_authority`, and (for
  a geo-dependent business) `local_intent`, `hybrid`, `informational`. These are
  sourced per field and stored per field. `data/query_templates.json` is the
  **local-trade** bank and must be labelled as such; it is not the default for
  anyone else.
- A field with no bank yet blocks the set. Adding one is the work in §1b, and it
  is a day, not a sprint.

### 0.5.3 · Sourcing at scale, without inventing anything

§1b's rule is unchanged and non-negotiable: **source → draft → format, never
originate.** It forbids *inventing* queries; it has never forbidden *finding*
them. So a model may be used to widen the search — Reddit and industry
communities for that field, review sites, "people also ask" boxes, forum threads,
the client's own inbound questions — and every candidate must arrive with a URL
and the verbatim snippet it came from. A candidate with no source is not a
candidate.

Three checks, and all three are structural rather than editorial:

1. **Every shape carries at least one slot.** A shape with none is the same
   string for every client alive, cannot be traced to a confirmed line, and
   cannot produce a mention — a guaranteed zero in the numerator and a live +1 in
   the denominator. Enforced in `generate.py`; a slotless shape is dropped.
2. **The top-up never crosses funnels.** A local set is filled from local
   buckets or it comes back short and blocked. Padding across funnels is what
   turned a local allocation into 13 consumer-funnel questions.
3. **Every competitor gets its own entry and its own question.** Six names in one
   field is one question no buyer would ask and five head-to-heads lost.

### 0.5.3b · Why the bank had a ceiling, and what lifts it

Measured before any of this: **31 questions max** for a local business, **30** for
a general one with two competitors. Asking for 50 was impossible whatever
`QUERY_SET_SIZE` said. The cause is one line of design:

> Every slot except `{competitor}` was **single-valued**. One category, one city,
> one year — so a shape like `best {category} in {city}` yields exactly ONE
> question however rich the fact sheet is. **The maximum size of a set was the
> number of lines in the JSON file.**

The fix is not more hand-written lines, it is **fan-out slots fed from lists the
sheet already holds**. `{competitor}` was already this and was hardcoded to the
comparison bucket; it is now the general case:

| Slot | Fed from | Yields |
|---|---|---|
| `{service}` | `Q-OFFER-01` — what they offer | `best {category} for {service}` × 6 |
| `{area}` | `Q-REACH-02` — the towns they named | `{category} in {area}` × N towns |
| `{segment}` | `Q-PROOF-02` — who it is for | one qualified head query |
| `{competitor}` | `Q-PROOF-02` — the shortlist | one head-to-head each |

This is methodology §3.2 finally expressible: *one head query, and every other
carries a qualifier drawn from the fact sheet's real segments.* Measured after:
**55** for a general business, **65** for a local one. Fifty is reachable, and the
extra questions are more specific rather than merely more numerous — every value
is a line the owner confirmed.

Three rules ride with it:

1. **Capped at six values per slot** (`_MAX_FANOUT`). Twenty services is twenty
   near-duplicates and a set that spends its whole budget on one dimension.
2. **Breadth first.** A bucket almost always truncates, so order decides
   coverage. A nested product walked every town for the first service before
   touching the second; the diagonal walk sees every service once before any
   twice.
3. **Bank order is priority order.** The top-up drops from the end, so the
   qualifier shapes sit directly behind the head query, not at the bottom of the
   bucket where a 25-question set never reaches them.

### 0.5.4 · The field-fit gate, at §6 with the read-aloud pass

The human lock (§6) gains one question, asked of the set as a whole and answered
out loud:

> **"Would somebody who buys this kind of business, in this field, type this?"**

A set that fails it does not ship, whatever its size, mix or provenance counts
say. The four questions at the top of this section pass every automated check in
`lint.py` and fail this one on sight, which is exactly why it is a human gate and
why it is not delegable.

## 1 · Inputs I assemble (the §1 required inputs)

**a. Fact sheet → analyzer-ready form.** The Oura sheet exists, but v2's analyzer needs two derived artifacts, so I prepare them alongside the queries:
- **Brand roster with `name_variants`** — e.g. Oura → ["Oura", "Oura Ring", "Ōura", "Oura Ring 5"]; Whoop → ["Whoop", "WHOOP", "Whoop band"]; Ultrahuman → ["Ultrahuman", "Ring Air"]; Samsung → ["Samsung Galaxy Ring", "Galaxy Ring"]; RingConn → ["RingConn"]. This is what powers variant matching in §2 of the analyzer.
- **Claim-ID'd fact sheet** — each falsifiable fact tagged `FS-01`, `FS-02`… (price tiers, the required $5.99/mo membership, current model = Ring 5 / 2026-05-28, flagship sleep tracking, platforms). The analyzer scores accuracy *only* against these claim_ids.

**a2. The field, the buyer and the geo-dependence** — §0.5.1. Established before any drafting, from the intake's own answers. These pick which bank is even eligible; the rest of §1 assumes they are settled.

**b. Buyer-language sourcing (the part that keeps me honest).** The schema requires real phrasing and ≥1/3 verbatim/near-verbatim queries — and the methodology forbids LLM-*originated* queries. Since a proxy has no sales calls or support tickets, I source **public** buyer language via web search: Reddit (r/ouraring, r/smartrings, r/whoop), review-site language (Best Buy, Amazon, Wirecutter comments), community forums, and "people also ask" boxes. I collect real phrasings **with provenance** (URL + verbatim snippet) so each sourced query can be marked verbatim/near-verbatim/constructed. My role is **source → draft → format**, never originate from imagination, and a human validates before lock (§6).

## 2 · Allocation plan (roadmap example distribution, at N=45)

| Bucket | Count | Share |
|---|---|---|
| 1 · Problem-aware | 7 | ~15% |
| 2 · Category / solution-aware | 13 | ~30% |
| 3 · Comparison | 11 | ~25% |
| 4 · Brand / bottom-funnel | 7 | ~15% |
| 5 · Adjacent-authority | 7 | ~15% |

Per the AEO/GEO roadmap's example distribution (15 / 30 / 25 / 15 / 15). Trim mode (gold-set, ~15–18) scales these proportionally, keeping comparison coverage of every competitor (see §3.3). *(This supersedes the looser Question-Set Schema v1 allocation of 18/31/27/15/9 — the roadmap distribution is the source of truth as of 2026-06-10.)*

## 3 · Drafting procedure, per bucket

Each query: fill `{slots}` only from the fact sheet + sourced language; obey the bucket's specific rules; tag exactly one intent.

**3.1 Problem-aware (7).** First-person buyer voice; **never** name category, client, or any brand. Anchor heavily to verbatim Reddit/forum pain posts. Oura-world example shape: *"why do I wake up exhausted even after a full night's sleep?"* (the pain, no "smart ring" anywhere).

**3.2 Category / solution-aware (13).** One head query (*"best smart ring"*); every other carries a **qualifier drawn from the fact sheet's real segments** — sleep tracking, recovery/athletes, battery life, no-subscription, women's health, budget. Year-stamp 2–3 here (*"best smart ring 2026"*, *"newest smart ring 2026"*) to bait the Ring 5 freshness/staleness behavior.

**3.3 Comparison (11).** Hard constraints from the schema: **every competitor appears in ≥1 comparison query**, and **≥2 queries leave the client (Oura) unnamed** (e.g. *"Whoop vs Ultrahuman for recovery"*, *"best alternative to the Samsung Galaxy Ring"*) — these test unprompted surfacing. Mix named head-to-heads (*"Oura vs Whoop"*) with "alternatives to {competitor}".

**3.4 Brand / bottom-funnel (7).** Probe the **claims most damaging if wrong** — for Oura: current price/tiers, the required membership, the flagship sleep capability, and the current model. Shapes: *"is the Oura Ring worth it?"*, *"how much does the Oura Ring cost?"*, *"does the Oura Ring need a subscription?"*, *"what's the newest Oura Ring?"*. This bucket is where accuracy flags surface.

**3.5 Adjacent-authority (7).** No brand named; topic must map to expertise Oura could plausibly own (sleep science, HRV, recovery, readiness, temperature, stress). Shape: *"how should I use HRV to guide my training?"*

## 4 · Phrasing pass (the §5 cross-bucket rules)

Sweep the whole draft against: write like a buyer talks to a chatbot (not keywords); one question per query, no compound asks; mix head and long-tail within each bucket; no leading queries that embed the answer; 2–3 deliberate year-stamps; slot fills only from fact sheet + sourced language.

## 5 · QA gate (run before lock — the §6 checklist)

Counts match the allocation table · every query has exactly one intent tag · no unfilled `{slots}` · every shape carries ≥1 slot · every competitor named in ≥1 query, one name per entry · client named only in bucket 4 + client-named comparisons · ≥2 comparison queries leave the client unnamed · read-aloud test passes on each · **field-fit test passes on the set (§0.5.4)** · near-duplicate sweep · ≥1/3 of the set is verbatim/near-verbatim (checked against the provenance tags from §1b).

Automated in `src/prompts/lint.py`, which blocks on the mechanical half (size, unfilled slots, competitor coverage, a comma-joined competitor field, a local set with no city, CSV round-trip) and warns on the judgement half (allocation drift, thin sourcing, near-duplicates, queries anchored to neither client nor category). **The lint cannot see field fit.** It passed the Black Propeller set with two warnings.

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
