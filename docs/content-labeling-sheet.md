# Content-judge gold set — labeling sheet

One section per crawled page. For each of the six checks, replace `____` with
**pass**, **partial**, or **fail**. Leave a label blank to skip that page/check
pair — a skipped pair is dropped, which is better than a guess.

**Do not consult the audit's own output while labeling.** The judge's verdicts are
deliberately absent from this sheet: κ measures whether the judge agrees with a
human, and a labeler who has seen the judge's answer is no longer independent.

Label against the **extracted text shown here**, not the rendered page. That text
is what the judge reads, so labeling the pretty version would score the judge for
a document it never saw.

Per `docs/grade-calibration-guide.md`, two people should label **independently and
blind**, then reconcile disagreements before the κ run.

---

## The six checks

**`answer_first_lead`** (Cat 3) — Answer-first lead
  - Does the page open with a direct answer to its main question in ~60 words?
  - Does the answer come before background/marketing preamble?
  - Is the opening answer concise (about one 40–60 word paragraph)?

**`self_contained_chunks`** (Cat 3) — Self-contained chunks
  - Can each major section be understood without earlier sections?
  - Does each section name its subject, not far-back pronouns?

**`definition_first`** (Cat 3) — Definition-first sentences
  - Are key terms defined with a clear 'X is …' style sentence?
  - Do those definitions appear early, not after long discussion?

**`expert_commentary`** (Cat 4) — Expert quotes / original commentary
  - Does the page give original analysis beyond common knowledge?
  - Does it include a named expert quote or first-hand insight?

**`original_data`** (Cat 4) — Original data / first-hand evidence
  - Does the page show original data, first-hand testing, or a case study?
  - Are specific numbers/results tied to a described method or source?

**`external_citations`** (Cat 4) — Authoritative external citations
  - Does the page cite authoritative external sources for its claims?
  - Are those sources credible, not just internal/marketing links?

A check is **pass** when every sub-question is yes, **fail** when none are, and
**partial** in between. Rule on the page in front of you, not the site.

---

**Source:** callafterglow.com · 15 pages with usable text (of 15 crawled)

---

## 1. https://callafterglow.com/

_Category: homepage · 4179 chars extracted (excerpt below)_

```text
The Bay Area's Radiant Heat & Plumbing Specialist
With over 20+ years of hydronic heating and plumbing expertise, Afterglow delivers steady warmth, smooth flow, and lasting comfort. From your first call to the final result, you work with professionals who make complex problems feel simple and ensure everything is handled with care, so your home keeps flowing and glowing long after the job is done.
What Our Neighbors Are Saying
Mniska helped a lot with my radiant heating system. He took a lot of time to explain everything to me and gave me several option for fixing and upgrading our system, without making me feel pressured. Recommended as a radiant heating expert.
Mniska made some repairs to my hydronic heating system which have improved its performance. He's knowledgeable and takes obvious pride in his work. Will use again.
We've worked with Mniska on the boiler/radiators in our new home and couldn't be happier with Mniska's attention to detail and communication. We cannot recommend his services more and look forward to a long term relationship with him over the years.
Mniska was amazing. We have a complicated heating system in a house we just bought and he figured it all out, patiently explained how it works to me and got it back in tip top shape. Highly recommend 👍
All plumbing experiences should be this pleasant and easy. Mniska gave me a clear, accurate estimate for all work, including the installation of an automatic gas shut-off valve on my house gas line, which shuts off in case of earthquake, along with a tutorial on how to use and/or reset it. He also performed a major seasonal flush of my on-demand water heater, as well as several minor deferred maintenance faucet-related fixes. Thanks!
Wow, you really feel taken care of with Afterglow Heating. They're passionate about their job and genuinely care for you as a customer. I appreciate when a technician takes time to explain things. Mniska showed me why it was better to do a long-term solution rather than a patch-up fix, as another company had suggested. They saved us money and extra headaches. I can't recommend them enough.
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing

[... 1979 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/ -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 2. https://callafterglow.com/services

_Category: service · 3378 chars extracted (excerpt below)_

```text
Heating & Plumbing Services in The Bay Area
From the hydronic system warming your floors to the pipes running through your walls, we take care of the systems that keep your home comfortable. Every service comes with 20+ years of focused expertise and our Afterglow Finish, a walkthrough to make sure everything works the way it should.
Every Service, Held to the Glow Standard
We specialize in the systems that keep your home warm, flowing, and efficient. Each one gets the same care: thorough assessment, clear explanation, and work that holds up for years.
Why Homeowners Choose Afterglow
There are plenty of plumbers in the Bay Area. Here's what makes working with us feel different from the moment you pick up the phone.
Specialist, Not a Jack-of-All-Trades
20+ years focused exclusively on hydronic heating and plumbing means deeper expertise, faster diagnosis, and solutions that actually last.
Our Team Shows Up.
We'll support you from the first call to the final walkthrough. Our technicians will explain the system in clear language for you to make the decision that works best for you.
Efficiency Without Compromise
We work at the intersection of comfort and sustainability - high-efficiency boilers, heat pumps, and solar heating that lower bills and environmental impact.
What Our Neighbors Are Saying
Professional, knowledgeable and punctual. Pleasure working with Mniska and Afterglow Heating
Mniska was amazing. We have a complicated heating system in a house we just bought and he figured it all out, patiently explained how it works to me and got it back in tip top shape. Highly recommend 👍
With Afterglow Heating, not only will you receive a hi-performance heating solution for you and your loved ones, you will also feel comforted by the trusted character and professionalism AH brings to make you feel heard and seen in achieving the right outcome for the job, leaving everyone involved warm on the inside and out! Top Notch!
Mniska is a pleasure to work with- he is professional, knowledgeable, respectful, honest and caring. He helped me think through a plumbing issue with my shower and ways to save money with the repairs. He cares about providing quality work and approaches

[... 1178 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/services -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 3. https://callafterglow.com/services/air-to-water-heat-pumps

_Category: service · 326 chars extracted_

```text
What is an air-to-water heat pump and how does it save energy?
It pulls heat from outdoor air and transfers it to water that circulates through your existing radiators, baseboards, or radiant floors. Because it moves heat instead of generating it, it can deliver three or four units of heat for every unit of electricity used.
```

<!-- LABELS url=https://callafterglow.com/services/air-to-water-heat-pumps -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 4. https://callafterglow.com/services/boiler-installation-service

_Category: service · 307 chars extracted_

```text
Is a high-efficiency boiler worth it in California?
For most Bay Area homes with hydronic heating, yes. Modern condensing boilers run at 90-95% efficiency compared to 70-80% on older units, and many installs qualify for utility rebates. Over a 15-year lifespan the savings usually outweigh the upgrade cost.
```

<!-- LABELS url=https://callafterglow.com/services/boiler-installation-service -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 5. https://callafterglow.com/services/hydro-solar-systems

_Category: service · 3925 chars extracted (excerpt below)_

```text
Hydro Solar Systems for Bay Area Homes
Use the Bay Area's sunshine to heat your home and your water. We design and install solar thermal systems that integrate with your existing hydronic loops.
Solar Thermal for Heating and Hot Water
Hydro solar uses rooftop collectors to heat water directly, which then feeds your radiant floors, radiators, or domestic hot water. It's a different technology from solar PV, and it's particularly well suited to homes that already have hydronic heating.
- Solar-assisted space heating
- Solar domestic hot water
- Integration with existing boilers and heat pumps
What Makes a Home a Good Fit
Not every roof is right for solar thermal. Here's what we look for.
Good Solar Exposure
South-facing roof area with minimal shade for several hours a day is the starting point.
Existing Hydronic System
Hydro solar pairs best with homes that already use radiant floors, radiators, or baseboards.
Heavy Hot Water Use
Larger families and homes with high hot water demand see the fastest return.
How We Design and Install Hydro Solar
Solar thermal is engineering, not just installation. We design systems that actually deliver on their promise.
1. Site Assessment
We evaluate roof exposure, hot water and heating loads, and your existing hydronic system.
2. System Design
Collector sizing, storage, controls, and integration with the rest of your system.
3. Installation
Careful installation by specialists, including all the plumbing, controls, and integration work.
4. Monitoring and Service
We commission the system, walk you through operation, and provide ongoing support.
We Built Our Business on Hydronic Systems
Solar thermal is only as good as the hydronic system behind it. Afterglow specializes in exactly that, designing and installing radiant and hydronic heating that performs for decades.
- Hydronic integration done right, every time
- Solar thermal systems engineered for your load
- One team handles installation and long-term support
What Our Neighbors Are Saying
If 6 stars were available, Afterglow Heating would receive them. Mniska is unarguably a master of his craft who has been building/designing and installing exceptional heating systems for over a d

[... 1725 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/services/hydro-solar-systems -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 6. https://callafterglow.com/services/hydronic-heating

_Category: service · 424 chars extracted_

```text
How does radiant heating work in older Bay Area homes?
Radiant heating, also called hydronic heating, circulates hot water through pipes to radiators, baseboards, or radiant floor tubing. Many older Berkeley and Oakland homes were built with these systems. The existing distribution can usually be preserved while upgrading to a high-efficiency boiler or air-to-water heat pump for better performance and lower energy costs.
```

<!-- LABELS url=https://callafterglow.com/services/hydronic-heating -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 7. https://callafterglow.com/services/plumbing

_Category: service · 5102 chars extracted (excerpt below)_

```text
Do you handle emergency plumbing calls?
We respond to urgent issues as quickly as we can. As an owner-operated business we can't always promise same-day for non-emergencies, but for active leaks and burst pipes we'll get to you fast.
Plumbing You Can Actually Trust
20+ years of hands-on plumbing experience.
Full-Service Plumbing
From a slow leak under the sink to a whole home repipe, we bring careful diagnosis and respect for your home to every job.
- Leak detection and repair
- Fixture installation and upgrades
- Repipes, water lines, and recirculation pumps
When to Call a Plumber
Bay Area homes have their quirks. Here are the issues we see most often.
From slow under-sink drips to mystery water stains. We trace the source rather than guessing.
Often related to aging galvanized lines, scale buildup, or pressure regulator issues.
Many pre-1960s Bay Area homes still have iron water supply lines that are nearing the end of their life.
The Afterglow Finish
Careful diagnosis, clear explanation, real fix. Not a band-aid that comes back next year.
We start with a real conversation about what's happening before we touch anything.
Find the actual cause, not just the symptom. That's how repairs actually last.
Quality parts, careful workmanship, respect for your home and your time.
Show you what we did, why, and what to watch for going forward.
Why Bay Area Homeowners Choose Afterglow
We answer the phone, listen to the issues and provide options for you to choose the one that feels right. We take care of your home like it was our own.
- Direct relationship from start to finish
- Transparent pricing, no upsells
- 20+ years working on Bay Area homes
What Our Neighbors Are Saying
Mniska came to our rescue fast and did a thorough investigation of our failing boiler. He was able to fix all of the problems as well as a shower arm issue we were having. He was thoughtful, efficient, informative and very helpful. It was a long project that took most of the day but he stayed until it was finished and made sure the house was as clean as when he arrived. Thank you for helping us out!
M G.
I used Afterglow services to help me fix a hydronic issue that another contractor messed up. He 

[... 2902 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/services/plumbing -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 8. https://callafterglow.com/services/water-heaters

_Category: service · 1336 chars extracted_

```text
remove first person:
Starting January 1, 2027, only zero-NOx (low-emission) water heaters may be sold or installed in all nine Bay Area counties under BAAQMD Rule 9-6. In plain terms: if your gas water heater fails after that date, a licensed plumber won’t be able to install a new gas unit to replace it. This is a point-of-sale restriction — not a forced retrofit mandate. If you already have a gas water heater running, you’re not required to rip it out. But the moment it needs replacing, your options change significantly. Residents are looking at roughly a $3,500 cost increase for heat pump models compared to traditional tank water heaters. The upside: the federal 25C Energy Efficient Home Improvement Credit offers up to $2,000 for qualifying heat pump water heaters, and state programs through TECH Clean California have offered rebates of $1,000–$3,100+ depending on income eligibility — though funding moves fast and waitlists are common. If your gas water heater is aging, 2026 is genuinely your last window to replace it on your own terms. I’m happy to walk you through your options — whether that’s going in with a gas unit now or planning ahead for a heat pump system. Regulations in this area are evolving — I’ll always do my best to keep this information current, but confirm the latest with BAAQMD or give me a call.
```

<!-- LABELS url=https://callafterglow.com/services/water-heaters -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 9. https://callafterglow.com/service-areas/berkeley

_Category: service · 3787 chars extracted (excerpt below)_

```text
Plumber and Radiant Heating Specialist in Berkeley, CA
From Craftsman cottages in North Berkeley to Tudors in the Hills, we know Berkeley's homes and the heating and plumbing systems inside them. Our team brings 20+ years of focused expertise to each project.
Heating and Plumbing for Berkeley's Older Homes
Berkeley's older homes are some of the most distinctive in the East Bay. Craftsman bungalows in Elmwood and Thousand Oaks, brown shingles tucked into the Claremont Hills, stucco Mediterraneans in South Berkeley, and the older homes of Kensington, each with its own construction era and its own set of mechanical quirks. A lot of these houses are still running original hydronic systems that haven't had a specialist's hands on them in decades.
- Hydronic heating, boilers, and radiators
- Whole-house plumbing repair and repipes
- Air-to-water heat pump and solar integration
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing, we bring two decades of hands-on expertise to every system in your home. Each service ends with our Afterglow Finish, a final walkthrough to make sure everything flows and glows.
Why Berkeley Homeowners Choose Afterglow
Berkeley homeowners value quality, transparency, and sustainability. That lines up with everything we do. We bring modern solutions like air-to-water heat pumps and hydro solar integration to homeowners who want to reduce their environmental footprint without sacrificing comfort.
Deep Knowledge of Berkeley Homes
20+ years working on Craftsman radiators, Victorian boilers, and mid-century plumbing across Berkeley's neighborhoods. We know what these homes need.
Local Roots and Expertise
Our Team lives and works in the East Bay. When you call, you get a team that actually cares and has fast response times across all Berkeley neighborhoods.
What Our Neighbors Are Saying
Professional and great to work with. Highly recommended!
Highly recommend Afterglow Radiant Heating! Mniska Lamb, the owner, quickly diagnosed and fixed our intermittent hot water issue with our tankless system. He completed important maintenance, suggested valuable upgrades, and communicated clearly throughout the process. He worked ef

[... 1587 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/service-areas/berkeley -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 10. https://callafterglow.com/service-areas/el-cerrito

_Category: service · 3491 chars extracted (excerpt below)_

```text
Plumbing and Heating Services in El Cerrito, CA
From the flatland bungalows near El Cerrito Plaza to the view homes climbing the hills toward Arlington, we bring 20+ years of focused hydronic and plumbing experience to every El Cerrito neighborhood.
Heating and Plumbing for El Cerrito Homeowners
Many homes in El Cerrito date to the post-war boom, with mid-century plumbing and heating that's now decades past its prime. From the bungalows near San Pablo Avenue to the hillside homes above, we handle the aging systems that quietly hold these houses together.
- Boiler service and high-efficiency upgrades
- Plumbing repair and whole-house repipes
- Water heater installation and service
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing, we bring two decades of hands-on expertise to every system in your home. Each service ends with our Afterglow Finish, a final walkthrough to make sure everything flows and glows.
Why El Cerrito Homeowners Choose Afterglow
El Cerrito homeowners want honest work and a plan they can trust, not the cheapest patch. That's exactly how we operate. We bring careful diagnosis and clear pricing to every job, whether it's an aging boiler or a tired set of pipes.
Experience With Post-War Homes
From mid-century bungalows to hillside view homes, we've worked on every era of El Cerrito construction and their systems.
One Team, Start to Finish
Our specialists handle your project from the first call to the final walkthrough. No handoffs, no miscommunication, no surprises.
What Our Neighbors Are Saying
Mniska came to our rescue fast and did a thorough investigation of our failing boiler. He was able to fix all of the problems as well as a shower arm issue we were having. He was thoughtful, efficient, informative and very helpful. It was a long project that took most of the day but he stayed until it was finished and made sure the house was as clean as when he arrived. Thank you for helping us out!
When our tankless water heater broke, I called Mniska and he came the same day. He was very good and thorough. He patiently explained our options and answered all our questions. Definitely recommend!
Excellent service! They answe

[... 1291 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/service-areas/el-cerrito -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 11. https://callafterglow.com/service-areas/emeryville

_Category: service · 2729 chars extracted (excerpt below)_

```text
Plumber and Heating Service in Emeryville, CA
Emeryville is a mix of historic homes and modern lofts. Each has its own plumbing and heating needs, and we bring 20+ years of specialist experience to both.
Heating and Plumbing for Emeryville Homes and Lofts
Whether you're dealing with an aging boiler in an older home or a tankless water heater in a newer condo, we bring focused expertise and honest pricing to every Emeryville job.
- Boiler and hydronic system service
- Tankless and traditional water heaters
- Plumbing repair and fixture upgrades
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing, we bring two decades of hands-on expertise to every system in your home. Each service ends with our Afterglow Finish, a final walkthrough to make sure everything flows and glows.
Why Emeryville Homeowners Choose Afterglow
One team, careful diagnosis, honest pricing. That's been the approach for 20+ years and it's the reason homeowners across the East Bay keep calling.
Range of Experience
From Victorian boilers to modern tankless installs, we've worked on the full range of Emeryville's housing stock.
A Reliable Team
Our specialists handle every project from start to finish. No hands-off, no rotating technicians, no miscommunication.
What Our Neighbors Are Saying
Professional, knowledgeable and punctual. Pleasure working with Mniska and Afterglow Heating
Mniska was amazing. We have a complicated heating system in a house we just bought and he figured it all out, patiently explained how it works to me and got it back in tip top shape. Highly recommend 👍
Our service was impeccable. They came within hours of calling with an issue, communicated extremely clearly and was very transparent with pricing. We even signed up for the membership program which already paid off! Highly recommend.
Afterglow Heating is a gem. Mniska is responsive, reasonable and imminently professional. Don't call anyone else for radiant work, he's the best.
Highly recommend Afterglow Radiant Heating! Mniska Lamb, the owner, quickly diagnosed and fixed our intermittent hot water issue with our tankless system. He completed important maintenance, suggested valuable upgrades, an

[... 529 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/service-areas/emeryville -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 12. https://callafterglow.com/service-areas/kensington

_Category: service · 3828 chars extracted (excerpt below)_

```text
Plumber and Radiant Heating Specialist in Kensington, CA
From the winding lanes above Colusa Circle to the homes tucked along the Tilden ridge, we know Kensington's hillside houses and the older heating systems inside them. We're a team of specialists with 20+ years of focused expertise.
Heating and Plumbing for Kensington's Hillside Homes
Kensington's homes were largely built in the 1920s and 30s, and many still run on the original hydronic heating they were designed around. Tudors, Arts and Crafts cottages, and Mediterranean revivals along the steep streets each come with their own quirks, and the boilers and radiators inside them require a specialist who has seen it all before.
- Hydronic heating, boilers, and radiators
- Whole-house plumbing repair and repipes
- Air-to-water heat pump and solar integration
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing, we bring two decades of hands-on expertise to every system in your home. Each service ends with our Afterglow Finish, a final walkthrough to make sure everything flows and glows.
Why Kensington Homeowners Choose Afterglow
Kensington homeowners value craftsmanship and care, and they tend to keep the same trusted hands for decades. That suits us perfectly. We bring patient diagnosis and a long-term plan to every hillside home, whether it's a vintage boiler or a modern efficiency upgrade.
Deep Knowledge of Older Homes
20+ years working on the kind of 1920s boilers and radiators that fill Kensington's hillside neighborhoods. We know what these homes need.
Local Roots and Expertise
Our specialists live and work in the East Bay. When you call, you get the person who does the work, with fast response across Kensington's hills.
What Our Neighbors Are Saying
Mniska found a leak that I did not know was there. He fixed it and showed me the pipe that had deteriorated. He goes above and beyond.
I had an automatic water shut-off valve installed today, and Mniska did an excellent job. He was very polite, professional, and explained all my options clearly before coming out. He arrived on time, worked efficiently, and completed the installation quickly. Everything was done neatly and profess

[... 1628 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/service-areas/kensington -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 13. https://callafterglow.com/service-areas/oakland

_Category: service · 3527 chars extracted (excerpt below)_

```text
Plumber and Radiant Heating in Oakland, CA
From Rockridge Craftsmans to Grand Lake Victorians and Montclair hillside homes, we bring 20+ years of focused hydronic and plumbing experience to every Oakland neighborhood.
Heating and Plumbing for Oakland's Diverse Housing Stock
Oakland has some of the Bay Area's oldest and most beautiful homes, and many still rely on aging boilers and hydronic systems that need a specialist who actually knows them. From Temescal to Montclair, we work on the whole range.
- Boiler repair and high-efficiency replacement
- Radiator and radiant floor service
- Whole-house plumbing for Victorians and Craftsmans
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing, we bring two decades of hands-on expertise to every system in your home. Each service ends with our Afterglow Finish, a final walkthrough to make sure everything flows and glows.
Why Oakland Homeowners Choose Afterglow
Oakland homes have history, character, and complicated heating systems. That's exactly what we specialize in. We bring careful diagnosis and an honest plan to every job, whether it's a Victorian boiler or a mid-century radiant floor.
Experience With Oakland's Homes
From Victorians to bungalows to mid-century homes, we've worked on every era of Oakland construction and their heating systems.
One Specialized Team, Start to Finish
Our specialists handle your project from the first call to the final walkthrough. No handoffs, no miscommunication, no surprises.
What Our Neighbors Are Saying
Wow, you really feel taken care of with Afterglow Heating. They're passionate about their job and genuinely care for you as a customer. I appreciate when a technician takes time to explain things. Mniska showed me why it was better to do a long-term solution rather than a patch-up fix, as another company had suggested. They saved us money and extra headaches. I can't recommend them enough.
Exceptional experience! Mniska is a professional, responded to our request for help the same day, identified the source of our leak and resolved the issue quickly saving us $$$$$!!! He figured out the part that failed was under warranty and filed the paperwork for us to

[... 1327 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/service-areas/oakland -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 14. https://callafterglow.com/service-areas/orinda

_Category: service · 3370 chars extracted (excerpt below)_

```text
Plumber and Radiant Heating Specialist in Orinda, CA
From the wooded hillsides above the Orinda Theatre to the larger estate homes tucked into the canyons, we bring 20+ years of focused hydronic and plumbing expertise to every corner of Orinda.
Heating and Plumbing for Orinda's Hillside Homes
Orinda's larger homes often run sizable hydronic and radiant systems, and they need someone who genuinely understands how they're put together. Spanish revivals, ranch homes, and custom builds across Lamorinda require a careful, specialist attention rather than a quick patch.
- Hydronic heating, boilers, and radiant floors
- Whole-house plumbing repair and repipes
- Air-to-water heat pump and solar integration
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing, we bring two decades of hands-on expertise to every system in your home. Each service ends with our Afterglow Finish, a final walkthrough to make sure everything flows and glows.
Why Orinda Homeowners Choose Afterglow
Orinda homeowners invest in their homes for the long run, and they want a tradesperson who thinks the same way. That's our whole approach. We bring patient diagnosis and well-thought-out solutions to every hillside home, from estate boilers to modern efficiency upgrades.
Radiant Heat Expertise
Orinda's larger homes lean on hydronic and radiant heating. That's the exact work we've mastered over the past 20+ years.
Team of Specialists
Our team handles your project with the patience, care, and attention to detail an Orinda home deserves, start to finish.
What Our Neighbors Are Saying
Afterglow Plumbing was very timely and professional, start to finish. Definitely recommend.
Mniska came to our rescue fast and did a thorough investigation of our failing boiler. He was able to fix all of the problems as well as a shower arm issue we were having. He was thoughtful, efficient, informative and very helpful. It was a long project that took most of the day but he stayed until it was finished and made sure the house was as clean as when he arrived. Thank you for helping us out!
Mniska taught us about our system, reviewed all of our options, and helped us decide how to proceed. His wor

[... 1170 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/service-areas/orinda -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->

---

## 15. https://callafterglow.com/service-areas/piedmont

_Category: service · 3317 chars extracted (excerpt below)_

```text
Plumbing and Heating Services in Piedmont, CA
Piedmont's historic homes deserve the same care that built them. We bring 20+ years of focused hydronic heating and plumbing expertise to every job in the area.
Heating and Plumbing for Piedmont's Established Homes
Piedmont's older heating infrastructure needs an experienced hand. Whether it's a vintage boiler that needs careful servicing or a high-end upgrade you've been planning, we bring quality and patience to every visit.
- Boiler service and high-efficiency upgrades
- Radiator and radiant floor systems
- Plumbing repair and fixture installation
Every System Gets the Glow Standard
From radiant hydronic heat to modern plumbing, we bring two decades of hands-on expertise to every system in your home. Each service ends with our Afterglow Finish, a final walkthrough to make sure everything flows and glows.
Why Piedmont Homeowners Choose Afterglow
A team that actually cares, hydronic specialization, and a reputation built on doing things properly. Exactly what Piedmont homes deserve.
Radiant Heating Specialist
Most Piedmont homes have hydronic systems. We've spent 20+ years mastering exactly that kind of work.
A Team that Actually Cares
Our team of specialists handle your project with the care and attention to detail a Piedmont home deserves.
What Our Neighbors Are Saying
After hearing an increasingly loud hissing sound in my kitchen wall, I gave Afterglow a call, worried it was a gas leak. Mniska was prompt, professional and focused. He also took time to explain what steps he was taking to hone in on the problem. He was able to fix the leaky hot water pipe in my wall skillfully and smoothly.
Truly the best plumbing experience we've had! Well thought out and excellently installed new manifold for our radiant heat system. Plus a full redo of the electrical and control box. Cleaned up the mess and made it a fully functional and logical system. So glad we found afterglow heating and plumbing! Yarrow
Highly recommend Afterglow Radiant Heating! Mniska Lamb, the owner, quickly diagnosed and fixed our intermittent hot water issue with our tankless system. He completed important maintenance, suggested valuable upgrades, and 

[... 1117 more characters ...]
```

<!-- LABELS url=https://callafterglow.com/service-areas/piedmont -->
- answer_first_lead: ____
- self_contained_chunks: ____
- definition_first: ____
- expert_commentary: ____
- original_data: ____
- external_citations: ____
<!-- /LABELS -->
