# Competitor-Set Plan

*The second artifact a lead needs before it can become an audit. Spec only —
nothing here ships before §7's decisions are made.*

Authored 2026-07-31, alongside `docs/factsheet-autogen-plan.md`, which this
mirrors deliberately: same claim/evidence discipline, same human gate, same
"blank is safe" default. Companions: `docs/audit-packaging-research.md` §9.5
(binds the fact sheet and competitor set into ONE governance artifact — that is
open decision **A4**), `src/pipeline/discovery.py`, `src/engines/local_pack.py`,
`teaser/src/resolver/profileExtraction.ts`.

---

## 0 · The gap this closes

The worker turns a lead into a fact sheet and stops. A run needs **two** things:
ground truth about the client (the sheet, built) and **the brands to measure it
against** (nothing).

Today competitors reach a run from exactly one place: the `config,competitors`
row of an uploaded CSV, typed by a human. So the automated path produces an
artifact that cannot start an audit by itself.

This matters more than the coverage gap it looks like. The competitive gap is
what the audit *sells*: the methodology puts it at Step 5, and the teaser
headline is literally *"AI is sending your buyers to {competitor}"*. A fact sheet
with no competitor set can catch a wrong phone number and can never produce that
sentence.

**Out of scope:** ranking competitors, scoring them, or deciding who the "real"
rival is. This produces a *measured set*, not a judgement.

---

## 1 · The one rule everything else follows from

**A competitor set derived from engine answers is not a measurement — it is a
mirror.**

The audit asks *"which brands do AI engines recommend instead of the client?"*
If the candidate list is itself built from what those engines said, the answer is
guaranteed before the run starts: every name is present by construction, and
share-of-voice becomes a statement about our own seeding.

So the competitor set must come from **outside the instrument**. Google's local
pack, an organic SERP, a directory listing and the client's own site are all
admissible — they are what the market says. An LLM's recollection is not.

`src/pipeline/discovery.py` (`discover_competitors`) does read a completed run's
answers, and stays useful for exactly the opposite job: finding brands we were
*not* tracking so a human can add them to the NEXT cycle. It must never seed the
set it will later be measured on. That is a one-way valve, and it is the single
most important line in this document.

---

## 2 · The contract

```ts
type CompetitorSource =
  | "local_pack"      // Google's own business listing for trade + city
  | "serp_organic"    // who ranks for "best {trade} in {city}"
  | "site_comparison" // the client's own /vs, /alternatives, /compare pages
  | "directory"       // Yelp / trade association listing
  | "lead_form"       // the owner named them
  | "client";         // the owner confirmed them on a call

interface CompetitorCandidate {
  name: string;               // as the SOURCE spells it, not normalised
  aliases: string[];          // only variants an evidenced source used
  source: CompetitorSource;
  source_url: string;
  verbatim_evidence: string;  // the literal line naming them (§3)
  as_of: string;
  /** How many INDEPENDENT sources named them. Ranking input, never a verdict. */
  corroboration: number;
}

type CompetitorSetStatus = "draft" | "client_reviewed" | "signed";

interface CompetitorSet {
  domain: string;
  business_kind: BusinessKind;
  candidates: CompetitorCandidate[];
  /** Names deliberately EXCLUDED, with the reason. Kept, not deleted (§5). */
  exclusions: { name: string; reason: string }[];
  questions: string[];
  version: number;
  status: CompetitorSetStatus;
  generated_at: string;
  lead_ref: string | null;
}
```

The shape intentionally mirrors `FactClaim`: a name, the source, a verbatim line,
a date. If it cannot be quoted, it does not ship.

---

## 3 · The evidence gate

Same mechanic as §4.1 of the fact-sheet plan, and it must be the same code path
where possible: `verbatim_evidence` has to be a literal substring of the fetched
text of `source_url`.

A name a model *inferred* from a category has no such line and is dropped. This
is what stops "who are Fort's competitors" being answered from training data and
then measured against training data.

**One asymmetry worth stating.** For the fact sheet, a wrong line is a false
accusation. Here, a wrong competitor is subtler and arguably worse: it does not
look wrong. Nobody reading a report questions why "Whoop" is in the list. It
quietly changes every share-of-voice number, and the error is invisible for as
long as the client keeps paying for it.

---

## 4 · Where candidates come from, by ICP

| Source | Local service | Product | Notes |
|---|---|---|---|
| `local_pack` | **Primary** | n/a | `fetch_local_pack(query, location)` already exists and returns `LocalEntity`. It is Google's own answer to "who does this in this city" and is not an AI answer. Requires a pinned location — an unpinned pack names the wrong metro. |
| `serp_organic` | Strong | Strong | Who ranks for "best {trade} in {city}" / "best {category}". Needs a SERP call; DataForSEO is already wired. |
| `site_comparison` | Weak | **Primary** | `/vs`, `/alternatives`, `/compare` pages. A SaaS names its rivals; a plumber does not. `PageCategory.COMPARISON` already selects these. |
| `directory` | Medium | Weak | Yelp and trade associations, via `review_platforms_for(business_kind)` — call the selector, never import either constant. |
| `lead_form` | Medium | Medium | Not asked for today. Adding one field to `/free-check` is the cheapest high-quality source in this table, and it is the owner's own opinion. |
| **engine answers** | **FORBIDDEN as a seed** | **FORBIDDEN as a seed** | §1. Post-run only, via `discover_competitors`, for the next cycle. |

The local pack is the strongest starting point and needs no new vendor: it is
already fetched for local runs and already location-pinned.

---

## 5 · The rules that keep the set honest

**5.1 Same trade AND same market.** A Berkeley plumber does not compete with a
Sacramento plumber, and a franchise's national page is not a local rival. Local
candidates carry the market they were found in; a candidate from another metro is
an exclusion with a reason, not a silent drop.

**5.2 Never the client itself, and never its own aliases.** Obvious, and the
failure is not: a client with two listed names appears as its own competitor and
its share-of-voice halves.

**5.3 Never a directory, marketplace or aggregator.** Yelp, Angi, Thumbtack and
Home Advisor outrank every real business for local queries. Measuring against
them produces a report saying the client loses to Yelp, which is true and
useless. Maintain an exclusion list; record each exclusion rather than filtering
silently, so the reason is auditable.

**5.4 Corroboration ranks, it does not admit.** Two independent sources naming a
business is a strong signal for ordering the list. It is not a substitute for
evidence: a single quoted local-pack entry is admissible, an uncorroborated
inference is not.

**5.5 Cap the set, and record what was cut.** Every competitor multiplies judge
cost across every answer. 3–5 is the working range; anything dropped by the cap
goes to `exclusions` with `reason: "over cap"`, because a silent truncation reads
as "we looked and there were only five".

**5.6 Disagreement is a question.** Same as §4.3: if the local pack and the
client's own site name different rivals, that is worth asking about, not
averaging.

---

## 6 · Where it lives

Mirror the fact sheet exactly: `competitor_sets` + `competitor_candidates` in the
PLATFORM project, `draft` on write, promoted by a human.

**The review screen is the open question (A4).** Two options:

- **One artifact.** `/fact-sheets` gates the sheet AND the set together; approving
  means "this is who they are and who they compete with". Matches
  `audit-packaging-research.md` §9.5, and it is one review instead of two.
- **Two artifacts.** Separate queues and lifecycles. A sheet is durable; a
  competitor set decays faster (a new shop opens). Coupling them means re-approving
  facts that did not change.

I lean to **one screen, two independently-versioned records** — a reviewer sees
both at once, but a competitor refresh does not re-key the fact sheet, and the
fact sheet is in the judge cache key. That gets §9.5's single governance moment
without inheriting its versioning.

The F4 screen was deliberately built to gate the sheet only, structured so a
second panel is additive rather than a rewrite.

---

## 7 · Decisions needed

1. **A4: one artifact or two?** §6. Decide before building the screen.
2. **Does `/free-check` gain a "who do you compete with?" field?** One input,
   owner-sourced, higher quality than anything scraped. It also lengthens the form,
   which costs leads.
3. **Cap: 3 or 5?** Judge cost scales with it on every answer of every run.
4. **Does an unreviewed set ever run?** The conservative answer, matching Tier 1's
   narrow authority in the fact-sheet plan, is that it may aim a teaser's low/med
   path and may never appear in a signed deliverable.

---

## 8 · Build sequence

`C*`, beside the `F*` items.

| # | Item | Depends on | Acceptance |
|---|---|---|---|
| **C0** | The `CompetitorCandidate` / `CompetitorSet` types + the evidence gate | — | A candidate whose evidence is not a literal substring of its source is dropped, with the drop logged. Reuses the fact sheet's gate, not a second copy. |
| **C1** | `local_pack` → candidates, for local | C0 | On a real Berkeley trade query, produces 3–5 quoted candidates, no aggregators, client excluded by alias. |
| **C2** | `site_comparison` → candidates, for product | C0 | A `/alternatives` page yields the brands it names and nothing it merely mentions in prose. |
| **C3** | Storage + the queue panel | C0, A4 | Approve moves `draft` → `active`; each candidate shows its source link and quote; exclusions are visible with reasons. |
| **C4** | `competitor_set_id` on a run, mirroring `fact_sheet_id` | C3 | `POST /audits` accepts it; refuses a non-active set and refuses a set alongside CSV `config,competitors` — two sources for one run, same rule as the sheet. |
| **C5** | The one-way valve, asserted | C4 | A test proves `discover_competitors` output can never enter a set that has not passed a human gate. **Never weaken this test.** |

**C1 alone is worth shipping**: it turns a local lead into a runnable audit
without a human typing a competitor list, which is the whole point.

---

## 9 · What this does NOT solve

A competitor set makes a lead *runnable*. It does not make the run *good*. The
judge still needs a fact sheet with enough contradictable lines (see the local
gold set's flag-density problem), the engines still cost money per competitor,
and a set that is merely plausible produces a report that is merely plausible.

The measured set is a floor, not a substitute for Josh knowing the market.
