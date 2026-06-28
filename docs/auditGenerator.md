# AI Visibility Audit Generator — Design & Build Plan

> Status: **BUILT (Phases 0–3)** — 2026-06-25. Authored 2026-06-24; §15 decisions
> resolved 2026-06-24. Generator lives in `teaser/` (`npm run audit -- <run_id>`):
> `select/buildAudit.ts` (synthesis, unit-tested) → `render/audit/template.ts`
> (8-section Ledger render) → `render/audit/pdf.ts` (PDF). Persistence:
> `data/schema_audits.sql` + `db.save/get/list/update_audit_*` + `/audit-deliverables`
> API. UI: `web/app/audit/page.tsx` + `/api/audit` + `/api/audit/render`. Schema
> applied to Supabase 2026-06-25 (`audit_deliverables`; db round-trip verified).
> **Outstanding:** Phase 4 polish (§8 narrative tuning, trend/re-audit section).
> Companion to `teaser/BUILD_PLAN.md`. The teaser is the free hook; the **audit
> is the paid deliverable** it converts into. This doc specifies the generator
> that turns a completed audit run into a polished, client-ready
> **AI Visibility Audit**.

---

## 0. What this is

The **Audit Generator** assembles a completed GEO audit run (engine answers +
judge verdicts + site-audit scrape) into a polished, founder-readable
**AI Visibility Audit** — delivered as an interactive web report and an
auto-generated PDF leave-behind, with a human review/approve gate, persisted to
Supabase.

It is an **assembly + render layer**, not a measurement layer. Every input it
needs is already produced by the platform and exposed on `ReportPayload`
(`src/api/reports.py`). Like the teaser, the hard measurement work is done; this
turns the data into the deliverable.

**One-line job:** `run_id → AI Visibility Audit (web + PDF) → review → Supabase`.

---

## 1. Relationship to the teaser

| | Teaser | Audit |
|---|---|---|
| Role | Free **hook** (outbound / demo opener) | Paid **deliverable** (the engagement) |
| Length | 1 page | Multi-page (≈4–8) |
| Content | 1 lead loss + "why" + CTA | Full grade, all evidence, full diagnosis, full roadmap |
| Audit run | Lean (small query set, fast) | **Full** (broad query set + fact sheet for accuracy flags) |
| Input | A prospect URL (runs its own lean audit) | A **completed full audit `run_id`** |
| Render | `teaser/src/render/template.ts` (Ledger design) | **Reuses the same design system**, multi-section |
| Persistence | `teasers` table | new `audit_deliverables` table (mirror) |
| Review | approve / edit / reject (web) | same lifecycle, deeper edit surface |

The teaser is, structurally, **§1 (Verdict) + a slice of §3 (See it yourself) +
a slice of §7 (Roadmap)** of the audit. Reuse aggressively (§13).

---

## 2. Architecture

```
                          ┌──────────────────────────────────────────────┐
 completed audit run  ──▶ │  Audit Generator (TS, lives in audit-gen/ or  │
 (audit_runs + report)    │  alongside teaser/)                           │
                          │                                              │
                          │  1. fetch report + answers (+ fact sheet)    │
                          │  2. synthesize → AuditDraft                  │
                          │  3. render → HTML (+ PDF via Playwright)     │
                          │  4. persist draft+html → audit_deliverables  │
                          └───────────────┬──────────────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                                ▼
        Web review UI (Next.js)                          PDF leave-behind
        (approve / edit / reject;                        (Ledger design,
         interactive exploration)                         print-ready)
```

**Where it lives.** Mirror the teaser's decoupling: a self-contained TS package
(`audit-gen/` or a sibling of `teaser/`) that talks to the platform only through
the existing HTTP surface (`GET /audits/{id}/report`, `/answers`) and a new
`POST /audit-deliverables` persistence endpoint. Reuse the teaser's render
modules directly (import or copy `render/template.ts`, `render/proofCard.ts`,
`render/pdf.ts`, `render/copy.ts`, `select/selectFindings.ts`,
`select/entity.ts`).

> **Decision (open, §15):** ship the generator as a new package, or extend
> `teaser/` with an `audit` mode. Recommendation: **extend `teaser/`** — it
> already has the render pipeline, `PlatformClient`, env loading, PDF, and the
> Supabase persistence seam. Add `src/audit/` (assembly) + `src/render/audit/`
> (template) and an `audit` CLI subcommand. Avoids duplicating the design system.

---

## 3. Input — a completed audit run

The generator operates on a **completed full audit `run_id`** (state `done`).
The full audit differs from the teaser's lean run:

- **Broad query set** — the full methodology query set (problem-aware → category
  → comparison → brand → adjacent-authority), not the teaser's leanest-N cut.
- **Fact sheet attached** — so the judge can emit `accuracy_flags` (the "AI says
  wrong things about you" section, §4). The teaser usually skips this.
- **All engines** + `detection: "judge"`.
- **Site audit ran** — `site_audit` populated (technical + content + schema +
  off-site checks and the synthesized roadmap).

The run is produced by the normal platform path (CSV upload via the UI, or the
teaser's `submitAudit`). The generator does **not** run its own audit; it
consumes a finished one by id. (A thin "run + generate" wrapper can chain them.)

**Fetched via the existing `PlatformClient`:**
- `getReport(runId)` → `ReportPayload` (`src/api/reports.py`)
- `getAnswers(runId)` → `AnswerRecord[]` (verbatim answers for proof cards)

---

## 4. The deliverable structure

Mirrors the 7-step methodology in `docs/CLAUDE.md` (ending on *deliver &
convert*). Each section binds to data that **already exists** on `ReportPayload`.

### §1 — Verdict (cover)
- **Leads with the share-of-voice gap** (the hero, un-arguable, continuous with
  the teaser): *"When buyers ask AI for the best [category], [client] shows up in
  X of N answers; [top competitor] shows up in Y."*
- **Grade as a trajectory scorecard** beneath the hero, not a naked verdict:
  `current letter → achievable letter (90d)` — severity reframed as headroom,
  paired with the §7 roadmap (the path out). Then a one-line **"what's inside"**
  depth promise (why · evidence · competitive gap · roadmap).
- Data: `scorecard.mention_rate_client`, `scorecard.share_of_model_client`,
  `top_competitor`, `top_competitor_share`, `scorecard.visibility_grade`
  (`{letter, score, raw_score, accuracy_penalty, n_flags, rationale}`), `engines`,
  `run_date`. (The "achievable" grade is analyst-set narrative, not a measured
  field — phrase as a target, never fabricate a score.)
- This page **is the teaser's hero**, expanded. Reuse the Ledger hero + big-stat.
  Decision detail: §15.7.

### §2 — Where you stand (baseline)
- Mention rate + **share-of-voice** across all engines, client vs top
  competitors; the leaderboard; performance **by buyer-journey stage**.
- Data: `leaderboard` (`LeaderRow[]`: `brand, is_client, visibility,
  mention_rate, share_of_model`), `by_bucket` (`BucketRow[]`: `bucket,
  mention_rate, citation_rate`), `scorecard.share_of_model_client`,
  `top_competitor`, `top_competitor_share`.
- Render: the teaser's `visibilityChart` (full leaderboard) + a per-bucket
  table (problem-aware / category / comparison / brand / adjacent).

### §3 — See it yourself (evidence)
- **Verbatim losing answers** rendered as proof cards, **grouped by journey
  stage** (problem-aware → category → comparison) so it reads as a pattern, not
  cherry-picking.
- Data: `losing_queries` (`LosingRow[]`) joined to `AnswerRecord[]` (verbatim).
- Render: reuse `renderProofCard` + `cleanAnswerText` (strips Markdown). Show
  the top **K per bucket** (K configurable; §15 depth decision).

### §4 — What AI gets *wrong* about you (accuracy)
- Factual errors the engines state about the client ("costs $X" / "lacks feature
  Y" — both false), each with the **claim vs reality**.
- Data: `accuracy_flags` (`FlagRow[]`: `type, severity, claim, reality`),
  `scorecard.accuracy_assessed`, `accuracy_flag_count`,
  `scorecard.accuracy_penalty` (how much it dragged the grade).
- **Currently underused and very persuasive.** Requires the fact sheet on the
  run. Omit the section cleanly when `accuracy_assessed` is false.

### §5 — Who's winning & why (competitive gap)
- Competitors' **off-site authority** mapped against the client's: Wikidata
  entity, app-store / review-platform presence, Reddit/community, listicles,
  press.
- Data: `site_audit.offsite` (`SiteFindingRow[]`: `finding_type, title, url,
  confidence`), `sources` (`SourceRow[]`: `domain, count` — which domains AI
  cites), `leaderboard`.
- Render: a gap map (client column vs top-competitor column) + the cited-source
  domains (where AI is getting its answers).

### §6 — Why AI skips you (diagnosis)
- The **full technique checklist**: technical accessibility (robots/WAF/llms.txt/
  sitemap/gated/SSR), content structure & substance, schema, off-site — per the
  7-category rubric.
- Data: `site_audit.checks` (`SiteCheckRow[]`: `check_key, category, page_url,
  status, detail`), `site_audit.pages_crawled`, `errors`.
- Render: grouped by the 7 categories, each check pass/partial/fail with the
  `detail`. The teaser's "Why" block (`selectWhyGaps`) is the **top-3 slice** of
  this — here it's the full table.

### §7 — The roadmap (what to do)
- The **prioritized roadmap**: phase 1→4, impact × effort, each gap → an action.
- Data: `site_audit.roadmap` (`RoadmapRow[]`: `category, check_name, status,
  impact_label, effort, phase`).
- Render: grouped by phase (1 Accessibility → 2 Content → 3 Structured data → 4
  Off-site), each row with impact/effort badges. This is the literal
  *"here's what we'd do for you"* pitch.

### §8 — Projected impact + engagement
- What fixing phases 1–2 could move (visibility lift narrative); the retainer
  ask; a 90-day re-audit promise (the trend feature already exists — `report
  --previous <run_id>`).
- Mostly **analyst-authored narrative** (see review flow, §10).

---

## 5. Data model — section → fields

Single source of truth: `ReportPayload` (`src/api/reports.py`, mirrored in
`teaser/src/types/platform.ts`). Full map for the generator:

| Section | Reads |
|---|---|
| §1 Verdict | `scorecard.visibility_grade.{letter,score,rationale,accuracy_penalty,n_flags}`, `scorecard.mention_rate_client`, `engines`, `run_date`, `client_name` |
| §2 Baseline | `leaderboard[]`, `by_bucket[]`, `scorecard.{share_of_model_client,top_competitor,top_competitor_share,mention_rate_top_competitor,citation_rate_client}` |
| §3 Evidence | `losing_queries[]` ⨝ `AnswerRecord[]` (by `query_id`+`engine_name`) |
| §4 Accuracy | `accuracy_flags[]`, `scorecard.{accuracy_assessed,accuracy_flag_count,accuracy_penalty}` |
| §5 Competitive | `site_audit.offsite[]`, `sources[]`, `leaderboard[]` |
| §6 Diagnosis | `site_audit.checks[]`, `site_audit.{pages_crawled,errors,summary}` |
| §7 Roadmap | `site_audit.roadmap[]` |
| §8 Engagement | analyst narrative + `query_set_version`, `competitors`, `client_domains` |

> **Nothing new needs to be measured.** The only platform additions are (a)
> ensuring the full audit attaches the fact sheet for §4, and (b) the
> persistence endpoint/table (§11).

---

## 6. Domain types (`AuditDraft`)

The assembled, reviewable object (analogue of `TeaserDraft`). Sketch:

```ts
interface AuditDraft {
  runId: string;
  clientName: string;
  clientDomains: string[];
  category: string;
  runDate: string;
  engines: string[];

  // §1
  grade: { letter: string; score: number; rationale: string };
  headline: string;            // analyst-editable
  verdictSentence: string;     // analyst-editable

  // §2
  leaderboard: LeaderRow[];
  byBucket: BucketRow[];
  shareOfVoiceClient: number;

  // §3 — evidence grouped by journey stage
  evidence: { bucket: IntentBucket; findings: Finding[] }[];

  // §4
  accuracy: { assessed: boolean; flags: FlagRow[]; penalty: number };

  // §5
  competitiveGap: { offsite: SiteFindingRow[]; citedSources: SourceRow[] };

  // §6
  diagnosis: { categories: { category: number; checks: SiteCheckRow[] }[] };

  // §7
  roadmap: RoadmapRow[];       // grouped by phase at render

  // §8 — analyst-authored
  engagement: { projectedImpact: string; nextSteps: string };

  // review lifecycle
  status: "draft" | "approved" | "rejected" | "exported";
  editedFields: AuditEditedFields;   // analyst overrides (headline, verdict, narrative…)

  // reproducibility
  report: ReportPayload;             // cached, like TeaserDraft.report
  answers: AnswerRecord[];
}
```

`Finding`, `IntentBucket`, `LeaderRow`, `BucketRow`, `FlagRow`, `SiteCheckRow`,
`SiteFindingRow`, `RoadmapRow`, `SourceRow`, `ReportPayload`, `AnswerRecord` are
all already defined in `teaser/src/types/platform.ts` / `types/domain.ts`.

---

## 7. Generation pipeline

Pure orchestration (like `teaser/src/pipeline.ts`), all I/O injected:

```
1. fetch        getReport(runId), getAnswers(runId)          [PlatformClient]
2. guard        require detection === "judge" and a usable report;
                degrade per-section (omit §4 if !accuracy_assessed,
                omit §5/§6/§7 if !site_audit?.present)
3. synthesize   report + answers → AuditDraft (§8 synthesis below)
4. render       AuditDraft → HTML (render/audit/template.ts)
5. pdf          HTML → PDF (Playwright, reuse render/pdf.ts)
6. persist      POST /audit-deliverables { draft, html } → audit_deliverables row
7. emit         { ok, draft, html, deliverableId }  (or files in CLI mode)
```

**CLI:** `npm run audit -- <run_id> [--require-real] [--out dir] [--json]`
— mirrors the teaser CLI (env auto-load, `--require-real` guard, auto-persist).

---

## 8. Synthesis & selection logic

Deterministic, pure, **testable** (like `selectFindings`). New module
`select/buildAudit.ts`:

- **Grade (§1):** straight from `scorecard.visibility_grade`. Verdict sentence
  templated from grade + mention rate + top competitor; analyst-editable.
- **Evidence grouping (§3):** bucket `losing_queries` by `intent`; within each
  bucket rank by the existing `scoreRow` (engine credibility × intent) and take
  top **K** (default 2–3/bucket). Join to `AnswerRecord` via
  `(query_id, engine_name)`; clean Markdown with `cleanAnswerText`. Reuse the
  teaser's lead-selection insight: lead each section with the cleanest,
  highest-intent finding.
- **Accuracy (§4):** sort `accuracy_flags` by `severity` (high→low); each row is
  `{claim, reality, type}`. Skip the whole section if `!accuracy_assessed`.
- **Competitive gap (§5):** map `offsite` findings by `finding_type`
  (wikidata/reviews/community/listicle/press) into present/absent per brand;
  `sources` → the top cited domains (the off-site real estate AI pulls from).
- **Diagnosis (§6):** group `checks` by `category` (the 7 rubric categories);
  roll per-page checks up to a category verdict (fail > partial > pass) for the
  header, list the failing/partial pages underneath.
- **Roadmap (§7):** group `roadmap` by `phase`; within phase order by
  fail-before-partial then impact (same ordering as `selectWhyGaps`).
- **Engagement (§8):** templated projected-impact + next-steps scaffolding the
  analyst edits (no fabricated numbers — phrase as ranges / "typically").

> **Honesty rule (carried from the teaser):** every claim traces to data. No
> invented metrics. Accuracy claims must cite the verbatim engine span +
> fact-sheet reality. Off-site "absent" must come from a real `offsite` finding,
> not an assumption.

---

## 9. Rendering

- **Reuse the Ledger design system** (`teaser/src/render/template.ts` STYLE +
  `copy.ts` + `proofCard.ts`). The audit is the same visual language, multi-page.
- New `render/audit/template.ts` composes the 8 sections; each section is a small
  pure function (`renderVerdict`, `renderBaseline`, `renderEvidence`, …) — keep
  them independently testable like the teaser sub-renderers.
- **PDF:** reuse `render/pdf.ts` (`renderPdf` via Playwright). Add CSS
  `@media print` page breaks between sections (`break-before: page`) so each §
  starts on a clean page.
- **Proof cards** reuse `renderProofCard` + `cleanAnswerText` verbatim.
- **Reviewer edits** flow through the same overlay mechanism the teaser uses
  (`TeaserEdits` → `AuditEdits`): headline, verdict, per-section narrative, and
  the §8 engagement copy are override-able and re-rendered (`renderCli` analogue
  + `/api/audit/render` route).

---

## 10. Review lifecycle & human-in-the-loop

Same gate as teasers (`status`: draft → approved/rejected/exported), but the
audit has a richer **analyst narrative** surface, because the deliverable sells
the engagement:

- **Auto-generated:** §1–§7 (data-driven) + scaffolded §8.
- **Analyst edits (stored in `edited_fields`):** the headline, verdict sentence,
  per-section framing, §5 competitive narrative, §8 projected impact + next
  steps. The original auto-draft stays in `draft` (auditable) — edits are an
  overlay, exactly like the teaser's `edited_fields`.
- **Approve → export** the PDF as the client leave-behind.

Recommendation: **human-in-the-loop**, not fully automated. The data assembles
itself; the strategic narrative and the ask are human. (Matches the teaser's
"LLM proposes, human confirms" stance.)

---

## 11. Persistence (Supabase)

New table, mirroring `data/schema_teasers.sql` (RLS enabled, service-role only),
in a new `data/schema_audits.sql`:

```sql
create table if not exists public.audit_deliverables (
    id uuid primary key default gen_random_uuid(),
    run_id uuid,                         -- FK-ish to audit_runs.id (the source run)
    client_name text,
    client_domains jsonb not null default '[]'::jsonb,
    category text,
    run_date text,
    grade_letter text,                   -- denormalized for the list view
    grade_score numeric,
    headline jsonb not null default '{}'::jsonb,
    scorecard jsonb not null default '{}'::jsonb,
    draft jsonb not null default '{}'::jsonb,   -- the full AuditDraft
    html text,
    status text not null default 'draft'
        check (status in ('draft','approved','rejected','exported')),
    edited_fields jsonb not null default '{}'::jsonb,
    reject_reason text,
    reviewed_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_audit_deliverables_run on public.audit_deliverables (run_id);
create index if not exists idx_audit_deliverables_status on public.audit_deliverables (status);
create index if not exists idx_audit_deliverables_created on public.audit_deliverables (created_at desc);
alter table public.audit_deliverables enable row level security;
```

- `db.py` gains `save_audit_deliverable / get / list / update_audit_status`
  (copy the teaser functions). **Project only summary columns in `list`** (the
  `list_teasers` lesson — never `select('*')` the big `draft`/`html`).
- The **source run data stays in** `audit_runs` / `query_results` / `judgments`
  / `site_audit_*`; this table holds the rendered deliverable + review state +
  the cached `draft` for reproducibility.
- **Every generated audit is persisted** (the standing teaser rule applies here
  too — these are training data / a record of every deliverable).

---

## 12. API & Web surface

**API (`src/api/app.py`), mirroring `/teasers`:**
- `POST /audit-deliverables` `{ draft, html }` → `{ deliverable_id }`
- `GET /audit-deliverables` → summary list (projected columns)
- `GET /audit-deliverables/{id}` → full row
- `POST /audit-deliverables/{id}/approve|reject|edit` (edit takes
  `{ edited_fields, html }` — re-rendered html, like the teaser edit path)

**Web (`web/`):**
- An `/audit` page (mirror `/teaser`): pick a completed run → generate → review
  (approve / edit / reject) → download PDF.
- The **interactive report** (`web/components/report-view.tsx`) already renders
  most §2/§5/§6/§7 — reuse it for on-screen exploration; the PDF is the
  leave-behind.
- A `/api/audit/render` Next route (mirror `/api/teaser/render`) shells the audit
  render-only entrypoint so reviewer edits re-render server-side.

---

## 13. What to reuse from the teaser (don't rebuild)

| Reuse | From |
|---|---|
| Design system (Ledger CSS, fonts) | `teaser/src/render/template.ts` STYLE |
| Proof cards + Markdown cleaning | `render/proofCard.ts` (`renderProofCard`, `cleanAnswerText`) |
| PDF rendering (Playwright, lazy) | `render/pdf.ts` |
| Copy helpers | `render/copy.ts` (`engineLabel`, `engineColor`, …) |
| Entity matching (client/competitor) | `select/entity.ts` (`buildMatcher`) |
| Finding selection + `selectWhyGaps` | `select/selectFindings.ts` |
| Platform HTTP client | `platform/HttpPlatformClient.ts` (add `getReport`/`getAnswers` already there; add `saveAuditDeliverable`) |
| Env auto-load | `src/env.ts` |
| `--require-real` adapter guard | `config.ts` (`adapterModes`, `mockedAdapters`) |
| Review lifecycle + edits overlay | `web/app/teaser/page.tsx`, `/api/teaser/render`, `db.update_teaser_status` |
| Supabase schema + RLS pattern | `data/schema_teasers.sql` |

The audit is ≈70% existing render/select/persist plumbing + ≈30% new section
composition + the new table/endpoints.

---

## 14. Build phases

**Phase 0 — Plumbing & types.**
`AuditDraft` types; `data/schema_audits.sql` applied; `db.py` audit functions;
`POST/GET /audit-deliverables` endpoints; `saveAuditDeliverable` on the platform
client.

**Phase 1 — Synthesis.**
`select/buildAudit.ts` (pure): `report + answers → AuditDraft`. Unit-tested per
section (grade, evidence grouping, accuracy, competitive, diagnosis, roadmap).

**Phase 2 — Render (web-parity first).**
`render/audit/template.ts` composing §1–§8 in the Ledger design; reuse proof
cards. PDF with per-section page breaks. CLI `npm run audit -- <run_id>`.

**Phase 3 — Review + persist.**
Auto-persist on generate; `/audit` web page with approve/edit/reject; edit
re-render route. Exit gate: **one real audit run → reviewed → approved → PDF
downloaded ready to send.**

**Phase 4 — Polish.**
§8 narrative scaffolding tuning; 90-day re-audit/trend section (`report
--previous`); per-vertical copy tuning (B2C consumer).

---

## 15. Decisions (resolved 2026-06-24)

All seven open decisions are locked. Build to these.

1. **Package vs mode → extend `teaser/`** with an `audit` CLI subcommand. Reuses
   the Ledger design system, `PlatformClient`, env loading, PDF pipeline, and the
   Supabase persistence seam rather than duplicating them. (~70% existing plumbing.)
2. **Format → web report + PDF.** The interactive `report-view.tsx` already
   renders most of §2/§5/§6/§7 for on-screen exploration; the PDF is the
   leave-behind. Both come nearly for free.
3. **Automation → auto-skeleton + analyst narrative gate** (not fully automated).
   §1–§7 assemble from data; the strategic narrative and the §8 retainer ask are
   human. Matches the teaser's "LLM proposes, human confirms" stance.
4. **Evidence depth (§3) → top-K per bucket, K=2–3** (configurable). Grouping by
   journey stage reads as a pattern, not cherry-picking.
5. **§4 prominence → headline section, always on.** "What AI gets wrong about you"
   is a marquee section of every audit. **Implication:** every *full* audit run
   MUST attach a client fact sheet so the judge can emit `accuracy_flags` — see
   §3 (input) and §4 (deliverable). When `accuracy_assessed` is somehow false the
   section still degrades cleanly, but the standard path attaches the fact sheet.
6. **Run source → from an existing `run_id`** (rec), with a thin "run full audit +
   generate" one-shot wrapper added later. The generator stays a pure assembly
   layer; it never re-measures (Phase-1 non-goal).
7. **Grade exposure → gap-led cover; grade as a current→achievable trajectory.**
   The cover leads with the un-arguable **share-of-voice gap** ("Acme shows up in
   2 of 10 answers; Competitor X in 8") — continuous with the teaser hero and a
   fact about the client's own market, not a judgment. The A–F grade appears
   beneath it as a **trajectory scorecard** (`C → A- (90d)`), reframing severity
   as headroom — a credit-score, not a verdict. The grade is paired with the §7
   roadmap (the path out), which is why the audit — not the teaser — is where the
   grade belongs. Cover closes with a "what's inside" depth promise. See the §1
   spec below.

---

## 16. Non-goals (Phase 1)

- Re-measuring / re-running engines inside the generator (it consumes a finished
  run).
- A new design system (reuse Ledger).
- Auto-sending / outreach automation.
- Fully unattended generation without a human approve gate.
- Fix implementation (the audit recommends; it doesn't apply on-site changes).

---

## Appendix — data lineage cheat-sheet

```
client fact sheet ─┐
                   ├─▶ platform audit run ─▶ ReportPayload + AnswerRecord[]
query set ─────────┤        (engines + judge + site-audit crawl)
engines ───────────┘
                                   │
                                   ▼
                          Audit Generator
                          (buildAudit → AuditDraft → render → PDF)
                                   │
                 ┌─────────────────┼─────────────────┐
                 ▼                 ▼                 ▼
        web review UI      audit_deliverables    PDF leave-behind
        (approve/edit)        (Supabase)          (client)
```

`ReportPayload` fields → sections: see §5. Reuse map: see §13.
```
