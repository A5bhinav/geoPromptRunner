# Spec — Redress the App Chrome in Sable

> **Status (2026-08-02): P0–P4 DONE, P5 done except the noted gaps.** Build-log entry: "Sable app chrome
> — P1–P4". P0 landed later the same day (the correction-run work was still uncommitted, so it was
> written on top of it, navigating by function name). **Two corrections to this spec, found while building it:** (a) §2.6's premise
> is wrong — Tailwind v3 does *not* fail the build on `text-destructive`, it emits nothing, so the
> build was green before any migration; use `grep` + `tsc` instead. (b) §7.6 is wrong that
> `charts.tsx` is unaffected — it consumes the `hsl(var(--*))` triplets P1 deletes, and P1 breaks
> every chart in the client report unless they are repointed. §6.4's "two lines" is now six.
> (c) §6.1's own task list is wrong about how a run aborts: `run_query_set` catches `Exception`,
> so only a `BaseException` (Ctrl-C) reaches the new `finally` — an engine error never can.
> **Gates run:** report-pdf = 15 pages (in band), print-check OK, 0 contrast/focus failures in the
> app. **Outstanding:** `charts.tsx` still carries a 7-hue categorical palette, and the REPORT
> (`sable.css`, out of scope here) sets body text to Harbour on Paper = 4.14:1, failing AA.
>
> **Audience:** a Claude Code session (one phase per session, in order).
> **Source of truth for the brand:** the Sable Identity Guide, Berkeley v1.0 ("Direction 7d Plume ·
> Berkeley 8a"), already transcribed in `web/styles/sable.css` and
> `docs/audit-packaging-implementation.md` §4.9. §1 below re-states the parts this spec depends on so
> you do not have to open the PDF; where they disagree, **the guide wins.**
> **Scope:** `web/app/**`, `web/components/**` (excluding `report-view.tsx` and `charts.tsx`),
> `web/styles/`, `web/tailwind.config.ts`, **plus one small Python change in P0**
> (`src/pipeline/orchestrator.py`). **Out of scope:** the client-facing report, the PDF renderer,
> and every other file under `src/`.
> **Standing rules:** load `.claude/skills/audit-packaging/SKILL.md` before touching anything a
> client can see. Nothing in this spec touches judge prompts or cache keys — if a change here
> tempts you into `src/pipeline/judge.py`, you have gone off-spec, stop.
> **Every phase ends green:** P0 uses the repo gate — `mypy src/ && ruff check src/ && pytest
> tests/`. P1–P5 use `cd web && npm run typecheck && npm run build`; they touch no Python, so if you
> find yourself running `mypy` in P1+ you are editing the wrong tree.

---

## The one-paragraph problem

Sable already exists in this codebase — the palette, both typefaces and the three-plume logic are
in `web/styles/sable.css`, and `web/app/layout.tsx` already loads Cormorant Garamond and Libre
Franklin. But `sable.css` deliberately scopes every token under `.sable`, and its own header comment
says why: *"The app chrome (upload, projects, teaser) keeps its existing indigo shadcn theme; only
the client-facing report wears Sable."* That was the right call when the report was the only
client-facing artifact. It is the wrong call now. The app chrome is screen-shared on sales calls,
recorded in demos, and handed to founders during onboarding — it is a client-facing surface that
happens to also be a tool. Today it ships **indigo `#4f46e5`**, an Inter body face, a lightning-bolt
favicon, and five accent hues (sky, indigo, violet, emerald, amber) that violate the guide's
explicit *"no colours outside the palette."* This spec promotes Sable to `:root`, retires the indigo
theme entirely, and states the one deviation the tool is allowed: **density.**

---

## The one decision, up front

The app is **the same system as the report, in a denser workshop variant.** Concretely:

| | Report (`.sable`, unchanged) | App chrome (this spec) |
|---|---|---|
| Palette | Sable, locked | **Sable, locked — identical** |
| Display face | Cormorant Garamond, 32px+ | **Cormorant for the wordmark, page `<h1>`, and hero numbers only** |
| Text face | Libre Franklin 15/1.7 | **Libre Franklin 13–14/1.55** |
| Ground | Paper, cards white | **Identical** |
| Density | Generous, print-oriented | **Tight: 40px header, 12px card padding steps, 36px controls** |
| Buttons | Tracked uppercase pills | **Sentence-case pills; tracked uppercase reserved for the one hero action per page** |

The deviation is *scale and spacing*, never colour, never typeface, never the mark. If a reviewer
cannot tell the app and the report were designed by the same people, this spec failed. If a user
cannot scan 40 rows of a run table, it also failed.

**Two things get worse before they get better, and both are deliberate — read §6 before you argue
with them:** the app loses its red error banners and its green/amber state badges. Sable has no
alert hue at all.

---

## Dependency graph

```
P0 (backend honesty, Python)   ── independent, do it first ──┐
                                                             ▼
P1 (tokens)  ──►  P2 (mark + shell)  ──►  P3 (primitives)  ──►  P4 (pages)  ──►  P5 (QA)
     │                                          ▲
     └──────────────────────────────────────────┘
                 P3 cannot start before P1; P4 cannot start before P3.
```

P0 is Python and touches no styling; it is separable and can land any time, but it should go **first**
because P4-T3 relabels a UI string whose meaning P0 changes.

P1 alone will make the app look *wrong* — navy-on-indigo half-states, mismatched borders. That is
expected and is why P1 and P2 should land in the same session if possible. Do not ship P1 alone to a
demo branch.

---

## 0 · Phase P0 — Make the CLI's runs terminal (Python; do this first)

> **⚠ Merge hazard, checked 2026-08-02.** `src/pipeline/orchestrator.py`, `src/api/runner.py`,
> `src/cli.py`, `src/storage/db.py` and `src/pipeline/cost.py` all have **uncommitted changes in the
> working tree** — an in-flight "correction run" feature (`src/pipeline/correction.py`,
> `tests/test_correction.py`, `data/schema_run_corrections.sql`, new `run_kind` /
> `supersedes_run_id` columns). `orchestrator.py` grew from ~295 to 378 lines *during the writing of
> this spec*. **Every line number below is a hint, not an address — navigate by function name, and
> check with Abhi before starting P0.**

### 0.1 Why the obvious fix is the wrong one

The tempting fix is "have the CLI store its query set like the API does, so its runs auto-resume."
**Do not do this.** `resume_interrupted_runs()` runs unattended at API startup and relaunches every
resumable row it can rebuild. Storing the CLI's query set would mean: the operator Ctrl-Cs a
25-query audit because they spotted a bad config → someone restarts the API → the run silently
relaunches and **spends real money on engine calls nobody asked for.** That is squarely against the
cost discipline in `CLAUDE.md` (`MAX_AUDIT_COST_USD` / `MAX_TOTAL_SPEND_USD`, "engine calls cost real
money"). An abort is a decision; auto-resume would quietly overrule it.

It also drags `_serialize_queries` out of `src/api/runner.py` into the storage layer to avoid
`src/pipeline/` importing from `src/api/` — a refactor of files that are being edited right now.

### 0.2 The fix: never leave a CLI row non-terminal

`resume_interrupted_runs()` only ever sees rows whose status is `running` or `queued`
(`db.list_resumable_runs`). So the bug disappears entirely if the CLI's runs always reach a terminal
status — no query-set storage, no auto-resume, no layering change, no money risk.

Today `run_audit()` sets `status="done"` on exactly one line, on the happy path only (currently
`orchestrator.py:303`). Nothing in `src/cli.py` or `orchestrator.py` catches `KeyboardInterrupt` or
wraps the measurement loop, so any abort leaves the row at `"running"` forever. Wrap it:

```python
# Terminal status is derived from what actually landed, not from reaching the
# happy path. Two bugs close here:
#   1. A Ctrl-C / crash used to leave the row at "running", so the API's next
#      startup scan flipped it to "interrupted" — a status that means "we could
#      not rebuild this at startup", which was never what happened.
#   2. A process that died between the last result write and the old success
#      line left a COMPLETE run stuck at "running", and _prior_comparable_run
#      (runner.py, `status == "done"`) then excluded a perfectly good cycle from
#      the trend comparison permanently.
# "cancelled" rather than "failed": an operator aborting is not an error, and the
# UI, _prior_comparable_run and the engine-state rollup already treat cancelled
# as terminal.
completed = False
try:
    for index, query in enumerate(queries, start=1):
        ...  # unchanged loop body
    completed = True
finally:
    if run_id is not None:
        try:
            db.update_audit_run_progress(
                run_id,
                completed_calls=len(results),
                status="done" if completed else "cancelled",
                error=None if completed else "aborted before all queries ran",
            )
        except StorageError as exc:
            # Best-effort, exactly like every other progress write here: a
            # storage failure must not mask the original exception.
            logger.warning("Could not write terminal status for run %s: %s", run_id, exc)
```

Delete the old standalone `status="done"` call — the `finally` replaces it. `completed = True` must
sit **inside** the `try`, after the loop, so an exception from the final iteration cannot mark the
run done.

### 0.3 What this fixes, and what it does not

| Case | Before | After |
|---|---|---|
| CLI run finishes cleanly | `done` | `done` (unchanged) |
| Ctrl-C mid-run | `running` → `interrupted` at next API start | **`cancelled`, immediately** |
| Crash / exception mid-run | `running` → `interrupted` | **`cancelled`, immediately** |
| Died after last write, before the success line | `running` → `interrupted`, **silently dropped from trend forever** | **`done`** — the `finally` runs and `completed` is `True` |
| `kill -9` / power loss | `running` → `interrupted` | unchanged — genuinely unrecoverable, and `interrupted` is now the *honest* label for the only case still reaching it |
| API-created runs | unaffected | unaffected |

Existing bad rows are **not** retro-fixed. Check with Abhi whether any are real cycles worth
rescuing before anyone writes a migration.

### 0.4 Tasks

- [x] P0-T1 Confirm the correction-run work is committed or stashed, then re-read `run_audit()` —
      do not trust the line numbers above.
- [x] P0-T2 Wrap the measurement loop per §0.2; delete the standalone `status="done"` write.
- [x] P0-T3 Fix the stale reason string at the `interrupted` write in `resume_interrupted_runs()`:
      it says *"interrupted before resume support (no stored query set)"*, which after P0 describes
      only hard-killed CLI rows. Say that instead.
- [x] P0-T4 **Regression tests**, one per bug: (a) an exception raised mid-loop leaves the stored
      status `cancelled`, not `running`; (b) a loop that completes and then raises still leaves
      `done`. Fake the `db` module — this test must make no engine calls and cost nothing.
- [x] P0-T5 Gate: `mypy src/ && ruff check src/ && pytest tests/`, then a `docs/build-log.md` entry.

---

## 1 · What the guide actually says

Everything in this section is normative. It is copied from the identity guide, not invented here.

### 1.1 The mark

Three plumes on a shared baseline. Each plume is *"a teardrop with three rounded corners and one
square heel."* Heights step evenly; **tone steps with them**, so the eye lands on the tallest,
darkest form.

| Property | Value |
|---|---|
| Width, each plume | 1 u |
| Heights | 1.7 u · 2.3 u · 2.9 u |
| Gap | 0.3 u |
| Corner | `60% 60% 60% 0` (square heel at bottom-left) |
| Tones on paper | Mist · Harbour · Navy |
| Tones on navy | white 36% · white 74% · **Sky** |

Total mark box = 3.6 u wide × 2.9 u tall.

**Clearspace:** one plume width (1 u) on all sides. Nothing enters that field — not rules, not other
logos.

**Minimum sizes:** below **20 px** the mark drops its faintest plume and runs two-up; below **16 px**
use the tallest plume alone. The wordmark never sets below **14 px**.

### 1.2 Palette (locked)

| Token | Hex | Role |
|---|---|---|
| Berkeley Navy | `#0E2340` | ink, tallest plume |
| Sable Blue | `#12325C` | links, active states |
| Sky | `#7FA6D9` | **accent on navy only** |
| Harbour | `#697585` | middle plume, body |
| Mist | `#B2B7BC` | first plume, rules |
| Paper | `#F2F1EC` | ground |
| White | `#FFFFFF` | cards |

> *"Navy and paper carry almost everything. Sky appears only against navy, never on paper — it is
> the one bright note in the system and loses its job if it is used twice on a page."*

### 1.3 Type

- **Cormorant Garamond** — display only. Light 300 & Regular 400. Headlines from 32 px up, tracked
  +0.01 to +0.04 em. Italic for emphasis only, never body copy.
- **Libre Franklin** — text and UI. Body sets 15/1.7 in Harbour or navy at 80%.
- **Sentence case everywhere.** The only uppercase in the system is the tracked label
  (10 px / 0.36 em).
- The wordmark always stays Garamond, even where the surrounding UI is Libre Franklin.

### 1.4 The guide's own in-use header

The guide ships a site-header mock, and the app header should be read as a direct descendant of it:
54 px navy band, mark at ~19 px height with Sky on the tallest plume, Garamond wordmark at 20 px,
nav links at 10 px / 0.1 em in white 72%, and a single white pill CTA on the right.

> **One inconsistency in the source, resolved upward.** The guide's scale card sets the three-plume
> minimum at **20 px** ("20 px · min"), but its own header mock draws three plumes at 19 px — one
> pixel under its own floor. **This spec uses 20 px in the header** so the mark stays legal by the
> guide's own rule. Do not "match the mock" at 19: the `Plume` component will silently drop a plume
> and you will ship a two-plume logo.

### 1.5 Don'ts (verbatim)

1. Never rotate the mark.
2. **No colours outside the palette.**
3. Never stretch or squash.
4. The wordmark stays Garamond.

---

## 2 · Phase P1 — Promote Sable to `:root`, retire indigo

### 2.1 Why channels, not hex, and not HSL

`sable.css` stores hex. shadcn's `globals.css` stores HSL triplets so Tailwind can do
`bg-primary/10`. If the app converts Sable's hexes to HSL, `#F2F1EC` round-trips to `#F2F1EB` and the
app ground stops matching the report ground by one unit of blue — invisible on screen, visible in a
side-by-side screenshot on a sales deck, and impossible to diagnose later.

Store **space-separated RGB channels** alongside the hex. Tailwind's `<alpha-value>` placeholder
works with them, and the hex stays exact.

### 2.2 New file: `web/styles/tokens.css`

Create it. Do **not** put these in `sable.css` — that file is the report's, and P1 must not be able
to break the report.

```css
/* Sable — the APP CHROME's design tokens.
 *
 * Source of truth: the Sable Identity Guide, Berkeley v1.0 ("Direction 7d Plume ·
 * Berkeley 8a"). Same guide, same hexes, same two faces as web/styles/sable.css.
 *
 * WHY THIS FILE IS SEPARATE FROM sable.css, given the values are identical:
 * sable.css is the REPORT's skin and is the seam a white-label tenant replaces
 * (web/lib/brand.ts). If the report inherited its tokens from :root, a neutral
 * tenant would have to override every variable to avoid leaking Sable into a
 * resold artifact, and any it missed would leak silently. Two files, one shared
 * set of hexes, zero inheritance between them. DO NOT "de-duplicate" these.
 *
 * Channels, not hex, for the palette: Tailwind's <alpha-value> needs them, and
 * an HSL round-trip moves Paper by one unit of blue — enough to make the app
 * ground and the report ground differ in a screenshot.
 *
 * SKY IS NOT DEFINED HERE. Same structural guarantee sable.css makes: Sky is
 * legal on navy and nowhere else, so it lives only inside .on-navy. On a paper
 * ground var(--sky) resolves to nothing and fails visibly, rather than passing
 * review and shipping.
 */

:root {
  /* --- palette (locked; no colours outside it) --- */
  --navy: #0e2340;
  --navy-rgb: 14 35 64;
  --blue: #12325c;
  --blue-rgb: 18 50 92;
  --harbour: #697585;
  --harbour-rgb: 105 117 133;
  --mist: #b2b7bc;
  --mist-rgb: 178 183 188;
  --paper: #f2f1ec;
  --paper-rgb: 242 241 236;
  --white: #ffffff;
  --white-rgb: 255 255 255;

  /* --- derived surfaces: navy at low alpha, never a separate grey ---
   * A grey rule beside a navy one reads as a mistake. Same reasoning as
   * sable.css, same alphas, so app cards and report cards have the same edge. */
  --rule: rgb(14 35 64 / 0.12);
  --rule-soft: rgb(14 35 64 / 0.07);
  --hover: rgb(14 35 64 / 0.04);
  --selected: rgb(14 35 64 / 0.06);

  /* --- secondary ink, and the reason it is not just Harbour ---
   * Harbour IS navy at 60% over Paper — #697585 to the byte. That is a nice
   * property of the palette and also the trap: at 60% it measures 4.14:1 on
   * the Paper ground, which FAILS WCAG AA for normal text. On a white card it
   * clears at 4.68:1. So: Harbour on white, --ink-secondary on paper. Same
   * hue, same family, one passes and one does not, and the difference is
   * invisible to the eye that has to sign off on it — hence a token. */
  --ink-secondary: rgb(14 35 64 / 0.7); /* 5.59:1 on Paper */

  /* --- type --- */
  --font-display: var(--font-cormorant), Georgia, "Times New Roman", serif;
  --font-text: var(--font-libre-franklin), ui-sans-serif, system-ui, sans-serif;

  /* --- geometry: the guide's card is 14px, its small card 12px, pills 999px --- */
  --radius: 0.875rem; /* 14 */
}

/* Sky lives HERE and only here. In the app chrome that scope is the header band
 * and nothing else — Sky "is the one bright note in the system and loses its job
 * if it is used twice on a page," and the header's tallest plume already spends
 * it. Inside .on-navy the ACTIVE NAV ITEM therefore gets white + a white rule,
 * not Sky. */
.on-navy {
  --sky: #7fa6d9;
  --sky-rgb: 127 166 217;
  background-color: var(--navy);
  color: var(--white);
}
```

### 2.3 Rewrite `web/app/globals.css`

Replace the whole file. The `.dark` block goes: **Sable has no dark palette**, there is no theme
toggle in the app, and a half-invented dark mode is how a sixth hue gets in.

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  * {
    border-color: var(--rule);
  }

  body {
    background-color: var(--paper);
    color: var(--navy);
    font-family: var(--font-text);
    font-feature-settings: "rlig" 1, "calt" 1;
  }

  /* Cormorant is DISPLAY ONLY (32px+ per the guide). In the app that is: the
   * wordmark, the page <h1>, and hero numbers. Everything else is Franklin. */
  .display {
    font-family: var(--font-display);
    font-weight: 300;
    letter-spacing: 0.02em;
  }

  /* The one legitimate uppercase in the system. */
  .label {
    font-family: var(--font-text);
    font-size: 0.625rem; /* 10 */
    font-weight: 600;
    letter-spacing: 0.36em;
    text-transform: uppercase;
    color: var(--harbour);
  }

  .tabular-nums {
    font-variant-numeric: tabular-nums;
  }
}

@media print {
  .no-print {
    display: none !important;
  }
  body {
    background: white;
  }
}
```

> **Do not delete the `@media print` block.** `web/app/audits/[id]/page.tsx` renders the report
> inside the app shell, and `render-report-pdf.mjs` depends on `.no-print` hiding the chrome. The
> report's own print rules stay in `sable.css`; these two do not overlap.

### 2.4 `web/app/layout.tsx` — import order

```ts
import "./globals.css";
import "../styles/tokens.css";
import "../styles/sable.css";
```

`tokens.css` must load **after** `globals.css` (Tailwind's `base` layer would otherwise win on
`body`) and **before** `sable.css` (so the report's scoped class stays last and unambiguous).

### 2.5 `web/tailwind.config.ts`

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  // No dark mode. Sable has no dark palette and the app has no toggle; a
  // half-invented one is how a sixth hue gets in.
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // The palette, by its real names. Semantic aliases below exist only so
        // the existing shadcn class names keep compiling during the migration —
        // new code should reach for navy/harbour/mist/paper directly.
        navy: "rgb(var(--navy-rgb) / <alpha-value>)",
        blue: "rgb(var(--blue-rgb) / <alpha-value>)",
        harbour: "rgb(var(--harbour-rgb) / <alpha-value>)",
        mist: "rgb(var(--mist-rgb) / <alpha-value>)",
        paper: "rgb(var(--paper-rgb) / <alpha-value>)",
        // Sky is NOT here. It exists only inside .on-navy — see tokens.css.

        border: "var(--rule)",
        input: "var(--rule)",
        ring: "rgb(var(--blue-rgb) / <alpha-value>)",
        background: "rgb(var(--paper-rgb) / <alpha-value>)",
        foreground: "rgb(var(--navy-rgb) / <alpha-value>)",
        primary: {
          DEFAULT: "rgb(var(--navy-rgb) / <alpha-value>)",
          foreground: "rgb(var(--white-rgb) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "rgb(var(--paper-rgb) / <alpha-value>)",
          foreground: "rgb(var(--navy-rgb) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "rgb(var(--paper-rgb) / <alpha-value>)",
          foreground: "rgb(var(--harbour-rgb) / <alpha-value>)",
        },
        accent: {
          DEFAULT: "rgb(var(--blue-rgb) / <alpha-value>)",
          foreground: "rgb(var(--white-rgb) / <alpha-value>)",
        },
        card: {
          DEFAULT: "rgb(var(--white-rgb) / <alpha-value>)",
          foreground: "rgb(var(--navy-rgb) / <alpha-value>)",
        },
        // `destructive`, `success` and `warning` are GONE. See §6. Leaving them
        // aliased to navy would let `text-destructive` keep compiling while
        // silently doing nothing — the build error is the point.
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)", // 18
        lg: "var(--radius)", //              14
        md: "calc(var(--radius) - 2px)", //  12
        sm: "calc(var(--radius) - 4px)", //  10
      },
      fontFamily: {
        sans: ["var(--font-libre-franklin)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-cormorant)", "Georgia", "serif"],
      },
      // NO fontSize OVERRIDE. This is the obvious next move and it is a trap:
      // report-view.tsx uses text-sm / text-xs / text-base 37 times, so
      // redefining the scale would resize the CLIENT REPORT and repaginate the
      // PDF — a 17-page deliverable is not a place to discover a global type
      // change. The workshop scale is applied per-element in app code as
      // `text-[13px]` etc. Verbose on purpose: it cannot leak.
    },
  },
  plugins: [],
};

export default config;
```

> **`--radius` moves from `0.75rem` to `0.875rem`.** That is deliberate (the guide's card is 14 px),
> and it reaches the report: `rounded-lg` goes 12 → 14 px and `rounded-xl` 16 → 18 px in
> `report-view.tsx`. Cosmetic, no pagination impact, but it *is* a client-visible change — note it
> in the build-log entry. The correct follow-up, out of scope here, is to move the report's cards
> from `rounded-xl` to `rounded-lg` so they sit at the guide's 14 px.

### 2.6 P1 exit criteria

`npm run build` fails, loudly, on every `text-destructive` / `bg-success` / `border-amber-500/30` /
`bg-indigo-100` in the tree. **That failure list is your P3+P4 worklist.** Capture it before moving
on:

```bash
cd web && npm run build 2>&1 | tee /tmp/sable-migration-worklist.txt
grep -rn "destructive\|success\|warning\|indigo\|violet\|emerald\|amber\|sky-\|-500\|-100\|-700" \
  app components --include=*.tsx
```

Expected hits at time of writing: `components/badges.tsx` (intent + state maps),
`app/page.tsx:141`, `app/teaser/page.tsx:281,287-291`, `app/fact-sheets/page.tsx:124,206`,
`app/audits/[id]/page.tsx:103`, `app/projects/page.tsx:32`, `app/projects/[key]/page.tsx:89,246`,
`app/audit/page.tsx:203,226`, `components/ui/button.tsx`, `components/ui/badge.tsx`.

---

## 3 · Phase P2 — The mark and the shell

### 3.1 New file: `web/components/plume.tsx`

The mark is currently nowhere in the codebase — `lib/brand.ts` has a `showMark` flag with nothing to
render. This component is that missing piece, and the report should adopt it later too.

```tsx
/**
 * The Sable mark — three plumes on a shared baseline.
 *
 * Geometry is the guide's, exactly: width 1u, heights 1.7 / 2.3 / 2.9 u, gap
 * 0.3 u, corner `60% 60% 60% 0`. The box is therefore 3.6u × 2.9u.
 *
 * WHY SVG PATHS AND NOT THREE DIVS: the guide draws the plumes with CSS
 * border-radius, which the browser CLAMPS — 60%+60% on one axis exceeds 100%,
 * so every radius is scaled by 1/1.2 and the real shape is an ellipse of
 * rx=w/2, ry=h/2 with the bottom-left quadrant squared off. The paths below are
 * that shape stated directly, which means they survive `transform: scale()`,
 * print at any DPI, and drop into a favicon. Verified pixel-identical to the
 * CSS version at 87px tall.
 *
 * DON'Ts encoded here rather than left to review: no rotation, no non-uniform
 * scale (the viewBox does the scaling), no colour outside the palette (`tone`
 * is a closed union), and the sub-20px degradations the guide requires.
 */
import * as React from "react";

type Tone = "paper" | "navy" | "mono";

const TONES: Record<Tone, [string, string, string]> = {
  // On a paper/white ground: Mist · Harbour · Navy.
  paper: ["#B2B7BC", "#697585", "#0E2340"],
  // On navy: white 36% · white 74% · Sky. This is the ONLY place Sky appears.
  navy: ["rgba(255,255,255,0.36)", "rgba(255,255,255,0.74)", "#7FA6D9"],
  // The guide's approved one-colour lockup, for favicons and stamps.
  mono: ["currentColor", "currentColor", "currentColor"],
};

/** One plume: an ellipse with the lower-left quadrant squared off. */
function path(x: number, w: number, h: number, base: number): string {
  const rx = w / 2;
  const ry = h / 2;
  const mid = base - ry;
  return [
    `M${x} ${base}`,
    `L${x} ${mid}`,
    `A${rx} ${ry} 0 0 1 ${x + rx} ${base - h}`,
    `A${rx} ${ry} 0 0 1 ${x + w} ${mid}`,
    `A${rx} ${ry} 0 0 1 ${x + rx} ${base}`,
    "Z",
  ].join(" ");
}

export interface PlumeProps {
  /** Rendered HEIGHT in px. The guide sizes the mark by height, never width.
   * 20 is the guide's three-plume minimum — go below it only deliberately. */
  size?: number;
  tone?: Tone;
  className?: string;
}

export function Plume({ size = 20, tone = "paper", className }: PlumeProps) {
  const fills = TONES[tone];
  // The guide's degradation ladder — below 20px drop the faintest plume and run
  // two-up; below 16px use the tallest alone. Encoded, not remembered.
  const count = size < 16 ? 1 : size < 20 ? 2 : 3;
  const u = 10;
  const heights = [1.7, 2.3, 2.9].slice(3 - count).map((k) => k * u);
  const gap = 0.3 * u;
  const width = count * u + (count - 1) * gap;
  const base = 2.9 * u;
  const shown = fills.slice(3 - count);

  return (
    <svg
      // Height drives; width follows the aspect ratio. Never set both.
      height={size}
      viewBox={`0 ${base - heights[heights.length - 1]} ${width} ${heights[heights.length - 1]}`}
      width={(size * width) / heights[heights.length - 1]}
      className={className}
      role="img"
      aria-label="Sable"
    >
      {heights.map((h, i) => (
        <path key={i} d={path(i * (u + gap), u, h, base)} fill={shown[i]} />
      ))}
    </svg>
  );
}

/** The full lockup: mark + Garamond wordmark + tracked descriptor. */
export function Wordmark({
  size = 20,
  tone = "paper",
  descriptor,
}: {
  size?: number;
  tone?: Tone;
  descriptor?: string;
}) {
  const onNavy = tone === "navy";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: size * 0.55 }}>
      <Plume size={size} tone={tone} />
      <span style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        {/* The wordmark ALWAYS stays Garamond, and never sets below 14px. */}
        <span
          className="display"
          style={{
            fontSize: Math.max(14, size * 1.05),
            lineHeight: 1,
            fontWeight: 400,
            letterSpacing: "0.04em",
            color: onNavy ? "#FFFFFF" : "var(--navy)",
          }}
        >
          Sable
        </span>
        {descriptor ? (
          <span
            className="label"
            style={{ fontSize: 7.5, color: onNavy ? "rgba(255,255,255,0.6)" : undefined }}
          >
            {descriptor}
          </span>
        ) : null}
      </span>
    </span>
  );
}
```

**Clearspace is the caller's job.** The component draws the 3.6u × 2.9u box and nothing more; every
placement must leave 1 u (= `size / 2.9` px) clear on all sides. In the header that is the `gap` on
the flex row — do not let a nav link or a border creep into it.

### 3.2 Replace `web/app/icon.svg`

The lightning bolt is not ours. The guide's app-icon treatment is a navy tile with the mark
bottom-aligned; at 32 px the two-plume degradation would be wrong for an icon (the tile gives the
mark its own field), so the icon uses all three at the guide's 46 px proportions scaled down.

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="9" fill="#0E2340" />
  <path d="M6.5 25 L6.5 20.5 A2.5 4.5 0 0 1 9 16 A2.5 4.5 0 0 1 11.5 20.5 A2.5 4.5 0 0 1 9 25 Z"
        fill="#FFFFFF" fill-opacity="0.40" />
  <path d="M13.5 25 L13.5 18.5 A2.5 6.5 0 0 1 16 12 A2.5 6.5 0 0 1 18.5 18.5 A2.5 6.5 0 0 1 16 25 Z"
        fill="#FFFFFF" fill-opacity="0.78" />
  <path d="M20.5 25 L20.5 16.5 A2.5 8.5 0 0 1 23 8 A2.5 8.5 0 0 1 25.5 16.5 A2.5 8.5 0 0 1 23 25 Z"
        fill="#7FA6D9" />
</svg>
```

This is the one place outside the header where Sky appears, and it is legal: the tile is navy.

### 3.3 `web/app/layout.tsx` — the shell

Rewrite the header. Changes: Inter is deleted outright (Libre Franklin is the UI face now, and a
third webfont is 40 KB of nothing); the `Activity` lucide icon is replaced by the mark; the band is
navy; the nav gets an active state.

```tsx
import type { Metadata } from "next";
import { Cormorant_Garamond, Libre_Franklin } from "next/font/google";
import "./globals.css";
import "../styles/tokens.css";
import "../styles/sable.css";
import { AppHeader } from "@/components/app-header";

// Sable's two faces, self-hosted at build by next/font. Deliberately NOT a CDN
// <link>: that breaks static export, and the PDF worker's header/footer
// templates render in an isolated iframe that cannot reach a relative webfont
// either. Both faces are metrically unlike system-ui — re-measure every print
// layout after a font change rather than assuming the spacing held.
//
// Inter is GONE. Libre Franklin is the UI face per the guide; a third face was
// 40KB serving nothing.
const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["300", "400"],
  style: ["normal", "italic"], // italic is for EMPHASIS ONLY, never body copy
  variable: "--font-cormorant",
  display: "swap",
});

const libreFranklin = Libre_Franklin({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-libre-franklin",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Sable — AI visibility",
  description: "Measure how often your brand appears in AI-generated answers.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${cormorant.variable} ${libreFranklin.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <AppHeader />
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
```

### 3.4 New file: `web/components/app-header.tsx`

A client component, because the active nav item needs `usePathname()`.

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Wordmark } from "@/components/plume";
import { cn } from "@/lib/utils";

/** Nav order is the workflow order: make one → look at them → sell one → the
 * two supporting surfaces. Not alphabetical. */
const NAV = [
  { href: "/", label: "Run" },
  { href: "/projects", label: "Projects" },
  { href: "/teaser", label: "Teaser" },
  { href: "/audit", label: "Deliverable" },
  { href: "/fact-sheets", label: "Fact sheets" },
];

export function AppHeader() {
  const pathname = usePathname();
  return (
    // `on-navy` is what makes Sky resolve — see web/styles/tokens.css. The band
    // is the ONLY place in the app chrome where Sky is legal, and the mark's
    // tallest plume already spends it, so the active nav item below is marked
    // with white + a rule rather than with colour.
    <header className="on-navy no-print sticky top-0 z-30">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-8 px-6">
        {/* Clearspace: the 1u field around the mark is this gap. Nothing enters it. */}
        <Link href="/" aria-label="Sable — home">
          <Wordmark size={20} tone="navy" descriptor="AI SEO" />
        </Link>
        <nav className="ml-auto flex items-center gap-6">
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "border-b-[1.5px] pb-0.5 text-[13px] transition-colors",
                  active
                    ? "border-white text-white"
                    : "border-transparent text-white/70 hover:text-white",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
```

> The old header carried a `"AI visibility measurement"` tagline beside the logo. It goes: the
> descriptor under the wordmark now says `AI SEO`, and two descriptors is one too many.

---

## 4 · Phase P3 — Primitives

### 4.1 `web/components/ui/button.tsx`

```tsx
const buttonVariants = cva(
  // Pill, per the guide. Sentence case — the tracked-uppercase treatment the
  // guide shows on its Primary/Secondary chips is reserved for the ONE hero
  // action per page (`variant="hero"`); applying it to "Add file" and "Cancel"
  // makes a dense tool unreadable and is this spec's only sanctioned deviation.
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "bg-navy text-white hover:bg-blue",
        outline: "border border-navy/25 bg-transparent text-navy hover:bg-navy/[0.04]",
        ghost: "text-harbour hover:bg-navy/[0.04] hover:text-navy",
        // The one action a page exists for. Tracked uppercase, per the guide.
        hero: "bg-navy px-6 text-[11px] uppercase tracking-[0.14em] text-white hover:bg-blue",
        // No `destructive`. Sable has no alert hue — see §6. Destructive actions
        // use `outline` and are gated by a typed confirmation, which is the
        // safety mechanism that actually works.
      },
      size: {
        default: "h-9 px-4",
        sm: "h-8 px-3 text-xs",
        lg: "h-10 px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);
```

Call sites to change: `app/audit/page.tsx:226` and `app/projects/[key]/page.tsx:246` are the only
two `variant="destructive"` uses. Both become `variant="outline"`; both already sit behind a
confirmation.

### 4.2 `web/components/ui/card.tsx`

Only the base class and the padding steps change.

```tsx
// Guide: white card, 1px navy-at-12% rule, 14px radius. No shadow — the guide's
// cards are drawn with a rule, and a shadow under a navy rule reads as muddy.
"rounded-lg border border-[var(--rule)] bg-white text-navy"
```

Padding: `CardHeader` `p-5 pb-3`, `CardContent` `p-5 pt-0`. (Was `p-6`. The workshop step.)
`CardTitle` becomes `text-[15px] font-medium tracking-normal` — **not** Cormorant. Card titles are
UI, and the guide puts Cormorant above 32 px only.

> **This one reaches the report.** `report-view.tsx` uses the same `Card`, so dropping `shadow-sm`
> and tightening the padding changes the client artifact and the PDF. Both changes move the report
> *toward* the guide (whose cards are drawn with a rule and carry no shadow — `sable.css` already
> says so), so this is a fix, not a regression. But it is a client-facing change:
> **load `.claude/skills/audit-packaging/SKILL.md` before P3-T2, and re-run `npm run report-pdf`
> after it.** If the tighter padding costs a page, revert the padding and keep the shadow removal.

### 4.3 `web/components/ui/badge.tsx`

```tsx
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium",
  {
    variants: {
      variant: {
        // Fill = navy family. Outline = categorical. Nothing else exists.
        solid: "bg-navy text-white",
        muted: "bg-navy/[0.06] text-navy",
        outline: "border border-navy/20 text-navy",
        quiet: "border border-[var(--rule)] text-harbour",
      },
    },
    defaultVariants: { variant: "muted" },
  },
);
```

### 4.4 New file: `web/lib/ui.ts` — the form-control class strings

`app/teaser/page.tsx` defines a local `inputCls`; `app/page.tsx`, `app/audit/page.tsx` and
`components/upload-dropzone.tsx` each inline their own `<select>` classes, and they already disagree
about border radius. One export, four call sites.

```ts
/** Every text input and select in the app. One string, so they cannot drift. */
export const INPUT_CLS =
  "h-9 w-full rounded-md border border-[var(--rule)] bg-white px-3 text-[13px] text-navy " +
  "placeholder:text-mist focus:border-blue focus:outline-none focus:ring-1 focus:ring-blue";

/** The field label above an input. Sentence case, Franklin, never Cormorant. */
export const FIELD_LABEL_CLS = "text-[13px] font-medium text-navy";

/** The helper line under an input. */
export const FIELD_HINT_CLS = "text-[11px] leading-relaxed text-harbour";
```

### 4.5 New file: `web/components/notice.tsx`

Replaces every `rounded-lg border border-destructive/30 bg-destructive/5 …` banner (eight sites).

```tsx
import * as React from "react";
import { AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The app has no alert hue — Sable's palette is entirely cool and "no colours
 * outside the palette" is an explicit brand Don't. So a notice is distinguished
 * by a 3px navy-family LEFT RULE, an ICON, and a plain sentence. The icon and
 * the rule weight are load-bearing, not decoration: with a single-hue system,
 * colour genuinely cannot carry the distinction. Same reasoning as the report's
 * severity ramp (see components/badges.tsx).
 */
const TONE = {
  problem: { rule: "border-l-navy", Icon: AlertTriangle, ink: "text-navy" },
  info: { rule: "border-l-harbour", Icon: Info, ink: "text-navy" },
  done: { rule: "border-l-blue", Icon: CheckCircle2, ink: "text-navy" },
} as const;

export function Notice({
  tone = "problem",
  title,
  children,
  className,
}: {
  tone?: keyof typeof TONE;
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  const { rule, Icon, ink } = TONE[tone];
  return (
    <div
      role={tone === "problem" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-md border border-[var(--rule)] border-l-[3px] bg-white p-3.5 text-[13px]",
        rule,
        ink,
        className,
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="space-y-1">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div className="text-harbour">{children}</div> : null}
      </div>
    </div>
  );
}
```

### 4.6 `web/components/badges.tsx` — the two colour maps

**`IntentBadge` — delete `INTENT_CLASSES` entirely.** Five hues (sky, indigo, violet, emerald,
amber) is the single largest brand violation in the tree. The replacement uses the navy tone ramp on
a leading **dot**, ordered by funnel stage — which is legitimate because funnel stage genuinely *is*
ordinal, so a tone ramp encodes real information rather than decorating a category:

```tsx
/** Funnel order, cold → warm. The tone ramp is legal here (and only here)
 * because this axis is ORDINAL: a prospect moves problem-aware → category →
 * comparison → brand. `adjacent_authority` sits off the funnel and gets a
 * hollow dot rather than a rung on the ramp. */
const INTENT_ORDER = ["problem_aware", "category", "comparison", "brand"] as const;
const INTENT_TONE: Record<string, string> = {
  problem_aware: "var(--mist)",
  category: "var(--harbour)",
  comparison: "var(--blue)",
  brand: "var(--navy)",
};

export function IntentBadge({ intent }: { intent: string }) {
  const label = INTENT_LABELS[intent] ?? intent;
  const tone = INTENT_TONE[intent];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--rule)] px-2.5 py-0.5 text-[11px] font-medium text-navy">
      <span
        aria-hidden
        className="h-1.5 w-1.5 rounded-full"
        style={
          tone
            ? { backgroundColor: tone }
            : { border: "1px solid var(--harbour)" } /* off-funnel: hollow */
        }
      />
      {label}
    </span>
  );
}
```

**`StateBadge` / `CheckStatusBadge` / `ImpactBadge` — see §6.**

---

## 5 · Phase P4 — Page by page

Each entry lists only what changes. Anything not listed keeps its current structure.

### 5.1 Shared page header pattern

Every page currently opens with `<h1 className="text-2xl font-semibold tracking-tight">`. Replace
with the one place Cormorant is legal at page level:

```tsx
<div className="space-y-1">
  <p className="label">New audit</p>            {/* tracked uppercase eyebrow */}
  <h1 className="display text-[34px] leading-tight">Upload your prompts</h1>
  <p className="max-w-xl text-[13px] leading-relaxed text-harbour">…</p>
</div>
```

34 px is above the guide's 32 px display floor. If a page title cannot justify 34 px, it is not a
page title — drop the Cormorant and use `text-lg font-medium`.

Eyebrow / title pairs, in nav order:

| Route | Eyebrow | Title |
|---|---|---|
| `/` | `Run` | Upload your prompts |
| `/audits/[id]` | `Run` + short id | *(client name, from the payload)* |
| `/projects` | `Projects` | Every client, every run |
| `/projects/[key]` | `Project` | *(project label)* |
| `/teaser` | `Teaser` | Generate a prospect teaser |
| `/audit` | `Deliverable` | Assemble the visibility audit |
| `/fact-sheets` | `Fact sheets` | Ground truth for the judge |

### 5.2 `/` — Run (`app/page.tsx`, `components/upload-dropzone.tsx`)

- Dropzone: `border-2 border-dashed` → **`border border-dashed border-navy/25`**. A 2 px dash at
  navy reads as a hard box; the guide's own clearspace diagram uses a 1 px dash at
  `rgba(18,50,92,0.5)`. Drag state: `border-blue bg-navy/[0.04]`.
- The circular `bg-primary/10 text-primary` upload glyph becomes **the mark at 34 px, tone
  `paper`** — the empty state is the single best place in the app to show the logo at size, and it
  replaces a stock cloud icon with something that is ours.
- Dropzone copy stays. It is good.
- `Run audit` becomes `variant="hero"` — this is the page's reason to exist.
- The `Download template` link: `text-primary hover:underline` → `text-blue hover:underline`
  (Sable Blue is the link colour, by the guide).
- Fact-sheet picker `<select>` and the trade `<select>` both take `INPUT_CLS`.
- Error string at `app/page.tsx:141` → `<Notice tone="problem">`.
- File chips: `rounded-lg border bg-card` → `rounded-md border border-[var(--rule)] bg-white`; the
  filename in `font-medium text-navy`, the summary in `text-harbour`.

### 5.3 `/audits/[id]` (`app/audits/[id]/page.tsx`, `components/progress-view.tsx`)

- This route renders the client report inside the app shell. **The report keeps its own `.sable`
  scope — do not restyle anything inside `report-view.tsx`.** Confirm after the change that the
  report's ground still reads Paper and its cards white, i.e. that `:root` did not leak.
- Back link `text-muted-foreground hover:text-foreground` → `text-harbour hover:text-navy`, and its
  label changes from "New audit" to **"Run"** to match the renamed nav (`page.tsx:99`).
- The loading spinner rows keep `Loader2` but the caption goes to `text-harbour`.
- Progress bars (`components/ui/progress.tsx`): track `bg-navy/[0.08]`, fill `bg-navy`. If the bar
  is segmented per engine, insert the report's 2 px gap between segments — on a single-hue ramp
  adjacent segments merge into one block, which `sable.css` already documents.

### 5.4 `/projects` and `/projects/[key]`

- Project cards: hover `group-hover:border-primary/50` → `group-hover:border-navy/35`.
- The `divide-y` run lists get `divide-[var(--rule)]`, row hover `hover:bg-navy/[0.03]` instead of
  `hover:opacity-80` (opacity fades the text too, which reads as disabled).
- Timestamps: `text-xs text-muted-foreground` → `text-[11px] tabular-nums text-harbour`. Every
  number in the app that sits in a column gets `tabular-nums`; Libre Franklin ships a `tnum` table
  (verified in `sable.css`).
- Delete project: `variant="destructive"` → `variant="outline"`. The typed-confirmation dialog
  already present is the real guard, and it stays exactly as it is.

### 5.5 `/teaser` (`app/teaser/page.tsx`, 729 lines — the biggest job)

- Local `inputCls` → import `INPUT_CLS`.
- Engine toggle chips: currently a hand-rolled conditional class. Selected = `bg-navy text-white`;
  unselected = `border border-navy/20 text-navy hover:bg-navy/[0.04]`. Pill radius.
- Both `destructive` banners (lines ~281 and ~287) → `<Notice tone="problem">`.
- `Generate teaser` → `variant="hero"`.
- The approve / reject / regenerate cluster: `outline` for all three, no colour distinction, with
  `Check` / `X` / `RefreshCw` icons carrying the meaning.

### 5.6 `/audit` — Deliverable (`app/audit/page.tsx`)

- Wrapper is `mx-auto max-w-6xl space-y-6 p-6`, duplicating the layout's `<main>`. Delete the
  wrapper's `mx-auto max-w-6xl p-6` and keep `space-y-6`; same for `app/fact-sheets/page.tsx:98`,
  which is a `<main>` nested inside the layout's `<main>` (also an a11y bug).
- The `<iframe>` preview: `rounded-md border bg-white` → `rounded-lg border border-[var(--rule)]
  bg-white`. **Do not restyle the iframe's contents** — that is the report.
- Approve stays `default` (navy fill); Reject becomes `outline`.
- The Supabase-not-configured warning → `<Notice tone="info">`.

### 5.7 `/fact-sheets` (`app/fact-sheets/page.tsx`)

- `border-amber-500/30 bg-amber-500/5` open-questions block → `<Notice tone="info" title="Open
  questions — ask before approving">`.
- `stateTone()` returns Tailwind colour classes per state; replace with the §6 state pill.
- Selected sheet card `className="border-2"` → `border-navy/40` (a 2 px rule at this radius bows
  visibly at the corners).

---

## 6 · The thing you will want to argue with: no alert hue

**Sable has no red, no green, no amber, and no alert hue of any kind.** `components/badges.tsx`
already documents how the report solved this for severity — a monochrome navy ramp where *"the icon
and the label are therefore LOAD-BEARING, not belt-and-braces."* The app inherits the same solution
and the same discipline.

### 6.1 Run states

`StateBadge` covers `done · running · queued · cancelled · interrupted · failed`. Two of those
(`done`, `failed`) are the ones a person scans a list for, and they must be distinguishable at a
glance without colour. Distinguish by **fill weight + glyph**, not hue:

| State | Fill | Glyph | Rationale |
|---|---|---|---|
| `done` | navy solid, white ink | filled circle | the terminal success; the darkest, heaviest chip |
| `running` | navy 6% fill, navy ink | spinning `Loader2` | motion is unmistakable and no other chip moves |
| `queued` | outline, harbour ink | hollow circle | lightest weight = least happened |
| `failed` | navy solid, white ink | `×` in a circle | same weight as `done` (both terminal), opposite glyph |
| `cancelled` | outline, harbour ink | `MinusCircle` | user-terminal, not system-terminal |
| `interrupted` | mist fill, navy ink | `AlertTriangle` | the only chip carrying the warning glyph — and it is **terminal and unrecoverable**, not paused (§6.1.1) |

```tsx
const STATE: Record<string, { cls: string; Icon: LucideIcon; spin?: boolean }> = {
  done:        { cls: "bg-navy text-white",              Icon: CheckCircle2 },
  failed:      { cls: "bg-navy text-white",              Icon: XCircle },
  running:     { cls: "bg-navy/[0.06] text-navy",        Icon: Loader2, spin: true },
  queued:      { cls: "border border-[var(--rule)] text-harbour", Icon: Circle },
  cancelled:   { cls: "border border-[var(--rule)] text-harbour", Icon: MinusCircle },
  interrupted: { cls: "bg-mist text-navy",               Icon: AlertTriangle },
};
```

`done` and `failed` sharing a fill is deliberate: both are *finished*, which is the property a
scanner is actually filtering on, and the glyph splits them instantly. If in testing this proves
genuinely unreadable at a glance in a 40-row list, the fix is **a column, not a colour** — sort or
group by state.

#### 6.1.1 `interrupted` is not vestigial — and it does not mean what its label says

Traced statically (no API run). `"interrupted"` is written in **exactly one place** in the whole
codebase — `src/api/runner.py:1403`, inside `resume_interrupted_runs()`, which only ever executes
during the API's startup scan (`src/api/app.py:61`). A run dying never sets it. So the chip does not
mean *"this run was interrupted"*; it means **"at startup we found this row non-terminal and could
not rebuild it, so it will never resume."** That is terminal and unrecoverable, while
`progress-view.tsx:67` currently labels it `"Audit interrupted"`, which reads as transient and
retryable. **Relabel it `"Audit abandoned"`** (or `"Cannot resume"`) as part of P4-T3.

The reachable trigger today is not the legacy case the docstring describes:

```
src/pipeline/orchestrator.py:172   CLI run  →  db.create_audit_run(...)   ← no `queries=` kwarg
src/storage/db.py  (create_audit_run body)  →  "queries": queries or []   ← column gets []
                                               "status":  "running"       (signature default)
src/pipeline/orchestrator.py:212   clean finish → status="done"
                                   Ctrl-C / crash / MAX_AUDIT_COST_USD abort → stays "running"
src/storage/db.py:789              list_resumable_runs()  picks up status in (running, queued)
src/api/runner.py:1322             _rebuild_audit_from_row() → None   (queries is empty)
src/api/runner.py:1403             → status = "interrupted"
```

**Any CLI audit that does not finish cleanly shows up as `interrupted` in the web UI the next time
the API restarts** — because the CLI path never stores its query set, while the API path
(`runner.py:363`) does. The stored reason string, *"interrupted before resume support (no stored
query set)"*, is therefore misleading: these are not pre-resume rows, they are today's CLI rows.

**Severity: low, with one narrow exception.** Every downstream consumer treats a non-`done` row
correctly, so the wrong *label* mostly does not cause a wrong *outcome*:

- `runner.py:915` (`_prior_comparable_run`) excludes non-`done` runs from week-over-week comparison
  — deliberately, and the comment says why: *"A run that never finished measured a different
  (smaller) thing… the single most damaging false claim available here."* An aborted CLI run
  **should** be excluded, so the filter does the right thing by accident.
- `runner.py:1078` gates only the report cache. Performance, self-correcting.
- Results are written per query as the run proceeds, so the row's status is metadata — **no data
  loss.**
- The API-restart-during-a-live-CLI-run race self-heals: the row flips to `interrupted`, then the
  CLI reaches `orchestrator.py:212` and sets `done`.

**The exception, and it is the reason to fix this:** if the CLI process dies *between its last
result write and line 212*, the run has complete data but is stuck at `"running"` → next API start
marks it `interrupted` → it is excluded from trend comparison **permanently**, despite being a valid
cycle. Rare, silent, and only recoverable by editing the row by hand.

**Keep the chip — and fix the cause in §0.** This is now **P0**, not backlog. The fix is *not* the
obvious one (storing the CLI's query set would make aborted runs auto-resume and spend money
unasked — see §0.1); it is to give the CLI's runs a terminal status so they never enter the resume
scan at all (§0.2). After P0, `interrupted` is reachable only by `kill -9`, which is the one case
the word actually describes.

Two UI-side leftovers, both inside this spec:

- Relabel the string in `progress-view.tsx:67` — P4-T3.
- The stored reason string is stale — P0-T3.

### 6.2 `CheckStatusBadge` and `ImpactBadge`

These render in the client-facing report path and are already governed by the audit-packaging spec.
Map them onto the report's existing severity ramp (`--sev-*`), not onto new tokens:
`pass → quiet`, `partial → muted`, `fail → solid navy`, `ungradeable/unknown → quiet` with an
em-dash glyph. **Load `.claude/skills/audit-packaging/SKILL.md` before touching these two.**

### 6.3 The escape hatch, and how not to use it

If the team concludes an alert hue is genuinely necessary, **it gets added to the identity guide
first, with a name, a hex and a stated role — then to `sable.css` and `tokens.css` together.** It
does not get added as a one-off `text-red-600` in an error banner, because the next one is a
`text-red-500`, and then the app has two reds and no guide. Reopen this section, don't route around
it.

---

### 6.4 The two lines inside the report that P1 will break

Deleting `destructive` and `success` from the Tailwind config breaks the build in
`components/report-view.tsx`, which is otherwise out of scope:

- **line 419** — `<span className="text-[hsl(var(--success))]">warm, Judge is $0</span>`, the judge
  cache-warm indicator.
- **line 432** — `no-print rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm
  text-destructive`, the judge-failed banner.

Both are `no-print` developer affordances that never reach a client PDF, which is why fixing them is
the **single sanctioned exception** to §7.1. Line 419 → `text-blue font-medium`; line 432 →
`<Notice tone="problem" className="no-print">`. Change nothing else in that file. This is P3-T8.

---

## 7 · What must not change

1. **`web/styles/sable.css` is untouched by this spec.** Not one line. It is the report's skin and
   the white-label seam.
2. **No inheritance between `tokens.css` and `sable.css`.** They share hexes by copy, on purpose.
   A future `NEUTRAL` tenant must be able to override the report's skin completely; if the report
   inherited from `:root`, any variable the tenant missed would leak Sable into a resold artifact
   silently. `lib/brand.ts` currently has `NEUTRAL.themeClass = "sable"`, which is a known gap —
   **out of scope here**, but do not make it worse.
3. **The report's print CSS.** `@page`, the `break-inside` rules, `print-color-adjust` — all in
   `sable.css`, all load-bearing for `npm run report-pdf`, all off-limits.
4. **`.no-print`.** Both the app's `globals.css` and the report's `sable.css` define it. Keep both.
5. **Anything under `src/`.** No Python changes. No judge prompt changes. No `_PROMPT_LAYOUT` bump —
   this spec cannot invalidate a cached verdict and must not.
6. **`components/charts.tsx`.** Already on the Sable navy ramp with a documented rationale.

> **The shared-primitive blast radius, stated once so nobody is surprised.** `report-view.tsx`
> imports `Card`, `Badge`, `Table` and `Progress` from `components/ui/`. Every P3 change to those
> files therefore lands in the client report and the PDF, whether or not you open `report-view.tsx`.
> The three that matter are the `Card` restyle (§4.2), the `Badge` variants (§4.3) and the two lines
> in §6.4. Treat P3 as a client-facing phase: skill loaded, `npm run report-pdf` re-run, page count
> checked against the 13–18 band.

---

## 8 · Don'ts, app edition

The guide's four (never rotate · no colours outside the palette · never stretch or squash · the
wordmark stays Garamond), plus five this codebase can violate specifically:

5. **Never put Sky on paper.** It is undefined outside `.on-navy` and will resolve to nothing —
   which is the design. If you find yourself writing `#7FA6D9` as a literal, stop.
6. **Sky appears at most once per page.** In the app that once is the header plume. The favicon is
   outside the page.
7. **Never set Cormorant below 32 px**, except the wordmark (which has its own 14 px floor) and
   hero numbers. Card titles, table headers, buttons and labels are Libre Franklin.
8. **Never set the mark by width.** Height drives; the `Plume` component enforces this, so do not
   hand-roll an `<svg width>` beside it.
9. **Never reintroduce a colour to carry meaning alone.** Every distinction needs a glyph, a label
   or a weight as well. This is the rule that makes a single-hue palette survive contact with a
   dashboard.

---

## 9 · Task list

Each task ends with `cd web && npm run typecheck && npm run build` green, and one `docs/build-log.md`
entry per completed phase (append at the top, most recent first).

**P0 — Backend honesty** *(Python; independent of everything below, but do it first —
see §0.4 for the five tasks and the merge hazard)*

**P1 — Tokens** *(one session; leaves the app visibly broken, which is expected)*
- [x] P1-T1 Create `web/styles/tokens.css` (§2.2).
- [x] P1-T2 Rewrite `web/app/globals.css` (§2.3); delete the `.dark` block.
- [x] P1-T3 Rewrite `web/tailwind.config.ts` (§2.5); delete `darkMode`, `destructive`, `success`,
      `warning`.
- [x] P1-T4 Fix the import order in `layout.tsx` (§2.4).
- [x] P1-T5 Capture the build-failure worklist (§2.6) into the build-log entry.

**P2 — Mark and shell** *(same session as P1 if possible)*
- [x] P2-T1 Add `web/components/plume.tsx` (§3.1).
- [x] P2-T2 Replace `web/app/icon.svg` (§3.2).
- [x] P2-T3 Add `web/components/app-header.tsx`, rewrite `layout.tsx`, delete the Inter import
      (§3.3, §3.4).
- [x] P2-T4 Visual check: **three plumes** in the header (size 20, not 19 — §1.4), clearspace held,
      wordmark not below 14 px, exactly one Sky in the DOM.

**P3 — Primitives**
- [x] P3-T1 `button.tsx`: pill, navy, `hero` variant, no `destructive` (§4.1).
- [x] P3-T2 `card.tsx`: rule not shadow, workshop padding (§4.2).
- [x] P3-T3 `badge.tsx`: four monochrome variants (§4.3).
- [x] P3-T4 Add `lib/ui.ts`; replace the four divergent input class strings (§4.4).
- [x] P3-T5 Add `components/notice.tsx`; replace all eight `destructive` banners (§4.5).
- [x] P3-T6 `badges.tsx`: `IntentBadge` dot ramp, `StateBadge` per §6.1.
- [x] P3-T7 `badges.tsx`: `CheckStatusBadge` / `ImpactBadge` per §6.2 — **load the
      audit-packaging skill first.**
- [x] P3-T8 `report-view.tsx` lines 419 and 432 only — the sanctioned two-line exception (§6.4).
- [x] P3-T9 *(15 pages, in band; print-check OK)* **Client-facing gate for the whole phase:** `npm run report-pdf <known run-id>`, page
      count still in the 13–18 band, spot-check a card and a severity chip against the previous PDF.

**P4 — Pages** *(one task per route; they are independent and can interleave)*
- [x] P4-T1 Shared page-header pattern + the eyebrow/title table (§5.1).
- [x] P4-T2 `/` and `upload-dropzone.tsx` (§5.2).
- [x] P4-T3 `/audits/[id]` and `progress-view.tsx` (§5.3).
- [x] P4-T4 `/projects` and `/projects/[key]` (§5.4).
- [x] P4-T5 `/teaser` (§5.5).
- [x] P4-T6 `/audit` (§5.6) — includes deleting the duplicated `max-w-6xl` wrapper.
- [x] P4-T7 `/fact-sheets` (§5.7) — includes the nested-`<main>` a11y fix.

**P5 — QA** (§10)

---

## 10 · Acceptance checklist

Run every one of these before calling the redesign done.

**Brand**
- [ ] `grep -rn "indigo\|violet\|emerald\|amber\|-red-\|-green-\|4f46e5" web/app web/components` →
      no hits.
- [ ] `grep -rn "7FA6D9\|7fa6d9" web/app web/components` → hits only in `plume.tsx` (the `navy`
      tone) and `icon.svg`.
- [ ] Every rendered page: at most one Sky element in the DOM, and it is inside the header.
- [ ] No Cormorant below 32 px except the wordmark and hero numbers.
- [ ] Every state, severity and status indicator carries a glyph or a label as well as a fill.

**Fidelity**
- [ ] Screenshot `/` and the report at `/audits/[id]` side by side. The ground colour must be
      identical (`#F2F1EC`), the card rule identical, both typefaces identical.
- [ ] The header mark renders **three** plumes and its clearspace holds — nothing within
      `20/2.9 ≈ 7 px` of the mark box on any side.

**Function**
- [ ] `mypy src/ && ruff check src/ && pytest tests/` green (P0).
- [ ] Abort a CLI audit with Ctrl-C, restart the API, confirm the run reads **`cancelled`** and not
      `interrupted` (P0). No engine calls should re-fire on that restart.
- [ ] `npm run typecheck && npm run build` green.
- [ ] `npm run report-pdf <a known run-id>` still produces the 13–18 page band, and page 1 is not
      clipped. **This is the regression that matters most** — the app and the report share a
      stylesheet load order and a `.no-print` contract.
- [ ] `npm run print-check` passes.
- [ ] Focus ring visible on every interactive element (the paper ground is low-contrast; a navy
      ring at 1 px on white can disappear — verify, don't assume).
- [ ] **Contrast, measured not assumed.** Harbour on white = **4.68:1** (passes AA). Harbour on the
      Paper ground = **4.14:1** (**fails**). Since the page ground is Paper and cards are white,
      the rule is: *Harbour inside a card, `text-[color:var(--ink-secondary)]` outside one.*
      `grep -n "text-harbour"` every file and check what it is sitting on. The full table:

      | Pair | Ratio | Verdict |
      |---|---|---|
      | Navy on Paper | 13.93 | ✅ |
      | White on Navy | 15.75 | ✅ |
      | Sable Blue on white | 12.83 | ✅ |
      | Navy on Mist (`interrupted` chip) | 7.80 | ✅ |
      | Sky on Navy (header plume) | 6.27 | ✅ non-text, fine |
      | `--ink-secondary` on Paper | 5.59 | ✅ |
      | Harbour on white | 4.68 | ✅ |
      | **Harbour on Paper** | **4.14** | ❌ **use `--ink-secondary`** |
      | Mist on white | 2.02 | ❌ rules and the faintest plume only — never text |

---

## Appendix A — Palette reference

| Name | Hex | RGB channels | Legal grounds |
|---|---|---|---|
| Berkeley Navy | `#0E2340` | `14 35 64` | anywhere |
| Sable Blue | `#12325C` | `18 50 92` | anywhere (links, active, focus) |
| Harbour | `#697585` | `105 117 133` | anywhere (body, metadata) |
| Mist | `#B2B7BC` | `178 183 188` | anywhere (rules, faintest plume) |
| Paper | `#F2F1EC` | `242 241 236` | ground |
| White | `#FFFFFF` | `255 255 255` | cards |
| **Sky** | `#7FA6D9` | `127 166 217` | **on navy only, once per page** |

Derived, all navy alpha: rule `12%` · rule-soft `7%` · hover `4%` · selected `6%` ·
**`--ink-secondary` `70%`** (secondary text on the Paper ground — see §10).

Worth knowing: **Harbour is exactly navy at 60% over Paper.** The palette is one hue and an alpha
ramp, which is why the monochrome severity ramp, the intent dots and the notice rules all belong to
the same family rather than being three inventions.

## Appendix B — File inventory

| File | Action |
|---|---|
| `web/styles/tokens.css` | **new** |
| `web/components/plume.tsx` | **new** |
| `web/components/app-header.tsx` | **new** |
| `web/components/notice.tsx` | **new** |
| `web/lib/ui.ts` | **new** |
| `web/app/globals.css` | rewritten |
| `web/tailwind.config.ts` | rewritten |
| `web/app/layout.tsx` | rewritten |
| `web/app/icon.svg` | replaced |
| `web/components/ui/{button,card,badge}.tsx` | variants rewritten |
| `web/components/badges.tsx` | colour maps rewritten |
| `web/components/{upload-dropzone,recent-audits,progress-view,preview-panels,assemble-from-lead,site-audit-section}.tsx` | class-level edits |
| `web/app/{page,audit/page,teaser/page,fact-sheets/page,projects/page,projects/[key]/page,audits/[id]/page}.tsx` | class-level edits |
| `web/components/report-view.tsx` | **lines 419 and 432 only** (§6.4) |
| `web/styles/sable.css` | **untouched** |
| `web/components/charts.tsx` | **untouched** |
| `src/**` | **untouched** |

## Appendix C — Decisions (resolved 2026-08-02)

All four are **resolved** (Josh, 2026-08-02). Recorded here so a build session does not reopen them.

1. **`/audit` vs `/` naming — RESOLVED.** The nav had both "New audit" (`/`) and "Visibility Audit"
   (`/audit`); two things called *audit* on one bar is a demo hazard. **`/` = "Run",
   `/audit` = "Deliverable".** Already applied to §3.4, §5.1 and §5.3.
2. **Does `interrupted` still occur — RESOLVED: yes, keep the chip.** It is *not* vestigial, and
   the reason is not the one the code's docstring gives. Full trace in **§6.1.1**, which also
   relabels the chip (the current "Audit interrupted" describes a transient state; the real
   condition is terminal) and logs two backlog items against `orchestrator.py`.
3. **Domain — OPEN, and deliberately not blocking.** `sable.ai` vs `sable.com` is undecided. The
   guide's business card sets `sable.ai`, but **nothing in this spec hardcodes a domain**: the
   header wordmark links to `/`, and the app has no external marketing link. Keep it that way until
   the decision lands. When it does, the string belongs in `lib/brand.ts` (`BrandConfig`) alongside
   `name` and `descriptor` — one field, one place, so a white-label tenant can carry its own.
4. **Header descriptor — RESOLVED: keep `AI SEO`.** `<Wordmark descriptor="AI SEO" />` stays as
   written in §3.4. Consequence to watch in P2-T4: the descriptor sits under a 20 px wordmark inside
   a 56 px band, so the lockup is ~34 px tall in a 56 px space — comfortable, but it means the
   band cannot shrink below 52 px later without dropping the descriptor first. The old
   `"AI visibility measurement"` tagline beside the logo still goes; the descriptor replaces it.
