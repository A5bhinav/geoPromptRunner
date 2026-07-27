# Client Fact Sheet (LOCAL SERVICE) — {Business Name}

*Ground-truth reference for the GEO audit's **accuracy** checks on a service-area business — a contractor, shop or salon customers call or visit. The LLM judge compares what AI engines say about this business against the facts below and flags anything wrong.*

**This is the local variant of `fact-sheet-template.md`.** Both are live; pick by business kind. The consumer template is organised around *pricing / features / versions* — the things a product's accuracy turns on. A local business's accuracy turns on something else entirely: **can I actually get them, where, and are they legitimate.** That is what the four local flag types check (`wrong_hours`, `wrong_service_area`, `wrong_contact`, `licensing`).

**What this powers (and what it doesn't):** only the *accuracy* parts of the report. Mention, prominence and framing are judged straight from the AI's answer with **no fact sheet needed** — so a missing sheet never blocks a run or a demo. This is the upgrade that adds "here's where AI is wrong about you", which for a local owner is often the most alarming section: an AI confidently giving customers the wrong hours or the wrong phone number is a lost job, today.

**Two rules when filling it in:**
1. **Only falsifiable facts** — a phone number, a licence number, a closing time. Never marketing language ("the most trusted plumber in town"). The judge can only check things that are true-or-false.
2. **Blank is safe.** Any field you can't fill confidently, leave blank. The judge only checks against facts that are *present*, so a blank field means "no accuracy check on that dimension", never a false flag.

> **Meta**
> - Business name / legal entity: {Name} / {Legal name, DBA}
> - Business type: local service · Trade: {plumber / HVAC contractor / barbershop / …}
> - Prepared by: {name} · **Last verified: {YYYY-MM-DD}** · Verification: {confirmed with owner / public sources only}
> - Primary sources: {the site's contact page, Google Business Profile, Yelp listing, state licence lookup — link each}

*Italic notes are guidance — delete them in a working copy. Hours and staffing change; date anything volatile with "as of {date}". A stale sheet produces false flags.*

---

## A · Identity & basics
*Catches: confusion with a same-named business in another town, wrong trade, wrong ownership.*

- **What it is (one line):** {plain description — "family-owned plumbing contractor serving the East Bay since 1998"}
- **Trade / category label you want models to use:** {the exact framing, e.g. "plumbing contractor", "barbershop" — not "home services company"}
- **Name variants & aliases (for matching):** {legal name, DBA, common misspellings, "& Sons" vs "and Sons", any former name — so a mention isn't missed}
- **Founded / owner:** {year} · {owner name, if they want to be named}
- **Website:** {url}
- **Businesses it is NOT / commonly confused with:** {a same-named shop in another metro, a former franchise affiliation — a very common local failure}

## B · Contact & location → `wrong_contact`
*Models routinely surface a stale number from an old directory listing. This is the highest-consequence field on the sheet.*

- **Phone (primary, as of {date}):** {number — write it once, in one format; the judge treats formatting differences as agreement}
- **Other numbers:** {emergency line, text line — label each}
- **Street address:** {full address, or "mobile / no storefront" if they don't take walk-ins}
- **Numbers/addresses that are NO LONGER theirs:** {an old number or a previous location still floating around online — the single most useful line here}

## C · Hours & availability → `wrong_hours`
*Catches: "open Sundays" when they aren't, invented 24/7 emergency service, wrong holiday behaviour.*

- **Regular hours (as of {date}):** {per day; be explicit about days they are CLOSED}
- **Emergency / after-hours service?** {yes/no — and whether it costs more. If no, say so plainly: "No after-hours service" is what makes a false 24/7 claim flaggable}
- **Same-day / next-day availability?** {what they can honestly promise}
- **Appointment vs walk-in:** {which, or both}
- **Seasonal or holiday closures:** {anything predictable}

## D · Service area → `wrong_service_area`
*Catches: AI telling a customer in the next town over that this business serves them (or won't).*

- **Primary city:** {city, state}
- **Towns / neighborhoods / counties served:** {list them — this is the line a "do they serve X?" answer gets checked against}
- **Areas explicitly NOT served:** {the boundary. Without this, an over-broad claim is unflaggable}
- **Travel/trip fee beyond a radius?** {if any}

## E · Licensing, insurance & credentials → `licensing`
*Catches: an AI asserting a credential they don't hold — a real liability — or denying one they do.*

- **Licence number(s) & issuing body:** {e.g. CSLB #123456 (California)}
- **Bonded / insured?** {yes/no, and coverage type if they publish it}
- **Certifications:** {manufacturer certifications, trade bodies, EPA, etc.}
- **Credentials they do NOT hold:** {only if a competitor commonly claims it and confusion is likely}

## F · Services & pricing → `wrong_pricing`, `missing_or_invented_feature`
*Same two flag types as the consumer sheet — a local business still has services and prices.*

- **Services they DO offer:** {the real list}
- **Services they explicitly do NOT offer:** {the false-positive guard — "no septic work", "no commercial jobs"}
- **Call-out / diagnostic fee (as of {date}):** {$X, or "free estimates"}
- **Typical price ranges (as of {date}):** {only where they'd stand behind a number publicly}
- **Payment / financing:** {cards, financing offers}
- **Brands or equipment they work on:** {if it matters for the trade}

## G · Reputation & presence
*Not directly flagged, but this is what the offsite audit (Cat 6) scores and what AI actually cites for local.*

- **Google Business Profile:** {link — claimed? complete?}
- **Yelp:** {link} · **BBB:** {link, rating} · **Angi / Thumbtack:** {links}
- **Facebook / Nextdoor / Bing Places:** {links}
- **Review counts & ratings (as of {date}):** {per platform — useful for spotting an AI quoting a stale rating}

---

### Judge notes (how these become flags)

Every flag still requires the judge to quote a **verbatim contradicting line** from this sheet. Consequences worth understanding before you fill it in:

- A dimension you leave blank is simply **not checked**. It cannot produce a false flag, and it cannot produce a true one either.
- **Negative lines are the valuable ones.** "Closed Sunday", "No after-hours service", "Does not serve Marin County", "No septic work" are what make an over-claiming answer flaggable. A sheet of only positive facts catches far less.
- An **omission is never a flag.** If an AI simply fails to mention the emergency line, that is not an accuracy problem — it is a visibility problem, and it shows up elsewhere in the report.
- Formatting differences are **agreement**, not contradiction: "(510) 555-0100" and "510-555-0100" are the same number.

See `docs/labeling-guide.md` for how these flags get gold-labeled, and `docs/grade-calibration-guide.md` for how agreement is measured. **Until the local gold set is built and calibrated (W3.4), no local report may quote an accuracy or agreement figure.**
