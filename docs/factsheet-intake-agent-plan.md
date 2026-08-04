# Fact-Sheet Chat Intake — Engineering Plan (for a Claude coding agent)

*Turning the fact sheet from a crawl artifact nobody vouched for into a document
the business owner has confirmed line by line — through a conversational intake
that ends with a runnable query CSV in a review screen.*

**Companion document:** `docs/factsheet-intake-design-plan.md` (for Claude Design).
**§1 of both documents is byte-identical.** It is the seam. If you change a
question id, a state name, an API route or a field name, change it in both or the
two builds diverge silently.

**Read before starting:** `CLAUDE.md` (hard invariants),
`.claude/skills/geo-dev/SKILL.md`, `docs/factsheet-autogen-plan.md` (§2 the claim
contract, §4 the anti-hallucination rules, §8 verification tiers, §13.5 what is
actually built), `docs/query-generation-plan.md` (§2 allocation, §5 the QA gate),
`docs/ui-redesign-sable-spec.md` (the app chrome you are building inside).
**Load `.claude/skills/audit-packaging/SKILL.md` before touching anything a
client reads** — the review screen is one of those things.

**The gate for every change:** `mypy src/ && ruff check src/ && pytest tests/`
for Python; `cd web && npm run typecheck && npm run build` for the frontend.
One `docs/build-log.md` entry per completed phase, appended at the top.

---

## 0 · Why this exists, in one paragraph you should not skip

`src/audit/factsheet/gate.py` is the whole argument. A sheet's
`verification_tier` is the **weakest** verification across its claims, and
`SENDABLE_SEVERITIES[public_source_only]` is `{LOW, MED}`. Today every
auto-generated sheet is permanently `public_source_only` — `resolve_conflicts`
refuses to upgrade on agreement and no other writer exists
(`docs/factsheet-autogen-plan.md` §13.5). So **HIGH and CRITICAL accuracy flags
are structurally unreachable**, and HIGH/CRITICAL is exactly the class of finding
the product sells: *"ChatGPT is quoting your old phone number," "Gemini says you
have no subscription fee."* This intake is the only mechanism in the system that
can set `Verification.CLIENT_CONFIRMED`. It is not a nicer form. It is the switch
that turns the accuracy half of the product on.

The second reason: two of the four local flag types have **no producer at all**.
`licensing` is declared, titled and never emitted, and the negative half of
`wrong_service_area` — the boundary line — is forbidden to derive (§4.4) and
nothing asks for it. `Q-LOC-08` and `Q-LOC-07` below are those producers.

---

## 1 · The shared contract

> **This section is identical in `docs/factsheet-intake-design-plan.md`. Keep it that way.**

### 1.1 The five surfaces

| # | Surface | Route | What it is |
|---|---|---|---|
| S1 | **Queue** | `/fact-sheets` → tab **Needs review** | Everything not yet approved: untouched crawl drafts, intakes in progress, intakes awaiting review |
| S2 | **Intake** | `/fact-sheets/[sheetId]/intake` | The conversational Q&A. One question at a time. |
| S3 | **Review** | `/fact-sheets/[sheetId]/review` | The sheet + the generated queries + the CSV, all editable. The approve gate. |
| S4 | **Active** | `/fact-sheets` → tab **Active** | Approved sheets. Read-only until you click Edit, which opens a new intake. |
| S5 | **Home** | `/` → "Ready to run" strip | Active sheets with a query set, one click from a run. |

There is **no Rejected tab and no Reject button.** The only exits from the queue
are *approve* and *leave it there*. See §6.3 for what happens to the
`rejected` state that still exists in the database.

### 1.2 States

Two independent state machines. Do not merge them.

**`IntakeState`** — new, per session, per domain:

```
not_started ──► in_progress ──► awaiting_review ──► approved
                     │                 │
                     └────────┬────────┘
                              ▼
                          abandoned      (a state, never a delete)
```

**`FactSheetState`** — existing, in `src/storage/db.py`, **unchanged**:
`draft` · `active` · `superseded` · `rejected`.

The join: an intake reaching `approved` writes exactly one new `fact_sheets` row
at `version = N+1` in `draft`, then immediately calls `activate_fact_sheet`,
which demotes the domain's previous `active` row to `superseded`. One approval,
one version, one row. Nothing is ever mutated in place and nothing is deleted.

### 1.3 Question id namespace

| Prefix | Branch | Count |
|---|---|---|
| `Q-ID-*` | Trunk — asked of everyone | 5 |
| `Q-LOC-*` | Local-service branch | up to 11 |
| `Q-PRD-*` | Product branch | up to 11 |
| `Q-END-*` | Shared tail | 2 |

**Ceiling: 18 cards. Median: 13** when the crawl found JSON-LD, because
pre-filled facts collapse into batch-confirm cards that carry 3–5 facts each.
A *card* is not a *field*.

### 1.4 The question record

One JSON object per question, served by the API, consumed by the UI. The UI
never hardcodes a question; the registry is the single source of truth.

```ts
type AnswerKind =
  | "choice"         // 2–4 options, single select
  | "multi"          // options, multi select, + "add your own"
  | "confirm"        // "I found X. Right?" → yes | fix (reveals an input)
  | "batch_confirm"  // N pre-filled facts, tap the wrong ones
  | "text"           // one line
  | "longtext"       // 2–4 lines
  | "list"           // repeatable chips
  | "hours"          // 7-day grid, per-day open/closed
  | "money"          // currency, auto-stamped "as of"
  | "tiers"          // repeatable {name, price, includes}
  | "links"          // labelled URL fields
  | "watchlist";     // repeatable {what the AI said, what is actually true}

interface IntakeQuestion {
  id: string;                    // "Q-LOC-04"
  kind: AnswerKind;
  section: SheetSection;         // routes the resulting claim
  keys: string[];                // fact-row keys this card can produce
  prompt: string;                // the bot's line
  helper?: string;               // the smaller line under it
  placeholder?: string;
  options?: { value: string; label: string }[];
  prefill?: unknown;             // from the draft sheet; null when nothing was found
  prefillSourceUrl?: string;     // shown as "found on your pricing page"
  skippable: boolean;            // false only for Q-ID-01 and Q-LOC-00
  negativeFirst: boolean;        // true ⇒ "no" is the valuable answer, lead with it
  assertionPreview: string;      // template with {slots} — see §1.6 rule 4
  showIf?: { questionId: string; equals: unknown }; // branching
}
```

### 1.5 API routes

All under the existing `X-API-Key` scheme in `src/api/app.py`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/fact-sheets/{sheet_id}/intake` | Create or resume a session. Returns `{session_id, plan, prefill, next}` |
| `GET` | `/intake/{session_id}` | Full session state (resume after a refresh) |
| `POST` | `/intake/{session_id}/answer` | `{question_id, value \| null, skipped}` → `{next, progress, assertions}` |
| `POST` | `/intake/{session_id}/back` | Step back one card; the answer stays, editable |
| `POST` | `/intake/{session_id}/complete` | Build claims + query set + CSV → `awaiting_review` |
| `GET` | `/intake/{session_id}/review` | `{claims, unconfirmed, query_set, csv, lint, cost, tier}` |
| `PATCH` | `/intake/{session_id}/review` | Edit claims / queries / config. Revalidates, returns fresh lint |
| `POST` | `/intake/{session_id}/approve` | Write `fact_sheets` v(N+1) → activate → `{fact_sheet_id, version}` |
| `GET` | `/fact-sheets/{sheet_id}/query-set` | The stored set + CSV for an active sheet |
| `POST` | `/fact-sheets/{sheet_id}/edit` | New session pre-filled from the active sheet |

`GET /fact-sheets?state=active` gains `has_query_set: bool` so S5 can filter
without an N+1.

### 1.6 The four rules that govern every answer

1. **Only falsifiable facts.** A price, a licence number, a closing time. Never
   "the leading platform." The judge can only check things that are true or false,
   and a marketing line in the sheet is a line that can never fire.
2. **Blank is safe, and it is the default.** A skipped card produces *zero*
   claims. A dimension the sheet is silent on is not checked, so it can never
   produce a false flag. Coverage is not the metric — fourteen confirmed lines
   beat forty with six guesses.
3. **Negatives are where the value is.** *Closed Sunday.* *No after-hours
   service.* *Does not serve Marin County.* *There is no free tier.* These are
   what make an over-claiming AI answer flaggable. A sheet of only positive facts
   catches a fraction of what one with negatives does. Cards marked
   `negativeFirst` exist for this and must not be reworded into positives.
4. **The owner always sees the exact sentence they will be quoted on.** Before a
   card commits, the UI renders the assertion the answer becomes — *"No
   after-hours service."* — not the raw input — *"No."* This is the trust
   mechanism, the teaching mechanism, and the cheapest defence against a false
   accusation in a document we send a stranger.

### 1.7 The tier rule (the one that decides whether any of this pays off)

`FactSheet.verification_tier` is a **minimum**. One leftover
`public_source_only` claim caps the entire sheet at LOW/MED and nullifies the
intake.

**Therefore: at approval, every claim in the outgoing sheet is either
`client_confirmed` or it is dropped.** The review screen must show the tier, name
what is holding it down, and offer exactly two ways out — confirm it, or drop it.
There is no third option and no silent pass-through.

---

## 2 · What already exists (verified against the tree, 2026-08-04)

Do not rebuild any of this.

| Piece | Where | State |
|---|---|---|
| The claim contract | `src/audit/factsheet/models.py` — `FactClaim`, `FactSheet`, `assigned_claims` | ✅ complete, frozen, validated in `__post_init__` |
| Both renderers | `src/audit/factsheet/render.py` — `to_fact_rows`, `to_csv`, `to_markdown`, `suggested_run_inputs` | ✅ complete |
| Deterministic extraction (L0 + L1) | `src/audit/factsheet/extract.py` — `build_sheet`, `claims_from_json_ld`, `claims_from_html`, `derive_negative_claims`, `verify_quotes`, `resolve_conflicts` | ✅ complete, zero model calls |
| The severity gate | `src/audit/factsheet/gate.py` | ✅ complete |
| Queue lifecycle | `db.save_fact_sheet` (always DRAFT), `activate_fact_sheet` (demote-then-promote), `reject_fact_sheet`, `uq_fact_sheets_active_domain` | ✅ complete |
| Queue API + UI | `GET/POST /fact-sheets*` in `src/api/app.py`; `web/app/fact-sheets/page.tsx` | ✅ built (tabs: draft/active/rejected/superseded) |
| Sheet reaches a run | `runner._attach_fact_sheet` loads an ACTIVE sheet by id; `fact_sheet_verification` is threaded to `build_report` | ✅ **fixed since the autogen plan was written** — §13.5's B1/B2 no longer apply |
| **The local run CSV assembler** | `src/prompts/assemble.py` — `assemble_run_csv(business, website, trade, city, region, competitors, …)` | ✅ **complete and exactly what S3 needs.** Emits config + query rows, **no fact block**, because "the sheet attaches to the run by id and a run carrying both is refused" |
| Local query templates | `src/prompts/local_templates.py` — `render_trade_queries(trade, city, brand)`, `TRADES = (hvac, plumbing, barbershop)` | ✅ complete, deterministic, free |
| Intent buckets + allocation | `src/prompts/intent.py` — `BUCKET_ALLOCATION`, `LOCAL_BUCKET_ALLOCATION` | ✅ complete |
| CSV parse + validate | `src/prompts/csv_loader.py` — `parse_csv_files` | ✅ complete. The generated CSV goes through it unchanged |
| Run submission | `POST /audits` (multipart + `fact_sheet_id` form field) | ✅ complete. **No new run plumbing is needed** |
| Cost model | `src/pipeline/cost.py` | ✅ complete — feeds the review screen's estimate |
| Sable app chrome | `web/styles/tokens.css`, `components/{plume,notice,app-header}.tsx`, `lib/ui.ts`, `components/ui/*` | ✅ P0–P4 shipped |

**The gap is not a pipeline.** It is: a question registry, an answer→claim
mapper, a session store, a product-side query generator, and two screens.

---

## 3 · Phase I0 — Prerequisites. Nothing below works until these land.

Each of these is small and each one independently makes the whole feature inert.
Do them first, in one session, and end green.

### I0-T1 · Apply `data/schema_factsheets.sql`

```bash
python -m scripts.apply_schema data/schema_factsheets.sql
```

Until this runs, **every `/fact-sheets` call raises `StorageError` → 503.** The
queue, the worker and the gate are all inert. Verify with
`GET /fact-sheets?state=draft` returning `200 []` rather than 503.

### I0-T2 · Version allocation — the hard blocker

`build_sheet` never sets `version`; `save_fact_sheet` is a plain insert against
`unique (domain, version)`. **The second sheet for a known domain fails**, and
the worker files it as `FAILED` / `"StorageError"` — so it is both unreachable
and mislabelled. Approving an intake for a domain that already has a sheet is
exactly that second insert, so this blocks the feature's main path.

Add to `src/storage/db.py`:

```python
def next_fact_sheet_version(domain: str) -> int:
    """The next free version for a domain. 1 when none exists.

    `unique (domain, version)` means an approval racing another approval loses
    on the insert, which is the correct outcome — the caller retries and gets
    N+2. Do NOT wrap this in a read-then-write "check" that pretends to be
    atomic; the constraint is the atomicity.
    """
```

`save_fact_sheet` takes `version` explicitly. Retry once on the unique violation,
then surface a `StorageError` with a reason a human can act on.

### I0-T3 · The CLIENT-source carve-out in `verify_quotes`

§4.1's gate requires `verbatim_quote` to be a literal substring of the fetched
text at `source_url`. An owner's spoken answer has no page. Add an explicit,
documented exemption keyed on `source_kind`:

```python
# The §4.1 substring gate converts "the model said so" into "the page says so".
# A CLIENT claim has no page: the owner said so, on the record, in an intake
# session we can point at. Its quote is their raw input verbatim, and the thing
# that makes it trustworthy is provenance (source_url carries the session and
# question id), not corroboration.
#
# This is a carve-out on the SOURCE KIND, never on the claim's content, and it
# is the ONLY one. If a future layer wants an exemption, it argues for it here
# in the open rather than passing an already-verified flag through the gate.
_GATE_EXEMPT: frozenset[SourceKind] = frozenset({SourceKind.CLIENT})
```

Mirror `extract.LEAD_FORM_SOURCE_URL`'s sentinel precedent:

```python
INTAKE_SOURCE_URL_PREFIX = "intake://"   # intake://{session_id}/{question_id}
```

**Adversarial test, and never weaken it:** a claim with
`source_kind=SITE_TEXT` and a quote that is not in the source is still dropped.
A claim with `source_kind=CLIENT` passes. A claim with `source_kind=CLIENT` and
an *empty* quote still raises in `__post_init__`.

### I0-T4 · Append three `SheetSection` members

The enum is local-shaped. A product sheet has nowhere to put features,
positioning or the watch-list.

```python
class SheetSection(StrEnum):
    IDENTITY = "identity"
    CONTACT = "contact"
    HOURS = "hours"
    SERVICE_AREA = "service_area"
    LICENSING = "licensing"
    SERVICES_PRICING = "services_pricing"
    PRESENCE = "presence"
    # --- appended 2026-08-XX for the product branch. APPEND ONLY. ---
    # Declaration order is claim-ID order (`assigned_claims`), and a claim ID
    # change re-keys every cached verdict for that client. Appending is safe:
    # every existing sheet's sections sort before these, so existing IDs are
    # byte-identical. Inserting or reordering is not, ever.
    FEATURES = "features"
    POSITIONING = "positioning"
    WATCHLIST = "watchlist"
```

Add a parity test asserting that a fixture of pre-existing local claims produces
the *same* `FS-nn` ids before and after this change.

### I0-T5 · Split render order from claim-ID order

With I0-T4, a product sheet renders `presence` before `features`, which reads
wrong. Claim-ID order must not move (I0-T4), so give `to_markdown` its own order:

```python
# Claim-ID order is SheetSection's declaration order and is immutable (it is
# inside the judge cache key). READ order is a document concern and is free to
# differ. This dict is the only place they are allowed to disagree.
_RENDER_ORDER: dict[BusinessKind, tuple[SheetSection, ...]] = {
    BusinessKind.LOCAL_SERVICE: (IDENTITY, CONTACT, HOURS, SERVICE_AREA,
                                 LICENSING, SERVICES_PRICING, PRESENCE, WATCHLIST),
    BusinessKind.PRODUCT: (IDENTITY, SERVICES_PRICING, FEATURES,
                           POSITIONING, PRESENCE, WATCHLIST),
}
```

`to_fact_rows` and `to_csv` are **unchanged** — they must stay in claim-ID order,
because that is what the judge reads.

### I0-T6 · Gate

`mypy src/ && ruff check src/ && pytest tests/` green, plus a build-log entry
naming I0-T2 and I0-T3 explicitly — both change behaviour that a future reader
will otherwise assume was always this way.

---

## 4 · Phase I1 — The question registry and the assertion engine (pure Python, no UI)

New package: `src/audit/factsheet/intake/`.

```
intake/
  __init__.py        public surface
  questions.py       the registry — data, no logic
  assertions.py      answer → a complete, quotable sentence
  claims.py          answer → FactClaim[]
  plan.py            registry + prefill + business_kind → the ordered question plan
```

Keep it inert in the same sense F0 is: **no fetching, no clock, no model.**
`as_of` is passed in. That is what lets I2 and I4 land independently.

### 4.1 `questions.py` — the registry

A frozen tuple of `IntakeQuestion` dataclasses. Below is the full inventory. The
`prompt` column here is *intent*; the exact client-facing copy lives in the
design plan §4 and the two must be reconciled before I4 — the design doc's
wording wins on tone, this doc's `keys` and `assertion` win on structure.

#### Trunk — `Q-ID-*`, asked of everyone

| id | kind | section | keys | Asks for | Notes |
|---|---|---|---|---|---|
| `Q-ID-01` | `choice` | — | — | Product or local business? | **Not skippable.** Routes the whole tree. Pre-filled from the draft's `business_kind` → renders as a `confirm` |
| `Q-ID-02` | `batch_confirm` | identity | `identity_name`, `identity_website`, `identity_founded`, `identity_category` | Confirm what the crawl found | Absorbs up to 4 dimensions in one card. Anything not found is *omitted*, not asked as a blank |
| `Q-ID-03` | `longtext` | identity | `identity_what` | One factual sentence: what is it | Marketing-language guard, §4.3 |
| `Q-ID-05` | `list` | identity | `identity_aliases` | Other spellings, legal name, DBA, former name | **Not a judge claim — a matcher input.** See §4.4 |
| `Q-ID-06` | `list` | identity | `identity_not` | Who do people mix you up with | `negativeFirst`. Cheap, high value |

`Q-ID-04` and `Q-ID-07` are deliberately absent — category folds into
`Q-ID-02`'s batch, leadership folds into `Q-ID-02` for local and into
`Q-PRD-*`'s identity confirm for product. Gaps in the numbering are kept so ids
stay stable if either is ever restored.

#### Local branch — `Q-LOC-*`

| id | kind | section | keys | Asks for | Notes |
|---|---|---|---|---|---|
| `Q-LOC-00` | `choice` | — | — | Which trade | **Not skippable.** Options are `TRADES` + "something else". See §4.5 — "something else" is a real dead end today |
| `Q-LOC-01` | `batch_confirm` | contact | `contact_phone`, `contact_address`, `contact_email` | Confirm the NAP block | Highest-consequence card on the sheet |
| `Q-LOC-02` | `list` | contact | `contact_retired` | Old numbers/addresses still online | `negativeFirst`. The single most useful line in the local template |
| `Q-LOC-03` | `hours` | hours | `hours_monday` … `hours_sunday` | The week | Pre-filled from `openingHoursSpecification`. One claim per day. Closed days are the point |
| `Q-LOC-04` | `choice` | hours | `hours_after_hours`, `hours_booking` | Emergency/after-hours? Appointment or walk-in? | `negativeFirst`. "No" → `No after-hours service.` — the classic AI over-claim |
| `Q-LOC-06` | `list`+`text` | service_area | `service_area_towns`, `service_area_primary` | Towns served, + city and **full state name** | State is a `<select>`, never free text — `_ABBREVIATED_REGION_RE` rejects "CA" and the SERP vendor returns an empty surface that reads as absence |
| `Q-LOC-07` | `list` | service_area | `service_area_excluded` | Where you do **not** go | `negativeFirst`. **No producer exists today** |
| `Q-LOC-08` | `text`+`multi` | licensing | `licensing_number`, `licensing_bonded`, `licensing_insured`, `licensing_certifications` | Licence number + issuer, bonded/insured, certs | **No producer exists today.** A liability-grade dimension |
| `Q-LOC-09` | `list` | services_pricing | `services_offered` | What you do | Pre-filled from the crawl |
| `Q-LOC-10` | `list` | services_pricing | `services_excluded` | What you don't do | `negativeFirst`. The false-positive guard |
| `Q-LOC-11` | `money` | services_pricing | `pricing_callout_fee` | Call-out / diagnostic fee, or free estimates | `as_of` stamped |
| `Q-LOC-12` | `links` | presence | `presence_gbp`, `presence_yelp`, `presence_bbb`, `presence_other` | Profile links we're missing | Mostly pre-filled from `sameAs`; only the blanks render |

#### Product branch — `Q-PRD-*`

| id | kind | section | keys | Asks for | Notes |
|---|---|---|---|---|---|
| `Q-PRD-01` | `choice` | services_pricing | `pricing_model` | One-time / subscription / per-seat / usage / hardware+sub | |
| `Q-PRD-02` | `tiers` | services_pricing | `pricing_tiers` | Plans, prices, what's included | Highest-hallucination area in the whole template |
| `Q-PRD-03` | `choice`+`text` | services_pricing | `pricing_mandatory_fee` | Anything mandatory on top of the sticker price | The Oura membership. The single most demo-able claim on a product sheet |
| `Q-PRD-04` | `choice`×2 | services_pricing | `pricing_free_tier`, `pricing_trial` | Free tier? Trial? | `negativeFirst`. "No" → `There is no free tier.` |
| `Q-PRD-05` | `text`+date | features | `features_current_version`, `pricing_previous_version` | Newest version, ship date, old price if it moved | #1 staleness hotspot — training data lags |
| `Q-PRD-06` | `list` | features | `features_core` | What it actually does | Pre-filled from the crawl |
| `Q-PRD-07` | `list` | features | `features_recent` | Shipped in the last 6–12 months | Second staleness hotspot |
| `Q-PRD-08` | `list` | features | `features_excluded` | What people wrongly assume you do | `negativeFirst`. "No Android app." "Not owned by X." |
| `Q-PRD-09` | `multi`+`list` | features | `features_platforms`, `features_requirements`, `features_integrations` | Where it runs, what it needs, what it plugs into | Three fields, one card |
| `Q-PRD-11` | `text` | positioning | `positioning_icp` | Who it is actually for | |
| `Q-PRD-12` | `list` | positioning | `positioning_competitors` | The named benchmark set | **Feeds the query generator's hard constraint** — every competitor must appear in ≥1 comparison query |

#### Tail — `Q-END-*`, both branches

| id | kind | section | keys | Asks for | Notes |
|---|---|---|---|---|---|
| `Q-END-01` | `watchlist` | watchlist | `watchlist_{n}` | "Have you seen an AI say something wrong about you?" — what it said / what's true | Repeatable. Maps to template §E. This is what the sales demo opens with |
| `Q-END-02` | `longtext` | watchlist | `watchlist_other` | Anything else an AI could get wrong | Optional catch-all |

`Q-END-03` is **not a question** — it is the close screen. See design plan §5.

### 4.2 `assertions.py` — the part that actually matters

Every answer must become a **complete, single-line, quotable sentence**. The
judge quotes `FactClaim.value` verbatim; `hours_sunday: closed` is not quotable
and `after_hours: no` is not a contradiction of anything.

```python
def to_assertion(question: IntakeQuestion, key: str, answer: Answer,
                 *, as_of: str, business_name: str) -> str | None:
    """A complete assertion, or None when this key produces no claim.

    Returning None is the normal case for a skip, and it is load-bearing:
    rule 2 says a blank must produce zero claims, not an empty claim.
    """
```

Worked table — pin every one of these in tests:

| Question | Raw answer | `value` | polarity |
|---|---|---|---|
| `Q-LOC-04` | `no` | `No after-hours service.` | negative |
| `Q-LOC-04` | `yes_surcharge` | `After-hours service is available at a higher rate.` | positive |
| `Q-LOC-03` Sun | closed | `Closed Sunday.` | negative |
| `Q-LOC-03` Mon | 08:00–17:00 | `Open Monday 8:00 AM to 5:00 PM.` | positive |
| `Q-LOC-02` | `(510) 555-0100` | `(510) 555-0100 is no longer this business's phone number.` | negative |
| `Q-LOC-07` | `Marin County` | `Does not serve Marin County.` | negative |
| `Q-LOC-08` | `CSLB 123456` | `Licensed by the CSLB, licence number 123456.` | positive |
| `Q-LOC-10` | `septic work` | `Does not offer septic work.` | negative |
| `Q-LOC-11` | `0` / free | `Estimates are free; there is no call-out fee (as of 2026-08-04).` | negative |
| `Q-ID-06` | `Nahman Plumbing of San Jose` | `Not affiliated with Nahman Plumbing of San Jose.` | negative |
| `Q-PRD-04` free tier | `no` | `There is no free tier.` | negative |
| `Q-PRD-03` | `$5.99/mo membership` | `A $5.99/month membership is required in addition to the hardware price (as of 2026-08-04).` | positive |
| `Q-PRD-08` | `Android app` | `There is no Android app.` | negative |
| `Q-PRD-05` | `Ring 5, 2026-05-28` | `The current model is the Ring 5, released 2026-05-28.` | positive |

Hard constraints, enforced by a property test over the **entire registry** × a
fixture answer per kind:

- never empty, never whitespace-only
- **never contains `\n` or `\r`** — `FactClaim.__post_init__` raises, and
  `_build_fact_sheet` would otherwise deliver the tail to the judge as a second,
  keyless fact
- ends in a full stop
- volatile keys (`pricing_*`, `hours_*`, `presence_*`) carry `(as of {date})`
- a skipped answer returns `None` for every key on the card

### 4.3 The marketing-language guard

`Q-ID-03` and the free-text tails are where "the leading platform" gets in. A
soft guard, in `assertions.py`, surfaced as a UI nudge and **never as a block**:

```python
_UNFALSIFIABLE = frozenset({
    "leading", "best", "premier", "top-rated", "world-class", "trusted",
    "innovative", "cutting-edge", "#1", "number one", "award-winning",
})
```

Hit → the UI shows *"An AI can't be wrong about 'the best' — only about what you
do. Want to rephrase?"* with a **Keep it anyway** escape. Blocking the owner from
describing their own business is worse than one unfireable claim.

### 4.4 Aliases are not a claim

`Q-ID-05` produces **no `FactClaim`.** Name variants are a *matcher* input —
`docs/query-generation-plan.md` §1a's brand roster — and asserting
`identity_aliases: Also known as Acme Plumbing.` puts a non-falsifiable line in
front of the judge. Store them on the session and thread them into the query set
and the run config, not into `claims[]`. Same for the trade (`Q-LOC-00`) and the
state (`Q-LOC-06`'s region): run inputs, not ground truth.

`render.suggested_run_inputs` already exists for exactly this shape — extend it
rather than inventing a parallel channel.

### 4.5 `Q-LOC-00`'s dead end, stated plainly

`TRADES` is `("hvac", "plumbing", "barbershop")`. A local business outside those
three has **no query template**, and `assemble_run_csv` raises `AssembleError`.
Three honest options, in preference order:

1. **Fall back to the product-side generator** (§6.2) with the local bucket
   allocation. It only needs `category`, `competitors` and a city, all of which
   the intake has. This is the recommended path and it is the reason to build
   §6.2 as bucket-generic rather than product-specific.
2. Let the intake finish and mark the review screen's query pane
   *"No template for this trade — upload a CSV or ask for one."* The sheet is
   still worth having on its own.
3. Refuse at `Q-LOC-00`. Do not do this — the sheet is the valuable half.

Whichever you pick, **say so in the UI**. Silently producing a thin or wrong
query set is the failure mode that costs a real audit.

---

## 5 · Phase I2 — Session storage and the API

### 5.1 The table

New file `data/schema_factsheet_intake.sql`, applied with
`python -m scripts.apply_schema`.

```sql
create table if not exists factsheet_intake_sessions (
  id                       uuid primary key default gen_random_uuid(),
  domain                   text not null,
  fact_sheet_id            uuid references fact_sheets(id),  -- the source draft, nullable
  business_kind            text not null,
  state                    text not null default 'in_progress',
  current_question_id      text,
  answers                  jsonb not null default '{}'::jsonb,
  prefill                  jsonb not null default '{}'::jsonb,
  run_inputs               jsonb not null default '{}'::jsonb,  -- aliases, trade, region (§4.4)
  query_set                jsonb,
  csv_text                 text,
  lint                     jsonb,
  approved_fact_sheet_id   uuid references fact_sheets(id),
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  completed_at             timestamptz
);

-- One live intake per domain, for the same reason uq_factsheet_jobs_inflight
-- exists: two people starting the same sheet in the same minute is ordinary,
-- and the loser should be handed the existing session, not a second one.
create unique index if not exists uq_intake_sessions_live
  on factsheet_intake_sessions (domain)
  where state in ('in_progress', 'awaiting_review');

alter table factsheet_intake_sessions enable row level security;
```

`answers` shape: `{"Q-LOC-04": {"value": "no", "skipped": false, "raw": "No", "answered_at": "..."}}`.

**On the create-only invariant.** `CLAUDE.md` says core-data writes are
create-only and the only delete path is project deletion. A session is *working
state*, not a core-data artifact — it is mutated on every answer, exactly as
`update_audit_run_progress` mutates a run row. What it is **never** allowed to do
is get deleted: an abandoned intake is `state = 'abandoned'`, and
`delete_fact_sheets` (project deletion) must learn to cascade sessions or they
become the orphan surface `delete_audit_runs` already is for Storage blobs. Add
that to `_delete_*` in the same commit.

All access goes through `src/storage/db.py` and its `_execute` wrapper, which
owns the try/except, raises `StorageError` and logs the exception *type* only.

### 5.2 The API

Routes per §1.5, in a new `src/api/intake.py` mounted from `app.py` — `app.py`
is already 42 KB and the fact-sheet block is the last coherent thing in it.

`POST /fact-sheets/{id}/intake` builds the plan:

1. Load the draft sheet. Read `business_kind` and every existing claim.
2. Build `prefill` — a map of `key → {value, source_url, source_kind, confidence}`
   from those claims, plus `sheet.questions[]` (the §4.3 disagreements the
   extractor already recorded, which become *forced* cards: a disagreement the
   owner can settle live is the best possible use of thirty seconds).
3. Run `plan.build_plan(registry, prefill, business_kind)`:
   - drop `showIf` cards whose condition can't be met
   - collapse fully-prefilled dimensions into `batch_confirm` cards
   - **omit** cards whose only keys have no prefill *and* are optional-by-value
     if the plan exceeds 18 cards, dropping lowest-value first
     (`Q-LOC-12` → `Q-ID-05` → `Q-PRD-09` → `Q-END-02`)
4. Return `{session_id, plan, prefill, next}`.

`POST /intake/{id}/answer` is **idempotent per question id** — re-answering
overwrites. That is what makes `back` and the review screen's inline edits free.

`POST /intake/{id}/complete`:
1. `claims.from_session(session, as_of=today)` → `list[FactClaim]`
2. `verify_quotes(claims)` — CLIENT claims pass the I0-T3 carve-out, any
   surviving crawl claims are still gated
3. Merge with the source sheet's claims; **upgrade** any crawl claim the owner
   confirmed to `Verification.CLIENT_CONFIRMED`, preserving `source_kind` — §8:
   *"a signature confers client_confirmed only on the lines the owner actually
   vouched for; it does not upgrade the rest."*
4. Generate the query set + CSV (§6)
5. Lint (§6.3), cost-estimate (`src/pipeline/cost.py`)
6. `state = 'awaiting_review'`

`POST /intake/{id}/approve`:
1. **Refuse if any claim is not `client_confirmed`** — §1.7. 409 with the list.
   The UI must have already resolved this; the API is the backstop.
2. `version = next_fact_sheet_version(domain)` (I0-T2)
3. `save_fact_sheet(...)` → DRAFT
4. `activate_fact_sheet(id)` → demotes the previous active to superseded
5. Persist the query set + CSV against the new sheet id
6. `state = 'approved'`, `approved_fact_sheet_id` set

Steps 3–4 are two calls because PostgREST has no cross-table transaction; the
existing failure window is "no active sheet", never "two active sheets", and that
ordering must not be flipped.

### 5.3 The judge-cache consequence, and saying it out loud

`fact_sheet` is an input to `_verdict_key()` (`judge_cache.py:97`). **Approving a
new version re-keys every cached verdict for that client.** It is per-client, not
global — `_PROMPT_LAYOUT` is untouched, so `tests/test_judge.py`'s parity tests
are unaffected and nothing here may tempt you into `src/pipeline/judge.py`.

Re-warming is cheap via `prejudge`, with one wrinkle: the dump step refuses to
run while `JUDGE_VERIFY` or `JUDGE_CASCADE` are set, and `.env` sets
`JUDGE_VERIFY=1`. Pass `JUDGE_VERIFY=0` for the dump step only.

The review screen must state this in one plain sentence before the approve
button — see design plan §6.5.

---

## 6 · Phase I3 — Query generation and the CSV

### 6.1 Local — reuse what exists

```python
csv_text = assemble_run_csv(
    business=run_inputs["business"],          # identity_name
    website=run_inputs["website"],            # identity_website
    trade=run_inputs["trade"],                # Q-LOC-00
    city=run_inputs["city"],                  # Q-LOC-06
    region=run_inputs["region"],              # Q-LOC-06, full state name
    competitors=run_inputs["competitors"],    # src/audit/competitors.py
    category=run_inputs.get("category"),      # Q-ID-02
)
```

That is the whole local path. It already emits config + query rows and **no fact
block** — do not add one. The sheet travels by `fact_sheet_id`; a run carrying
both is refused, and the id is also what carries `fact_sheet_verification` into
`build_report`, which is what makes any accuracy finding sendable at all.

Competitors are the one input that costs money (`GET /local-entities`). Fetch
once at `complete`, store on the session, and let the review screen edit the list
without refetching.

### 6.2 Product — a template bank, not a model

There is no product query generator. **Do not write an LLM one.**
`docs/query-generation-plan.md` §1b is explicit that the methodology *forbids
LLM-originated queries* — the drafter's role is "source → draft → format, never
originate from imagination." An LLM generator would also cost money on a path
that currently costs nothing, and would be nondeterministic in a screen whose
whole job is human review.

Build `src/prompts/generate.py`:

```python
def generate_query_set(
    *, business_kind: BusinessKind, category: str, client: str,
    competitors: Sequence[str], slots: Mapping[str, Sequence[str]],
    n: int = 45, allocation: Mapping[IntentBucket, float] | None = None,
) -> QuerySet:
    """Bucket-allocated query set from a template bank. Pure, deterministic, free.

    `allocation` defaults to BUCKET_ALLOCATION for PRODUCT and
    LOCAL_BUCKET_ALLOCATION for LOCAL_SERVICE — which is also what makes this
    the fallback for a trade with no hand-written template (§4.5).
    """
```

`data/query_templates_product.json` — head and long-tail shapes per bucket, with
slots filled **only** from sheet claims:

| Bucket | Share | Shapes | Slot source |
|---|---|---|---|
| `problem_aware` | 15% | first-person pain, **never** naming category or brand | `Q-END-01` watch-list, `Q-PRD-11` ICP |
| `category` | 30% | one head (`best {category}`), the rest qualified | `Q-PRD-06` features, `Q-ID-02` category |
| `comparison` | 25% | `{client} vs {competitor}`, `best alternative to {competitor}` | `Q-PRD-12` |
| `brand` | 15% | the claims most damaging if wrong | `Q-PRD-02/03/04/05` |
| `adjacent_authority` | 15% | expertise topics, no brand named | `Q-PRD-06`, `Q-PRD-11` |

Two hard constraints from §3.3, enforced not suggested:
- **every competitor appears in ≥1 comparison query**
- **≥2 comparison queries leave the client unnamed** — these test unprompted
  surfacing, which is the measurement that matters most

Year-stamp 2–3 category queries to bait staleness against `Q-PRD-05`.

Each query carries a provenance tag (`verbatim | near_verbatim | constructed`)
so §5's "≥1/3 verbatim" check is auditable. Template-bank entries sourced from
real buyer language are tagged `near_verbatim`; pure shapes are `constructed`.

### 6.3 The lint — `docs/query-generation-plan.md` §5, automated

Runs at `complete` and on every `PATCH`. Returns a list of
`{level: "block" | "warn", message}`. **`block` disables approve.**

| Check | Level | Why |
|---|---|---|
| Counts within ±20% of allocation | warn | balance, not law |
| Exactly one valid intent per query | **block** | `csv_loader` rejects the CSV otherwise |
| No unfilled `{slot}` | **block** | a literal `{city}` reaching an engine scores as a loss on a question nobody asked |
| Every competitor in ≥1 comparison query | **block** | schema constraint |
| ≥2 comparison queries with the client unnamed | **block** | schema constraint |
| Client named only in `brand` + client-named comparisons | warn | |
| No duplicate query ids | **block** | `csv_loader` rejects |
| Near-duplicate sweep (normalized Levenshtein) | warn | |
| ≥1/3 verbatim/near-verbatim | warn | unenforceable without real sourcing |
| Region is a full state name | **block** | `_ABBREVIATED_REGION_RE` — an abbreviation returns an empty surface that reads as the brand being absent |
| `client_name` and `category` present | **block** | `REQUIRED_CONFIG_KEYS` |
| Every engine in `KNOWN_ENGINES` | **block** | |
| **The CSV round-trips through `parse_csv_files` with zero errors** | **block** | the only check that matters; the others are for a better message |

That last one is the real gate. Generate, then parse your own output with the
exact function `POST /audits` will use. If it does not come back clean, the
review screen must not offer approve.

### 6.4 Running it from S5

**No new run endpoint.** The frontend builds a `File` from `csv_text` and posts
it to the existing multipart `POST /audits` with `fact_sheet_id` set. That reuses
`parse_csv_files`, the preview panels, the cost guard and every validation path
already in production. A `POST /audits/from-sheet/{id}` convenience route is
optional and should only be added if the client-side `File` construction proves
awkward — not before.

---

## 7 · Phase I4/I5/I6 — The frontend

Presentation is the design plan's job. This section is the data layer and the
non-negotiables.

### 7.1 `web/lib/api.ts`

Add typed clients for every §1.5 route, in the file's existing style: one
function per endpoint, `authHeaders()`, a `catch` that rewrites the 409s into
sentences a person can act on.

```ts
// 409 on approve means an unconfirmed claim survived §1.7. Name the claim.
if (res.status === 409) throw new Error(
  `${body.unconfirmed.length} claims still need confirming before this sheet can be approved.`
);
```

Types mirror the Python dataclasses exactly — `IntakeQuestion`, `IntakeSession`,
`ReviewPayload`, `LintItem`. They already do this for `FactSheetState` and
`FactSheetVerification`; follow that.

### 7.2 Routes and files

| File | Action |
|---|---|
| `web/app/fact-sheets/page.tsx` | Rework tabs to **Needs review / Active**; drop rejected + superseded tabs; add "Start intake" / "Continue" / "Review" row actions |
| `web/app/fact-sheets/[id]/intake/page.tsx` | **new** — the chat |
| `web/app/fact-sheets/[id]/review/page.tsx` | **new** — sheet + queries + CSV |
| `web/components/intake/*.tsx` | **new** — one component per `AnswerKind`, plus the transcript and progress rail |
| `web/components/intake/motion.css` | **new** — the only new stylesheet; see design plan §8 |
| `web/app/page.tsx` | add the "Ready to run" strip above the dropzone |
| `web/lib/api.ts` | the clients above |

### 7.3 Non-negotiables inherited from the Sable spec

- **No new colour.** `destructive`, `success` and `warning` do not exist in
  `tailwind.config.ts` and `npm run build` fails on them. Lint levels use
  `<Notice tone="problem" | "info" | "done">` — a 3px navy-family left rule, an
  icon and a sentence.
- **Every distinction carries a glyph or a label as well as a fill.** A
  single-hue palette does not survive a dashboard otherwise.
- **Sky (`#7FA6D9`) appears at most once per page and only inside `.on-navy`.**
  The header plume already spends it. Do not put Sky in the progress rail.
- **Cormorant never below 32px** except the wordmark and hero numbers. The
  question text is Libre Franklin.
- **Contrast:** Harbour on white = 4.68 ✅; Harbour on Paper = 4.14 ❌. Inside a
  card, `text-harbour`; on the Paper ground, `text-[color:var(--ink-secondary)]`.
- Form controls use `INPUT_CLS` / `FIELD_LABEL_CLS` / `FIELD_HINT_CLS` from
  `web/lib/ui.ts`. Do not inline a fifth set of input classes.
- Autosave every answer. A `POST /answer` per card is cheap and a browser refresh
  mid-intake must not cost the owner anything.

---

## 8 · Tests

Add `tests/test_factsheet_intake.py`. The ones that must exist:

**Registry properties** (parametrized over the whole registry)
- every question id is unique and matches `Q-(ID|LOC|PRD|END)-\d\d`
- every `section` is a real `SheetSection`; every `key` is non-empty
- every `showIf.questionId` refers to a question earlier in the plan
- a plan for either `BusinessKind` never exceeds 18 cards

**Assertions** (parametrized over registry × a fixture answer per kind)
- non-empty, no `\n`/`\r`, ends in a full stop
- `negativeFirst` questions answered "no" yield `Polarity.NEGATIVE`
- volatile keys carry `(as of …)`
- **a skipped answer yields zero claims for every key on the card** — rule 2

**The quote gate** (adversarial; never weaken)
- `SITE_TEXT` claim whose quote is absent from source → dropped, one log line
- `CLIENT` claim → passes
- `CLIENT` claim with an empty quote → `ValueError` from `__post_init__`

**Tier**
- approve with one `public_source_only` claim → 409, claim named
- approve after confirming it → `verification_tier == CLIENT_CONFIRMED`
- an unconfirmed crawl claim that is *dropped* also reaches CLIENT_CONFIRMED

**Round-trip** (the F0 shape, extended)
- answers → claims → `to_fact_rows` → `parse_csv_files` → `_build_fact_sheet`
  gives the expected string
- generated CSV contains **no `fact` block**
- generated CSV parses with `errors == []`

**Versioning**
- two approvals for one domain → v1 then v2; v1 becomes `superseded`
- a domain with an existing sheet no longer produces the `FAILED`/`StorageError`
  path (the I0-T2 regression)

**Claim-ID stability** (the I0-T4 regression)
- a fixture of pre-existing local claims produces byte-identical `FS-nn` ids
  before and after the three appended sections

**Query lint**
- a set missing a competitor from comparison → `block`
- a set with `{city}` surviving → `block`
- `region="CA"` → `block` with the full-name message

Every test in this file makes **zero engine calls and costs nothing.** Fake the
`db` module and the competitor fetch.

---

## 9 · Build sequence

| # | Phase | Depends on | Done when |
|---|---|---|---|
| **I0** | Prerequisites (§3) | — | Schema applied; `next_fact_sheet_version` exists; CLIENT gate carve-out tested; three sections appended with a claim-ID parity test; repo gate green |
| **I1** | Registry + assertions + claims (§4) | I0 | Every §8 registry/assertion/round-trip test passes. No UI, no API, no network |
| **I2** | Session store + API (§5) | I1 | A session can be created, answered end to end and completed via `curl`. Approve writes v2 and demotes v1 |
| **I3** | Query generation + lint (§6) | I2 | Local path produces a CSV that `parse_csv_files` accepts with zero errors; product path satisfies both comparison constraints |
| **I4** | The intake screen | I2 | An owner can complete an intake in a browser; refresh mid-flow loses nothing |
| **I5** | The review screen | I3, I4 | Claims and queries editable; lint blocks approve; tier meter reaches client-confirmed; approve lands an active sheet |
| **I6** | Active tab + Home strip | I5 | An approved sheet appears on `/` and one click starts a real run against it |
| **I7** | QA | all | Design plan §12 checklist; `npm run report-pdf` still in the 13–18 page band |

**Ship I0–I3 alone if nothing else gets built.** They make the sheet
client-confirmable through `curl` and unblock HIGH/CRITICAL flags, which is the
value; the screens are how it stops being Josh's job.

---

## 10 · Decisions still open

1. **`Q-LOC-00`'s "something else."** §4.5 recommends falling back to the
   bucket-generic generator. Confirm before I3 — it changes whether §6.2 is built
   product-specific or generic.
2. **Does the watch-list (`Q-END-01`) produce claims, or only aim the reverse
   pass?** As claims it is the most demo-able section of the sheet. As input to
   §7's reverse pass it is cheaper and never wrong. Recommendation: **both** —
   store as claims in `WATCHLIST`, and thread into the reverse pass when F5
   lands. Decide before I1 because it sets the section's `keys`.
3. **`SheetStatus` (`draft | client_reviewed | signed`) has no database column**
   and every loaded sheet reports `draft`. A completed intake is precisely
   `client_reviewed`, and it is what F4.5's "Brand Fact Sheet v1.0" export is
   defined against. Adding the column is ~10 lines and this is the first feature
   with a real reason to. Decide before I2.
4. **Does anything notify the owner** when their sheet is approved, or is the
   intake a one-way form? Out of scope here; it changes whether the session needs
   a contact reference (and if it does, note that the cross-project worker is
   deliberately PII-free and this must not be the thing that breaks that).
