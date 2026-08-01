# All-search engine set at 25 queries — cost table (rev. 2 · 2026-08-01)

Six surfaces, 25 queries, judge $0 via prejudge. All prices verified live 2026-08-01.

**What changed in rev. 2:**
- `openai_search` = **`gpt-5.6-luna` + Responses `web_search`**, not `gpt-5-search-api` (§3)
- `gemini_grounded` = **`gemini-3.6-flash`**, not `gemini-2.5-flash` (§4)
- Luna's price **settled at $0.20/$1.20** — OpenAI's model page is stale (§2)
- Gemini grounding **confirmed free at your volume** — you're Tier 1, $0.05 spend over 28 days (§4)

---

## 1. The table

`anthropic_search` on the current pin:

| Surface | Model / vendor | $/call | Share | K=5 | K=3 | K=2 | K=1 |
|---|---|---|---|---|---|---|---|
| `anthropic_search` | `claude-sonnet-4-5` | $0.0508 | 58.2% | $6.35 | $3.81 | $2.54 | $1.27 |
| `openai_search` | `gpt-5.6-luna` + `web_search` | $0.0140 | 16.0% | $1.75 | $1.05 | $0.70 | $0.35 |
| `gemini_grounded` | `gemini-3.6-flash` | $0.0104 | 11.9% | $1.30 | $0.78 | $0.52 | $0.26 |
| `perplexity` | `sonar` | $0.0054 | 6.2% | $0.68 | $0.41 | $0.27 | $0.14 |
| `google_ai_mode` | DataForSEO | $0.0040 | 4.6% | $0.50 | $0.30 | $0.20 | $0.10 |
| `google_ai_overviews` | DataForSEO | $0.0026 | 3.0% | $0.33 | $0.20 | $0.13 | $0.07 |
| Judge | prejudge | $0.0000 | — | $0.00 | $0.00 | $0.00 | $0.00 |
| **Total** | | **$0.0872** | | **$10.90** | **$6.54** | **$4.36** | **$2.18** |

With `anthropic_search` repinned to `claude-sonnet-5` — the other change with no downside (§5):

| Surface | Model / vendor | $/call | Share | K=5 | K=3 | K=2 | K=1 |
|---|---|---|---|---|---|---|---|
| `anthropic_search` | `claude-sonnet-5` | $0.0372 | 50.5% | $4.65 | $2.79 | $1.86 | $0.93 |
| `openai_search` | `gpt-5.6-luna` + `web_search` | $0.0140 | 19.0% | $1.75 | $1.05 | $0.70 | $0.35 |
| `gemini_grounded` | `gemini-3.6-flash` | $0.0104 | 14.1% | $1.30 | $0.78 | $0.52 | $0.26 |
| `perplexity` | `sonar` | $0.0054 | 7.4% | $0.68 | $0.41 | $0.27 | $0.14 |
| `google_ai_mode` | DataForSEO | $0.0040 | 5.4% | $0.50 | $0.30 | $0.20 | $0.10 |
| `google_ai_overviews` | DataForSEO | $0.0026 | 3.5% | $0.33 | $0.20 | $0.13 | $0.07 |
| **Total** | | **$0.0736** | | **$9.20** | **$5.52** | **$3.68** | **$1.84** |

Add **~$0.25** (K=5) / **~$0.15** (K=3) if you run the flag verifier over the API — see §6.

**Reference points:** the same six surfaces at 45 queries, K=5, on the original pins
(`gpt-5-search-api` + `gemini-2.5-flash` billed) = **$26.09**. Cells per engine: K=5 → 125,
K=3 → 75, K=2 → 50, K=1 → 25.

### Basis for each line

| Surface | Calculation |
|---|---|
| `anthropic_search` | 10,928 in + 534 out + $10/1k search fee. **Floor** — measured n=1, one search |
| `openai_search` | 16,700 in @ $0.20 + 530 out @ $1.20 + $10/1k tool fee |
| `gemini_grounded` | 20 in @ $1.50 + 1,385 out @ $7.50; grounding fee $0 inside quota |
| `perplexity` | 20 in + 415 out @ $1/$1 + $5/1k low-context request fee |
| `google_ai_mode` | DataForSEO live endpoint |
| `google_ai_overviews` | $0.002/SERP + $0.0006 async surcharge |

---

## 2. `openai_search` — Luna's price is settled

Two OpenAI pages disagreed. The **pricing page** ($0.20 / $0.02 cached / $1.20) is correct;
the **Luna model page** ($1.00 / $0.10 / $6.00) is stale. OpenAI's own July 30 announcement:

> *"Starting July 30, API pricing is $2 per million input tokens and $12 per million output
> tokens for Terra, and $0.20 per million input tokens and $1.20 per million output tokens
> for Luna."* … *"GPT-5.6 Luna … will cost 80% less."*

$1.00 → $0.20 and $6.00 → $1.20 are both exactly −80%. **Lesson worth keeping: model pages
can carry stale prices; the pricing page is the source of truth.**

Note the shape of the $0.0140 call — **$0.010 of it (72%) is the flat `web_search` tool
fee.** The model barely matters on this surface any more; Terra instead of Luna is +$0.036,
but nothing gets below $0.010.

## 3. Why `openai_search` runs at all now

`gpt-5-search-api` has no published model page and, on this account, a **6,000 TPM** ceiling
against a ~17,230-token call. Two live tests answered **0 of 10**
(`local_templates.py:117-121`).

The Responses API `web_search` tool uses *the calling model's* limits — verified: *"Responses
API web search uses the underlying model's tiered rate limits."* Luna at Tier 1 is **500,000
TPM / 500 RPM**.

| Path | Tier-1 TPM | 125 cells | 75 cells |
|---|---|---|---|
| `gpt-5-search-api` | 6,000 | **6.0 hours** (0/10 answered) | 3.6 hours |
| `gpt-5.6-luna` + `web_search` | 500,000 | **4.3 minutes** | 2.6 minutes |

No tier upgrade needed. It's a rewrite of `openai_search_engine.py` from
`chat.completions.create` to `responses.create` with `tools=[{"type":"web_search"}]`, plus a
different citation-extraction path. `MODEL_ID` becomes undated → needs an `UNDATED_PINS` entry.

## 4. `gemini_grounded` on 3.6-flash — a fidelity purchase, not a saving

Confirmed from the AI Studio spend page: **Tier 1**, total Gemini spend **$0.05 over 28 days**
(2026-07-05 → 08-01). At 2.5's $35/1,000 that's ~1.4 billed grounded prompts — i.e. grounding
has been costing you nothing. Both allowances are **paid-tier** allowances:

| Pin | Paid-tier free allowance | $/call inside it | Billing unit |
|---|---|---|---|
| `gemini-2.5-flash` | **1,500 per day** (~45,000/mo) | $0.0035 | per **prompt** |
| `gemini-3.6-flash` | 5,000 per **month** | $0.0104 | per **search executed** |

Every cost dimension favours 2.5: 3× cheaper per call, 9× bigger pool, and one call can never
cost more than one unit. **So 3.6 is bought purely for fidelity** — 2.5 is two generations
behind what a person gets in the Gemini app today, and the product's claim is "this is what
Gemini says about you." The price of that is **+$0.87/audit** at K=5 (from ~$0.43 to $1.30).

⚠️ **`gemini-3.6-flash` grounding is "Not available" on the free tier** — Tier 1 is required.
You have it.

⚠️ **Watch the monthly ceiling.** 5,000/month with per-*search* billing:

| searches/call | `gemini_grounded` line (K=5) | audits/month inside quota |
|---|---|---|
| inside quota | $1.30 | — |
| 1 | $3.05 | 40 |
| 2 | $4.80 | 20 |
| 3 | $6.55 | 13 |

Log `groundingMetadata` on one real call to learn which regime you're in.

## 5. `anthropic_search` → `claude-sonnet-5`

| | $/call | K=5 |
|---|---|---|
| `claude-sonnet-4-5` (current) | $0.0508 | $6.35 |
| `claude-sonnet-5`, through Aug 31 | $0.0372 | $4.65 |
| `claude-sonnet-5`, from Sep 1 | $0.0508 | $6.35 |

The $2/$10 is **introductory pricing** with a published end date, not a promo that gets
extended: *"Introductory pricing … is in effect through August 31, 2026, after which the
standard pricing of $3/$15 … will take effect."* Don't plan around an extension.

But you don't need it: from Sep 1, Sonnet 5 costs **exactly what Sonnet 4.5 costs today**,
and Sonnet 4.5 has a retirement floor of not sooner than 2026-09-29. **You have to move
anyway** — moving this month is just free money. No code change needed on this adapter (it
already sends no temperature and declares `SAMPLING = "default"`).

⏱ **Time it between client cycles.** Answers captured under different pins aren't comparable
cycle-over-cycle, so a mid-engagement repin makes the client's "movement" partly your churn.

## 6. "The judge is free" has a price, and it isn't dollars

`.claude/skills/prejudge/SKILL.md`: *"This replicates the single judge (`Judge()` with no
cascade/verify)… The `dump` step refuses to run if `JUDGE_CASCADE`/`JUDGE_VERIFY` are set."*

But `JUDGE_VERIFY` defaults to **1** (`settings.py:150-159`) because *"failing toward the
expensive-but-correct path is the right default for something whose output accuses a client
of an error."* So free judging = **unverified** judging.

The verifier over the API on this set is **~$0.25/audit** at K=5 (~$0.15 at K=3) — under 3%
of the bill. **Prejudge the structural pass free; run the verifier over the API for anything
a client reads.**

## 7. Two open items

**`anthropic_search` is 50–58% of the bill and its figure is a floor.** $0.0508 was measured
at n=1 on a query that triggered *one* web search; a question that searches three times costs
more. It's the only large line left that is both dominant and unmeasured. Measure it across
the real 25-query set before quoting a per-audit number to anyone.

**Check Rate Limit in AI Studio.** Google no longer publishes per-model RPM/TPM in the docs
and points at your account page instead. Your runner fans out at
`ENGINE_PROVIDER_CONCURRENCY=4` against 125 grounded calls per audit — worth knowing Tier 1's
ceiling before the first real run, given `openai_search` was lost to exactly this. Note you
won't graduate to Tier 2 by accident: it needs $100 paid + 3 days, ~77 audits away at $1.30
of Gemini spend each. If Tier 1 binds, the fix is the limit-increase form, not waiting.

## 8. Don't cut K on this set

`DEFAULT_RUNS_PER_QUERY = 5` is data-driven (`settings.py:92-105`) — worst-brand label
agreement measured ~60% on gemini and perplexity. Retrieval surfaces are the wobbliest,
because the retrieved document set varies run to run independently of the model, and this set
is **entirely** retrieval surfaces. K is what averages that out.

Also: **25 × K=3 and 15 × K=5 cost exactly the same** (75 cells/engine). The question isn't
how to save 40% — it's whether 75 cells is better spent as breadth or depth. Decide on purpose.

## 9. Sample composition — the reason to pick one Google SERP surface

Running `gemini_grounded` + `google_ai_mode` + `google_ai_overviews` makes **3 of 6 surfaces
Google-owned — 50% of the cells** — against OpenAI 17%, Anthropic 17%, Perplexity 17%. Since
`metrics.coverage()` pools all cells into the headline number, a client's "AI visibility
score" would be half a Google score across three overlapping views of one index.

Cost is not the argument: AI Mode as a sixth surface is **+$0.50/audit** at K=5. Validity is.
Your own code already picked one per ICP — `local_templates.py` uses `google_ai_mode` and
drops AI Overviews for local, because AIO returned **0 of 5** local-intent queries and
`engine_routing.py` now skips them. Consumer → AIO. Local → AI Mode.

If you want both anyway, report them separately (`coverage_by_engine()`) rather than letting
both feed the pooled number.

---

### Caveats

- **`anthropic_search` $0.0508 is a floor** (n=1, one search). Largest line in the table.
- **The 16,700-token input profile** was measured on `gpt-5-search-api`. The Responses
  `web_search` tool governs retrieved volume via `return_token_budget`, whose default OpenAI
  does not publish — so the Luna figure is modeled until one real call is logged.
- **Reasoning tokens** on Luna bill as output and aren't in the 530-token estimate.
- **`gemini-3.6-flash`'s verbosity** is assumed equal to 2.5-flash's (1,385 output tokens).
  Output dominates the token cost, and 3.6's output rate is 3× higher.
- Token counts are `chars/4` approximations. Fine for ranking configurations; not for
  quoting a bill.

### Sources

[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) ·
[Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) ·
[OpenAI pricing](https://developers.openai.com/api/docs/pricing) ·
[OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits) ·
[OpenAI web search tool](https://developers.openai.com/api/docs/guides/tools-web-search) ·
[GPT-5.6 announcement](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/) ·
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) ·
[Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) ·
[Perplexity pricing](https://docs.perplexity.ai/docs/getting-started/pricing.md)
