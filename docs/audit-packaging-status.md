# Audit packaging — what's built, what's left

> **Live status.** Update it in the same commit as the work. The normative spec is
> `docs/audit-packaging-spec.md`; the standing rules are
> `.claude/skills/audit-packaging/SKILL.md`. This file is only the checklist.
>
> Last updated **2026-08-04**.

## State

| Phase | Status |
|---|---|
| **0 — Foundation** | ✅ complete |
| **1 — Restructure** | ✅ complete |
| **2 — Recurring** | ✅ complete |
| **3 — Delivery** | ✅ complete |
| **4 — Operations** | ✅ complete (code + persistence + generator); P4-T1 still needs a real gold SET |
| **5 — Commercialize** | ✅ complete (code) |
| **T — the Track report** | ✅ complete (TR-T0 … TR-T11) |

Plus one addition that is not in the spec: **correction runs**
(`src/pipeline/correction.py`), which re-measure a finished run's failed cells
instead of re-running the whole audit.

## Done

| Task | Where |
|---|---|
| P0-T1 finding identity | `src/pipeline/finding_id.py` |
| P0-T2 four-level severity | `src/pipeline/severity.py`, `models.JUDGE_SEVERITIES` |
| P0-T3 theme taxonomy | `src/pipeline/themes.py` |
| P0-T4 Sable tokens + fonts | `web/styles/sable.css`, `web/lib/brand.ts` |
| P1-T1 themed finding groups | `src/pipeline/findings.py` |
| P1-T2 severity bar, Med/Low collapsed | `web/components/badges.tsx`, `report-view.tsx` |
| P1-T3 verbatim queries | `reports.LosingRow.prompt` |
| P1-T4 priority + actions | `src/pipeline/priority.py` |
| P1-T5 exec summary | `reports._exec_summary` |
| P1-T6 grade removed, four tiles | `reports.ScorecardPayload` |
| P1-T7 print pipeline | `web/scripts/render-report-pdf.mjs` |
| P1-T8 render-mode fork | `web/lib/render-mode.tsx` |
| P2-T1 prior comparable run | `runner._prior_comparable_run` |
| P2-T2 lifecycle | `src/pipeline/lifecycle.py` |
| P2-T3 Wilson / DEFF / MDE | `src/pipeline/stats.py` |
| P2-T4 significance gating | `src/pipeline/movement.py` |
| P2-T5 what changed | `reports.WhatChangedPayload` |
| P2-T6 charts *(partial)* | `web/components/charts.tsx` |
| P2-T7 evidence bundle | `findings.Evidence` |
| P4-T1 agreement metrics + gate | `src/pipeline/agreement.py`, `calibration.severity_agreement` |
| P4-T1 sampler + override ledger | `src/pipeline/review.py` |
| P4-T2 QA sampling queue | `review.sample_for_review` |
| P4-T3 engine drift canaries | `src/pipeline/drift.py` |
| P4-T4 narrative verifier | `src/pipeline/narrative.py` |
| P4-T5 query-set versioning | `src/prompts/versioning.py` |
| P4-T6 per-client config | `versioning.ClientConfig` |
| P3-T1 answer drill-down | endpoint + `AnswerPanel` in `report-view.tsx` |
| P3-T2 engine + intent filters | `web/components/report-view.tsx` |
| P3-T3 weekly digest | `src/api/digest.py` |
| P3-T4 shareable links | `src/api/sharing.py` + `web/app/shared/[token]` |
| P3-T5 server-side PDF | `GET /audits/{id}/report.pdf` |
| P3-T6 fix-pack export | `src/pipeline/fixpack.py` |
| TR-T0 composite + grade removed | `judge_metrics`, `grade_calibration` (dev-only) |
| TR-T2 pp vs percent | `src/pipeline/fmt.py`, `web/lib/format.ts` |
| TR-T11 section registry | `web/lib/report-sections.tsx` |
| TR-T1/T3–T9 sections | `src/api/sections.py`, `web/components/report-contract.tsx` |
| TR-T10 back matter A1–A6 | `sections.build_back_matter` |
| Pareto sources *(P2-T6 remainder)* | `sections.CitationDomainRow.cumulative_share` |
| Oldest-still-open tile | `reports.ScorecardPayload.oldest_open` |
| P0-T1 `findings_registry` table | `data/schema_findings_registry.sql`, `db.SupabaseFindingRegistry` |
| P4 persistence (reviews/drift/config) | `data/schema_operations.sql`, `db.py` |
| P3-T4 durable share revocation | `db.revoke_share_token`, `app._revoked_share_ids` |
| P4-T2 review queue + submission API | `app.get_review_queue`, `app.submit_review` |
| P4-T4 grounded narrative generator | `src/pipeline/narrative_generator.py` |
| P4-T1 gold stratification script | `scripts/stratify_gold.py` |
| P5-T1 free scan | `src/pipeline/free_scan.py` |
| P5-T2 signed fact sheet | `src/audit/factsheet/signoff.py` |
| P5-T3 white-label second skin | `web/styles/neutral.css`, `brand.NEUTRAL` |
| P5-T4 reference panel | `src/pipeline/reference_panel.py` |
| P5-T5 tier enforcement | `src/pipeline/tiers.py` |

## Left to build

### The one thing code cannot finish

**The gold sets' flag-bearing half.** `data/fort_gold.json` and
`data/oura_gold.json` measure brand-level agreement well (Fort 94% present / 86%
prominence / 93% framing, n=240). What is thin is flags: Fort carries 3 gold
findings and Oura 18 against a 20-finding floor, so
`AgreementSummary.flags_are_quotable` is False for both and the methodology names
the gap instead of quoting a number. A perfect judge cannot pass
`gate_critical_high_recall` on either set — the gate correctly refusing to
certify recall from a sample that cannot support it.

`scripts/stratify_gold.py` now does the sampling half: point it at the Fort
`csv-2026-06-13` run (115 flags across 540 judged cells) and it writes ~60
stratified, deterministically-chosen candidates with the judge's verdicts
withheld. What remains is two people labelling them blind.

### Held back on purpose

**The narrative generator is not wired into the client-facing report.** P4-T4
requires human sign-off on Critical/High narrative sentences and no sign-off flow
exists. The guard (`narrative.verify`), the generator
(`narrative_generator.generate_narrative`) and the wooden fallback are all in
place behind `RUN_NARRATIVE=0`; switching it on before a sign-off UI would
violate the task that created it.

**The bump chart** (part of P2-T6). TR-T3 makes the reason explicit: the trend
section draws no connecting line under four comparable cycles, and a bump chart of
competitor rank over cycles is the same problem one dimension up. No client has
four comparable cycles yet.

### Migrations to apply

Three schema files are written and NOT applied. Each degrades cleanly — the
feature falls back rather than failing — so applying them is a decision, not an
emergency:

    python -m scripts.apply_schema data/schema_findings_registry.sql
    python -m scripts.apply_schema data/schema_operations.sql

### Not in the spec, but owed

- **Correction runs are CLI-only.** No API endpoint, no UI button. Runs start in
  the UI, so a broken run is noticed there and fixed at a terminal.
- **`GEO_API_KEY` is empty in `.env`**, so the API is unauthenticated (its own
  startup warning says so) and share links cannot be signed — `mint_share_token`
  refuses rather than signing with an empty key. Fine on localhost; set it before
  anything is exposed.

  Note the local consequence: with a key set, the web app 401s unless
  `NEXT_PUBLIC_GEO_API_KEY` in `web/.env.local` matches. Share minting needs a
  key; the dev UI currently needs none. Set both together or neither.

## Open decisions

**1. How long is a cycle?** `trend.py` says `DEFAULT_CADENCE_DAYS = 42`; the
packaging spec and skill say *weekly*. These are different products, and the
answer decides whether the Phase-3 digest makes sense.

It also has a live consequence today. `_prior_comparable_run` applies **no
minimum interval**, so Fort's three runs of 2026-06-13 — 22:28, 22:49, 23:01 —
are treated as three cycles. The report renders an accountability line across
them. The numbers are correct and the significance gating correctly calls every
surface "held steady"; they are still not three cycles.

The agreed shape (2026-08-02) is a **labelling** rule, not a blocking one: runs
inside the gap are re-runs of the *current* cycle rather than new cycles.
Unlimited runs stay allowed — a client must never be locked out of recovering
from a failure.

**2. Is the cadence limit ever customer-facing?** Spec P5-T5 says do NOT meter
cadence. Internal spend control for two founders is a different thing, but the
same mechanism becoming a tier limit walks straight into that ruling.

## Tunable constants, and where they live

Each is a named constant in one module, so tuning is a config change:

| Constant | Module | Note |
|---|---|---|
| `DUP_THRESHOLD = 88.0` | `finding_id` | measured P=0.800 / R=0.667 on 72 labeled pairs |
| `RESOLUTION_CONFIRMATION_RUNS = 2` | `lifecycle` | absences before a fix is confirmed |
| `MIN_COVERAGE_RATIO = 0.95` | `lifecycle` | below this a run is not evidence |
| `PRACTICAL_FLOOR_PP = 10.0` | `movement` | **most in need of a real cycle to calibrate** |
| `DEFAULT_ICC = 0.68` | `stats` | replace with a measured value via `icc_one_way` |
| `_MAX_EVIDENCE_PER_GROUP = 4` | `findings` | 94 observations on one card was 16 PDF pages |
| `_LIFECYCLE_LOOKBACK_CYCLES = 12` | `runner` | the report states how many it considered |
| `CRITICAL_HIGH_RECALL_FLOOR = 0.90` | `agreement` | the production gate; recall, not accuracy |

## The thing no amount of building fixes

Everything in Phase 2 is **fixture-correct and unvalidated against a real
cadence**. Only three stored runs ever had a fact sheet, and they sit on three
different query sets. The Fort `csv-2026-06-13` trio is the only multi-cycle
history with real findings, and its cycles are minutes apart.

The unblock is one re-run of Fort on `csv-2026-06-14` with the same fact sheet
(relaunchable from the stored run row: 45 queries and a 10,082-char sheet are
both on it). ~$10 of engine calls; judging is free if prejudged.
