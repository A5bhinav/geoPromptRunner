# Albert Nahman Plumbing — Gold-Set Labeling Sheet

25 answers to label. Work down the file; items are **grouped by question**, so you read all four engines' answers to one query together and judge them consistently.

Edit only the cells inside the `<!-- LABELS -->` markers — leave the markers alone, they are how the sheet is read back. Pipe alignment does not matter; `|Acme|yes|mid_pack|positive|` parses fine.

When you are done:

```bash
python -m scripts.parse_labeling_sheet SHEET.md GOLD.json          # validate
python -m scripts.parse_labeling_sheet SHEET.md GOLD.json --write  # apply
```

It validates every value and refuses to write if anything is off, so a typo costs you a re-run and never a corrupted set.

## The three columns

| column | values | what it means |
| --- | --- | --- |
| `present` | `yes` · `no` | Is the brand named at all? A **disavowal** — "there is no such company", "I have no information about them" — is `no`. The name appearing only because the question contained it is also `no`. |
| `prominence` | `recommended_first` · `mid_pack` · `buried` · `also_ran` · `absent` | Relative *within this answer*: who is named first vs. buried at the bottom. Must be `absent` when `present=no`, and must not be when `present=yes`. |
| `framing` | `positive` · `neutral` · `negative` | How the answer treats it. Absent brands stay `neutral`. |

## The flags block

Real errors the answer makes **about Albert Nahman Plumbing only** — never about a competitor. One per line, `type | severity | note`. Leave it empty when the answer is accurate.

- **types** — `wrong_pricing` · `missing_or_invented_feature` · `competitor_confusion` · `identity` · `stale` · `wrong_hours` · `wrong_service_area` · `wrong_contact` · `licensing`
- **severity** — `high` · `med` · `low`

A flag needs a line in the fact sheet below that the answer **contradicts**. If the sheet is silent on the topic, that is not a flag — put it in **uncovered claims** instead, which is the list of things the judge must *not* flag.

<details><summary><b>Ground truth — the Albert Nahman Plumbing fact sheet</b> (open this before writing any flag)</summary>

# Client Fact Sheet (LOCAL SERVICE) — Albert Nahman Plumbing

> **Meta**
> - Domain: albertnahmanplumbing.com
> - Business kind: local_service · Status: draft · Version: 1
> - Generated: 2026-07-31T20:00:00+00:00 · Weakest verification: public_source_only
> - Claims: 10 · Open questions: 3

**10 of 10 claims are NOT client-confirmed.** A signature covers only the lines the owner vouched for; a line marked UNCONFIRMED may not be cited as the correct fact from a signed sheet (plan §8).

---

## A · Identity & basics

- **identity_name:** Albert Nahman Plumbing, Heating, and Cooling. — **UNCONFIRMED** — one public source [`FS-01`]
- **identity_website:** albertnahmanplumbing.com — **UNCONFIRMED** — one public source [`FS-02`]

## B · Contact & location → `wrong_contact`

- **contact_phone:** The published phone number is (510) 408-7879. — **UNCONFIRMED** — one public source [`FS-03`]
- **contact_address_berkeley:** The Berkeley office is at 3333 Martin Luther King Jr. Way, Berkeley, CA 94703. — **UNCONFIRMED** — one public source [`FS-04`]
- **contact_address_hayward:** A second office is at 2616 Barrington Court, Hayward, CA 94545, which is also the mailing address. — **UNCONFIRMED** — one public source [`FS-05`]
- **contact_offices:** There are two offices: Berkeley and Hayward. No other location is claimed. — **UNCONFIRMED** — one public source [`FS-06`]

## C · Hours & availability → `wrong_hours`

- **hours_answering:** The site advertises 24/7 live phone answering. This is ANSWERING, not a claim that technicians are dispatched or that an office is open 24 hours. — **UNCONFIRMED** — one public source [`FS-07`]

## D · Service area → `wrong_service_area`

- **service_area_primary:** Berkeley, California. — **UNCONFIRMED** — one public source [`FS-08`]

## E · Licensing, insurance & credentials → `licensing`

- **licensing_number:** California contractor license #1083634, as published on the site. — **UNCONFIRMED** — one public source [`FS-09`]
- **licensing_ownership:** Locally owned and operated. — **UNCONFIRMED** — one public source [`FS-10`]

---

## Open questions

*Sources disagreed, or the answer cannot be derived from a closed enumeration. Nothing below is a fact yet — ask, then add (§4.3, §4.4).*

1. OPENING HOURS ARE NOT PUBLISHED ANYWHERE ON THE SITE. The site advertises '24/7 Live Answering' (answering, not dispatch) and no day/time table exists. Ask the owner for real service hours and whether 24/7 dispatch is genuinely offered — until then NO hours claim may be added, and an answer stating specific opening hours is unverifiable rather than wrong.
2. A second phone number, (510) 295-0534, appears on some service pages while the homepage, the contact page and the footer all publish (510) 408-7879. Is 295-0534 a live line, a call-tracking number, or stale? (plan §4.3 — recorded, not chosen)
3. The service-area page lists many towns beyond Berkeley and Hayward. Confirm the real dispatch radius before any wrong_service_area flag can be graded.

---

## Provenance appendix

*Every line above, with the source text it was taken from. A claim whose quote is not a literal substring of its source never ships (§4.1).*

| claim_id | quote | source_url | as_of | verification |
|---|---|---|---|---|
| FS-01 | Albert Nahman Plumbing, Heating, and Cooling | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-02 | albertnahmanplumbing.com | urn:geo:lead-form | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-03 | (510) 408-7879 | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-04 | 3333 Martin Luther King Jr. Way Berkeley, CA 94703 | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-05 | 2616 Barrington Court Hayward, CA 94545 | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-06 | With 2 offices around the region | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-07 | 24/7 Live Answering | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-08 | Berkeley, California | urn:geo:lead-form | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-09 | License: #1083634 | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |
| FS-10 | Locally Owned & Operated | https://albertnahmanplumbing.com/contact/ | 2026-07-31 | public_source_only (UNCONFIRMED) |

</details>

## What you are labeling

| question | items | engines |
| --- | --- | --- |
| is Albert Nahman Plumbing a good plumbing company? | 0, 1, 2, 3 | gemini_grounded, google_ai_mode, openai, perplexity |
| Albert Nahman Plumbing reviews and complaints | 4, 5, 6, 7 | gemini_grounded, google_ai_mode, openai, perplexity |
| is Albert Nahman Plumbing licensed and insured? | 8, 9, 10, 11 | gemini_grounded, google_ai_mode, openai, perplexity |
| how much does a plumber cost in Berkeley? | 12, 13, 14, 15 | gemini_grounded, google_ai_mode, openai, perplexity |
| why is my water pressure suddenly low? | 16, 17 | openai, perplexity |
| best plumber in Berkeley | 18, 19 | gemini_grounded, google_ai_mode |
| who is the most reliable plumber in Berkeley? | 20, 21 | gemini_grounded, google_ai_mode |
| emergency plumber in Berkeley | 22 | google_ai_mode |
| 24 hour plumbing service Berkeley | 23 | google_ai_mode |
| top rated drain cleaning in Berkeley | 24 | perplexity |

---

# Question: is Albert Nahman Plumbing a good plumbing company?

## Item 0 · `gemini_grounded`

> is Albert Nahman Plumbing a good plumbing company?

*answer 1 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — 4×, first at **0%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Albert Nahman Plumbing, Heating, and Cooling generally receives a mixed but often positive reception from customers, with a significant number of reviews highlighting professionalism and quality work, while some express concerns regarding pricing and service contracts. The company has been in business since 1981, serving Berkeley, CA, and surrounding areas.

Here's a summary of what makes Albert Nahman Plumbing a good plumbing company, along with some areas where customers have reported issues:

**Positive Aspects:**
*   **High Overall Ratings:** Albert Nahman Plumbing, Heating, and Cooling holds an overall rating of 4.6 out of 5 on Angie's List and is Diamond Certified with a 4.7 average star score from 622 verified customer phone survey responses, indicating "Highest in Quality and Helpful Expertise." They also have an A+ rating with the Better Business Bureau (BBB).
*   **Professional and Courteous Technicians:** Many customers praise technicians for being polite, professional, friendly, and respectful. Reviewers frequently mention that technicians explain problems thoroughly and offer options for fixes.
*   **Effective Problem Diagnosis and Repair:** Customers have reported satisfaction with the company's ability to diagnose and fix complex plumbing issues, such as water leaks and drain clogs.
*   **Punctuality and Efficiency:** Several reviews commend the company for arriving on time and completing work efficiently.
*   **Cleanliness:** Technicians are often noted for doing a great job cleaning up after their work.
*   **Responsiveness:** The company has been praised for responding immediately and completing projects promptly.

**Areas for Consideration:**
*   **Pricing:** Some customers have reported that the estimated costs for repairs were significantly higher than the actual cost or what other plumbers quoted. There are mentions of high charges for parts and labor, with one customer noting a charge of $1100 for about an hour and ten minutes of work.
*   **Service Contracts and Honoring Promises:** One customer had a negative experience with a service contract, stating the company failed to honor it and did not send a technician on a promised day.
*   **Communication and Management:** While many praise individual technicians, some reviews mention issues with communication, particularly after installation, and difficulties reaching management to resolve problems.
*   **Inconsistent Experiences:** A few reviews describe "odd experiences" or express a loss of trust, particularly after the company was reportedly acquired by a larger national company, suggesting a potential change in service quality for some.
*   **Heat Pump Installation Issues:** One customer reported a disastrous heat pump installation with an ongoing buzzing sound and unaddressed issues despite repeated attempts to contact the company.

In conclusion, Albert Nahman Plumbing, Heating, and Cooling appears to be a reputable company with a long history and a strong focus on customer service and quality work, as evidenced by numerous positive reviews and high ratings from independent certification bodies. However, potential customers should be mindful of getting multiple quotes for larger jobs and thoroughly understanding service contract terms, as some past customers have raised concerns about pricing and follow-through on service agreements.
```

</details>

<!-- LABELS item=0 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=0 -->

---

## Item 1 · `google_ai_mode`

> is Albert Nahman Plumbing a good plumbing company?

*answer 2 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — 2×, first at **8%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Based on numerous, high-rating reviews on platforms like [Yelp](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4), Google , and [Angi](https://www.angi.com/companylist/us/ca/berkeley/albert-nahman-plumbing%2C-heating%2C-and-cooling-reviews-176247.htm) , Albert Nahman Plumbing, Heating, and Cooling is generally considered a **reputable, high-quality, and reliable** plumbing service provider in the San Francisco Bay Area, particularly in the East Bay. They are known for being professional, prompt, and experienced in a wide range of services, including emergency repairs and installations.[](https://www.homeadvisor.com/rated.AlbertNahman.140734115.html) [[1]](https://www.homeadvisor.com/rated.AlbertNahman.140734115.html)[[2]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVhaeE0xOW9kbWhyGAo)[[3]](https://bestplumbers.com/california/berkeley/plumbing-services/albert-nahman-plumbing)[[4]](https://albertnahmanplumbing.com/plumber-in-san-francisco-ca/)[[5]](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-hayward)

**Key Takeaways:** 

- **High Ratings:** The company often receives high praise for its professionalism, punctuality, and the quality of its work.[](https://www.homeadvisor.com/rated.AlbertNahman.140734115.html) [[1]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)
- **Reputation:** With over 40 years of service, they have built a strong, well-established reputation as a reliable and professional plumbing, heating, and cooling company, sometimes called "The Peace of Mind Folks".[](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/) [[1]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)[[2]](https://albertnahmanplumbing.com/about-us/)
- **Services:** They offer a full range of services including plumbing repairs, drain cleaning, water heater installation (including tankless), HVAC services, and more.[](https://www.homeadvisor.com/rated.AlbertNahman.140734115.html) 
- **Experience:** They have a highly experienced team, with many employees having been with the company for over 20 years.[](https://albertnahmanplumbing.com/about-us/) 

**Considerations:** 

- **Cost:** Some reviews have noted that their services can be more expensive compared to other options, although this often comes with high-quality service and warranties.[](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4) [[1]](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4)[[2]](https://www.reddit.com/r/eastbay/comments/1fu7n45/reputablepreferred_plumbers/)
- **Customer Experience:** While the vast majority of reviews are positive, there are some mixed reviews regarding the "process" and potential upselling of services, particularly for those without a service membership.[](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4) 

**Conclusion:**   
For many, Albert Nahman Plumbing is a preferred choice due to their reliability and expertise. They are often described as professional, knowledgeable, and reliable, making them a good option for those looking for quality work, especially if they are willing to pay a bit more for that, according to some.[[1]](https://albertnahmanplumbing.com/commercial/hvac/)[[2]](https://albertnahmanplumbing.com/about-us/)

Would you like me to find out about their specific **pricing for a common job** like a water heater installation, or perhaps their **current, available discounts**?
```

</details>

<!-- LABELS item=1 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=1 -->

---

## Item 2 · `openai`

> is Albert Nahman Plumbing a good plumbing company?

*answer 3 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **0%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Albert Nahman Plumbing is generally considered a reputable, established plumbing company in the East Bay/Berkeley–Oakland area. They’re known for offering plumbing, sewer, drain, and HVAC services, and many customers value their professionalism and responsiveness.

That said, customer experiences can vary—especially regarding **pricing**, since larger, established service companies may charge more than an independent plumber. Before hiring them, I’d recommend:

- Get a written estimate, including labor, parts, permits, and possible additional charges.
- Ask whether the diagnostic fee is credited toward the repair.
- Compare with one or two licensed local plumbers.
- Check recent Google/Yelp reviews for your specific location and service.
- Verify their current California contractor license and insurance.

**Bottom line:** They’re likely a reasonable choice if you prioritize a well-established company and clear service processes, but compare estimates if cost is important.
```

</details>

<!-- LABELS item=2 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=2 -->

---

## Item 3 · `perplexity`

> is Albert Nahman Plumbing a good plumbing company?

*answer 4 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **1%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
**Overall, Albert Nahman Plumbing appears to be a generally good plumbing company, but it is not uniformly rated as excellent.** Most major review sources show strong customer satisfaction, while a smaller number of sources and individual reviews raise concerns about *price* and occasional service/communication issues.[1][2][5][7][9][10]

- On Yelp, the Berkeley location shows **3.3/5 from 718 reviews**, which is mixed rather than outstanding.[1]
- On BirdEye, it shows **4.7/5 from 3,309 reviews**, and other platforms also show strong scores, including **4.6/5 on Angi** and **4.8/5** in Directorii’s listed reviews.[2][7][10]
- BBB lists the business with an **A+ rating**, but its customer review rating is only **3.21/5 from 19 reviews**, showing a gap between accreditation and customer sentiment.[9][3]
- HomeAdvisor reports **87% recommended**, which also points to generally favorable customer experience.[5]

What the reviews suggest:
- **Strengths:** professionalism, responsiveness, punctuality, and clean work are mentioned repeatedly.[8][9][4]
- **Common complaint:** several sources mention that the company can be **expensive** or that labor/pricing felt high.[4][6][3]
- **Occasional negatives:** a minority of reviews mention service or communication problems.[10][3]

If you want, I can also help you judge whether they’re a good fit for your specific job by comparing them with other local plumbers or by checking recent complaint patterns.
```

</details>

<!-- LABELS item=3 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=3 -->

---

# Question: Albert Nahman Plumbing reviews and complaints

## Item 4 · `gemini_grounded`

> Albert Nahman Plumbing reviews and complaints

*answer 1 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — 2×, first at **0%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Albert Nahman Plumbing, Heating, and Cooling receives a mixed range of reviews and complaints, with customers reporting both highly positive experiences and significant issues. The company is BBB accredited with an A+ rating and holds a Diamond Certified status, indicating a commitment to customer service and quality.

**Positive Reviews:**
Many customers praise Albert Nahman Plumbing for their professionalism, prompt service, and effective problem diagnosis. Several technicians, including Josue Hernandez, Jaleen, Fernando, Cole, James, Angel, and Charles, have been specifically commended for their courteousness, expertise, and thorough work. Customers appreciate that technicians often explain the issues and potential fixes clearly, arrive on time, and clean up thoroughly after completing the job. The company also offers warranties on new installations and certain repairs.

**Complaints:**
Despite positive feedback, a notable number of complaints highlight concerns about pricing and service quality. Some customers report being significantly overcharged, with estimates sometimes being much higher than the actual cost of the repair. There are accusations of taking advantage of elderly customers by charging exorbitant fees.

Other common complaints include incomplete work, poor communication, and extended delays. Some customers have experienced situations where management failed to return calls or honor service contracts. There are also instances where customers felt the work was incompetent, leading to the situation worsening or requiring further repairs shortly after the initial service. A few reviews suggest that the company's service quality has declined since its acquisition by a larger national entity.
```

</details>

<!-- LABELS item=4 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=4 -->

---

## Item 5 · `google_ai_mode`

> Albert Nahman Plumbing reviews and complaints

*answer 2 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **0%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Albert Nahman Plumbing, Heating, and Cooling , based in Berkeley and Hayward, CA, has a mixed reputation, with a high volume of reviews often citing professional, timely service alongside significant complaints regarding high costs and aggressive upselling tactics.[[1]](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4)[[2]](https://albertnahmanplumbing.com/hvac/)[[3]](https://albertnahmanplumbing.com/about-us/)

**Overall Sentiment and Reputation** 

- **Mixed Reviews:** While some customers praise the company as "prompt" and "professional," others describe it as a "bait-and-switch" operation that "takes advantage" of customers.[](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4) [[1]](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4)[[2]](https://directorii.com/us/ca/berkeley/albert-nahman-plumbing-heating-and-cooling-berkeley-reviews-10116/)[[3]](https://www.bbb.org/us/ca/hayward/profile/plumber/albert-nahman-plumbing-heating-and-cooling-1116-28226/customer-reviews?page=2)[[4]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)[[5]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)
- **High Costs:** A common complaint among negative reviews is that the company is "corrupt" and charges far more than other plumbing services.[](https://www.angi.com/companylist/us/ca/berkeley/albert-nahman-plumbing%2C-heating%2C-and-cooling-reviews-176247.htm) [[1]](https://www.angi.com/companylist/us/ca/berkeley/albert-nahman-plumbing%2C-heating%2C-and-cooling-reviews-176247.htm)[[2]](https://www.reddit.com/r/eastbay/comments/1fu7n45/reputablepreferred_plumbers/)
- **Mixed Feedback Loop:** The company is often described as having "two faces," where some technicians are highly rated, while others are seen as unprofessional or overly focused on selling extras.[](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4) [[1]](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4?start=10)[[2]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)[[3]](https://directorii.com/us/ca/berkeley/albert-nahman-plumbing-heating-and-cooling-berkeley-reviews-10116/)

**Common Complaints** 

- **Aggressive Upselling:** Numerous reviewers complained that standard service calls were used as opportunities for technicians to try to sell expensive, unnecessary filters and improvement systems.[](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-berkeley-4) 
- **Poor Post-Installation Service:** Complaints indicate that while the company is prompt to sell maintenance contracts, they have failed to honor them, with customers noting a lack of follow-through on promised service.[](https://www.angi.com/companylist/us/ca/berkeley/albert-nahman-plumbing%2C-heating%2C-and-cooling-reviews-176247.htm) 
- **Damaged Property/Poor Workmanship:** Some customers reported that the company broke pipes, toilets, or irrigation systems during repairs and then tried to charge more to fix their own mistakes.[](https://www.bbb.org/us/ca/hayward/profile/plumber/albert-nahman-plumbing-heating-and-cooling-1116-28226/customer-reviews?page=2) 
- **Communication Issues:** Several reviewers mentioned poor communication and high turnover of staff.[](https://www.bbb.org/us/ca/hayward/profile/plumber/albert-nahman-plumbing-heating-and-cooling-1116-28226/customer-reviews?page=2) [[1]](https://directorii.com/us/ca/berkeley/albert-nahman-plumbing-heating-and-cooling-berkeley-reviews-10116/)[[2]](https://m.yelp.com/biz/albert-nahman-plumbing-heating-and-cooling-hayward)

**Positive Reviews** 

- **Promptness and Professionalism:** Several customers described the team as "incredibly responsible" and "prompt," often noting that the technicians were well-trained in customer service.
- **Effective Problem Solving:** Some users noted that the company successfully diagnosed and fixed complex issues.
- **Knowledgeable Technicians:** Some specific technicians were singled out for being "patient" and explaining the costs clearly.[](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/) [[1]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)

**Key Details** 

- **Service Area:** Serves the East Bay, including Berkeley, Hayward, Walnut Creek, and Oakland.
- **Specials:** The company frequently offers promotions, such as "$25 off any plumbing, heating or cooling service".
- **Warranty:** They claim a 5-year warranty on new installations, 2 years on repairs, and 20 years on complete copper repiping.[](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/) [[1]](https://albertnahmanplumbing.com/)[[2]](http://albertnahmanplumbing.com/service-areas/walnut-creek/)[[3]](https://www.bbb.org/us/ca/hayward/profile/plumber/albert-nahman-plumbing-heating-and-cooling-1116-28226)

Would you like me to find **specific reviews** for a particular service, such as **HVAC repair** or **water heater installation**?
```

</details>

<!-- LABELS item=5 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=5 -->

---

## Item 6 · `openai`

> Albert Nahman Plumbing reviews and complaints

*answer 3 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **0%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Albert Nahman Plumbing, Heating & Drain Cleaning is a long-established Berkeley/East Bay plumbing company. I don’t have live access to current review databases, so I can’t reliably quote today’s ratings or complaint counts.

For the most useful current picture, check:

- **Google Reviews** – overall rating, recent service experiences, response to negative reviews  
- **Yelp** – often more detailed narratives, though ratings can be polarized  
- **BBB** – complaint history, business responses, and accreditation status  
- **California Contractors State License Board** – license status and any formal disciplinary records  
- **Angi/HomeAdvisor** – estimates, punctuality, workmanship, and warranty feedback  

When reviewing complaints, pay particular attention to repeated reports involving:

- Unexpected charges or estimates changing after work begins  
- Delays, missed appointments, or poor communication  
- Incomplete cleanup or damage to property  
- Warranty or callback problems  
- Whether the company responds constructively and resolves issues  

A few isolated negative reviews are normal for a busy service contractor; repeated, recent complaints with similar details are more significant. Before hiring, get a written estimate, ask whether diagnostic or emergency fees apply, confirm warranty terms, and verify the plumber’s California license and insurance.

If you share the review links or the specific complaint you’re concerned about, I can help assess whether it appears credible and how serious it is.
```

</details>

<!-- LABELS item=6 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=6 -->

---

## Item 7 · `perplexity`

> Albert Nahman Plumbing reviews and complaints

*answer 4 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **0%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Albert Nahman Plumbing appears to have a **strong overall rating** but also a recurring set of complaints, especially around **high pricing**, **communication problems**, and a few reports of **damage or incomplete work**.[2][5][6][9][10]

- On BBB, the company has **15 complaints in the last 3 years** and **8 complaints closed in the last 12 months**.[1]
- BBB customer reviews show an average of **3.21/5 stars from 19 reviews**, which is notably lower than some other review platforms.[2]
- Angi lists the company at **4.6/5 overall**, based on a much larger set of reviews, suggesting many customers are satisfied.[9][15]
- BirdEye shows a **4.7-star rating with 3,309 reviews**, and HomeAdvisor says there are **2,700+ Google reviews at 4.8 stars**, indicating generally positive volume overall.[5][3]

Common complaint themes across the results:
- **Overpricing / high labor costs**: multiple reviewers said the work was “very expensive” or “overpriced.”[4][6][7]
- **Poor communication or follow-through**: some complaints mention delayed responses, incomplete jobs, or trouble getting problems resolved.[6][10]
- **Alleged workmanship issues**: a few reviews describe damaged pipes, unresolved leaks, or work that required expensive follow-up repairs.[2][3][13]
- **Customer service frustration**: some reviewers praised the technicians but still criticized the company’s handling of billing or service recovery.[4][6]

Overall, the pattern is: **many customers rate them highly, but the negative reviews consistently cluster around cost and communication rather than simple service quality**.[2][6][9][10] If you want, I can also turn this into a **pros/cons summary** or compare Albert Nahman against a few other Bay Area plumbing companies.
```

</details>

<!-- LABELS item=7 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=7 -->

---

# Question: is Albert Nahman Plumbing licensed and insured?

## Item 8 · `gemini_grounded`

> is Albert Nahman Plumbing licensed and insured?

*answer 1 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — 2×, first at **1%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Yes, Albert Nahman Plumbing, Heating and Cooling is licensed and insured. The company holds an active license number 1083634, issued by the Contractors State License Board, which is valid until January 31, 2027.

Additionally, Albert Nahman Plumbing, Heating and Cooling is insured, carrying both liability insurance and workers' compensation.

It is important to note that while an older license number, 414359, is listed as expired and not able to contract, the company operates under the active license 1083634.
```

</details>

<!-- LABELS item=8 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=8 -->

---

## Item 9 · `google_ai_mode`

> is Albert Nahman Plumbing licensed and insured?

*answer 2 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **0%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Yes, Albert Nahman Plumbing, Heating, and Cooling is **licensed and insured** . They are a long-standing, established company in the Bay Area (since 1981) that provides plumbing and HVAC services.[](https://albertnahmanplumbing.com/plumber-in-richmond-ca/) [[1]](https://albertnahmanplumbing.com/plumber-in-richmond-ca/)[[2]](https://www.angi.com/companylist/us/ca/berkeley/albert-nahman-plumbing%2C-heating%2C-and-cooling-reviews-176247.htm)[[3]](https://albertnahmanplumbing.com/)[[4]](https://www.bbb.org/us/ca/hayward/profile/plumber/albert-nahman-plumbing-heating-and-cooling-1116-28226)

Here are the details:

- **Licensing:** They hold contractor licenses for plumbing and HVAC services, with records indicating active, insured status.
- **Insurance:** They carry both liability insurance and workers' compensation, ensuring protection for both customers and their staff.
- **Credentials:** They are [BBB Accredited](https://www.bbb.org/us/ca/hayward/profile/plumber/albert-nahman-plumbing-heating-and-cooling-1116-28226) with an A+ rating and are listed as [Diamond Certified](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/).
- **Warranties:** The company offers warranties on their work, including five years on parts and up to twenty years on re-piping or sewer replacement.[](https://www.cslb.ca.gov/414359) [[1]](https://www.cslb.ca.gov/414359)[[2]](https://www.healthsafetyqualified.org/company/ca/berkeley/albert-nahman-plumbing-and-heating/)[[3]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)

Would you like help looking up their **exact license number** on the CSLB website, or do you need to check if they have **specific availability** for a job?
```

</details>

<!-- LABELS item=9 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=9 -->

---

## Item 10 · `openai`

> is Albert Nahman Plumbing licensed and insured?

*answer 3 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **1%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Yes—Albert Nahman Plumbing & Heating in Berkeley, California, publicly represents that it is **licensed, bonded, and insured**.  

For the most reliable confirmation, check the California Contractors State License Board (CSLB) using the company’s exact legal name or license number, and ask the company for a current **certificate of insurance**—especially if you need proof of general liability or workers’ compensation coverage.
```

</details>

<!-- LABELS item=10 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=10 -->

---

## Item 11 · `perplexity`

> is Albert Nahman Plumbing licensed and insured?

*answer 4 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **4%** through the answer
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Yes. Available listings indicate **Albert Nahman Plumbing, Heating and Cooling** is **licensed** in California, with CSLB license **#1083634** and an expiration date of **1/31/2027** on multiple directory profiles and BBB records.[4][5][7] Several sources also describe the company as **insured**; HomeAdvisor lists **General Liability** insurance, BuildZoom lists it as insured up to **$2,000,000**, and the company’s own site says its plumbers are “licensed and insured.”[5][6][13]

A few notes on confidence:
- The **license** status is well supported and consistent across sources.[4][5][7]
- The **insurance** claim is supported by directory/profile sources, but insurance details can change, so if you need to verify current coverage for a job, it is best to ask the company directly for a current certificate of insurance.[5][6][10]
```

</details>

<!-- LABELS item=11 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=11 -->

---

# Question: how much does a plumber cost in Berkeley?

## Item 12 · `gemini_grounded`

> how much does a plumber cost in Berkeley?

*answer 1 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
The cost of a plumber in Berkeley, California, can vary significantly depending on the type of service, urgency, and complexity of the job. Generally, you can expect to pay a service call or diagnostic fee, and then an hourly rate or a flat fee for specific services.

**Typical Costs and Fees:**

*   **Service Call / Diagnostic Fee:** Plumbers in Berkeley typically charge between $75 and $150 for a service call or diagnostic fee.
*   **Hourly Rates:** While specific hourly rates for Berkeley plumbers can vary, the average hourly pay for a plumber in Berkeley is around $37.21 to $43.71. Some sources indicate that licensed professionals in urban areas of California, like Berkeley, may charge around $150 per hour, especially for specialized services.
*   **Specific Services:**
    *   Drain cleaning can range from $150 to $450.
    *   Toilet repair typically costs between $100 and $350.
    *   Faucet repair or replacement is usually $100 to $350.
    *   Pipe repair can be $200 to $1,000, while pipe replacement can range from $500 to over $3,500.
    *   Water heater repair is generally $150 to $700, and a tank water heater replacement can be $800 to $2,000. Tankless water heater installation is more expensive, ranging from $1,500 to $3,500.
    *   Sewer line repair can be extensive, costing $1,000 to over $5,000. A sewer camera inspection typically costs $150 to $400.
    *   Leak detection services are usually between $200 and $600.
    *   Slab leak repair can range from $1,500 to $4,500.

**Factors Affecting Plumbing Costs in Berkeley:**

*   **Type of Service:** The complexity of the plumbing issue is the primary determinant of cost. Minor repairs like a leaky faucet will be less expensive than major work such as sewer line replacement or whole-house repiping.
*   **Urgency (Emergency Services):** Emergency plumbing services, especially outside of normal business hours, on weekends, or holidays, will incur higher costs due to elevated labor rates and additional dispatch or labor premiums. Emergency service calls can range from $150 to over $350.
*   **Local Labor Rates:** Plumbing costs in Berkeley are often higher than the national average due to elevated Bay Area labor rates and the higher cost of living in the region.
*   **Age of Homes and Infrastructure:** Berkeley's older homes and aging underground infrastructure can increase the complexity and labor costs of plumbing repairs. Older plumbing materials, limited access behind walls or beneath crawl spaces, and issues like mature tree roots affecting aging clay piping systems are common challenges.
*   **Permit and Inspection Requirements:** Strict California building regulations and local permit and inspection requirements in Alameda County can increase pricing for certain projects like sewer replacements, repiping, and water heater installations.
*   **Materials:** The cost of materials used for the repair or installation will also impact the final price.

It is recommended to get detailed, upfront quotes from licensed plumbers before any work begins.
```

</details>

<!-- LABELS item=12 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=12 -->

---

## Item 13 · `google_ai_mode`

> how much does a plumber cost in Berkeley?

*answer 2 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Based on data from July 2026, the typical cost for a plumber in Berkeley ranges from **$115 to $298 per job** , with an average of around $185. Hourly rates for local plumbing companies are often between **$225 and $254**.[](https://www.yelp.com/costs/plumbing/berkeley) [[1]](https://www.yelp.com/costs/plumbing/berkeley)[[2]](https://www.berkeleyparentsnetwork.org/recommend/home/plumber)

Here is a breakdown of plumbing costs in Berkeley:

**Common Service Costs** 

- **Emergency Drain Cleaning:** $175 – $500
- **Sewer Backup Emergency:** $500 – $3,500
- **Water Heater Repair/Replacement:** $250 – $1,000
- **Camera Inspection:** $300 – $600
- **Slab Cut & Repair:** $1,850 – $3,700[[1]](https://proplumberberkeley.com/plumbing-cost-berkeley/)[[2]](https://plumber-cost.com/drain-line-replacement-cost/california/berkeley)

**Factors Affecting Price** 

- **Company vs. Individual:** Larger companies may have higher overhead (hourly rates over $200), while independent plumbers might be cheaper.
- **Emergency Fees:** Immediate, 24/7 service will generally be more expensive.
- **Severity:** Main drain line repairs or large-scale repiping can exceed $2,500-$9,000+.[](https://patch.com/california/berkeley/how-much-does-hiring-plumber-cost-berkeley) [[1]](https://patch.com/california/berkeley/how-much-does-hiring-plumber-cost-berkeley)[[2]](https://www.hamuch.com/rates/plumber)[[3]](https://www.mrrooter.com/oakland/berkeley/)

Many highly-rated plumbers in Berkeley, such as Pelican Plumbers or Bay Plumbing , offer estimates, so it is recommended to get a quote before work begins.[](https://www.homeadvisor.com/c.Plumbing.Berkeley.CA.-12058.html) [[1]](https://www.homeadvisor.com/c.Plumbing.Berkeley.CA.-12058.html)[[2]](https://m.yelp.com/biz/pelican-plumbers-berkeley)[[3]](https://www.armorproservices.com/san-antonio-plumber)[[4]](https://www.yelp.com/search?find_desc=Plumber+Service&find_loc=Berkeley%2C+CA)

Would you like me to find **plumbers with 5-star ratings** on Yelp, or perhaps **independent plumbers** who might charge less?
```

</details>

<!-- LABELS item=13 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=13 -->

---

## Item 14 · `openai`

> how much does a plumber cost in Berkeley?

*answer 3 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
In **Berkeley, CA**, a plumber typically costs:

- **Service/diagnostic call:** $75–$200  
- **Standard labor:** about **$120–$250 per hour**
- **Emergency or after-hours service:** $200–$400+ per hour
- **Unclogging a drain:** $150–$350
- **Repairing a leaking faucet or pipe:** $150–$600
- **Water heater repair:** $200–$900
- **Water heater replacement:** $1,500–$4,000+
- **Sewer line repair/replacement:** $2,000–$15,000+, depending on access and damage

Costs can be higher if the plumber is licensed, the work requires a **Berkeley permit**, parts are expensive, or walls/floors must be opened. Ask whether the quote includes the service call, labor, materials, permits, and disposal fees. For anything beyond a simple repair, getting **2–3 written estimates** is worthwhile.
```

</details>

<!-- LABELS item=14 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=14 -->

---

## Item 15 · `perplexity`

> how much does a plumber cost in Berkeley?

*answer 4 of 4 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
In Berkeley, a **plumber typically costs about $150–$250 per hour**, with a **service call fee of $90–$150** that is often credited if you approve the work.[1] For a real-world local benchmark, Yelp shows a **typical** plumbing cost of about **$115** and a higher-end figure of **$298** in Berkeley.[2]

For common jobs, local estimates vary widely by scope:

- **Drain cleaning:** about **$150–$500**.[1]
- **Water heater repair:** about **$150–$700**.[1]
- **Water heater installation:** about **$1,300–$3,500**.[1]
- **Toilet repair/installation:** about **$150–$800**.[1]
- **Leak detection:** about **$150–$600**.[1]
- **Emergency plumbing:** about **$200–$1,000**.[1]

Other Berkeley-specific cost guides give lower hourly estimates, such as **about $100 per hour** from ProMatcher[4] and **$45–$150 per hour** from HomeGuide[5], so the most reliable takeaway is that **simple jobs often start around $100–$200+, while larger or emergency jobs can run much higher**.[1][4][5]

If you want, I can also estimate the cost for a **specific plumbing job** in Berkeley, like a clogged drain, leak, or water heater replacement.
```

</details>

<!-- LABELS item=15 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=15 -->

---

# Question: why is my water pressure suddenly low?

## Item 16 · `openai`

> why is my water pressure suddenly low?

*answer 1 of 2 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Sudden low water pressure is usually caused by one of these:

### First, narrow it down
- **One faucet/shower only:** The aerator or showerhead may be clogged, or that fixture’s valve may not be fully open.
- **All cold-water fixtures:** Check whether your **main shutoff valve** is partly closed, a whole-house filter is clogged, or there’s a leak.
- **Hot water only:** The water heater’s shutoff valve, inlet screen, or plumbing may be restricted.
- **Inside and outside:** There may be a municipal supply problem, pressure-regulator failure, or a significant leak.

### Quick checks
1. Ask a neighbor whether they also have low pressure—this indicates a city/utility issue.
2. Check your main water shutoff valve; it should be fully open.
3. Look at your water meter with all fixtures off. If it’s still moving, you may have a leak.
4. Inspect for damp spots, running toilets, hissing sounds, or water pooling near the foundation.
5. Clean faucet aerators and showerheads.
6. If you have a whole-house filter or softener, check whether it needs replacement or bypassing.
7. If pressure fluctuates or is low throughout the house, the **pressure-reducing valve** may have failed.

### Call for help promptly if
- Water pressure dropped suddenly and you see water damage or unexplained meter movement.
- You hear water running inside walls.
- The main shutoff won’t work.
- Pressure is extremely low or absent throughout the house.

If you rent, contact the landlord. Otherwise, check your water utility’s outage notices, then call a plumber if the issue is only at your property.
```

</details>

<!-- LABELS item=16 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=16 -->

---

## Item 17 · `perplexity`

> why is my water pressure suddenly low?

*answer 2 of 2 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
A sudden drop in **water pressure** is most often caused by a problem in your home plumbing or a temporary issue with the local water supply, such as a partially closed main valve, a leak, a faulty pressure regulator, clogged fixtures, or municipal work/breaks.[1][3][6]

What to check first:

- **Is it only one faucet or one fixture?** If so, the issue is usually local, such as a clogged aerator, a partially closed shutoff valve, or debris in that fixture.[4][13]
- **Is hot water low but cold water normal?** That points to the water heater or its connections.[3][5]
- **Is low pressure everywhere in the house?** That suggests a main shutoff valve, pressure regulator, hidden leak, or supply issue.[1][4][6]
- **Did it happen suddenly after plumbing work?** A main valve may not have been reopened fully.[6][15]
- **Is your water meter still moving when all water is off?** If yes, that is a strong sign of a leak.[2]

Common causes of sudden low pressure include:

- **Partially closed main shutoff valve** or water meter valve.[1][4][12]
- **Hidden plumbing leak** inside or under the house.[1][2][6]
- **Failing pressure-reducing valve** or pressure regulator.[1][6][11]
- **Sediment, mineral buildup, or clogged fixtures** like aerators and filters.[1][4][7][12]
- **Municipal supply issues** such as water main breaks, hydrant flushing, maintenance, or high neighborhood demand.[3][4][6][10]

If you want, I can walk you through a quick **5-minute troubleshooting checklist** to narrow down the cause.
```

</details>

<!-- LABELS item=17 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=17 -->

---

# Question: best plumber in Berkeley

## Item 18 · `gemini_grounded`

> best plumber in Berkeley

*answer 1 of 2 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — once, first at **33%** through the answer
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
When searching for the best plumbers in Berkeley, several companies consistently receive high praise for their quality of work, responsiveness, and customer service. Based on numerous reviews and certifications, here are some of the top-rated options:

**Highly-Rated Plumbing Services in Berkeley:**

*   **Star Rooter and Plumbing, Inc.** is frequently mentioned for its high-quality work and customer satisfaction. Clients have praised their efficiency and the lasting nature of their repairs, often noting that they don't need follow-up calls for the same issue.
*   **Albion Plumbing & Rooter, Inc.** is recognized for being easy to work with, responding quickly, and providing competent service. Customers appreciate their promptness and the quality of their work.
*   **Savior Plumbing, Inc.** offers a wide range of residential and commercial plumbing services and is commended for being reliable, doing the work as promised, and completing it on time.
*   **LemonTree Plumbing** stands out for its honest, high-quality plumbing services across the East Bay, including Berkeley. They offer 24/7 live answering, upfront pricing, and have over 100 five-star reviews. Customers highlight their fast response, same-day service, clear communication, and professional, friendly technicians.
*   **Green Eagle Plumbing** is a top-rated, locally owned, and family-oriented company serving Berkeley and surrounding areas. They are known for quality workmanship, transparent pricing, and reliability, with customers often recommending them for both small and large projects, including whole-house repiping.
*   **Pelican Plumbers** in Berkeley has a high percentage of "superior" overall ratings from customers and offers prices that are reportedly 19% lower than the average. They are noted for being very responsive to communication and for efficient, effective repairs.
*   **Berkeley Plumbing and Heating** has been in business for over a century, offering experienced, union-trained plumbers who are dedicated to providing top-quality service for a wide range of plumbing, heating, and cooling needs. They are praised for their professionalism, quality, dependability, and affordability.
*   **Mr. Rooter Plumbing of The Oakland-Berkeley Area** is a trusted name for professional plumbing services, including repairs, drain cleaning, and tankless water heater repair. They are known for quick, efficient, and professional services from licensed and insured plumbers, aiming for 100% customer satisfaction.
*   **Pedro Galvan Plumbing, Inc.** receives high recommendations for professionalism, clarity, and compassion, especially in urgent situations. Customers appreciate their transparent pricing, cost-effectiveness, and precise, efficient, and tidy workmanship.

When choosing a plumber, it's always advisable to consider the specific nature of your plumbing issue, read recent reviews, and inquire about estimates.
```

</details>

<!-- LABELS item=18 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=18 -->

---

## Item 19 · `google_ai_mode`

> best plumber in Berkeley

*answer 2 of 2 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **61%** through the answer
- `LemonTree Plumbing` — once, first at **21%** through the answer
- `J J Rooter & Plumbing` — once, first at **35%** through the answer

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Based on recent reviews and local ratings, here are some of the top-rated plumbing services in and around Berkeley, CA, for 2026:

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-869c3042d546:20)
Afterglow Heating and Plumbing 5.0 (86)  
Heating contractor  
Open 1600 Shattuck Ave. Ste 214a  
(5/5 stars) Highly rated for prompt, professional service, especially for emergency repairs, water heaters, and boilers.[[1]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVhsbVpEUjBZbk5mGAo)[[2]](https://www.berkeleyplumbing.com/)[[3]](https://www.poorespropane.com/hvac/chester-md/)[[4]](https://bobbysplumbing.com/reviews/)

![](https://lh3.googleusercontent.com/grass-cs/ACvplmOPplKGq-_tf4DZvhF2-Ri0kfwz_Gb8fZjb20-_xRV8D5RNOJg6P5_vJORoKddaKkYWrwH1DvUBOD0ZTZwAm9NOpElM-ysnuKaHTVdOEYfuEg7xLY7ROb7daIRZ4LUlHVwQwF6omQ=s192-w192-h144-n-k-no)
LemonTree Plumbing 5.0 (30)  
Plumber  
Open  
(5/5 stars) Highly recommended for personalized service, fair pricing, and clear communication, founded by a local operator.[[1]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVhaZk1qbHVObWczGAo)[[2]](https://www.piazzaplumbing.net/reviews)[[3]](https://www.facebook.com/61561005844782/mentions/)[[4]](https://www.callbighorn.com/service-areas/new-washoe-city-nv-plumbing-services/)[[5]](https://www.jimwagnerplumbing.com/naperville-plumbers/underground-sewer-replacement/)

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-869c3042d546:21)
J J Rooter & Plumbing 4.9 (94)  
Plumber  
Open  
(4.9/5 stars) Known for excellent sewer, drain cleaning, and general plumbing, with a 20% off discount on drain cleaning noted.[[1]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVdwMk0yZzFiWGQ0GAo)[[2]](https://www.thumbtack.com/ca/north-hollywood/plumbing)[[3]](https://www.mrrooter.com/baton-rouge/)[[4]](https://www.mrspeedyplumbing.com/plumber/los-angeles/)[[5]](https://gograsshopper.com/plumbing/hydro-jetting/)

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-869c3042d546:22)
L.J. Kruse Company 4.9 (305)  
Plumber  
Open 920 Pardee St  
(4.9/5 stars) A long-standing family-owned business since 1916, offering reliable, skilled plumbing and heating services.[[1]](https://www.google.com/searchviewer/10?svid=CAwSGxIZCgNwdnESEkNnc3ZaeTh4ZEdzMlgzRjNkQRgK)[[2]](https://ljkruse.com/)[[3]](https://bestairconditioningplumbingrepair.com/plumbing/)[[4]](https://greeneagleplumbing.com/)[[5]](https://www.berkeleyplumbing.com/)

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-869c3042d546:23)
Albert Nahman Plumbing, Heating, and Cooling 4.7 (3.4K)  
HVAC contractor  
Open 3333 Martin Luther King Jr Way  
(4.7/5 stars) A well-known 24/7 service firm in the area, often cited for fast dispatch times.[[1]](https://www.google.com/searchviewer/10?svid=CAwSGxIZCgNwdnESEkNnc3ZaeTh4ZEdSd1oyWXlZZxgK)[[2]](https://www.diamondcertified.org/report/albert-nahman-plumbing-heating-and-cooling/)[[3]](https://www.fixmyleaknow.com/service-areas/lorton/)[[4]](https://www.homeadvisor.com/rated.JoeBelangerPlumbing.36927984.html)[[5]](https://www.dispatch.com/press-release/story/158234/portlands-top-choice-for-emergency-plumbing-services/)

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-869c3042d546:24)
Wally's Plumbing & Leak Detection 5.0 (5)  
Plumber  
Open 225 University Ave  
(5/5 stars) Specializes in leak detection and general plumbing repair.[[1]](https://www.thumbtack.com/ca/berkeley/drain-cleaning/wallys-plumbing/service/509067740351193089?utm_medium=partnership&utm_source=cma-google-ai)

Key Things to Consider

- **Emergencies:** Afterglow Heating and Plumbing and Albert Nahman offer 24-hour service.
- **Specialties:** Pipe Spy is specialized for sewer lateral replacements, while AquaSaver Water Heaters focuses on water heaters.
- **Local Focus:** Green Eagle Plumbing and Pelican Plumbers are frequently recommended by local community members.[](http://pelicanplumbers.com/) [[1]](http://pelicanplumbers.com/)[[2]](https://nextdoor.com/topics/plumber/berkeley/ca)

Are you dealing with an **emergency** , such as a **burst pipe** or **major clog** , or looking for a **routine repair/installation**?
```

</details>

<!-- LABELS item=19 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=19 -->

---

# Question: who is the most reliable plumber in Berkeley?

## Item 20 · `gemini_grounded`

> who is the most reliable plumber in Berkeley?

*answer 1 of 2 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — once, first at **10%** through the answer
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
When seeking the most reliable plumber in Berkeley, several companies consistently receive high praise for their professionalism, responsiveness, and quality of work. Based on customer reviews and industry ratings, the following plumbers are frequently highlighted for their dependability:

**LemonTree Plumbing** is often recommended for its reliable East Bay plumbing services, offering 24/7 live answering, upfront pricing, and numerous five-star reviews. Customers commend their professional, on-time service, quick response, and thorough work, with specific mentions of technicians like Ramon providing excellent service for various issues, including water heater installations and drain cleaning.

**Bay Plumbing** is recognized as an honest and reliable plumbing solution in Berkeley, Albany, and Oakland, with over 15 years of experience. They emphasize responsiveness, honesty, and a commitment to getting the job done right, employing a qualified team for general repairs, replacements, water heaters, and drain issues.

**LJ Kruse** is a family-owned and operated company with over a century of service in the Greater Bay Area, known for its excellence and reliability in plumbing, heating, and cooling. They are praised for their traditional values, exceptional customer service, and effective solutions for both residential and commercial clients.

**Berkeley Plumbing and Heating** also boasts over a century in business, with a reputation for trustworthy service. They are noted for their experienced, union-trained plumbers who are dedicated to providing top-quality service, resolving problems quickly and affordably, and taking pride in their work.

Other highly-rated plumbers in the Berkeley area, as noted by Angi and Diamond Certified, include:

*   **A.E Plumbing** received positive feedback for prompt arrival, clear explanations, reasonable pricing, and quick repairs.
*   **Star Rooter and Plumbing, Inc.** is consistently praised by customers for their high-quality work, with many stating they don't need to call them back for repeat issues.
*   **Albion Plumbing & Rooter, Inc.** is highlighted for being easy to work with, responding quickly, and providing quality service.
*   **Pelican Plumbers** received a "superior" overall rating from 85% of 93 reviewers and are noted for being very responsive to communication and offering prices lower than average.
*   **Pedro Galvan Plumbing, Inc.** is recommended for being attentive, transparent about pricing, and committed to solving problems quickly and efficiently.
*   **Plumbing 1 Builders Inc.** is noted for being a professional and responsible team that offers competitive pricing and efficient work.

When choosing a plumber, it's advisable to consider factors such as their responsiveness, clarity in explaining issues and pricing, and consistent positive feedback regarding the longevity and quality of their repairs.
```

</details>

<!-- LABELS item=20 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=20 -->

---

## Item 21 · `google_ai_mode`

> who is the most reliable plumber in Berkeley?

*answer 2 of 2 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **35%** through the answer
- `LemonTree Plumbing` — once, first at **6%** through the answer
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Several plumbers in Berkeley are highly regarded for reliability based on customer reviews and expert ratings as of July 2026. Top options include specialized local firms and highly rated technicians in the East Bay area.[[1]](https://google.com/goto?url=CAESYgHuR6pNOUtISASd-TN2w7JZvlQ0CJSxDwGv3Ry56PZmEUAZ-qJaDKXoaaqQPbBk1pY6lJfvMCYvB_g83s8Ng-1I3uUr-KKohOB_nfJ1JejTr4faWj-oyqUhMuvHDRv3yY6e)

Highly Recommended Berkeley Plumbers

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-b2eb5f665a3c:28)
LemonTree Plumbing 5.0 (30)  
Plumber  
Open  
Known for being professional, on-time, and providing thorough, clear communication on repairs, with high praise for their technicians like Chia and Ramon.[](https://google.com/goto?url=CAESRQHuR6pNG7k4_vsgjYflBlfdUbg0ryJDZRQ382Yip5ynHvf1poIJ2o9P2NawnOZpiBzBVthXTNBPREWlJGU1fsqXSTRzlw==) [[1]](https://google.com/goto?url=CAESRQHuR6pNG7k4_vsgjYflBlfdUbg0ryJDZRQ382Yip5ynHvf1poIJ2o9P2NawnOZpiBzBVthXTNBPREWlJGU1fsqXSTRzlw==)[[2]](https://google.com/goto?url=CAESVwHuR6pNvSX05T_BJuGyCt1wU4kT-6AaTBA7gCYdyxZ2yvGAxyQeFnjxvg8vKlOYyOZAKh4ZCDLjHNrF9JWli0QgSGGi2GeXidEGkG1LBVCe4xgKCnj8vw==)

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-b2eb5f665a3c:29)
Pelican Plumbers 4.3 (9)  
Plumber  
Open 1881 Alcatraz Ave  
A local Berkeley firm with over 15 years of experience in residential and commercial plumbing, including drainage and gas lines.[](https://google.com/goto?url=CAESYAHuR6pNzSl3CstNTKZg4VILzMvsU_abD3eizPTZNe2JyWMVm-e2pZYIsfeVWY3xA9gFoXSnVsmZtoBhXXxmVFSTho6iDa6rLzOAegv2c1A2mqQUp6yHsjfnMIB-2QPaEg==) [[1]](https://google.com/goto?url=CAESYAHuR6pNzSl3CstNTKZg4VILzMvsU_abD3eizPTZNe2JyWMVm-e2pZYIsfeVWY3xA9gFoXSnVsmZtoBhXXxmVFSTho6iDa6rLzOAegv2c1A2mqQUp6yHsjfnMIB-2QPaEg==)[[2]](https://google.com/goto?url=CAESPgHuR6pNl2tc4vzvlMedZauYczgvnybRYG_ahJonPHxD1akn-dNiq9HIRsWqdXfRz0V2bPUCBhchnhyWs5Bc)[[3]](https://google.com/goto?url=CAESTwHuR6pNIPj-RTH98AHnaN0T1gWeZfXwOrExt7dxBRenGuYNAOcL3qgb0nk6qZ39nmPBTGWk24EjMagXmu4uTyCQ2jTBcGNB2EXYFpnaljc=)

![](https://lh3.googleusercontent.com/grass-cs/ACvplmN3uinPVFROtWZ5MuPp2_Y5Q8EvAIo-Bm0tsBRMHM3KckHwaBcquJely64mHrhc19mDc8CpnWLESFYUWrujpoCNXbNX2G93JBa802jrkOkQQdZfIkXw6vhuMSDF6dsHUJnWPu8I=s192-w192-h144-n-k-no)
Green Eagle Plumbing 5.0 (23)  
Plumber  
Open Kensington, CA  
Highly recommended for reliability and prompt, professional service, often praised by Berkeley homeowners for fixing leaks and sewer issues.[](https://google.com/goto?url=CAESYAHuR6pNzSl3CstNTKZg4VILzMvsU_abD3eizPTZNe2JyWMVm-e2pZYIsfeVWY3xA9gFoXSnVsmZtoBhXXxmVFSTho6iDa6rLzOAegv2c1A2mqQUp6yHsjfnMIB-2QPaEg==) [[1]](https://google.com/goto?url=CAESQgHuR6pNEHhiMsHCT0saO8QMdpAk2GEUeXSdyYOzTW3kNtnJEWUG0KQ2Y4Wc81tYOXy_Bn5IWusj0V4a0O5jay-ZAg==)[[2]](https://google.com/goto?url=CAESQgHuR6pNEHhiMsHCT0saO8QMdpAk2GEUeXSdyYOzTW3kNtnJEWUG0KQ2Y4Wc81tYOXy_Bn5IWusj0V4a0O5jay-ZAg==)[[3]](https://google.com/goto?url=CAESUwHuR6pNRYIUx9I20NjqOae3YkBJwllAkzo1K5aLC44CZMNCvx-pWohI_7zy3H3yiq9xQlPOlmTxpNKHB-rZTpYeB8nqgTvWyBgEUMuiomV6owZS)[[4]](https://google.com/goto?url=CAESUgHuR6pNwZTQkXxwa1pHhMKrCUKtdTRXIzukLZFJSCeliSRNJGsS0zrenl2Gz_1tJbJ1V3ikNCdSU-Wte-npa6oYiNPiJ02W57B0UStdKLNZsik=)

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-b2eb5f665a3c:30)
Albert Nahman Plumbing, Heating, and Cooling 4.7 (3.4K)  
HVAC contractor  
Open 3333 Martin Luther King Jr Way  
Listed as a top-rated local expert with 24/7 emergency service available.[](https://google.com/goto?url=CAESYgHuR6pNOUtISASd-TN2w7JZvlQ0CJSxDwGv3Ry56PZmEUAZ-qJaDKXoaaqQPbBk1pY6lJfvMCYvB_g83s8Ng-1I3uUr-KKohOB_nfJ1JejTr4faWj-oyqUhMuvHDRv3yY6e) [[1]](https://google.com/goto?url=CAESYgHuR6pNOUtISASd-TN2w7JZvlQ0CJSxDwGv3Ry56PZmEUAZ-qJaDKXoaaqQPbBk1pY6lJfvMCYvB_g83s8Ng-1I3uUr-KKohOB_nfJ1JejTr4faWj-oyqUhMuvHDRv3yY6e)[[2]](https://google.com/goto?url=CAESWQHuR6pNQXJtgQy3ZdAEWwYAB491K5NF9Tvg0wsMFPBVWrBR92hydZrcb_i_qqFKwTdgGldCFLtaJgBrEGbPIYvRZcmtJSj3DNMnD19kJrsldyThX19EAJjG)[[3]](https://google.com/goto?url=CAESdgHuR6pNYnS8Y2xXh_iTJi9UkaOgyHq-kzNFye6ti0moq0IxLL4747wMjMvkfYP4ZAvy_4whkuSz0yuw5b5VIpitrzGwlnqbFTw1oDDucXpePAXK0808yRQecmgpcKjbjbdKIkGdeH7yU25phoAOrutznr0nZ_o=)

![](https://streetviewpixels-pa.googleapis.com/v1/thumbnail?panoid=TBDRg9vaxH-KbhjvMDbTow&cb_client=search.gws-prod.grass&yaw=39.630848&pitch=0&thumbfov=100&w=82&h=82)
A Better Rooter Plumbing 4.8 (6)  
Plumber  
Open 379 Vassar Ave  
A small, family-owned company established in 1984 with extensive experience in video inspection and drain/sewer cleaning.[](https://google.com/goto?url=CAESXQHuR6pNzmeuvFuXYKHBmLSrzI9LqmcJljgJ4nLZEvEhCFCemVGRc-U0SA1a-vE7R67-I8XSbIfTjdQzjZBqqOYNsCJS2PktP9Xp7yndtM6IjMDrUSCRDc_AuW7G0g==) [[1]](https://google.com/goto?url=CAESXQHuR6pNzmeuvFuXYKHBmLSrzI9LqmcJljgJ4nLZEvEhCFCemVGRc-U0SA1a-vE7R67-I8XSbIfTjdQzjZBqqOYNsCJS2PktP9Xp7yndtM6IjMDrUSCRDc_AuW7G0g==)

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-b2eb5f665a3c:31)
Wally’s Plumbing & Leak Detection 5.0 (5)  
Plumber  
Open 225 University Ave  
Features 5-star ratings for expertise in drain repair and leak detection in Berkeley.[[1]](https://google.com/goto?url=CAESswEB7keqTZaP0g_C82A7euMNlobFQWqgPiel0wo2ITlGsqeDYyH-2mtiPiA0jUZVmhXj2v6Y83ybsRY4hf-Y-zdivJ6qPgsnwcvqP5qYr34jI3CsHy1c6ZfgWeFd0rb3FTmzXs2XNI1hOQLiLe-ydsOazzdYF0E0cgfqi0QjLnFi6h0seflsjl6EVNX5YS9sLieEJPrY-k-OG-C7jBX7qBVJxQHTkgJV_CyhL7V8fzapyAR4ww==)

![](https://streetviewpixels-pa.googleapis.com/v1/thumbnail?panoid=lwx3ifOLOnDepI6SjShdyQ&cb_client=search.gws-prod.grass&yaw=239.73&pitch=0&thumbfov=100&w=82&h=82)
Alfa Plumbing 5.0 (13)  
Plumber  
Open Albany, CA  
A highly rated local option frequently mentioned for quality, quick service in the Berkeley/Albany area.[](https://google.com/goto?url=CAESYAHuR6pNzSl3CstNTKZg4VILzMvsU_abD3eizPTZNe2JyWMVm-e2pZYIsfeVWY3xA9gFoXSnVsmZtoBhXXxmVFSTho6iDa6rLzOAegv2c1A2mqQUp6yHsjfnMIB-2QPaEg==) [[1]](https://google.com/goto?url=CAEScAHuR6pN3DLjbazOWolDN-SiX5jabD7Qt1wsIFlf-E2YEx2VFEEfbjoa8pGzxgV1ypUkLgC1x8tUV4nwoPqQbZy0KCi9-sVCgsDlJLOHZjjmTFUOR5DLtv7GN4tN3hfqY7PJ203VbHp4AvDlyZ7WYL8=)

Top-Rated Emergency/General Plumbers

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-b2eb5f665a3c:32)
Mr. Rooter Plumbing of The Oakland-Berkeley Area 4.9 (1.4K)  
Plumber  
Open Oakland, CA  
Known for 24/7 service, licensed technicians, and strong customer reviews for emergency repairs.

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-b2eb5f665a3c:33)
Oakland Rooter & Plumbing 4.9 (105)  
Plumber  
Open Fruitvale  
Highly rated for fast response times across the East Bay.

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-b2eb5f665a3c:34)
Clogbusters Plumbing & General Building 3.0 (4)  
Plumber  
Open 2000 Allston Way #495  
Known for 36+ years of experience in the local area, offering quick response times for repairs.[](https://google.com/goto?url=CAESYAHuR6pNzSl3CstNTKZg4VILzMvsU_abD3eizPTZNe2JyWMVm-e2pZYIsfeVWY3xA9gFoXSnVsmZtoBhXXxmVFSTho6iDa6rLzOAegv2c1A2mqQUp6yHsjfnMIB-2QPaEg==) [[1]](https://google.com/goto?url=CAESnQEB7keqTQRFDMLRewuLEQadGlFClU-U4xCSqTc13_RpHmMk_RrPI603U1_5iTydlep3MCMGiNl17UMFLDX8n8FD_sijV-aBCPF6oLt9Lfl54uIPQUDOYcu-qgD8d1vrYWRqdVqXcqxtVSjPtC4vZsqA3PKeY8qHC1RcR3vU7g8V74HY-YxmmS8oVUnd6kmv4Vypsx2x05Cag_ODWd_5)[[2]](https://google.com/goto?url=CAESTQHuR6pNdRkSOCo9pWcVcAlEz7W3atQF9qytEAhnqqrCEmr1yVrUn0j5-gB0gICw52Vlcp8ol4QeWSDt58k5xgZkvA6cyhqhu8Fshiga)[[3]](https://google.com/goto?url=CAESYgHuR6pNuCy1wfvd8MQeSNLJp9QlNX1PDWOQWwr139I55qlKnE6_uB1KbQlVTCQ34mOSI74jTxB_cpbOLVim_D6XtrcBkPC2skUksS1lKhsjDHC2c1sUr3NO9xhYN8AOwEMt)

Things to Consider When Choosing

- **Specialty:** Ensure the plumber specializes in your issue (e.g., sewers, water heaters, or general repairs).
- **Experience with Older Homes:** Berkeley has many older homes; choosing a plumber experienced in "old house" plumbing is crucial, such as those listed by the [Berkeley Parents Network](https://google.com/goto?url=CAESYAHuR6pNzSl3CstNTKZg4VILzMvsU_abD3eizPTZNe2JyWMVm-e2pZYIsfeVWY3xA9gFoXSnVsmZtoBhXXxmVFSTho6iDa6rLzOAegv2c1A2mqQUp6yHsjfnMIB-2QPaEg==).
- **Availability:** For urgent issues, 24/7 companies like Mr. Rooter or Albert Nahman may be best.[](https://google.com/goto?url=CAESYAHuR6pNzSl3CstNTKZg4VILzMvsU_abD3eizPTZNe2JyWMVm-e2pZYIsfeVWY3xA9gFoXSnVsmZtoBhXXxmVFSTho6iDa6rLzOAegv2c1A2mqQUp6yHsjfnMIB-2QPaEg==) [[1]](https://google.com/goto?url=CAESYwHuR6pNz4o4Deu3CbmvVcZTlcaASLzLAzQbFQUA7sOmD2QOTPo2rJ5zw0RD4fqma3XnvcWMcRc20iEGx_uMfdl3aeMqu3DZtyAQ9n2i1Jn9QpS71QooJSUgXiCLIWPj1JYEGA==)[[2]](https://google.com/goto?url=CAESVQHuR6pNxPdB152lNG5kgzuOi8llN-d23nirBMhCJCdD2kh17CJVA6hM3X9d2wAINHcTagQha6pcz3o6JOqARcKsPgD1FlAWe8NmGSSgD9S4icdxX3g=)[[3]](https://google.com/goto?url=CAESSQHuR6pN6c8c9QbLxIlefTRoZ0YYmMeq6inzkKSK4fyPp0S2zRaOYb-tOTGn1uaSeR-RZtrmTxobCKWpjq40YJ-9ELDi5-4duAA=)

For the most reliable service, it is recommended to verify current availability and get quotes from at least two of these companies.

Would you like to focus on:

- A **specific problem** (e.g., water heater, drain clog, sewer lateral)?
- A **quick quote** for an **emergency**?
- A **local, family-owned company**?

Let me know, and I can narrow down the best option for you.
```

</details>

<!-- LABELS item=21 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=21 -->

---

# Question: emergency plumber in Berkeley

## Item 22 · `google_ai_mode`

> emergency plumber in Berkeley

*answer 1 of 1 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **40%** through the answer
- `LemonTree Plumbing` — once, first at **13%** through the answer
- `J J Rooter & Plumbing` — once, first at **27%** through the answer

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Several plumbers in Berkeley offer 24/7 emergency services to address urgent issues like burst pipes, severe clogs, and water heater failures.[[1]](https://www.checkatrade.com/Search/Plumber/in/Berkeley)[[2]](https://caplumberdirectory.com/berkeley-ca/)[[3]](https://proplumberberkeley.com/emergency-plumber/)

Top-Rated 24/7 Emergency Plumbers in Berkeley

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-51a1ff3079a0:22)
LemonTree Plumbing 5.0 (30)  
Plumber  
Open  
Known for same-day emergency service, including weekends, with a focus on clear communication.

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-51a1ff3079a0:23)
Afterglow Heating and Plumbing 5.0 (86)  
Heating contractor  
Open 1600 Shattuck Ave. Ste 214a  
Specializes in after-hours repairs for leaks and water heaters.

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-51a1ff3079a0:24)
J J Rooter & Plumbing 4.9 (94)  
Plumber  
Open  
Available for emergency sewer clogs and drain cleaning.

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-51a1ff3079a0:25)
Mr. Rooter Plumbing of The Oakland-Berkeley Area 4.9 (1.4K)  
Plumber  
Open Oakland, CA  
Offers 24/7 service, including holidays, with no overtime fees.

![](https://api.dataforseo.com/cdn/i/07290120-2179-0139-0000-51a1ff3079a0:26)
Albert Nahman Plumbing, Heating, and Cooling 4.7 (3.4K)  
HVAC contractor  
Open 3333 Martin Luther King Jr Way  
Provides 24/7 emergency commercial and residential services.[[1]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVhaZk1qbHVObWczGAo)[[2]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVhsbVpEUjBZbk5mGAo)[[3]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVdwMk0yZzFiWGQ0GAo)[[4]](https://www.google.com/searchviewer/10?svid=CAwSGxIZCgNwdnESEkNnc3ZaeTh4ZGpjMWN6TjJjURgK)[[5]](https://www.google.com/searchviewer/10?svid=CAwSGxIZCgNwdnESEkNnc3ZaeTh4ZEdSd1oyWXlZZxgK)

Other Emergency Options

- **One Step Plumbing:** Open late (up to 11 PM on some weekdays).
- **EO Plumbing Service:** 24/7 service operating in the Richmond/Berkeley area.
- **[Roto-Rooter](https://www.rotorooter.com/berkeleyca/):** 24/7 service with same-day availability.[](https://www.rotorooter.com/berkeleyca/) [[1]](https://www.rotorooter.com/berkeleyca/)[[2]](https://www.rotorooter.com/berkeleyca/)[[3]](https://www.rotorooter.com/westminsterco/)

Important Tips for Plumbing Emergencies

- **Shut off the water:** Locate your main water shut-off valve immediately to stop further damage, especially for burst pipes.
- **Call for a professional:** For severe leaks or sewage backups, call a 24/7 service immediately.
- **Be aware of fees:** Some plumbers may charge a surcharge for after-hours or emergency service.[](https://proplumberberkeley.com/emergency-plumber/) [[1]](https://proplumberberkeley.com/emergency-plumber/)[[2]](https://banddindustries.com/things-to-consider-before-hiring-a-24-hour-emergency-plumber/)[[3]](https://www.sosaffordablerooter.com/plumbing-repair-questions)[[4]](https://goodplumbertn.com/emergency-plumber/)

Would you like to see **customer reviews** for a specific company, or are you looking for someone who specializes in **water heaters** or **drain cleaning**?
```

</details>

<!-- LABELS item=22 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=22 -->

---

# Question: 24 hour plumbing service Berkeley

## Item 23 · `google_ai_mode`

> 24 hour plumbing service Berkeley

*answer 1 of 1 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — once, first at **17%** through the answer
- `LemonTree Plumbing` — once, first at **13%** through the answer
- `J J Rooter & Plumbing` — **not found**

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
Several plumbers offer 24-hour, emergency services in Berkeley, CA, to handle urgent issues like burst pipes, sewer backups, and water heater failures.[[1]](https://www.rotorooter.com/berkeleyca/)

**Top-Rated 24-Hour Plumbers in Berkeley (July 2026)** 

- **Afterglow Heating and Plumbing:** Open 24 hours, specializing in water heaters, leak repairs, and heating systems (510-495-0550).
- **LemonTree Plumbing:** 24-hour service (510-502-7843) with reported fast, same-day, and evening emergency response.
- **Albert Nahman Plumbing, Heating, and Cooling:** 24/7 service (510-408-7879) for plumbing, drain cleaning, and HVAC needs.
- **Mr. Rooter Plumbing of The Oakland-Berkeley Area:** 24/7 emergency service, particularly for drain cleaning, hydro jetting, and sewer lines (510-957-9648).
- **Clogbusters Plumbing And General Building:** 24/7 service (510-689-8733).
- **Lifesaver Plumbing & Rooter:** 24/7 emergency services including water heater repair and sewer backups.[[1]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVhsbVpEUjBZbk5mGAo)[[2]](https://www.google.com/searchviewer/10?svid=CAwSHRIbCgNwdnESFENnMHZaeTh4TVhaZk1qbHVObWczGAo)[[3]](https://www.google.com/searchviewer/10?svid=CAwSGxIZCgNwdnESEkNnc3ZaeTh4ZEdSd1oyWXlZZxgK)[[4]](https://www.google.com/searchviewer/10?svid=CAwSGxIZCgNwdnESEkNnc3ZaeTh4ZGpjMWN6TjJjURgK)[[5]](https://www.google.com/searchviewer/10?svid=CAwSGxIZCgNwdnESEkNnc3ZaeTh4ZEdSZlluaHRjURgK)[[6]](https://www.yelp.com/search?find_desc=Emergency+Plumber&find_loc=Berkeley%2C+CA)

**Common Emergency Services Available:** 

- **Drain Cleaning & Sewer Repairs:** Immediate response for backed-up sewer lines.
- **Water Heater Services:** Repair or replacement for failed water heaters.
- **Leak Detection & Pipe Repair:** Emergency, trenchless, or traditional repair for bursts.[](https://www.rotorooter.com/berkeleyca/) [[1]](https://www.rotorooter.com/berkeleyca/)[[2]](https://superservicetoday.com/areas-we-serve/danvers-ma/)[[3]](https://www.mrrooter.com/oakland/berkeley/)

**Notes on Emergency Service** 

- **Rates:** Emergency plumbing calls typically cost between $100 and $500 per hour, with higher rates potentially applying to holiday or after-hours calls.
- **Response Time:** Many services, such as Mr. Rooter , offer rapid dispatch, with some arriving within 30 minutes of a call.
- **Coverage:** These services often cover Berkeley and surrounding areas such as Oakland, Albany, and Emeryville.[](https://www.angi.com/articles/emergency-plumber-cost.htm) [[1]](https://www.angi.com/articles/emergency-plumber-cost.htm)[[2]](https://www.barkerandsonsplumbing.com/city/whittier-plumber/)[[3]](https://www.mrrooterplumbingpa.com/plumbers-lewistown-pa-plumbing-repair-service)

To help you get the **fastest service** , are you experiencing a **specific emergency** (e.g., sewage backup, burst pipe, or no hot water) that I can use to refine this list?
```

</details>

<!-- LABELS item=23 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=23 -->

---

# Question: top rated drain cleaning in Berkeley

## Item 24 · `perplexity`

> top rated drain cleaning in Berkeley

*answer 1 of 1 to this question. Client: **Albert Nahman Plumbing**. Competitors: LemonTree Plumbing, J J Rooter & Plumbing.*

**Where each name appears** — literal text match, so you do not have to scan for it.
This is evidence, not a label: a disavowal ("there is no such company") names the brand while meaning the opposite, and only you can see that.

- `Albert Nahman Plumbing` — **not found**
- `LemonTree Plumbing` — **not found**
- `J J Rooter & Plumbing` — once, first at **12%** through the answer

<details open><summary><b>The answer</b> (click to collapse once labeled)</summary>

```text
If you mean **top-rated drain cleaning in Berkeley**, the strongest match in the results is **J J Rooter & Plumbing**, which has a **4.9-star rating from 257 Yelp reviews**.[2]

Other Berkeley-area options in the results include:

- **Mr. Rooter Plumbing of The Oakland-Berkeley Area** — promotes drain cleaning services in Berkeley, but no review score is shown in the result provided.[1]
- **Capelli Plumbing** — advertises drain cleaning in Berkeley, but the result does not include a rating.[3]
- **Roto-Rooter Plumbing Sewer & Drain Cleaning Service** — listed in Berkeley with a **2.0-star rating from 3 reviews**.[4]

If you want, I can also help you narrow this to:
- **highest-rated by reviews**
- **best for emergency service**
- **most affordable**
- **local independent plumbers vs. chains**
```

</details>

<!-- LABELS item=24 -->

`present` yes/no · `prominence` recommended_first / mid_pack / buried / also_ran / absent · `framing` positive / neutral / negative

| brand | present | prominence | framing |
| --- | --- | --- | --- |
| Albert Nahman Plumbing | no | absent | neutral |
| LemonTree Plumbing | no | absent | neutral |
| J J Rooter & Plumbing | no | absent | neutral |

**Flags about Albert Nahman Plumbing** — `type | severity | note`, one per line. Empty = accurate.

```flags

```

**Uncovered claims** — things the answer asserts that the fact sheet does not cover, one per line. The judge must not flag these.

```candidates

```

<!-- /LABELS item=24 -->

---

_Generated from `local_gold.json` — 25 items to label._
