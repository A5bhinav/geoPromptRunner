# Teaser Quality Audit — Root-Cause Findings (2026-07-05)

> Deep multi-agent audit of the teaser (and the paid audit deliverable) triggered by
> the symptoms Abhi described: "different every time," "headlined with Fort but the body
> talks about the wrong category," and "Whoop vs Fitbit, Fort nowhere — shown as a loss."
> Every item cites `file:line`. Scope: `teaser/src/**` + the platform contract it reads.

## The headline conclusion (answers the Opus question)

**Almost every real defect here is a CONFIG, LOGIC, or PROMPT bug — not a model-quality
problem. Switching Haiku→Opus would fix essentially none of them.** The two most visible
symptoms are a one-line temperature fix and a selection-logic fix; the category mismatch
is a resolver-prompt + missing-validation-gate issue that Opus reads the same way. Fix
these first; they're mostly free. Reserve a model bump (Sonnet, not Opus) for the small
residual that's genuinely model-sensitive.

**Tag key:** `[CONFIG]` one-line setting · `[LOGIC]` code/rule bug · `[PROMPT]` prompt
wording · `[MODEL]` a stronger model would materially help.

---

## ✅ Verification status (post-fix, commit `bb1a7d8`, 2026-07-05)

A second multi-agent pass verified the fixes. **The teaser itself is fully fixed** —
D1–D5, S1–S8, C1/C2/C3/C5/C6, R1/R2/R3/R5/R6/R7/R8 all **RESOLVED** and correct; 112
tests pass, `tsc` clean; no regressions in the teaser path. The remaining work is
concentrated in the **paid audit deliverable** (`buildAudit.ts` + `render/audit/*`),
which didn't fully inherit the teaser's guards, plus the **regenerate/stored path** — and
two genuinely NEW issues the fixes surfaced.

**Remaining changes (do these — the teaser is done, these are the audit + regen paths):**

1. **[MED-HIGH] Audit evidence cards bypass the un-winnable / brand / honest-hero gates.**
   `buildAudit.buildEvidence` imports `isUnwinnableQuery` but only uses it in
   `computeHeadline`, not in the evidence cards — so the paid audit §3 can still render a
   "Whoop vs Fitbit, client nowhere" A-vs-B card or a brand-query card (the exact S1/S3
   embarrassment, in the thing you charge for). Apply the same `excludedQueryIds` +
   honest-hero check in `buildEvidence`. (`buildAudit.ts:204-238`)
2. **[MED] NEW — audit verdict can pair the wrong brand with its %.** `verdictLine` prints
   `h.competitorName` (count-based honest-hero pick) with `mention_rate_top_competitor`
   (share-based top brand) — different brands in a multi-competitor report. Source the %
   from the same aggregation (`h.competitorAppears / h.n`) or fall back to client-only.
   Not caught by tests (single-competitor fixture). (`buildAudit.ts:298-305`)
3. **[MED] Client aliases dropped on regenerate.** `profileFromStored` sets no client
   aliases, so a regenerated teaser runs alias-blind and re-opens S4. Persist
   `profile.aliases` into the stored draft/report and rehydrate. (This is also why R4/audit
   aliases are "data-blocked" — the stored payload needs an alias field.)
   (`pipeline.ts:229-242`)
4. **[MED] D3 not ported to the audit.** `buildAudit.findAnswer` still quotes `run_index 0`;
   port the reproduction-preferring `findAnswer` so audit proof cards don't quote a
   non-reproducing run. (`buildAudit.ts:166-173`)
5. **[LOW-MED] C4 validator half missing.** The query-gen prompt was tightened, but
   `validateAndRepair` still has no deterministic check that category-intent queries contain
   the client's category token (defense-in-depth). Add it; optionally drop the residual
   "may carry a real qualifier" clause. (`ClaudeQuerySetGenerator.ts:81,139-187`)
6. **[LOW] NEW — mixed denominators.** Audit §1 headline ("X of N", winnable-only) sits
   beside the verdict ("named in Y%", all-queries) — both honest but can read inconsistent.
   Reconcile the basis or add a note. (`buildAudit.ts:298-352`)
7. **[LOW] R4 audit competitor aliases** — data-blocked; unlocks with #3's schema change.
   Minor watch items: C1 could over-narrow a legitimately broad-category client; `pipeline.ts`
   query-cap sort lacks a tiebreaker (deterministic in practice).

**Theme:** the thing prospects see first (the teaser) is clean; the thing they *pay* for
(the audit deliverable) still carries 3–4 of the same-class issues plus one new brand/%
mismatch. That's where the next pass should go.

➡️ **These remaining items are scoped into a build-ready plan:
[`audit-deliverable-fix-plan.md`](./audit-deliverable-fix-plan.md)** (T1–T7, file/line +
change + regression test each).

---

## Fix in this order (highest leverage first)

- **P0 — `[CONFIG]` Pin `temperature: 0`** on both Claude calls (`llm/claude.ts:78`, `:195`).
  Single biggest cause of "different every time" — de-randomizes profile, query-gen, and
  the relationship check at once.
- **P0 — `[LOGIC]` Hard-exclude A-vs-B / un-winnable rows** from hero, table, AND the
  headline denominator (Selection S1+S2). Kills the "Whoop vs Fitbit, Fort nowhere" finding
  and the inflated "0 of N."
- **P1 — `[PROMPT]` Pin the specific category + same-category competitors** in the resolver
  prompt, and add a same-category gate (Coherence C1–C3). Fixes the "wrong category body."
- **P1 — `[LOGIC]` Client aliases + prominence default + reproduction floor** (Selection
  S4, S7, S6). Makes "0 of N" trustworthy and stops over-claiming "recommends."
- **P1 — `[LOGIC]` Port the teaser's guards into the paid audit deliverable** (Copy R1, R3,
  R6) — the audit reintroduces overclaims the teaser already fixed.
- **P2 — deterministic sort tiebreakers, engine-label fall-through, matcher collisions.**

---

## A. Determinism — why it's "different every time"

| ID | Sev | Tag | Issue | Location | Fix |
|---|---|---|---|---|---|
| D1 | HIGH | CONFIG | No `temperature` on either Claude call → runs at API default **1.0**. Nondeterminizes profile extraction, query generation, and the relationship check (structured output constrains shape, not content). | `llm/claude.ts:78`, `:195` | Add `temperature: 0` (plumb through Extract/ResearchOptions). |
| D2 | HIGH | LOGIC | "Store prompts / regeneration" only stabilizes **re-renders** of an already-made teaser; the **first** live run resamples profile+queries+relationship every time. Caching happens downstream of the dice roll. | `pipeline.ts:100`, `cli.ts:190` | Fix D1; optionally cache resolved profile + query set keyed by URL. |
| D3 | MED | LOGIC | Selection/headline ARE stabilized (majority across `runsPerQuery=3`), but the verbatim proof quote comes from `run_index 0`; engine text drifts run-to-run, so the printed quote changes even when the finding is stable. | `selectFindings.ts:155`, `buildAudit.ts:139` | Pick the modal/representative run, or accept (engines are inherently nondeterministic). |
| D4 | MED | LOGIC | Ranking sorts lack a deterministic final tiebreaker → equal-ranked findings swap based on incoming (LLM/platform) order; the hero/headline can flip. | `selectFindings.ts:316,339,418`; `buildAudit.ts:181,217,236,303,341` | Add `\|\| a.query_id.localeCompare(b.query_id) \|\| a.engine_name.localeCompare(...)`. |
| D5 | LOW | LOGIC | `researchJson` `pause_turn` resume loop has no progress guard; combined with temp 1.0 a paused relationship check resumes into different search results. Recall-safe on failure, so low impact. | `llm/claude.ts:194` | Bound + guard the loop; fixed largely by D1. |

_Clock usage (`new Date()`/`Date.now()`) was checked and is content-safe (only drives the stale banner + metadata) — no fix._

## B. Finding / lead selection — the embarrassing findings

| ID | Sev | Tag | Issue | Location | Fix |
|---|---|---|---|---|---|
| S1 | HIGH | LOGIC | **The "Whoop vs Fitbit" bug.** A-vs-B comparison queries (two named competitors, client structurally absent) become "losing rows." Selection only **down-weights** comparison (it doesn't exclude), and `firstBoost=100` lets a recommended-first A-vs-B row beat a category row — or it wins outright when category losses are sparse. | `selectFindings.ts:38-58,136-142`; query gen `ClaudeQuerySetGenerator.ts:203-233` | Tag "named-rivals / client-not-a-candidate" queries at generation; hard-exclude them from hero, table, and denominator. |
| S2 | HIGH | LOGIC | Headline denominator `n = byQuery.size` includes un-winnable queries (A-vs-B, adjacent-authority) → "appears in 0 of 8" and the stakes line overstate the gap. | `selectFindings.ts:197-217`; `buildAudit.ts:106-129` | Compute `n` over the **winnable** set only (same exclusion as S1). |
| S3 | MED-HIGH | LOGIC | Brand-intent drop is applied only at **submission** (`pipeline.ts`); `computeHeadline` re-derives presence from `answers` with **no intent filter**, and the paid audit **keeps** brand queries → brand rows can re-inflate the number. | `pipeline.ts:121-131` vs `selectFindings.ts:197`, `buildAudit.ts:114` | Move the intent exclusion **into** the selection/headline functions, not the submit step. |
| S4 | HIGH | LOGIC | **Client matched on NAME ONLY (no aliases).** Competitors get aliases; the client gets `aliases:[]`. An engine naming the client by a common variant → false "absent" → a real presence printed as a reproduced loss, and "0 of N" understated. Can contradict the judge. | `selectFindings.ts:189`; `pipeline.ts:237` | Thread client aliases into `CompanyProfile` + every client `buildMatcher`. |
| S5 | MED | LOGIC | Matcher `\b(name)\b` collides for common-word brands ("Notion/Monday/Whoop/Mint") → false present/absent. Regex-path competitor is a comma-joined string (`"Whoop, Fitbit"`) → matches never fire. | `entity.ts:14-22` | Per-brand strictness for ambiguous names; split the comma-joined competitor into alternatives. |
| S6 | MED | LOGIC | Reproduction is a **soft tiebreaker, not a gate**: when nothing reproduces (e.g. `runsPerQuery=1`, or `confirming<observed`), a single-run fluke can become the hero while the headline asserts it as fact. | `selectFindings.ts:110,316` | When `runs≥2`, require a reproduced row for the hero; else fall back and soften the verbs. |
| S7 | MED | LOGIC | `isRecommendedFirst` treats `null`/undefined prominence as **recommended_first** → present-only rows get `firstBoost` and the strongest verbs ("AI is sending your buyers to X"). | `selectFindings.ts:131-133` | Default unknown prominence to the **weaker** claim; only print "recommends" when explicitly `recommended_first`. |
| S8 | MED | LOGIC | Pattern table draws from `named` with only `scoreRow` — it does **not** pass the honest-hero / proof-foregrounding gates the hero does, so a table row can contradict the headline (name a rival the client beats, or not appear in its own snippet). | `selectFindings.ts:337-349` | Run the table through the same gates + the S1 exclusion. |

## C. Coherence / category — "headlined Fort but body is the wrong category"

Data flow (profile → CSV → queries → findings → copy) is threaded **consistently** — the
mismatch is manufactured **upstream** by prompt/logic, then faithfully rendered. Every item
below is `[PROMPT]`/`[LOGIC]` — **a stronger model reads the same instructions and drifts the
same way.**

| ID | Sev | Tag | Issue | Location | Fix |
|---|---|---|---|---|---|
| C1 | HIGH | PROMPT | Resolver prompt nudges category to a **generic parent**: broad exemplars ("smart ring") + "use consumer language, not internal jargon" pushes "strength-training wearable" → "fitness wearable"/"smartwatch." Everything downstream then interpolates the generic term. | `profileExtraction.ts:116` | Require the **most specific** distinguishing category + a negative exemplar ("return 'strength-training wearable', NOT 'fitness tracker'"). |
| C2 | HIGH | PROMPT | Competitors required to be real + operating but **not same-category** → off-category rivals (Fitbit/Apple Watch for Fort) seed comparison queries and become the hero. | `profileExtraction.ts:117` | Add: competitors MUST be same specific category (direct substitutes). |
| C3 | HIGH | LOGIC | Only gates are realness (`DEFUNCT_BRANDS`) and corporate entanglement (`relationshipGuard`, recall-safe) — **no same-category validation** anywhere. | `relationshipCheck.ts`, `profileExtraction.ts:139-159` | Add a same-category drop verdict (mirror `relationshipGuard`), recall-safe + logged. |
| C4 | MED-HIGH | PROMPT+MODEL | Query-gen category rule "**may** carry a real qualifier" is permissive; `validateAndRepair` never checks the client's category token, so off-category queries pass. | `ClaudeQuerySetGenerator.ts:80-82,139-187` | Require the category term in category/adjacent queries; add a validator check. (Mildly model-sensitive.) |
| C5 | MED | PROMPT | "(none provided — use real category leaders)" invites the model to invent the **biggest generic** brands under a drifted category. | `ClaudeQuerySetGenerator.ts:101` | Remove/constrain to same-specific-category; prefer emitting extra category/problem queries. |
| C6 | MED | LOGIC | Empty extraction degrades silently: `category \|\| "product"` → "best product for a growing startup"; query-gen swallows exceptions. Bland-but-wrong teaser can still send. | `profileExtraction.ts:177-178`; `ClaudeQuerySetGenerator.ts:259-276` | Treat empty/`"product"` category as a hard failure; log (don't swallow) query-gen errors. |

## D. Copy / render claim-fidelity — mostly the PAID AUDIT deliverable

The **teaser's** own prominence gating is airtight (verified). The bugs cluster in the
**audit deliverable** (`buildAudit.ts` + `render/audit/*`), which was built after the teaser
and didn't inherit its guards.

| ID | Sev | Tag | Issue | Location | Fix |
|---|---|---|---|---|---|
| R1 | HIGH | LOGIC | Audit §1 cover verdict prints "**recommended** in X%" but X% is `mention_rate` (named, not recommended). The single most prominent claim in the paid deliverable overclaims. | `buildAudit.ts:247-257`; `render/audit/template.ts:202` | Say "named/mentioned in X%" (or source an actual recommended-first rate). |
| R2 | MED | TEMPLATE | Teaser chart kicker "Who AI **recommends** in your category" sits over a `mention_rate` bar chart — contradicts its own legend one line above. | `render/template.ts:369` | "Who AI **names** in your category." |
| R3 | MED-HIGH | LOGIC | Audit headline has **no honest-hero gate** (the teaser added one): can frame the competitor as winning when the client actually out-appears it. | `buildAudit.ts:106-129` | Port the teaser's honest-hero selection, or pick the highest-`competitorAppears` rival + soften framing when `≤` client. |
| R4 | MED | LOGIC | Audit competitor matched **without aliases** → undercounts the rival (alias-only mentions missed). | `buildAudit.ts:111-112` | Thread competitor aliases (parity with teaser). |
| R5 | MED | LOGIC | Audit "the one place AI named you" uses a **different matcher** than the count → can confidently name the **wrong query**. | `render/template.ts:47-68` | Return the matching `query_id` from `computeHeadline`; use one matcher. |
| R6 | MED | LOGIC | Audit proof card has **no `shownInProof` gate** (teaser does): a 400-char snippet can end **before** the competitor is mentioned while the callout says "recommended instead." | `buildAudit.ts:184-191`; `proofCard.ts:129` | Apply the teaser's `competitorMatcher(answerSnippet(...))` filter in `buildEvidence`. |
| R7 | MED | LOGIC/CONFIG | Unknown engine id falls through to the **raw snake_case id** + default color (e.g. real "copilot"/"bing" → "bing_copilot" leaks into the deliverable). | `copy.ts:11-40` | Add copilot/bing (+ any platform engine) to both maps, or humanize unknown ids. |
| R8 | LOW | ROBUSTNESS | `HttpPlatformClient` casts platform JSON with no runtime validation — a renamed field silently yields `undefined`/blank cells. | `HttpPlatformClient.ts:73-104` | Light schema check that fails loud. |

## Verified correct (don't re-fix)

- Teaser prominence gating is airtight — every claim routes through `isRecommendedFirst`; the
  pattern-table header downgrades to "AI names" if any row isn't recommends.
- Teaser proof card is single-cell consistent (engine/competitor/excerpt all from one cell);
  the markdown-strip → highlight → bold ordering is correct.
- Teaser headline stakes line avoids the "every gap went to a competitor" overclaim.
- The honest-hero and proof-foregrounding gates (teaser) fail **closed** with an explicit
  reason — good defenses.

## Bottom line

Of ~20 findings, **all but a sliver are CONFIG/LOGIC/PROMPT.** The teaser doesn't "suck
because it's on Haiku" — it drifts because temperature is unpinned, surfaces bad findings
because the selection rules don't exclude un-winnable queries, and goes off-category because
the resolver prompt invites a generic category with no same-category gate. Do the P0/P1 fixes
(mostly free), then, if a residual remains, A/B **Sonnet** (not Opus) on the resolver +
query-gen. The paid **audit deliverable** deserves special attention: it re-opened several
overclaim/mismatch invariants the teaser already closed.
