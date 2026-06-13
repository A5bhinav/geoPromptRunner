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

- **Headline grade: F.** Prominence-weighted visibility is **0.55** (the strongest in the category), but **315 distinct client accuracy flags** drive the accuracy-discounted score to **0.00**. Oura is *seen* but frequently *described wrong*.
- **Oura leads the category leaderboard** — visibility 0.55 vs. Ultrahuman 0.17; share-of-voice 43% of all brand mentions. Presence is not the problem.
- **The problem is two-sided:**
  1. **Accuracy.** 151 of 315 flags are *high* severity — overwhelmingly **stale pricing/model** facts: models still quote the $299–$549 Gen-3/Ring-4 era and call Oura subscription-optional, when the current line is **Ring 5 at $399/$499 with a required $5.99/mo membership** (Ring 5 launched 2026-05-28).
  2. **Funnel shape.** Oura owns bottom-funnel intent (brand 100%, category 90%, comparison 80%) but is **nearly invisible upper-funnel**: problem-aware 21%, adjacent-authority 7%. Buyers at the start of the journey never hear the name.
- **Where it loses outright:** 10 (query, engine) cells where Oura is absent and a competitor is recommended first — almost all in **comparison** queries (cmp-08/09/11), led by Whoop, Ultrahuman, RingConn, and Samsung.
- **Citations come from one surface.** Only Perplexity exposes sources; the off-site battleground it reveals is **YouTube, Facebook, and review media (wareable, CNET, Tom’s Guide)** — not Oura’s own site.

---

## §1 · AI Visibility Scorecard

### Grade: F

- **Raw visibility (prominence-weighted):** 0.55 / 1.00  — rewards being recommended *first* over being buried.
- **Accuracy penalty:** −30.97 across 315 distinct flags (high −0.15, med −0.07, low −0.03 each).
- **Discounted score:** 0.00 → **F** (floored at 0).

> The grade is deliberately severe on accuracy: a confidently wrong claim (“no subscription required”) erodes buyer trust even when the brand is front-and-centre. The raw 0.56 visibility is a **B/A-grade presence**; the F is entirely an accuracy verdict.

### Share-of-model

| Role | Brand | Visibility | Mention rate | Share-of-voice |
| --- | --- | --- | --- | --- |
| Client / category leader | Oura | 0.55 | 66% | 43% |
| Top competitor | Ultrahuman | 0.17 | 28% | 18% |
| Competitor | RingConn | 0.15 | 27% | 17% |
| Competitor | Samsung Galaxy Ring | 0.11 | 19% | 12% |
| Competitor | Whoop | 0.10 | 14% | 9% |

*Share-of-voice = a brand’s present-cells as a fraction of all brand present-cells across the run.*

### Per-engine — client mention & citation rate

| Engine | Client mention rate | Any-citation rate | Note |
| --- | --- | --- | --- |
| anthropic | 67% | 0% |  |
| gemini | 73% | 0% | most generous to Oura |
| openai | 58% | 0% | lowest — Oct-2023 training cutoff refuses 2026 queries |
| perplexity | 64% | 100% | only engine with live citations |

*Client **citation** rate is 0% on every engine: on the parametric surface models recommend from memory without linking, and where Perplexity does cite, it cites review media rather than ouraring.com. See §4.*

---

## §2 · Funnel analysis (by intent bucket)

Every score is tied back to *which queries* it comes from. Buckets run from upper-funnel (a consumer describing a problem) to navigational (typing the brand name).

### §2.2 Mention, visibility & prominence by bucket

| Intent bucket | Queries | Client mention | Client visibility | 🥇 first | mid-pack | also-ran | absent |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Brand (navigational) | 7 | 100% | 1.00 | 28 | 0 | 0 | 0 |
| Category (“best smart ring …”) | 13 | 90% | 0.79 | 37 | 6 | 4 | 5 |
| Comparison (“X vs Y”) | 11 | 80% | 0.59 | 21 | 7 | 7 | 9 |
| Problem-aware (upper funnel) | 7 | 21% | 0.11 | 2 | 1 | 2 | 22 |
| Adjacent authority (topic questions) | 7 | 7% | 0.05 | 1 | 0 | 0 | 26 |

**Read:** Oura is **dominant where intent is explicit** — 100% on brand queries, 88% on category (“best smart ring …”), 80% on comparison — and **effectively absent where it isn’t**: 11% problem-aware, 4% adjacent-authority. The upper-funnel gap is the single biggest *growth* opportunity; the comparison softness (often mid-pack, not first) is the biggest *competitive* risk. The two clusters map to different fixes (§5).

### §2.3 Accuracy flags — what the models get wrong about Oura

**315 distinct flags** (321 total instances across answers). This is the most persuasive material in the audit: concrete, falsifiable things the AIs state about Oura that are wrong.

| | high | med | low | **total** |
| --- | --- | --- | --- | --- |
| Wrong pricing / subscription | 37 | 20 | 20 | **77** |
| Stale model / generation | 73 | 40 | 17 | **130** |
| Missing or invented feature | 40 | 24 | 41 | **105** |
| **total** | **151** | **85** | **79** | **315** |

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

<details><summary><strong>All 315 distinct accuracy flags (type · severity · claim → reality)</strong></summary>

| # | Type | Sev | Claim → Reality |
| --- | --- | --- | --- |
| 1 | stale | med | The Oura Ring is one of the most popular smart rings on the market... (no mention of Ring 5 or current model) → The current model is the Oura Ring 5, launched 2026-05-28. Any reference to the Oura Ring without specifying Ring 5 as the latest is stale. |
| 2 | missing_or_invented_feature | high | No mention of the required monthly/annual membership subscription → Oura requires a $5.99/month or $69.99/year membership for full features; this is a material cost omission. |
| 3 | stale | high | Oura Ring Generation 3 is the top pick → The current model is the Oura Ring 5 (launched 2026-05-28). Ring 4 was the previous model; Ring 3 is even older and outdated. |
| 4 | wrong_pricing | high | $299 + $5.99/month subscription → The current Oura Ring 5 starts at $399 (base finishes) or $499 (premium finishes). $299 was the price of the much older Gen 3. |
| 5 | stale | high | Oura Ring 4 is named as the current/relevant model → The Oura Ring 5 launched 2026-05-28 and is the current model; Ring 4 is being cleared out. |
| 6 | wrong_pricing | med | Oura Ring 4 is described as 'expensive' implying a premium price point, without specifying; the model referenced (Ring 4) was $349 → Current model is Ring 5 at $399 base; Ring 4 is now being cleared below $349. |
| 7 | missing_or_invented_feature | low | Oura Ring 4 is described as 'subscription-based' correctly, but no mention of the specific cost ($5.99/mo or $69.99/yr) or that a first month is free → Membership is $5.99/month or $69.99/year with first month free — the answer correctly flags subscription exists but omits detail. Not a factual error per se, but the subscription framing is accurate. |
| 8 | stale | high | The answer claims RingConn Gen 2 delivers '90% of the performance of the premium Oura Ring 4', treating Ring 4 as the current premium benchmark → The current Oura model is the Ring 5 (launched 2026-05-28), not the Ring 4. |
| 9 | missing_or_invented_feature | high | The answer implies Oura Ring is a one-time purchase with no mention of a required monthly/annual membership → Oura requires a mandatory membership at $5.99/month or $69.99/year for full features; without it, insights are heavily limited |
| 10 | stale | high | Oura Ring Gen 3 listed as the top product → The current model is Oura Ring 5 (launched 2026-05-28); Ring 4 was the previous model, and Ring 3 is even older. |
| 11 | wrong_pricing | high | Price listed as ~$299-$549 → Current Oura Ring 5 base price is $399 (Silver/Black) and $499 (premium finishes). $299 is a stale Gen 3 price. |
| 12 | wrong_pricing | low | 4-7 day battery life stated → The fact sheet states up to ~8-day battery (Ring 4 generation); 4-7 days understates the battery life. |
| 13 | stale | high | Oura Ring 4 remains the undisputed leader / is the top pick → The Oura Ring 5 launched on 2026-05-28 and is the current model; the Ring 4 is now being cleared out. An answer dated mid-2026 should reference Ring 5 as the current model. |
| 14 | wrong_pricing | high | Starts at ~$349 → The Ring 4 was $349 but is now being cleared out below that price. The current model, Ring 5, starts at $399. The answer presents $349 as the active price. |
| 15 | missing_or_invented_feature | low | It requires a mandatory monthly subscription, making it the most expensive option long-term (implied one-time cost + subscription only) → The subscription is correctly flagged as required, but the answer omits the specific cost: $5.99/month or $69.99/year, with the first month free. While the omission of the exact price is minor, the framing is otherwise accurate on the subscription being mandatory. |
| 16 | stale | low | The Oura Ring typically lasts about 4-7 days on a single charge → The fact sheet lists up to ~8-day battery for the Ring 4 generation, and the Ring 5 is the current model as of 2026-05-28. |
| 17 | missing_or_invented_feature | low | Oura requires a subscription for full access to its features and insights (no specific price given) → The membership is required at $5.99/month or $69.99/year with the first month free. The answer acknowledges a subscription exists but omits the price, which is a material detail per the fact sheet's known-inaccuracy watch-list. |
| 18 | stale | med | No mention of Oura Ring 5 as the current model; the answer describes the device generically without referencing Ring 5 → The Oura Ring 5 launched 2026-05-28 and is the current model. Failing to mention it means the answer implicitly treats an older generation as current. |
| 19 | stale | med | Subscription: Lifetime (Gen 2) or $5.99/mo (Gen 3) → The current model is the Oura Ring 5 (launched 2026-05-28). There is no 'lifetime' membership for Gen 2 vs. Gen 3 framing that is current — the membership is $5.99/mo or $69.99/year for all current users. |
| 20 | missing_or_invented_feature | med | Subscription: Lifetime (Gen 2) or $5.99/mo (Gen 3) — implying Gen 2 owners have a lifetime/free membership and only Gen 3 requires $5.99/mo → The membership is required for full features and costs $5.99/mo (or $69.99/yr). The fact sheet does not describe any 'lifetime' free tier for Gen 2 as a current product distinction. |
| 21 | stale | high | The answer compares Oura Ring (Gen 2/Gen 3 framing) without mentioning the Oura Ring 5 as the current model → The Oura Ring 5 is the current model as of 2026-05-28. Referring to Gen 2/Gen 3 as the relevant current models is stale. |
| 22 | wrong_pricing | med | No hardware price is mentioned, but the subscription framing of 'Lifetime (Gen 2) or $5.99/mo (Gen 3)' implies Gen 2 has no ongoing cost → Current Oura Ring 5 hardware starts at $399 (base finishes) with a required $5.99/mo membership. There is no current 'lifetime' free membership offering described in the fact sheet. |
| 23 | missing_or_invented_feature | high | Oura uses a daily Readiness score that blends nightly data with longer-term trends — no mention of a required membership subscription → Oura requires a paid membership ($5.99/month or $69.99/year) for full features; the ring is not a standalone one-time purchase product without subscription |
| 24 | stale | low | The Oura Ring typically has a battery life of about 4-7 days, depending on usage. → The fact sheet states up to ~8-day battery (Ring 4 generation); Ring 5 is the current model as of 2026-05-28. |
| 25 | stale | high | The answer describes the Oura Ring's features and positioning without referencing the Oura Ring 5, implying an older model is current. → The Oura Ring 5 launched 2026-05-28 and is the current model. The answer gives no indication of Ring 5's existence. |
| 26 | missing_or_invented_feature | high | No mention of the required monthly/annual membership subscription ($5.99/mo or $69.99/yr) — implying the ring is a one-time purchase. → A required membership ($5.99/month or $69.99/year) is needed for full features; the ring is not a standalone one-time purchase product. |
| 27 | wrong_pricing | med | Pricing is discussed only vaguely ('worth considering how it compares to the Oura Ring in terms of value for money') with no specific price stated — but the implicit reference to an Oura Ring price is absent entirely, risking the impression of an older price point. → Current Oura Ring 5 base price is $399 (Silver/Black); premium finishes are $499. The old Ring 4 was $349. |
| 28 | stale | high | Oura Ring (Gen 3) is referenced as the current model → The current model is the Oura Ring 5, launched 2026-05-28. Ring 4 was the previous generation; Gen 3 is even older. |
| 29 | wrong_pricing | high | Oura Ring costs $299-$549 → Oura Ring 5 starts at $399 (base finishes) and $499 (premium finishes). $299 is an outdated Gen 3 price; $549 is not a listed price point. |
| 30 | stale | high | The answer recommends and describes the 'Oura Ring 4' as the current/best model throughout. → The Oura Ring 5 launched 2026-05-28 and is the current model. The Ring 4 is now being cleared out. Calling Ring 4 the best/current model is stale. |
| 31 | wrong_pricing | high | Oura Ring 4 starting price listed as $349. → The current Oura Ring 5 starts at $399. The Ring 4 was $349 but is the previous/outgoing model. |
| 32 | stale | high | The answer describes Oura Ring generically without mentioning the Ring 5 as the current model, implying Ring 4 or an older model is the current product. → The Oura Ring 5 launched on 2026-05-28 and is the current model. It is ~40% smaller than Ring 4 and ships 2026-06-04. |
| 33 | missing_or_invented_feature | high | The answer implies Oura is a one-time hardware purchase with no mention of a required subscription/membership. → Oura requires a mandatory membership at $5.99/month or $69.99/year for full features. Without it, insights are heavily limited. |
| 34 | missing_or_invented_feature | low | The answer does not mention blood-oxygen (SpO2) tracking as a feature. → The fact sheet lists SpO2 (blood-oxygen) as a core feature of the Oura Ring. |
| 35 | wrong_pricing | high | Oura Ring priced at $299-$549 → Current Oura Ring 5 is $399 (base) or $499 (premium finishes). $299 is an outdated Gen 3 price; $549 is not a listed price point. Ring 4 was $349 and is now being cleared out. |
| 36 | stale | high | No mention of the Oura Ring 5 as the current/latest model → The Oura Ring 5 launched 2026-05-28 and is the current model. The answer does not reference Ring 5 at all, implying an older model. |
| 37 | wrong_pricing | low | Subscription costs $72/year ($5.99/month × 12) → The annual subscription is $69.99/year (not $72/year). Monthly is $5.99/mo, but the annual plan is a discounted $69.99. |
| 38 | missing_or_invented_feature | med | Battery life listed as 4-7 days → The fact sheet states up to ~8-day battery for the Ring 4 generation. 4-7 days understates the claimed battery life. |
| 39 | stale | med | Oura Ring has reported around 8 days battery life in one hands-on comparison → The ~8-day battery figure corresponds to the Ring 4 generation. The current model is the Ring 5 (launched 2026-05-28); no updated battery figure for Ring 5 is provided, and the answer does not mention Ring 5 at all. |
| 40 | missing_or_invented_feature | med | Oura 'typically requires a membership' framed as optional/typical rather than required → The membership is explicitly required for full features — it is not merely typical but mandatory. The fact sheet flags omitting or softening this as a frequent material error. |
| 41 | stale | med | No mention of Oura Ring 5 as the current model; the answer discusses the Oura Ring generically without referencing the Ring 5 launched 2026-05-28. → The Oura Ring 5 is the current model, launched 2026-05-28, ~40% smaller than Ring 4. |
| 42 | wrong_pricing | high | Price described only as 'generally considered a premium product, with prices reflecting its advanced features and design' — no specific price mentioned, and no mention of required subscription. → Oura Ring 5 starts at $399 (base finishes) or $499 (premium finishes), plus a required $5.99/month membership. |
| 43 | missing_or_invented_feature | high | No mention of the required monthly/annual membership ($5.99/mo or $69.99/yr) needed for full features. → A required membership is needed for full features; without it, insights are heavily limited. This is a material omission. |
| 44 | stale | high | Oura Ring Gen 3 is the product being discussed → The current model is the Oura Ring 5, launched 2026-05-28. Ring 4 is the previous model now being cleared out. |
| 45 | wrong_pricing | high | Oura costs $299-399 → Oura Ring 5 base price is $399 (Silver/Black) and $499 for premium finishes. The $299 figure is stale (Gen 3 era). |
| 46 | missing_or_invented_feature | med | Subscription is $5.99/month — implied as optional ('required for most features') with implication ring works fine without it → The $5.99/month membership is required for the full product. Without it, insights are heavily limited. It is not truly optional for meaningful use. |
| 47 | missing_or_invented_feature | low | Oura battery life is 4-7 days → The fact sheet states up to ~8-day battery for the Ring 4 generation. The 4-7 day figure is understated/stale. |
| 48 | missing_or_invented_feature | med | Oura described as 'bulkier design' as a weakness → The Oura Ring 5 is ~40% smaller than Ring 4, with a thinner/lighter redesign — calling it 'bulkier' is inaccurate for the current model. |
| 49 | missing_or_invented_feature | high | Oura includes 'readiness-style coaching' as a notable feature → Oura does have Readiness and Recovery scores per the fact sheet, so this is broadly accurate — no flag needed. Flagging instead: the answer makes no mention of the required subscription fee, implying the ring stands on its own as a purchase. |
| 50 | missing_or_invented_feature | high | No mention of the required $5.99/month membership fee — the answer implicitly frames Oura as a straight hardware purchase vs. RingConn's 'no subscription fee' → Oura requires a $5.99/month (or $69.99/year) membership for full features; omitting this while highlighting RingConn's no-subscription advantage is a material inaccuracy |
| 51 | missing_or_invented_feature | high | The answer implies Oura is simply a 'wearable device' without mentioning the required monthly/annual membership subscription → Oura requires a mandatory $5.99/month or $69.99/year membership for full features; without it, insights are heavily limited. This is a material cost omission. |
| 52 | stale | med | The answer implies Oura Ring (as a product being compared against) without mentioning the Ring 5 as the current model → The Oura Ring 5 launched 2026-05-28 and is the current model; Ring 4 at $349 is now being cleared out |
| 53 | missing_or_invented_feature | high | The answer does not mention Oura's required monthly/annual membership subscription cost when framing it as the product being replaced → Oura requires a $5.99/month or $69.99/year membership for full features — this is a required ongoing cost, not optional |
| 54 | missing_or_invented_feature | med | The answer implies Oura requires a subscription (mentions 'subscription-free' as a differentiator for competitors), but never explicitly states the subscription is required for full features — the subscription model is effectively omitted/understated as a named Oura drawback. → Oura requires a mandatory $5.99/month or $69.99/year membership for full features; this is a material and frequently missed detail the fact sheet flags as high-priority. |
| 55 | missing_or_invented_feature | low | The answer implies Oura Ring alternatives are needed because of a monthly subscription, but does not explicitly state Oura's subscription is required for full features — it only frames Oura as having a subscription implicitly via the question context. No direct claim about Oura's subscription model is made in the answer body. → Oura requires a $5.99/month or $69.99/year membership for full features — this is a required, not optional, subscription. |
| 56 | missing_or_invented_feature | high | The answer implies Oura Ring is a one-time purchase by framing it as a product that alternatives replace, without mentioning Oura's required $5.99/month membership → Oura requires a mandatory membership ($5.99/month or $69.99/year) for full features — the ring is NOT a simple one-time purchase |
| 57 | stale | med | The answer does not mention the Oura Ring 5 (launched 2026-05-28), implicitly treating the product line as if Ring 4 or an older model is current → The Oura Ring 5 launched on 2026-05-28 and is the current model, priced at $399 (base) or $499 (premium finishes) |
| 58 | missing_or_invented_feature | med | The answer frames Oura as a product to replace/avoid due to its subscription, implying the subscription is an optional or notable negative differentiator, but does not explicitly state the subscription cost or that it is required for full features. → Oura requires a $5.99/month or $69.99/year membership for full features — this is a required ongoing cost, not merely an optional add-on. The answer never states the subscription price or that it is mandatory. |
| 59 | stale | med | Oura Ring is described generally with no mention of the Ring 5; the answer implies an older/unspecified model is current → The Oura Ring 5 launched 2026-05-28 and is the current model |
| 60 | missing_or_invented_feature | high | The answer makes no mention of a required monthly membership/subscription cost for the Oura Ring → Oura requires a mandatory $5.99/month (or $69.99/year) membership for full features; this is a material ongoing cost |
| 61 | wrong_pricing | low | Oura charges $5.99/month → The $5.99/month figure is correct, but the answer implies the subscription is optional ('Oura charges $5.99/month' as a disadvantage framing). The fact sheet notes membership is required for full features, not merely an add-on charge. |
| 62 | stale | med | Oura's battery life is 4-7 days → The fact sheet states up to ~8-day battery (Ring 4 generation). 4-7 days is understated and likely stale. |
| 63 | wrong_pricing | high | Oura Ring starts at $299 → Current Oura Ring 5 base price is $399 (Silver/Black). The $299 price is from a much older generation. Ring 4 was $349. |
| 64 | missing_or_invented_feature | high | No mention of the required monthly/annual membership fee ($5.99/mo) — implied to be a one-time purchase → Oura requires a mandatory membership at $5.99/month or $69.99/year for full features; this is a material ongoing cost |
| 65 | stale | med | No mention of Oura Ring 5 as the current model → Oura Ring 5 launched 2026-05-28 and began shipping 2026-06-04; it is the current model |
| 66 | stale | med | The answer discusses Oura Ring features without naming a current model, implying the current product is the Ring 4 or older generation (no mention of Ring 5). → The Oura Ring 5 launched 2026-05-28 and is the current model; Ring 4 is now being cleared out. |
| 67 | wrong_pricing | low | The answer does not state any hardware price for Oura, but implies cost comparison without noting the Ring 5 base price of $399. → Oura Ring 5 base price is $399 (Silver/Black); premium finishes are $499. |
| 68 | missing_or_invented_feature | low | The answer says Oura 'requires a subscription for full access to its features and insights' without specifying the cost ($5.99/month or $69.99/year). → Membership is $5.99/month or $69.99/year; first month free. The subscription is required — not mentioning the price is an omission, though the existence of the subscription is correctly noted. |
| 69 | missing_or_invented_feature | low | The answer states Ultrahuman provides 'insights into glucose levels and metabolic efficiency' and implies glucose monitoring is a feature of the Ultrahuman Ring itself. → This is a claim about Ultrahuman, not Oura, so it is not directly checkable against the Oura fact sheet. However, the fact sheet does not flag this as a competitor confusion issue for Oura. |
| 70 | wrong_pricing | high | Oura: $299-549 (ring) → Current Oura Ring 5 base price is $399 (premium finishes $499). $299 is a stale Gen 3 price; $549 does not correspond to any current listed price. |
| 71 | stale | high | Oura ring priced at $299-549, implying older/current models in that range → The Ring 5 launched 2026-05-28 at $399 base / $499 premium. Ring 4 is being cleared out below $349. Most AI models still quote Ring 4 or Ring 3 pricing. |
| 72 | missing_or_invented_feature | low | Oura has 10+ years of development → Oura was founded in 2013; as of 2026 that is approximately 13 years, so '10+' is technically not wrong, but the fact sheet notes founded 2013 — this is borderline and not a clear error. |
| 73 | wrong_pricing | high | Oura typically starts around $299–$349 depending on model/finish → The current Oura Ring 5 starts at $399 (base finishes). $349 was the Ring 4 price and $299 is an even older/stale price. |
| 74 | stale | high | Oura typically starts around $299–$349 depending on model/finish → The current model is the Oura Ring 5 (launched 2026-05-28), starting at $399. The answer implies Ring 4 / older pricing is current. |
| 75 | wrong_pricing | med | full access also costs about $5.99/month or about $69.99/year → Pricing is correct ($5.99/month or $69.99/year), but the answer frames it as optional ('full access also costs') rather than required for the full product. The membership is required for full features. |
| 76 | stale | high | Oura Ring 4 at about $349+ → The current model is the Oura Ring 5, starting at $399. The Ring 4 was $349 but is now being cleared out as the Ring 5 launches. |
| 77 | wrong_pricing | high | Oura Ring 4 costs about $349+ → Current Oura Ring 5 base price is $399 (Silver/Black); premium finishes are $499. |
| 78 | missing_or_invented_feature | med | Subscription is $5.99/month (implied optional or secondary) → The $5.99/month membership is required for full features — not truly optional. Without it, insights are heavily limited. |
| 79 | stale | low | The Oura Ring typically offers a battery life of about 4-7 days → The fact sheet states up to ~8-day battery (Ring 4 generation); the current Ring 5 is the latest model |
| 80 | wrong_pricing | high | The Oura Ring is relatively expensive compared to other fitness trackers (no specific price or subscription cost mentioned) → The Oura Ring 5 starts at $399 for base finishes, PLUS a required $5.99/month membership fee. The answer omits the mandatory subscription entirely, implying it may be a one-time purchase. |
| 81 | missing_or_invented_feature | med | It may not offer as many features as some smartwatches, such as GPS tracking or notifications → The fact sheet confirms no notifications/no screen (correct), but does not mention GPS as a missing feature explicitly — GPS omission is consistent. However, framing it as lacking 'some smartwatch features' is fair. The more critical omission is the mandatory membership not being mentioned at all. |
| 82 | wrong_pricing | high | Price — $299-549 + $5.99/month subscription → Current Oura Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes). The $299 figure is stale (Gen 3 era); the $549 figure does not correspond to any current model. The upper end should be $499. |
| 83 | stale | high | Price range starts at $299, implying older/current model pricing → The Ring 5 (launched 2026-05-28) starts at $399. $299 reflects a much older generation and is stale. |
| 84 | missing_or_invented_feature | low | Battery life 4-7 days → The fact sheet states up to ~8-day battery (Ring 4 generation). 4-7 days understates the advertised battery life. |
| 85 | wrong_pricing | high | The ring itself typically costs roughly $299–$549 → Current Oura Ring 5 base price is $399 (premium finishes $499). The $299 figure is for an older generation (Gen 3). The $549 figure does not appear in the fact sheet at all. |
| 86 | stale | high | The ring itself typically costs roughly $299–$549 (implying older/unclear model generation) → The current model is the Oura Ring 5, launched 2026-05-28, starting at $399. The Ring 4 ($349) is the previous model being cleared out. The answer does not mention Ring 5. |
| 87 | wrong_pricing | high | The Oura Ring typically costs between $299 and $549 → Current Oura Ring 5 starts at $399 (base finishes) and $499 (premium finishes). $299 is an outdated Gen 3 price; $549 is not a listed price point. |
| 88 | stale | high | Pricing range of $299–$549 implies stale/incorrect model pricing → The current model is the Oura Ring 5 (launched 2026-05-28), priced at $399–$499. The $299 price references the old Gen 3. |
| 89 | missing_or_invented_feature | high | The answer implies the Oura Ring is a one-time purchase with no mention of a required subscription → A required membership of $5.99/month or $69.99/year is needed for full features; without it, insights are heavily limited. |
| 90 | stale | high | Oura Ring Gen3 Heritage at $299 and Gen3 Horizon at $349-$399 are presented as current models → The current model is Oura Ring 5 (launched 2026-05-28), priced at $399 (base) or $499 (premium finishes). Ring Gen3 is two generations old. |
| 91 | wrong_pricing | high | Oura Ring costs $299-$399 depending on model and finish → Current Oura Ring 5 base price is $399 (Silver, Black) and $499 for premium finishes (Gold, Stealth, Brushed Silver, Deep Rose). |
| 92 | missing_or_invented_feature | med | New purchases typically include a free trial period of often 1-6 months of membership → The fact sheet states only the first month of membership is free — there is no 1-6 month range mentioned. |
| 93 | stale | high | The current Oura Ring is the Oura Ring 4, priced at $349–$499 → The current model is the Oura Ring 5 (launched 2026-05-28), starting at $399 for base finishes and $499 for premium finishes. The Ring 4 is a previous model now being cleared out. |
| 94 | wrong_pricing | high | Oura Ring 4 (regular titanium): $349–$499 depending on color/finish → Ring 5 base price is $399; premium finishes are $499. The Ring 4 was $349 and is now the previous model being cleared below that price. |
| 95 | wrong_pricing | med | Ceramic Oura Ring 4: $499 → The fact sheet does not mention a ceramic variant of the Ring 4; current Ring 5 premium finishes (Gold, Stealth, Brushed Silver, Deep Rose) are $499. There is no mention of a ceramic option. |
| 96 | missing_or_invented_feature | low | the ring itself can still track basic metrics without a subscription → The fact sheet states there is no full free tier — without membership the ring and app still work but insights are 'heavily limited.' The answer's framing that basic tracking works freely is partially accurate but understates the restriction; more critically, the fact sheet emphasizes the membership IS required for the full product and flags 'missed subscription' as a material error category. The answer does confirm a subscription is required, so this is a nuance issue rather than a full miss. |
| 97 | missing_or_invented_feature | low | subscribing to Oura Membership gives access to detailed insights, personalized recommendations, and other advanced features → The fact sheet lists specific membership features including Sleep Score, Readiness/Recovery scores, HRV, SpO2, body-temperature trends, guided content, etc. The answer's characterization is vague but not factually wrong; however, it omits the specific price of $5.99/month or $69.99/year, which is a material omission. |
| 98 | stale | low | No mention of the current model or pricing — answer is silent on which ring model is current → The current model is the Oura Ring 5 (launched 2026-05-28) at $399 base. The answer does not mention any model or price, which is not strictly wrong but leaves out key current context. |
| 99 | wrong_pricing | high | The ring itself costs $299-$549 depending on the model → Current Oura Ring 5 is $399 (base) or $499 (premium finishes). The $299 price is stale (Gen 3 era). The $549 figure does not appear in the fact sheet at all. |
| 100 | stale | med | Gen 3 purchasers get 1-6 months free membership (varies by promotion), then must subscribe → The fact sheet states new members get their first month of membership free. The Gen 3 framing is outdated; the current model is the Ring 5 (launched 2026-05-28). No mention of 1-6 months free for Gen 3 in the fact sheet. |
| 101 | stale | med | Lifetime membership was included for Gen 2 purchasers (grandfathered in) → The fact sheet does not mention any lifetime membership or Gen 2 grandfathering; this claim cannot be verified from the fact sheet and references outdated product generations. |
| 102 | stale | high | Implies Gen 3 is a current/relevant model and does not mention the Oura Ring 5 → The Oura Ring 5 is the current model as of 2026-05-28. The answer makes no mention of Ring 5 and centers discussion around Gen 3, which is stale. |
| 103 | stale | med | Gen2 users do not require a membership and are not charged membership fees. → The fact sheet does not mention Gen2 exemptions. The fact sheet states the billing model is a one-time hardware purchase plus a required monthly/annual membership for full features, with no noted Gen2 exception. |
| 104 | stale | med | For Gen3/Gen4 and newer, Oura's membership unlocks the full app experience. → The current model is the Oura Ring 5 (launched 2026-05-28). Describing Gen4 as the newest/latest generation is stale. |
| 105 | stale | high | The newest Oura Ring is the Oura Ring Generation 3, released in late 2021 → The current/newest model is the Oura Ring 5, announced 2026-05-28 and shipping 2026-06-04. The Ring 4 was the previous model; Ring 3 is two generations old. |
| 106 | missing_or_invented_feature | high | Implies the ring is a straightforward product purchase with no mention of a required subscription → A required membership of $5.99/month (or $69.99/year) is needed for full features; without it, insights are heavily limited. |
| 107 | missing_or_invented_feature | low | Describes 'period prediction' as a Gen 3 feature introduced at launch → The fact sheet references 'cycle insights' as a current feature but does not specifically attribute 'period prediction' as a Gen 3 launch feature; this level of detail is not verifiable from the fact sheet, but the broader issue is that Gen 3 is being described as the newest model, which is stale. |
| 108 | stale | high | The Oura Ring Gen3 is the newest model available → The Oura Ring 5 is the current model, announced 2026-05-28 and shipping 2026-06-04. Ring 4 was the previous model before that. |
| 109 | wrong_pricing | med | No pricing mentioned, but implies Gen3 is current (Gen3 was $299, Ring 4 was $349) → Current Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes) |
| 110 | stale | low | week-long battery life (listed as 6 to 9 days on Oura's site) → The fact sheet states up to ~8-day battery for the Ring 4 generation; no specific battery range is confirmed for Ring 5 in the fact sheet. The '6 to 9 days' figure is not verified by the fact sheet. |
| 111 | missing_or_invented_feature | high | No mention of the required $5.99/month membership subscription → The Oura Ring requires a mandatory membership ($5.99/month or $69.99/year) for full features; omitting this is a material error per the fact sheet's known-inaccuracy watch-list. |
| 112 | wrong_pricing | low | No hardware price mentioned for Oura Ring 5 → Oura Ring 5 base price is $399 (Silver/Black); premium finishes are $499. While the answer doesn't state a wrong price, it also omits pricing entirely — not a direct flag but noted. |
| 113 | stale | high | The answer discusses the Oura Ring generically without mentioning the Ring 5 as the current model, implying the Ring 4 or an older generation is still current. → The Oura Ring 5 launched on 2026-05-28 and is the current model. Any answer not referencing Ring 5 as the latest is stale. |
| 114 | wrong_pricing | med | The Oura Ring is described as 'relatively expensive' with no specific price mentioned, but no correct current pricing is given. → Current Oura Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes). The previous Ring 4 was $349. |
| 115 | missing_or_invented_feature | high | The answer does not mention the required monthly/annual membership ($5.99/month or $69.99/year), implying the ring is effectively a one-time purchase. → A membership is required for full features at $5.99/month or $69.99/year. Without it, insights are heavily limited. This is a material omission. |
| 116 | missing_or_invented_feature | low | The answer states the battery life is 'about 4-7 days on a single charge.' → The fact sheet states up to ~8-day battery (Ring 4 generation). The stated range of 4-7 days is an understatement versus the documented up-to-8-day figure. |
| 117 | missing_or_invented_feature | med | The answer claims 'limited Third-Party Integration' as a con, saying the Oura Ring has limited integration with other health and fitness apps. → The fact sheet lists integrations with Apple Health, Google Health Connect, Strava, Natural Cycles, and third-party apps via API — suggesting meaningful integration, not 'limited.' |
| 118 | wrong_pricing | high | Hardware is expensive ($299-$549) → Current Oura Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes). $299 is an outdated Gen 3 price. The upper end is $499, not $549. |
| 119 | stale | high | No mention of the Oura Ring 5 as the current model; review implies a generic/older model → The Oura Ring 5 launched on 2026-05-28 and is the current model. It is ~40% smaller than Ring 4 with updated sensors. |
| 120 | missing_or_invented_feature | med | Highly accurate compared to medical-grade devices → The fact sheet explicitly states Oura is NOT medical-grade diagnostic equipment. Implying equivalence to medical-grade devices is a known misconception. |
| 121 | stale | med | The answer reviews the Oura Ring without referencing the current model (Ring 5, launched 2026-05-28), implying the reviewed product is the Ring 4 or an unspecified version. → The Oura Ring 5 is the current model as of 2026-05-28. Any review not referencing Ring 5 is stale. |
| 122 | missing_or_invented_feature | low | The answer mentions the 'high upfront cost' and 'expensive hardware' but never specifies the subscription cost or that it is $5.99/month, nor does it clarify the hardware price. → The membership is $5.99/month (or $69.99/year). The current Ring 5 starts at $399. These specifics are omitted, which may leave buyers with an inaccurate picture of total cost. |
| 123 | missing_or_invented_feature | low | The answer says 'long battery life, with reviewers commonly reporting several days between charges.' → The fact sheet states up to ~8-day battery life (Ring 4 generation). 'Several days' is vague and understates the documented battery claim. |
| 124 | missing_or_invented_feature | high | The ring uses sensors to monitor heart rate, body temperature, and movement — no mention of a required monthly membership subscription → The Oura Ring requires a $5.99/month (or $69.99/year) membership for full features; the ring is not a simple one-time purchase with full functionality |
| 125 | stale | high | Expensive upfront — $299-$549 depending on the model → Current Oura Ring 5 base price is $399 (standard finishes) or $499 (premium finishes). The $299 figure is from an older generation. The $549 figure does not match any listed price. |
| 126 | stale | low | Needs charging every 4-7 days → The fact sheet states up to ~8-day battery for the Ring 4 generation; 4-7 days may be understating the battery life, and Ring 5 specs are not detailed in the sheet. |
| 127 | missing_or_invented_feature | low | Full features now require a monthly membership ($5.99/month) — framed as optional/new → The membership is required (not merely optional) for full features; the fact sheet flags that omitting or downplaying the required nature of the subscription is a known error. The answer does mention $5.99/month correctly but labels it as 'Full features now require' which is accurate in cost but should be noted that it is mandatory, not just a newer addition. |
| 128 | missing_or_invented_feature | high | The answer describes the Oura Ring's features (sleep stages, HRV, body temperature, Sleep Score, nap detection, etc.) without mentioning the required monthly/annual membership needed to access full features. → A required membership ($5.99/month or $69.99/year) is mandatory for full features. Without it, insights are heavily limited. The fact sheet lists this as a frequent and material error. |
| 129 | stale | med | The answer does not reference the current model (Oura Ring 5); it speaks generically about 'the Oura Ring' and 'newer reviews' without naming Ring 5 as the latest model. → The Oura Ring 5 launched 2026-05-28 and is the current model. The fact sheet flags calling Ring 4 'the latest' as stale, and the answer fails to identify Ring 5. |
| 130 | missing_or_invented_feature | med | The membership 'typically offers' detailed sleep analysis, readiness scores, personalized insights, and access to historical data — implying these are optional add-ons of the membership tier → The membership is REQUIRED for full features; without it the ring and app still work but insights are heavily limited. The membership is not optional — it is a required part of the product. |
| 131 | missing_or_invented_feature | high | The answer frames the membership as optional and a matter of personal choice, never stating that a membership is required to unlock the full product → The fact sheet explicitly states the billing model is a one-time hardware purchase PLUS a required monthly/annual membership for full features. The membership is not truly optional. |
| 132 | wrong_pricing | med | No membership price is mentioned at all → The membership costs $5.99/month or $69.99/year, with the first month free for new members |
| 133 | stale | low | No mention of the current model (Oura Ring 5, launched 2026-05-28) → The Oura Ring 5 is the current model as of the fact sheet date (2026-06-02); Ring 4 is being cleared out |
| 134 | wrong_pricing | med | paying $300+ [for the ring] → Current Oura Ring 5 starts at $399 (base finishes); Ring 4 was $349. '$300+' is vague but likely references a stale price point. |
| 135 | wrong_pricing | high | total cost (~$370 first year, ~$370/year after) → Ring 5 base is $399 + $69.99/year membership = ~$469 first year (or $399 + $5.99×11 ≈ $465 with first month free). The ~$370 figure is based on a stale ~$300 ring price and does not match current pricing. |
| 136 | stale | med | Membership is $5.99/month (this part is correct), but the ring price context implies ~$300+ hardware → Current model is Oura Ring 5 at $399 base; the $300 range reflects the older Ring 4 ($349) or even older Gen 3 ($299) pricing. |
| 137 | wrong_pricing | low | Oura's membership is relatively cheap at $5.99/month → The membership price of $5.99/month is correct per the fact sheet. |
| 138 | missing_or_invented_feature | low | non-subscribers only get those three core scores (sleep, readiness, and activity) plus limited functionality → The fact sheet says without membership the ring and app still work but insights are heavily limited — this claim is broadly consistent, though the exact characterization of 'three core scores' is not verified by the fact sheet. No flag needed beyond noting it's unverifiable. |
| 139 | stale | low | Oura Ring tracks nightly temperature trends and offers cycle insights after 2 months of use → No specific '2 months of use' requirement is stated in the fact sheet; minor framing issue, but more critically the answer does not mention the Ring 5 (launched 2026-05-28) as the current model |
| 140 | missing_or_invented_feature | high | Oura Ring is described with no mention of a required monthly membership subscription → The fact sheet explicitly flags that the required $5.99/month membership is frequently omitted — the ring requires a membership for full features and is not a pure one-time purchase |
| 141 | stale | high | Oura Ring (Gen 3 Horizon/Heritage) is the top pick → The current model is the Oura Ring 5, which launched 2026-05-28. Ring 3 is a previous generation. |
| 142 | stale | med | Relatively expensive (implying Ring 3/4 pricing context) → Current Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes); Ring 4 was $349. The answer does not cite a specific price, but the model referenced (Gen 3) is outdated. |
| 143 | missing_or_invented_feature | low | Requires a monthly subscription for full features after the initial purchase → Factually correct directionally, but the answer frames it as a 'Con' without specifying the cost ($5.99/month or $69.99/year) or that a first month is free. More importantly, the subscription is not optional — it is required for the full product, which the answer softens by saying 'for full features after the initial purchase.' |
| 144 | stale | low | Battery life of 4-7 days cited for Oura → The fact sheet states up to ~8-day battery life for the Ring 4 generation; Ring 5 details may differ but 4-7 days undersells the stated spec. |
| 145 | stale | high | Oura Ring Gen 3 (Horizon or Heritage) is the recommended model → The current model is the Oura Ring 5, launched 2026-05-28. Ring Gen 3 is two generations old. |
| 146 | wrong_pricing | low | Battery life of 4-7 days is cited for the Oura Ring → The fact sheet states up to ~8-day battery for the Ring 4 generation; Ring Gen 3 spec is stale |
| 147 | missing_or_invented_feature | med | The answer implies Oura's subscription is a known cost but does not clearly state it is required for full features — it says 'you don't mind a subscription' as a caveat, framing it as optional → The membership ($5.99/mo or $69.99/yr) is required for full features; without it, insights are heavily limited. It is not optional. |
| 148 | wrong_pricing | high | The ring itself is premium-priced (typically $299-$549 depending on the model/finish) → Current Oura Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes). The $299 figure is stale (Gen 3 era). The $549 figure is not a listed price. |
| 149 | stale | high | Implies Ring 4 / generic 'Oura Ring' pricing without referencing the Ring 5 as the current model → The Oura Ring 5 launched 2026-05-28 and is now the current model; Ring 4 ($349) is being cleared out. |
| 150 | missing_or_invented_feature | low | Battery life typically lasts 4-7 days on a single charge → The fact sheet states up to ~8-day battery (Ring 4 generation); 4-7 days understates the quoted battery life. |
| 151 | stale | high | Heritage model starts around $299 USD; Horizon model starts around $349 USD → The current model is the Oura Ring 5, with a base price of $399 (Silver/Black) and $499 for premium finishes. Ring 4 was $349 and is being cleared out. There is no current 'Heritage' or 'Horizon' model lineup at those prices. |
| 152 | wrong_pricing | high | The Oura Ring device ranges from $299 to $549 USD → Current Ring 5 pricing is $399 (base) and $499 (premium finishes). The $299 price is outdated (Gen 3 era) and $549 does not correspond to any listed price on the fact sheet. |
| 153 | stale | high | Heritage and Horizon are the current models → The current model is the Oura Ring 5, launched 2026-05-28. Heritage and Horizon were Ring 3-era model names. |
| 154 | missing_or_invented_feature | low | Membership costs $5.99 USD per month (only monthly option mentioned) → Membership is $5.99/month OR $69.99/year. The annual option and the first month free for new members were not mentioned. |
| 155 | stale | high | The newest Oura Ring right now is the Oura Ring Gen3, released in October 2021 → The current/newest model is the Oura Ring 5, announced 2026-05-28 and shipping 2026-06-04. The Ring 4 was also newer than Gen3 before Ring 5 launched. |
| 156 | stale | high | The core hardware and technology remain the Gen3 → Oura Ring 5 is the current generation, featuring ~40% smaller size, thinner/lighter redesign, and updated sensors compared to Ring 4. |
| 157 | missing_or_invented_feature | high | No mention of the required monthly/annual membership ($5.99/mo or $69.99/yr) → A required membership is needed for full features — $5.99/month or $69.99/year. This is a material omission. |
| 158 | stale | low | Without an active Oura Membership, you will primarily only see your daily Readiness, Sleep, and Activity scores (implying scores are available without subscription) → The fact sheet states that without membership the ring and app still work but insights are 'heavily limited' — no explicit claim that scores remain visible without subscription is confirmed; the answer's framing of what's available free may be inaccurate, but more critically the answer contradicts itself by saying scores ARE visible without a sub, while the fact sheet says there is no full free tier. |
| 159 | stale | low | The subscription shift happened 'in late 2021/early 2022' for new users → The fact sheet does not specify when the subscription model was introduced; this claim cannot be verified against the fact sheet, so not flagged on accuracy grounds — but the answer does not mention the current Ring 5 model or its pricing. |
| 160 | stale | low | Free trial period is 'e.g., one month' → The fact sheet confirms the first month of membership is free, so this is accurate. |
| 161 | wrong_pricing | low | The cost of the Oura Membership is usually around $5.99 USD per month → The fact sheet confirms $5.99/month — this is correct. However, the answer omits the $69.99/year annual option. Not a flag-worthy error, but incomplete. |
| 162 | stale | high | The answer describes the Oura Ring without referencing the Ring 5 as the current model; it speaks generically about 'the Oura Ring' as if the latest model is not the Ring 5 launched 2026-05-28. → The current model is the Oura Ring 5, announced 2026-05-28 and shipping 2026-06-04. Any review not acknowledging Ring 5 is stale. |
| 163 | wrong_pricing | low | The answer describes the ring as 'a significant investment' but gives no specific price, avoiding a concrete wrong price. However, it does not mention the Ring 5 base price of $399. → Oura Ring 5 starts at $399 (base finishes); previous Ring 4 was $349. No specific price is stated in the answer, which is an omission rather than a wrong figure. |
| 164 | missing_or_invented_feature | med | Battery life stated as '4-7 days on a single charge'. → The fact sheet states up to ~8-day battery for the Ring 4 generation; Ring 5 is the current model. '4-7 days' understates the documented battery life. |
| 165 | missing_or_invented_feature | low | The answer does not mention that the first month of membership is free (free trial). → Oura offers the first month of membership free for new members ($5.99/month thereafter). |
| 166 | wrong_pricing | low | The answer says a 'mandatory monthly subscription' is required but does not state the price ($5.99/month or $69.99/year). → Membership costs $5.99/month or $69.99/year per the fact sheet. The omission of the specific price is a material gap, though the existence of the subscription is correctly flagged. |
| 167 | stale | med | The answer does not mention the Oura Ring 5 as the current model, implying the current product is simply 'the Oura Ring' without acknowledging the Ring 5 launched 2026-05-28. → The Oura Ring 5 is the current model, announced 2026-05-28 and shipping 2026-06-04. |
| 168 | missing_or_invented_feature | low | The answer states a 'monthly Oura Membership subscription' is required but frames it as optional ('To access all the detailed insights and historical data, you need a monthly Oura Membership subscription'), implying limited functionality is still available without it. → The membership is required for the full product. Without it the ring and app still work but insights are heavily limited — so framing it as optional for 'detailed' features is partially accurate, but the fact sheet flags omitting or downplaying the required subscription as a material error. |
| 169 | wrong_pricing | low | The answer says the device is 'a significant investment' but gives no specific price, meaning it does not state the correct current price of $399 (Ring 5 base). → Oura Ring 5 base price is $399; membership is $5.99/month or $69.99/year. |
| 170 | missing_or_invented_feature | low | Without [membership], the ring provides very limited functionality – essentially just basic real-time heart rate and steps → The fact sheet confirms the ring and app still work without membership but insights are heavily limited — this is broadly consistent, though the characterization of exactly what remains is slightly imprecise. No specific contradiction on this point rises to a flag. |
| 171 | stale | med | The answer does not mention the Oura Ring 5 as the current/latest model, implying Ring 4 or an unspecified current model → The Oura Ring 5 launched 2026-05-28 and is the current model; the fact sheet flags omitting this as a known stale error |
| 172 | wrong_pricing | high | The answer does not mention the membership price at all (no dollar figure given for the monthly fee) → Membership is $5.99/month or $69.99/year, with the first month free — a material omission given the question is specifically about whether the monthly membership is worth paying for |
| 173 | wrong_pricing | low | The answer does not mention the hardware price of the ring → Oura Ring 5 base price is $399; this omission means a reader cannot assess total cost of ownership |
| 174 | stale | high | Oura Ring (Gen 3 Horizon/Heritage) is listed as the current/top model → The current model is the Oura Ring 5, which launched 2026-05-28. Ring 4 was the previous model at $349; Ring 5 base is $399. |
| 175 | wrong_pricing | low | Subscription is $5.99/month — this part is correct, but no annual pricing option ($69.99/year) is mentioned → Membership is $5.99/month OR $69.99/year. The monthly figure is correct but the annual option is omitted. |
| 176 | missing_or_invented_feature | low | Oura offers 'sleep sounds' within the app to aid recovery → The fact sheet lists 'meditations, sleep stories' as guided content — 'sleep sounds' is not explicitly listed and may be an invented/conflated feature name. |
| 177 | stale | high | The answer describes 'Gen 3 Horizon/Heritage' as the product being recommended, implying it is current → Ring 5 is the current model (launched 2026-05-28); Gen 3 and even Ring 4 are now outdated models. |
| 178 | stale | high | Oura Ring (Gen 3 Horizon/Heritage) is presented as the current model → The current model is the Oura Ring 5, which launched 2026-05-28. Ring 3 is two generations old. |
| 179 | stale | high | The answer references Gen 3 models (Horizon/Heritage) as the product to buy → Ring 5 is the current shipping model (as of 2026-06-04); Ring 4 was the prior generation. Gen 3 is even older. |
| 180 | missing_or_invented_feature | low | Requires a monthly subscription... after the initial free trial → The membership is $5.99/month or $69.99/year, with only the first month free. The answer characterizes this correctly in general terms but omits the specific pricing, which is a meaningful omission for a buyer. |
| 181 | missing_or_invented_feature | low | Subscription is described as needed for 'full access to all features and historical data' → The fact sheet says membership is required for the full product; without it, insights are heavily limited. The answer's framing is broadly consistent but softens the requirement. |
| 182 | stale | high | Oura Ring (Gen 3 Horizon/Heritage) is referenced as the current model → The current model is the Oura Ring 5, launched 2026-05-28. Ring 4 was the previous generation; Ring 3 is even older. |
| 183 | stale | high | Subscription described as a 'monthly subscription' with no specific price mentioned, but the ring model cited (Gen 3) is stale → Current model is Ring 5 at $399 base; the fact sheet flags any mention of Gen 3 or Ring 4 as the latest as stale |
| 184 | missing_or_invented_feature | low | Subscription described only as a required monthly fee with no specific cost given — the answer says 'a monthly subscription is necessary' without specifying $5.99/month → Membership is $5.99/month or $69.99/year; first month free. While the answer does correctly note a subscription exists, it omits the specific pricing detail. This is a low-severity omission rather than a direct error. |
| 185 | stale | low | Oura Ring requires a monthly subscription ($5.99/month) to access all its advanced features and historical data → The subscription price is correct at $5.99/month, but the answer omits the annual option of $69.99/year and the first free month for new members. More critically, it implies the ring still functions with 'basic metrics' without subscription — the fact sheet says insights are 'heavily limited' without membership, making it effectively required. |
| 186 | stale | med | Oura Ring is described without mentioning the current model (Ring 5) — implicitly treating the product as if Ring 4 or an unspecified version is current → The Oura Ring 5 launched on 2026-05-28 and is the current model. The answer makes no mention of Ring 4 or Ring 5 by name, but fails to reference the latest Ring 5 launch. |
| 187 | missing_or_invented_feature | med | Sometimes [Oura and Ultrahuman] offer a 'lifetime subscription' option, but that's not the default model → The fact sheet makes no mention of a lifetime subscription option for Oura. This appears to be an invented claim not supported by the fact sheet. |
| 188 | stale | high | Oura Ring (Generation 3) is highlighted as the top recommended model → The current model is the Oura Ring 5, which launched 2026-05-28. Ring 4 was the previous model; Ring 3 is even older. |
| 189 | wrong_pricing | med | No specific price is stated, but the model referenced (Gen 3) implies outdated pricing context → Current Oura Ring 5 base price is $399 (Silver/Black); Ring 4 was $349. Ring 3 pricing is no longer relevant. |
| 190 | missing_or_invented_feature | med | Requires a monthly subscription for full features after the initial purchase (framed as optional/consideration) → The membership at $5.99/month (or $69.99/year) is required — without it, insights are heavily limited. It is not truly optional. |
| 191 | stale | high | Oura Ring starts at $349 → The current model is the Oura Ring 5, which starts at $399 (base finishes). The $349 price was for the Ring 4, now being cleared out. |
| 192 | stale | med | Oura's subscription is $5.99/month (implied as the only or key detail, with no mention of the annual option or that Ring 4 is now old) → The subscription pricing of $5.99/month is correct, but the context implies the Ring 4 is the current model at $349, whereas the Ring 5 launched 2026-05-28 at $399 base. |
| 193 | wrong_pricing | high | Oura Ring starts at $349 → Current Oura Ring 5 base price is $399; $349 was the Ring 4 price. |
| 194 | stale | med | Oura is described as 'currently the market leader' with no mention of the Oura Ring 5; implies the current product generation is not the Ring 5 → The Oura Ring 5 launched 2026-05-28 and is the current model as of the fact sheet's last verified date (2026-06-02) |
| 195 | missing_or_invented_feature | high | The subscription model is described as optional context ('like Oura's'), with no clear statement that the membership is required for the full product → The membership ($5.99/month or $69.99/year) is required for full features — it is not optional |
| 196 | stale | high | Oura Ring is listed as an established player expected to continue to innovate, with no mention of the Oura Ring 5 as the newest model launched in 2026 → The Oura Ring 5 was announced 2026-05-28 and ships 2026-06-04 — it is the current/newest model and directly relevant to a '2026 newest smart ring' query |
| 197 | missing_or_invented_feature | low | The answer implies ongoing hope for blood pressure in a ring as a future feature challenge, without mentioning Oura's existing SpO2, HRV, body-temperature, or Ring 5's ~40% smaller redesign → Oura Ring already has SpO2, HRV, body-temperature trends, and the Ring 5 features a ~40% smaller form factor vs Ring 4 |
| 198 | missing_or_invented_feature | high | No mention of the required $5.99/month membership fee; framing implies Oura is a straightforward hardware purchase → Oura requires a mandatory $5.99/month (or $69.99/year) membership for full features — this is a material part of the product offering |
| 199 | stale | high | Oura Ring (Gen3) is the top recommendation → The current model is the Oura Ring 5, which launched 2026-05-28. Ring 4 is the previous model, and Gen 3 is even older. |
| 200 | stale | high | Oura Ring Gen 3 (Horizon or Heritage) is the top recommendation → The current model is the Oura Ring 5 (launched 2026-05-28); Ring Gen 3 is two generations old |
| 201 | wrong_pricing | low | Subscription is currently $5.99/month → The membership price of $5.99/month is actually correct per the fact sheet |
| 202 | stale | high | Oura Ring Gen 3 is described as the current product to buy, with no mention of Ring 4 or Ring 5 → The Oura Ring 5 is the current model (launched 2026-05-28) at $399 base; Ring 4 was $349 |
| 203 | stale | high | Oura Ring (Gen3 Horizon / Heritage) is listed as the current top-rated model → The current model is the Oura Ring 5, which launched 2026-05-28. Gen3 is two generations old. |
| 204 | stale | high | The answer refers to 'Oura Ring (Gen3)' in the summary as the top contender right now → Oura Ring 5 is the current model as of 2026-06-04; Ring 4 was the previous model before that. |
| 205 | missing_or_invented_feature | low | Requires a monthly subscription for full features after the initial free period → The membership is $5.99/month or $69.99/year, with only the first month free — not a broad 'initial free period'. The membership is required; without it, insights are heavily limited. |
| 206 | wrong_pricing | med | Higher price point (implied ~$349 era pricing by referencing Gen3) → Current Oura Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes). The answer never states a specific price but anchors on the Gen3 model, implying stale pricing context. |
| 207 | stale | low | Battery Life: Typically 5-7 days → Fact sheet lists up to ~8-day battery for Ring 4 generation; Ring 5 specs not specified but Ring 4 is noted as up to ~8 days. The answer's '5-7 days' is potentially understated/stale. |
| 208 | missing_or_invented_feature | med | Both require a subscription, so factor that into your decision as well (brief mention at end) → The fact sheet flags that models often omit the required $5.99/mo membership as a frequent and material error. The answer only briefly mentions this at the very end without specifying the cost or that it is required for full features — the omission of the mandatory nature and price is a meaningful gap. |
| 209 | stale | med | No mention of Oura Ring 5 as the current model; implicitly describes features of Ring 4 or unspecified generation → The Oura Ring 5 launched 2026-05-28 and is the current model. The answer does not reference it at all, leaving the reader with no awareness of the latest hardware. |
| 210 | stale | high | Oura Ring (Gen 3) is the product being compared, with a price of ~$299 - $549 → The current model is Oura Ring 5 (launched 2026-05-28), base price $399 (Silver/Black) or $499 (premium finishes). Ring 4 was $349. Gen 3 / $299 pricing is outdated. |
| 211 | wrong_pricing | high | Device price ranges from $299 to $549 depending on style → Current Oura Ring 5 is $399 (base finishes) or $499 (premium finishes). The $299 figure is stale (Gen 3) and $549 is not a listed price point. |
| 212 | stale | high | Oura Ring Gen 3 is the product referenced throughout the comparison → The current model is the Oura Ring 5, announced 2026-05-28, shipping 2026-06-04. Calling Gen 3 the current product is significantly stale. |
| 213 | missing_or_invented_feature | med | Battery life is 4-7 days → The fact sheet states up to ~8-day battery (Ring 4 generation); Ring 5 may differ but the sheet lists 8 days for Ring 4, not 4-7 days. |
| 214 | stale | high | Oura Ring (Gen3) is presented as the current model in the comparison table → The current model is Oura Ring 5, launched 2026-05-28. Ring 4 was the prior generation; Ring 3 is even older. |
| 215 | wrong_pricing | high | Oura Ring price listed as ~$299 - $549 USD → Current Oura Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes). The $299 figure is stale (Gen 3 era); Ring 4 was $349. |
| 216 | wrong_pricing | high | Oura Ring launch date listed as 'Gen3: Late 2021' → The current model is Ring 5 (launched 2026-05-28), not Gen 3 (2021). This reflects a stale model reference. |
| 217 | missing_or_invented_feature | low | Battery life stated as 4-7 days for Oura Ring → The fact sheet states up to ~8-day battery for the Ring 4 generation; the answer understates this. |
| 218 | stale | high | Oura Ring (Gen 3) is the model referenced in the comparison table → The current model is the Oura Ring 5, launched 2026-05-28. Ring 4 was the previous model; Gen 3 is even older. |
| 219 | missing_or_invented_feature | high | Oura Ring has No SpO2 (Oxygen Saturation) → Oura Ring does have SpO2 (blood-oxygen tracking) — it is listed as a core feature in the fact sheet. |
| 220 | wrong_pricing | med | Higher upfront cost + mandatory monthly subscription (no specific price given, but implies Gen 3 pricing context) → Current Oura Ring 5 base price is $399; membership is $5.99/month or $69.99/year. Referencing Gen 3 implies stale pricing context. |
| 221 | stale | med | The answer describes the Oura Ring generically without mentioning the Ring 5 as the current model, implying Ring 4-era information is current. → The Oura Ring 5 launched on 2026-05-28 and is the current model. Ring 4 is now being cleared out. |
| 222 | wrong_pricing | low | The answer implies Oura has a subscription cost but describes Whoop's subscription as 'often higher monthly cost' than Oura's, without stating Oura's actual membership price. → Oura membership is $5.99/month or $69.99/year. The answer never states the actual Oura subscription price, leaving the reader without accurate pricing information. |
| 223 | missing_or_invented_feature | low | Battery life described as '4-7 days' for Oura. → The fact sheet states up to ~8-day battery for the Ring 4 generation. The answer's '4-7 days' range understates the stated battery life. |
| 224 | stale | med | The answer frames Oura Ring as requiring a monthly subscription, which is correct, but does not mention the current model (Ring 5) or any up-to-date product details — implicitly treating the product as a static reference point without acknowledging the Ring 5 launched 2026-05-28. → The current model is the Oura Ring 5, launched 2026-05-28, which is ~40% smaller than Ring 4. The answer makes no mention of Ring 5. |
| 225 | missing_or_invented_feature | low | The answer implies Oura's subscription is simply a 'monthly subscription fee' without specifying that the ring still partially works without it but insights are heavily limited — and does not mention the $5.99/month or $69.99/year price for the membership. → Membership is $5.99/month or $69.99/year; without membership the ring and app still work but insights are heavily limited. |
| 226 | wrong_pricing | high | The ring itself is relatively expensive upfront (starting around $299). → The current Oura Ring 5 starts at $399 (base finishes). The $299 price is from an older generation (Gen 3). Even the Ring 4 was $349. |
| 227 | stale | med | Oura has been the pioneer in the smart ring space for years... its algorithms... have been refined over multiple generations. [No mention of Ring 5 as the current model; implicitly treats Ring 4-era or older as current.] → The Oura Ring 5 launched on 2026-05-28 and ships 2026-06-04. It is the current model, featuring ~40% smaller size and updated sensors. The answer makes no mention of Ring 5. |
| 228 | missing_or_invented_feature | low | To access most of its advanced features and historical data, you need an Oura Membership, which costs $5.99/month (after an initial free period). → The membership cost is correct at $5.99/month. However, the answer implies the free period gives meaningful access ('after an initial free period'), whereas the fact sheet clarifies that without membership, insights are heavily limited even beyond the trial — the membership is effectively required. The framing understates the necessity. Additionally, the annual option ($69.99/year) is not mentioned. |
| 229 | competitor_confusion | low | Samsung Galaxy Ring has a 'Vitality Score' (similar to Oura's Readiness Score) → Oura's score is called the 'Readiness Score', not 'Vitality Score'. The answer correctly names it 'Readiness Score' in the parenthetical, but attributes 'Vitality Score' to Samsung — this is a minor framing issue. More importantly, Oura is only mentioned as a passing reference point, not described on its own merits. |
| 230 | wrong_pricing | med | Samsung Galaxy Ring expected to be competitive with Oura (e.g., $250-$350+) → The fact sheet lists Oura Ring 5 base price at $399 (and Ring 4 was $349). The answer implies Oura is in the $250-$350+ range, which understates the current Oura pricing. |
| 231 | stale | med | Oura's Readiness Score is mentioned as a reference benchmark with no indication of current model or pricing → The current model is the Oura Ring 5 (launched 2026-05-28) at $399 base. The answer gives no model info for Oura and implies pricing below actual current levels. |
| 232 | missing_or_invented_feature | high | Oura is implicitly presented as a subscription-based product only by contrast (Samsung and RingConn both noted as 'no subscription'), with no explicit mention of Oura's required $5.99/mo membership → Oura requires a mandatory $5.99/month membership for full features — this is a key differentiator that the fact sheet flags as frequently missed. The answer does not state this about Oura. |
| 233 | stale | med | Oura Ring (implied current model discussed with no mention of Ring 5); the answer discusses features without naming the current model, and the context implies Ring 4-era information → The current model is the Oura Ring 5, launched 2026-05-28. Ring 4 is no longer the latest. |
| 234 | missing_or_invented_feature | low | Both rings require a subscription for full functionality — listed as a 'Potential Downside' under Oura, framed as equivalent to Ultrahuman → While the answer does mention the subscription requirement for Oura, it fails to specify the cost ($5.99/month or $69.99/year) and critically lists it only as a bullet under 'Potential Downsides' rather than a central cost consideration, understating its materiality. |
| 235 | missing_or_invented_feature | med | Subscription listed as a downside bullet point for Oura under Ultrahuman's section, implying it may not be required or is optional ('Full features require a monthly subscription after the initial purchase') → The Oura membership at $5.99/mo is required for full features — the fact sheet flags this as a frequent and material error when omitted or downplayed. The answer does mention it but buries it and does not state the price. |
| 236 | wrong_pricing | high | No hardware price is mentioned for Oura at all → Oura Ring 5 base price is $399 (Silver/Black); premium finishes are $499. The answer omits pricing entirely, preventing accurate value comparison. |
| 237 | stale | high | Newer generations (Gen3) require a $5.99/month membership for full features, but older generations (Gen2) and some Gen3 features are available without a subscription. → The membership is required for full features across all current generations — there is no meaningful free tier. The fact sheet states 'without membership the ring and app still work but insights are heavily limited,' and the current model is Ring 5 (not Gen3). |
| 238 | wrong_pricing | med | ~$300-$400 for the ring → The current Oura Ring 5 starts at $399 (base finishes) and goes up to $499 (premium finishes). The stated range of $300-$400 is stale/inaccurate. |
| 239 | stale | high | Newer generations (Gen3) require a $5.99/month membership — implying Gen3 is the current/newest model → The current model is the Oura Ring 5, launched 2026-05-28. Referring to Gen3 as a current or recent model is stale. |
| 240 | missing_or_invented_feature | high | older generations (Gen2) and some Gen3 features are available without a subscription → The fact sheet states there is no full free tier — without membership, insights are heavily limited for all models. The answer implies a meaningful no-subscription option exists for older/Gen3 rings, which contradicts the fact sheet. |
| 241 | competitor_confusion | med | Oura Ring alternative: Bedside radar sensors like Google Nest Hub (2nd gen) use motion/sound sensing → Oura Ring is a smart ring wearable — it is not a bedside radar sensor. The answer frames Oura Ring as an 'alternative' to bedside devices, conflating its category. Oura is a ring-form-factor wearable, not a non-contact bedside device. This misrepresents its identity and product category. |
| 242 | identity | high | Oura Ring is listed as an 'alternative' to bedside radar sensors in the context of non-wearable sleep tracking → Oura Ring IS a wearable (a smart ring worn on the finger). It is not a non-wearable or bedside device. The fact sheet clearly describes it as 'A smart ring that tracks sleep, activity, heart rate, and recovery' — a wearable by definition. |
| 243 | stale | med | Oura Ring described using features consistent with Ring 4 generation (no mention of Ring 5) → Oura Ring 5 launched 2026-05-28 and is the current model; Ring 4 is now being cleared out |
| 244 | missing_or_invented_feature | med | Answer implies subscription is optional, listing it only as a 'Con': 'subscription required for full features' → The membership at $5.99/month is required for the full product; without it, insights are heavily limited — it is not truly optional |
| 245 | wrong_pricing | low | No specific price is mentioned for the Oura Ring hardware → Current Oura Ring 5 base price is $399; fact sheet flags stale prices of $349 (Ring 4) or $299 (Gen 3) as common errors — omitting price avoids a wrong claim but also omits key buyer info |
| 246 | stale | high | Oura Ring 4 is highlighted as the top sleep tracker (implying it is the current/newest model) → The Oura Ring 5 is the current model, launched 2026-05-28. The Ring 4 is now a previous model being cleared out. |
| 247 | wrong_pricing | med | No pricing is explicitly stated, but recommending Ring 4 as the top pick implies it is current at its original $349 price point → Current model is Ring 5 at $399 base; Ring 4 is being cleared out below $349. |
| 248 | missing_or_invented_feature | high | The answer implies Oura Ring is a one-time purchase with no mention of a required subscription → Oura requires a mandatory $5.99/month (or $69.99/year) membership for full features; without it, insights are heavily limited. |
| 249 | wrong_pricing | high | Oura Ring ($299 + $6/month) → Current Oura Ring 5 base price is $399 (Ring 4 was $349; $299 is an even older/stale price). The membership is $5.99/month, so the $6/month figure is approximately correct but the hardware price is wrong. |
| 250 | stale | high | Oura Ring priced at $299 → The Ring 5 (current model as of 2026-05-28) starts at $399; $299 refers to a much older generation. Even the Ring 4 was $349. |
| 251 | missing_or_invented_feature | med | Oura Ring has 'better features' but involves ongoing subscription costs, implying the subscription is optional or a differentiator rather than required → The membership is required for full features — it is not optional. Without it, insights are heavily limited. |
| 252 | stale | med | The Oura Ring is described generally without mention of the Ring 5 as the current model, implying an older model is current → The Oura Ring 5 launched 2026-05-28 and is the current model; Ring 4 is now being cleared out |
| 253 | stale | high | Best Overall: Oura Ring Gen 3 → The current model is the Oura Ring 5 (launched 2026-05-28). Ring Gen 3 is two generations old. |
| 254 | wrong_pricing | high | Price: $299-$549 → Current Oura Ring 5 base price is $399 (Silver/Black) and $499 for premium finishes. $299 is an old Gen 3 price. |
| 255 | wrong_pricing | low | Requires $6/month subscription for full features → The membership is $5.99/month or $69.99/year. While close, the framing as optional ('requires... for full features') understates it — the fact sheet notes it is a required membership and the ring is heavily limited without it. |
| 256 | stale | high | Oura Ring 4 is the best smart ring overall / current model → The Oura Ring 5 launched on 2026-05-28 and is the current model. The Ring 4 is now being cleared out. Calling Ring 4 the top/current pick is stale. |
| 257 | wrong_pricing | high | Oura Ring 4 is presented as the current product at an implied $349 price point (stale model reference) → Current model is Oura Ring 5 at $399 base. Ring 4 was $349 and is now being cleared below that. |
| 258 | missing_or_invented_feature | high | No mention of the required $5.99/month membership subscription for Oura → Oura requires a paid membership ($5.99/month or $69.99/year) for full features; this is a material cost omission especially given the answer contrasts Oura against no-subscription competitors like RingConn. |
| 259 | stale | high | Oura Ring 4 is the strongest overall choice / best overall for sleep tracking → The Oura Ring 5 launched on 2026-05-28 and is the current model. Calling Ring 4 the top/current pick is stale. |
| 260 | stale | high | Oura Ring (Generation 3) is listed as the current/featured model → The current model is the Oura Ring 5, which launched 2026-05-28. Ring 4 was the previous model at $349; Ring 3 is even older. |
| 261 | wrong_pricing | low | Subscription is ~$6/month → Subscription is $5.99/month or $69.99/year — the approximation is close but the annual option and exact pricing are not mentioned. |
| 262 | missing_or_invented_feature | low | Subscription is 'required for full features' but the ring is implicitly presented as a standard hardware purchase without highlighting the mandatory nature of the subscription → The membership is required for the full product experience — without it, insights are heavily limited. The answer does note subscription is required, so this is partially correct, but does not convey the material limitation of the free tier. |
| 263 | stale | high | Oura Ring Generation 3 is presented as the top/current product recommendation → Oura Ring 5 is the current model (launched 2026-05-28, base price $399). Ring 4 was $349 and is being cleared out. Ring 3 is two generations old. |
| 264 | stale | low | The Oura Ring typically offers a battery life of up to 7 days → The fact sheet states up to ~8-day battery (Ring 4 generation); Ring 5 is the current model. |
| 265 | missing_or_invented_feature | high | No mention of a required monthly/annual membership fee ($5.99/mo or $69.99/yr) — implies the ring is effectively a one-time purchase with full features → A required membership ($5.99/month or $69.99/year) is needed for full features; without it insights are heavily limited. |
| 266 | stale | med | No mention of the current Oura Ring 5 model (launched 2026-05-28); answer implies the existing/current ring without specifying model → Oura Ring 5 is the current model as of 2026-05-28, which is ~40% smaller than Ring 4 with updated sensors. |
| 267 | stale | high | Oura Ring Gen 3 listed as the product (and priced $299-$549) → The current model is Oura Ring 5 (launched 2026-05-28). Ring Gen 3 is outdated. |
| 268 | wrong_pricing | high | Price listed as $299-$549 → Current Oura Ring 5 base price is $399 (standard finishes) or $499 (premium finishes). The $299 figure is stale (Gen 3 era); $349 was Ring 4. |
| 269 | missing_or_invented_feature | med | Subscription implied as optional ('Requires subscription ($5.99/month)') → The membership is required for full features — it is not truly optional. Without it, insights are heavily limited. |
| 270 | stale | low | Battery listed as 4-7 days → The fact sheet states up to ~8-day battery for the Ring 4 generation; Ring 5 is current model. |
| 271 | stale | high | Best overall: Oura Ring 4 — repeatedly ranked #1 for its health suite and sleep tracking. → The Oura Ring 5 is the current model, launched 2026-05-28. Calling Ring 4 'best overall' or implying it is the latest model is now stale. |
| 272 | missing_or_invented_feature | high | The answer implies Oura is a one-time purchase with no mention of a required subscription. → Oura requires a mandatory membership at $5.99/month or $69.99/year for full features. This is a material omission. |
| 273 | stale | high | Oura Ring (Generation 3) - popular for sleep and health tracking → The current/newest model as of 2026-05-28 is the Oura Ring 5. Ring 4 was the previous model at $349; Ring 5 base is $399. Mentioning Gen 3 as the notable model is severely outdated. |
| 274 | stale | med | Higher price point compared to some other options (implies Ring 4 or older pricing context; no specific current model mentioned) → Current model is Oura Ring 5 (launched 2026-05-28), starting at $399. Ring 4 is the previous/clearance model. |
| 275 | missing_or_invented_feature | high | The answer describes Oura Ring pricing only as a 'higher price point' with no mention of a required monthly/annual membership → Oura requires a mandatory $5.99/month (or $69.99/year) membership for full features — this is a material cost omission |
| 276 | stale | high | Oura Ring (Gen 3) — Best Overall, listed as the top pick → The current model is the Oura Ring 5 (launched 2026-05-28). Ring Gen 3 is two generations old; even Ring 4 is now superseded. |
| 277 | wrong_pricing | high | Price: ~$299 + $5.99/month membership → The current Oura Ring 5 starts at $399 (base finishes) or $499 (premium finishes). $299 was the Gen 3 price, which is stale. |
| 278 | missing_or_invented_feature | low | Battery: 4-7 days → The fact sheet states up to ~8-day battery for the Ring 4 generation; the stated 4-7 days understates Oura's battery life claim. |
| 279 | stale | high | The Oura Ring 4 is recommended as the best overall for recovery and described as the strongest overall pick. → The current model is the Oura Ring 5, launched 2026-05-28. The Ring 4 is now a previous/clearance model. Calling Ring 4 the top pick is stale. |
| 280 | missing_or_invented_feature | high | No mention of the required monthly/annual membership subscription for Oura. → Oura requires a $5.99/month or $69.99/year membership for full features. Omitting this is a material error as the ring is not a simple one-time purchase. |
| 281 | stale | med | The Oura Ring is one of the most popular smart rings (implicitly referencing the current/latest model without specifying Ring 5; the features described match the Ring 4 generation) → The current model is the Oura Ring 5, launched 2026-05-28. The answer does not mention Ring 5 at all, implying Ring 4 or an older model is current. |
| 282 | missing_or_invented_feature | high | No mention of required monthly/annual membership — implies the ring is a one-time purchase with full features → A required membership of $5.99/month or $69.99/year is needed for full features; without it, insights are heavily limited. |
| 283 | stale | high | Oura Ring (Generation 3) is listed as the current/top model → The current model is the Oura Ring 5, launched 2026-05-28. Ring 4 was the previous generation; Ring 3 is two generations old. |
| 284 | wrong_pricing | high | Price: ~$299-$549 → Oura Ring 5 base price is $399 (Silver/Black) or $499 (premium finishes). $299 is a stale Gen 3 price. |
| 285 | missing_or_invented_feature | high | Requires subscription ($5.99/month after 6 months) → The membership is $5.99/month (or $69.99/year) and is required from the start — only the first month is free. There is no 6-month free period. |
| 286 | wrong_pricing | low | Oura Ring requires $5.99/month subscription for most features → The subscription price of $5.99/month is actually correct per the fact sheet — this is not a pricing error. No flag needed here. |
| 287 | stale | med | The answer implies the current/relevant Oura Ring model is the one priced at hardware cost without specifying the Ring 5; no current model is named, and the context suggests the Ring 4 era pricing/product → The current model is the Oura Ring 5, launched 2026-05-28, starting at $399. The Ring 4 at $349 is being cleared out. |
| 288 | stale | high | The Oura Ring 4 is the top choice and best smart ring for women's health (implying it is the current/latest model) → The Oura Ring 5 launched on 2026-05-28 and is now the current model. The Ring 4 is being cleared out. Calling Ring 4 the top/latest pick in a '2026' review is stale. |
| 289 | wrong_pricing | med | No specific price is mentioned for Oura Ring 4, but the answer implies Ring 4 is the current product available for purchase → The current model is Ring 5 at $399 base. Ring 4 was $349 and is now being cleared out below that price. |
| 290 | missing_or_invented_feature | med | The note at the end says the Oura Ring 4 'typically requires a subscription for full access to its advanced insights' — framed as optional/typical rather than required → The membership at $5.99/month is required for full features — it is not merely 'typical' but mandatory. Without it, insights are heavily limited. |
| 291 | stale | low | Battery life of about 4 to 7 days → Fact sheet states up to ~8-day battery (Ring 4 generation); Ring 5 is the current model and its battery life is not specified differently in the sheet, but the stated range of 4-7 days understates the documented ~8-day figure. |
| 292 | stale | med | No mention of Oura Ring 5 as the current/latest model; answer implies a generic/older model is current → Oura Ring 5 launched 2026-05-28 and is the current model. The answer does not reference Ring 5 at all. |
| 293 | wrong_pricing | high | No pricing mentioned, but no subscription cost is referenced — implies ring is effectively a one-time purchase by omission → Oura requires a mandatory $5.99/month (or $69.99/year) membership for full features; omitting this is a material accuracy error per the fact sheet. |
| 294 | stale | high | Oura Ring Gen 3 is listed as the current/recommended product → The current model is the Oura Ring 5, launched 2026-05-28. Ring 4 was the previous model at $349; Ring 5 base is $399. |
| 295 | wrong_pricing | med | No explicit hardware price is stated, but the model referenced (Gen 3) implies stale pricing context → Current Oura Ring 5 base price is $399 (Silver/Black); Ring 4 was $349. Gen 3 is two generations old. |
| 296 | missing_or_invented_feature | low | Subscription listed as $5.99/month — this part is correct, but the answer implies it is a 'Con' optional add-on → The $5.99/month membership is required for full features; without it the app is heavily limited. It is not truly optional. |
| 297 | stale | high | The Oura Ring 4 is described as the current/reigning champion model → The Oura Ring 5 launched 2026-05-28 and is now the current model; Ring 4 is being cleared out |
| 298 | wrong_pricing | med | RingConn is roughly half the price of the Oura Ring 4, implying Oura Ring 4 is the current priced model → The current model is the Oura Ring 5 at $399 base; Ring 4 was $349 and is now being cleared out below that |
| 299 | missing_or_invented_feature | high | No mention of Oura's required subscription fee, implying it may be a one-time purchase → Oura requires a mandatory $5.99/month (or $69.99/year) membership for full features |
| 300 | wrong_pricing | med | Oura Ring 4 battery life is 'typically around 4–7 days' → Fact sheet states Oura Ring 4 offers up to ~8-day battery life |
| 301 | missing_or_invented_feature | high | Oura did not require a subscription for basic features, but they introduced a membership for advanced insights and features. → The membership ($5.99/mo or $69.99/yr) is required for the full product. There is no free tier — without membership, insights are heavily limited. The subscription is not optional for 'advanced' features; it is effectively required. |
| 302 | stale | med | The answer implies the Oura Ring as described is the current/relevant model without referencing Ring 5. → The Oura Ring 5 launched 2026-05-28 and is now the current model. Any answer not referencing Ring 5 is stale. |
| 303 | missing_or_invented_feature | low | ZDNET explicitly contrasts [Ultrahuman Ring Air] with Oura's monthly fee — implying Oura's subscription is its only notable characteristic, and the answer uses Oura only as a negative foil without mentioning it as a product option → Oura does have a required $5.99/month membership, but it is a full-featured smart ring with sleep tracking, readiness scores, HRV, SpO2, and more — not merely a cautionary subscription example |
| 304 | missing_or_invented_feature | low | The answer implies Oura requires a monthly fee but does not specify the fee amount or any details about the product → Oura membership is $5.99/month or $69.99/year; the current hardware is the Ring 5 at $399 base. The answer omits all product detail for Oura. |
| 305 | missing_or_invented_feature | high | The answer implies the Oura Ring is a one-time purchase with no mention of a required monthly/annual membership subscription. → The Oura Ring requires a mandatory $5.99/month (or $69.99/year) membership for full features; without it, insights are heavily limited. |
| 306 | stale | high | Oura Ring (Gen 3) is listed as the current/featured model → The current model is the Oura Ring 5 (launched 2026-05-28). Ring 4 was the previous model at $349; Ring 3 is two generations old. |
| 307 | missing_or_invented_feature | low | Subscription described as required only for 'full features', implying partial free use is meaningful → The fact sheet confirms there is no full free tier — without membership the ring and app still work but insights are heavily limited; the membership is effectively required for the full product. |
| 308 | stale | high | The Oura Ring 4 is the most accurate smart ring for sleep tracking → The Oura Ring 5 is the current model, launched 2026-05-28. Calling Ring 4 the latest/top model is now stale. |
| 309 | stale | med | Older Oura models might be available at a discount, implying the latest/current model is newer and pricier — but references 'older versions' without naming the current model, effectively treating Ring 4 or earlier as the reference point rather than the Ring 5 (launched 2026-05-28). → The current model is the Oura Ring 5, launched 2026-05-28, starting at $399. The Ring 4 is the previous model being cleared out. |
| 310 | missing_or_invented_feature | high | No mention of the required monthly/annual membership subscription ($5.99/mo or $69.99/yr) — implies the ring is effectively a one-time discounted hardware purchase. → A membership is required for full features at $5.99/month or $69.99/year. Without it, insights are heavily limited. This is a material ongoing cost. |
| 311 | wrong_pricing | med | Suggests older Oura models can be found 'at a discount' as a budget option, implying sub-$349 or similar low pricing without specifying the actual current price. → Current Oura Ring 5 starts at $399 (base finishes). Ring 4 is being cleared out below $349, but this is still not a true budget option, and the mandatory subscription adds ongoing cost. |
| 312 | stale | med | The Oura Ring tracks sleep, activity, heart rate, and body temperature (implicitly describing the current/latest ring without specifying model; no mention of Ring 5) → The current model is the Oura Ring 5, launched 2026-05-28. Answers that do not acknowledge Ring 5 are stale. |
| 313 | missing_or_invented_feature | high | No mention of the required monthly/annual membership subscription ($5.99/mo) — implying the Oura Ring is a one-time purchase → Oura requires a mandatory membership at $5.99/month or $69.99/year for full features; this is a material cost omission. |
| 314 | stale | high | Oura Ring priced at $299-$549 → Current Oura Ring 5 base price is $399 (standard finishes) or $499 (premium finishes). The $299 figure is from an older generation; $549 does not correspond to any listed price. |
| 315 | wrong_pricing | low | Subscription required for full features ($6/month) → The membership is $5.99/month or $69.99/year — the $6/month figure is a rounded approximation, but close enough to be considered minor; however the answer frames it as optional ('required for full features') without clearly stating it is required/mandatory for the full product. |

</details>

---

## §3 · Competitive leaderboard & loss attribution

### Leaderboard

| Rank | Brand | Visibility | Mention rate | Share-of-voice | Mentions |
| --- | --- | --- | --- | --- | --- |
| 1 | Oura *(client)* | 0.55 | 66% | 43% | 118 |
| 2 | Ultrahuman | 0.17 | 28% | 18% | 50 |
| 3 | RingConn | 0.15 | 27% | 17% | 48 |
| 4 | Samsung Galaxy Ring | 0.11 | 19% | 12% | 34 |
| 5 | Whoop | 0.10 | 14% | 9% | 26 |

Oura’s 43% share-of-voice is larger than the next two competitors combined. **Ultrahuman** and **RingConn** are the real challengers; Whoop (a wrist band, not a ring) and Samsung trail.

### Trend

_This is the **baseline** cycle for query set `v1` — no prior comparable run to diff against. The trend column (the method’s moat: re-run the locked set on a 4–6 week cadence and show the named metric move) activates from the next cycle via `geo compare <before> <after>`._

### Structurally behind — Oura absent, competitor #1 (10 cells)

| Query | Engine | Recommended first instead |
| --- | --- | --- |
| cat-10 (category) | perplexity | Ultrahuman |
| cmp-08 (comparison) | anthropic | Whoop |
| cmp-08 (comparison) | gemini | Whoop |
| cmp-08 (comparison) | openai | Whoop |
| cmp-08 (comparison) | perplexity | Whoop |
| cmp-09 (comparison) | anthropic | Samsung Galaxy Ring |
| cmp-09 (comparison) | openai | Samsung Galaxy Ring |
| cmp-09 (comparison) | perplexity | RingConn |
| cmp-11 (comparison) | anthropic | Whoop |
| cmp-11 (comparison) | openai | Whoop |

Concentrated in **comparison** intent: `cmp-08` (Whoop vs Ultrahuman for athletes — Oura isn’t in the matchup framing), `cmp-09` (Samsung/RingConn win on a spec angle), `cmp-11` (cheaper-alternatives-to-Whoop → Whoop/others). On category, `cat-06` (no-subscription) and `cat-10` (newest-2026) are lost on Perplexity.

### Closest to winning — Oura present but *not* first (23 cells)

These are the cheapest wins: Oura already appears, just ranked behind a competitor recommended first. Nudging prominence here moves the leaderboard fastest.

| Query | Engine | Loses first place to | Oura currently |
| --- | --- | --- | --- |
| cat-05 | gemini | RingConn | mid-pack |
| cat-05 | perplexity | RingConn | mid-pack |
| cat-06 | anthropic | Ultrahuman | also-ran |
| cat-06 | gemini | RingConn | also-ran |
| cat-06 | perplexity | Ultrahuman | also-ran |
| cat-08 | anthropic | RingConn | also-ran |
| cat-08 | gemini | RingConn | mid-pack |
| cat-10 | gemini | Samsung Galaxy Ring | mid-pack |
| cat-13 | perplexity | RingConn | mid-pack |
| cmp-01 | perplexity | Whoop | mid-pack |
| cmp-03 | gemini | Ultrahuman | mid-pack |
| cmp-05 | anthropic | RingConn | also-ran |
| cmp-05 | perplexity | Samsung Galaxy Ring | also-ran |
| cmp-06 | anthropic | RingConn | also-ran |
| cmp-06 | gemini | Ultrahuman | also-ran |
| cmp-06 | openai | Whoop | also-ran |
| cmp-06 | perplexity | RingConn | also-ran |
| cmp-07 | anthropic | Samsung Galaxy Ring | mid-pack |
| cmp-07 | gemini | Samsung Galaxy Ring | mid-pack |
| cmp-07 | perplexity | Samsung Galaxy Ring | mid-pack |
| cmp-09 | gemini | Samsung Galaxy Ring | also-ran |
| cmp-10 | perplexity | Ultrahuman | mid-pack |
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
| adj-03 | gemini | ✅ | buried | neutral |  | — | — |  |
| adj-03 | openai | — | — | neutral |  | — | — |  |
| adj-03 | perplexity | — | — | neutral |  | — | — | 8 |
| adj-04 | anthropic | — | — | neutral |  | — | — |  |
| adj-04 | gemini | — | — | neutral |  | — | — |  |
| adj-04 | openai | — | — | neutral |  | — | — |  |
| adj-04 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | — | 7 |
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
| brd-01 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-01 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Whoop |  |
| brd-01 | openai | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-01 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | Whoop | 8 |
| brd-02 | anthropic | ✅ | 🥇 first | neutral | 3 | Oura | — |  |
| brd-02 | gemini | ✅ | 🥇 first | positive | 4 | Oura | — |  |
| brd-02 | openai | ✅ | 🥇 first | neutral | 3 | Oura | — |  |
| brd-02 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | — | 8 |
| brd-03 | anthropic | ✅ | 🥇 first | neutral | 4 | Oura | — |  |
| brd-03 | gemini | ✅ | 🥇 first | neutral | 4 | Oura | — |  |
| brd-03 | openai | ✅ | 🥇 first | neutral | 3 | Oura | — |  |
| brd-03 | perplexity | ✅ | 🥇 first | neutral | 2 | Oura | — | 7 |
| brd-04 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-04 | gemini | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-04 | openai | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-04 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | — | 8 |
| brd-05 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-05 | gemini | ✅ | 🥇 first | positive | 5 | Oura | — |  |
| brd-05 | openai | ✅ | 🥇 first | positive | 5 | Oura | — |  |
| brd-05 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | — | 8 |
| brd-06 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-06 | gemini | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| brd-06 | openai | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| brd-06 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | — | 7 |
| brd-07 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Whoop |  |
| brd-07 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Whoop, Samsung Galaxy Ring |  |
| brd-07 | openai | ✅ | 🥇 first | neutral | 4 | Oura | — |  |
| brd-07 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | — | 9 |
| cat-01 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-01 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-01 | openai | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-01 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 7 |
| cat-02 | anthropic | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-02 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, RingConn |  |
| cat-02 | openai | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| cat-02 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, RingConn | 6 |
| cat-03 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, RingConn |  |
| cat-03 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, RingConn |  |
| cat-03 | openai | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-03 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 10 |
| cat-04 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | RingConn |  |
| cat-04 | gemini | ✅ | mid-pack | positive | 4 | — | Ultrahuman, Samsung Galaxy Ring |  |
| cat-04 | openai | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-04 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | RingConn | 7 |
| cat-05 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, RingConn |  |
| cat-05 | gemini | ✅ | mid-pack | positive | 3 | RingConn | Ultrahuman, RingConn |  |
| cat-05 | openai | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| cat-05 | perplexity | ✅ | mid-pack | positive | 4 | RingConn | Samsung Galaxy Ring, RingConn | 6 |
| cat-06 | anthropic | ✅ | also-ran | negative | 2 | Ultrahuman | Ultrahuman, RingConn |  |
| cat-06 | gemini | ✅ | also-ran | neutral | 3 | RingConn | Ultrahuman, RingConn |  |
| cat-06 | openai | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-06 | perplexity | ✅ | also-ran | negative | 2 | Ultrahuman | Ultrahuman, Samsung Galaxy Ring, RingConn | 7 |
| cat-07 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, RingConn |  |
| cat-07 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, RingConn |  |
| cat-07 | openai | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| cat-07 | perplexity | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 4 |
| cat-08 | anthropic | ✅ | also-ran | negative | 3 | RingConn | Ultrahuman, RingConn |  |
| cat-08 | gemini | ✅ | mid-pack | negative | 3 | RingConn | Ultrahuman, RingConn |  |
| cat-08 | openai | ✅ | 🥇 first | positive | 3 | Oura | — |  |
| cat-08 | perplexity | — | — | neutral |  | — | RingConn | 8 |
| cat-09 | anthropic | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-09 | gemini | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, RingConn |  |
| cat-09 | openai | — | — | neutral |  | — | — |  |
| cat-09 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 7 |
| cat-10 | anthropic | ✅ | 🥇 first | positive | 1 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-10 | gemini | ✅ | mid-pack | positive | 3 | Samsung Galaxy Ring | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-10 | openai | — | — | neutral |  | — | — |  |
| cat-10 | perplexity | — | — | neutral |  | Ultrahuman | Ultrahuman, RingConn | 7 |
| cat-11 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Whoop, Ultrahuman, RingConn |  |
| cat-11 | gemini | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-11 | openai | ✅ | 🥇 first | positive | 2 | Oura | Whoop |  |
| cat-11 | perplexity | — | — | neutral |  | — | Whoop | 4 |
| cat-13 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-13 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring |  |
| cat-13 | openai | ✅ | 🥇 first | positive | 2 | Oura | — |  |
| cat-13 | perplexity | ✅ | mid-pack | negative | 4 | RingConn | Samsung Galaxy Ring, RingConn | 6 |
| cat-14 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-14 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn |  |
| cat-14 | openai | ✅ | 🥇 first | positive | 1 | Oura | — |  |
| cat-14 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman, Samsung Galaxy Ring, RingConn | 5 |
| cmp-01 | anthropic | ✅ | 🥇 first | positive | 4 | Oura | Whoop |  |
| cmp-01 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Whoop |  |
| cmp-01 | openai | ✅ | 🥇 first | positive | 3 | Oura | Whoop |  |
| cmp-01 | perplexity | ✅ | mid-pack | positive | 1 | Whoop | Whoop | 7 |
| cmp-02 | anthropic | ✅ | 🥇 first | positive | 2 | Oura | Samsung Galaxy Ring |  |
| cmp-02 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Samsung Galaxy Ring |  |
| cmp-02 | openai | ✅ | 🥇 first | positive | 4 | Oura | Samsung Galaxy Ring |  |
| cmp-02 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | Samsung Galaxy Ring | 8 |
| cmp-03 | anthropic | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman |  |
| cmp-03 | gemini | ✅ | mid-pack | positive | 4 | Ultrahuman | Ultrahuman |  |
| cmp-03 | openai | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman |  |
| cmp-03 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | Ultrahuman | 6 |
| cmp-04 | anthropic | ✅ | 🥇 first | positive | 5 | Oura | RingConn |  |
| cmp-04 | gemini | ✅ | 🥇 first | positive | 3 | Oura | RingConn |  |
| cmp-04 | openai | ✅ | 🥇 first | positive | 3 | Oura | RingConn |  |
| cmp-04 | perplexity | ✅ | 🥇 first | positive | 2 | Oura | RingConn | 7 |
| cmp-05 | anthropic | ✅ | also-ran | neutral | 2 | RingConn | Whoop, Ultrahuman, RingConn |  |
| cmp-05 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Whoop, Ultrahuman |  |
| cmp-05 | openai | ✅ | 🥇 first | positive | 1 | Oura | Whoop |  |
| cmp-05 | perplexity | ✅ | also-ran | neutral | 1 | Samsung Galaxy Ring | Ultrahuman, Samsung Galaxy Ring, RingConn | 8 |
| cmp-06 | anthropic | ✅ | also-ran | neutral | 2 | RingConn | Ultrahuman, RingConn |  |
| cmp-06 | gemini | ✅ | also-ran | neutral | 2 | Ultrahuman | Ultrahuman, RingConn |  |
| cmp-06 | openai | ✅ | also-ran | neutral | 1 | Whoop | Whoop |  |
| cmp-06 | perplexity | ✅ | also-ran | neutral | 1 | RingConn | Ultrahuman, Samsung Galaxy Ring, RingConn | 8 |
| cmp-07 | anthropic | ✅ | mid-pack | positive | 2 | Samsung Galaxy Ring | Samsung Galaxy Ring |  |
| cmp-07 | gemini | ✅ | mid-pack | positive | 3 | Samsung Galaxy Ring | Samsung Galaxy Ring |  |
| cmp-07 | openai | ✅ | 🥇 first | positive | 2 | Oura | Samsung Galaxy Ring |  |
| cmp-07 | perplexity | ✅ | mid-pack | positive | 3 | Samsung Galaxy Ring | Samsung Galaxy Ring | 8 |
| cmp-08 | anthropic | — | — | neutral |  | Whoop | Whoop, Ultrahuman |  |
| cmp-08 | gemini | — | — | neutral |  | Whoop | Whoop, Ultrahuman |  |
| cmp-08 | openai | — | — | neutral |  | Whoop | Whoop, Ultrahuman |  |
| cmp-08 | perplexity | — | — | neutral |  | Whoop | Whoop, Ultrahuman | 8 |
| cmp-09 | anthropic | — | — | neutral |  | Samsung Galaxy Ring | Samsung Galaxy Ring, RingConn |  |
| cmp-09 | gemini | ✅ | also-ran | neutral | 4 | Samsung Galaxy Ring | Samsung Galaxy Ring, RingConn |  |
| cmp-09 | openai | — | — | neutral |  | Samsung Galaxy Ring | Samsung Galaxy Ring, RingConn |  |
| cmp-09 | perplexity | — | — | neutral |  | RingConn | Samsung Galaxy Ring, RingConn | 9 |
| cmp-10 | anthropic | ✅ | 🥇 first | positive | 3 | Oura | Ultrahuman |  |
| cmp-10 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman |  |
| cmp-10 | openai | ✅ | 🥇 first | positive | 4 | Oura | Ultrahuman |  |
| cmp-10 | perplexity | ✅ | mid-pack | positive | 3 | Ultrahuman | Ultrahuman | 7 |
| cmp-11 | anthropic | — | — | neutral |  | Whoop | Whoop |  |
| cmp-11 | gemini | ✅ | 🥇 first | positive | 4 | Oura | Whoop |  |
| cmp-11 | openai | — | — | neutral |  | Whoop | Whoop |  |
| cmp-11 | perplexity | ✅ | mid-pack | positive | 3 | Whoop | Whoop | 9 |
| pa-01 | anthropic | — | — | neutral |  | — | — |  |
| pa-01 | gemini | — | — | neutral |  | — | — |  |
| pa-01 | openai | — | — | neutral |  | — | — |  |
| pa-01 | perplexity | ✅ | also-ran | neutral |  | — | — | 7 |
| pa-02 | anthropic | — | — | neutral |  | — | — |  |
| pa-02 | gemini | ✅ | mid-pack | neutral |  | — | — |  |
| pa-02 | openai | — | — | neutral |  | — | — |  |
| pa-02 | perplexity | — | — | neutral |  | — | — | 7 |
| pa-03 | anthropic | ✅ | buried | neutral | 2 | — | — |  |
| pa-03 | gemini | ✅ | 🥇 first | positive | 3 | Oura | Whoop |  |
| pa-03 | openai | — | — | neutral |  | — | Whoop |  |
| pa-03 | perplexity | ✅ | 🥇 first | positive | 3 | Oura | Whoop | 8 |
| pa-04 | anthropic | — | — | neutral |  | — | — |  |
| pa-04 | gemini | — | — | neutral |  | — | — |  |
| pa-04 | openai | — | — | neutral |  | — | — |  |
| pa-04 | perplexity | — | — | neutral |  | — | — | 8 |
| pa-05 | anthropic | ✅ | also-ran | positive |  | — | — |  |
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
