# Client Fact Sheet — {Company Name}

*Ground-truth reference for the GEO audit's **accuracy** checks. The LLM judge compares what AI engines say about this company against the facts below and flags anything wrong.*

**What this powers (and what it doesn't):** This sheet feeds only the *accuracy* parts of the report — §1 "Accuracy (correct when mentioned)" and §2.3 the accuracy-flags table. The judge scores *mention, prominence, and framing* straight from the AI's answer with **no fact sheet needed**; this document exists purely so the judge can tell true from false. So it's never a blocker for a run or a demo — it's the upgrade that adds the "here's where AI is wrong about you" findings.

**Two rules when filling it in:**
1. **Only falsifiable facts** — concrete, checkable claims (a price, a feature, a founding year), never marketing language ("the leading platform"). The judge can only check things that are true-or-false.
2. **Blank is safe.** Any field you can't fill confidently, leave blank — the judge only checks against facts that are present, so a blank field means "no accuracy check on that dimension," never a false flag. A thin first pass is fine; deepen it over time.

> **Meta**
> - Brand name / legal entity: {Brand} / {Legal name}
> - Business type: B2C consumer · Category: {how it should be described}
> - Prepared by: {name} · **Last verified: {YYYY-MM-DD}** · Verification: {confirmed with client / public sources only}
> - Primary sources: {pricing page, docs, press, etc. — link the pages each fact came from}

*Italic notes are guidance — delete them in a working copy. Date every volatile fact (pricing, current version) with "as of {date}"; a stale sheet produces false flags.*

---

## A · Identity & basics
*Catches: confusion with another company, wrong founders/leadership, wrong founding facts, miscategorization.*

- **What it is (one line):** {plain description of the product/service}
- **Category label you want models to use:** {e.g., "project management tool" / "smart ring" — the exact framing}
- **Name variants & aliases (for matching):** {official name, common spellings, product names, legal entity — so a mention isn't missed or split}
- **Founded / HQ:** {year} · {city, country}
- **Founders & key leadership:** {founders; current CEO and other named execs — models hallucinate these}
- **Company stage / size:** {funding stage or public/private, valuation or employee count — only if confidently known}
- **Website:** {url}

## B · Pricing
*Highest-hallucination area — models routinely quote stale or invented prices. Be exact and date it.*

- **Billing model:** {one-time / per-seat / usage-based / subscription; monthly vs annual; hardware + subscription split if applicable}
- **Plans & prices (as of {date}):**
  - {Plan / tier / SKU} — {$X}, {what's included}
  - {Plan / tier} — {$X ...}
  - {Enterprise / custom} — {"contact sales" if no public number}
- **Separate mandatory fees:** {e.g., a required membership/subscription on top of a hardware price — a common omission}
- **Free tier?** {yes/no — and its limits}
- **Free trial?** {yes/no — length}
- **Current vs. previous version pricing:** {if a new model/version just changed the price, note both so stale answers are catchable}
- **Regional / currency notes:** {only if price differs materially by market}

## C · Features & capabilities
*Catches: "missing-but-real feature" (model says they can't do something they can), invented features, and stale capability claims.*

- **Core features they DO have:** {the real, current capability set — bullet them}
- **Recently shipped (last ~6–12 months):** {newest features / latest model or version — the #1 staleness hotspot, since training data lags}
- **Things they explicitly do NOT do / common misconceptions:** {the false-positive guards — e.g., "no free tier", "iOS only (no Android yet)", "not owned by [competitor]"}
- **Key integrations / ecosystem:** {the integrations worth naming}
- **Notable limitations or requirements:** {anything material a buyer should know that models distort}

## D · Positioning & competitors
*Catches: competitor confusion, wrong target segment.*

- **Ideal customer / who it's for:** {ICP — segment, company size or consumer type, use case}
- **Key differentiators (factual, not slogans):** {what's actually distinct and checkable}
- **Named competitors (the benchmark set), with aliases:** {Competitor A (aliases), B, C, D}
- **Most often confused with:** {the company/companies models wrongly conflate it with, and why}
- **Category leader, if not them:** {who currently leads the category — context for the §1 leaderboard}

## E · Known-inaccuracy watch-list
*The highest-value section and the one that drives the demo. Pre-list the specific wrong things you expect or have already seen models say. Mirror the report's §2.3 columns so it maps straight through.*

| Claim models make | Reality | Flag type | Severity |
|---|---|---|---|
| {e.g., "latest model is the v4"} | {"v5 launched {date}"} | stale info | {high/med/low} |
| {e.g., "$349, no subscription"} | {"$399 + required $5.99/mo"} | wrong pricing / missed fee | {high/med/low} |
| {e.g., "US company"} | {"founded in {country}"} | identity | {low} |
| {e.g., confused with {competitor}} | {how it differs} | competitor confusion | {med} |
| {acquisitions, rebrands, discontinued products, leadership changes models miss} | {...} | stale info | {...} |

*Severity guide — pick a scale and hold it constant: **high** = wrong price / feature / "they're owned by a competitor" (directly misleads a buyer); **med** = outdated-but-not-damaging; **low** = minor/cosmetic. Severity drives what the demo leads with.*

---

## How the judge uses this sheet
*Reference — not part of the filled sheet.*

When an engine's answer mentions this company, the judge reads it against Sections A–E and returns, for the client, an **accuracy verdict + typed flags** that feed the report:

| Sheet section | Error type it catches | Report cell it powers |
|---|---|---|
| A | Identity / founders / category confusion | §1 accuracy · §2.3 |
| B | Wrong pricing / missed mandatory fee | §1 accuracy · §2.3 |
| C | Missing-but-real or invented feature; stale capability | §1 accuracy · §2.3 |
| D | Competitor confusion; wrong segment | §1 accuracy · §2.3 |
| E | Pre-identified stale facts — the demo highlights | §2.3 (lead with high-severity) |

**Worked illustration (from the Oura example):** for a query like *"best smart ring 2026,"* an answer that says *"the Oura Ring 4 is the newest, $349, no subscription needed"* trips three flags against this sheet at once — stale model (E/C), wrong price (B), and missed mandatory membership (B/C). Those three flags are exactly the visceral findings a sales demo opens with. That is the entire point of the sheet: it turns *"are they mentioned?"* into *"here's what the AI gets wrong about them."*
