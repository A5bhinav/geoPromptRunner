# Content-judge labels — MODEL PASS (comparison only, NOT the gold set)

⚠️ **These are not gold labels and must never be used as the κ ground truth.** They were
produced by Claude reading the extracted page text, and the calibration gate exists to
measure whether the *judge* (also a language model) agrees with a *human*. Scoring one
model against another would measure shared failure modes, not correctness — the gate would
pass for reasons unrelated to the judge being right.

Their only purpose is to give Abhi something to diff his own labels against, and to
surface where a model and a human diverge.

**Disclosed contamination:** the labeller had previously seen the *aggregate* verdict
distribution the judge produced for this exact site (e.g. `definition_first` failing on 12
of 15 pages, `external_citations` on 12 of 15). Per-page assignments were not seen, but the
aggregate anchors expectations. Discount the agreement accordingly — a genuinely blind
second pass would be worth more.

Source: `docs/content-labeling-sheet.md` (callafterglow.com), pages 1–8.
Labelled against the six checks' sub-questions in `content_judge.CONTENT_CHECKS`.

---

## 1. https://callafterglow.com/ — homepage

| check | label | reasoning |
|---|---|---|
| answer_first_lead | partial | The specialty ("hydronic heating and plumbing", "20+ years") is stated up front, but wrapped in brand voice — "steady warmth, smooth flow, and lasting comfort … keeps flowing and glowing". Answer is present but not clean of preamble. |
| self_contained_chunks | pass | "What Our Neighbors Are Saying" and each testimonial stand alone and name their subject. |
| definition_first | fail | "Hydronic", "radiant heat" are used throughout and never defined. |
| expert_commentary | fail | Customer testimonials are not expert commentary or original analysis from the business. |
| original_data | fail | "20+ years" is a credential, not data. No method, results, or case study. |
| external_citations | fail | None. |

## 2. https://callafterglow.com/services — service

| check | label | reasoning |
|---|---|---|
| answer_first_lead | partial | Opening does say what they do ("hydronic system … pipes"), but immediately pivots to the "Afterglow Finish" brand frame. |
| self_contained_chunks | pass | "Specialist, Not a Jack-of-All-Trades", "Efficiency Without Compromise" etc. each name their subject. |
| definition_first | fail | No key term defined. |
| expert_commentary | fail | "20+ years focused exclusively on hydronic" is a claim about themselves, not analysis. |
| original_data | fail | No numbers tied to a method. |
| external_citations | fail | None. |

## 3. https://callafterglow.com/services/air-to-water-heat-pumps — service

| check | label | reasoning |
|---|---|---|
| answer_first_lead | pass | Question as the heading, answered in the first sentence, ~50 words, zero preamble. Textbook. |
| self_contained_chunks | pass | Single chunk, names its subject. |
| definition_first | partial | Defined by mechanism ("pulls heat from outdoor air and transfers it to water") and early — but not in "X is a …" form. The borderline call on this page. |
| expert_commentary | fail | The 3–4× COP figure is field common knowledge; no named expert or first-hand insight. |
| original_data | fail | A spec, not original testing, and unsourced. |
| external_citations | fail | None. |

## 4. https://callafterglow.com/services/boiler-installation-service — service

| check | label | reasoning |
|---|---|---|
| answer_first_lead | pass | Question, then "For most Bay Area homes with hydronic heating, yes." Direct and concise. |
| self_contained_chunks | pass | Single self-contained chunk. |
| definition_first | fail | "Condensing boiler" / "high-efficiency" never defined. |
| expert_commentary | partial | The regional judgment ("for most Bay Area homes … yes", 15-year payback framing) is mild original analysis; the efficiency figures are not. |
| original_data | fail | 90–95% vs 70–80% are specific but tied to no method or source. |
| external_citations | fail | "Many installs qualify for utility rebates" — unsourced. |

## 5. https://callafterglow.com/services/hydro-solar-systems — service

| check | label | reasoning |
|---|---|---|
| answer_first_lead | pass | States what it is and what they do in the first two sentences. |
| self_contained_chunks | pass | "What Makes a Home a Good Fit", "Good Solar Exposure", "How We Design and Install" — all named and standalone. |
| definition_first | pass | "Hydro solar uses rooftop collectors to heat water directly, which then feeds your radiant floors…", early, and explicitly distinguished from solar PV. |
| expert_commentary | partial | "Not every roof is right for solar thermal", "Solar thermal is engineering, not just installation" is real practitioner judgment — but no named expert quote. |
| original_data | fail | No figures, no case study. |
| external_citations | fail | None. |

## 6. https://callafterglow.com/services/hydronic-heating — service

| check | label | reasoning |
|---|---|---|
| answer_first_lead | pass | Question then direct answer, ~65 words. |
| self_contained_chunks | pass | Single chunk, names its subject. |
| definition_first | pass | "Radiant heating, also called hydronic heating, circulates hot water through pipes to radiators…" — definition-first, first sentence. |
| expert_commentary | partial | "The existing distribution can usually be preserved while upgrading" is locale-specific practitioner insight; no named quote. |
| original_data | fail | None. |
| external_citations | fail | None. |

## 7. https://callafterglow.com/services/plumbing — service

| check | label | reasoning |
|---|---|---|
| answer_first_lead | partial | Opens with an honest FAQ answer about emergencies — but that is a narrow sub-question, not the page's main one ("what plumbing do you do?"), which arrives later. |
| self_contained_chunks | **fail** | Several chunks are orphaned from their headings: "From slow under-sink drips to mystery water stains" and "Often related to aging galvanized lines, scale buildup, or pressure regulator issues" never name their subject. The clearest structural failure in the set. |
| definition_first | fail | No definitions. |
| expert_commentary | partial | "Many pre-1960s Bay Area homes still have iron water supply lines nearing the end of their life" is genuine diagnostic insight. |
| original_data | fail | None. |
| external_citations | fail | None. |

## 8. https://callafterglow.com/services/water-heaters — service

The strongest page in the set on Cat 4, and the weakest on hygiene — it opens with a
leftover editing instruction, `remove first person:`, left in the published text.

| check | label | reasoning |
|---|---|---|
| answer_first_lead | partial | Substantively strong lead (the 2027 rule stated immediately), but no framed question and a visible authoring artifact at the very top. |
| self_contained_chunks | partial | Coherent but one undivided wall — there are no real sections to be self-contained. |
| definition_first | pass | "zero-NOx (low-emission)" defined parenthetically; "This is a point-of-sale restriction — not a forced retrofit mandate" is a clear early definitional clarification. |
| expert_commentary | pass | First-person practitioner guidance: "In plain terms…", "2026 is genuinely your last window to replace it on your own terms." |
| original_data | partial | Specific figures ($3,500 delta, $2,000 25C credit, $1,000–$3,100+ TECH Clean California) tied to named programmes — but cited, not first-hand. |
| external_citations | pass | BAAQMD Rule 9-6, federal 25C, TECH Clean California, plus "confirm the latest with BAAQMD". |

---

## Where I expect a human to disagree with me

Worth checking these first when you diff — they are the calls I was least sure of, and
disagreement here usually means the *check definition* is ambiguous rather than that one
of us is wrong. Those are the ones to write down, because they become judge-prompt rules.

1. **Page 3 `definition_first`** — I said partial because the definition is functional
   ("it pulls heat from…") rather than "X is a …". A stricter reading is fail; a looser one
   is pass. This single ruling probably swings several pages.
2. **`expert_commentary` across pages 4–7** — I gave partial wherever a practitioner made a
   locale-specific judgement, on the "original analysis beyond common knowledge"
   sub-question, even with no named expert. If you require the named quote, all of these
   drop to fail.
3. **Page 8 `original_data`** — cited government/utility figures are specific and sourced
   but not first-hand. I said partial; "original" arguably requires their own data, i.e. fail.
4. **Homepage `answer_first_lead`** — what *is* a homepage's main question? I treated it as
   "who are you and what do you do". If you treat a homepage as exempt, this becomes unknown
   rather than partial.
