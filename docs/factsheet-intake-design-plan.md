# Fact-Sheet Chat Intake — Design Plan (for Claude Design)

*A conversational intake that turns a business owner's five minutes into the only
document in the system anyone has actually vouched for — then hands them a
reviewable set of queries and a run they can start with one click.*

**Companion document:** `docs/factsheet-intake-agent-plan.md` (for the coding agent).
**§1 of both documents is byte-identical.** It is the seam. If you change a
question id, a state name, a route or a field name, change it in both.

**Read before designing:** `docs/ui-redesign-sable-spec.md` (the app chrome you
are designing inside — palette, type, motion-free austerity, the no-alert-hue
rule), `web/styles/tokens.css`, `web/components/{plume,notice}.tsx`,
`web/lib/ui.ts`. **Load `.claude/skills/audit-packaging/SKILL.md` before
designing the review screen** — a client reads it.

**The gate:** `cd web && npm run typecheck && npm run build` green, plus the §12
checklist. No Python.

---

## 0 · The one decision, up front

**This is a chat in feel and a form in structure.** It reads conversational —
one question at a time, a bot voice, a choreographed handoff between cards — but
it is not a transcript. A real chat log grows downward, buries the input, and by
question twelve the owner is scrolling through their own answers to find the
field. Instead:

**The current question owns the viewport. Answered questions lift, shrink and
settle into a transcript above it that stays collapsed until touched.**

You get the warmth of a conversation and the legibility of a form. The animation
between the two is the product's signature moment and the reason this is worth
building instead of shipping a twenty-field page.

**The second decision, and it is the honest one:** the intake is not a data-entry
chore we are dressing up. Every answer measurably changes what the product can
say — see §1.7. The design's job is to make that visible, one card at a time, so
that five minutes feels like an investment rather than a toll.

---

## 1 · The shared contract

> **This section is identical in `docs/factsheet-intake-agent-plan.md`. Keep it that way.**

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

## 2 · Design language — what you inherit, and the one thing you must invent

### 2.1 Inherited, and locked

From `web/styles/tokens.css` and the Sable identity guide. **No colour outside
this table exists.** `npm run build` fails on `destructive`, `success`,
`warning`, `indigo`, `amber`.

| Token | Hex | Where it is legal |
|---|---|---|
| Berkeley Navy | `#0E2340` | anywhere — ink, fills, the tallest plume |
| Sable Blue | `#12325C` | anywhere — links, active, focus ring |
| Harbour | `#697585` | anywhere, but **on white only** (see contrast below) |
| Mist | `#B2B7BC` | rules, the faintest plume — **never text** |
| Paper | `#F2F1EC` | the page ground |
| White | `#FFFFFF` | cards |
| **Sky** | `#7FA6D9` | **on navy only, at most once per page.** The header plume already spends it. Not available to you. |

Derived surfaces are navy at alpha, never a separate grey:
`--rule` 12% · `--rule-soft` 7% · `--hover` 4% · `--selected` 6% ·
`--ink-secondary` 70%.

**Contrast, measured not assumed.** Harbour on white = 4.68 ✅. Harbour on Paper
= **4.14 ❌**. The rule: *Harbour inside a card,
`text-[color:var(--ink-secondary)]` outside one.* The intake card is white, so
helper text inside it is Harbour; the progress rail sits on Paper, so its labels
are `--ink-secondary`.

**Type.** Libre Franklin for everything the owner reads. Cormorant Garamond only
at 32px+ — in this feature that means the close screen's hero number and nothing
else. **The question text is Libre Franklin.** A 20px serif question would break
the guide and read as a wedding invitation.

| Element | Spec |
|---|---|
| Question prompt | Libre Franklin 20/1.35, weight 400, navy |
| Helper under it | 13/1.55, `--ink-secondary` |
| Answer input | `INPUT_CLS` from `web/lib/ui.ts` — h-9, radius-md, 13px |
| Committed answer (the assertion) | 15/1.5, weight 500, navy |
| Transcript entry | 12/1.4, `--ink-secondary`, one line, ellipsized |
| Eyebrow (`.label`) | 10px / 600 / 0.36em / uppercase / Harbour |
| Card | white, `1px solid var(--rule)`, radius 14px, **no shadow** |
| Buttons | pill; primary `bg-navy text-white`, outline `border-navy/25`, ghost |
| Hero button (one per screen) | uppercase, 11px, `tracking-[0.14em]`, px-6 |

**No alert hue.** Warnings, errors and blocks use `<Notice tone="problem" |
"info" | "done">` — a 3px navy-family left rule, a Lucide icon, and a plain
sentence. The icon and the rule weight are load-bearing, not decoration.

**Every distinction carries a glyph or a label as well as a fill.** This is the
rule that lets a one-hue palette survive a screen with states in it.

### 2.2 The one thing you must invent: motion

**The redesign artifacts contain zero authored motion** — no keyframes, no
transitions, no easing tokens, in any of the five mockups. The only animation
anywhere in the bundle belongs to the artifact runtime, not to Sable. So the
motion system for this feature is being designed here, from nothing, and it sets
the precedent for the rest of the app. Design it as tightly as the palette.

`framer-motion` is **not installed** and should not be. Everything below is CSS
transitions and `@keyframes` in one new file, `web/components/intake/motion.css`.
The choreography needs two elements moving in opposite directions with
overlapping timing — CSS does that natively, and the restraint is the point.

#### Motion tokens — add to `motion.css`, not to `tokens.css`

`tokens.css` is the app's palette contract and should not grow a motion section
until a second feature needs one.

```css
:root {
  /* Entrances and settles. Fast out of the gate, long tail — the curve that
   * reads as "arriving" rather than "sliding". */
  --ease-arrive: cubic-bezier(0.25, 1, 0.5, 1);
  /* Departures and moves between two known positions. Symmetric. */
  --ease-move:   cubic-bezier(0.45, 0, 0.55, 1);

  --dur-tap:   120ms;  /* hover, focus, chip select — must feel instant */
  --dur-hand:  220ms;  /* the handoff's individual legs */
  --dur-settle:420ms;  /* the full handoff, start to finish */
}
```

**The ceiling is 420ms.** Fifteen questions × a half-second transition is seven
seconds of the owner watching furniture move. Anything slower and the intake
stops feeling responsive and starts feeling like fifteen loading screens.

#### The handoff — the signature transition

Three overlapping phases. Total 420ms.

| Phase | Window | What moves |
|---|---|---|
| **1 · Commit** | 0–120ms | The input locks: border goes `--blue` → `--navy`, a 1px hairline sweeps left→right beneath it (`scaleX(0)→1`, `transform-origin: left`). The raw input is replaced in place by **the assertion sentence** at 15/500. |
| **2 · Ascend** | 80–300ms | The answered card translates up by its own height + 16px, scales to `0.94`, fades to `opacity: 0.5`, and lands as a one-line transcript entry. The transcript above shifts up by the delta in the same beat. `--ease-move`. |
| **3 · Arrive** | 200–420ms | The next question fades in from `translateY(14px)` / `opacity: 0` with `--ease-arrive`. Its input's focus ring appears **last, at 380ms**, so the eye reads the question before it finds the field. |

Phases 2 and 3 overlap by 100ms deliberately — the two cards cross, which is what
makes it read as a handoff and not as a page change.

```css
@keyframes intake-ascend {
  from { transform: translateY(0)      scale(1);    opacity: 1;   }
  to   { transform: translateY(-100%)  scale(0.94); opacity: 0.5; }
}
@keyframes intake-arrive {
  from { transform: translateY(14px); opacity: 0; }
  to   { transform: translateY(0);    opacity: 1; }
}
@keyframes intake-commit-rule {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}
```

#### Reduced motion — required, not optional

```css
@media (prefers-reduced-motion: reduce) {
  .intake-card, .intake-transcript-entry, .intake-progress-plume {
    animation: none !important;
    transition-duration: 1ms !important;
  }
}
```

With motion reduced the handoff becomes an instant swap. The transcript still
grows, the progress still advances, the assertion still renders — **nothing
informational is carried by motion alone.** That is the test: turn animation off
and the intake must still be completely legible.

#### The progress rail — the plume, used honestly

A horizontal row of small marks above the card, one per question in the plan.
Answered marks are Navy; the current one is Harbour; unanswered are Mist.
Skipped answers get a Mist mark with a 1px navy ring — visibly *addressed* rather
than *pending*, since a skip is a legitimate answer under rule 2.

Use **only the tallest plume's silhouette**, at 8px, never three-up. The identity
guide's own degradation ladder says below 16px you use the tallest plume alone,
so this is compliant by the guide's rule and it stops the rail reading as a row
of tiny logos. **It is not the mark and must not be mistaken for it.**

The current mark breathes: `opacity 0.55 → 1`, 1800ms, `ease-in-out`, alternate.
That is the only looping animation in the feature. Under reduced motion it is a
static ring instead.

Under the rail, one line at 10px `.label`: `QUESTION 6 OF 14 · ABOUT 3 MIN LEFT`.
Estimate from a measured median per `AnswerKind`, not from a constant — a `hours`
card is not a `choice` card.

#### The thinking indicator — and when not to use it

Three 6px plume silhouettes, staggered opacity pulse, 900ms cycle.

**Only show it when there is real latency.** The pre-fill lookup on open, the
competitor fetch, and query generation at `complete` are real. Between two cards
there is nothing to wait for, and manufacturing a delay to make a bot feel
"alive" is a tax the owner pays fifteen times. If a real wait resolves under
150ms, do not show the indicator at all — a flash is worse than nothing.

---

## 3 · S2 — the intake screen

### 3.1 Layout

```
┌─ app header (navy, 56px, unchanged) ──────────────────────────────┐
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│         ●●●●●○○○○○○○○○      ← progress rail, plume marks          │
│         QUESTION 6 OF 14 · ABOUT 3 MIN LEFT                       │
│                                                                   │
│    ┌───────────────────────────────────────────────────┐          │
│    │  Q-LOC-02 · You said (510) 555-0100 is current.   │ ← transcript
│    │  Q-LOC-01 · Confirmed 3 facts                     │   collapsed,
│    │  ⌄ show 4 earlier                                 │   max 3 rows
│    └───────────────────────────────────────────────────┘          │
│                                                                   │
│    ┌───────────────────────────────────────────────────┐          │
│    │  HOURS                                            │ ← eyebrow │
│    │                                                   │          │
│    │  Which days are you closed?                       │ ← 20px    │
│    │  Be blunt about it — "closed Sunday" is what      │ ← 13px    │
│    │  lets us catch an AI telling someone otherwise.   │          │
│    │                                                   │          │
│    │  [ the input, per AnswerKind ]                    │          │
│    │                                                   │          │
│    │  ── This will read: "Closed Sunday." ─────────    │ ← rule 4  │
│    │                                                   │          │
│    │  [ Continue ]              Skip this one          │          │
│    └───────────────────────────────────────────────────┘          │
│                                                                   │
│    I found this on your contact page ↗                            │ ← provenance
└───────────────────────────────────────────────────────────────────┘
```

Card is `max-w-[640px]`, centred, white, radius 14, `1px solid var(--rule)`, no
shadow, `p-8`. The page keeps the layout's `mx-auto max-w-6xl px-6 py-8` — the
card is narrower than the shell on purpose; a 640px measure is what makes a
20px question read as a question and not a headline.

The transcript sits **above** the card, right-aligned to it, capped at 3 visible
rows with a `⌄ show N earlier` disclosure. Rows are 12px `--ink-secondary`,
one line, ellipsized, and clicking one jumps back to that card (which calls
`POST /back` repeatedly, or a direct jump — see agent plan §5.2; answers are
idempotent so either is safe).

The provenance line under the card ("I found this on your contact page ↗") only
renders when `prefillSourceUrl` is set. It is a real link, opens in a new tab,
and it is what makes a confirm card checkable rather than a trust exercise.

### 3.2 The commit affordance

- **Enter commits** on `text`, `money`, `choice` (with a selection), `confirm`.
- **⌘/Ctrl + Enter commits** on `longtext`, `list`, `tiers`, `watchlist` — a
  bare Enter adds a line or a chip there.
- **1–4 select** on `choice` and `batch_confirm`, with the numeral shown at 10px
  Mist inside each option's left edge. This is the single biggest speed win for
  anyone who does more than one of these.
- **Esc** blurs; it does not skip. Skipping is a decision and needs a click.
- **Skip is always visible** on skippable cards, as a ghost button to the right
  of Continue, never hidden in an overflow. Rule 2 means a skip is a *correct*
  answer, and burying it produces guesses, which is the one outcome that costs a
  false accusation later.

### 3.3 Every `AnswerKind`, specified

| Kind | Control | Notes |
|---|---|---|
| `choice` | 2–4 stacked pill rows, full width, `border-navy/20`; selected = `bg-navy text-white` + `Check` glyph | Numeral hint at left. Never a native `<select>` — this is the most-used kind and it should feel tapped, not chosen |
| `multi` | Same rows, multi-select, plus an "Add your own" chip that reveals an inline input | |
| `confirm` | The found value at 15/500 navy in a `--selected` tinted block, with the source line beneath. Two buttons: **That's right** (navy) / **Fix it** (outline) | "Fix it" reveals `INPUT_CLS` pre-filled with the found value, cursor at end |
| `batch_confirm` | N rows, each `label · value · Check`. All start checked. Tapping a row unchecks it and reveals an inline input | Header copy: *"Tap anything that's wrong."* Unchecking is the interaction, which is why all start checked — the common case is one tap on Continue |
| `text` | `INPUT_CLS` | Character budget hint at 11px when there is a real one |
| `longtext` | `INPUT_CLS` as a 3-row textarea | Marketing-language nudge (§3.5) fires here |
| `list` | Chip input: type, Enter, chip appears; Backspace on empty removes the last | Pre-filled chips render Harbour-outlined with an × ; owner-added chips render navy-filled. The difference is visible provenance |
| `hours` | 7 rows: day label · [Open ▾ time range] / [Closed] toggle | Pre-filled from JSON-LD. **Closed is a first-class toggle, never an empty time field** — the negative is the valuable answer here |
| `money` | `INPUT_CLS` with a `$` prefix, plus a **Free / none** pill that zeroes it | The "as of {today}" stamp renders as static 11px text, not a field |
| `tiers` | Repeatable 3-column rows (name / price / includes) + **Add a plan** | Max 6 rows before it needs a scroll; if a product has more, that is a call, not a form |
| `links` | Only the *missing* platforms render as labelled URL fields. Found ones render as confirmed chips with the platform name | Keeps a 6-field card down to one or two fields in the common case |
| `watchlist` | Repeatable pair: *"What did it say?"* / *"What's actually true?"* + **Add another** | Starts with one empty pair. This card is allowed to be the longest one |

### 3.4 The assertion preview — rule 4, made concrete

Beneath every input, above the buttons, separated by a `--rule-soft` hairline:

> `This will read: "Closed Sunday."`

Live, updating as they type, at 13px with the sentence in navy 500 and the
`This will read:` in `--ink-secondary`. On a `batch_confirm` it lists one line
per confirmed fact and collapses past three with `+2 more`.

This is the most important element on the screen. It is what makes the intake
teach rather than extract: the owner watches a "no" become *"No after-hours
service."* and understands, without being told, that they are writing the
sentence an AI will be measured against. Do not tuck it into a tooltip and do not
render it after commit only.

When an answer produces **no** claim — a skip, or an alias card — the line reads
`Nothing will be checked on this.` in `--ink-secondary`. Silence needs a label
too, or a skip feels like a failure instead of a safe default.

### 3.5 The marketing-language nudge

`Q-ID-03` and the free-text tails. On a hit, a `<Notice tone="info">` slides in
beneath the field:

> *An AI can't be wrong about "the best" — only about what you actually do. Want
> to rephrase?*  **Rephrase** · **Keep it anyway**

Never blocks. Never a red field. A business owner describing their own business
in their own words and being refused is a worse outcome than one claim that can
never fire.

### 3.6 The opening screen (before `Q-ID-01`)

Not a question. One card:

> **`ABOUT YOUR BUSINESS`** *(eyebrow)*
>
> **We pulled some facts off albertnahmanplumbing.com. Let's check them.**
>
> Fourteen questions, about six minutes. Most are just "is this right?"
>
> Anything you're not sure about, hit **Skip** — we'd rather leave a blank than
> guess. A blank is never wrong; a guess can be.
>
> `[ Start ]`

The mark renders at 34px, tone `paper`, above the eyebrow. This is the one place
in the feature the logo appears at size, and it is the same move the run page's
empty state already makes.

### 3.7 The close screen (after `Q-END-02`)

Not a question. The payoff, and the only place Cormorant is legal here.

> **`DONE`**
>
> **14** *(Cormorant 300, 56px, navy)*
> facts you've confirmed
>
> From now on, if ChatGPT, Gemini, Claude or Perplexity says something that
> contradicts one of these, we'll flag it — including the serious ones.
>
> *[thinking indicator] Writing your questions…*

Hold for the real duration of query generation, then **auto-navigate to S3.**
No button. The user asked for the intake to hand off to review automatically and
they are right: a button here is a button that says "yes, I would like the thing
I just spent six minutes earning."

If generation fails, the screen resolves to a `<Notice tone="problem">` with the
reason and a **Go to review anyway** button — the sheet is the valuable half and
must never be held hostage to the query set (see agent plan §4.5).

### 3.8 Empty, error and resumed states

| State | Treatment |
|---|---|
| Resumed mid-intake | Open on the last unanswered card with the transcript pre-populated. A `<Notice tone="info">` above it: *"Picking up where you left off — 6 of 14 done."* Dismissible, once |
| Network error on commit | The card stays, the button shows a spinner, then a `<Notice tone="problem">` with **Try again**. **Never lose the typed answer** — it lives in component state until the POST resolves |
| Nothing was pre-filled | The batch-confirm cards simply don't appear; the plan is longer and the copy changes from "is this right?" to "what is it?". Do not render an empty confirm card |
| Sheet already has a live session | The queue row's action reads **Continue** and routes into the existing session. Never offer to start a second one |

---

## 4 · The script — exact copy, every card

Tone: a competent person who has done this before, is not going to waste your
time, and tells you why they're asking when the why isn't obvious. Sentence case.
No exclamation marks. No emoji. Second person. Short.

`{brand}`, `{domain}`, `{city}` are substituted live.

### 4.1 Trunk — everyone

**`Q-ID-01` · business kind** *(not skippable)*
> Which one is {brand}?
> *(helper)* This changes what we ask about — and what we check for.
> `[ Something people buy or subscribe to online ]` `[ A local business people call or visit ]`
>
> *Pre-filled variant:* Looks like {brand} is a local business people call or visit. Right?

**`Q-ID-02` · identity confirm** *(batch)*
> Quick check — tap anything that's wrong.
> *(rows)* Name · Website · In business since · What you'd call it

**`Q-ID-03` · one line**
> In one sentence, what does {brand} do?
> *(helper)* Plain and factual. "Family-owned plumbing contractor serving the East Bay since 1998" — not "the most trusted plumber in town."

**`Q-ID-05` · aliases**
> Any other ways people write your name?
> *(helper)* Misspellings, your legal name, "& Sons" vs "and Sons", an old name. We use these to spot a mention we'd otherwise miss — they're not fact-checked.
> *(placeholder)* Type a name and press Enter

**`Q-ID-06` · confused with** *(negativeFirst)*
> Is there another business people mix you up with?
> *(helper)* A same-name shop in another town, a franchise you left, a competitor people confuse you with. This is one of the things AI gets wrong most often.

### 4.2 Local branch

**`Q-LOC-00` · trade** *(not skippable)*
> What kind of work is it?
> `[ Plumbing ]` `[ HVAC ]` `[ Barbershop ]` `[ Something else ]`

**`Q-LOC-01` · contact confirm** *(batch)*
> This is the most important card here — tap anything that's wrong.
> *(helper)* If an AI gives someone the wrong number, that's a job you never hear about.
> *(rows)* Phone · Address · Email

**`Q-LOC-02` · retired contact** *(negativeFirst)*
> Any old number or address of yours still floating around online?
> *(helper)* An old listing, a previous location, a disconnected line. Telling us lets us flag an AI still handing it out.

**`Q-LOC-03` · hours**
> When are you open?
> *(helper)* Be exact about the days you're **closed** — that's what catches an AI saying you're open seven days.

**`Q-LOC-04` · after-hours** *(negativeFirst)*
> Do you take emergency or after-hours calls?
> `[ No ]` `[ Yes, same rate ]` `[ Yes, costs more ]`
> *(secondary)* Appointment only, walk-ins welcome, or both?
> *(helper)* "No" is worth saying out loud — AIs invent 24/7 emergency service constantly.

**`Q-LOC-06` · service area**
> Which towns do you actually serve?
> *(secondary)* Home city · State *(select)*
> *(helper)* We need the state spelled out — "California", not "CA".

**`Q-LOC-07` · boundary** *(negativeFirst)*
> Where do you **not** go?
> *(helper)* Without this, nobody can catch an AI promising a customer in the next county over that you'll come out.

**`Q-LOC-08` · licensing**
> Licence number, and who issued it?
> *(placeholder)* CSLB 123456
> *(secondary)* Bonded · Insured · Any certifications
> *(helper)* An AI claiming a licence you don't hold is a real liability. So is one denying the licence you do hold.

**`Q-LOC-09` · services offered**
> What do you actually do?

**`Q-LOC-10` · services not offered** *(negativeFirst)*
> Anything people ask for that you don't do?
> *(helper)* "No septic work." "No commercial jobs." These stop an AI volunteering you for work you don't take.

**`Q-LOC-11` · call-out fee**
> What's the call-out or diagnostic fee?
> `[ Free estimates ]` or `$ ___`

**`Q-LOC-12` · presence**
> Anything we're missing?
> *(helper)* We found your Google and Yelp pages. Paste any others.

### 4.3 Product branch

**`Q-PRD-01` · billing**
> How do people pay for {brand}?
> `[ One-time purchase ]` `[ Subscription ]` `[ Per seat ]` `[ Usage-based ]` `[ Hardware plus a subscription ]`

**`Q-PRD-02` · plans**
> What are the plans, and what do they cost?
> *(helper)* Prices are the single most-hallucinated thing about any product. Exact numbers, today's.

**`Q-PRD-03` · mandatory fee**
> Is there anything people have to pay on top of that?
> *(helper)* A required membership, an activation fee, a mandatory add-on. AIs quote the sticker price and miss this constantly — it's usually the finding that lands hardest.

**`Q-PRD-04` · free tier & trial** *(negativeFirst)*
> Is there a free tier?  `[ No ]` `[ Yes — limits: ___ ]`
> Is there a free trial? `[ No ]` `[ Yes — ___ days ]`

**`Q-PRD-05` · current version**
> What's the newest version, and when did it ship?
> *(secondary)* Did the price change with it? What was the old one?
> *(helper)* AI training data lags by months. This is the fastest way to catch an AI still describing last year's product.

**`Q-PRD-06` · core features**
> What does it actually do?

**`Q-PRD-07` · recently shipped**
> Anything you've shipped in the last six to twelve months?

**`Q-PRD-08` · do not do** *(negativeFirst)*
> What do people wrongly assume you do?
> *(helper)* "No Android app yet." "Not owned by {competitor}." "No offline mode." These are the guardrails — without them an invented feature isn't catchable.

**`Q-PRD-09` · platforms**
> Where does it run, what does it need, and what does it plug into?

**`Q-PRD-11` · ICP**
> Who is it actually for?

**`Q-PRD-12` · competitors**
> Who do you actually compete with?
> *(helper)* We'll ask the AIs about each of these by name, so this list decides what gets measured.

### 4.4 Tail — everyone

**`Q-END-01` · watch-list**
> Have you ever seen ChatGPT or Google's AI say something wrong about you?
> *(pair)* What did it say? / What's actually true?
> *(helper)* Anything you've already caught. This is usually the first thing we go and check.

**`Q-END-02` · anything else**
> Anything else an AI could get wrong about you?
> *(helper)* Last one. Skip it if nothing comes to mind.

---

## 5 · S1 — the queue

`/fact-sheets`, two tabs: **Needs review** · **Active**.

Each row is a card:

```
┌────────────────────────────────────────────────────────────────┐
│  Albert Nahman Plumbing                    ● 6 of 14 answered  │
│  albertnahmanplumbing.com · v2 · 3 days ago                    │
│  ⚠ 2 sources disagreed — we'll ask                             │
│                                          [ Continue ]  ⋯       │
└────────────────────────────────────────────────────────────────┘
```

Row action by state, one primary button, never two:

| Row state | Button | Secondary |
|---|---|---|
| Crawl draft, no session | **Start intake** | — |
| `in_progress` | **Continue** | Progress shown as `6 of 14` + a plume mini-rail |
| `awaiting_review` | **Review** | Lint block count if any |

**Age is visible and it matters.** A draft older than 30 days shows
`Facts are 34 days old` in `--ink-secondary` — that is `SHELF_LIFE_DAYS` from
`teaser/src/freshness.ts` and reusing it means one staleness rule, not two.

Because nothing is ever rejected, this queue only grows. It needs, from day one:
sort (newest · oldest · most complete), a domain search field, and a count in the
tab label. Do not ship it as an unsorted list — that is the design failure this
tab is most likely to have in six months.

The `⋯` overflow carries exactly one destructive item, **Discard sheet**, behind
a typed confirmation. It writes the existing `rejected` state, which has no tab
and no badge. See §6.3.

---

## 6 · S3 — the review screen

The most important screen in the feature. Two panes on desktop, stacked on
mobile, with a fixed action bar.

```
┌─ REVIEW ─ Albert Nahman Plumbing v2 ──────────────────────────────┐
│                                                                   │
│  ┌─ THE SHEET ───────────────┐  ┌─ THE QUESTIONS ──────────────┐  │
│  │ ▸ Identity          4     │  │  29 questions · 5 assistants │  │
│  │ ▸ Contact           3     │  │  3 runs each · 435 calls     │  │
│  │ ▸ Hours             7     │  │  about $14                   │  │
│  │ ▸ Service area      5     │  │                              │  │
│  │ ▸ Licensing         3     │  │  [intent] [id] [text]  …     │  │
│  │ ▸ Services          6     │  │  ⋯ 29 rows, editable         │  │
│  │                           │  │                              │  │
│  │ FS-14  Closed Sunday.     │  │  ✓ every competitor covered  │  │
│  │ "Sun: Closed"  · you      │  │  ✓ 4 unnamed comparisons     │  │
│  │                           │  │  ⚠ 2 near-duplicates         │  │
│  └───────────────────────────┘  │  [ Download CSV ]            │  │
│                                 └──────────────────────────────┘  │
│  ─────────────────────────────────────────────────────────────    │
│  ✓ All 28 facts confirmed by you — this sheet can flag anything   │
│                                              [ APPROVE & ACTIVATE ]│
└───────────────────────────────────────────────────────────────────┘
```

### 6.1 The sheet pane

Claims grouped by section, sections collapsible, count in each header. Each claim
row shows, in this order:

1. The **assertion** at 14/500 navy — the sentence, not the key
2. The **verbatim quote** as a `<blockquote>` at 12px Harbour with a left rule
3. A footer at 11px: `FS-14 · you confirmed this · 2026-08-04` — or, for a claim
   that came from the site, `FS-09 · from your contact page ↗ · 2026-08-04`
4. On hover: **Edit** (inline, becomes an input) and **Drop** (outline, one click,
   undoable via a 5-second `<Notice tone="done">` with Undo)

Editing a claim rewrites its value and marks it `client_confirmed`. Dropping it
removes it from the outgoing sheet. Both are the per-claim controls the current
queue screen conspicuously lacks — today a reviewer who spots one bad claim in
nine has to reject all nine.

### 6.2 The tier meter — §1.7 made visible

The bar above the action buttons, and the thing that most changes what this
product can do:

**When everything is confirmed:**
> ✓ **All 28 facts confirmed by you.** This sheet can flag anything, at any
> severity.

**When something isn't:**
> ⚠ **3 facts nobody has confirmed.** Until they're handled, this sheet can only
> flag low and medium issues — the serious ones stay hidden.
> `[ Review the 3 ]`

Clicking scrolls the sheet pane to the first unconfirmed claim and filters to
them. Each gets two buttons and no third: **That's right** (→ confirmed) or
**Drop it**. `APPROVE` is disabled until the count reaches zero, with the reason
in the button's `title` and as a `<Notice tone="problem">` above it — never a
disabled button with no explanation.

Use the plume rail here too: a 3-mark rail where mark 1 = "one source",
mark 2 = "two sources agree", mark 3 = "you confirmed it". It is the same visual
grammar as the intake progress and it makes an abstract tier concrete.

### 6.3 What happened to Reject

The database still has `rejected`, and it should: a rejection is a recorded
verdict that tunes the extractor, `activate_fact_sheet` refuses to promote one,
and existing rows exist. What goes away is **the tab, the badge and the button.**

The new model is simpler and matches how people actually work: *if it isn't
right, fix it; if you don't want it, leave it.* An ignored sheet sits in the
queue costing nothing. The only path to `rejected` is the `⋯` → **Discard sheet**
overflow item in §5, behind a typed confirmation, for the one real case — the
crawler grabbed the wrong business entirely.

**The consequence to design for:** the queue is now append-only from the user's
point of view. That is why §5 mandates sort, search and a count. Without them
this is a good decision that produces a bad screen in three months.

### 6.4 The questions pane

- Header: the run shape — `29 questions · 5 assistants · 3 runs each · 435 calls
  · about $14`. Cost from `src/pipeline/cost.py`. Owners deserve to see the size
  of the thing they're approving.
- Table: intent chip · id · text · persona. The intent chip is the existing
  `IntentBadge` — a navy tone ramp on a leading dot, ordinal by funnel stage.
- Every row editable inline; **Add a question** at the foot; × to remove.
- **Lint chips** beneath, from the agent plan §6.3. `✓` items are `--ink-secondary`
  and quiet; `⚠` warnings are `<Notice tone="info">`; **blocks are
  `<Notice tone="problem">` and they disable Approve.** Each block names the fix,
  never just the rule: *"Add a comparison question naming RingConn"*, not
  *"competitor coverage failed."*
- **Download CSV** as an outline button. The file is the same artifact the run
  consumes, which is what makes it worth downloading.

This pane is doing something the methodology explicitly requires: it is the
**human lock** from `docs/query-generation-plan.md` §6 — the read-aloud, "would a
real buyer actually say this?" pass that has to happen before a set is frozen.
Design it as a reading surface, not a spreadsheet: 14px text, generous row
height, the query text as the widest column.

### 6.5 The approve bar

Fixed to the bottom of the viewport, Paper ground, `1px solid var(--rule)` top.

- **APPROVE & ACTIVATE** — the one hero button in the feature (uppercase, 11px,
  `tracking-[0.14em]`). Right-aligned.
- To its left, one plain sentence, 12px `--ink-secondary`:
  > This replaces v1. Past reports keep the version they were run against; your
  > next run uses this one.

  That sentence is not decoration — approving a new version re-keys every cached
  judge verdict for this client, and the honest version of that fact is "your
  next run re-judges", which the owner can act on.
- **Save & come back later** as a ghost button, far left. The session stays in
  `awaiting_review` and the queue row keeps its **Review** action.

---

## 7 · S4 — the Active tab

Same card grammar as the queue. Each active sheet shows:

- Business name, domain, `v2 · active since 2026-08-04`
- `Used by 3 runs`
- Staleness: `Confirmed 12 days ago` in `--ink-secondary`; past 30 days it reads
  `Confirmed 41 days ago — worth a re-check` with a `<Notice tone="info">` in the
  detail view
- Actions: **View** (read-only detail, same claim rows as §6.1 minus the
  controls) and **Edit** (outline)

**Edit opens a new intake pre-filled from the active sheet.** It does not mutate
it. The copy on the confirm modal says exactly that:

> Editing starts a new version. v2 stays active until you approve v3, and every
> report already run keeps the version it used.

Superseded versions live in a `⌄ 2 earlier versions` disclosure inside the detail
view, read-only. They do not get a tab.

---

## 8 · S5 — the Home strip

`/` currently opens with the eyebrow/title pair and the CSV dropzone. Insert a
**Ready to run** strip above the dropzone, rendered only when at least one active
sheet has a query set.

```
READY TO RUN
┌─────────────────────────────────────────────────────────────────┐
│  Albert Nahman Plumbing        29 questions · v2 · about $14     │
│  albertnahmanplumbing.com                       [ Run audit ]  ⋯ │
└─────────────────────────────────────────────────────────────────┘
[ or upload a CSV ↓ ]
```

- **Run audit** is the `hero` variant here — it takes that role from the
  dropzone's own button when the strip is present, because one hero per page is
  the rule. When the strip is absent, the dropzone keeps it.
- Clicking it posts the stored CSV to the existing run endpoint with the sheet
  attached, and routes to `/audits/[id]`. No intermediate screen, no confirm —
  the confirm already happened at approve, and the cost was shown there.
- `⋯` carries **Preview the questions** (→ S3 read-only) and **Download CSV**.
- The dropzone stays exactly as it is, one heading lower, under
  `or upload a CSV`. This flow adds a path; it does not take one away.

---

## 9 · Accessibility

Non-negotiable, and cheaper to build in than to retrofit.

- The card region is `role="group"` with `aria-labelledby` pointing at the
  question text. On each new card, move focus to the card container (not the
  input — a screen reader must hear the question before the field) and announce
  progress via a visually-hidden `aria-live="polite"`: *"Question 6 of 14."*
- The assertion preview is `aria-live="polite"` and debounced 400ms, so a typist
  is not read their own keystrokes.
- The transcript is a `<ol>`; each entry is a `<button>` that jumps back, with an
  accessible name of `Edit answer to: {question}`.
- The progress rail is `role="progressbar"` with `aria-valuenow/min/max` and
  `aria-label="Intake progress"`. The individual plume marks are `aria-hidden`.
- Every state and lint level carries a **glyph and a label**, never a fill alone.
  Turn the stylesheet off and the screen must still parse.
- Focus rings: `focus-visible:ring-2 ring-blue ring-offset-2 ring-offset-paper`.
  Verify on the Paper ground rather than assuming — a 1px navy ring on white
  disappears, which is why the spec calls for 2px with an offset.
- The whole intake is keyboard-completable. Test it that way once, end to end,
  before calling I4 done.

---

## 10 · Responsive

| Breakpoint | Change |
|---|---|
| ≥ 1024 | As drawn. Review is two panes |
| 768–1023 | Review stacks: sheet, then questions, then the action bar. Intake card goes `max-w-[560px]` |
| < 768 | Intake card is full-bleed with `px-4`; the transcript collapses to a single `⌄ 6 answered` row; the progress rail scrolls horizontally with no fade mask (a fade on Paper reads as a rendering bug); the action bar is sticky and full width |

The intake must work on a phone. The most likely real-world use is a shop owner
answering it on the same phone they took Josh's call on.

---

## 11 · Component inventory

| File | New? | Notes |
|---|---|---|
| `web/components/intake/motion.css` | new | The **only** new stylesheet. Tokens + 3 keyframes + the reduced-motion block |
| `web/components/intake/intake-card.tsx` | new | The shell — eyebrow, prompt, helper, slot, assertion preview, buttons |
| `web/components/intake/transcript.tsx` | new | Collapsed list + jump-back |
| `web/components/intake/progress-rail.tsx` | new | Plume marks + the count line |
| `web/components/intake/thinking.tsx` | new | Three-mark pulse. Latency-gated |
| `web/components/intake/answers/*.tsx` | new | One per `AnswerKind`, twelve files. Each takes `{question, value, onChange, onCommit}` and nothing else |
| `web/components/intake/assertion-preview.tsx` | new | Live sentence, `aria-live` |
| `web/components/review/{sheet-pane,query-pane,tier-meter,approve-bar}.tsx` | new | |
| `web/components/plume.tsx` | existing | **Reuse. Do not fork.** The rail imports it at `size={8}`, which the component's own degradation ladder already resolves to one plume |
| `web/components/notice.tsx` | existing | Every warning, block and info line in the feature |
| `web/components/ui/{button,card,badge}.tsx` | existing | Unchanged. If you need a variant that doesn't exist, that is a signal to reuse, not to add one |
| `web/lib/ui.ts` | existing | `INPUT_CLS`, `FIELD_LABEL_CLS`, `FIELD_HINT_CLS`. Do not inline a fifth set |

---

## 12 · Acceptance checklist

**Brand**
- [ ] `grep -rn "indigo\|violet\|emerald\|amber\|-red-\|-green-\|7FA6D9" web/components/intake web/components/review` → **no hits**
- [ ] No Cormorant below 32px anywhere in the feature except the close screen's hero number
- [ ] At most one Sky element in the DOM on every screen, and it is the header plume
- [ ] Every state, lint level and tier indicator carries a glyph or a label as well as a fill
- [ ] The progress rail reads as marks, not as a row of logos, at every breakpoint

**Motion**
- [ ] The full handoff completes in ≤ 420ms, measured
- [ ] `prefers-reduced-motion: reduce` → the intake is fully legible and complete-able with zero animation
- [ ] Exactly one looping animation exists (the current progress mark), and it stops under reduced motion
- [ ] The thinking indicator never appears for a wait under 150ms

**Function**
- [ ] A 14-card intake is completable **keyboard-only**, end to end
- [ ] Refresh at question 8 → resumes at question 8 with nothing lost
- [ ] A skipped card renders `Nothing will be checked on this.` and produces no claim
- [ ] Approve is disabled, with a stated reason, while any lint `block` or unconfirmed claim exists
- [ ] Approving routes to `/fact-sheets` Active, and the sheet appears on `/` in Ready to run
- [ ] Run audit from the Home strip starts a real run against the approved sheet
- [ ] `cd web && npm run typecheck && npm run build` green
- [ ] `npm run report-pdf <known run-id>` still lands in the 13–18 page band — the feature shares `Card`, `Badge` and `Button` with the client report

**Contrast**
- [ ] Every `text-harbour` in the feature sits on white, not on Paper. Anything on Paper uses `text-[color:var(--ink-secondary)]`
- [ ] Focus ring visible on every interactive element, verified on the Paper ground

---

## 13 · Open questions for Josh

1. **The close screen's promise.** *"we'll flag it — including the serious
   ones"* is only true once §1.7's tier rule is enforced end to end. If I5 ships
   before that enforcement, the copy has to be softer. Flag it rather than
   shipping the stronger line early.
2. **Does the owner get a copy?** A confirmed fact sheet is a genuinely useful
   document for a business — it is the thing they'd hand a new employee. A
   "email me this sheet" checkbox on the close screen is one line of design and
   a real reason for them to finish. It needs a contact reference on the session,
   which the backend deliberately keeps PII-free today (agent plan §10.4).
3. **Who reviews — the owner or Josh?** This plan assumes the owner completes the
   intake and Josh (or the owner) approves in S3. If S3 is operator-only, the
   close screen should say *"we'll review these and get back to you"* and the
   auto-navigation goes to a thank-you instead. One sentence either way, but it
   has to be decided before the close screen is built.
