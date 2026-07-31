# Fact-Sheet Autogeneration Plan

*Turning a `/free-check` lead (business name, website, service area) into a
runnable fact sheet, without inventing a single fact. Plan only — nothing here
ships before §11's decisions are made.*

**Authored 2026-07-31. Revised 2026-07-31 after a full verification pass against
both repos** — §13 lists what the pass changed and what it found blocking.
Companions: `docs/fact-sheet-template.md` (consumer),
`docs/fact-sheet-template-local.md` (local service),
`docs/smb-pivot-build-plan.md` (Phases 0–5 complete; this sits beside Phase 4),
`docs/query-generation-plan.md` §1a (which already asks for the artifact this
plan produces), `docs/audit-packaging-research.md` §9.4–§9.8 (a competing
proposal for the same artifact — **must be reconciled, see §11.5**),
`teaser/BUILD_PLAN.md` §4b.

---

## 0 · Scope

**In:** a repeatable path from `{business, website, area}` to (a) `fact` rows in
the teaser's audit CSV and (b) a markdown sheet for `geo audit --fact-sheet` /
the `fact_sheet` column on the run row. Site-first, cited, human-gated.

**Out:** anything that makes the judge less conservative, any auto-send of
flags, and any generation that runs inside the website or Supabase.

**Two invariants this plan bumps into, and must not quietly reinterpret:**

- `geoWebsite/CLAUDE.md` says *"No auto-triggering of the teaser pipeline, no
  client-side secrets."* Tier 1 auto-running on lead insert is arguably inside
  that prohibition. It needs an **explicit amendment to the invariant** in the
  same commit, not a silent reading that fact-sheet generation isn't "the
  teaser pipeline."
- The leads table is **no longer insert-only-with-no-trigger.** An
  `AFTER INSERT` trigger has been live since 2026-07-30 (`lead-email-alerts.sql`,
  `scaffold.md` §6b). That is the hook this plan extends, not a rule it breaks.

**The standing rule everything else is downstream of:** a fact sheet is the
*reference* the judge measures answers against. A wrong line in it does not
produce a missing finding, it produces a **false accusation in a document we
send a stranger.** `teaser/BUILD_PLAN.md` §4b says we don't auto-generate fact
sheets in the MVP; this plan is the argument for changing that, and it only
holds if the generator is extraction-only.

---

## 1 · What already exists (re-verified 2026-07-31 against the code)

| Piece | Where | State |
|---|---|---|
| Fact sheet as a judge input | `src/pipeline/judge.py` `_ACCURACY_BLOCK` (L88), threaded through `judge_answer` / `_judge_single` / `_judge_cascade` / `_verify_flags` | ✅ Done |
| Fact rows → sheet | `src/prompts/csv_loader.py` — `_BLOCKS` (L53), `_build_fact_sheet()` (L201-204) joins `"{key}: {value}"`, **or the bare value when `key` is empty** | ✅ Done |
| All nine flag types | `src/storage/models.py` `AccuracyFlagType` (L131-155) — five product + `wrong_hours` / `wrong_service_area` / `wrong_contact` / `licensing` | ✅ Done |
| A worked fact-row example | `csv_loader.build_template_csv()` (L495-515) emits three hand-written fact rows, byte-pinned by `tests/test_consumer_path_regression.py` | ✅ Free F0 fixture |
| CSV emitter (teaser) | `teaser/src/platform/csv.ts` `buildAuditCsv()` — emits config (7 keys + a conditional `location`) and query rows, **and never reads `profile.productClaims`** | 🟡 One function |
| Claim extraction from the site | `teaser/src/resolver/profileExtraction.ts:164` asks for "0-6 concrete, falsifiable claims … that could seed a fact sheet"; `buildProfile` (L454-467) **populates them on the live profile** | 🟡 Extracted and carried — **no consumer, no persistence** |
| A richer page corpus | `src/audit/crawl/` — `PageRecord` carries `raw_html`, `rendered_html`, `extracted_text` (trafilatura), `json_ld` (extruct), `content_sha256`; `PageCategory` includes `PRICING`, `SERVICE`, `SERVICE_AREA` | ✅ Done, unused for facts |
| Bounded tool-loop precedent | `src/audit/offsite/agent.py` — `MAX_STEPS=8`, `WALL_CLOCK_SECONDS=90`, `TOOL_QUOTAS`, result cache, terminal `submit_findings`, forced final submit | ✅ Shape reusable. **The "JSONL audit log" is a dataclass only — nothing serializes it** |
| Local review platforms | `offsite/tools.py` — `LOCAL_REVIEW_PLATFORMS` (L69-78), selected via `review_platforms_for(business_kind)` (L81-86). `REVIEW_PLATFORMS` is the **consumer** tuple | ✅ Done — call the selector, never import either constant |
| Human gate precedent | `teaser/src/confirmGate.ts` — pure core + readline wrapper. Gates **only the competitor list** | 🟠 Exists, but see §9.2 |
| Review-lifecycle API precedent | `src/api/app.py` — `/teasers` and `/audit-deliverables` are exact mirrors: POST, GET, GET `/{id}`, POST `/{id}/approve|edit|reject` | ✅ Copy this |
| Fact rows in the upload UI | `web/lib/api.ts` already types `FactItem`, `FileProvenance.n_fact`, `ResolvedConfig.fact_sheet_present`, `ParsePreview.facts` | ✅ A CSV sheet renders today |

**So the gap is:** a typed claim structure, an extraction pass that cites its
sources, a cross-source disagreement rule, a gate that is reachable on the live
path, and a consumer for the flags. Not a new pipeline.

---

## 2 · The contract — one structure, two renderers

```ts
type Verification = "public_source_only" | "cross_confirmed" | "client_confirmed";

interface FactClaim {
  claim_id: string;        // "FS-01" — stable across regenerations
  section: SheetSection;   // identity | contact | hours | service_area
                           // | licensing | services_pricing | presence
  key: string;             // the fact-row key: "hours_sunday". NEVER empty (§2.1)
  value: string;           // a complete assertion (§4.4)
  polarity: "positive" | "negative";
  verbatim_quote: string;  // the literal source line. NOT a paraphrase (§4.1)
  source_url: string;
  source_kind: "site_jsonld" | "site_text" | "gbp" | "directory"
             | "registry" | "lead_form" | "client";
  as_of: string;
  verification: Verification;
  confidence: "high" | "medium" | "low";
}

// Per-SHEET state, distinct from per-claim verification (§11.5).
// "Brand Fact Sheet v1.0" in docs/audit-packaging-research.md §9.4 is defined
// here as: the sheet snapshot at the moment sheet_status first reaches `signed`.
type SheetStatus = "draft" | "client_reviewed" | "signed";
```

**Renderer 1 — fact rows** (`block,key,value,intent,persona`). Flat by
construction: `_build_fact_sheet` produces `"{key}: {value}"` lines, so the
markdown template's sections do not survive. **The key carries the section**
(`hours_sunday`, `service_area_excluded`), because that is all the structure the
judge gets.

**2.1 — never emit a keyless row.** `_build_fact_sheet` (L204) falls back to the
bare value when `key` is empty. Since the key is the only section signal the
judge receives, a keyless row silently degrades the sheet. Assert non-empty in
F0.

**Renderer 2 — markdown**, for `--fact-sheet`, the paid audit, and human review.
Full template layout plus a provenance appendix (claim_id → quote → URL →
as_of).

**Only ever generate from renderer inputs.** One caveat on the "never hand-write
a fact row" rule: `build_template_csv()` already does, deliberately, for the
Oura starter template. That is a fixture, not a generator, and F0's round-trip
test should use it.

---

## 3 · The pipeline — and where each layer runs

Revised: **the LLM layers moved after the audit.** Running them speculatively
extracts thirty facts when the engines only make claims about five dimensions,
and you cannot know which five until the run happens. See §7.

**L0 · Lead form (free).** `business` → §A name and the client matcher.
`website` → §A url + `client_domains`. `area` → §D primary city, normalized to
`City,Region,United States` (`canonicalLocation`; SearchApi rejects the ISO
code). `description` → a hint that tells later layers what to look for, never a
fact on its own.

**L1 · Deterministic site extraction (no LLM). Runs automatically.**
`extruct` JSON-LD is already parsed into `PageRecord.json_ld`. `LocalBusiness`
yields name, `telephone`, `address`, `openingHoursSpecification`, `areaServed`,
`priceRange`, `sameAs`. Add `tel:`/`mailto:` hrefs and the footer NAP block.
**Platform-Python only** — the teaser resolver has no JSON-LD parser at all
(`FetchClaudeResolver` hands Claude plain text). Confidence `high`.

**L2 · Cited LLM extraction. Runs after the audit, aimed by §7.**
Sibling of `PROFILE_SCHEMA` / `extractJson`, one call per page category, output
`FactClaim[]` with `verbatim_quote` mandatory, then the §4.1 gate.

**L3 · Off-site, bounded. Runs after the audit, aimed by §7.**
The `offsite/agent.py` shape with a terminal `submit_facts` tool: GBP and Yelp
for hours / phone / review counts, the state registry for licensing. Get the
platform list from `review_platforms_for(business_kind)` — the consumer and
local tuples are deliberately forked and must not be merged.

**Cost note, corrected.** L2/L3 are cheap — a handful of extraction calls. The
**audit** is the expensive step (three engines × queries × 3 runs + judging),
and `anthropic_search` was just repriced 0.035 → 0.051 as a measured floor. The
admission control in §12.4 exists to protect the audit, not the fact sheet.

---

## 4 · The anti-hallucination rules

### 4.1 The verbatim-quote gate

A claim ships only if `verbatim_quote` is a literal substring of the fetched
text of `source_url` (normalized whitespace, case-insensitive). Fail → drop
silently, log it. Mechanical, free, and it converts "the model said so" into
"the page says so."

**Two implementation facts.** The existing `productClaims` cannot feed this
directly: it carries no quote, and `buildProfile` filters only on a non-empty
`claim`, so an unfounded `sourceUrl` survives. And `FetchClaudeResolver`
truncates each page to 40 000 chars across only two pages, so on the teaser path
the text a gate would re-check is partial. The gate belongs on the platform
crawl, which retains full text per page.

### 4.2 Blank is safe, and it is the default

A dimension left blank is not checked and cannot produce a false flag.
**Coverage is not the metric.** Fourteen quoted lines beat forty with six
guesses.

### 4.3 The disagreement rule

Two sources conflict — footer phone vs GBP, site hours vs Yelp — **emit nothing
and raise a question.** A stale footer plus a correct AI answer produces a flag
saying the AI is wrong when it is right. Disagreements go to a `questions[]`
list that becomes the confirm step.

### 4.4 Negative facts, which is where the value is

- **Derive only from closed enumerations.** `openingHoursSpecification` covering
  Mon–Sat is closed → `hours_sunday: Closed Sunday.` A services list is not
  closed → never infer "does not offer X" from absence.
- **Everything else becomes a question.**
- Write negatives as complete assertions — the judge must quote a verbatim
  contradicting line. `after_hours: No after-hours service.` is quotable;
  `after_hours: no` is not.

### 4.5 Date everything volatile

`as_of` per claim, stamped from the fetch. **Reuse the existing decay
machinery** — `teaser/src/freshness.ts` already has `SHELF_LIFE_DAYS = 30`,
`validThrough`, `isStale`, and the CLIs already thread staleness into the
render. Do not invent a second rule.

### 4.6 A thin-text refusal has to be written, not reused

`assertSufficientProfileText` is TypeScript-only
(`profileExtraction.ts:48`, 200-char floor). The Python crawl records
Cloudflare challenges (`fetcher.py` `_is_blocked` → `fetch_meta.blocked`) but
has **no thin-text refusal at all**. And it is a post-fetch guard either way, so
it cannot serve as the pre-flight "does this domain resolve" check §12.4 wants.

---

## 5 · Coverage map

| Section | L1 site | L2 site text | L3 off-site | Realistic |
|---|---|---|---|---|
| A · Identity | name, url | description, trade, founded | Wikidata (weak for local) | **Good** |
| B · Contact → `wrong_contact` | phone, address | contact page | GBP is the tiebreak | **Good, gated by §4.3** |
| C · Hours → `wrong_hours` | `openingHoursSpecification` | hours prose | GBP hours | **Good; Sunday-closed derivable** |
| D · Service area → `wrong_service_area` | `areaServed` | `SERVICE_AREA` pages | — | **Positives good, boundary needs asking** |
| E · Licensing | rarely in schema | footer licence numbers | state registry | **Medium, high value** |
| F · Services & pricing | `priceRange` | `SERVICE` + `PRICING` pages | — | **Positives good, negatives need asking** |
| G · Presence | `sameAs` | — | `LOCAL_REVIEW_PLATFORMS` counts | **Good, and it is Phase-4 data** |

Consumer: A/B/C strong from a pricing page and changelog; D comes from
`CompanyProfile.competitors`, not a second extraction; E is §7's output.

---

## 6 · Cache and versioning discipline

`fact_sheet` is an input to `_verdict_key()` (`judge_cache.py:97`). Two
consequences:

1. **Regenerating a sheet re-keys every verdict for that client.** The sheet is
   a stored, versioned artifact, not a per-run side effect.
2. **The invalidation is per-client, not global.** The prompt fingerprint is
   untouched, so W3.3's rules do not apply.

**Two things that make this harder than it reads.**

`audit_runs` has `fact_sheet` and `fact_sheet_present` and **no version
column**, and `create_audit_run()` takes no version argument. Nothing links a
run to `fact_sheets.id`. The provenance discipline this section asks for is
currently unimplementable — it needs `audit_runs.fact_sheet_id` /
`fact_sheet_version` added.

And re-warming after regeneration is *not* free in the current configuration:
the `prejudge` dump step refuses to run while `JUDGE_VERIFY` or `JUDGE_CASCADE`
are set, and `.env` sets `JUDGE_VERIFY=1`. Re-warming means unsetting them for
the dump, which changes what is being re-warmed.

---

## 7 · The reverse pass — the layer that aims L2 and L3

The §E watch-list is the section that carries a demo, and it is the one section
scraping cannot produce, because it is about the *models*, not the business.

After a run: collect the claims the answers make about the client, diff against
L0/L1 facts, and route the result. Agreement is silent. Contradiction is a
candidate flag. **A claim about a dimension the sheet is blank on is the
interesting case** — that is exactly what L2 and L3 should go and check, and
nothing else. Rank by consequence (`wrong_contact` and `wrong_hours` cost a job
today) and hand the top ~8 to the owner.

This inverts the human cost from "fill in 40 fields" to "confirm the eight
things AI is currently saying about you", and it makes the paid layers targeted
instead of speculative. It costs no extra engine calls.

---

## 8 · Verification tiers, and what may be said today

| Tier | Meaning | May produce a flag in a **sent** teaser? |
|---|---|---|
| `public_source_only` | one source, quoted | Only low/med severity, and only from the client's own site |
| `cross_confirmed` | two independent sources agree | Yes |
| `client_confirmed` | the owner said so | Yes, any severity |

**The freeze is global, and it covers the numbers this section used to cite.**
`judge.py:245-249` is explicit: until W3.4's consumer gold-set re-run passes,
**quote no accuracy figure for either ICP.** The 96/88/93 agreement figures and
the 80%-with-verifier / ~42%-without precision pair were all measured 2026-06-28
on the *pre-bump* prompt; the Phase 3 bump (2026-07-27) changed the fingerprint
and no re-measurement has happened (`data/oura_gold.json` and
`data/fort_gold.json` untouched since 2026-06-19). So the verifier remains the
right architecture — one adversarial pass per flag, recall-safe — but its
effectiveness is currently unquotable. Mention, prominence and framing are
explicitly exempt from the freeze.

**A signature is not a fourth tier — it is an orthogonal axis.** A signed sheet
(`sheet_status = "signed"`) is what confers `client_confirmed` on the claims the
client actually vouched for. It does not upgrade the rest. So a `v1.0` document
containing any `public_source_only` claim must **render those claims visibly
marked as unconfirmed**, or `audit-packaging-research.md` §4.4's finding card —
"Correct fact: from the signed fact sheet" — launders provenance the client
never gave. This is the one place where adopting the packaging doc uncritically
would make the product less honest.

One operational note: `JUDGE_VERIFY` used to default to `0` in code and was on
only because `.env` set it, so any environment without that line silently got
the weaker path. **Flipped to default-on 2026-07-31** (§13.3 D2). The Layer-3
content judge is live and also uncalibrated (no κ run, no labeled gold set),
which remains a second unquantified surface in the same report.

---

## 9 · Where the code lives

### 9.1 Two homes, one spec

**Platform (Python) — `src/audit/factsheet.py`.** Runs after the crawl, reads
the full `CrawlResult`, writes the markdown sheet and the claims. **This is the
only home where L1 is implementable**, since JSON-LD parsing exists only here.

**Teaser (TypeScript) — `teaser/src/factsheet/`.** Consumes the sheet the
platform produced and renders fact rows into `buildAuditCsv`. It should not
run its own extraction; two extraction prompts is the drift this plan exists to
avoid.

**Never on the website side.** Static export, no API routes, public anon key.

### 9.2 Four wiring facts that change the estimate

1. **The confirm gate is unreachable on the live path.** `cli.ts:121` disables
   it under `--json`, and `/api/teaser` always passes `--json`. Anything hung
   off `opts.confirm` is dead code for the actual GTM flow. The reachable gate
   is the review UI, which today runs *after* the audit has been paid for. The
   fact-sheet gate therefore belongs in the queue screen (§12.3), before the
   run is submitted — not in `confirmGate`.
2. **Extending `confirmGate` is not additive.** Its hook is typed
   `(profile, querySet) => Promise<{profile, querySet} | null>`. Carrying claims
   through means changing that signature in `pipeline.ts`, `confirmGate.ts` and
   `cli.ts`.
3. **`productClaims` is a required field** on `CompanyProfile` despite its
   comment. Any new `factClaims` field must be optional like `aliases` and
   `location`, or every profile literal and seven test files break.
4. **`regenerateFromDraft` would silently drop the sheet.** It rebuilds the
   profile from the stored `ReportPayload`, which carries no claims — the same
   failure already patched for `clientAliases`, `businessKind` and `location` by
   persisting them on `TeaserDraft`. A sheet must be persisted the same way.

### 9.3 Flags do not reach the teaser one-pager today

`selectFindings` never reads `report.accuracy_flags`; `toFinding` hardcodes
`source: "losing_query"`, so the `"accuracy_flag"` arm of `Finding.source` is
dead code. Emitting fact rows lights up flags on the `ReportPayload` and changes
**nothing** about the teaser PDF. The only TS consumer is
`select/buildAudit.ts`, in the paid audit deliverable.

**This is the single biggest scope correction in this revision.** "Fact rows
make the teaser show accuracy findings" requires work in `selectFindings`, not
just a CSV change. It gets its own work item (F3).

---

## 10 · Build sequence

`F*` sits beside the `W*` items in `smb-pivot-build-plan.md`. F0–F2 are
cache-neutral and touch no judge prompt.

| # | Item | Depends on | Acceptance |
|---|---|---|---|
| **F0** | The `FactClaim` type + both renderers + provenance appendix | — | Round-trip: claims → fact rows → `csv_loader` → `_build_fact_sheet` gives the expected string, using `build_template_csv`'s pinned Oura rows as the fixture. Keyless rows rejected (§2.1). |
| **F1** | L0 + L1 deterministic extraction, platform-side | F0, §13.2 measurement | On 8–10 real trade sites, produce a sheet with zero LLM calls; every line traces to JSON-LD or a `tel:`/NAP block. A Python thin-text refusal written (§4.6). |
| **F2** | Fact rows in `buildAuditCsv` + persistence on `TeaserDraft` | F1 | A run with a sheet emits `accuracy_flags` on the `ReportPayload`; a regenerated teaser keeps its sheet. Consumer CSV config block unchanged — note `teaser/tests/consumerPathRegression.test.ts:252` is a whole-CSV substring check for `"location"`, so a fact key containing that string fails it. |
| **F3** | `selectFindings` reads `accuracy_flags` | F2 | The `"accuracy_flag"` arm of `Finding.source` stops being dead; a high-severity flag can be selected as a lead or table finding. **Without this, F2 changes nothing visible.** |
| **F4** | The queue screen + `/fact-sheets` endpoints (the reachable gate) | F0 | Approve moves `draft` → `active`; each claim shows its quote and source link; questions listed. Mirrors the `/teasers` lifecycle. |
| **F4.5** | Signed-sheet export: the `v1.0` render + changelog + competitor-set section | F4 | `audit-packaging-research.md` item 23's deliverable. A renderer, not a pipeline — F0's renderer 2 already carries the provenance appendix. Unconfirmed claims render visibly marked (§8). |
| **F5** | §7 reverse pass → the question list | F2, a real run | Against the Fort or Oura corpus, a ranked question list a human agrees with. |
| **F6** | L2 cited extraction + the §4.1 gate, aimed by F5 | F5 | Adversarial test: a fixture page with no price, asked for pricing → zero claims, one drop logged. Never weaken this test. |
| **F7** | §4.3 disagreement rule + L3 off-site via `review_platforms_for` | F6 | Footer phone ≠ GBP phone → no claim, one question. Budgets and quotas like `offsite/agent.py`; if the audit log is to be JSONL, that serializer must be written. |

**Ship F1 alone if nothing else gets built** — but only after §13.2.

---

## 11 · Decisions needed (Josh + Abhi)

1. **Does F3 happen?** Without it, fact sheets improve the paid audit
   deliverable and the internal picture, and change nothing a prospect sees in a
   teaser. That reorders everything.
2. **Does the owner-confirm step exist as a product surface**, or is it Josh
   reading questions off a call? The second needs no build and is probably right
   for the first ten clients.
3. **May a `public_source_only` sheet produce flags in something we send?**
   §8 says low/med only. The conservative alternative is internal-only until a
   call confirms it.
4. **Who owns the re-verify cadence** as sheets age (§4.5)?
5. **~~Pick one plan~~ — RESOLVED 2026-07-31. They split by lifecycle; keep
   both.** `docs/audit-packaging-research.md` is a *governance and commercial*
   plan for a B2B retainer buyer (§14.3, $349–$2,000+/mo, plus a $1,500–$5,000
   one-time "Calibration" fee); this is a *production* plan for a local SMB
   arriving through `/free-check`. Its sheet is a contract annex — "claimed
   features, unclaimed features/guardrails, pricing, positioning", signed before
   the first run. This one's is a crawl output — hours, phone, service area,
   licensing. Same name, same consumer (`judge.py`), different lifecycle state.
   Reconciliation, folded in above: `sheet_status` (§2) makes "v1.0" the signed
   snapshot of one record; §8 keeps a signature from laundering unconfirmed
   claims; F4.5 (§10) is item 23's deliverable; §12.3 narrows Tier 1's
   authority. **Two corrections to the earlier framing:** §9.6 of that doc is
   *query-set* versioning, not fact-sheet versioning — there was never a
   conflict there, and its §12.9 ("one record per client per version") is
   external corroboration for C2. And its item 22 (free scan → lead queue) is
   already built, so its Phase-5 placement of this work is wrong on the facts.
   **Still open from that doc:** its §9.5 binds the fact sheet and the
   competitor set into one governance artifact. This plan has no competitor-set
   plan at all. If you adopt §9.5, F4's screen gates two things — decide before
   building it, not after.

---

## 12 · Storage, auto-generation, and admission control

*SQL: `data/schema_factsheets.sql` (platform) and
`geoWebsite/scripts/leads-dedup.sql` (leads). Both are untracked and unapplied.*

### 12.1 Two Supabase projects

Leads live in the project in `geoWebsite/lib/site.ts` (`satjbyfjzrwocwwonsxz`).
`audit_runs`, the judge cache and `site-audit-html` live in the project in
`geoPromptRunner/.env` (`hohveqgemavghcpfjdiy`). **Different databases.**

Fact sheets belong to the **platform** project — the sheet feeds
`audit_runs.fact_sheet`, it is an input to `_verdict_key()`, and it authorizes
platform spend. A worker bridges the two carrying only `lead_ref`; **no prospect
email or phone crosses over.**

Consequence: **a constraint on `leads` cannot see whether a fact sheet exists.**
The real limiter sits next to the spend.

### 12.2 Tables for the sheet, a bucket for the sources

`fact_sheets` + `fact_claims`. Not a bucket: every question you ask of a sheet
is a query.

`audit_runs.fact_sheet` stays as the point-in-time snapshot; `fact_sheets` is
the living record.

**The bucket's job** is the gzipped page snapshots backing each quote, in a
private `factsheet-sources` bucket. One correction: `upload_site_audit_html` /
`download_site_audit_html` hardcode `BUCKET_SITE_AUDIT_HTML` and take no bucket
argument — the *shape* transfers, the functions do not. Either parameterize them
or write parallel helpers. And `delete_audit_runs` does not cascade Storage, so
a second bucket adds a second orphan surface that the deletion path must learn
about.

**On grants:** the schema file's explicit `revoke`s are **new**, not parity with
the other `data/schema_*.sql` files — those enable RLS and stop. Two of them
(`schema_judge_cache.sql`, `schema_content_judge_cache.sql`) do not enable RLS
at all, which is the live exposure of the same footgun.

### 12.3 Generation on submit: enqueue, then a worker

Postgres cannot crawl, and the INSERT path must never cost a lead — the alert
trigger already catches every exception and returns `NEW` for exactly that
reason.

**The enqueue is cross-project**, which the first draft glossed. `factsheet_jobs`
lives in the platform project, so the leads trigger cannot insert into it. Two
options: a `pg_net` POST to the platform API (fire-and-forget, needs the same
reconciliation `lead_alert_log` already does, and needs the API hosted), or a
worker polling `leads` with a scoped role. **Polling is the only one that works
today**, since `run-api.sh` is localhost.

| Tier | What runs | Cost | When |
|---|---|---|---|
| 1 | L0 + L1 | a fetch and a parse | Automatically, every admitted lead |
| 2 | L2 + L3 | small, but real | **After the audit**, aimed by §7 |

The lead state machine already exists — `status in ('new','vetted','teaser_sent',
'converted','disqualified')` — so "gate on `vetted`" is a use of it, not a new
concept.

**Tier 1's authority is narrow, and that is what keeps the §0 invariant
amendment defensible.** A Tier-1 sheet may aim the reverse pass (§7) and feed
the teaser's low/med-severity path. It may never be the "signed fact sheet" that
`audit-packaging-research.md` §4.4 cites in a finding card. Automation of the
*labor* is endorsed by that doc (§12.2: "whoever writes fact sheets and eyeballs
output today cannot remain in that loop at 50 clients"); automation of the
*authority* is not.

### 12.4 The limiter: dedup at the spend

**One active sheet per domain** (`uq_fact_sheets_active_domain`). **One in-flight
job per domain** (`uq_factsheet_jobs_inflight`), enforced by Postgres because two
submissions in the same minute is the ordinary case. **A daily tier-2 budget**
with over-cap jobs recorded as `skipped_cap`.

One thing *not* to mirror from the alert cap: it counts every
`lead_alert_log` row including the `flood` rows it writes itself, so once
tripped it stays tripped for a full hour regardless of real volume.

The generator gets its own spend ceiling separate from `MAX_AUDIT_COST_USD` /
`MAX_TOTAL_SPEND_USD`.

**Identity key.** The registrable domain, via `_registered_domain`. Note there
are **two copies** of that function (`offsite/tools.py:97`,
`audit/checks/links.py:130`) — pick one and say which. And the key is wrong for
platform-hosted SMBs: two businesses on `facebook.com/...` or `*.wixsite.com`
share a host. Fall back to lead review rather than auto-rejecting those.

### 12.5 Deduping `leads` itself — four traps

1. **`where phone is null` is load-bearing.** The callback opt-in inserts a
   second row with the same email; a plain `unique(email)` breaks it and the
   form's catch swallows the error.
2. **A 409 must read as success in the form** — `postLead` currently throws on
   any non-2xx. But **this does not close the enumeration oracle**: the
   publishable key is public, so an attacker POSTs directly and reads the 409
   themselves. The client change is UX only; say so honestly.
3. **A rejected insert is a lead that vanishes with no record.** The alert
   trigger is `AFTER INSERT`; a unique violation aborts the insert, so no row, no
   alert, nobody told — while the owner sees a confirmation screen. Dedup must
   ship with an `on conflict` path that logs a `repeat_inquiry`, or the queue
   loses real prospects invisibly. **This is the reason not to rush 12.5.**
4. **`verify-leads-backend.mjs` breaks after dedup.** It inserts a fixed
   `test@example.com` / `https://example.com` row and asserts 201, and its own
   DELETE probe is blocked by RLS by design — so it becomes single-use until
   someone clears the row by hand. It is a launch gate; plan for that.

Also: `leads_queue` enumerates columns, so a new `website_host` will not appear
in the queue until the view is updated — and re-running `leads-visibility.sql`
wholesale **reverts the SLA email wiring**. Update the view standalone.

---

## 13 · What the verification pass changed, and what blocks F0

### 13.1 Corrections folded in

`productClaims` is populated on the live path, not dropped (the drop is on the
regenerate-from-storage path) · flags never reach the teaser one-pager (new F3) ·
the confirm gate is unreachable under `--json` (gate moved to the queue screen) ·
`LOCAL_REVIEW_PLATFORMS` via `review_platforms_for`, not `REVIEW_PLATFORMS` ·
no `fact_sheet_version` column exists · bucket helpers are not reusable as-is ·
no Python thin-text refusal exists · `build_template_csv` already emits fact rows
· the accuracy freeze is **global, not local**, and covers the precision figures
§8 previously cited · the cross-project enqueue needs a worker, not a trigger ·
L1 has no TypeScript path · Tier 2 is not the expensive layer, the audit is.

### 13.2 Three things that block starting

**No migration runner** (downgraded 2026-07-31 — this is smaller than first
written). The build-log's claim that `.env` "carries no direct Postgres
credential, only the REST key" is **stale**: `.env.example:81-86` documents
`SUPABASE_DB_URL` for exactly this purpose, `settings.py:24` reads it, and the
live `.env` sets it. What is missing is a consumer — `settings.py:24` is the
only reference in the repo, so nothing applies a `data/*.sql` file
programmatically, which is why `audit_runs.judge_model` and
`audit_runs.location` are still unapplied and run provenance is degraded today.

**Fixed 2026-07-31:** `scripts/apply_schema.py` is the consumer. Whole file in
one transaction, DSN redacted in output, `--dry-run` to check a file without
connecting.

    python -m scripts.apply_schema data/schema_run_provenance.sql
    python -m scripts.apply_schema data/schema_cache_rls.sql
    python -m scripts.apply_schema data/schema_factsheets.sql

The credential has never been exercised, so the first run is also its test; if
`db.<ref>.supabase.co` does not resolve, `supabase/.temp/pooler-url` holds the
pooler string. **Migrations only** — it bypasses RLS, and it is the same class
of credential `leads-visibility.sql` forbids for reading the leads queue. The
API, the runner and any worker keep the REST key.

**The JSON-LD coverage question is unmeasured** — the one item still genuinely
open. `scripts/measure_jsonld_coverage.py` now exists; it needs a list of ~10
real local sites and one run. It measures raw HTML under a GPTBot UA with the
same extruct call `fetcher.py::_extract_json_ld` makes, because measuring the
rendered DOM would count schema the engines never see and send F1 down the wrong
path. Under roughly 40% schema coverage, F1's centre of gravity is `tel:` links
and prose, and L1's spec should say so before anyone writes it.

**~~The packaging doc conflict~~ — resolved**, see §11.5. Two plans, two
lifecycle states, both kept, four amendments folded in.

### 13.3 Punch list

Ordered by what has to move first. "Mine/ours" is the split between work that
needs a decision or a human and work that is just code.

**A · Clear before F1 (F0 is safe to start regardless)**

| # | Issue | Fix | Owner |
|---|---|---|---|
| A1 | `docs/audit-packaging-research.md` was a second plan for this artifact | ✅ **Resolved** — they split by lifecycle and ICP; both kept, four amendments folded in (§11.5) | done |
| A2 | JSON-LD coverage on real trade sites is unmeasured | ✅ **Tooled** — `python -m scripts.measure_jsonld_coverage --urls sites.txt`. Raw HTML, GPTBot UA, the same extruct call the crawler makes. Needs a list of ~10 real local sites and one run | Josh runs it |
| A3 | Undecided: does F3 happen | Without it, sheets improve the paid audit only and no teaser changes | 🔴 Josh |
| A4 | `audit-packaging-research.md` §9.5 binds fact sheet + competitor set into one governance artifact; this plan has no competitor-set plan | Decide before F4 — it changes what the queue screen gates | 🔴 Josh + Abhi |

**B · Bugs in the drafts written this session — all fixed by one redesign**

`leads-dedup.sql` now **marks duplicates instead of rejecting them**. Rejecting
was wrong on every axis at once: a unique violation aborts the INSERT, so the
`AFTER INSERT` alert trigger never fires — no row, no `lead_alert_log`, no
email, while the owner sees the confirmation screen (B2). It needed a form
change that would not have closed the oracle it created (B3). It broke
`verify-leads-backend.mjs`, which inserts a fixed row, asserts 201, and cannot
clean up because its DELETE probe is blocked by design (B4). And a host is not
an owner: two SMBs on `facebook.com/<page>` or `*.wixsite.com` share one (B5).

Marking costs none of that. A `lead_host()` function (with the `'i'` flag — the
admitting constraint is `~*`, so a case-sensitive pattern silently failed to
dedup, B1), a generated `website_host`, a `duplicate_of` pointer filled by an
exception-safe `BEFORE INSERT` trigger that skips known platform hosts, and a
standalone `create or replace view` for `leads_queue` — standalone because
re-running `leads-visibility.sql` wholesale reverts the SLA email wiring (B6).
The insert always succeeds, the alert always fires, the form is untouched, both
launch gates still pass, and a false positive is a flag a human overrules
rather than a lead that never arrived. ✅ **All six closed.**

**C · Pre-existing gaps this work depends on**

| # | Issue | Fix | State |
|---|---|---|---|
| C1 | No migration runner; `SUPABASE_DB_URL` was declared and read but had no consumer, which is why two migrations sat unapplied | `scripts/apply_schema.py` — one transaction, redacted DSN in logs, `--dry-run` | ✅ done |
| C2 | `audit_runs` has no `fact_sheet_id` / `fact_sheet_version`; `judge_model` and `location` never landed | `data/schema_run_provenance.sql` — all four, `add column if not exists` | ✅ written, **needs applying** |
| C3 | Two copies of `_registered_domain` with separate `TLDExtract` instances | `src/audit/domains.py`; both call sites import it | ✅ done |
| C4 | `upload_site_audit_html` / `download_site_audit_html` hardcode the bucket | Parameterize, or write `*_factsheet_source` siblings | ⏸ lands with F1 |
| C5 | `delete_audit_runs` does not cascade Storage; a second bucket is a second orphan surface | Extend `_delete_site_audit_blobs` | ⏸ lands with the bucket |
| C6 | No Python thin-text refusal — `assertSufficientProfileText` is TS-only, and post-fetch either way | Write one for the crawl; separate pre-flight resolve check | ⏸ lands with F1 |
| C7 | `productClaims` is a required field on `CompanyProfile` | Make any new claims field optional | ⏸ lands with F2 |
| C8 | `regenerateFromDraft` would silently drop a sheet | Persist it on `TeaserDraft` | ⏸ lands with F2 |

C4–C8 are deliberately **not** done now: each one adds a parameter, a field or a
helper that nothing would call until its build item exists, and dead code that
looks live is its own hazard.

**D · Hygiene**

| # | Issue | Fix | State |
|---|---|---|---|
| D1 | `judge_cache` and `content_judge_cache` were the only tables with **RLS never enabled** — a comment, never a statement. Not a live leak (that project's key never reaches a browser; `web/` talks only to the FastAPI), but the one gap in an otherwise uniform posture. Safe: every other table runs RLS with no policies and the app works, so its key bypasses RLS | `data/schema_cache_rls.sql` | ✅ written, **needs applying** |
| D2 | `JUDGE_VERIFY` defaulted to `0`; the accurate path shipped only because `.env` said so, so a fresh clone or CI silently produced low-precision verdicts that looked identical to good ones | Default flipped to `1`. Note the `prejudge` dump step refuses while it is set — pass `JUDGE_VERIFY=0` for that step. A loud refusal beats a silent wrong default | ✅ done |
| D3 | The alert `hourly_cap` counts its own `flood` rows, so once tripped it sustains itself for an hour regardless of real volume — suppressing exactly the leads someone is waiting on | `lead-alert-cap-fix.sql` adds `kind <> 'flood'` to the count. **Diff the live function first** in case it has drifted | ✅ written, **needs applying** |
| D4 | Stale docs quoting frozen figures with no freeze notice | Freeze banners on `project-queue.md` and `judge-accuracy-plan.md`, superseded banner on `left.md`, `BUILD_PLAN.md`'s niche row corrected | ✅ done |

**E · Human-only, and the gate on selling any of this**

W3.4: label 25–40 real local answers (models must not label their own gold set),
then run calibration twice — the local set and a re-run of Oura + Fort against
the post-bump judge. Until it passes, **no accuracy or agreement figure may be
quoted for either ICP.** The Layer-3 content judge is live and uncalibrated on
the same terms.

### 13.5 State of the build — audited 2026-07-31, evening

*Two read-only audits against `464125e`, working tree clean. Everything below was
traced in code, not inferred from commit messages.*

#### The flow, as actually built

| # | Step | State |
|---|---|---|
| 1 | Form → `leads` row + alert email | ✅ live |
| 2 | Worker polls leads cross-project, enqueues Tier 1 | ✅ built (`worker.py`), PII-safe — the SELECT names five columns and `email`/`phone` are not among them |
| 3 | Crawl + deterministic extraction → DRAFT sheet | ✅ built (`extract.py`, L0+L1, zero model calls) |
| 4 | Sheet lands in a queue | ✅ built (`/fact-sheets`, `web/app/fact-sheets/page.tsx`) |
| 5 | Human reviews claim-by-claim, approves | ✅ built — every claim shows its verbatim quote and a link to the page it came from; questions render first |
| 6 | **The approved sheet reaches a run** | ❌ **does not exist in any form** |
| 7 | Judge emits accuracy flags | ✅ pre-existing |
| 8 | A flag becomes a teaser finding | ❌ built, permanently inert (below) |
| 9 | Teaser renders it | ❌ no renderer reads it |
| 10 | Email to the prospect | ❌ blocked on a verified Resend domain |

**Steps 1–5 and 7 work. Steps 6, 8 and 9 are three breaks in series**, and each
one independently nullifies work that is already shipped and tested.

#### The three breaks

**B1 — nothing reads an approved sheet.** `db.load_fact_sheet(domain, state=ACTIVE)`
is complete, documented, tested and has **zero callers** outside `db.py`. Every
run path still takes a hand-made artifact: `geo audit --fact-sheet` reads a *file
path*; `POST /audits` reads `fact` rows from an *uploaded CSV*; `runner.py` never
queries `fact_sheets`. `save_audit_run(fact_sheet_id=, fact_sheet_version=)`
exists, the columns are applied, and no caller passes them — so every run row
has NULL provenance. Approving a sheet changes one column and nothing else: no
notification, no writeback to `leads.status`, no next step. The UI's own promise
— *"Approving one makes it the reference every accuracy finding for that domain
is measured against"* — is not true today.

**B2 — `fact_sheet_verification` is never populated.** It is a `build_report`
parameter defaulting to `None` (`reports.py:340`) and **neither production call
site passes it** (`runner.py:899`, `:987`). The TS mirror `maySendFlag(null, …)`
returns `false` unconditionally, so `selectAccuracyFindings` returns `[]` on
every real run. F3 is built and can never fire.

**B3 — `accuracyFindings` is produced and consumed by nothing.**
`selectFindings.ts:568` builds the list; no renderer reads it.

Fixing B2 is one argument at two call sites. B1 and B3 are real work.

#### Also unrunnable / unreachable

- **`data/schema_factsheets.sql` is still unapplied.** Against the live database
  every `/fact-sheets` call raises `StorageError` → 503. The queue, the worker
  and the gate are all inert until one command runs.
- **No version allocation.** `build_sheet` never sets `version`; `save_fact_sheet`
  is a plain insert against `unique (domain, version)`. The second worker job for
  a known domain is filed as **`FAILED` / `"StorageError"`** — so every
  regeneration is permanently unreachable *and* mislabelled as a crawler fault.
  No test covers it.
- **`CROSS_CONFIRMED` can never be set.** `resolve_conflicts` deliberately
  refuses to upgrade on agreement and no other writer exists, so
  `verification_tier` is permanently `public_source_only`. Even with B2 fixed,
  `SENDABLE_SEVERITIES` would suppress every HIGH flag forever.
- **`geo factsheet` does not persist.** It writes markdown/CSV to disk and never
  calls `save_fact_sheet`. The queue's empty-state copy names it as a source of
  rows; that is wrong.
- **`rejected` → `active` is reachable.** `POST /approve` checks no current
  state, and the UI offers a live Approve button on the rejected tab.
- **`SheetStatus` (draft/client_reviewed/signed) has no column**, so every loaded
  sheet reports `draft` and F4.5 has nothing to read.
- **No per-claim edit or drop.** A reviewer who spots one bad claim in nine must
  reject all nine. The `/teasers` and `/audit-deliverables` lifecycles both have
  an `edit` arm; this one omits it.

#### Extraction coverage — what the sheet can and cannot say

The two fabrications found by the verify phase **were fixed at HEAD**
(`464125e`), with tests pinning the correct behaviour — a street now needs a real
thoroughfare type on an anchored line, and an unreadable hours entry refuses the
whole block rather than deriving a closure from it.

One residual of the same class survives, untested: the **same-line** NAP branch
still uses unanchored `_STREET_RE.search`, so a footer reading
`"Over 30 years on the road, Berkeley, CA 94702"` still produces
`contact_address: 30 years on the road, Berkeley, CA 94702`. Every prose fixture
in `test_factsheet_fabrication.py` puts the prose on a separate line, exercising
only the branch that was hardened.

By template section: **A** partial (name, website — no trade, aliases, founder),
**B** good, **C** good, **D** positives only, **E · licensing — nothing at all**
(declared, titled, never emitted), **F** `priceRange` only — the `SERVICE` and
`PRICING` pages are crawled and never mined, **G** `sameAs` links only.

So **two of the four local flag types have no producer**: `licensing`, and the
negative half of `wrong_service_area` — the boundary line that §4.4 forbids
deriving and nothing asks about.

#### Deviation from the goal, stated plainly

The goal was: *a form submission becomes a fact sheet, a human approves it, and
the teaser tells the prospect what AI gets wrong about them.*

What exists is **two working halves that do not touch.** The left half —
lead to reviewed sheet — is real and good. The right half — judge, flags, teaser
— is real and pre-existing. The join between them was never built, and three
separate shipped work items (F2, F3, the gate) sit on the far side of it
producing no observable effect.

The cheapest path to closing it, in order: apply the schema; pass
`fact_sheet_verification` at the two call sites; add version allocation; make
`POST /audits` accept a `fact_sheet_id` and hydrate it through
`load_fact_sheet` + `to_fact_rows`; then render `accuracyFindings`.

### 13.4 Stale docs this plan cites

`docs/project-queue.md` (snapshot 2026-06-24) predates the entire SMB pivot and
carries no freeze notice on its calibration figures — the exact trap §8 fell
into. `docs/left.md` (2026-06-03) is superseded on gold sets, fact sheets and
test counts, and lists outreach automation as a non-goal, which is now the
product. `docs/judge-accuracy-plan.md` is frozen at 2026-06-28, all pre-bump.
`teaser/BUILD_PLAN.md:347` still says the niche is "RESOLVED: B2C consumer".
