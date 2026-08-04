# The Fact-Sheet Question Set

*Sixteen questions, one set, every business. This document is only the questions —
what each one asks, why it exists, what claim it produces, and proof that it
survives contact with six different kinds of business.*

**Scope:** the question set alone. The chat UI, the review screen, the API and
the build sequence live in `docs/factsheet-intake-design-plan.md` and
`docs/factsheet-intake-agent-plan.md`. Those two remain the build specs; this is
the source they should agree with on question wording and structure.

**Revision:** re-passed 2026-08-04 against all six audiences. §5 lists the seven
things that pass changed and why.

---

## 1 · The four rules

Everything below is downstream of these. They come from
`docs/fact-sheet-template.md` and `docs/factsheet-autogen-plan.md` §4.

1. **Only falsifiable facts.** A price, a licence number, a closing time. Never
   "the leading platform." The judge can only check things that are true or
   false; a marketing line is a line that can never fire.
2. **Blank is safe, and it is the default.** A skipped question produces *zero*
   claims. A dimension the sheet is silent on is not checked, so it cannot
   produce a false flag. Coverage is not the metric — fourteen confirmed lines
   beat forty with six guesses. **Every one of the sixteen is skippable.**
3. **Negatives are where the value is.** *Closed Sunday.* *No phone support.*
   *Does not serve Marin County.* *Not admitted in Nevada.* These are what make
   an over-claiming AI answer flaggable. Nine of the sixteen questions carry a
   deliberate negative half, and they are the half that earns the demo.
4. **The owner sees the sentence they'll be quoted on.** Before a card commits,
   the UI renders the assertion the answer becomes — *"No after-hours service."* —
   not the raw input — *"No."*

**Why the answers matter more than the crawl.** A sheet's severity ceiling is set
by its *weakest* claim (`src/audit/factsheet/gate.py`). A crawl-only sheet is
permanently `public_source_only`, which caps it at LOW/MED. An owner's confirmed
answer is `client_confirmed`, which is the only way HIGH and CRITICAL flags ever
fire. Every question below exists to move one dimension across that line.

---

## 2 · The test — six audiences

A question is **robust** if all six of these can answer it truthfully without the
wording being changed. Where a question only worked for one or two, it got fixed
(§5), not forked.

| | Archetype | Stand-in | What makes it awkward |
|---|---|---|---|
| **A** | Local service | Albert Nahman Plumbing, Berkeley | Van, phone, towns, state licence |
| **B** | Consumer product | Oura (ring + app + membership) | Versions, retail, no service area |
| **C** | B2B SaaS | A project-management tool | Seats, SOC 2, **no phone, no address** |
| **D** | E-commerce / D2C | A coffee roaster | **Hundreds of SKUs**, shipping zones |
| **E** | Professional services | An employment law firm; a dental practice | **Jurisdiction**, hourly/contingency, bar admission |
| **F** | Wildcard (agency roster) | A nonprofit, a restaurant, a marketplace, a franchisee | Anything. This is the honest state of an agency's client list |

The only thing business type is allowed to change is the **for-instance** line
under a question. Never the prompt, never the helper, never whether the card
appears.

> **The maintenance rule:** if you want to reword a *prompt* for one archetype,
> the prompt is too narrow. Widen it, and put the specificity in the
> for-instance. A question that needed rewriting for a law firm would also have
> needed rewriting for the restaurant nobody thought of.

---

## 3 · The sixteen questions

Each entry: what the card asks · why it exists · the claims it produces · how all
six answer it.

---

### `Q-WHAT-01` — what we already found
**Kind** `batch_confirm` · **Section** `identity` · **Keys** `identity_name`, `identity_website`, `identity_founded`, `identity_category`

> **Quick check — tap anything that's wrong.**
> *Name · Website · In business since · What you'd call it*
>
> *For instance —* "What you'd call it" is the words you'd want an AI to use —
> "employment law firm", not "professional services company."

**Why.** Four dimensions in one tap. Only rows the crawl actually found are
rendered; a blank is omitted, never shown as an empty field. The category label
is the load-bearing one — it is the exact framing the judge checks *and* the slot
the query generator fills.

**Produces** four positive `identity` claims, each `client_confirmed`.

| | Answers it as |
|---|---|
| A | "Plumbing contractor" — not "home services company" |
| B | "Smart ring" — not "wearable platform" |
| C | "Project management tool" — not "work OS" |
| D | "Coffee roaster" — not "lifestyle brand" |
| E | "Employment law firm" / "general dentistry practice" |
| F | "Food bank", "neighbourhood Italian restaurant", "Sotheby's franchisee" |

---

### `Q-WHAT-02` — what it is
**Kind** `longtext` · **Section** `identity` · **Key** `identity_what`

> **In one sentence, what does {brand} actually do?**
> *Plain and factual. Skip the sales language — an AI can't be wrong about "the
> best", only about what you do.*
>
> *For instance —* local: "Family-owned plumbing contractor serving the East Bay
> since 1998." · product: "A smart ring that tracks sleep, recovery and
> readiness." · neutral: "A two-person design studio doing brand identity for
> restaurants."

**Why.** The card that "gets the idea of what the business is about." It is also
the one most likely to attract marketing language, so it carries the
unfalsifiable-word nudge (leading, best, premier, trusted, world-class,
innovative, award-winning) with a **Keep it anyway** escape. Never blocks —
refusing to let someone describe their own business is worse than one claim that
can't fire.

**Produces** one positive `identity` claim.

---

### `Q-WHAT-03` — other names
**Kind** `list` · **Section** `identity` · **Key** `identity_aliases`

> **Any other ways people write your name?**
> *Misspellings, your legal name, an old name. We use these to catch a mention
> we'd otherwise miss — they aren't fact-checked.*

**Why.** **This one produces no claim.** Name variants are a *matcher* input —
the brand roster in `docs/query-generation-plan.md` §1a — and asserting "Also
known as Acme Plumbing" would put a non-falsifiable line in front of the judge.
Without it, a mention gets missed and scores as absence, which is the most
expensive kind of wrong the measurement can be.

**Produces** nothing on the sheet. Threads into the run config.

| | Answers it as |
|---|---|
| A | "& Sons" vs "and Sons"; the LLC on the paperwork |
| B | "Ōura", "Oura Ring", the current model name |
| C | The product name vs the company name, when they differ |
| D | Brand vs the legal entity on the invoice |
| E | "Smith & Jones LLP" vs "Smith and Jones"; a pre-merger name |
| F | The franchisor's name; a DBA; a former name after a rebrand |

---

### `Q-WHAT-04` — who you get confused with · **negative**
**Kind** `list` · **Section** `identity` · **Key** `identity_not`

> **Is there anyone people mix you up with?**
> *This is one of the things AI gets wrong most often, and one of the easiest to
> catch.*

**Why.** Arguably the most universal card in the set, and the cheapest source of
a `competitor_confusion` or `identity` flag. Assertions are written as complete
negatives: *"Not affiliated with Nahman Plumbing of San Jose."*

**Produces** negative `identity` claims → `identity`, `competitor_confusion` flags.

| | Answers it as |
|---|---|
| A | A same-name shop two towns over; a franchise they left |
| B | A competitor with a similar name; a parent company they're not part of |
| C | A same-name product in another category |
| D | A national brand with the same word in its name |
| E | **Extremely common** — same-surname firms, a former partnership |
| F | Franchisee vs franchisor; a same-name nonprofit in another state |

---

### `Q-OFFER-01` — what you offer
**Kind** `list` · **Section** `services_pricing` · **Key** `services_offered`

> **What do you actually offer?**
> *Name the level a customer would ask about — the categories, not every
> individual item. Ten or so is plenty.*
>
> *For instance —* local: drain cleaning, water heater install, repiping ·
> product: sleep tracking, HRV, readiness score, the iOS app · neutral: the
> services, product lines or practice areas you'd put on a menu.

**Why.** The positive half of the invented-feature check. **Fixed in this pass**
(§5.1) — the original wording invited a coffee roaster to list 140 SKUs, which is
both unusable as a chip list and useless to the judge. The judge checks whether
an AI knows you do *water heaters*, not whether it knows about the 12oz Ethiopian.

**Produces** positive `services_pricing` claims → `missing_or_invented_feature`.

| | Answers it as |
|---|---|
| A | Six trades: drains, water heaters, repiping, leak detection, gas lines, fixtures |
| B | The capability set: sleep stages, HRV, SpO2, temperature, the app |
| C | Modules: boards, timelines, reporting, the API |
| D | **Categories, not SKUs:** single-origin, blends, decaf, subscriptions, brewing gear |
| E | Practice areas: wrongful termination, discrimination, wage & hour |
| F | Programs, menu sections, listing types |

---

### `Q-OFFER-02` — what you don't offer · **negative**
**Kind** `list` · **Section** `services_pricing` · **Key** `services_excluded`

> **What do people ask for that you *don't* do?**
> *This is the most valuable question here. Without it, nobody can catch an AI
> volunteering you for work you don't take.*

**Why.** The single highest-value card in the set. An invented capability is
**unflaggable** without a negative to contradict it — an omission is never a
flag, only a contradiction is. `docs/fact-sheet-template-local.md` calls these
the false-positive guards, and every archetype has three of them ready.

**Produces** negative `services_pricing` claims → `missing_or_invented_feature`.

| | Answers it as |
|---|---|
| A | "No septic work." "No commercial jobs." "No new construction." |
| B | "No Android app." "No blood pressure." "Not a medical device." |
| C | "We're not a CRM." "No on-prem deployment." "No native mobile app." |
| D | "We don't ship refrigerated." "No wholesale." "No returns on opened bags." |
| E | "No criminal defence." "We don't take contingency cases." "No pediatric." |
| F | "No walk-ins." "We don't do weddings." "Not a food pantry — meals only." |

---

### `Q-OFFER-03` — what's changed
**Kind** `pairs` (*What changed · When*) · **Section** `features` · **Keys** `features_current`, `features_added`, `features_removed`

> **What's new, and what have you stopped doing?**
> *AI training data lags by months. This is the fastest way to catch an AI still
> describing you as you were last year.*

**Why.** The staleness card, and the one that produces the `stale` flag type.
Covers a product version, a new service line, a new location and a discontinued
one with the same control. The *removed* half is a negative and is usually the
more valuable one — an AI recommending a service you dropped sends a customer to
a dead end.

**Produces** positive and negative `features` claims → `stale`.

| | Answers it as |
|---|---|
| A | "Added emergency water damage, March." "Stopped duct cleaning, January." |
| B | "Ring 5 shipped, May 28." "Retired the Ring 3 trade-in, February." |
| C | "SSO on all plans, June." "Sunset the free tier, April." |
| D | "New Colombian single-origin, July." "Discontinued the espresso blend." |
| E | "Opened the Oakland office, May." "No longer taking new immigration matters." |
| F | "New winter menu." "Closed the Tuesday clinic." |

---

### `Q-COST-01` — what it costs
**Kind** `priced_rows` (*What · Price · Basis · What's included*) · **Section** `services_pricing` · **Key** `pricing_rows`

> **What does it cost?**
> *Prices are the single most-hallucinated thing about any business. Exact
> numbers, today's. `Free`, `From $X`, `Varies by scope` and `Quote only` are all
> real answers.*

**Why.** The highest-hallucination dimension in the entire template. **Fixed in
this pass** (§5.2) — the original had a price field and no **basis**, which made
it unanswerable for anyone who doesn't sell a flat-priced thing. A law firm bills
hourly, a SaaS per seat per month, a dentist per visit, a plumber per job. The
basis selector is: *one-time · per hour · per seat/mo · per month · per year ·
per visit · per project · per unit*.

Every row is stamped `(as of {date})` — an undated price goes stale silently and
a stale sheet produces false flags.

**Produces** positive `services_pricing` claims → `wrong_pricing`.

| | Answers it as |
|---|---|
| A | Diagnostic visit · $89 · per visit · applied to the repair |
| B | Premium · $499 · one-time · plus membership |
| C | Business · $12 · per seat/mo · unlimited boards, SSO |
| D | Single-origin 12oz · $22 · per unit; **plus one "range across the catalogue" row** |
| E | Partner time · $450 · per hour · ; Initial consult · Free · one-time |
| F | Dinner entrées · $18–34 · per unit; Membership · $60 · per year |

---

### `Q-COST-02` — what else they pay · **negative**
**Kind** `choice` + reveal ×2 · **Section** `services_pricing` · **Keys** `pricing_mandatory_extra`, `pricing_free_option`

> **Is there anything people have to pay on top of that?**
> `[ No, that's the full price ]` `[ Yes — ___ ]`
>
> **Is there a free option — a free tier, a free trial, a free consult, free
> shipping?**
> `[ No ]` `[ Yes — ___ ]`
>
> *AI quotes the headline price and misses this constantly. It's usually the
> finding that lands hardest.*

**Why.** The most demo-able claim the system can make. Oura's required $5.99/mo
membership on top of a $399 ring is the canonical example, and every archetype
has its own version. The free-option half is a `negativeFirst` question: "no"
produces *"There is no free option."*, which is quotable and therefore flaggable.

**Produces** positive and negative `services_pricing` claims → `wrong_pricing`.

| | Answers it as |
|---|---|
| A | Trip charge outside the city; weekend surcharge; two-hour minimum |
| B | The required $5.99/mo membership |
| C | Implementation fee; per-seat overage; annual-only on Enterprise |
| D | **Shipping** — and "free over $50" as the free-option answer |
| E | Court filing fees, expert costs; "free 30-minute consult" |
| F | Service charge on parties of six; a membership fee |

---

### `Q-REACH-01` — how people reach you · **negative half**
**Kind** `batch_confirm` + `list` · **Section** `contact` · **Keys** `contact_phone`, `contact_email`, `contact_booking`, `contact_address`, `contact_none`, `contact_retired`

> **This is the most important card here — tap anything that's wrong.**
> *Phone · Email · Booking or support link · Address*
> `[ + Add a channel ]` `[ We don't have a phone line ]` `[ No public address ]`
>
> **Any old number, address or link of yours still floating around online?**
>
> *If an AI hands someone the wrong way to reach you, that's a customer you never
> hear about.*

**Why.** Highest-consequence card on the sheet, and the one this pass changed
most (§5.4). The original four rows were local-shaped and left a SaaS with three
empty fields. Two fixes: the rows are now **whatever channels actually exist**,
and *"we don't have a phone line"* / *"no public address"* are **first-class
negative answers**, not blanks. An AI inventing a support phone number for a
software company is a real and common failure, and it is unflaggable unless the
absence is asserted.

The retired-contact half is the single most useful line in
`fact-sheet-template-local.md` and it applies to everyone — an old address in an
old directory outlives the lease.

**Produces** positive and negative `contact` claims → `wrong_contact`.

| | Answers it as |
|---|---|
| A | Phone, address, emergency line; the disconnected old number |
| B | Support email + help centre; **"No phone support."** |
| C | Support email, status page; **"No phone support." "No public office address."** |
| D | Support email, returns portal; the old warehouse address |
| E | Phone, office address, intake form; a former office still in listings |
| F | Phone + reservations link; a Google listing with the wrong suite number |

---

### `Q-REACH-02` — where you serve · **negative half**
**Kind** `choice` + reveal · **Section** `service_area` · **Keys** `service_area_scope`, `service_area_included`, `service_area_excluded`

> **Where can people get you?**
> `[ Anywhere ]` `[ Specific places ]`
> *(on "Specific places")* Which ones? · Home city · State *(spelled out — "California", not "CA")*
>
> **Anywhere you *don't* serve — or aren't licensed to?**
>
> *Without the second answer, nobody can catch an AI promising someone in the
> next county — or the next country — that you'll cover them.*

**Why.** The negative half **has no producer anywhere in the system today** —
`docs/factsheet-autogen-plan.md` §4.4 forbids deriving it from an open list, and
nothing else asks. **Widened in this pass** (§5.5) to name *licensing area*
explicitly, because for regulated professions "where do you serve" is really
"where are you admitted to practise," and an AI telling someone a firm can take
their Nevada case is a liability, not an inconvenience.

The state field is a select, never free text: `_ABBREVIATED_REGION_RE` in
`src/prompts/assemble.py` rejects "CA", and a rejected locale returns an empty
surface that reads as the brand being absent.

**Produces** positive and negative `service_area` claims → `wrong_service_area`.

| | Answers it as |
|---|---|
| A | Berkeley, Oakland, Albany, El Cerrito. **Not** Marin County |
| B | Ships to US, CA, UK, EU. **Not** Australia |
| C | Anywhere. **Not** customers requiring EU data residency |
| D | **Shipping zones** — domestic only; no PO boxes; no HI/AK |
| E | **Admitted in California and New York. Not admitted in Nevada.** |
| F | One location; delivery radius 4 miles; grant area = three counties |

---

### `Q-REACH-03` — when you're available · **negative half**
**Kind** `availability` · **Section** `hours` · **Keys** `hours_scope`, `hours_monday`…`hours_sunday`, `hours_after_hours`

> **When can someone actually reach a person?**
> `[ Any time — round the clock ]` `[ Set hours ]` `[ By appointment or arrangement ]`
> *(7-day grid appears only on "Set hours")*
>
> **Anything outside those hours — emergency, on-call, after-hours cover?**
> `[ No ]` `[ Yes, same rate ]` `[ Yes, costs more ]`
>
> *Be blunt about the gaps. "Closed Sunday" and "no weekend support" are the same
> answer, and they're what catch an AI inventing round-the-clock cover.*

**Why.** **Sharpened in this pass** (§5.6): the prompt now says *reach a person*.
Without that, a SaaS answers "always" because the product is self-serve 24/7,
which is true and produces a claim that reads as "support is available at 3am" —
a false line in a document we send a stranger. Self-serve availability is not
support availability, and only one of them is a fact a customer acts on.

The grid renders only when it applies, so nobody is asked to fill seven rows they
don't have. `Closed` is a first-class toggle, never an empty time field — the
negative is the whole point.

**Produces** positive and negative `hours` claims → `wrong_hours`.

| | Answers it as |
|---|---|
| A | Set hours, Mon–Sat 7–5, **closed Sunday**; no after-hours |
| B | Set hours — support 9–5 PT weekdays; no phone cover at all |
| C | Set hours — support 9–6 ET weekdays; **P1 on-call, Enterprise only** |
| D | Set hours — orders ship Mon–Thu, cutoff 2pm; no weekend dispatch |
| E | By appointment; Tue/Thu only for new matters; **24h emergency line** |
| F | Set hours; closed Mondays; kitchen closes 21:30 |

---

### `Q-PROOF-01` — what you can prove · **negative half**
**Kind** `pairs` (*What you hold · Who issued it*) · **Section** `licensing` · **Keys** `licensing_credentials`, `licensing_not_held`

> **Anything you're licensed, certified or accredited for?**
> *What you hold · Who issued it*
>
> **Anything people assume you hold that you don't?**
>
> *An AI claiming a credential you don't have is a real liability. So is one
> denying the credential you do have.*

**Why.** `licensing` is **declared, titled and never emitted** anywhere in the
system — this card is its only producer. And it generalizes further than its enum
name suggests: a CSLB number and a SOC 2 report are the same dimension, checked
the same way, with the same consequence when an AI gets it wrong. The negative
half is the liability guard and is highest-value for C and E.

**Produces** positive and negative `licensing` claims → `licensing`.

| | Answers it as |
|---|---|
| A | CSLB · licence 123456; bonded & insured; EPA 608 |
| B | FCC ID; CE mark; **"Not an FDA-cleared medical device."** |
| C | SOC 2 Type II · 2026; ISO 27001; **"Not HIPAA compliant — no BAA."** |
| D | USDA Organic · cert #; Fair Trade; FDA-registered facility |
| E | **State bar admission · number; board certification; malpractice carrier** |
| F | 501(c)(3) · EIN; health department grade; franchise agreement |

---

### `Q-PROOF-02` — who else they'd look at
**Kind** `list` ×2 · **Section** `positioning` · **Keys** `positioning_competitors`, `positioning_for`

> **If someone didn't pick you, who else would they be looking at?**
>
> **And who is it for?**
>
> *We'll ask the AIs about each of these by name, so this list decides a good
> chunk of what gets measured.*

**Why.** **Reworded in this pass** (§5.7) from "who do you compete with." A
nonprofit, a law firm and a solo practice all bristle at "competitors" and
answer "nobody, really" — which produces an empty list and breaks a hard
constraint downstream: **every competitor named here must appear in at least one
comparison query**, and at least two comparison queries must leave the client
unnamed. An empty list means the comparison bucket has nothing to measure.

"Who else would they be looking at" gets a real answer from all six.

**Produces** positive `positioning` claims → `competitor_confusion`. Also feeds
the query generator's comparison bucket and the run's `competitors` config.

---

### `Q-AI-01` — what AI already gets wrong
**Kind** `pairs` (*What did it say · What's actually true*) · **Section** `watchlist` · **Keys** `watchlist_{n}`

> **Have you ever seen ChatGPT or Google's AI say something wrong about you?**
> *Anything you've already caught. This is usually the first thing we go and
> check.*

**Why.** This is the §E watch-list from `docs/fact-sheet-template.md` — the
section that carries the sales demo and the one section scraping structurally
cannot produce, because it is about the *models*, not the business. Repeatable.

**Produces** paired `watchlist` claims, and aims the reverse pass when it lands.

---

### `Q-AI-02` — anything else
**Kind** `longtext` · **Section** `watchlist` · **Key** `watchlist_other`

> **Anything else an AI could get wrong about you?**
> *Last one. Skip it if nothing comes to mind.*

**Why.** The catch-all. Cheap, optional, and it is where the thing nobody
anticipated shows up.

---

## 4 · Robustness matrix

✅ answers naturally · ◐ answers, with the fix noted in §5 · — genuinely N/A, and
a skip costs nothing

| Question | A local | B product | C SaaS | D e-comm | E prof. svc | F wildcard |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| `Q-WHAT-01` found facts | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-WHAT-02` what it is | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-WHAT-03` other names | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-WHAT-04` confused with | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-OFFER-01` what you offer | ✅ | ✅ | ✅ | ◐ 5.1 | ✅ | ✅ |
| `Q-OFFER-02` what you don't | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-OFFER-03` what's changed | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-COST-01` what it costs | ◐ 5.2 | ✅ | ◐ 5.2 | ◐ 5.1/5.2 | ◐ 5.2 | ◐ 5.2 |
| `Q-COST-02` what else | ✅ | ✅ | ✅ | ◐ 5.3 | ✅ | ✅ |
| `Q-REACH-01` how to reach | ✅ | ◐ 5.4 | ◐ 5.4 | ◐ 5.4 | ✅ | ✅ |
| `Q-REACH-02` where | ✅ | ✅ | ✅ | ✅ | ◐ 5.5 | ✅ |
| `Q-REACH-03` when | ✅ | ◐ 5.6 | ◐ 5.6 | ✅ | ✅ | ✅ |
| `Q-PROOF-01` what you prove | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-PROOF-02` who else | ✅ | ✅ | ✅ | ✅ | ◐ 5.7 | ◐ 5.7 |
| `Q-AI-01` what AI got wrong | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `Q-AI-02` anything else | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**After the seven fixes, every cell is ✅.** No archetype has a dead question, and
no question needed a fork.

### Flag-type coverage

All nine members of `AccuracyFlagType` have a producer, and eight of the nine
have a *negative* producer — which is what makes them fire.

| Flag type | Positive from | Negative from |
|---|---|---|
| `identity` | `Q-WHAT-01`, `Q-WHAT-02` | `Q-WHAT-04` |
| `competitor_confusion` | `Q-PROOF-02` | `Q-WHAT-04` |
| `missing_or_invented_feature` | `Q-OFFER-01` | **`Q-OFFER-02`** |
| `stale` | `Q-OFFER-03` | `Q-OFFER-03` (removed half) |
| `wrong_pricing` | `Q-COST-01` | **`Q-COST-02`** |
| `wrong_contact` | `Q-REACH-01` | **`Q-REACH-01`** (retired + "no phone") |
| `wrong_service_area` | `Q-REACH-02` | **`Q-REACH-02`** (excluded half) |
| `wrong_hours` | `Q-REACH-03` | **`Q-REACH-03`** (closed + no after-hours) |
| `licensing` | **`Q-PROOF-01`** | **`Q-PROOF-01`** (not-held half) |

Bold = the only producer that exists anywhere in the system.

---

## 5 · What this pass changed

Seven fixes. Each came from an archetype that could not answer a question
truthfully without the wording changing — which under the maintenance rule means
the question was wrong, not the archetype.

**5.1 · `Q-OFFER-01` and `Q-COST-01` — the catalogue explosion (D).**
"What do you offer?" invited a coffee roaster to list 140 SKUs into a chip input.
Unusable as a control and useless to the judge, which checks whether an AI knows
you sell *single-origin*, not whether it knows the 12oz Ethiopian. Fixed: the
helper now says *"the level a customer would ask about — the categories, not
every individual item. Ten or so is plenty."* `Q-COST-01` gains a
*"price range across the catalogue"* row for the same reason.

**5.2 · `Q-COST-01` — a price with no basis is unanswerable (A, C, E, F).**
The original had *what · price · what's included*. A law firm bills hourly, a
SaaS per seat per month, a dentist per visit, a plumber per job — and "450" with
no basis is a claim the judge cannot check and an AI cannot contradict. Fixed: a
**Basis** selector — *one-time · per hour · per seat/mo · per month · per year ·
per visit · per project · per unit* — plus `Varies by scope` and `Quote only` as
first-class price values alongside `Free` and `From $X`. **This changes
`priced_rows` from three columns to four; the two build plans need the same
change.**

**5.3 · `Q-COST-02` — shipping was missing (D).**
For an e-commerce business, shipping *is* the hidden cost, and "free shipping
over $50" is the free-option answer. It was absent from the for-instance line.
Copy fix only.

**5.4 · `Q-REACH-01` — the contact card was local-shaped (B, C, D).**
Four fixed rows — phone, email, address, booking — left a SaaS with three empty
fields and no way to say the thing that is actually true and actually valuable:
**there is no phone line.** An AI inventing a support number for a software
company is a real, frequent failure, and it is completely unflaggable unless the
absence is asserted. Fixed: rows are whatever channels exist, plus *"We don't
have a phone line"* and *"No public address"* as first-class negative answers
producing quotable assertions. **This is the largest fix in the pass.**

**5.5 · `Q-REACH-02` — jurisdiction, not just geography (E).**
"Where do you serve" reads as delivery radius. For a regulated profession it
means *where are you admitted to practise*, and an AI telling someone a firm can
take their out-of-state matter is a liability rather than an inconvenience.
Fixed: the negative half now reads *"Anywhere you don't serve — or aren't
licensed to?"*, and this card is noted as interacting with `Q-PROOF-01`.

**5.6 · `Q-REACH-03` — "available" was ambiguous (B, C).**
A SaaS answers "always available" truthfully about the *product*, and the
resulting claim reads as *support is reachable at 3am* — a false line in a
document sent to a stranger. Fixed: the prompt now asks **"when can someone
actually reach a person?"**, and the helper says self-serve availability is not
support availability.

**5.7 · `Q-PROOF-02` — "competitors" gets refused (E, F).**
A nonprofit and a law firm answer "nobody, really," which produces an empty list —
and an empty list breaks a hard downstream constraint: every named competitor
must appear in ≥1 comparison query, and ≥2 comparison queries must leave the
client unnamed. With nothing named, the comparison bucket measures nothing.
Fixed: **"If someone didn't pick you, who else would they be looking at?"** —
which all six answer.

### Two things this pass deliberately did *not* change

- **The count stayed at 16.** Every fix was a widening, not an addition. A
  seventeenth card would have to displace one, and none of the sixteen is weaker
  than a new one would be.
- **No question was forked by business type.** Six archetypes, one set. The
  for-instance line absorbed all of it.

---

## 6 · What this set deliberately does not ask

Each of these was considered and cut. Recorded so they don't get re-proposed.

| Not asked | Why |
|---|---|
| **Leadership / founders by name** | High hallucination value, but for four of six archetypes the owner doesn't want to be named, and a name is the sort of fact that goes stale without anyone noticing. `Q-WHAT-01` carries "in business since"; that is enough identity anchoring |
| **Review counts and star ratings** | Volatile weekly, and a stale rating in the sheet produces a *false* flag against an AI quoting the correct current one. Rule 2 says leave it blank |
| **Social and directory profile links** | Useful for the off-site audit, not for accuracy — a missing link is a visibility problem, not a contradiction. `sameAs` from the crawl covers it without a card |
| **Payment methods / financing** | Almost never something an AI asserts wrongly, and when it does the consequence is trivial. Did not earn a card against the 16 ceiling |
| **Anything with a number that changes weekly** | Headcount, inventory, wait times, current promotions. `as_of` cannot save a fact that is wrong four days later |
| **"What makes you different?"** | Attracts marketing language by construction. `Q-OFFER-01` + `Q-OFFER-02` capture the same information in falsifiable form |
| **Business type as its own gate question** | It routes nothing (see §2). It is confirmed inside `Q-WHAT-01`'s batch and inferred from `Q-REACH-02` if unknown |
