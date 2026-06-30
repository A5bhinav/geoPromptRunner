# Client Fact Sheet — Oura

*Ground-truth reference for the GEO audit's **accuracy** checks. The LLM judge compares what AI engines say about Oura against the facts below and flags anything wrong. Only falsifiable facts; blank = no check on that dimension.*

> **Meta**
> - Brand / legal name: Oura / Ōura Health Oy
> - Business type: B2C consumer · Category: smart ring
> - Prepared by: GEO audit team · **Last verified: 2026-06-29** · Verified with client? No — public sources
> - Primary sources: ouraring.com/store/rings/oura-ring-5, ouraring.com/membership, Oura blog "Introducing Oura Ring 5", CNBC (2026-05-28 launch; 2026-05-21 IPO filing), Forbes Vetted (2026-05-28), Tom's Guide (Ring 5 vs Ring 4), Fortune (2026-02-04), Bloomberg (2026-06-19)

---

## A · Identity & basics

- **What it is (one line):** A screenless smart ring that tracks sleep, activity, heart rate, and recovery, paired with the Oura health app.
- **Category label you want models to use:** Smart ring / health-and-sleep wearable.
- **Name variants & aliases:** "Oura", "Ōura", "Oura Ring", legal entity "Ōura Health Oy".
- **Founded / HQ:** Founded 2013 in Oulu, Finland · operates with a U.S. base in San Francisco (commercial HQ) alongside Finland operations.
- **Founders & key leadership:** Co-founders Petteri Lahtela, Kari Kivelä, Markku Koskela · CEO **Tom Hale** (joined 2022; not a co-founder).
- **Company stage / size:** Private, venture-backed · ~**$11B** valuation (Series E, late 2025) · **confidentially filed for IPO in May 2026** (as of 2026-06-29, still private).
- **Website:** ouraring.com

## B · Pricing
*(all prices as of 2026-06-29, US)*

- **Billing model:** One-time hardware purchase **+ a required Oura Membership subscription** for full features.
- **Hardware — Oura Ring 5 (current model):**
  - Base finishes (Silver, Black) — **$399**
  - Premium finishes (Stealth, Brushed Silver, Gold, Deep Rose) — **$499**
- **Previous model — Oura Ring 4:** launched at **$349** base; still sold alongside Ring 5, now discounted (~20% off reported at Ring 5 launch).
- **Membership:** **$5.99/month** or **$69.99/year** (US). **First month free** for new members (begins when the ring is paired; tied to the account, not the ring).
- **Separate mandatory fee:** The membership is **separate from and required on top of** the hardware price for the full product. A common omission in AI answers.
- **Free tier?** No full free tier — without membership the ring and app still function but insights/scores are heavily limited.
- **Free trial?** One free month of membership with a new ring (not 12 months).
- **Regional / currency notes:** Membership pricing varies by region (EU, UK, Canada, Australia, Japan, Switzerland differ from US).

## C · Features & capabilities

- **Core features they DO have:** Sleep tracking (stages, Sleep Score), Readiness and Activity scores, 24/7 heart rate, HRV, blood-oxygen (SpO2), body-temperature trends, activity/steps, cycle/period insights, Oura Advisor (AI health companion), 50+ health metrics, guided content in the app.
- **Recently shipped (last ~6–12 months):** **Oura Ring 5** (announced 2026-05-28, ships 2026-06-04) — marketed as the "world's smallest smart ring," ~**40% smaller** than Ring 4, redesigned sensing (more LEDs, 12 signal pathways), **6–9 days** battery life. New/rolling software: GLP-1 Insights, Oura Advisor, Health Radar (Counsel Health partnership) — several available to Gen3 and newer, not Ring 5 only.
- **Things they explicitly do NOT do / common misconceptions:** It is **not a smartwatch** — no screen, no display, no on-device notifications. It is **not free** — Oura Membership is required for the full product. It is **not a medical-grade diagnostic device**. It is **not owned by a competitor** (independent company; not Samsung/Whoop/etc.).
- **Key integrations / ecosystem:** Apple Health, Google Health Connect, Strava, Natural Cycles; third-party apps via Oura API.
- **Notable limitations / requirements:** Requires a paired smartphone and the Oura app; full insights require an active paid membership.

## D · Positioning & competitors

- **Ideal customer / who it's for:** Health-conscious consumers focused on sleep, recovery, and longevity who want a discreet, screenless wearable.
- **Key differentiators (factual, not slogans):** Screenless ring form factor; strong sleep/recovery software; longest-tenured major smart-ring brand; Ring 5 positioned as the smallest/thinnest smart ring; 6–9 day battery.
- **Named competitors (benchmark set):** Whoop, Ultrahuman (Ring Air / Ring AIR), Samsung Galaxy Ring (~$399), RingConn.
- **Most often confused with:** Ultrahuman and Samsung Galaxy Ring (same ring form factor); Whoop (recovery focus, but a screenless band, not a ring).
- **Category leader, if not them:** Oura is the incumbent leader in the consumer smart-ring category.

## E · Known-inaccuracy watch-list

| Claim models make | Reality | Flag type | Severity |
|---|---|---|---|
| "Latest model is the Oura Ring 4" (or Ring 3 / Gen 3) | **Oura Ring 5** launched 2026-05-28, ships 2026-06-04 | stale info | high |
| "It's $349" or "$299, one-time, no subscription" | Ring 5 base is **$399** ($499 premium); a **required $5.99/mo membership** applies | wrong pricing / missed fee | high |
| Omits the membership entirely (implies one-time purchase) | Oura Membership ($5.99/mo or $69.99/yr) is **required** for full features | missed mandatory fee | high |
| "Comes with a free year / 12 months of membership" | Only the **first month** is free for new members | wrong pricing | med |
| "Oura is a U.S. company" | **Founded in Finland (2013, Oulu)**; runs U.S. operations from San Francisco | identity | low |
| "Oura is owned by Samsung / Whoop / [competitor]" | Independent company (Ōura Health Oy); not owned by a competitor | competitor confusion | high |
| "Oura is publicly traded" / names a ticker | Still **private** as of 2026-06-29; only **confidentially filed** for IPO (May 2026) | stale info | med |
| "It has a screen / shows notifications like a smartwatch" | Screenless; no display, no on-device notifications | invented feature | med |
| Misses acquisitions (e.g., Proxy, Veri, Sparta Science) | Oura has made these acquisitions | stale info | low |

---

*How to read this: for a query like "best smart ring 2026" or "is the Oura Ring worth it," the judge compares the answer to Sections A–E. "The Oura Ring 4 is the newest, $349, no subscription needed" trips three high-severity flags — stale model (E/C), wrong price (B), and missed mandatory membership (B/C) — the visceral findings a demo leads with.*
