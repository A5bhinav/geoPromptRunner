# Client Fact Sheet — Fort

*Ground-truth reference for the GEO audit's accuracy checks. The judge compares what AI engines say about Fort against the facts below. Falsifiable facts only.*

> **Meta**
> - Brand name / legal entity: Fort
> - Business type: B2C · Category: strength-training wearable (fitness wearable / smart fitness band)
> - Prepared by: {analyst} · **Last verified: 2026-06-13** · Verification: public sources (fort.cx + press: Athletech News, New Atlas, Wellworthy, YC)
> - Primary sources: https://fort.cx/ , https://fort.cx/about , https://fort.cx/order ; founder/HQ/YC details from Athletech News, New Atlas, Wellworthy, ycombinator.com/companies/fort
> - ⚠️ **Pre-launch company** — most volatile facts are pricing and ship date; re-verify near demo time.

---

## A · Identity & basics

- **What it is (one line):** A strength-training wearable wristband that automatically detects exercises, counts reps/sets, and tracks training load — plus all-day cardio, sleep, and stress.
- **Category label models should use:** "strength-training wearable" (it positions as *the first wearable built for strength training*, not a generic smartwatch or fitness band).
- **Name variants & aliases (for matching):** Fort; "Fort wearable"; "Fort band". (Common-word name — watch for false matches on the word "fort" in unrelated contexts.)
- **HQ:** **San Francisco, CA.**
- **Founders & key leadership** (all ex-**Tesla** engineers):
  - **Miranda Nover** — Founder & CEO (prev. Tesla product design engineer, 4680 battery cells / Cybertruck)
  - **Paul Schneider** — Co-founder & CTO (prev. Tesla; mmWave radar, Semi/Robotaxi systems & autonomy architecture)
  - **Zac Valles** — CPO (prev. Tesla senior engineer; Cybercab/Cybertruck body & powertrain subsystems)
- **Company stage / size:** Venture-backed, **pre-launch** (selling pre-orders; not yet shipping). **Y Combinator — Winter 2026 (W26) batch.** (Exact incorporation year not publicly stated; treat "YC W26" as the firm date anchor.)
- **Backers:** Afore Capital, Carnegie Mellon University, Weekend Fund, Theory Forge, Banana Capital, plus angels from OpenAI and Tesla. (Y Combinator W26.)
- **Website:** https://fort.cx · contact founders@fort.cx
- **Press (claimed "as seen in"):** Athletech News, Forbes, WIRED, Fitt Insider.

## B · Pricing
*(as of 2026-06-13 — pre-order phase)*

- **Billing model:** One-time hardware purchase **+ an annual app membership** (a free tier exists after the included year).
- **Pre-order price:** **$289**, discounted from a struck-through **$319**. The $289 pre-order **includes the first year of the app subscription** (normally $79.99/yr).
- **Expected retail (post-launch):** **$319 device + $79.99/yr membership** (per fort.cx, the authoritative source). ⚠️ *Some press (e.g. Athletech, New Atlas) quote **$349** retail — the site says $319. Treat $319 as truth; expect models to echo the press's $349.*
- **Free tier:** Yes — "a free tier is always available" after the first included year.
- **Refunds:** Pre-orders fully refundable; cancel anytime before shipment.
- **Customization (no price change stated):** device colors Silver / Black / Gold; straps in Sports Fabric, Silicone, and Leather (multiple colorways).

## C · Features & capabilities

- **Core (strength):** Automatic exercise detection (**50+ exercises**, barbell compounds to cable accessories), automatic rep counting, set + rest-period tracking, bar/rep **velocity**, **proximity to failure**, **time under tension**, per-muscle volume breakdowns, session scores, rep cadence — **no manual logging**.
- **Beyond strength:** Heart-rate zones, **VO2 max estimation**, sleep stages (deep / light / REM), recovery scoring, overnight **HRV**, all-day activity, real-time **stress** detection.
- **Sensors:** IMU (accelerometer + gyroscope) + PPG heart-rate sensor.
- **Specs:** **7-day battery life** (normal use); **Bluetooth Low Energy**; interchangeable bands.
- **App:** Companion app on **both iOS and Android**.
- **Things it is NOT / common misconceptions (false-positive guards):** Not a screen-first smartwatch — it's positioned as a wristband whose differentiator is *automatic strength tracking* (most rivals only do heart rate / calories / duration); not shipping yet (pre-order only).

## D · Positioning & competitors

- **Ideal customer:** Lifters / strength-training enthusiasts who want automatic, hands-free tracking of reps, sets, and training load — and want strength data in the context of overall health.
- **Key differentiators (factual):** First/only wearable built specifically for **automatic strength tracking** (rep/set/exercise detection, proximity-to-failure, time under tension) — capabilities general wearables don't offer; combines that with full all-day cardio/sleep/stress tracking.
- **Named competitors / the benchmark set:** *Not named on the site.* For the audit, the comparison set must be chosen — likely candidates by category overlap: **WHOOP, Oura, Apple Watch, Garmin, Fitbit, Ultrahuman** (general wearables), and any dedicated strength/rep-tracker (e.g., a device positioned on velocity-based training). **Decide and lock the competitor set before the run.**
- **Most often confused with:** Likely general fitness wearables (Whoop/Oura/Apple Watch) — Fort's claim is they *don't* do automatic strength tracking, so a model conflating Fort with them is a competitor-confusion flag.

## E · Known-inaccuracy watch-list
*Pre-fill the wrong things you expect AIs to say. For a brand-new, pre-launch company, the dominant risk is that the models have little or no training data on Fort — so the highest-value findings will be **absence** (not mentioned at all) and **hallucination/invention** if a model pretends to know it.*

| Claim models make | Reality | Flag type | Severity |
|---|---|---|---|
| Fort doesn't exist / "no such product" / confusing it with something else | Fort is a real pre-launch strength-training wearable (fort.cx) | identity | high |
| Any specific price other than $289 pre-order / $319 retail | $289 pre-order (incl. 1yr app), $319 + $79.99/yr retail | wrong_pricing | high |
| "Already shipping / available now" | Pre-order only; Batch 1 ships **Q3 2026** | stale / identity | high |
| Invented features it doesn't claim (e.g., blood pressure, ECG, GPS) | Capabilities are those in §C; anything else is invented | missing_or_invented_feature | high |
| "No app for Android" / iOS-only | App is on **both iOS and Android** | missing_or_invented_feature | med |
| Wrong battery (e.g., "1–2 days") | **7-day** battery | missing_or_invented_feature | med |
| "It's just a heart-rate band like Whoop" | Differentiator is automatic strength/rep/exercise tracking | competitor_confusion | med |

*Severity guide: **high** = misleads a buyer (wrong price, "doesn't exist," invented feature); **med** = outdated/incomplete; **low** = cosmetic.*

---

### Notes for the run

- **Two big asks before the audit:** (1) **lock the competitor set** (the site names none — pick 3–5 by category overlap, e.g. Whoop / Oura / Apple Watch / Garmin + a strength-specific tracker), and (2) expect a very different shape from Oura: Fort is **pre-launch and obscure**, so the story is likely "the AI engines barely know you exist, and where they do, they may invent details" — an *absence/visibility* problem more than the *stale-facts* problem Oura had. That's still a strong demo for a founder ("buyers asking AI about strength wearables never hear your name").
- A few site facts are deliberately left blank (founding year, HQ, exact founder names) because they aren't stated publicly — per the "blank is safe" rule, the judge simply won't accuracy-check those dimensions.

---

**Ground-truth validation (2026-06-19):** identity + features re-verified against Athletech News, New Atlas, Wellworthy, and fort.cx — Fort is a **screenless wristband** (ex-Tesla, SF) that auto-tracks reps / velocity / range-of-motion / proximity-to-failure across 50+ exercises, plus cardio / sleep / stress; pre-order **$289**, retail **$319 + $79.99/yr** (press's $349 is the known discrepancy); ships **Q3 2026**. The 3 Fort gold flags (the item-10 "Fortis" hallucination) rest on these confirmed facts.
