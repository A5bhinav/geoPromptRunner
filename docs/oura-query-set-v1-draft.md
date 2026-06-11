# Oura — Query Set v1 (DRAFT, awaiting human review + lock)

**Status:** DRAFT for review. Not locked. — **Drafted:** 2026-06-10 · **Cycle:** v1
**Client:** Oura · **Category:** smart ring · **Mode:** full instrument (N=45)
**Engines:** ChatGPT · Claude · Gemini · Perplexity (+ Google AI Overviews). One set, run identically across all — never tuned per engine.

> **Review gate (do this before lock):** read each query aloud — "would a real buyer actually type this to a chatbot?" Cut/fix any that fail, then we stamp `v1` + date and freeze. These are drafted in buyer voice from category knowledge; for a *real* client we'd source verbatim phrasing from their intake + Reddit/reviews with provenance URLs. For this proxy run, a light pass is fine.

---

## Brand roster + name variants (analyzer input)

| Brand | is_client | name_variants |
|---|---|---|
| Oura | yes | Oura, Oura Ring, Ōura, Oura Ring 5, Oura Ring 4 |
| Whoop | no | Whoop, WHOOP, Whoop band, Whoop 5.0 |
| Ultrahuman | no | Ultrahuman, Ultrahuman Ring Air, Ring Air |
| Samsung Galaxy Ring | no | Samsung Galaxy Ring, Galaxy Ring |
| RingConn | no | RingConn, RingConn Gen 2 |

*Watch for auto-discovered brands the engines name unprompted (Apple Watch, Fitbit, Garmin) — capture them, don't suppress them.*

---

## Bucket 1 · Problem-aware (8) — ~18%
*First-person buyer voice. Names no category, client, or brand. Tests whether Oura is even in the conversation before the buyer knows smart rings exist.*

| id | intent | query | weight | buyer-voice |
|---|---|---|---|---|
| pa-01 | problem_aware | why do I wake up exhausted even after sleeping 8 hours? | 1.0 | ✓ |
| pa-02 | problem_aware | how can I figure out why my sleep is so bad lately? | 1.0 | ✓ |
| pa-03 | problem_aware | what's the best way to track my sleep and recovery without wearing a watch? | 1.0 | ✓ |
| pa-04 | problem_aware | how do I know if I'm overtraining and need to rest? | 1.0 | ✓ |
| pa-05 | problem_aware | how can I actually improve my deep sleep? | 1.0 | ✓ |
| pa-06 | problem_aware | is there a way to tell if my body is recovered enough to work out hard today? | 1.0 | ✓ |
| pa-07 | problem_aware | how can I keep track of my stress levels during the day? | 1.0 | ✓ |
| pa-08 | problem_aware | what should I look at to understand my overall health day to day? | 1.0 | |

## Bucket 2 · Category / solution-aware (14) — ~31%
*One head query; every other carries a real-segment qualifier. 2 year-stamps (cat-09, cat-10) to bait freshness/Ring-5 staleness.*

| id | intent | query | weight | persona | buyer-voice |
|---|---|---|---|---|---|
| cat-01 | category | best smart ring | 1.5 | — | ✓ |
| cat-02 | category | best smart ring for sleep tracking | 1.5 | sleep-focused | ✓ |
| cat-03 | category | best smart ring for athletes and recovery | 1.5 | athlete | ✓ |
| cat-04 | category | best smart ring for women's health and cycle tracking | 1.5 | women's health | |
| cat-05 | category | best smart ring with long battery life | 1.5 | battery-focused | ✓ |
| cat-06 | category | best smart ring without a monthly subscription | 1.5 | cost-conscious | ✓ |
| cat-07 | category | most accurate smart ring for sleep | 1.5 | accuracy-focused | ✓ |
| cat-08 | category | best budget smart ring | 1.5 | budget | ✓ |
| cat-09 | category | best smart ring 2026 | 1.6 | — | ✓ |
| cat-10 | category | what's the newest smart ring in 2026? | 1.6 | — | ✓ |
| cat-11 | category | best health tracker you don't wear on your wrist | 1.5 | — | ✓ |
| cat-12 | category | what's a good smart ring for everyday health tracking? | 1.5 | — | |
| cat-13 | category | best smart ring for beginners | 1.5 | beginner | |
| cat-14 | category | top rated smart rings right now | 1.5 | — | |

## Bucket 3 · Comparison (12) — ~27%
*Every competitor appears ≥1×. cmp-08/09/11 leave Oura unnamed (≥2 required) to test unprompted surfacing.*

| id | intent | query | weight | buyer-voice |
|---|---|---|---|---|
| cmp-01 | comparison | Oura Ring vs Whoop for recovery | 1.8 | ✓ |
| cmp-02 | comparison | Oura vs Samsung Galaxy Ring — which is better? | 1.8 | ✓ |
| cmp-03 | comparison | Oura Ring vs Ultrahuman Ring Air | 1.8 | ✓ |
| cmp-04 | comparison | Oura vs RingConn for sleep tracking | 1.8 | |
| cmp-05 | comparison | best alternatives to the Oura Ring | 1.8 | ✓ |
| cmp-06 | comparison | Oura Ring alternatives without a monthly subscription | 1.8 | ✓ |
| cmp-07 | comparison | is the Samsung Galaxy Ring better than Oura? | 1.8 | ✓ |
| cmp-08 | comparison | Whoop vs Ultrahuman for athletes | 1.8 | ✓ |
| cmp-09 | comparison | Samsung Galaxy Ring vs RingConn | 1.8 | |
| cmp-10 | comparison | which is better value, Oura or Ultrahuman? | 1.8 | ✓ |
| cmp-11 | comparison | cheaper alternatives to Whoop | 1.8 | ✓ |
| cmp-12 | comparison | Oura Ring vs Apple Watch for sleep tracking | 1.8 | ✓ |

## Bucket 4 · Brand / bottom-funnel (7) — ~15%
*Probes the claims most damaging if wrong: price, the required membership, current model, flagship capability. This is where accuracy flags surface.*

| id | intent | query | weight | targets claim |
|---|---|---|---|---|
| brd-01 | brand | is the Oura Ring worth it? | 2.0 | overall |
| brd-02 | brand | how much does the Oura Ring cost? | 2.0 | pricing |
| brd-03 | brand | does the Oura Ring require a subscription? | 2.0 | required membership |
| brd-04 | brand | what's the newest Oura Ring right now? | 2.0 | current model (Ring 5) |
| brd-05 | brand | Oura Ring review: pros and cons | 2.0 | overall |
| brd-06 | brand | is the Oura Ring good for sleep tracking? | 2.0 | flagship capability |
| brd-07 | brand | is the Oura Ring membership worth paying for monthly? | 2.0 | membership + price |

## Bucket 5 · Adjacent-authority (4) — ~9%
*No brand named. Topics Oura could plausibly own as the authority.*

| id | intent | query | weight | buyer-voice |
|---|---|---|---|---|
| adj-01 | adjacent_authority | how does heart rate variability relate to recovery? | 1.0 | ✓ |
| adj-02 | adjacent_authority | what's a healthy resting heart rate during sleep? | 1.0 | ✓ |
| adj-03 | adjacent_authority | how much deep sleep do I actually need each night? | 1.0 | ✓ |
| adj-04 | adjacent_authority | how can I use body temperature to track my menstrual cycle? | 1.0 | |

---

## Self-checked QA (vs. Question-Set Schema v1 §6)

- ✅ **Counts** match allocation: 8 / 14 / 12 / 7 / 4 = 45. Buckets 2+3 = 26 (58% ≥ 55%).
- ✅ **One intent tag** per query; no unfilled `{slots}`.
- ✅ **Every competitor** named ≥1×: Whoop (cmp-01/08/11), Ultrahuman (cmp-03/08/10), Samsung (cmp-02/07/09), RingConn (cmp-04/09).
- ✅ **Client named only** in bucket 4 + client-named comparisons (problem-aware, category, adjacent name no brand).
- ✅ **≥2 comparison queries leave Oura unnamed:** cmp-08, cmp-09, cmp-11 (3).
- ✅ **Year-stamps:** cat-09, cat-10 (freshness/Ring-5 bait).
- ✅ **≥1/3 verbatim/near-verbatim buyer voice:** ~26 flagged (≥15 needed).
- ⏳ **Read-aloud test:** pending your review.
- ⚠️ **Near-dup note:** brd-02 (hardware cost) vs brd-07 (membership cost) and cat-02 (sleep) vs cat-07 (accuracy-for-sleep) are close but intentionally distinct — confirm you're OK keeping both.
- ⏳ **Lock:** pending approval → then `v1` + date.

---

## Recommended thin-pass subset (12) for the first cheap run
*Walk-before-sprint: run these 12 at 1 run × 3 engines first to prove the chain end-to-end, then scale to the full 45 × 3 runs × all surfaces. Chosen for label variety — likely recommendations, burials, absences, and accuracy flags.*

`cat-01`, `cat-02`, `cat-09`, `cmp-01`, `cmp-02`, `cmp-08`, `brd-01`, `brd-03`, `brd-04`, `pa-01`, `pa-03`, `adj-01`

---

*On approval I emit this as the runner-ready `sample_queries.json` shape (query_id / intent / text / weight / persona), plus the claim-ID'd Oura fact sheet for the analyzer, and we run it.*


Yes — that's exactly the end-to-end test, and everything it needs is in place: live keys for all engines, the fact sheet and competitor roster for Oura, the runner, the judge, the calibration harness, and the CLI/UI. Nothing's blocking it.
The full loop, with who does what:

I draft the queries (sourced from real buyer language, per the generation plan) → you review/approve. Light touch for a proxy.
I run them through the engines — via the CLI directly, or, since you mentioned it, I generate the upload CSV and we run it through the app to test that path too. Either works; the CSV route also exercises the front end, which is a bonus for an end-to-end test.
We review the raw answers together — I hand you the answers (pre-loaded in the gold-set Sheet format), and you and Abhi read them. This is where two things happen at once: you're sanity-checking that the engines returned sane output (end-to-end working), and it's your labeling session (the gold set).
The judge runs on those same answers → I show you its verdicts next to the raw answers.
Calibration compares the judge's labels to yours → the agreement number. That single number is the end-to-end verdict: if the judge agrees with your human reads, the whole pipeline — queries → engines → judge → report — works.
The report renders (CLI markdown or the UI charts) so you see the actual deliverable a client would get.

So you'd be testing all four layers in one pass: query generation, the stateless engine runner, the judge, and the report. The two human checkpoints (approve queries, label answers) are the same two we keep landing on — they're not test overhead, they're the parts that require your judgment.
One scoping call worth making so the first run is fast and cheap: do a thin pass first — ~10–12 queries, 1 run each, the three core engines (OpenAI, Anthropic, Gemini) — to confirm the whole chain works before spending on the full 45 × 3-runs × all-surfaces version. Walk before sprint; if the thin pass holds together, scale up with confidence.