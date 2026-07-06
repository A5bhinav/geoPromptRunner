# Plan — Port the Teaser's Guards into the Audit Deliverable (+ regen aliases)

> **Status:** not started. Follow-up to `docs/teaser-quality-audit.md` after the teaser
> fixes (commit `bb1a7d8`) were verified. **The teaser is clean;** every remaining issue is
> in the **paid audit deliverable** (`teaser/src/select/buildAudit.ts` + `render/audit/*`)
> or the **regenerate/stored path**, plus one new correctness bug.
> **Audience:** a Claude Code session. **Guiding principle:** *reuse* the teaser's
> already-correct helpers (`isUnwinnableQuery`, the honest-hero logic, the reproduction-
> preferring `findAnswer`) — don't reimplement. Every task ends green: `npm test` (112+
> passing) and `npm run typecheck` clean, with a regression test added.

---

## ✅ DONE + verified (commit `d24cb38`, 2026-07-05)

Implemented and verified by a 3-agent pass. **T1–T7 all RESOLVED and correct**; 118 tests
pass (incl. the new multi-competitor fixture + T1/T2/T3/T4/T5/T7 regressions), `tsc` clean,
**no regressions** — the shared-helper refactor (`computeHeadline`→`analyzeQueries`, exported
`findAnswer`) did not change the teaser path. Highlights confirmed: evidence cards now drop
brand + A-vs-B and apply the honest-hero filter; verdict %s share the winnable-count basis
(the multi-competitor case that hid T2 is now tested); aliases round-trip through the stored
draft's jsonb; the category validator is recall-safe.

**Two minor, non-blocking cosmetic follow-ups** (neither affects a number or re-opens a bug):
- **[LOW]** `render/audit/template.ts:51-52` — `clientAppearanceLine`/`selectWhyGaps` still build
  name-only matchers (no aliases), though the draft now carries them. Counts stay correct
  (they come from the alias-aware headline); only the "the one place AI named you" sentence
  degrades to a generic line when the client appears *alias-only*. Thread `t.clientAliases`.
- **[LOW]** `web/lib/api.ts:247-256` — the web-side `TeaserDraft` type doesn't declare the new
  `clientAliases`/`competitorAliases` fields. Works today (whole draft is JSON-serialized), but
  the type is out of sync; add the fields so a future stricter serializer can't drop them.
- **[LOW, no fix needed]** T5's token match can drop a valid query phrased with a pure category
  *synonym* — bounded by the recall-safe fallback; the audit called it not worth fixing.

---

## T1 — [MED-HIGH] Gate the audit's evidence cards (un-winnable + brand + honest-hero)
**Bug:** `computeHeadline` already excludes brand/A-vs-B rows (`buildAudit.ts:117-120,156`),
but `buildEvidence` (`buildAudit.ts:204-238`) iterates `EVIDENCE_BUCKET_ORDER` — which
includes `"brand"` (`:71-76`) — and never calls `isUnwinnableQuery`. So the paid §3 evidence
can still render a "Whoop vs Fitbit, client nowhere" A-vs-B card or a brand-query card — the
exact S1/S3 embarrassment, in the thing you charge for.
**Change:** compute the `excluded` set once (extract the brand+`isUnwinnableQuery` logic from
`computeHeadline:117-120` into a shared helper) and pass it into `buildEvidence`; skip any row
whose `query_id ∈ excluded`. Drop `"brand"` from `EVIDENCE_BUCKET_ORDER` (or filter brand rows).
Also apply the honest-hero check the teaser uses (only keep a row where its competitor
out-appears the client) for parity with `selectFindings`' `heroPool`.
**Test:** an audit fixture with (a) an A-vs-B `comparison` row naming two rivals and (b) a
`brand` row → neither appears in `evidence`; a legit category loss still does.

## T2 — [MED, NEW BUG] Fix the verdict brand/% mismatch
**Bug:** `verdictLine` (`buildAudit.ts:293-303`) prints `${h.competitorName} in ${compPct}%`,
but `compPct` comes from `report.scorecard.mention_rate_top_competitor` (the **share-based**
top brand) while `h.competitorName` is the **count-based honest-hero pick**
(`:147-159`). In a multi-competitor report these are different brands → the verdict attributes
the top brand's % to a *different* named competitor. Hidden by the single-competitor test
fixture.
**Change:** derive the percentage from the **same basis** as the named brand —
`pctOf(h.competitorAppears / h.n)` — so the number always matches `h.competitorName`. (Or, if
you keep `mention_rate_top_competitor`, only print the competitor clause when
`h.competitorName === report.scorecard.top_competitor`, else fall back to the client-only
verdict at `:431`.)
**Test:** a **multi-competitor** fixture where the honest-hero pick ≠ `top_competitor` →
the verdict's brand and its % are consistent.

## T3 — [MED] Persist + rehydrate aliases so regeneration isn't alias-blind
**Bug:** `profileFromStored` (`buildAudit`/`pipeline.ts:229-237`) sets competitor
`aliases: []` and no client aliases (comment at `pipeline.ts:225` concedes this), because the
stored `ReportPayload`/`TeaserDraft` carry only names (`types/platform.ts:147,152`). So a
teaser **regenerated from storage** runs alias-blind and re-opens S4 (an alias-only client
mention is re-counted as a loss → wrong headline/hero).
**Change:** persist aliases at save time — add an `aliases` field to the saved `TeaserDraft`
(store `profile.aliases` + each competitor's `aliases` when `saveTeaser` runs, `cli.ts:190`),
and have `profileFromStored` read them from the draft instead of defaulting to `[]`. This also
**unblocks T7** (audit competitor aliases).
**Test:** regenerate a draft whose stored profile had a client alias that appears (alias-only)
in a stored answer → that query is counted as a client *presence*, not a loss.

## T4 — [MED] Port the reproduction-preferring `findAnswer` to the audit
**Bug:** `buildAudit.findAnswer` (`:166-172`) quotes `run_index === 0` blindly, so an audit
proof card can quote a run where the loss did **not** reproduce. The teaser already fixed this
(`selectFindings.ts` `findAnswer` takes a `prefer` predicate and picks the lowest-index
*reproducing* run).
**Change:** reuse/share the teaser's `prefer`-aware `findAnswer`; pass a "loss reproduces"
predicate so the audit quotes a run that actually backs the claim.
**Test:** fixture where run 0 doesn't reproduce the loss but run 1 does → audit quotes run 1.

## T5 — [LOW-MED] Add the missing C4 category-token validator
**Bug:** the query-gen prompt was tightened (`ClaudeQuerySetGenerator.ts:81`) but
`validateAndRepair` (`:139-187`) still has no deterministic check that `category`/
`adjacent_authority` queries actually contain the client's specific category token, and the
permissive "may carry a real qualifier" clause remains (`:81`).
**Change:** in `validateAndRepair`, for category/adjacent-intent queries, require the client's
category token (case-insensitive, whitespace-tolerant); drop/repair those that broaden to a
generic parent. Optionally delete the residual "may carry a real qualifier" clause.
**Test:** a generated category query lacking the category token is dropped or repaired.

## T6 — [LOW] Reconcile the mixed denominators in audit §1
**Bug:** §1 headline says "X of N" on the **winnable-only** denominator (`:428`) while the
adjacent verdict says "named in Y%" on the **all-query** `mention_rate` — both honest, but
side-by-side they can read inconsistently.
**Change:** base both on the same set (preferred), or add a one-line clarifier. Cosmetic; do
last.

## T7 — [LOW] Thread competitor aliases through the audit matchers
Once T3 lands (stored aliases available), pass competitor aliases into the audit's
`computeHeadline`/`toFinding` `buildMatcher` calls (`buildAudit.ts:111-112,180-185`) — parity
with the teaser (fixes R4, currently "data-blocked").

---

## Order & global acceptance
**Order:** T1 → T2 → T3 → T4 → T5 → (T6, T7). T1/T2 are the client-facing correctness wins;
T3 unblocks T7.
**Global:**
- Reuse teaser helpers (extract shared functions rather than duplicate); the theme is
  *"the audit deliverable didn't inherit the teaser's guards — give it the same ones."*
- **Add a multi-competitor audit test fixture** — the single-competitor fixture is exactly
  what hid T2; several of these bugs only surface with ≥2 competitors.
- Keep all existing tests green + `tsc --noEmit` clean; add one regression test per task.
- Out of scope (teaser already correct, verified): D1–D5, S1–S8, C1/C2/C3/C5/C6,
  R1/R2/R3/R5/R6/R7/R8. Don't touch those paths.
