# Marketing Website — Sitemap & Copy Draft

Status: draft v1 (2026-07-20). Audience: general ("your business") — flexes between
local SMBs and startups via examples, per founder decision. Primary CTA: **Free AI
Visibility Check** (feeds the teaser pipeline). Secondary CTA: **Book a call**.

Copy rules baked in throughout (from gtm-legal-readiness.md + smb-pivot-plan.md):
never guarantee placement or rankings; report sampled rates, not point-in-time ranks;
every statistic carries a named source; no "AI domination" language. Honesty is the
positioning, not just the legal posture.

`[Brand]` = placeholder until you pick a name. `[$X]` = pricing placeholders.

---

## 1. Sitemap

```
/                    Home
/free-check          Free AI Visibility Check  ← primary conversion page
/sample-report       Sample Report (anonymized real teaser)
/how-it-works        Methodology
/pricing             Pricing
/learn               Learn hub (FAQ-style articles)
/learn/<slug>        Individual articles
/about               About the founders
/contact             Contact / Book a call
/our-score           We audited ourselves (dogfood page)
```

Navigation: Home · How it works · Sample report · Pricing · Learn · About — with
"Free visibility check" as a persistent button-styled nav item. Footer: full page
list, business name + city (NAP), email, LinkedIn links for both founders.

Rule: every page has the primary CTA visible without scrolling back up (sticky
header button), and no page is more than one click from /free-check or /contact.

---

## 2. Page-by-page copy

### Home (/)

**Hero**

> ## When someone asks AI for a recommendation, does it say your name?
>
> ChatGPT, Google AI, and Perplexity now answer your customers' questions directly —
> and they only name a few businesses per answer. [Brand] measures whether you're
> one of them, who's being named instead, and what's driving the answer.
>
> [ Get your free AI visibility check ]   [ See a sample report ]

**Stat bar** (3 tiles, each with source line)

- "45% of U.S. consumers used AI tools to find local businesses last year — up from
  6% the year before." — BrightLocal, 2026
- "AI answers surface ~3× fewer businesses than traditional search results." —
  Sterling Sky / Places Scout, 322-market study
- "Google shows an AI-generated answer on roughly 2 of 3 local-business searches —
  and 9 of 10 informational ones." — Whitespark, 2025 (68% overall / 92%
  informational; never pair "informational" with the 68% figure)

**Problem section — "The shortlist got smaller"**

When a customer asks Google or ChatGPT "best {your category} near me" or "which
{product} should I buy," the answer isn't ten blue links anymore. It's a paragraph
that names two or three options. If you're not in that paragraph, you're not in the
conversation — and you can't see it happening, because everyone's answer looks
different and nobody screenshots the AI that *didn't* mention them.

**What we do — "We measure it. Properly."**

We run the questions your customers actually ask across ChatGPT, Google's AI
answers, Gemini, and Perplexity — each question multiple times, because AI answers
change run to run. Then we judge every answer: Were you mentioned? How prominently?
Was what the AI said about you *accurate*? Who got recommended instead? And which
websites is the AI citing when it decides?

You get numbers, not vibes: mention rates ("named in 4 of 5 runs"), share of voice
against named competitors, the queries you're losing, and the exact sources behind
the answers.

**How it works (3 steps)** — condensed from /how-it-works, with link

1. **We ask** — a versioned set of real customer questions, run across every major
   AI engine, multiple times each.
2. **We judge** — every answer graded for your presence, prominence, and accuracy
   against a fact sheet you approve.
3. **You get a roadmap** — a report with your numbers, your gaps, and a prioritized
   list of fixes ordered by what actually moves AI answers.

**Honesty block — "What we won't promise"**

Nobody controls what ChatGPT says — anyone who guarantees you a #1 spot in AI
answers is selling something they can't deliver. What we deliver is measurement:
where you stand, how it changes over time, and which fixes have evidence behind
them. Our reports show sampled rates with honest uncertainty, because that's the
only claim that survives contact with how these systems actually behave.

**Sample report strip** — 2–3 report screenshots, link to /sample-report.

**Final CTA**

> ## Find out what AI says about you. Free.
> Takes one minute. We'll email your report within 1–2 business days.
> [ Get your free AI visibility check ]

---

### Free AI Visibility Check (/free-check) — THE conversion page

This is where cold-email links land. Minimal nav, zero distractions.

> ## What does AI say when customers ask about businesses like yours?
>
> Tell us who you are. We'll run real customer questions through ChatGPT, Google's
> AI answers, and Perplexity, and email you a short report: whether you're
> mentioned, who's named instead of you, and which sources are shaping the answer.
> Free, no call required.

**Form fields:** Business name · Website · City / service area · What do you do?
(short free text) · Email. One button: **Run my free check**.

**Under the form ("What you'll get"):** verbatim excerpts of what the AI engines
said · the competitors named instead of you, by name · the sources the AI cited ·
whether AI bots can even read your website.

**Confirmation state:** "Got it — we're running your check. Your report will land
in your inbox within 1–2 business days." (Buys time for the teaser pipeline +
manual review; captures the email regardless.)

Ops note: submissions go to a queue you vet before spending API budget — protects
`MAX_AUDIT_COST_USD` from freebie floods and lets Josh prioritize real prospects.

---

### Sample Report (/sample-report)

> ## This is what you actually get.

An anonymized real teaser ("Berkeley plumbing company, May 2026" or an early
startup client), shown as rendered pages, annotated with margin notes:

- Verbatim AI answers with the client's absence highlighted
- The competitor names that appeared instead
- Mention-rate table ("mentioned in 2/5 runs on ChatGPT, 0/5 on Google AI")
- The cited-sources checklist (red/yellow/green)
- The prioritized fix list from the full audit

Close with: "Want yours? → Free visibility check."

---

### How It Works (/how-it-works)

Transparency page = credibility page = GEO content. Question-form H2s throughout
(each is FAQPage-schema fodder):

- **Which AI engines do you measure?** ChatGPT, Google AI Overviews / AI Mode,
  Gemini, Perplexity, Claude — both what models "know" and what they find when
  they search live.
- **Why do you run every question multiple times?** AI answers change between
  runs — a single fetch is a coin flip. We sample repeatedly and report rates.
  Anyone showing you a single-run "AI rank" is measuring noise.
- **How do you judge the answers?** Every answer is graded for presence,
  prominence, and accuracy against a fact sheet about your business that you
  approve — so "the AI mentioned you but got your pricing/hours/services wrong"
  is a finding, not a blind spot.
- **What's in the audit?** Beyond visibility: can AI crawlers read your site at
  all (many firewalls silently block them), does your content exist without
  JavaScript, structured data, whether the sources AI cites in your category even
  know you exist.
- **Can you guarantee results?** No — and no one honest can. [Repeat the honesty
  block.]

---

### Pricing (/pricing)

Three tiers, ascending commitment:

1. **Free Visibility Check — $0.** The short report. Where you stand on the big
   three engines, who's named instead of you. *[Get started]*
2. **Full AI Visibility Audit — [$X] one-time.** Full query set across all
   engines, sampled runs, judged answers, accuracy findings, site + off-site
   audit, prioritized roadmap. Delivered as a report + a walkthrough call.
3. **Ongoing Measurement — [$X]/mo.** We re-run your audit on a cadence and show
   what changed: before/after mention rates, new competitors, new sources.
   Because AI answers move — the point is the trend line.

FAQ under pricing: "Do you do the fixes too?" (answer per your current service
scope) · "How long until AI answers change?" (honest: weeks-to-months, and we
measure rather than promise) · "What do you need from me?" (a fact sheet + 30 min).

---

### Learn (/learn) — the GEO content engine

Launch with 5 articles, each answer-first (first paragraph is the quotable
answer), each targeting a question AI engines themselves get asked:

1. What is GEO (Generative Engine Optimization)?
2. Why doesn't ChatGPT mention my business?
3. Which sources do AI engines actually cite? (category-by-category, with data)
4. Is your website invisible to AI crawlers? (the CDN/WAF-blocking problem)
5. AI search vs. traditional SEO: what actually changed?

These pages are how *[Brand]* itself gets cited by AI engines — your customers'
first question to ChatGPT is often "what is GEO / why am I not in AI results,"
and these are the pages that answer it.

---

### About (/about)

> ## Two founders, measuring the thing everyone else is guessing about.

Real names, real faces, real city. Abhi (technical — built the measurement
platform) and Josh (works directly with every client). Why you started it, one
paragraph each. E-E-A-T is a ranking input for the engines you sell visibility
in — practice what you preach: Person schema for both, LinkedIn links, Berkeley
NAP in the footer.

---

### Our Score (/our-score) — the dogfood page

> ## We ran our own audit on this website. Here's the report.

Publish the actual Cat 1–6 results for the marketing site itself, and the mention
rates for "[Brand]"-related queries, updated on a cadence, dated. Close: "This is
the exact report you'd get. → Free visibility check."

This page is the single most differentiating thing on the site — no competitor
publishes their own audit of themselves.

---

### Contact (/contact)

Short. Email, scheduling embed for a 20-minute call with Josh, and the form as a
fallback. "Prefer to see your numbers first? → Free visibility check."

---

## 3. GEO rubric build checklist (dogfooding Cat 1–6)

- **Rendering (Cat 2):** Fully static / server-rendered HTML. Every word of copy
  and all schema present in the raw HTML response with JavaScript disabled. No
  client-only rendering for content.
- **Bot access (Cat 1):** robots.txt explicitly allows GPTBot, ClaudeBot,
  Claude-SearchBot, PerplexityBot, Google-Extended, Bingbot, CCBot. Verify the
  host/CDN (Vercel) isn't challenge-blocking them. Add to CI (see §4).
- **Schema (Cat 5):** Organization + ProfessionalService on home; FAQPage on
  /how-it-works, /pricing FAQ, /learn articles; Service on /pricing; Person
  (both founders) on /about; Article on /learn posts. Schema content must match
  visible text (your own validator checks this).
- **Content structure (Cat 3/4):** Question-form H2s; answer-first paragraphs
  (the first sentence under each heading is the standalone, quotable answer);
  cited statistics with named sources (citation bait); consistent NAP in the
  footer of every page.
- **Hygiene:** sitemap.xml, canonical URLs, unique titles/meta descriptions, OG
  tags, fast static pages. Per your own research discipline: no llms.txt (Google
  has said it doesn't use it — don't ship theater you'd flag in a client audit).

## 4. Playwright QA loop (build + CI)

1. **Design iteration:** screenshot every page at 390px / 768px / 1440px after
   each change; critique against the clean-and-conventional bar; fix; repeat.
2. **GEO self-check (the mini-audit, run on every deploy):** fetch each page with
   JS disabled → assert full copy + JSON-LD present in raw HTML; fetch as GPTBot/
   ClaudeBot/PerplexityBot user agents → assert 200s, no challenge pages; validate
   JSON-LD parses and required types exist per page.
3. **Funnel tests:** from every page, reach /free-check in ≤1 click; submit the
   form end-to-end; confirmation renders; queue receives the entry.
4. **Competitor reference shots:** Profound, Peec, Otterly, Local Falcon,
   BrightLocal — side-by-side screenshots for layout/tone reference (conventional
   and clean, not novel).

## 5. Conversion flow map

```
Cold email / LinkedIn / AI citation / word of mouth
        → /free-check  (or Home → /free-check)
        → email report (1–2 days; teaser pipeline + manual vet)
        → Josh follow-up: "want the full picture?" → /pricing or call
        → Full Audit [$X]
        → walkthrough call → Ongoing Measurement [$X]/mo
```

Instrument each step (simple analytics: form submits, report-email link clicks,
call bookings) so you know where the funnel leaks.

## 6. Decisions & open items (updated 2026-07-20)

**Decided:**

- Stack: **Next.js static export, deployed on Vercel.** One framework across the
  repo; satisfies the Cat 2 SSR/static requirement.
- /free-check submissions: **manual queue at launch.** Vet each submission, then
  run the teaser and email the report ("within 1–2 business days" promise).
- Run-count language: **site copy states what the instrument actually does** —
  `RUNS_PER_QUERY=5` for the paid audit (teaser runs 3×). Examples above say n/5
  for that reason. If we want a bigger-K story (the volatility data argues for
  more runs, not fewer), bump the config first, then the copy.

**Still open:**

- Brand name + domain (blocks: logo, NAP, schema, sending-domain setup from the
  GTM doc — same domain decision). Build with `[Brand]` placeholders meanwhile.
- Pricing numbers for tiers 2 and 3. Build /pricing with `[$X]` placeholders.
- Which past run becomes the /sample-report content — pick the stored audit/teaser
  with the most vivid story (client absent, competitors named, clear fix list),
  anonymize it; or run the teaser on a real local business and anonymize that.
  Doesn't block building the rest of the site.
