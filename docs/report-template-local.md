# Local Audit Report — structure and rules (W5.2)

The local variant of the client report. Same instrument, different reader: a shop owner
who wants to know *whether customers are being sent to someone else*, not a growth lead
reading a dashboard.

Both report shapes stay live. This one is selected on `business_kind == "local_service"`.

---

## What changes from the consumer report, and why

| Consumer report | Local report | Why |
|---|---|---|
| "buyers" | "customers" / "homeowners" | The owner's own word for the person calling |
| Share-of-voice chart | Red/yellow/green source checklist | *"Owners respond to named competitors and phone-call economics, not dashboards"* |
| "Appears in X of N queries" | **No aggregate ratio** | The denominator is a query set *we* chose. It reads as a visibility rate and is not one |
| Trustpilot / App Store / Play Store | GBP, Yelp, BBB, Angi, Thumbtack, Facebook, Bing Places, Nextdoor | The directories AI actually cites for local |
| Pricing / features / version accuracy | Hours, service area, phone, licensing | What a customer acts on when their AC just died |

---

## Section order

**1 · The one answer that matters.** A single verbatim engine answer to `best {trade} in {city}` with the named rival highlighted and the client absent. Prominence-graded copy — "sending your customers to X" only when the judge saw X recommended first (`localHeadline`, `copy.ts`). No summary statistics above this; the artifact's whole job is the visceral moment.

**2 · Reproducibility.** How many times we asked, and how many times the result held. Printed only at `runsObserved >= 2 && runsConfirming == runsObserved`, per `reproNote`. **Carry the sampling note** from `local_sampling.sampling_note(trade)` — if the trade has no measured determinism band, the report must say so rather than implying the number is settled.

**3 · Where AI looks for a {trade} in {city}.** The red/yellow/green checklist over `LOCAL_REVIEW_PLATFORMS`. GBP is its own row, visually separated — it is weighted 3.0 in the rubric, matching SSR, because the local pack and the AI answers built on it are generated *from* the profile.

**4 · What AI gets wrong about you.** The four local accuracy flags (`wrong_hours`, `wrong_service_area`, `wrong_contact`, `licensing`), each with the verbatim contradicted fact-sheet line. Usually the most alarming section for an owner: an AI confidently giving customers the wrong hours or a dead phone number is a lost job today.

**5 · What to fix, in order.** The roadmap from `build_site_audit_roadmap(..., business_kind="local_service")`. GBP first when missing; NAP consistency next.

**6 · How this was measured.** Engines, query set, runs per query, date, location. The location must be printed — a local result from an unpinned locale is not a local result.

---

## Hard rules

These are not style preferences; each one exists because breaking it produces a claim we cannot back.

1. **Never print an aggregate appearance ratio.** See the table above.
2. **Never claim more than the judge measured.** All verbs grade off judged prominence via `competitorVerb` / `competitorProminenceWord`. The local path inherits this — it does not get its own ungraded copy.
3. **Never name a competitor that did not come from a captured local-pack entity.** `attachLocalCompetitors` is the only path; it throws rather than emit a rival-less teaser.
4. **Never quote an accuracy or agreement figure until W3.4 calibration passes.** The Phase-3 judge bump was global, so this freeze covers both ICPs. Mention, prominence and framing are unaffected and remain quotable.
5. **Never report a cadence delta as progress without a measured noise floor.** `local_cadence_warning(trade)` returns the banner that must appear otherwise — local answers churn heavily between runs, so an unqualified "improved" is more likely jitter than progress.
6. **Print the location, always.** An audit whose location was `None` measured an unpinned locale and is not a local audit.

---

## Dollar framing

The strategy doc calls for phone-call economics. **We do not have this business's job value**, so any dollar figure would be invented — the same class of error as an unmeasured prominence verb.

If dollar framing is added later it must come from a constants module with a cited source (industry-average job value per trade), be labelled as an industry average rather than this shop's number, and never be multiplied by our own query-set denominator to manufacture a "lost revenue" total. Until then, section 1's named-rival moment carries the weight on its own.
