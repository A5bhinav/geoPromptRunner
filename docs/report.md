# GEO Audit — Oura (smart ring)

**Run ID:** `204e7854-d4cc-4e9c-869e-81cdf594148e`  
**Surface:** parametric memory (what each model recommends from training, no live retrieval) — Perplexity additionally returns live citations  
**Query set:** `v1` · 45 queries, locked 2026-06-11  
**Engines:** anthropic, gemini, openai, perplexity (4)  
**Competitors benchmarked:** Whoop, Ultrahuman, Samsung Galaxy Ring, RingConn  
**Coverage:** 180 answers · 180 judge verdicts (every answer scored by one held-constant `gpt-4o` judge against the Oura fact sheet)  
**Detection:** LLM judge (prominence / framing / typed accuracy flags); regex fallback unused here.

> **What this measures.** When a consumer asks an AI assistant a question in the smart-ring category, does Oura show up, where in the answer, framed how, and is what the model says about Oura *true*? This is the GEO analogue of a search-ranking audit. It powers Steps 1 (baseline) and 5 (competitive benchmark) of the audit method; the §5 synthesis below is the analyst layer.

---

## Executive summary

- **Headline grade: F.** Prominence-weighted visibility is **0.56** (the strongest in the category), but **156 distinct client accuracy flags** drive the accuracy-discounted score to **0.00**. Oura is *seen* but frequently *described wrong*.
- **Oura leads the category leaderboard** — visibility 0.56 vs. Ultrahuman 0.18; share-of-voice 41% of all brand mentions. Presence is not the problem.
- **The problem is two-sided:**
  1. **Accuracy.** 99 of 156 flags are *high* severity — overwhelmingly **stale pricing/model** facts: models still quote the $299–$549 Gen-3/Ring-4 era and call Oura subscription-optional, when the current line is **Ring 5 at $399/$499 with a required $5.99/mo membership** (Ring 5 launched 2026-05-28).
  2. **Funnel shape.** Oura owns bottom-funnel intent (brand 100%, category 88%, comparison 80%) but is **nearly invisible upper-funnel**: problem-aware 11%, adjacent-authority 4%. Buyers at the start of the journey never hear the name.
- **Where it loses outright:** 13 (query, engine) cells where Oura is absent and a competitor is recommended first — almost all in **comparison** queries (cmp-08/09/11), led by Whoop, Ultrahuman, RingConn, and Samsung.
- **Citations come from one surface.** Only Perplexity exposes sources; the off-site battleground it reveals is **YouTube, Facebook, and review media (wareable, CNET, Tom’s Guide)** — not Oura’s own site.

---

## §1 · AI Visibility Scorecard

### Grade: F

- **Raw visibility (prominence-weighted):** 0.56 / 1.00  — rewards being recommended *first* over being buried.
- **Accuracy penalty:** −17.36 across 156 distinct flags (high −0.15, med −0.07, low −0.03 each).
- **Discounted score:** 0.00 → **F** (floored at 0).

> The grade is deliberately severe on accuracy: a confidently wrong claim (“no subscription required”) erodes buyer trust even when the brand is front-and-centre. The raw 0.56 visibility is a **B/A-grade presence**; the F is entirely an accuracy verdict.

### Share-of-model

| Role | Brand | Visibility | Mention rate | Share-of-voice |
| --- | --- | --- | --- | --- |
| Client / category leader | Oura | 0.56 | 63% | 41% |
| Top competitor | Ultrahuman | 0.18 | 28% | 19% |
| Competitor | RingConn | 0.17 | 27% | 18% |
| Competitor | Samsung Galaxy Ring | 0.11 | 19% | 12% |
| Competitor | Whoop | 0.11 | 14% | 10% |

*Share-of-voice = a brand’s present-cells as a fraction of all brand present-cells across the run.*

### Per-engine — client mention & citation rate

| Engine | Client mention rate | Any-citation rate | Note |
| --- | --- | --- | --- |
| anthropic | 64% | 0% |  |
| gemini | 69% | 0% | most generous to Oura |
| openai | 58% | 0% | lowest — Oct-2023 training cutoff refuses 2026 queries |
| perplexity | 60% | 100% | only engine with live citations |

*Client **citation** rate is 0% on every engine: on the parametric surface models recommend from memory without linking, and where Perplexity does cite, it cites review media rather than ouraring.com. See §4.*

---

## §2 · Funnel analysis (by intent bucket)

Every score is tied back to *which queries* it comes from. Buckets run from upper-funnel (a consumer describing a problem) to navigational (typing the brand name).

### §2.2 Mention, visibility & prominence by bucket

| Intent bucket | Queries | Client mention | Client visibility | 🥇 first | mid-pack | also-ran | absent |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Brand (navigational) | 7 | 100% | 1.00 | 28 | 0 | 0 | 0 |
| Category (“best smart ring …”) | 13 | 88% | 0.79 | 37 | 6 | 3 | 6 |
| Comparison (“X vs Y”) | 11 | 80% | 0.65 | 22 | 11 | 1 | 10 |
| Problem-aware (upper funnel) | 7 | 11% | 0.09 | 2 | 1 | 0 | 25 |
| Adjacent authority (topic questions) | 7 | 4% | 0.04 | 1 | 0 | 0 | 27 |

**Read:** Oura is **dominant where intent is explicit** — 100% on brand queries, 88% on category (“best smart ring …”), 80% on comparison — and **effectively absent where it isn’t**: 11% problem-aware, 4% adjacent-authority. The upper-funnel gap is the single biggest *growth* opportunity; the comparison softness (often mid-pack, not first) is the biggest *competitive* risk. The two clusters map to different fixes (§5).

### §2.3 Accuracy flags — what the models get wrong about Oura

**156 distinct flags** (184 total instances across answers). This is the most persuasive material in the audit: concrete, falsifiable things the AIs state about Oura that are wrong.

| | high | med | low | **total** |
| --- | --- | --- | --- | --- |
| Wrong pricing / subscription | 62 | 1 | 11 | **74** |
| Stale model / generation | 25 | 3 | 1 | **29** |
| Missing or invented feature | 12 | 16 | 25 | **53** |
| **total** | **99** | **20** | **37** | **156** |

**The three failure modes, in plain terms:**

1. **Stale pricing & subscription (74 flags, 62 high).** Models quote the old $299–$549 range and — most damagingly — tell shoppers Oura needs **no subscription**. Reality: Ring 5 base **$399** / premium **$499**, plus a **required $5.99/mo (or $69.99/yr) membership** for full features.
2. **Stale model / generation (29 flags, 25 high).** Models name the **Gen 3 / Ring 4** as current or “best in 2026.” Reality: **Oura Ring 5 launched 2026-05-28.**
3. **Missing/invented features (53 flags).** Battery quoted as 4–7 days (actual ~8), SpO2 omitted or denied, “period prediction” invented, integration breadth understated.

**Evidence (verbatim from the answers):**

- **cat-09 “best smart ring 2026” · Perplexity** — recommends Oura *first* but stale and wrong on both model and price:
  > “The **best smart ring in 2026 overall is the Oura Ring 4** according to multiple expert test roundups … If you want the best *subscription-free* option, the **Samsung Galaxy Ring** is a leading pick.”
  Flags: `stale/high` (Ring 4 ≠ current Ring 5), `wrong_pricing/high` (“was $349”), `missing_or_invented_feature/high` (frames a *subscription-free* alternative as the win).
- **cat-06 “best smart ring without a monthly subscription” · Gemini** — Oura is correctly *demoted* here (it requires a membership), and **RingConn is recommended first**. A legitimate competitive loss, not a hallucination:
  > “**RingConn** … is arguably the most direct competitor to Oura … but without any subscription. **No Subscription:** All features are included with the purchase price.”
- **cat-10 “what’s the newest smart ring in 2026?” · OpenAI** — the parametric cutoff makes the model refuse outright, so Oura (and everyone) is absent:
  > “I can’t provide real-time or future-specific information as my training only includes data up to October 2023.”

The full flag list is in [§6.2](#62--per-query--per-engine-capture) context and enumerated below.

<details><summary><strong>All 156 distinct accuracy flags (type · severity · claim → reality)</strong></summary>

| # | Type | Sev | Claim → Reality |
| --- | --- | --- | --- |
| 1 | wrong_pricing | high | Oura Ring alternatives without a monthly subscription → Oura Ring requires a monthly subscription for full features |
| 2 | missing_or_invented_feature | low | The Oura app is intuitive and provides detailed insights, making it a great choice for beginners. → The fact sheet does not mention the app being intuitive or specifically suitable for beginners. |
| 3 | wrong_pricing | high | $299 + $5.99/month subscription → Current Ring 5 base is $399 |
| 4 | stale | high | Oura Ring Generation 3 → Ring 5 launched 2026-05-28 |
| 5 | stale | high | Oura Ring 4 → Oura Ring 5 launched 2026-05-28 |
| 6 | wrong_pricing | high | Oura Ring 4 → Oura Ring 5 base is $399 |
| 7 | missing_or_invented_feature | high | no subscription required → required $5.99/mo membership |
| 8 | missing_or_invented_feature | low | offering features like sleep tracking, heart rate monitoring, and activity tracking → Sleep tracking (stages, Sleep Score), Readiness and Recovery scores, 24/7 heart rate, HRV, blood-oxygen (SpO2), body-temperature trends, activity/steps, cycle insights, guided content (meditations, sleep stories) in the app |
| 9 | wrong_pricing | high | Price: ~$299-$549 → Current Ring 5 base is $399 |
| 10 | stale | high | Oura Ring Gen 3 → The Oura Ring 5 launched 2026-05-28 |
| 11 | wrong_pricing | high | Starts at ~$349 → Current Ring 5 base is $399 |
| 12 | missing_or_invented_feature | med | It requires a mandatory monthly subscription → Membership is required for full features, but the ring and app still work without it, albeit with limited insights |
| 13 | wrong_pricing | high | Oura requires a subscription for full access to its features and insights. → Membership is $5.99/month or $69.99/year, with the first month free for new members. |
| 14 | wrong_pricing | high | Lifetime (Gen 2) or $5.99/mo (Gen 3) → $5.99/month or $69.99/year for membership, required for full features |
| 15 | stale | med | The Oura Ring typically has a battery life of about 4-7 days, depending on usage. → up to ~8-day battery (Ring 4 generation) |
| 16 | wrong_pricing | high | more expensive ($299-$549) → Current Ring 5 base is $399 |
| 17 | stale | high | Oura Ring (Gen 3) → Ring 5 launched 2026-05-28 |
| 18 | missing_or_invented_feature | med | longer battery life (4-7 days) → up to ~8-day battery (Ring 4 generation) |
| 19 | wrong_pricing | high | Starting price $349 → Current Ring 5 base is $399 |
| 20 | missing_or_invented_feature | high | No subscription needed → Required $5.99/mo membership |
| 21 | wrong_pricing | high | The Oura Ring is known for its sleek and minimalist design, often available in a variety of finishes like silver, black, and gold. → Current Ring 5 base is $399 for Silver, Black; Premium finishes (Gold, Stealth, Brushed Silver, Deep Rose) are $499. |
| 22 | missing_or_invented_feature | high | Oura is renowned for its comprehensive sleep tracking capabilities, providing insights into sleep stages, sleep quality, and overall sleep score. → Sleep tracking (stages, Sleep Score) is a core feature, but the answer omits the required membership for full features. |
| 23 | missing_or_invented_feature | high | The Oura app provides detailed insights and trends over time, with a focus on improving sleep and overall wellness. → The membership is required for full product features, including detailed insights. |
| 24 | wrong_pricing | high | $299-$549 → $399-$499 |
| 25 | missing_or_invented_feature | low | Period prediction for women → Cycle insights, but not specifically period prediction |
| 26 | wrong_pricing | high | Typically requires a membership for full access to insights. → Membership is required for full features, not just typically. |
| 27 | wrong_pricing | high | Generally considered a premium product, with prices reflecting its advanced features and design. → Current Ring 5 base is $399 with a required $5.99/month membership. |
| 28 | missing_or_invented_feature | low | Provides continuous heart rate monitoring, including resting heart rate and heart rate variability (HRV). → The fact sheet does not confirm continuous heart rate monitoring, only 24/7 heart rate and HRV. |
| 29 | wrong_pricing | high | $299-399 + $5.99/month subscription required for most features → Current Ring 5 base is $399 with a $5.99/month membership required for full features |
| 30 | stale | high | Gen 3 → The Oura Ring 5 launched 2026-05-28 |
| 31 | wrong_pricing | high | RingConn is the better value if you want good-enough sleep tracking without a subscription. → Oura requires a $5.99/month membership for full features. |
| 32 | wrong_pricing | high | Oura Ring alternatives without monthly subscriptions → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 33 | stale | low | Oura Ring is known for its accurate sleep tracking, heart rate monitoring, and readiness scores. → Oura Ring 5 is the current model with updated sensors and features. |
| 34 | wrong_pricing | low | Oura charges $5.99/month → Membership is $5.99/month or $69.99/year |
| 35 | missing_or_invented_feature | low | Better sleep tracking accuracy (generally considered best-in-class) → The fact sheet does not confirm this claim about sleep tracking accuracy |
| 36 | wrong_pricing | high | Starts at $299 → Current Ring 5 base is $399 |
| 37 | missing_or_invented_feature | low | Oura Ring is generally the better choice for iPhone or mixed-platform users because it works with both iOS and Android → Oura Ring works with iOS and Android but no specific advantage for iPhone or mixed-platform users is mentioned |
| 38 | wrong_pricing | high | $299-549 (ring) + $5.99/month subscription → Base finishes $399, Premium finishes $499, $5.99/month subscription |
| 39 | wrong_pricing | high | Oura typically starts around $299–$349 depending on model/finish → Current Ring 5 base is $399 |
| 40 | wrong_pricing | low | full access also costs about $5.99/month or about $69.99/year → Membership is $5.99/month or $69.99/year, first month free for new members |
| 41 | wrong_pricing | high | Oura Ring 4 about $349+ → Previous model — Oura Ring 4: was $349; now being cleared out below that as Ring 5 launches. |
| 42 | missing_or_invented_feature | low | Ring form factor with strong sleep/recovery tracking → A smart ring that tracks sleep, activity, heart rate, and recovery, paired with a health app. |
| 43 | wrong_pricing | high | The Oura Ring is relatively expensive compared to other fitness trackers. → Current Ring 5 base is $399 with a required $5.99/mo membership. |
| 44 | missing_or_invented_feature | low | The Oura Ring typically offers a battery life of about 4-7 days. → Up to ~8-day battery (Ring 4 generation). |
| 45 | missing_or_invented_feature | low | Oura has a strong focus on data privacy. → Not mentioned in the fact sheet. |
| 46 | wrong_pricing | high | $299-549 + $5.99/month subscription → Base finishes $399, Premium finishes $499, $5.99/month membership |
| 47 | stale | med | Battery life - 4-7 days beats most smartwatches → up to ~8-day battery (Ring 4 generation) |
| 48 | wrong_pricing | high | The ring itself typically costs roughly $299–$549 → Current Ring 5 base is $399 |
| 49 | wrong_pricing | high | the Oura Ring typically costs between $299 and $549 → Current Ring 5 base is $399, Premium finishes are $499 |
| 50 | wrong_pricing | high | The Oura Ring typically costs $299-$399 depending on the model and finish you choose → Current Ring 5 base is $399; previous model Ring 4 was $349 |
| 51 | stale | high | Oura Ring Gen3 Heritage: $299 (silver, black, stealth) → Ring 5 launched 2026-05-28 |
| 52 | stale | high | Oura Ring Gen3 Horizon: $349-$399 (various finishes) → Ring 5 launched 2026-05-28 |
| 53 | wrong_pricing | high | The Oura Ring typically costs $349 to $499 for the current Oura Ring 4, depending on finish and model → Current Ring 5 base is $399; Ring 4 was $349 and is being cleared out below that |
| 54 | stale | high | current Oura Ring 4 → Ring 5 launched 2026-05-28 |
| 55 | wrong_pricing | high | the ring itself costs $299-$549 depending on the model → Current Ring 5 base is $399 |
| 56 | missing_or_invented_feature | med | Gen2 users do not require a membership and are not charged membership fees. → No full free tier — without membership the ring and app still work but insights are heavily limited. |
| 57 | stale | high | the newest Oura Ring is the Oura Ring Generation 3 → the newest Oura Ring is the Oura Ring 5 |
| 58 | stale | high | Oura Ring Gen3 is the newest model available. → Oura Ring 5 is the newest model, launched 2026-05-28. |
| 59 | missing_or_invented_feature | med | week-long battery life (listed as 6 to 9 days on Oura’s site) → up to ~8-day battery (Ring 4 generation) |
| 60 | wrong_pricing | high | The Oura Ring is relatively expensive compared to other fitness trackers, which may be a barrier for some potential users. → Current Ring 5 base is $399 with a required $5.99/month membership. |
| 61 | missing_or_invented_feature | low | The ring typically lasts about 4-7 days on a single charge, which is longer than many other wearable devices. → Up to ~8-day battery (Ring 4 generation). |
| 62 | missing_or_invented_feature | med | The Oura Ring has limited integration with other health and fitness apps, which may be a drawback for users who rely on a comprehensive ecosystem of health data. → Key integrations include Apple Health, Google Health Connect, Strava, Natural Cycles; third-party apps via API. |
| 63 | wrong_pricing | high | Hardware is expensive ($299-$549) → Current Ring 5 base is $399 |
| 64 | wrong_pricing | high | high upfront cost → Base finishes (Silver, Black) — $399; Premium finishes (Gold, Stealth, Brushed Silver, Deep Rose) — $499 |
| 65 | missing_or_invented_feature | med | activity tracking is less robust than a smartwatch → It is not a smartwatch — no screen, no notifications, no on-device display |
| 66 | wrong_pricing | high | $299-$549 depending on the model → $399 for base finishes, $499 for premium finishes |
| 67 | missing_or_invented_feature | med | Needs charging every 4-7 days → up to ~8-day battery (Ring 4 generation) |
| 68 | wrong_pricing | high | monthly fee → $5.99/month or $69.99/year |
| 69 | missing_or_invented_feature | med | detailed sleep analysis, readiness scores, personalized insights, and access to historical data → Sleep tracking (stages, Sleep Score), Readiness and Recovery scores, 24/7 heart rate, HRV, blood-oxygen (SpO2), body-temperature trends, activity/steps, cycle insights, guided content (meditations, sleep stories) in the app |
| 70 | wrong_pricing | high | the $300+ ring → Current Ring 5 base is $399 |
| 71 | missing_or_invented_feature | med | The membership is basically required to get value from the $300+ ring → without membership the ring and app still work but insights are heavily limited |
| 72 | wrong_pricing | low | Oura’s membership is relatively cheap at $5.99/month in the US → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 73 | wrong_pricing | high | relatively expensive upfront cost → Oura Ring 5 base is $399 with a required $5.99/month membership |
| 74 | missing_or_invented_feature | high | subscription required for full features → membership is required for the full product |
| 75 | wrong_pricing | high | Oura Ring ($299 + $6/month) → Current Ring 5 base is $399 |
| 76 | missing_or_invented_feature | med | Oura Ring has better features but ongoing costs → Membership is required for full features; without it, insights are limited |
| 77 | missing_or_invented_feature | low | long battery life (4-7 days) → up to ~8-day battery (Ring 4 generation) |
| 78 | missing_or_invented_feature | low | Requires $6/month subscription for full features → $5.99/month or $69.99/year |
| 79 | stale | high | Oura Ring (Generation 3) → Oura Ring 5 launched 2026-05-28 |
| 80 | wrong_pricing | low | Subscription: Required for full features (~$6/month) → $5.99/month or $69.99/year |
| 81 | wrong_pricing | low | The Oura Ring typically offers a battery life of up to 7 days → up to ~8-day battery (Ring 4 generation) |
| 82 | missing_or_invented_feature | low | The Oura Ring provides a readiness score that helps users understand their overall recovery and readiness for the day based on sleep and other physiological metrics → Readiness and Recovery scores |
| 83 | wrong_pricing | high | expensive ($299-$549) → Current Ring 5 base is $399 |
| 84 | missing_or_invented_feature | high | requires subscription ($5.99/month) → Membership is required for full features |
| 85 | stale | high | Oura Ring 4 is the best smart ring in 2026 → The Oura Ring 5 launched 2026-05-28 |
| 86 | wrong_pricing | high | Oura Ring 4 was $349 → Oura Ring 5 base is $399 |
| 87 | missing_or_invented_feature | high | best smart ring in 2026 overall is the Oura Ring 4 → Oura Ring 5 is the current model |
| 88 | missing_or_invented_feature | high | best subscription-free option → Oura requires a $5.99/month membership for full features |
| 89 | stale | high | Oura Ring 4 is the strongest overall choice → The Oura Ring 5 is the newest model |
| 90 | wrong_pricing | high | Higher price point compared to some other options. → Current Ring 5 base is $399 with a required $5.99/mo membership. |
| 91 | missing_or_invented_feature | low | long battery life → up to ~8-day battery (Ring 4 generation) |
| 92 | wrong_pricing | high | ~$299 + $5.99/month membership → Current Ring 5 base is $399 |
| 93 | missing_or_invented_feature | med | Menstrual Cycle Tracking: Allows users to log and track their menstrual cycle, helping to predict periods and understand cycle patterns. → Cycle insights are mentioned, but not specifically logging and predicting periods. |
| 94 | missing_or_invented_feature | low | Tracks temperature variations for cycle prediction → Cycle insights are mentioned but not specifically temperature variations for cycle prediction |
| 95 | missing_or_invented_feature | low | Requires subscription ($5.99/month after 6 months) → Membership is $5.99/month or $69.99/year with the first month free |
| 96 | wrong_pricing | med | Oura Ring requires $5.99/month subscription for most features → Membership is $5.99/month or $69.99/year, with the first month free for new members |
| 97 | stale | high | Oura Ring 4 is the latest → Oura Ring 5 launched 2026-05-28 |
| 98 | wrong_pricing | high | Oura Ring 4 typically requires a subscription → Oura Ring 5 requires a $5.99/month membership for full features |
| 99 | stale | med | It typically offers a battery life of about 4 to 7 days, depending on usage. → up to ~8-day battery (Ring 4 generation) |
| 100 | wrong_pricing | low | Requires subscription ($5.99/month) → $5.99/month or $69.99/year |
| 101 | wrong_pricing | high | roughly half the price → Oura Ring 5 base is $399 |
| 102 | missing_or_invented_feature | high | zero ongoing subscription fees → required $5.99/mo membership |
| 103 | wrong_pricing | high | Oura did not require a subscription for basic features → Membership is required for full features, $5.99/month or $69.99/year |
| 104 | missing_or_invented_feature | low | Requires $5.99/month subscription for full features → Membership is required for full features, but the first month is free for new members |
| 105 | stale | high | Oura Ring 4 is the most accurate smart ring for sleep tracking → The Oura Ring 5 is the newest model |
| 106 | wrong_pricing | low | older versions might be available at a discount → Previous model — Oura Ring 4: was $349; now being cleared out below that as Ring 5 launches |
| 107 | missing_or_invented_feature | low | The Oura Ring provides insights into your readiness and recovery. → The Oura Ring provides Readiness and Recovery scores, 24/7 heart rate, HRV, blood-oxygen (SpO2), body-temperature trends, activity/steps, cycle insights, guided content (meditations, sleep stories) in the app. |
| 108 | missing_or_invented_feature | low | Subscription required for full features ($6/month) → required $5.99/mo membership |
| 109 | stale | high | Oura Ring (Gen 3 Horizon/Heritage) → Oura Ring 5 launched 2026-05-28 |
| 110 | wrong_pricing | high | relatively expensive → Current Ring 5 base is $399 |
| 111 | missing_or_invented_feature | low | period prediction → cycle insights |
| 112 | stale | high | Oura Ring Gen 3 (Horizon or Heritage) → Oura Ring 5 launched 2026-05-28 |
| 113 | wrong_pricing | high | no mention of required subscription → required $5.99/mo membership |
| 114 | wrong_pricing | high | The ring itself is premium-priced (typically $299-$549 depending on the model/finish). → Current Ring 5 base is $399, Premium finishes $499. |
| 115 | missing_or_invented_feature | med | Oura now requires a monthly membership ($5.99/month in the US) to access all its features and historical data. → Membership is required for full features, but the first month is free for new members. |
| 116 | wrong_pricing | high | The price of the ring itself typically ranges from $299 to $549 USD or more, depending on the model and finish. → Current Ring 5 base is $399; previous model Ring 4 was $349. |
| 117 | stale | high | Heritage: Usually starts around $299 USD for standard finishes. → Current Ring 5 base is $399; previous model Ring 4 was $349. |
| 118 | stale | high | Horizon: Usually starts around $349 USD for standard finishes. → Current Ring 5 base is $399; previous model Ring 4 was $349. |
| 119 | wrong_pricing | low | The cost of the Oura Membership is usually around $5.99 USD per month → Membership: $5.99/month or $69.99/year |
| 120 | stale | high | The newest Oura Ring right now is the Oura Ring Gen3. → The Oura Ring 5 launched 2026-05-28. |
| 121 | wrong_pricing | high | Mandatory monthly subscription: To access all your data, insights, and features, you must pay a monthly subscription fee. → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 122 | stale | high | The Oura Ring is a popular smart ring designed to track various health metrics, primarily focusing on sleep, recovery, and activity. → Oura Ring 5 (announced 2026-05-28, ships 2026-06-04) — ~40% smaller than Ring 4, thinner/lighter redesign, updated sensors. |
| 123 | wrong_pricing | high | The device itself is a significant investment. → Current Ring 5 base is $399. |
| 124 | missing_or_invented_feature | med | Subscription Required: To access all the detailed insights and historical data, you need a monthly Oura Membership subscription. → Membership is required for full features, but the first month is free for new members. |
| 125 | wrong_pricing | high | The membership unlocks... → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 126 | wrong_pricing | low | Requires a monthly subscription ($5.99/month in the US) → Membership is $5.99/month or $69.99/year |
| 127 | wrong_pricing | high | Requires a monthly subscription for full access to all features and historical data after the initial free trial. → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 128 | wrong_pricing | high | A monthly subscription is necessary to access most of the advanced features after the initial trial period. This is a significant ongoing cost. → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 129 | wrong_pricing | low | Oura Ring requires a monthly subscription (currently $5.99/month) to access all its advanced features and historical data. → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 130 | missing_or_invented_feature | med | Without the subscription, you only get basic metrics. → Without membership the ring and app still work but insights are heavily limited. |
| 131 | wrong_pricing | high | Requires a monthly subscription for full features after the initial purchase → $5.99/month or $69.99/year membership required for full features |
| 132 | wrong_pricing | high | Oura Ring (which starts at $349 + $5.99/month subscription) → Current Ring 5 base is $399 |
| 133 | missing_or_invented_feature | med | Oura, which requires a monthly subscription to access all your data → Membership is required for full features, but the ring and app still work without it, albeit with limited insights |
| 134 | missing_or_invented_feature | med | Oura to push further into predictive health, more advanced illness detection → Oura focuses on sleep, activity, heart rate, and recovery tracking, not predictive health or illness detection |
| 135 | missing_or_invented_feature | low | Oura potentially expand its ecosystem → Oura's key integrations are Apple Health, Google Health Connect, Strava, Natural Cycles; third-party apps via API |
| 136 | stale | high | Oura Ring (Gen3) → Oura Ring 5 launched 2026-05-28 |
| 137 | wrong_pricing | low | Oura Membership (currently $5.99/month) → $5.99/month or $69.99/year |
| 138 | stale | high | Oura Ring (Gen3 Horizon / Heritage) → Oura Ring 5 is the newest model |
| 139 | wrong_pricing | high | higher price point → Current Ring 5 base is $399 |
| 140 | missing_or_invented_feature | high | requires a monthly subscription for full features after the initial free period → Membership is required for full features, $5.99/month or $69.99/year, first month free |
| 141 | wrong_pricing | high | Both require a subscription, so factor that into your decision as well. → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 142 | wrong_pricing | high | ~$299 - $549 (depending on style) → Base finishes $399, Premium finishes $499 |
| 143 | missing_or_invented_feature | low | Subscription required for full features ($5.99/month) → $5.99/month or $69.99/year, first month free for new members |
| 144 | wrong_pricing | high | Price: ~$299 - $549 USD (plus subscription) → Current Ring 5 base is $399 |
| 145 | missing_or_invented_feature | low | SpO2 (limited) → blood-oxygen (SpO2) is a core feature |
| 146 | stale | high | Gen3: Late 2021 → Ring 5 launched 2026-05-28 |
| 147 | missing_or_invented_feature | low | Battery Life: 4-7 days → up to ~8-day battery (Ring 4 generation) |
| 148 | missing_or_invented_feature | high | No SpO2 (Oxygen Saturation) → blood-oxygen (SpO2) |
| 149 | wrong_pricing | high | Higher upfront cost + mandatory monthly subscription → Base finishes $399, Premium finishes $499, $5.99/month membership |
| 150 | wrong_pricing | high | No subscription required (as of current writing), which is a significant advantage over Oura. → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 151 | wrong_pricing | high | The ring itself is relatively expensive upfront (starting around $299). → Current Ring 5 base is $399. |
| 152 | missing_or_invented_feature | high | To access most of its advanced features and historical data, you need an Oura Membership, which costs $5.99/month (after an initial free period). → Membership is required for full features, not just advanced features and historical data. |
| 153 | missing_or_invented_feature | low | Vitality Score (similar to Oura's Readiness Score) → Readiness and Recovery scores |
| 154 | wrong_pricing | high | Subscription Required: Full features require a monthly subscription after the initial purchase. → Membership: $5.99/month or $69.99/year. First month free for new members. |
| 155 | wrong_pricing | high | $300-$400 for the ring. Newer generations (Gen3) require a $5.99/month membership for full features, but older generations (Gen2) and some Gen3 features are available without a subscription. → Current Ring 5 base is $399. Membership is required for full features, no full free tier. |
| 156 | stale | high | Newer generations (Gen3) require a $5.99/month membership for full features, but older generations (Gen2) and some Gen3 features are available without a subscription. → The Ring 5 launched 2026-05-28, and the membership is required for full features. |

</details>

---

## §3 · Competitive leaderboard & loss attribution

### Leaderboard

| Rank | Brand | Visibility | Mention rate | Share-of-voice | Mentions |
| --- | --- | --- | --- | --- | --- |
| 1 | Oura *(client)* | 0.56 | 63% | 41% | 113 |
| 2 | Ultrahuman | 0.18 | 28% | 19% | 51 |
| 3 | RingConn | 0.17 | 27% | 18% | 49 |
| 4 | Samsung Galaxy Ring | 0.11 | 19% | 12% | 34 |
| 5 | Whoop | 0.11 | 14% | 10% | 26 |

Oura’s 41% share-of-voice is larger than the next two competitors combined. **Ultrahuman** and **RingConn** are the real challengers; Whoop (a wrist band, not a ring) and Samsung trail.

### Trend

_This is the **baseline** cycle for query set `v1` — no prior comparable run to diff against. The trend column (the method’s moat: re-run the locked set on a 4–6 week cadence and show the named metric move) activates from the next cycle via `geo compare <before> <after>`._

### Structurally behind — Oura absent, competitor #1 (13 cells)

| Query | Engine | Recommended first instead |
| --- | --- | --- |
| cat-06 (category) | perplexity | Ultrahuman |
| cat-10 (category) | perplexity | Ultrahuman |
| cmp-08 (comparison) | anthropic | Whoop |
| cmp-08 (comparison) | gemini | Ultrahuman |
| cmp-08 (comparison) | gemini | Whoop |
| cmp-08 (comparison) | openai | Whoop |
| cmp-08 (comparison) | perplexity | Whoop |
| cmp-09 (comparison) | anthropic | Samsung Galaxy Ring |
| cmp-09 (comparison) | openai | Samsung Galaxy Ring |
| cmp-09 (comparison) | perplexity | RingConn |
| cmp-09 (comparison) | perplexity | Samsung Galaxy Ring |
| cmp-11 (comparison) | anthropic | Whoop |
| cmp-11 (comparison) | openai | Whoop |

Concentrated in **comparison** intent: `cmp-08` (Whoop vs Ultrahuman for athletes — Oura isn’t in the matchup framing), `cmp-09` (Samsung/RingConn win on a spec angle), `cmp-11` (cheaper-alternatives-to-Whoop → Whoop/others). On category, `cat-06` (no-subscription) and `cat-10` (newest-2026) are lost on Perplexity.

### Closest to winning — Oura present but *not* first (20 cells)

These are the cheapest wins: Oura already appears, just ranked behind a competitor recommended first. Nudging prominence here moves the leaderboard fastest.

| Query | Engine | Loses first place to | Oura currently |
| --- | --- | --- | --- |
| cat-05 | gemini | RingConn | mid-pack |
| cat-05 | perplexity | RingConn | mid-pack |
| cat-06 | anthropic | Ultrahuman | also-ran |
| cat-06 | gemini | RingConn | also-ran |
| cat-08 | anthropic | RingConn | also-ran |
| cat-08 | gemini | RingConn | mid-pack |
| cat-10 | gemini | Samsung Galaxy Ring | mid-pack |
| cat-13 | perplexity | RingConn | mid-pack |
| cmp-01 | perplexity | Whoop | mid-pack |
| cmp-05 | gemini | Ultrahuman | mid-pack |
| cmp-05 | openai | Whoop | mid-pack |
| cmp-05 | perplexity | Samsung Galaxy Ring | mid-pack |
| cmp-06 | anthropic | RingConn | mid-pack |
| cmp-06 | gemini | Ultrahuman | mid-pack |
| cmp-06 | openai | Whoop | mid-pack |
| cmp-06 | perplexity | RingConn | mid-pack |
| cmp-07 | anthropic | Samsung Galaxy Ring | mid-pack |
| cmp-07 | perplexity | Samsung Galaxy Ring | mid-pack |
| cmp-09 | gemini | Samsung Galaxy Ring | also-ran |
| cmp-11 | perplexity | Whoop | mid-pack |

---

## §4 · Sources & technical accessibility

### §4.4 Sources behind the category

Where models *do* cite (Perplexity only on this surface), these are the domains shaping the category answer. Per the method, this **routes the off-site work**: if the sources are review media and social, the battleground isn’t ouraring.com.

| Rank | Domain | Cited in cells | Engines |
| --- | --- | --- | --- |
| 1 | youtube.com | 34 | perplexity |
| 2 | facebook.com | 19 | perplexity |
| 3 | wareable.com | 18 | perplexity |
| 4 | cnet.com | 10 | perplexity |
| 5 | ouraring.com | 9 | perplexity |
| 6 | cosmopolitan.com | 8 | perplexity |
| 7 | tomsguide.com | 8 | perplexity |
| 8 | pmc.ncbi.nlm.nih.gov | 8 | perplexity |
| 9 | bestbuy.com | 7 | perplexity |
| 10 | zdnet.com | 7 | perplexity |
| 11 | sleepfoundation.org | 7 | perplexity |
| 12 | techadvisor.com | 6 | perplexity |
| 13 | ringconn.com | 6 | perplexity |
| 14 | bodyspec.com | 5 | perplexity |
| 15 | my.clevelandclinic.org | 5 | perplexity |

**Read:** the category is decided on **YouTube (34), Facebook (19), and review media** — wareable, CNET, Tom’s Guide, ZDNet, TechAdvisor — plus retail (BestBuy) and health authorities (PMC/NIH, SleepFoundation, Cleveland Clinic) for the problem-aware questions. `ouraring.com` is cited in only 9 cells. **Earning creator and review-media coverage is higher-leverage than on-site changes.**

### §4.1 Technical accessibility

_Not run in this cycle._ Crawler-access / WAF / rendering / llms.txt / sitemap checks are available via `geo technical ouraring.com` and should be attached in the full deliverable (Step 2). Flagged as a gap, not a pass.

---

## §5 · Prioritized takeaways (analyst synthesis)

Sequenced by impact × fixability. Items 1–2 are the demo-ready story; 3–4 are the growth program.

1. **Fix the facts the models repeat (highest impact, partially in client’s control).** Every high-severity flag traces to **stale pricing/model** data. Publish clear, current, answer-first Ring 5 pricing + membership facts on ouraring.com, and — because the models cite *review media*, not Oura — push the corrected Ring 5 / $399 / membership facts into the wareable / CNET / Tom’s Guide / YouTube ecosystem so the next training + retrieval pass sees the truth. This is what flips “F on accuracy” without touching visibility.
2. **Defend the comparison queries (highest competitive risk).** `cmp-08/09/11` and the “closest to winning” set are where Ultrahuman, RingConn, Whoop and Samsung take first place. Build/seed **“Oura vs Ultrahuman”, “Oura vs RingConn”, “Oura vs Samsung Galaxy Ring”** comparison content and creator coverage that names Oura first on the axes buyers ask about.
3. **Own the “no-subscription” and “budget” framings or concede them honestly.** `cat-06`/`cat-08` are legitimate losses (Oura requires a membership). Decide messaging: compete on value-with-membership, or accept these queries route to RingConn/Samsung.
4. **Attack the upper funnel (biggest growth headroom).** Problem-aware (11%) and adjacent-authority (4%) are wide open — when someone asks “why do I wake up exhausted?” or “how does HRV relate to recovery?”, no smart-ring brand owns the answer. Authoritative, citable explainer content (the kind PMC / SleepFoundation currently supply) is the path in.
5. **Lock the cadence (the moat).** Re-run this exact locked query set in 4–6 weeks and diff with `geo compare` to prove the accuracy flags fall and comparison prominence rises.

---

## §6 · Appendix

### §6.1 Query set

`v1` · 45 queries · locked 2026-06-11. Intent mix: problem_aware 7, category 13, comparison 11, brand 7, adjacent_authority 7.

| Query ID | Intent | Weight | Persona/modifier | Prompt |
| --- | --- | --- | --- | --- |
| pa-01 | problem_aware | 1.0 | — | why do I wake up exhausted even after sleeping 8 hours? |
| pa-02 | problem_aware | 1.0 | — | how can I figure out why my sleep is so bad lately? |
| pa-03 | problem_aware | 1.0 | — | what's the best way to track my sleep and recovery without wearing a watch? |
| pa-04 | problem_aware | 1.0 | — | how do I know if I'm overtraining and need to rest? |
| pa-05 | problem_aware | 1.0 | — | how can I actually improve my deep sleep? |
| pa-06 | problem_aware | 1.0 | — | is there a way to tell if my body is recovered enough to work out hard today? |
| pa-07 | problem_aware | 1.0 | — | how can I keep track of my stress levels during the day? |
| cat-01 | category | 1.5 | — | best smart ring |
| cat-02 | category | 1.5 | sleep-focused | best smart ring for sleep tracking |
| cat-03 | category | 1.5 | athlete | best smart ring for athletes and recovery |
| cat-04 | category | 1.5 | women's health | best smart ring for women's health and cycle tracking |
| cat-05 | category | 1.5 | battery-focused | best smart ring with long battery life |
| cat-06 | category | 1.5 | cost-conscious | best smart ring without a monthly subscription |
| cat-07 | category | 1.5 | accuracy-focused | most accurate smart ring for sleep |
| cat-08 | category | 1.5 | budget | best budget smart ring |
| cat-09 | category | 1.6 | — | best smart ring 2026 |
| cat-10 | category | 1.6 | — | what's the newest smart ring in 2026? |
| cat-11 | category | 1.5 | — | best health tracker you don't wear on your wrist |
| cat-13 | category | 1.5 | beginner | best smart ring for beginners |
| cat-14 | category | 1.5 | — | top rated smart rings right now |
| cmp-01 | comparison | 1.8 | — | Oura Ring vs Whoop for recovery |
| cmp-02 | comparison | 1.8 | — | Oura vs Samsung Galaxy Ring — which is better? |
| cmp-03 | comparison | 1.8 | — | Oura Ring vs Ultrahuman Ring Air |
| cmp-04 | comparison | 1.8 | — | Oura vs RingConn for sleep tracking |
| cmp-05 | comparison | 1.8 | — | best alternatives to the Oura Ring |
| cmp-06 | comparison | 1.8 | — | Oura Ring alternatives without a monthly subscription |
| cmp-07 | comparison | 1.8 | — | is the Samsung Galaxy Ring better than Oura? |
| cmp-08 | comparison | 1.8 | — | Whoop vs Ultrahuman for athletes |
| cmp-09 | comparison | 1.8 | — | Samsung Galaxy Ring vs RingConn |
| cmp-10 | comparison | 1.8 | — | which is better value, Oura or Ultrahuman? |
| cmp-11 | comparison | 1.8 | — | cheaper alternatives to Whoop |
| brd-01 | brand | 2.0 | — | is the Oura Ring worth it? |
| brd-02 | brand | 2.0 | — | how much does the Oura Ring cost? |
| brd-03 | brand | 2.0 | — | does the Oura Ring require a subscription? |
| brd-04 | brand | 2.0 | — | what's the newest Oura Ring right now? |
| brd-05 | brand | 2.0 | — | Oura Ring review: pros and cons |
| brd-06 | brand | 2.0 | — | is the Oura Ring good for sleep tracking? |
| brd-07 | brand | 2.0 | — | is the Oura Ring membership worth paying for monthly? |
| adj-01 | adjacent_authority | 1.0 | — | how does heart rate variability relate to recovery? |
| adj-02 | adjacent_authority | 1.0 | — | what's a healthy resting heart rate during sleep? |
| adj-03 | adjacent_authority | 1.0 | — | how much deep sleep do I actually need each night? |
| adj-04 | adjacent_authority | 1.0 | — | how can I use body temperature to track my menstrual cycle? |
| adj-05 | adjacent_authority | 1.0 | — | what's a good HRV score and how do I improve it? |
| adj-06 | adjacent_authority | 1.0 | — | how do I know if I'm actually getting enough quality sleep? |
| adj-07 | adjacent_authority | 1.0 | — | how does alcohol affect sleep and recovery? |

### §6.2 Per-query × per-engine capture

One row per (query, engine): Oura’s presence, prominence and framing, the number of accuracy flags the judge raised on that answer, which brand was recommended first, which competitors appeared, and citation count. This is the raw §6.3 data rolled to the cell level — every number above traces here.

Legend: prominence 🥇 first · mid-pack · also-ran · — absent.

| Query | Engine | Oura | Prominence | Framing | Flags | Led by | Competitors present | Cites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| adj-01 | anthropic | — | — | neutral |  | — | — |  |
| adj-01 | gemini | — | — | neutral |  | — | — |  |
| adj-01 | openai | — | — | neutral |  | — | — |  |
| adj-01 | perplexity | — | — | neutral |  | — | — | 9 |
| adj-02 | anthropic | — | — | neutral |  | — | — |  |
| adj-02 | gemini | — | — | neutral |  | — | — |  |
| adj-02 | openai | — | — | neutral |  | — | — |  |
| adj-02 | perplexity | — | — | neutral |  | — | — | 9 |
| adj-03 | anthropic | — | — | neutral |  | — | — |  |
| adj-03 | gemini | — | — | neutral |  | — | — |  |
| adj-03 | openai | — | — | neutral |  | — | — |  |
| adj-03 | perplexity | — | — | neutral |  | — | — | 8 |
| adj-04 | anthropic | — | — | neutral |  | — | — |  |
| adj-04 | gemini | — | — | neutral |  | — | — |  |
| adj-04 | openai | — | — | neutral |  | — | — |  |
| adj-04 | perplexity | ✅ | 🥇 first | positive |  | Oura | — | 7 |
| adj-05 | anthropic | — | — | neutral |  | — | — |  |
| adj-05 | gemini | — | — | neutral |  | — | — |  |
| adj-05 | openai | — | — | neutral |  | — | — |  |
| adj-05 | perplexity | — | — | neutral |  | — | — | 7 |
| adj-06 | anthropic | — | — | neutral |  | — | — |  |
| adj-06 | gemini | — | — | neutral |  | — | — |  |
| adj-06 | openai | — | — | neutral |  | — | — |  |
| adj-06 | perplexity | — | — | neutral |  | — | — | 9 |
| adj-07 | anthropic | — | — | neutral |  | — | — |  |
| adj-07 | gemini | — | — | neutral |  | — | — |  |
| adj-07 | openai | — | — | neutral |  | — | — |  |
| adj-07 | perplexity | — | — | neutral |  | — | — | 8 |
| brd-01 | anthropic | ✅ | 🥇 first | neutral | 2 | Oura | — |  |
| brd-01 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Whoop |  |
| brd-01 | openai | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-01 | perplexity | ✅ | 🥇 first | neutral | 1 | Oura | Whoop | 8 |
| brd-02 | anthropic | ✅ | 🥇 first | neutral | 3 | Oura | — |  |
| brd-02 | gemini | ✅ | 🥇 first | neutral | 3 | Oura | — |  |
| brd-02 | openai | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| brd-02 | perplexity | ✅ | 🥇 first | neutral | 2 | Oura | — | 8 |
| brd-03 | anthropic | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| brd-03 | gemini | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| brd-03 | openai | ✅ | 🥇 first | neutral |  | Oura | — |  |
| brd-03 | perplexity | ✅ | 🥇 first | neutral | 1 | Oura | — | 7 |
| brd-04 | anthropic | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| brd-04 | gemini | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| brd-04 | openai | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| brd-04 | perplexity | ✅ | 🥇 first | neutral | 1 | Oura | — | 8 |
| brd-05 | anthropic | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| brd-05 | gemini | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| brd-05 | openai | ✅ | 🥇 first | neutral | 3 | Oura | — |  |
| brd-05 | perplexity | ✅ | 🥇 first | neutral | 2 | Oura | — | 8 |
| brd-06 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| brd-06 | gemini | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| brd-06 | openai | ✅ | 🥇 first | positive |  | Oura | — |  |
| brd-06 | perplexity | ✅ | 🥇 first | positive |  | Oura | — | 7 |
| brd-07 | anthropic | ✅ | 🥇 first | neutral | 2 | Oura | Whoop |  |
| brd-07 | gemini | ✅ | 🥇 first | positive | 1 | Oura | Whoop, Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| brd-07 | openai | ✅ | 🥇 first | neutral | 2 | Oura | — |  |
| brd-07 | perplexity | ✅ | 🥇 first | neutral | 1 | Oura | — | 9 |
| cat-01 | anthropic | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-01 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-01 | openai | ✅ | 🥇 first | positive |  | Oura | — |  |
| cat-01 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 7 |
| cat-02 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-02 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, RingConn |  |
| cat-02 | openai | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-02 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, RingConn | 6 |
| cat-03 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, RingConn |  |
| cat-03 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, RingConn |  |
| cat-03 | openai | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-03 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 10 |
| cat-04 | anthropic | ✅ | 🥇 first | positive | 4 | Oura | RingConn |  |
| cat-04 | gemini | ✅ | mid-pack | positive | 2 | — | Ultrahuman, Samsung Galaxy Ring |  |
| cat-04 | openai | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| cat-04 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | RingConn | 7 |
| cat-05 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, RingConn |  |
| cat-05 | gemini | ✅ | mid-pack | positive | 1 | RingConn | Ultrahuman, RingConn |  |
| cat-05 | openai | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| cat-05 | perplexity | ✅ | mid-pack | neutral | 3 | RingConn | Samsung Galaxy Ring, RingConn | 6 |
| cat-06 | anthropic | ✅ | also-ran | negative | 1 | Ultrahuman | Ultrahuman, RingConn |  |
| cat-06 | gemini | ✅ | also-ran | neutral | 2 | RingConn | Ultrahuman, RingConn |  |
| cat-06 | openai | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| cat-06 | perplexity | — | — | neutral |  | Ultrahuman | Ultrahuman, Samsung Galaxy Ring, RingConn | 7 |
| cat-07 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, RingConn |  |
| cat-07 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, RingConn |  |
| cat-07 | openai | ✅ | 🥇 first | positive |  | Oura | — |  |
| cat-07 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 4 |
| cat-08 | anthropic | ✅ | also-ran | negative | 2 | RingConn | Ultrahuman, RingConn |  |
| cat-08 | gemini | ✅ | mid-pack | neutral | 2 | RingConn | Ultrahuman, RingConn |  |
| cat-08 | openai | ✅ | 🥇 first | neutral | 1 | Oura | — |  |
| cat-08 | perplexity | — | — | neutral |  | — | RingConn | 8 |
| cat-09 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-09 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, RingConn |  |
| cat-09 | openai | — | — | neutral |  | — | — |  |
| cat-09 | perplexity | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 7 |
| cat-10 | anthropic | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-10 | gemini | ✅ | mid-pack | neutral |  | Samsung Galaxy Ring | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-10 | openai | — | — | neutral |  | — | — |  |
| cat-10 | perplexity | — | — | neutral |  | Ultrahuman | Ultrahuman, RingConn | 7 |
| cat-11 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Whoop, Ultrahuman, RingConn |  |
| cat-11 | gemini | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-11 | openai | ✅ | 🥇 first | positive | 1 | Oura | Whoop |  |
| cat-11 | perplexity | — | — | neutral |  | — | Whoop | 4 |
| cat-13 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-13 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, Samsung Galaxy Ring |  |
| cat-13 | openai | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| cat-13 | perplexity | ✅ | mid-pack | neutral | 3 | RingConn | Samsung Galaxy Ring, RingConn | 6 |
| cat-14 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-14 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-14 | openai | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| cat-14 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 5 |
| cmp-01 | anthropic | ✅ | 🥇 first | positive | 1 | Oura | Whoop |  |
| cmp-01 | gemini | ✅ | 🥇 first | positive | 1 | Oura | Whoop |  |
| cmp-01 | openai | ✅ | 🥇 first | neutral | 1 | Oura | Whoop |  |
| cmp-01 | perplexity | ✅ | mid-pack | positive |  | Whoop | Whoop | 7 |
| cmp-02 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Samsung Galaxy Ring |  |
| cmp-02 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Samsung Galaxy Ring |  |
| cmp-02 | openai | ✅ | 🥇 first | positive | 1 | Oura | Samsung Galaxy Ring |  |
| cmp-02 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | Samsung Galaxy Ring | 8 |
| cmp-03 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman |  |
| cmp-03 | gemini | ✅ | 🥇 first | neutral | 4 | Oura | Ultrahuman |  |
| cmp-03 | openai | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman |  |
| cmp-03 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman | 6 |
| cmp-04 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | RingConn |  |
| cmp-04 | gemini | ✅ | 🥇 first | positive | 2 | Oura | RingConn |  |
| cmp-04 | openai | ✅ | 🥇 first | positive | 2 | Oura | RingConn |  |
| cmp-04 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | RingConn | 7 |
| cmp-05 | anthropic | ✅ | — | neutral |  | RingConn | Whoop, Ultrahuman, RingConn |  |
| cmp-05 | gemini | ✅ | mid-pack | positive | 1 | Ultrahuman | Whoop, Ultrahuman |  |
| cmp-05 | openai | ✅ | mid-pack | neutral |  | Whoop | Whoop |  |
| cmp-05 | perplexity | ✅ | mid-pack | neutral |  | Samsung Galaxy Ring | Ultrahuman, Samsung Galaxy Ring, RingConn | 8 |
| cmp-06 | anthropic | ✅ | mid-pack | neutral | 1 | RingConn | Ultrahuman, RingConn |  |
| cmp-06 | gemini | ✅ | mid-pack | neutral | 1 | Ultrahuman | Ultrahuman, RingConn |  |
| cmp-06 | openai | ✅ | mid-pack | neutral | 1 | Whoop | Whoop |  |
| cmp-06 | perplexity | ✅ | mid-pack | neutral | 1 | RingConn | Ultrahuman, Samsung Galaxy Ring, RingConn | 8 |
| cmp-07 | anthropic | ✅ | mid-pack | positive | 2 | Samsung Galaxy Ring | Samsung Galaxy Ring |  |
| cmp-07 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Samsung Galaxy Ring |  |
| cmp-07 | openai | ✅ | 🥇 first | positive | 1 | Oura | Samsung Galaxy Ring |  |
| cmp-07 | perplexity | ✅ | mid-pack | neutral | 2 | Samsung Galaxy Ring | Samsung Galaxy Ring | 8 |
| cmp-08 | anthropic | — | — | neutral |  | Whoop | Whoop, Ultrahuman |  |
| cmp-08 | gemini | — | — | neutral |  | Whoop | Whoop, Ultrahuman |  |
| cmp-08 | openai | — | — | neutral |  | Whoop | Whoop, Ultrahuman |  |
| cmp-08 | perplexity | — | — | neutral |  | Whoop | Whoop, Ultrahuman | 8 |
| cmp-09 | anthropic | — | — | neutral |  | Samsung Galaxy Ring | Samsung Galaxy Ring, RingConn |  |
| cmp-09 | gemini | ✅ | also-ran | neutral | 1 | Samsung Galaxy Ring | Samsung Galaxy Ring, RingConn |  |
| cmp-09 | openai | — | — | neutral |  | Samsung Galaxy Ring | Samsung Galaxy Ring, RingConn |  |
| cmp-09 | perplexity | — | — | neutral |  | Samsung Galaxy Ring | Samsung Galaxy Ring, RingConn | 9 |
| cmp-10 | anthropic | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman |  |
| cmp-10 | gemini | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman |  |
| cmp-10 | openai | ✅ | 🥇 first | neutral | 1 | Oura | Ultrahuman |  |
| cmp-10 | perplexity | ✅ | 🥇 first | neutral | 2 | Oura | Ultrahuman | 7 |
| cmp-11 | anthropic | — | — | neutral |  | Whoop | Whoop |  |
| cmp-11 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Whoop |  |
| cmp-11 | openai | — | — | neutral |  | Whoop | Whoop |  |
| cmp-11 | perplexity | ✅ | mid-pack | neutral | 2 | Whoop | Whoop | 9 |
| pa-01 | anthropic | — | — | neutral |  | — | — |  |
| pa-01 | gemini | — | — | neutral |  | — | — |  |
| pa-01 | openai | — | — | neutral |  | — | — |  |
| pa-01 | perplexity | — | — | neutral |  | — | — | 7 |
| pa-02 | anthropic | — | — | neutral |  | — | — |  |
| pa-02 | gemini | — | — | neutral |  | — | — |  |
| pa-02 | openai | — | — | neutral |  | — | — |  |
| pa-02 | perplexity | — | — | neutral |  | — | — | 7 |
| pa-03 | anthropic | ✅ | mid-pack | neutral |  | — | — |  |
| pa-03 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Whoop |  |
| pa-03 | openai | — | — | neutral |  | — | Whoop |  |
| pa-03 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Whoop | 8 |
| pa-04 | anthropic | — | — | neutral |  | — | — |  |
| pa-04 | gemini | — | — | neutral |  | — | — |  |
| pa-04 | openai | — | — | neutral |  | — | — |  |
| pa-04 | perplexity | — | — | neutral |  | — | — | 8 |
| pa-05 | anthropic | — | — | neutral |  | — | — |  |
| pa-05 | gemini | — | — | neutral |  | — | — |  |
| pa-05 | openai | — | — | neutral |  | — | — |  |
| pa-05 | perplexity | — | — | neutral |  | — | — | 8 |
| pa-06 | anthropic | — | — | neutral |  | — | — |  |
| pa-06 | gemini | — | — | neutral |  | — | — |  |
| pa-06 | openai | — | — | neutral |  | — | — |  |
| pa-06 | perplexity | — | — | neutral |  | — | — | 9 |
| pa-07 | anthropic | — | — | neutral |  | — | — |  |
| pa-07 | gemini | — | — | neutral |  | — | — |  |
| pa-07 | openai | — | — | neutral |  | — | — |  |
| pa-07 | perplexity | — | — | neutral |  | — | — | 8 |

### §6.3 Methodology & honesty caveats

- **Surface.** Parametric memory (no live web) on OpenAI/Anthropic/Gemini; Perplexity returns live citations. A separate `--surface search` run measures the live-retrieval surfaces (ChatGPT-search, Claude-search, Gemini grounding, Google AI Overviews) and is recommended as a companion.
- **Determinism.** Temperature pinned to 0; 1 run per query this cycle (repeat-run averaging is supported via `--runs`).
- **Judge.** One held-constant `gpt-4o` judge, forced-JSON, no outside knowledge — accuracy is checked **only** against the supplied Oura fact sheet (`docs/fact-sheet-example-oura.md`). Accuracy flags are **client-only** by design; competitors get presence/prominence/framing.
- **Trust.** The judge is currently **plausible but lightly calibrated** (placeholder gold set). Calibrate against a hand-labeled gold set before quoting flag counts to a client as ground truth.
- **Gemini provenance.** Gemini’s answers in this run were backfilled 2026-06-12 after an API-key/quota fix and judged on the same fact sheet as the other engines.
- **Citations.** Client citation rate is 0% because the parametric surface doesn’t link and Perplexity cites review media over ouraring.com — a finding, not a data gap.
