# Model selection — prompt runner + judge (2026-08-01)

**Question:** which models should the runner and the judge use, keeping cost low without
giving up accuracy.

**Method.** Read the code as-is (`src/engines/*`, `src/pipeline/judge.py`,
`src/config/settings.py`, `src/pipeline/cost.py`), re-derived every price from the four
providers' live pricing pages on 2026-08-01, and rebuilt the per-call cost model from
token counts measured out of the repo's own artifacts rather than the estimates in
`cost.py`. No API spend.

**The one-line answer:** the *engine* pins are a clear, cheap decision and should move
now; the *judge* model is not decidable on evidence today, because every flag metric it
would be decided on is under the repo's own quoting freeze — and that freeze now collides
with a September retirement deadline on `claude-sonnet-4-5`. Building a flag-powered gold
set is the blocking task, not a model bake-off.

Token inputs to the cost model, all measured from repo artifacts:

| Quantity | Value | Source |
|---|---|---|
| answer length, pooled | 640 tok mean (n=80) | `data/fort_gold.json`, `data/oura_gold.json` |
| answer length, per engine | anthropic 294 · openai 468 · perplexity 415 · **gemini 1,385** | same, n=20 each |
| fact sheet | 1,655–1,927 tok | `docs/fact-sheet-*.md`, sheet embedded in `fort_gold.json` |
| `_ACCURACY_BLOCK` / `_RUBRIC_TAIL` / `_ANSWER_HEAD` | 1,964 / 286 / 10 tok | `src/pipeline/judge.py` |
| `anthropic_search` call | 10,928 in / 534 out + 1 search | measured live 2026-07-30, `cost.py:30` |

That per-engine spread matters more than it looks: **Gemini's answers are 4.7× longer
than Anthropic's**, so a per-call cost table that assumes one output length (which is
what `cost.py` and my own first pass both did) mis-ranks the surfaces.

---

## 1. The five findings that decide this

### 1. You cannot pick the judge model on evidence right now

Every comparison that would justify a judge model — Haiku's 43% flag recall vs Sonnet's
95%, the cascade's 100%, the verifier's 42%→80% precision lift — is a **flag precision or
recall figure on a gold set**, and `docs/project-queue.md:20-30` freezes exactly those:

> *"quote no flag precision, recall or severity figure for either ICP. … Fort carries 3
> gold flags; two identical runs returned precision 29% then 43%, recall 67% then 100%,
> on the same inputs with the same settings. One flag moves the metric by 14 points."*

The freeze is not "we haven't measured yet" — the W3.4 re-run **completed 2026-07-31**
and structural agreement is quotable again (Fort 94/86/93, Oura 99/90/94). The freeze is
"the gold sets are too thin in flag-bearing items for the metric to mean anything."

So: this document does **not** re-litigate Sonnet vs Haiku. The current configuration
fails toward expensive-and-correct, which is the right default for output that accuses a
paying client of an error. Hold it, and go build the measurement.

### 2. The cascade costs 2.44× the default judge, not less

`JUDGE_CASCADE` was designed and validated (2026-06-28) *before* the single-judge path
moved its rubric into a `cache_control` system block. That change made the expensive path
cheap and left the cascade paying full uncached input for the fact sheet on every answer.
`judge.py` contains exactly one `cache_control` (line 710, in `_single_judge_messages`);
`_judge_cascade` and `_verify_flags` pass bare system strings.

It is off by default, which is correct. Its measured advantage (100% flag recall vs 95%)
is under the §1 freeze. **Recommendation: leave it off and do not invest in it.** If it
is ever revived, the fix is structural, not a model swap — move `_ACCURACY_BLOCK` + the
fact sheet into a cached system block on the accuracy pass, which brings it to 0.93× the
default. Even then it is not worth a second cache identity.

### 3. `cost.py` under-estimates in three places, and under-estimates are the dangerous direction

`ROUGH_COST_PER_CALL` feeds `MAX_AUDIT_COST_USD`. Recomputed with per-engine output
lengths and today's prices:

| Line | `cost.py` | Modeled | Verdict |
|---|---|---|---|
| `openai` | $0.0015 | $0.00057 | 2.65× over |
| `anthropic` | $0.0120 | $0.00447 | 2.68× over |
| `perplexity` | $0.0060 | $0.00543 | 1.10× over — accurate |
| `anthropic_search` | $0.0510 | $0.05079 | 1.00× — accurate |
| **`gemini`** | **$0.0020** | **$0.00347** | **0.58× — UNDER** |
| **`gemini_grounded`** | **$0.0100** | **$0.0385** (beyond free tier) | **0.26× — UNDER** |
| **`JUDGE_COST_PER_CALL`** | **$0.0030** | **$0.00984** (default path, verifier on) | **0.30× — UNDER** |

The two accurate lines are the two that were derived from live measurement rather than
estimated. That is the pattern to copy. The `gemini` line is under because Gemini's
answers are 4.7× longer than the table's implicit assumption; the judge line is under
because it predates both prompt caching and the verifier being on by default.

### 4. The judge has a September deadline that collides with the frozen gold set

`claude-sonnet-4-5-20250929` carries a tentative retirement floor of **not sooner than
2026-09-29** — under two months. The held-constant judge has to move, and the evidence
needed to move it responsibly does not exist yet (finding 1). That ordering is the whole
plan: **gold set first, then model decision, before late September.**

### 5. The dated-snapshot rule has been overtaken by the industry

`src/engines/model_pins.py` exists to make an undated pin "a decision with a written cost,
never an accident," enforced by `tests/test_isolation.py`. As of today:

| Provider | Dated snapshots on current-generation models? |
|---|---|
| Anthropic | **No** — `claude-sonnet-5`, `opus-5`, `opus-4-6/7/8`, `sonnet-4-6` are their own canonical IDs. Only the retiring 4.5 line is dated. |
| OpenAI | **No** for the 5.6 family — each model page's Snapshots section lists only the bare ID. |
| Google | **No** for stable models; dated forms exist only on previews. |
| Perplexity | **No** — floating aliases only. |

The rule now has exactly one effect: **it pins the platform to a legacy generation on
every surface.** That is a real cost, and it is not the cost the rule was written to buy.
See §5.

---

## 2. Judge — recommendation

### Hold the current configuration

- **Single-model judge** (`JUDGE_CASCADE=0`) — already default, correct (finding 2).
- **`JUDGE_MODEL=claude-sonnet-4-5-20250929`** — hold until the gold set can justify a
  move. Not because Sonnet 4.5 is proven better than the alternatives, but because it is
  the configuration the one *quotable* measurement (2026-07-31 structural agreement) was
  taken under, and changing it discards that baseline for nothing.
- **`JUDGE_VERIFY=1` with a Sonnet-class verifier** — already default since 2026-07-31.
  Cost is ≥+25% on the judge. The precision lift that justified it is frozen, but the
  design argument stands on its own: `_verify_flags` only ever *removes* flags and
  `_verdict_keep` keeps on any failure, so it cannot cost recall by construction.
  Recall-safe-by-construction is a property you can assert without a gold set.

**Do not switch to Haiku for the accuracy block.** Not on the frozen numbers, and not on
first principles either — the whole point of the judge is the flag, and the one thing
everyone agrees on is that the cheap model is weaker exactly there.

**Do not use Opus 5.** 1.67× the cost with no evidence it helps on this task.

### Cost per judged answer (fact sheet present), modeled

| Configuration | $/answer | vs current |
|---|---|---|
| **single Sonnet 4.5 — current default** | **$0.00787** | 1.00× |
| single Sonnet 5 (August price) | $0.00525 | **0.67×** |
| single Sonnet 5 (from 2026-09-01) | $0.00787 | 1.00× |
| single Haiku 4.5 | $0.00262 | 0.33× |
| single Opus 5 | $0.01312 | 1.67× |
| cascade Haiku + Sonnet 4.5 — *as built* | $0.01922 | **2.44×** |
| cascade if its passes were cached | $0.00735 | 0.93× |
| single Sonnet 4.5 with caching removed | $0.02035 | 2.58× |

Verifier add-on: **≥$0.00197/answer on Sonnet 4.5 (≥+25%)**. Stated as a floor because
the 7 flags in `fort-2026-07-31.md` are *post*-verifier survivors while `_verify_flags`
bills one call per *proposed* flag — the true rate is higher by an unknown factor.

Per 145-answer audit: current **$1.43**, Sonnet 5 **$0.95**, cascade **$3.07**.

### When the gold set is ready, Sonnet 5 is the likely answer — with one real cost

Through 2026-08-31 Sonnet 5 is **33% cheaper** than Sonnet 4.5 for a newer model
($2/$10 vs $3/$15). From 2026-09-01 it equalizes and the argument becomes purely "4.5 is
retiring." Either way it is the obvious candidate.

**The cost, stated plainly: Sonnet 5 rejects a non-default `temperature` with a 400.**
`judge.py:_call_flags` handles this correctly — `"claude-sonnet-5"` matches nothing in
`_TEMPERATURE_ACCEPTED`, so the parameter is omitted — but omitting it means the judge
samples at the API default of 1.0, and `_call_tool`'s own docstring records what that
does: *"at the API default of 1.0 the flag list swung run-to-run."*

- *Blunted:* the judge cache means each unique answer is judged once, so a delivered
  report stays internally consistent. Thinking can still be disabled on Sonnet 5, and the
  code already sends `{"type":"disabled"}` — the forced-tool path is unaffected.
- *Not blunted:* **calibration itself gets noisier**, on top of the sample-size noise
  that already caused the freeze. Fort already swung 14 points between two *identical*
  temperature-0 runs. Adding sampling variance to that is the wrong order of operations —
  which is another reason the gold set comes first.

There is no way around this: **every current-generation Anthropic model rejects
temperature.** Staying on 4.5 buys determinism until late September and no longer.

### Two code fixes worth more than any judge model swap

- **The verifier prefix is uncached.** It re-sends the fact sheet (~1,900 tok) in the
  user prompt on every flag. Caching it takes a verifier call from $0.0113 to $0.0045.
  Only pays off if ≥2 flags land inside the 5-minute TTL — worth doing, not worth rushing.
- **Concurrent cold-start cache misses.** `judge_results` fans out over a
  `ThreadPoolExecutor` at `ENGINE_PROVIDER_CONCURRENCY` (default **4**) with no warm-up
  (`judge.py:1002-1009`), so 3 of the first 4 workers pay the 1.25× write price on the
  ~4,600-token prefix instead of the 0.1× read. Avoidable spend ≈ **$0.05/run** —
  small, and fixed by judging one answer before releasing the pool.

---

## 3. Prompt runner — recommendation per surface

| Surface | Current pin | Modeled $/call | Recommendation |
|---|---|---|---|
| `openai` | `gpt-5.6-luna` | $0.00057 | **Keep — but A/B against Terra once** (§3.3). |
| `anthropic` | `claude-sonnet-4-5-20250929` | $0.00447 | **→ `claude-sonnet-5`.** −33%, matches the consumer surface. Needs a code change. |
| `gemini` | `gemini-2.5-flash` | $0.00347 | **→ `gemini-3.6-flash`.** +$1.01/audit; closes a two-generation fidelity gap. `gemini-3.5-flash-lite` is the zero-cost alternative (§3.1). |
| `perplexity` | `sonar` | $0.00543 | **Keep the model; audit the API surface** — Sonar Chat Completions is deprecated in favour of the Agent API. Liveness risk, not a model choice. |
| `anthropic_search` | `claude-sonnet-4-5-20250929` | $0.05079 | **→ `claude-sonnet-5`.** −27% (−$1.98/audit), **no code change** — this adapter already sends no temperature and declares `SAMPLING = "default"`. |
| `gemini_grounded` | `gemini-2.5-flash` | $0.0385 beyond free tier | **Fix the estimate first**, then decide by volume (§3.2). |
| `openai_search` | `gpt-5-search-api-2025-10-14` | ~$0.019 | **Not a model problem — a tier problem** (§3.4). |

### Per-audit engine spend (29 queries × K=5 = 145 cells per engine)

| Set | Cost | Δ |
|---|---|---|
| Current 4-engine parametric set | $2.02 | — |
| Sonnet 5 + `gemini-3.6-flash` | $2.81 | **+$0.79** |
| Sonnet 5 + `gemini-3.5-flash-lite` | **$1.81** | **−$0.22** |

Component moves: `anthropic`→Sonnet 5 **−$0.22**; `gemini`→3.6-flash **+$1.01**;
`gemini`→3.5-flash-lite **$0.00**; `openai`→Terra **+$0.74**.
Optional surfaces: `anthropic_search` **$7.37 → $5.39**; `openai_search` ~$2.76.

⚠️ **These projections assume the new model is as verbose as the old one.** Output length
drives the cost (input is ~20 tokens), and the per-engine lengths above were measured on
the *current* pins in gold sets untouched since 2026-06-19. If `gemini-3.6-flash` is
materially chattier or terser than 2.5-flash, the +$1.01 moves with it. This is the
largest single source of error in the engine numbers, and one cheap run settles it.

### 3.1 `gemini` — the fidelity gap is the point, and there's a free option

Three-way choice, all current pricing:

| Pin | Generation | $/call | $/audit |
|---|---|---|---|
| `gemini-2.5-flash` (current) | two behind | $0.00347 | $0.50 |
| `gemini-3.5-flash-lite` | current, lite tier | **$0.00347** | **$0.50** |
| `gemini-3.6-flash` | current, matches consumer app | $0.01042 | $1.51 |

`gemini-3.5-flash-lite` is priced **identically** to `gemini-2.5-flash` ($0.30/$2.50), so
moving off a two-generation-old model costs literally nothing. But flash-lite is not what
a person gets in the Gemini app either, and the product's claim is "this is what Gemini
says about you." **Recommend `gemini-3.6-flash`** and treat +$1.01/audit as noise against
a bill where `anthropic_search` alone is $7.37 — with flash-lite as the fallback if you
want the generation upgrade for free.

### 3.2 `gemini_grounded` — the free-tier fork is the whole decision

Google prices grounding by generation, with asymmetric free allowances:

| Generation | Free allowance | Paid rate |
|---|---|---|
| Gemini 3.x | **5,000 search requests / month** | $14 / 1,000 |
| Gemini 2.5 | **1,500 requests / day** (≈45,000/mo) | $35 / 1,000 |

At 145 grounded cells per audit: the 3.x monthly allowance covers ~34 audits/month; the
2.5 daily allowance covers ~10 audits/day. So "**$14 beats $35**" is only true past the
free tier, and the free tiers favour opposite volume shapes.

**Recommendation: leave `gemini_grounded` on 2.5 for now** — at a manual-audit-service
volume it is plausibly free either way — and fix `cost.py`'s $0.010 to a tiered figure
($0 within allowance, $0.0385 beyond) so the spend guard stops silently under-reporting.
Revisit if monthly grounded volume crosses ~5,000 requests.

⚠️ **Unverified and decision-flipping:** whether the 2.5 "1,500 RPD" allowance applies on
a *billed* account or only on the free tier. Check the Google Cloud billing statement
before relying on it.

### 3.3 `openai` — Luna is defensible, but prove it once

`gpt-5.6-luna` is OpenAI's *cost-optimized* tier; ChatGPT's consumer default is reportedly
GPT-5.5 Instant (unverified — the Help Center 403s). Terra costs 10× Luna (+$0.74/audit).

No API model reproduces the ChatGPT product surface anyway — system prompt, memory and
routing all differ — so the pin is a proxy either way, and a 10× premium for a proxy that
is still a proxy is hard to defend. But it is cheap to check: run the existing 29-query
set on Luna and Terra and compare the brand read. If `present`/`prominence` agree, Luna
is free accuracy and you can say so in the methodology; if they diverge, pay the $0.74.
**Cost: ~$1.16 of engine spend**, no gold labels needed (it only asks whether two models
produce the same read). Add ~$2.30 if you also judge both sets.

### 3.4 `openai_search` — do not solve this with a model

The binding constraint is **6,000 tokens/minute** on this account against a **17,227
token** single call (`prompt_runner.py:19-35`). Both `gpt-5-search-api` and the retired
`gpt-4o-search-preview` carry the same cap, so it is tier, not model. Raise the OpenAI
tier or drop the surface; a cheaper model does not move a token-rate cap.

Housekeeping: `gpt-4o-search-preview` was shut down **2026-07-23**, and
`openai_search_engine.py:30` still describes it as a live alternative.

---

## 4. The dated-snapshot rule needs a written decision

Finding 5 leaves the platform with a choice it should make deliberately rather than by
letting a test decide it: **stay a generation behind everywhere, or replace "dated ID"
with a drift control that still exists.**

The honest replacement is to stop treating a dated ID as *the* drift control and start
treating it as *one* of several, naming the control per surface:

- **Response fingerprints** where the provider returns one — not OpenAI 5.6, where
  `system_fingerprint` is absent from the documented response object.
- **A drift canary** — a fixed probe set with known-stable answers, run at the start of
  every cycle; a shift is a drift signal regardless of what the model ID says.
  ⚠️ Note: `src/verification/canary.py` is **not** this. It is the isolation probe (Test
  A) — it plants `zanzibar-cerulean-47` in one call and checks a second call cannot echo
  it, i.e. it tests memory leakage, not drift. `src/verification/determinism.py` /
  `scripts/run_determinism.py` is closer to the right shape. A drift canary would be new
  work, built on that pattern.
- **Recording `engine_models` per run** — already done, still useful for renames.

**Recommendation:** widen `UNDATED_PINS` from "reviewed exceptions" to "the pin registry,
with the drift control named per surface," keep `tests/test_isolation.py` enforcing that
*every* surface names one, and build the drift canary. That preserves what the rule was
actually protecting — no accidental pins — while letting the platform run current models.

---

## 5. What has to be measured, in order

1. **Build a flag-powered gold set.** This is the blocking item for every judge decision
   and `project-queue.md:29-30` already names it: *"the fix is not a better judge, it is
   a gold set with enough flag-bearing items to measure one — build the local set
   (`data/local_gold.json`) accordingly."* Fort has 3 gold flags; one flag moves precision
   by 14 points. Target enough flag-bearing items that a single label cannot swing the
   metric — and note Oura's separate finding, **severity agreement 18% exact**, which is
   worse than the detection it grades and needs its own labels.
2. **Re-baseline Sonnet 4.5** on the new set with `isolated_cache()`. This re-establishes
   what "no regression" means on the metric that matters.
3. **Then evaluate Sonnet 5** on the same set, **n≥3 per item, reporting the spread**,
   because temperature is no longer pinnable. ⚠️ *This does not work as written today:*
   `calibrate()` calls `judge_answer_cached` (`calibration.py:402`) and `isolated_cache()`
   dedupes within a run — three repeats of an identical item return one cached verdict and
   the spread is zero by construction. Needs `cache=None` or a per-repeat key first.
4. **Ship gate:** Sonnet 5 matches Sonnet 4.5 on flag recall, does not regress κ on
   present/prominence/framing, and its run-to-run spread is small enough to state in the
   methodology. If the spread is large, stay on 4.5 until retirement — that just makes
   the September deadline real.
5. **Independently and cheaply:** the Luna-vs-Terra engine A/B (§3.3) and a one-run check
   of `gemini-3.6-flash`'s answer length (§3). Neither needs gold labels.

Judge spend for the campaign is ~$0.95–$1.43 per 145-answer pass, so a four-configuration
sweep is a few dollars, and the cache makes re-runs free.

---

## 6. Change list

| # | Change | Effect | Blocked on |
|---|---|---|---|
| 1 | Fix `JUDGE_COST_PER_CALL` (0.003 → ~0.0098 with verifier on) | Closes a 3.3× under-estimate in the spend guard | Nothing |
| 2 | Fix `gemini` (0.002 → ~0.0035) and `gemini_grounded` (0.010 → tiered) in `cost.py` | Closes the other two under-estimates | Verifying the 2.5 free-tier terms on a billed account |
| 3 | Repin `anthropic_search` → `claude-sonnet-5` | −$1.98/audit; no code change needed | An `UNDATED_PINS` entry |
| 4 | Repin `gemini` → `gemini-3.6-flash` | +$1.01/audit; closes a two-generation fidelity gap | Nothing (`3.5-flash-lite` is the $0 fallback) |
| 5 | Repin `anthropic` → `claude-sonnet-5` | −$0.22/audit; matches the consumer surface | **Code change:** `anthropic_engine.py:53` sends `temperature`, which 400s on Sonnet 5. Drop it, add `SAMPLING = "default"` (it currently inherits `"pinned"` from `base.py:70`), update the report methodology. |
| 6 | Build a flag-powered gold set | Unblocks every judge decision | **Labeling time.** On a September clock. |
| 7 | Move `JUDGE_MODEL` → `claude-sonnet-5` | −33% judge cost through August; ahead of the 4.5 retirement floor | #6, and fixing the `isolated_cache()` repeat problem in §5.3 |
| 8 | Rewrite the L3 dated-pin rule around a drift canary | Lets the platform run current models everywhere | A written decision from Abhi + Josh |
| 9 | Luna-vs-Terra A/B on `openai` | Justifies the cheap pin in writing, or buys back fidelity for $0.74/audit | ~$1.16 of API spend |
| 10 | Fix the dead-model comment at `openai_search_engine.py:30` | Stops the code describing a retired model as a live option | Nothing |

**If only three things get done:** #1+#2 (the spend guard is lying in the dangerous
direction), #3+#4 (a generation upgrade on two surfaces for +$0.79 net, or −$0.22 with
the flash-lite fallback), and **#6** — because it is the only one on a deadline and
nothing about the judge can be decided without it.

---

## Appendix — sources and what was *not* verified

Pricing and availability verified live 2026-08-01:
[Anthropic models](https://platform.claude.com/docs/en/about-claude/models/overview) ·
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) ·
[Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) ·
[Anthropic thinking](https://platform.claude.com/docs/en/build-with-claude/thinking) ·
[OpenAI pricing](https://developers.openai.com/api/docs/pricing) ·
[OpenAI models](https://developers.openai.com/api/docs/models) ·
[GPT-5.6 announcement](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/) ·
[OpenAI web search tool](https://developers.openai.com/api/docs/guides/tools-web-search) ·
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) ·
[Gemini models](https://ai.google.dev/gemini-api/docs/models) ·
[Perplexity pricing](https://docs.perplexity.ai/docs/getting-started/pricing.md) ·
[Perplexity models](https://docs.perplexity.ai/getting-started/models)

**Not verified — do not build on these without checking:**

- Whether Gemini 2.5's 1,500 RPD grounding allowance applies on a billed account (§3.2).
  This one flips a recommendation.
- Whether `gemini-3.6-flash` produces answers of similar length to `gemini-2.5-flash`.
  This drives the +$1.01 figure.
- Whether `gpt-5-search-api-2025-10-14` is still served. Current OpenAI docs list only
  the undated `gpt-5-search-api`; one fetch of the pricing page did not list the model at
  all, while a second source gave $1.25/$10.
- Whether GPT-5.6 accepts `temperature` — absent from the model pages, not affirmatively
  denied. One cheap Luna call settles it.
- ChatGPT's and Perplexity's consumer default models (both providers' pages are stale or
  403). Gemini's app default is reported as 3.6-flash by secondary sources only.

**Token counts are `chars/4` approximations**, not tokenizer output. Fine for ranking
configurations 2–3× apart; not fine for quoting a per-audit bill to a client.

**No accuracy figure in this document is new.** The only quotable calibration result in
the repo is structural agreement from 2026-07-31 (Fort 94/86/93, Oura 99/90/94). Every
flag metric remains frozen per `docs/project-queue.md:20-30`.
