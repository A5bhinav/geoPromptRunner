# How to Build the Audit Repackaging — Implementation Guide

**Compiled:** 2026-08-01 · **Method:** 5 research agents (~250 sources) on implementation technique
**Scope:** the *how* for `docs/audit-packaging-spec.md`. The spec says what to build and in what order; this says how to build each piece and what will bite you.
**Companion docs:** `audit-packaging-research.md` (why) · `audit-packaging-spec.md` (what/order) · `.claude/skills/audit-packaging/SKILL.md` (standing rules) · `licensing-implementation.md` (accounts/tenancy).

---

## ⚠️ Correction to the existing spec — read first

**`docs/audit-packaging-spec.md` P1-T7 is wrong.** It tells an agent to implement running headers with `position: running()` + `@page` margin boxes. That does not work.

- Chrome **131 (Nov 2024)** shipped native `@page` margin boxes (`@top-center`, `@bottom-right`, …) with `counter(page)`/`counter(pages)`. ✅ static content and page numbers work.
- **`position: running()` and `string-set()` were explicitly out of scope and are NOT implemented in Chromium** — `string-set()` is tracked as an open, unresolved feature request ([issue 376420244](https://issues.chromium.org/issues/376420244)). Only Paged.js, Prince and WeasyPrint implement them.
- Therefore **dynamic, section-aware running headers are impossible in headless Chromium**, in any mode.

Use Playwright's `headerTemplate`/`footerTemplate` instead (§4.2). Two more traps found in the same area:

- Headless Chrome **silently refuses to fetch `url()` resources inside `@page` CSS** — a logo in a margin box will just not appear. Base64 data-URIs work.
- Mixing `@page { margin }` with Playwright's `margin` option gives unpredictable results ([open bug](https://github.com/microsoft/playwright/issues/34423) — a maintainer: *"for PDF, it is what it is, we just return what browser generates"*). **Pick exactly one margin source.**

Fix the spec before an agent starts P1-T7.

---

## 1. Finding identity — the keystone, done right

Spec P0-T1 says `finding_id = sha256(client + type + normalized_claim_stem)[:12]`. That is the right *starting* instinct and the wrong *final* design, for a reason worth understanding: **any hash is brittle by construction.** "Fort is a relatively new **player** in the fitness tracking market" and "…new **entrant** in the fitness tracking space" hash to unrelated values. Next week's report would show a fixed finding plus a new one, when nothing changed.

### Use a two-layer ID

| Layer | What | Purpose |
|---|---|---|
| `row_hash` | `sha256(normalize(claim))[:16]` — recomputed every run | Idempotency only. "Have I already ingested this exact row this run?" |
| `cluster_id` | UUID, **persisted**, assigned by matching against previously-seen findings | The stable, client-facing finding ID. This is what survives across weeks. |

This is how entity-resolution systems actually do it. **OpenSanctions** keeps a resolver graph where merged records leave a forwarding "referent" pointer with a 6-month grace period. **Zingg** assigns a new record the existing cluster's ID when it matches above threshold, else mints a new one, and never silently overrides a human-confirmed match. Google formalized the "does the same real-world thing keep the same ID across runs" property as a separately-measurable metric family, [ABCDE](https://arxiv.org/abs/2409.18254) — distinct from cluster quality.

### Similarity: don't use SimHash or MinHash here

Both are built for documents, not 10–40 word sentences.

- **SimHash** votes per bit across tokens; with ~20 tokens a handful dominate each bit, so small edits swing many bits and destroy the "small edit → small Hamming distance" property that makes it useful. Google's production thresholds (64-bit, k=3) assume web-page-length input. The existence of short-text-specific variants ([SimText](https://github.com/oudb/SimText), [RETSim](https://arxiv.org/html/2311.17264)) is the tell.
- **MinHash/LSH** estimates Jaccard over shingle *sets*; a short sentence yields 5–15 shingles, so the estimator variance is high and LSH's banding math (which assumes many independent shingles for a sharp threshold) doesn't hold.

**Use `rapidfuzz.fuzz.token_set_ratio`** — already a repo dependency, C++-backed, deterministic, robust to reordering and to one string being a subset of another (exactly the Fort paraphrase cases). At n≈235/run that's ~27.6k pairs, sub-second.

```python
DUP_THRESHOLD = 85.0   # STARTING POINT ONLY — tune by sweeping 70→95 on labeled pairs
```

> **Do not ship 85 as a constant without tuning it.** There is no universal correct value. Build `tests/fixtures/labeled_pairs.csv` (~150–300 hand-labeled `claim_a, claim_b, is_duplicate` rows), sweep the threshold, plot precision/recall, pick the knee.

**Short-circuit normalized exact match first** (dict lookup, O(1)) before running fuzzy comparison.

### Clustering: Union-Find, not HDBSCAN or agglomerative

HDBSCAN and `scipy.fcluster` both recompute the whole structure from the entire dataset and return arbitrary integer labels (1..k). Adding item #236 can reshuffle which integer means which real cluster — which is exactly the instability that would make the weekly diff lie.

The correct shape is a **persisted registry + incremental assignment**:

1. Postgres table of clusters, each with a stable UUID and a representative claim.
2. For a new claim, block via `pg_trgm` to get ~20 candidates, re-score those with rapidfuzz in Python.
3. Best match ≥ threshold → attach (UUID unchanged). Else → mint new UUID.
4. Within a single run's *new* items, Union-Find merges mutual near-duplicates into connected components before registry assignment.

Union-Find over a similarity graph *is* single-linkage clustering, but implemented incrementally, so it composes with the registry without relabeling anything already assigned.

```python
class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # deterministic tie-break: lower index always becomes root
            self.parent[max(ra, rb)] = min(ra, rb)
```

> **Determinism requires sorting the input** by a stable key (`row_hash`, then original index) before iterating. Union-Find on an unsorted list can produce different components near the threshold depending on comparison order.

### Postgres blocking

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE findings_registry (
    cluster_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    representative   text NOT NULL,
    normalized_text  text NOT NULL,
    theme            text NOT NULL,
    first_seen_run   uuid NOT NULL,
    occurrence_count int  NOT NULL DEFAULT 1
);
CREATE INDEX findings_registry_trgm_idx
    ON findings_registry USING GIN (normalized_text gin_trgm_ops);
```

```sql
-- blocking: cheap candidate fetch, then rapidfuzz re-scores in Python
SET pg_trgm.similarity_threshold = 0.25;   -- looser than default 0.3; recall over precision here
SELECT cluster_id, representative, similarity(normalized_text, $1) AS sim
FROM findings_registry
WHERE normalized_text % $1
ORDER BY sim DESC LIMIT 20;
```

**Skip pgvector/embeddings.** The determinism requirement rules them out — even a fixed local model has floating-point variance across BLAS versions and hardware. Accept that a semantic-only pair like *"There isn't a widely recognized brand called 'Fort'"* vs *"Fort (assuming you mean Fitbit?)"* will score low on lexical similarity. **That's fine** — the *theme classifier* (§2) catches them as the same root cause even when the sentences share no tokens. Don't make the similarity layer solve semantic equivalence.

### Representative and title

Pick the **medoid** (min total distance to other members), ties broken by shortest → lexicographically first. Generate the title from a **template keyed off the classifying rule**, not from the text. Reserve keyword extraction (YAKE) as a fallback only where no template exists.

### Evaluation harness

Three files, maintained opportunistically:
- `tests/fixtures/labeled_pairs.csv` — threshold tuning + precision/recall regression gate.
- `tests/fixtures/labeled_clusters.json` — one full run hand-labeled, for **B-cubed F-score** (better than pairwise at handling cluster-size imbalance).
- A stored baseline JSON; CI fails if F-score regresses.

Monthly: dump the 10 largest clusters and the whole UNCLASSIFIED bucket to CSV for a human skim. Automated metrics on a small labeled set miss systematic drift.

---

## 2. Theme classification

**Ordered decision list, first match wins.** Simpler to reason about and test than a multi-label rule set needing a conflict resolver. Put specific rules before catch-alls.

```python
@dataclass(frozen=True)
class Rule:
    theme: str
    patterns: tuple[re.Pattern[str], ...]

    def matches(self, normalized: str) -> bool:
        return any(p.search(normalized) for p in self.patterns)

RULES: list[Rule] = [
    Rule("identity_disambiguation", (
        re.compile(r"\bnot?\s+(a\s+)?(widely\s+)?recogni[sz]ed\b"),
        re.compile(r"\bassuming you mean\b"),
        re.compile(r"\bif by .{1,20} you mean(t)?\b"),
    )),
    Rule("pricing_offer", (re.compile(r"\$\d"), re.compile(r"\bprice point\b"))),
    # … ~9 more, specific → general
]

def classify(claim: str) -> str:
    n = normalize(claim)
    for rule in RULES:
        if rule.matches(n):
            return rule.theme
    return "UNCLASSIFIED"   # tracked as a coverage metric, never silently dropped
```

**Track `unclassified_count / total` as a first-class metric.** It's the leading indicator that the rule set needs a new rule. Test with a golden `(claim_text, expected_theme)` CSV run through `@pytest.mark.parametrize` on every rule change.

**Optional fallback:** for claims matching no rule, nearest-exemplar by TF-IDF cosine against a *frozen, versioned* set of hand-picked exemplars per theme. Deterministic, no network. Tag these `classified_by: "fallback"` so you can audit and promote good ones into real rules.

> ⚠️ If you use TF-IDF anywhere, **freeze the vocabulary/idf weights**. Recomputing idf per run makes classification non-deterministic across runs — a silent violation of the reproducibility requirement.

**Weak supervision (Snorkel-style labeling functions)** is the right escalation if the rule set outgrows what one person can order manually — note it for later, don't build it for 10 themes.

---

## 3. Statistics — hand-roll it, and here's why

### 3.0 The measured cost model — and why it changes K

Measured 2026-08-01. Supersedes every estimated cost figure in the research docs.

| Surface | Model | $/call | Share of spend |
|---|---|---|---|
| Claude (`anthropic_search`) | `claude-sonnet-5` | $0.0372 | **50.5%** |
| ChatGPT | `gpt-5.6-luna` + `web_search` | $0.0140 | 19.0% |
| Gemini | `gemini-3.6-flash` | $0.0104 | 14.1% |
| Perplexity | `sonar` | $0.0054 | 7.4% |
| Google AI Overviews | DataForSEO | $0.0040 | 5.4% |
| Google AI Mode | DataForSEO | $0.0026 | 3.5% |
| **Total** | | **$0.0736** | |

Per run, 25 queries: **K=5 → $9.20 · K=3 → $5.52 · K=2 → $3.68 · K=1 → $1.84** (engine calls only; judge pass is separate).

**The K trade — act on this before tuning anything else.** Repeated runs of the same
prompt are heavily correlated (ICC ~0.48–0.86, mean 0.68 in published LLM-eval work), so
marginal runs cost full price and add almost no independent information. Query breadth
does. Holding spend at $9.20/run:

| | queries | K | raw cells | DEFF @ρ=0.68 | **effective n** |
|---|---|---|---|---|---|
| today | 25 | 5 | 125 | 3.72 | **34** |
| same cost | ~42 | 3 | 126 | 2.36 | **53** |

**Same dollar, ~60% more effective sample** — +51% at ρ=0.5, +59% at ρ=0.68. And 42
queries moves the set toward the 50–200 "serious tracking" band it currently sits below.

**K=3 is the floor for the product, not just the statistics.** At K=2 you can observe
disagreement but not quantify it; at K=1 the entire "N of M runs" honesty framing
collapses into single observations, which is the one thing the packaging cannot give up.

**Cost concentration.** `claude-sonnet-5` is 50.5% of spend at 3.6× gemini-flash's
per-call cost. If cost ever binds, that is the only lever that matters — and the first
move is token efficiency on that surface (shorter cached system block, capped
`max_tokens`), not dropping it. Engine coverage is a product feature and Claude is a real
consumer surface.

**Implications for the report layer:**
- The engine strip is **6 surfaces, not 4**. Two are Google (AI Overviews and AI Mode via
  DataForSEO) and must be labeled distinctly — they are different surfaces with different
  behavior, not one "Google."
- Six rows don't fit as cards. Use an aligned table so a reader can scan one column.
- Client-facing labels are the product name plus the pinned model in muted type
  ("ChatGPT · GPT-5.6 Luna, web search"). Never `sonar` or `gpt-5.6-luna` alone.
- P2-T7's evidence bundle requires the pinned model id per finding —
  `src/engines/model_pins.py` already holds these; wire it through rather than
  re-deriving.


### Library decision: zero new dependencies

`statistics.NormalDist().inv_cdf()` has been in the **stdlib since Python 3.8**. Every formula you need is a dozen lines of closed-form arithmetic. That means the whole statistics module can be dependency-free, fully typed, and *exhaustively* property-tested — which buys more confidence than importing statsmodels for two functions.

- **Do not add statsmodels.** Heavyweight, pulls pandas+scipy+patsy, no official type stubs found. Fails both the small-dependency and strict-typing constraints.
- **If scipy is already a hard dependency**, `scipy.stats.binomtest(...).proportion_ci(method="wilson")` is fine for the base CI — scipy ships an official, actively-maintained [`scipy-stubs`](https://github.com/scipy/scipy-stubs) package. You still hand-write Newcombe, ICC/DEFF, MDE and BH regardless; none exist in scipy.
- Skip Barnard's exact test. More powerful in principle, needs nuisance-parameter optimization, and GraphPad quotes Feinstein on the controversy: *"can otherwise be generally ignored."*

### Wilson interval (with continuity correction)

```python
def wilson_interval(
    successes: int, n: int, confidence: float = 0.95, continuity: bool = True
) -> tuple[float, float]:
    """Wilson score CI. Never degenerate at p=0 or p=1, never leaves [0,1]."""
    if n == 0:
        return (0.0, 1.0)                       # full uncertainty, NOT "0%"
    if not 0 <= successes <= n:
        raise ValueError(f"successes={successes} not in [0,{n}]")

    p_hat = successes / n
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    z2 = z * z

    def bound(p: float) -> tuple[float, float]:
        denom = 1 + z2 / n
        center = (p + z2 / (2 * n)) / denom
        margin = (z / denom) * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
        return center - margin, center + margin

    if continuity:
        lo, _ = bound(max(p_hat - 1 / (2 * n), 0.0))
        _, hi = bound(min(p_hat + 1 / (2 * n), 1.0))
    else:
        lo, hi = bound(p_hat)
    return max(0.0, lo), min(1.0, hi)
```

`n == 0 → (0.0, 1.0)` is deliberate: it signals the report layer to say *"insufficient data"* rather than *"0%"*.

### Comparing weeks: CI of the difference, not CI overlap

**Non-overlapping CIs is not a valid test.** Two 95% CIs can overlap while the difference is significant — the overlap heuristic effectively tests against an interval ~√2 too wide, making it conservative and underpowered. Compute the CI of the *difference* and check whether it excludes zero. Use **Newcombe's hybrid score method**:

```python
def newcombe_diff_interval(x1: int, n1: int, x2: int, n2: int, conf: float = 0.95):
    l1, u1 = wilson_interval(x1, n1, conf, continuity=False)
    l2, u2 = wilson_interval(x2, n2, conf, continuity=False)
    p1 = x1 / n1 if n1 else 0.0
    p2 = x2 / n2 if n2 else 0.0
    d = p1 - p2
    lower = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return max(-1.0, lower), min(1.0, upper)
```

Fagerland/Lydersen/Laake rank Agresti–Min exact-unconditional highest for n<30, with Newcombe an acceptable alternative that's *"relatively straightforward to calculate."* Agresti–Min needs numerical optimization — not worth it.

**This replaces the existing single-threshold `is_real_move()`** in `src/pipeline/trend.py`. The improvement: the CI self-adjusts to each cell's actual n, so a cell with n=20 gets a more sensitive test than one with n=3, rather than one global noise floor for everything.

### The design-effect correction — the most important stats fix

Repeated runs of the same prompt are correlated. Pooling them as independent badly understates uncertainty.

```
DEFF   = 1 + (m − 1) · ICC        # Kish
n_eff  = n / DEFF
```

**Plug `n_eff`, not raw n, into every interval.** This is a strict widening — it can never make an interval falsely narrow.

On the ICC figure: the earlier research file cites ICC ≈ 0.57 giving effective n ≈ 34 from 20 prompts × 30 runs. The agent **could not trace that specific number to a primary source** — treat it as illustrative. But a directly relevant paper, [*Do Repetitions Matter? Strengthening Reliability in LLM Evaluations*](https://arxiv.org/html/2509.24086v1), reports **ICC 0.48–0.86, mean 0.68** across repeated-run LLM eval slices. The order of magnitude is real; compute your own from your own data:

```python
def icc_one_way(groups: dict[str, list[float]]) -> float:
    """ICC(1) via one-way random-effects ANOVA. groups: {prompt_id: [0/1 outcomes]}"""
    k = len(groups)
    if k < 2:
        raise ValueError("need ≥2 prompts")
    all_vals = [v for vals in groups.values() for v in vals]
    grand = sum(all_vals) / len(all_vals)

    ms_b_num = ms_w_num = 0.0
    n_total, m_vals = 0, []
    for vals in groups.values():
        m = len(vals); m_vals.append(m); n_total += m
        gm = sum(vals) / m
        ms_b_num += m * (gm - grand) ** 2
        ms_w_num += sum((v - gm) ** 2 for v in vals)

    df_b, df_w = k - 1, n_total - k
    ms_b = ms_b_num / df_b
    ms_w = ms_w_num / df_w if df_w > 0 else 0.0
    m0 = (sum(m_vals) - sum(m * m for m in m_vals) / sum(m_vals)) / df_b  # unbalanced correction
    denom = ms_b + (m0 - 1) * ms_w
    return max(0.0, (ms_b - ms_w) / denom) if denom else 0.0
```

Hand-rolled deliberately — `pingouin.intraclass_corr` pulls pandas+scipy+tabulate for one formula.

### Thresholds: derive, don't guess

Replace the arbitrary 15pp with a computed minimum detectable effect:

```python
def minimum_detectable_effect(n: float, baseline_p: float = 0.5,
                              alpha: float = 0.05, power: float = 0.80) -> float:
    nd = NormalDist()
    return (nd.inv_cdf(1 - alpha / 2) + nd.inv_cdf(power)) * math.sqrt(
        2 * baseline_p * (1 - baseline_p) / n)
```

Then two gates: statistical (Newcombe CI excludes 0) **and** practical (magnitude ≥ a business floor). Both must pass.

**Multiple comparisons:** ~20 simultaneous tests per report (4 engines × 5 buckets). Use **Benjamini–Hochberg FDR, not Bonferroni** — for an exploratory weekly scan where under-flagging real movement is worse than an occasional false positive that self-corrects next week, controlling false *discovery* rate is the right frame.

### On McNemar's test

Formally the same query set each week makes observations paired. **Don't do it.** Three reasons: per-prompt verdicts are themselves noisy aggregates over stochastic repeat runs (compounding, not reducing, complexity); prompt sets and engine versions drift week to week, breaking the same-units assumption; and the ICC correction above already captures the correlation the pairing would exploit, more simply.

### Control charts

A **p-chart** fits well. With varying subgroup size, recompute limits per period or standardize to Z-scores. **Reuse your DEFF** to inflate the limits rather than reimplementing Laney's p′-chart:

```
UCL_i = p̄ + 3·√(DEFF · p̄(1−p̄)/n_i)
```

The agent could not verify Laney's exact moving-range formula from a primary source and explicitly recommended against shipping a reconstruction from memory. DEFF-inflation achieves the same goal with a factor you already compute and can unit-test.

### Testing numerical code

Four layers:
1. **Golden values** hardcoded from statsmodels/R output — so tests have no runtime dependency on them.
2. **Hypothesis property tests**: bounds in [0,1] and ordered; symmetry (`wilson(n−x,n)` mirrors `wilson(x,n)`); width shrinks as n grows at fixed rate.
3. **Monte Carlo coverage simulation** — the strongest test that the interval means what it claims. Mark `@pytest.mark.slow`, run on a grid, assert empirical coverage lands in 0.93–0.98 for nominal 95%.
4. **Dev-only cross-check** against `scipy.stats.binomtest(...).proportion_ci` over a random grid, so future refactors are caught without scipy being a runtime dep.

---

## 4. Rendering and PDF

### 4.1 Architecture

**A standalone always-on Docker worker**, not in the Next.js process, not serverless.

- Base image: `mcr.microsoft.com/playwright:v<version>-jammy`, tag matching your installed Playwright exactly. Version skew is the #1 "works locally, breaks in prod" cause.
- Memory: idle Chromium ~400MB–1GB; under load 1.5–4GB for a chart-heavy 15-page report. Budget 2GB minimum, 4GB comfortable.
- **One long-lived `Browser` per worker, a fresh `BrowserContext` per render.** Contexts are cheap and isolated (no cookie/cache bleed between tenants); a new Browser costs 1–2s cold launch. Always `context.close()` in `finally` — a leaked context accumulates until OOM.
- Concurrency: `p-limit(3)` in-process. Don't reach for BullMQ/Redis until render volume actually needs backpressure across instances.

**Serverless is a non-starter for the primary path:** Vercel's [250MB unzipped function limit](https://vercel.com/kb/guide/troubleshooting-function-250mb-limit) versus Chromium's ~300MB binary. If you ever must (`@sparticuz/chromium`): ≥1600MB RAM, and note the easy-to-miss bug that Playwright doesn't clean its user-data-dir between warm starts, so `/tmp` fills and you get `ERR_INSUFFICIENT_RESOURCES` — `rm -rf` a per-invocation dir.

### 4.2 Headers, footers, page numbers

```ts
const headerTemplate = `
  <style>* { margin:0; font-family: Inter, sans-serif; }</style>
  <div style="width:100%; font-size:8px; padding:6px 24px 0; display:flex;
              justify-content:space-between; color:#666;">
    <span>${tenantName} — AI Visibility Report</span><span>Confidential</span>
  </div>`;

await page.pdf({
  format: 'Letter',
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate,
  footerTemplate,   // use <span class="pageNumber"></span> / <span class="totalPages"></span>
  margin: { top: '0.9in', bottom: '0.9in', left: '0.6in', right: '0.6in' },
  preferCSSPageSize: false,   // don't ALSO declare @page margins
});
```

Gotchas, all verified: `displayHeaderFooter: true` is required or templates are ignored entirely · **default font-size is effectively 0**, set it explicitly inline · templates render in an **isolated iframe** so no external stylesheet, no webfonts by relative path, images must be base64 · `margin.top`/`bottom` must reserve space or the header is clipped · recognized classes are `date`, `title`, `url`, `pageNumber`, `totalPages`.

For a section-aware running header, compute the section→page map in the two-pass render (§4.3) and overlay per-page text with `pdf-lib`. There is no live mechanism.

### 4.3 TOC page numbers and bookmarks

**Two-pass render** is the only way — same trick LaTeX uses with its `.aux` file:
1. Render once with a placeholder TOC. Open the PDF with `pdfjs-dist`, search each page's text content for known heading strings, record `{heading, pageIndex}`.
2. Re-render the same HTML with the TOC populated from that map.

**`page.pdf()` does not generate a PDF outline from headings.** Confirmed open feature request ([playwright#29417](https://github.com/microsoft/playwright/issues/29417)); a maintainer states PDF support "is definitely not the priority for the project."

**`pdf-lib` has no high-level outline API** either — three separate open issues ([#567](https://github.com/Hopding/pdf-lib/issues/567), [#786](https://github.com/Hopding/pdf-lib/issues/786), [#1151](https://github.com/Hopding/pdf-lib/issues/1151)). You build the raw outline dictionary tree via the low-level `context` API, or shell out to `qpdf`/`mutool` — often simpler if you already spawn CLI tools.

### 4.4 The readiness signal — `networkidle` is not enough

`networkidle` only means HTTP quiesced. Client-rendered SVG finishes *after* that, on subsequent animation frames. Gate the capture on three things:

1. `isAnimationActive={false}` on every chart so there's no multi-frame transition to wait out.
2. `await page.waitForFunction(() => document.fonts.ready)` — font metrics affect axis-label layout, so fonts must settle before charts finalize measurements.
3. An **app-emitted readiness flag**: a React context counter incremented per chart in `useLayoutEffect`, setting `document.body.dataset.reportReady = 'true'` at zero. Then `await page.waitForFunction(() => document.body.dataset.reportReady === 'true')`.

### 4.5 Charts

**Recharts is client-only, permanently.** Rendering it in a Server Component throws `TypeError: Super expression must either be null or a function` — it still ships legacy class components ([recharts#4336](https://github.com/recharts/recharts/issues/4336)). Maintainers confirm this needs an incomplete internal refactor. Plan `'use client'` boundaries as permanent, not a workaround.

**`ResponsiveContainer` does not resize for print** ([recharts#1114](https://github.com/recharts/recharts/issues/1114)) — it sizes via `ResizeObserver` and print layout doesn't fire the events. Charts render at whatever the last on-screen size was.

**Consolidate every print fork into one `RenderModeContext` (`'screen' | 'print'`)** set from a `?mode=print` query param the Playwright URL passes. One flag drives: `ResponsiveContainer` → fixed pixel dimensions matching the `@page` content box; animation off; lazy sections eager; virtualized tables fully rendered.

Per chart type:

| Chart | Use | Why |
|---|---|---|
| Brand × engine heatmap w/ numbers | **Hand-rolled SVG / CSS grid** + `d3-scale` for the ramp | No library ships a first-class labeled heatmap; hand-rolled is smaller, deterministic, fixed-size, and SSR-safe |
| Bump chart | `@nivo/bump`, or hand-rolled with `d3-shape` | Only Nivo has a native bump primitive; otherwise you're writing line interpolation anyway |
| Pareto combo (bars + cumulative line, dual axis) | **Recharts `ComposedChart`** | Squarely Recharts' strength, and you already have the dependency |
| Sparklines in table cells | **Hand-rolled inline SVG** | Per-instance library overhead is wasted on a 40×16px mark repeated dozens of times; a path string is SSR-safe by construction |

Hand-rolled SVG has a second benefit: being a pure function of data, it **can render in a Server Component** — so the PDF path can serialize those charts entirely server-side without waiting on hydration.

### 4.6 The bug that silently eats PDF content

This is the highest-impact gotcha in the whole rendering section, and it's easy to miss because the live page looks perfect.

**Print never scrolls the viewport, so `IntersectionObserver` never fires for below-the-fold content.** Tracked as a spec-level issue ([whatwg/html#6581](https://github.com/whatwg/html/issues/6581)). Consequences:

- `loading="lazy"` images below the fold → blank in the PDF.
- `next/dynamic(..., { ssr: false })` sections → missing.
- **A virtualized/windowed long table renders only its visible slice into the DOM** → your 200-row appendix becomes 20 rows in the PDF.

All three are fixed by the same `RenderModeContext` flag from §4.5.

### 4.7 Print CSS

```css
@media print {
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  @page { size: letter; margin: 0; }   /* margins via page.pdf() — pick ONE source */

  .no-print { display: none !important; }
  [class*="overflow-"] { overflow: visible !important; }  /* shadcn Card clips otherwise */

  .report-card    { break-inside: avoid; }
  .report-section { break-before: page; }

  thead { display: table-header-group; }
  tfoot { display: table-footer-group; }
  tr    { break-inside: avoid; }

  p, li { orphans: 3; widows: 3; }
  table { width: 100%; border-collapse: collapse; }
}
```

`break-inside: avoid` failure cases, all real: **flex/grid containers block it** — put it on a plain `display: block` wrapper *around* the flex content, not on the flex element · an element taller than a page can't honor it · nested `overflow: hidden/auto` clips instead of paginating · `orphans`/`widows` don't apply inside flex/grid or to table rows.

**Tabular numerals:** `font-variant-numeric: tabular-nums`. Caveat — **not every font ships a `tnum` table**, and when it's missing the property silently no-ops. Verify by eyeballing `1111` vs `8888` width before relying on it for numeric columns.

### 4.8 Visual regression

- `expect(page).toHaveScreenshot()` with `mask:` for timestamps/IDs. Don't freeze the clock — masking is the documented approach.
- **Generate and update baselines inside the same Docker image CI uses.** macOS CoreText and Linux FreeType antialias differently enough that Mac-generated baselines will never match Linux CI, with zero UI changes. This sidesteps the problem instead of fighting it:
  ```bash
  docker run --rm -v $(pwd):/work -w /work \
    mcr.microsoft.com/playwright:v1.XX.0-jammy npx playwright test --update-snapshots
  ```
- Add [`diff-pdf`](https://vslavik.github.io/diff-pdf/) as a cheap PR gate — exit code 0/1, plus `--output-diff` for a visual annotated diff.
- **Test pagination in the DOM, not the PDF.** Under `emulateMedia({media:'print'})`, assert a card's start and end markers fall in the same page-height multiple:
  ```ts
  Math.floor(top / pageHeightPx) === Math.floor(bottom / pageHeightPx)
  ```
  Catches the failure earlier and needs no PDF parser.

---

## 4.9 Brand — the report wears **Sable**

Source of truth: the **Sable Identity Guide, Berkeley v1.0** ("Direction 7d Plume ·
Berkeley 8a"). Brand name **Sable**, descriptor **AI SEO**, domain sable.ai.

> ⚠️ **This supersedes the "weir" system** (`geoWebsite/app/globals.css`, Poppins +
> `#003262` + California gold `#fdb515`) for the report. The two are unrelated systems —
> different typefaces, a different navy (`#0E2340` vs `#003262`), and **Sable has no gold at
> all**. `geoWebsite` is still built on weir; someone has to decide whether the site
> migrates. Until then, do not mix tokens between them — pick Sable for the report and keep
> it internally consistent.

### The mark

Three rising plumes. Each plume is a teardrop with **three rounded corners and one square
heel** (`border-radius: 60% 60% 60% 0`), all seated on a shared baseline. Heights step
evenly (1.7u · 2.3u · 3u at width 1u each, gap ≈0.35u); **tone steps with them, so the eye
lands on the tallest, darkest form.**

- On paper: Mist → Harbour → Berkeley Navy (short→tall).
- On navy: Harbour → Mist → **Sky** (Sky is the accent, and navy is the only ground it is
  allowed on).

**Clearspace:** one plume-width (1u) on all sides. Nothing — rules, photography, other
logos — enters that field.
**Scale:** 34px standard · 20px minimum · below 20px drop the faintest plume and run
two-up · below 16px use the tallest plume alone · **the wordmark never sets below 14px.**
**Four approved lockups:** primary horizontal · stacked centred · reversed on navy ·
mono (one colour, or wordmark alone).

### Colour

| Name | Hex | Role |
|---|---|---|
| Berkeley Navy | `#0E2340` | ink, tallest plume |
| Sable Blue | `#12325C` | links, active states |
| **Sky** | `#7FA6D9` | accent — **on navy only, never on paper** |
| Harbour | `#697585` | middle plume, body text |
| Mist | `#B2B7BC` | first plume, rules |
| Paper | `#F2F1EC` | ground |

The guide's own rule: *"Navy and paper carry almost everything. Sky appears only against
navy, never on paper — it is the one bright note in the system and loses its job if it is
used twice on a page."*

**Consequence for data viz, and it is a real constraint:** the palette is entirely cool and
has no alert hue, and its single accent is forbidden on the report's ground. There is no
"warning colour" available and `Don't → no colours outside the palette` forbids inventing
one. Plan encodings around this rather than discovering it mid-build.

### ✅ The severity ramp — resolved, and it fits the brand exactly

This is the third answer to the same question, and it's the right one. Earlier drafts had
Critical in red (wrong for weir) then in gold (wrong for Sable). **Severity is a monochrome
navy ramp, darkest = most severe:**

| Tier | Fill | Icon |
|---|---|---|
| Critical | Berkeley Navy `#0E2340` | triangle |
| High | Sable Blue `#12325C` | circle |
| Medium | Harbour `#697585` | square |
| Low | Mist `#B2B7BC` | dot |

This isn't a compromise — it *is* the mark's own logic. The plumes step tone with height
"so the eye lands on the tallest, darkest form." A severity ramp does exactly that: darkest
draws the eye to what matters most. The report's most important chart and the logo now
encode the same idea.

Icon **and** label on every tier remain mandatory (a single-hue ramp cannot carry the
distinction alone), plus a 2px surface gap between bar segments.

### Typography

- **Cormorant Garamond** — *display only*. Light 300 & Regular 400. Headlines from 32px up,
  tracked +0.01 to +0.04em. **Italic for emphasis only.** Use it for the BLUF sentence, big
  numbers, tile values, section titles, action titles.
- **Libre Franklin** — text & UI. Body 15/1.7 in Harbour or navy at 80%. Label 10px /
  0.36em.
- **Sentence case everywhere. The only uppercase in the system is the tracked label.** All
  the ALL-CAPS chips from earlier drafts are wrong — chips read "Up from 1 of 6", not
  "UP FROM 1 OF 6". Section eyebrows and column heads are the legitimate tracked labels.
- **The wordmark always stays Garamond**, even where the UI is Libre Franklin.

> Both faces are metrically unlike `system-ui`. **Re-measure every print layout after fonts
> land** — the page-1 mockup needed three tightening passes across two font swaps.

### Don'ts (from the guide, verbatim in spirit)

Never rotate the mark · no colours outside the palette · never stretch or squash · the
wordmark stays Garamond.

### Print adaptation

Ground is **Paper `#F2F1EC`**, cards are white — matching the business-card treatment in the
guide rather than inventing a report-only ground. The masthead is a full-bleed **navy band**
carrying the reversed lockup, which is also the only place Sky is legal.

### The white-label collision — unchanged, and now sharper

Sable's identity is distinctive enough that a white-labelled report cannot simply swap a
colour: the plumes, the Garamond wordmark and the navy band are all Sable's. When an agency
resells, **the Sable brand comes off the end-client artifact and lives on the methodology
page** (Pierview's line: *"The client experience is yours. The data infrastructure is
Pierview's"*). That means the report template needs two skins from the start —
Sable-branded and neutral-tenant — driven by **one config object**
(`licensing-implementation.md` §4.1). Build the abstraction before the second skin exists,
not after.

## 5. The lifecycle engine

### 5.1 Data model that fits create-only storage

You need SCD Type 2's query ergonomics without its `UPDATE valid_to` step. The answer is a **revisioned append-only derived table**:

- `runs`, `finding_observations` — immutable snapshots, one insert per run/finding. Source of truth.
- `lifecycle_facts` — one row per `(finding_id, run_id, revision)`. "Current" is always `MAX(revision)`. Never update, just insert a new revision.

Skip true bitemporal modeling (you only measure at discrete weekly boundaries, not continuous time) and skip event sourcing (a single weekly batch job, no concurrent commands, no rich per-command business rules). A `computed_at` + `revision` gives ~95% of bitemporal's audit value at a fraction of the cost.

### 5.2 The absence-vs-not-measured problem — the highest-risk bug

Telling a client something is fixed when the engine actually timed out is the worst correctness failure available here.

**Vendors don't solve this well.** Tenable and Qualys both mark a finding "Fixed" after **one** absent scan. That works for them because their scanners have near-100% deterministic coverage per asset. It does **not** transfer to an LLM-judged pipeline where a missed finding might just mean the model didn't reproduce the error this run. The closest useful analog is Nagios **flapping detection** — evaluating the last 21 checks with a weighted state-change percentage before declaring a stable transition. The transferable principle: **require sustained evidence, not a single sample.**

**Two independent guardrails:**

**A — run coverage gate.** A run counts as evidence only if:
```
status == 'COMPLETE' AND coverage_ratio >= 0.95 AND query_set_version_id == current
```
Failing runs are stored immutably but **skipped entirely** by the state machine — as if they don't exist in the sequence. They never trigger RESOLVED and never break an absence streak. This is the actual answer to "not found vs not measured."

**B — confirmation count.** RESOLVED only after **N=2 consecutive comparable-run absences**. A single missed week keeps the finding PERSISTING with an internal `consecutive_absences` counter.

This also resolves the "absent 3 weeks then returns" ambiguity cleanly — **the cutoff is state-based, not time-based**. If the finding never reached confirmed RESOLVED, a return is just continuation (PERSISTING, no drama). If it did, a return is REGRESSED. And NEW is permanent: assigned once, on the run where the `finding_id` was first minted, never reassigned.

### 5.3 The algorithm

```python
RESOLUTION_CONFIRMATION_RUNS = 2   # per-org configurable

def compute_finding_lifecycle(
    finding_id: str,
    comparable_runs: Sequence[RunMeta],   # pre-filtered: COMPLETE, coverage OK, same qsv, sorted
    presence: Mapping[str, bool],
) -> list[LifecycleFact]:
    """Pure function of stored data. Same inputs → same outputs, always."""
    facts, first_seen, episode_start = [], None, None
    absences = age = 0
    was_open = was_resolved = False

    for run in comparable_runs:
        seen = presence.get(run.run_id, False)

        if first_seen is None:
            if not seen:
                continue                       # finding doesn't exist yet
            first_seen = episode_start = run.run_id
            age, was_open, absences = 1, True, 0
            facts.append(fact(run, NEW)); continue

        if seen and was_open:
            age += 1; absences = 0; status = PERSISTING
        elif seen and was_resolved:
            episode_start, age = run.run_id, 1  # new episode
            was_open, was_resolved, absences = True, False, 0
            status = REGRESSED
        elif seen:                              # reappeared during UNCONFIRMED absence
            age += 1; absences = 0; was_open = True
            status = PERSISTING                 # was never actually resolved
        elif was_open:
            absences += 1
            if absences >= RESOLUTION_CONFIRMATION_RUNS:
                was_open, was_resolved = False, True
                status = RESOLVED
            else:
                status = PERSISTING             # ← the guardrail
        else:
            absences += 1; status = RESOLVED

        facts.append(fact(run, status))
    return facts
```

**Query-set version change:** filter `comparable_runs` to one version before calling. `first_seen_at` for the *finding* still looks up the earliest observation across all versions (the brand error predates whichever query set surfaced it), but `age_in_cycles` restarts at the boundary with a UI footnote. You cannot honestly assert continuous presence across a change in the instrument.

**Merges/splits when clustering changes:** never rewrite a `finding_id`. Append to a `finding_identities` ledger — `MERGED_INTO` (canonicalize B→A via recursive CTE for all historical queries) or `SPLIT_FROM` (pre-split history stays attributed to the old id, new ids start fresh, UI annotates that history was tracked jointly). Honest compromise over fabricating which sub-claim was present when.

### 5.4 The regression SQL

This is genuinely tricky — it's a **gaps-and-islands** problem. Group consecutive same-state runs into islands via the `row_number() - row_number()` trick, then find a present-island immediately preceded by an absent-island of length ≥ N.

```sql
WITH comparable_runs AS (
  SELECT id AS run_id, org_id, sequence_no FROM runs
  WHERE status = 'COMPLETE' AND coverage_ratio >= 0.95
),
presence AS (
  SELECT ffs.finding_id, cr.run_id, cr.sequence_no,
         (fo.finding_id IS NOT NULL) AS present
  FROM finding_first_seen ffs
  JOIN comparable_runs cr ON cr.org_id = ffs.org_id AND cr.sequence_no >= ffs.first_seq
  LEFT JOIN finding_observations fo
    ON fo.run_id = cr.run_id AND fo.finding_id = ffs.finding_id
),
islands AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY finding_id ORDER BY sequence_no)
      - ROW_NUMBER() OVER (PARTITION BY finding_id, present ORDER BY sequence_no) AS island_id
  FROM presence
),
absence_islands AS (
  SELECT finding_id, MAX(sequence_no) AS absence_end_seq, COUNT(*) AS absence_len
  FROM islands WHERE present = false GROUP BY finding_id, island_id
)
SELECT p.finding_id, p.run_id AS reappearance_run_id, ai.absence_len
FROM islands p
JOIN absence_islands ai
  ON ai.finding_id = p.finding_id AND ai.absence_end_seq = p.sequence_no - 1
WHERE p.present = true AND ai.absence_len >= 2;   -- N, not hardcoded LAG chains
```

**Cumulative "resolved since we started"** must count *transitions into* RESOLVED, not rows — otherwise a finding that stays resolved for 20 weeks counts 20 times. Use `LAG(status) ... IS DISTINCT FROM 'RESOLVED'`.

**Indexes:** `runs(org_id, query_set_version_id, sequence_no)` unique · `finding_observations(run_id, finding_id)` unique + `(org_id, finding_id, run_id)` · `lifecycle_facts(finding_id, run_id, revision DESC)`.

### 5.5 Idempotency, re-judging, backfill

- `runs.idempotency_key = hash(org_id, qsv_id, period_start, pipeline_input_hash)`, unique. Re-submission returns the existing run.
- A genuine reprocessing is **not** the same key — new immutable row, `run_kind='CORRECTION'`, `supersedes_run_id`. Nothing about the original is touched, so you can always see exactly what the client was shown.
- **Re-judging after a diff was already shown:** re-run the pure function, insert a new `revision`. To reconstruct "what we told them on date D," filter `computed_at <= D` and take the max revision as of then.
- **Backfill = replay, not reconstruct.** Run the *current* fingerprinting+matching over historical raw runs in chronological order, exactly as if each were arriving live — matching is inherently order-dependent. Then run the same lifecycle function over the full history. Materialize once; don't recompute on read.
- **Findings predating fingerprinting:** don't fabricate a `first_seen_at`. Set `first_seen_is_estimated = true` and surface it as a lower bound ("open for at least N cycles") — standard left-censoring convention, applied honestly.

### 5.6 Testing

- **Fixture builder DSL** for readable histories: `RunSeriesBuilder().run({"f1","f2"}).run({"f2"}).run({"f1","f2"}).build()`
- **Table-driven** over `(presence_sequence, expected_statuses)`: `[T]`→NEW · `[T,F,T]`→NEW,PERSISTING,PERSISTING (guardrail) · `[T,F,F,T]`→NEW,PERSISTING,RESOLVED,REGRESSED
- **Hypothesis** over random boolean sequences asserting invariants: exactly one status per (finding, run) · first fact is always NEW · RESOLVED only after ≥N falses · REGRESSED only immediately after RESOLVED · age resets to 1 exactly on REGRESSED.
- **Metamorphic check**: a `RuleBasedStateMachine` that drives the real DB pipeline and asserts the SQL cumulative-resolved query agrees with the Python reference. Two independent implementations that must converge.
- **Golden file**: one 8-week multi-finding scenario, regenerated deliberately via `--update-golden`, never silently.
- **Age in cycles, not days.** Runs are irregular; calendar math implies false precision when a run didn't happen on schedule.

---

## 6. Narrative generation without hallucinating

### 6.1 Shape guarantees ≠ value guarantees

Forced tool calls and OpenAI Structured Outputs guarantee the JSON parses and matches types. They **do not** guarantee `"delta": "23%"` is real. Constrained decoding (Outlines/XGrammar) isn't available on hosted Anthropic/OpenAI anyway, and there's measured evidence it degrades quality: ["Let Me Speak Freely?"](https://arxiv.org/abs/2408.02442) found significant reasoning decline under format restriction, and [ACL RANLP 2025](https://aclanthology.org/2025.ranlp-1.124/) found instruction-tuned models frequently degrade on generation tasks under constraint.

**So the guarantee has to come from a deterministic verifier, not the generation step.**

### 6.2 The cite-the-field-ID pattern

The model never sees raw findings or the fact sheet. It sees only the already-validated structured summary, and must declare which field IDs back each sentence:

```json
facts = [
  {"id": "F1", "label": "total_findings",  "value": 12,    "kind": "count"},
  {"id": "F2", "label": "critical",        "value": 3,     "kind": "count"},
  {"id": "F3", "label": "mention_delta_pp","value": -8,    "kind": "pct_delta"}
]

→ {"sentences": [
     {"text": "This cycle surfaced 12 findings, 3 of them Critical.", "fact_ids": ["F1","F2"]},
     {"text": "Mention rate fell 8 percentage points.",               "fact_ids": ["F3"]}
   ]}
```

This converts unconstrained factual recall (where recall errors are the dominant hallucination mode) into **closed-set selection + composition** over a tiny enumerated set. Same principle as the Narrative Science NLG lineage: extract intents → generate structure → substitute verified values, never letting prose and facts originate from the same generative step.

### 6.3 The verifier — build this carefully, it's the actual guarantee

Two independent checks per sentence:
1. Every cited `fact_id` exists.
2. **Every number extracted from the raw text** (regex, not trusting the model's self-reported citations) matches a cited fact within tolerance. This catches the model citing F1 while writing a different fabricated number.

**Unit normalization is the hard part.** "6 of 12", "50%", and "half" must all normalize to the same canonical value. Match and *consume spans* in order — ratio → percentage-points → percentage → "half" → bare number — or "6 of 12" gets double-counted as claims "6" and "12".

```python
_RATIO_RE    = re.compile(r"\b(\d+)\s+of\s+(\d+)\b", re.I)
_PP_DELTA_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:percentage\s*points?|pts?\b)", re.I)
_PCT_RE      = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
_PLAIN_NUM_RE= re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")

def extract_numeric_claims(text: str) -> list[ExtractedClaim]:
    claims, consumed = [], []
    for m in _RATIO_RE.finditer(text):
        num, den = int(m.group(1)), int(m.group(2))
        if den:
            claims.append(ExtractedClaim(m.group(0),
                (Decimal(num)/Decimal(den)*100).quantize(Decimal("0.01")), "ratio_as_pct"))
            consumed.append(m.span())
    # … pp_delta, pct, "half", then plain numbers — each skipping consumed spans
    return claims
```

Also check **enum terms**: if "Critical" appears in the prose, a cited fact must have that value.

No drop-in library does this — teams build it in-house. Related academic work: [ClaimDB](https://arxiv.org/html/2601.14698) (verification over structured data), [claim-extraction survey](https://arxiv.org/html/2502.04955v1).

**NLI entailment as a second layer:** worth adding, but only as belt-and-suspenders. It catches what regex can't — qualitative overclaiming ("an alarming trend" with no trend field) and **direction reversal** ("improved" vs "worsened" with the number unchanged). It's probabilistic, so make it a *stricter gate to fallback*, not a hard block.

### 6.4 Fallback policy

1. **Retry once** with the specific `VerificationFailure` list fed back, regenerating only the failing sentences — cheaper and avoids introducing new errors elsewhere.
2. **Fall back to a pure template** f-string built from the fact fields. Wooden but 100% correct, which is strictly better for a product whose pitch is "no invented facts."
3. **Never silently drop** the failing claim — that's silent data loss. Log it; track fallback-rate as a pipeline health metric.
4. Hard error only if even the template is impossible — that means an upstream bug in the "already-validated" step.

### 6.5 Determinism

`temperature=0` does not give reproducibility. The cause is **batch-size-dependent floating-point non-associativity in GPU kernels** — the same request in a different batch composition takes a different reduction order and can flip the argmax even under greedy decoding. Client-side temperature has no control over it.

So: don't chase model determinism, **cache**. Key on `sha256(canonical_json(facts) + prompt_fingerprint + model_id)`, canonicalizing the JSON (sorted keys, fixed float formatting) first. **Cache the verified output, not the raw LLM response** — so a hit skips both the call and re-verification, and a fallback-template result caches identically. Any change to the narrative prompt, fact schema, *or verifier logic* must bump the fingerprint — otherwise you serve a narrative verified against a looser verifier.

---

## 7. Judge QA

### 7.1 Gold set sized by the rare class, not total volume

Total sample size is the wrong knob. What matters is **how many Critical/High examples** you have.

At a 6% base rate: 50 traces → ~3 minority examples (useless). 200 → ~12. For ~20 stable minority examples you need roughly `20 / base_rate` total. Size backwards from the class you care about, and oversample deliberately: stratify across "judge said Critical/High," "judge said no-flag," and boundary cases (near-threshold severities, ambiguous evidence, long/short answers). Random sampling under-represents exactly the cases that break judges.

**Labeler disagreement:** never silently pick one. Record both, compute agreement, route disagreements to a third adjudicator or a documented tie-break — for a client-facing product, "escalate to Critical when in doubt," since false negatives on Critical cost more.

### 7.2 Use Gwet's AC1, not Cohen's kappa

This is the single most important metric decision, and it's counterintuitive.

**The kappa paradox:** kappa penalizes agreement in proportion to class imbalance. With most answers having no flags, expected chance agreement is already very high, so kappa looks mediocre even at near-perfect real agreement. A documented case: two reviewers at **97.5% raw agreement** on a 5%-prevalence task produced **Cohen's kappa 0.747** but **Gwet's AC1 0.972**.

**Report AC1 as headline, alongside raw agreement, kappa, and the full confusion matrix.** Never one number alone.

**And the actual production gate is per-class recall on Critical/High, not aggregate accuracy.** A judge that outputs "no flag" for everything scores 95%+ accuracy against a 5%-prevalence set with *zero recall on the class that matters*.

```python
def gate_critical_high_recall(report: AgreementReport, floor: float = 0.90) -> list[str]:
    return [f"{lbl} recall {report.per_class_recall[lbl]:.3f} below {floor}"
            for lbl in ("CRITICAL", "HIGH")
            if not (report.per_class_recall.get(lbl, float("nan")) >= floor)]
```

Libraries: [`irrCAC`](https://irrcac.readthedocs.io/) (AC1/AC2 + kappa + Krippendorff in one package, by a Gwet collaborator) and `sklearn.metrics` for the confusion matrix. Verify `irrCAC.raw.CAC(...).gwet()`'s exact return shape against the installed version.

### 7.3 Bias mitigation

Measured magnitudes worth knowing:
- **Position bias:** GPT-4-as-judge showed significant first-position preference; **swap-consistency commonly 0.7–0.8**, i.e. 20–30% of judgments reverse purely from presentation order.
- **Self-preference:** the [dedicated study](https://arxiv.org/html/2410.21819v1) across 8 models found GPT-4 had the strongest self-preference, attributable not to literal self-recognition but to rating **lower-perplexity (more familiar-sounding) text** more favorably. So a judge from the same family as the generator is structurally biased even without self-identification.

Checklist: run both orders and treat disagreement as "flag for human review," not noise to average · use a **cross-family judge**, or a second-family judge on Critical/High only · force evidence citation (auditable disagreements) · explicit anti-verbosity rubric language · periodic adversarial canary probes (verbose-but-wrong vs terse-but-correct) independent of the main gold set.

Set expectations at the honest ceiling: MT-Bench found strong judges reach **>80% agreement with humans — the same level as human-human agreement.** Not "the judge is right," but "the judge agrees with a careful human about as often as two careful humans agree."

### 7.4 Review workflow

Don't over-tool it. Argilla/Label Studio are the escalation path, not the start. For two reviewers weekly, a structured sheet works — **the critical property isn't the tool, it's blind independent labeling before reconciliation.** Anchoring on the judge's verdict (or each other's) is how small-team gold sets get silently contaminated.

Record every override durably: `(case_id, judge_verdict, human_label, reviewer, rationale, prompt_fingerprint_at_judge_time)`. Tying it to the prompt fingerprint is what turns "the judge feels off lately" into a concrete ticket.

### 7.5 Prompt regression gates

Treat prompt changes like code changes. Before merging: run against a **frozen holdout partition** never used during prompt iteration, and require AC1 and Critical/High recall to **meet or beat the previous version** — a regression blocks the merge, not just an absolute floor. Your fingerprint cache already forces prompt versioning; extend it so every eval run records the fingerprint it scored, giving a queryable history of "recall over time, per prompt version."

---

## 8. Revised task notes for the spec

> **✅ All applied to `audit-packaging-spec.md` on 2026-08-02.** This table is now a *changelog*, not
> a to-do — the spec itself carries the corrected versions, each with a dated revision note. Read it
> to understand why a task says what it says; do not re-apply these changes.


Corrections and additions to `docs/audit-packaging-spec.md`:

| Spec task | Change |
|---|---|
| **P0-T1** | Replace the pure content-hash `finding_id` with the two-layer design (§1): `row_hash` for idempotency + persisted `cluster_id` matched against a registry. This is the difference between a working lifecycle and a broken one. |
| **P0-T3** | Add the frozen-vocabulary warning if any TF-IDF fallback is used. Add `unclassified_count / total` as a tracked metric. |
| **P1-T1** | Specify Union-Find + registry, explicitly *not* HDBSCAN/agglomerative. Add the sort-before-iterate determinism requirement. |
| **P1-T7** | **Rewrite.** `position: running()` does not exist in Chromium. Use `headerTemplate`/`footerTemplate`. Add the "pick one margin source" rule and the base64-in-`@page` caveat. |
| **P2-T2** | Add the run-coverage gate and N=2 confirmation rule as *normative*, not optional. Add the merge/split ledger. |
| **P2-T3** | Specify hand-rolled with `statistics.NormalDist`, no new deps. Add the ICC/DEFF step — `n_eff`, not raw n. |
| **P2-T4** | Replace the fixed 15pp with computed MDE. Add Benjamini–Hochberg for the ~20 simultaneous comparisons. |
| **P2-T6** | Add: `RenderModeContext` flag; Recharts `'use client'` is permanent; `ResponsiveContainer` must be swapped for fixed dims in print. |
| **New task** | **Lazy-loading / virtualization audit.** Any `loading="lazy"`, `ssr:false`, or windowed table silently drops content from the PDF. This deserves its own task; it's invisible on the live page. |
| **P3-T5** | Standalone Docker worker, not serverless. One Browser, per-request Context. Two-pass render for TOC. `pdf-lib` has no outline API. |
| **P4-T1** | **Gwet's AC1, not Cohen's kappa**, and gate on per-class Critical/High recall. |
| **P4-T4** | Add the cite-the-field-ID pattern and the span-consuming numeric extractor. Cache the *verified* output. |

---

## 9. Sources

**Dedup & clustering** — [Manku et al., Detecting Near-Duplicates for Web Crawling](https://research.google.com/pubs/archive/33026.pdf) · [RETSim](https://arxiv.org/html/2311.17264) · [SimText](https://github.com/oudb/SimText) · [datasketch MinHashLSH](https://ekzhu.com/datasketch/lsh.html) · [RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/) · [OpenSanctions identifiers](https://www.opensanctions.org/docs/identifiers/) · [Zingg incremental clustering](https://www.zingg.ai/post/fuzzy-matching-at-scale-part-5-incremental-flow-and-living-clusters) · [dedupe.io](https://github.com/dedupeio/dedupe) · [ABCDE cluster-ID evaluation](https://arxiv.org/abs/2409.18254) · [Princeton near-duplicate notes](https://www.cs.princeton.edu/courses/archive/spr08/cos435/Class_notes/duplicateDocs_corrected.pdf) · [Union-Find clustering](https://dinocausevic.com/2024/09/11/union-find-hierarchical-clustering/) · [Canopy clustering](http://www.kamalnigam.com/papers/canopy-kdd00.pdf) · [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) · [B-cubed metrics](https://pypi.org/project/bcubed-metrics/) · [er_evaluation](https://er-evaluation.readthedocs.io/en/latest/er_evaluation.metrics.html) · [YAKE](https://github.com/INESCTEC/yake) · [Snorkel weak supervision](https://www.snorkel.org/blog/weak-supervision) · [Interpretable ML: decision rules](https://christophm.github.io/interpretable-ml-book/rules.html)

**Statistics** — [Wilson interval derivation](https://www.econometrics.blog/post/the-wilson-confidence-interval-for-a-proportion/) · [Newcombe 1998](http://www.stats.org.uk/statistical-inference/Newcombe1998.pdf) · [Brown/Cai/DasGupta, Interval Estimation for a Binomial Proportion](http://www.acsu.buffalo.edu/~cxma/STA517/Interval%20Estimation%20for%20Binomial%20Proportion-StatSci.pdf) · [Fagerland/Lydersen/Laake](https://www.ms.uky.edu/~mai/sta635/FagerlandLydersenLaake2011---RecommendedCIsForTwoIndependent....pdf) · [Why overlapping CIs mean nothing](https://medium.com/data-science/why-overlapping-confidence-intervals-mean-nothing-about-statistical-significance-48360559900a) · [Kish design effect (PracTools)](https://cran.r-project.org/web/packages/PracTools/vignettes/Design-effects.html) · [Do Repetitions Matter? (ICC in LLM eval)](https://arxiv.org/html/2509.24086v1) · [MDE & power](https://blog.x.com/engineering/en_us/a/2016/power-minimal-detectable-effect-and-bucket-size-estimation-in-ab-tests) · [Bonferroni vs BH](https://www.statsig.com/blog/controlling-type-i-errors-bonferroni-benjamini-hochberg) · [p-chart control limits](https://www.orbitaljump.com/spc-quality-charts/blog/p-chart-control-limits) · [scipy-stubs](https://github.com/scipy/scipy-stubs) · [Hypothesis](https://hypothesis.readthedocs.io/) · [Wilke, Visualizing Uncertainty](https://clauswilke.com/dataviz/visualizing-uncertainty.html) · [Absence of evidence is not evidence of absence](https://pmc.ncbi.nlm.nih.gov/articles/PMC351831/)

**Rendering & PDF** — [Chromium @page margin boxes Intent to Ship](https://groups.google.com/a/chromium.org/g/blink-dev/c/XKb6IQZXNks) · [Chrome for Developers: print margins](https://developer.chrome.com/blog/print-margins) · [string-set() open issue](https://issues.chromium.org/issues/376420244) · [Playwright @page margin bug](https://github.com/microsoft/playwright/issues/34423) · [Playwright header/footer gotchas](https://github.com/microsoft/playwright/issues/14441) · [Playwright PDF outline request](https://github.com/microsoft/playwright/issues/29417) · [pdf-lib outline issues](https://github.com/Hopding/pdf-lib/issues/786) · [headless print-to-pdf caveats](https://andre.arko.net/2025/05/25/chrome-headless-print-to-pdf/) · [Playwright in Docker](https://bug0.com/knowledge-base/playwright-docker) · [Playwright memory in production](https://medium.com/@onurmaciit/8gb-was-a-lie-playwright-in-production-c2bdbe4429d6) · [@sparticuz/chromium](https://github.com/Sparticuz/chromium) · [Vercel 250MB limit](https://vercel.com/kb/guide/troubleshooting-function-250mb-limit) · [Recharts SSR/RSC bug](https://github.com/recharts/recharts/issues/4336) · [Recharts print resize bug](https://github.com/recharts/recharts/issues/1114) · [lazy loading vs print (whatwg)](https://github.com/whatwg/html/issues/6581) · [break-inside grid bug](https://bugs.chromium.org/p/chromium/issues/detail?id=719908) · [repeating table headers](https://blog.dev030.com/posts/repeating-table-headers-pdf-downloads-using-headless-chrome) · [diff-pdf](https://vslavik.github.io/diff-pdf/) · [tnum missing from fonts](https://github.com/google/fonts/issues/1500)

**Lifecycle** — [Tenable vulnerability states](https://docs.tenable.com/vulnerability-management/Content/Explore/Findings/VulnerabilityStates.htm) · [Qualys status levels](https://docs.qualys.com/en/vm/latest/scans/vulnerability_status.htm) · [GitHub code scanning alert states](https://docs.github.com/en/code-security/how-tos/manage-security-alerts/manage-code-scanning-alerts/resolve-alerts) · [SonarQube new code](https://docs.sonarsource.com/sonarqube-server/user-guide/about-new-code) · [Semgrep findings in CI](https://docs.semgrep.dev/semgrep-ci/findings-ci) · [Nagios flapping detection](https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/flapping.html) · [Gaps and islands](https://www.practicewindowfunctions.com/learn/gap_and_island) · [SCD Type 2](https://datadriven.io/data-modeling/slowly-changing-dimensions) · [When not to use event sourcing](https://event-driven.io/en/when_not_to_use_event_sourcing/) · [Expand/contract migrations](https://dev.to/jp_fontenele4321/the-expand-and-contract-pattern-for-zero-downtime-migrations-445m) · [freezegun fixture gotcha](https://github.com/spulec/freezegun/issues/176) · [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html) · [ApprovalTests.Python](https://github.com/approvals/approvaltests.python)

**Narrative & judge QA** — [Let Me Speak Freely?](https://arxiv.org/abs/2408.02442) · [The Hidden Cost of Structure (RANLP 2025)](https://aclanthology.org/2025.ranlp-1.124/) · [JSONSchemaBench](https://arxiv.org/html/2501.10868v1) · [Thinking Machines: Defeating Nondeterminism](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) · [SelfCheckGPT](https://arxiv.org/pdf/2303.08896) · [Patronus Lynx](https://docs.patronus.ai/docs/research_and_differentiators/Lynx/base) · [DeepEval + pytest](https://qaskills.sh/blog/deepeval-pytest-llm-testing-guide) · [RAGAS faithfulness](https://qaskills.sh/blog/ragas-faithfulness-answer-relevancy-guide) · [Gwet's AC1 vs kappa](https://mappedresearch.com/blog/inter-rater-reliability-screening) · [AC1 comparative literature](https://www.sciencedirect.com/science/article/pii/S2215016123002108) · [irrCAC](https://irrcac.readthedocs.io/) · [Position bias in LLM judges](https://mbrenndoerfer.com/writing/position-bias-in-llm-judges) · [Self-preference bias study](https://arxiv.org/html/2410.21819v1) · [MT-Bench / Chatbot Arena](https://arxiv.org/abs/2306.05685) · [Golden dataset evaluation](https://langfuse.com/resources/engineering/golden-dataset-evaluation) · [CI/CD for evals](https://www.kinde.com/learn/ai-for-software-engineering/ai-devops/ci-cd-for-evals-running-prompt-and-agent-regression-tests-in-github-actions/) · [ClaimDB](https://arxiv.org/html/2601.14698)

---

*Compiled 2026-08-01 from 5 implementation-research agents. Findings flagged verified vs inferred where the underlying agent distinguished them. Numbers and API details from fast-moving vendors should be re-verified at implementation time.*
