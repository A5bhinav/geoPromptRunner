# Engine repin spec — the six-surface search set (2026-08-01)

**Audience:** an agent implementing these changes in `geoPromptRunner`.
**Scope:** repin three engines, rewrite one adapter, and lift the concurrency cap that
would otherwise negate the rewrite. Judge changes are explicitly **out of scope**.

Read `.claude/skills/geo-dev/SKILL.md` before starting. The invariants in `CLAUDE.md`
apply in full — engines return `None` on error and never raise; every change passes
`mypy src/ && ruff check src/ && pytest tests/`; `docs/build-log.md` gets one append-only
entry when this is done.

## Target state

| Surface | Current pin | **Target pin** | Change |
|---|---|---|---|
| `anthropic_search` | `claude-sonnet-4-5-20250929` | **`claude-sonnet-5`** | one constant + `UNDATED_PINS` |
| `openai_search` | `gpt-5-search-api-2025-10-14` | **`gpt-5.6-luna` + Responses `web_search`** | **adapter rewrite + concurrency cap + template** |
| `gemini_grounded` | `gemini-2.5-flash` | **`gemini-3.6-flash`** | one constant |
| `perplexity` | `sonar` | `sonar` | none (watch item, §8) |
| `google_ai_mode` | DataForSEO | DataForSEO | none |
| `google_ai_overviews` | DataForSEO | DataForSEO | none |

## Run configuration

**25 queries, `runs_per_query = 3`** → **75 cells per engine**, 450 cells across the six
surfaces. This is a change from the current default of 5 and needs an explicit edit — see
§4.

| Surface | $/call | Share | 75 cells |
|---|---|---|---|
| `anthropic_search` (`claude-sonnet-5`) | $0.0372 | 50.5% | $2.79 |
| `openai_search` (`gpt-5.6-luna` + `web_search`) | $0.0140 | 19.0% | $1.05 |
| `gemini_grounded` (`gemini-3.6-flash`) | $0.0104 | 14.1% | $0.78 |
| `perplexity` (`sonar`) | $0.0054 | 7.4% | $0.41 |
| `google_ai_mode` | $0.0040 | 5.4% | $0.30 |
| `google_ai_overviews` | $0.0026 | 3.5% | $0.19 |
| **Total engine spend** | **$0.0736** | | **$5.52** |

**$5.52/audit through Aug 31; $6.54 from Sep 1** when Sonnet 5's introductory pricing
ends and `anthropic_search` returns to $0.0508/call. Judge excluded — §6 covers how that
interacts with the spend guard, which is not optional reading. Add ~$0.15 if the flag
verifier runs over the API. Basis: `docs/search-set-costs-25q.md`.

Order: §1 and §3 are ~5 lines each and can land immediately. §2 is the real work.

---

## 1. `anthropic_search` → `claude-sonnet-5`

### Why

`claude-sonnet-4-5-20250929` has a tentative retirement floor of **not sooner than
2026-09-29**. Sonnet 5 is $2/$10 through 2026-08-31 and $3/$15 after — identical to
Sonnet 4.5's current price from September on. The move is required regardless; doing it
now is a 27% discount on the way.

### Edit — `src/engines/anthropic_search_engine.py:18`

Replace the constant **and its comment** — the comment currently claims a dated snapshot,
which stops being true:

```python
# Dated snapshot (Anthropic ids carry their release date) — isolation plan, L3.
MODEL = "claude-sonnet-4-5-20250929"
```
becomes
```python
# UNDATED — see src/engines/model_pins.py. Anthropic publishes no dated snapshot for
# Sonnet 5 (verified 2026-08-01: `claude-sonnet-5` is its own canonical id, as is the
# rest of the current generation — opus-5, opus-4-6/7/8, sonnet-4-6).
MODEL = "claude-sonnet-5"
```

**No other change to this file.** It already declares `SAMPLING = "default"` (line 39) and
its payload (lines 59–64) sends no `temperature` — which matters, because Sonnet 5 **400s
on any non-default temperature**. The parametric `AnthropicEngine` *does* send one and
would break; it is not in this surface set (§9).

### Edit — `src/engines/model_pins.py`

Add a new key to `UNDATED_PINS`.
`tests/test_isolation.py:147-148` requires the reason be **> 60 characters** and the name
be in `ENGINE_SOURCES`, so write a real one:

```python
    "anthropic_search": (
        "claude-sonnet-5. Anthropic publishes no dated snapshot for the Sonnet 5 "
        "generation (verified live 2026-08-01: `claude-sonnet-5` is its own canonical "
        "id, as are opus-5 and sonnet-4-6). Repinned off claude-sonnet-4-5-20250929, "
        "which carried a dated id but a retirement floor of 2026-09-29 — so the choice "
        "was a dated pin that dies in eight weeks or an undated pin that does not. "
        "Drift here is detectable only through the run's engine_models metadata and "
        "answer-level change, not through the model id."
    ),
```

### Tests

`test_anthropic_search_payload_isolated` (line 230) asserts payload isolation, absence of
`system`, `tools == ["web_search_20250305"]`, and the sampling label — **not** a dated
model. It passes unchanged. `test_engine_model_pins_are_dated_or_explicitly_excepted`
passes via the new entry.

---

## 2. `openai_search` → `gpt-5.6-luna` + the Responses `web_search` tool

### Why this is a rewrite, not a repin

`gpt-5-search-api` is a Chat Completions specialized model with **no published model
page** and, on this account, a **6,000 TPM** ceiling against a ~17,230-token call. It has
been measured answering **0 of 10** cells, twice — `src/prompts/local_templates.py:117-121`,
which is why the surface is excluded from the local template today.

The Responses API `web_search` tool bills against **the calling model's** limits (verified:
*"Responses API web search uses the underlying model's tiered rate limits."*).
`gpt-5.6-luna` at Tier 1 is **500,000 TPM / 500 RPM** — 83× the headroom, no tier upgrade.

It is also arguably a fidelity upgrade: ChatGPT today is a frontier model calling a search
tool, not a dedicated search model.

### 2a. Rewrite — `src/engines/openai_search_engine.py`

Keep the class name, `ENGINE_NAME`, the never-raises contract, `record_payload`, and the
`query` → `query_with_citations` delegation. Replace the model constant, the API call, and
the citation extraction.

```python
from __future__ import annotations

import logging
from typing import Any, Literal

import openai
from openai import OpenAI

from src.config import settings
from src.engines.base import BaseEngine
from src.engines.payload_log import record_payload

__all__ = ["OpenAISearchEngine"]

logger = logging.getLogger(__name__)

# The ChatGPT-with-search surface: a frontier model calling the hosted web_search tool
# via the Responses API — which is how ChatGPT itself now works, rather than the
# dedicated search model this adapter used to call.
#
# UNDATED — see src/engines/model_pins.py. OpenAI publishes no dated snapshot for the
# 5.6 family (verified live 2026-08-01: each model page's Snapshots section lists only
# the bare id).
#
# WHY NOT `gpt-5-search-api-2025-10-14` (the previous pin): capped at 6,000 tokens/min
# on this account while one search answer consumes ~17,230, so a real run lost every
# cell to 429s (0 of 10 answered, verified twice). The Responses web_search tool bills
# against the CALLING MODEL's limits instead — Luna is 500,000 TPM / 500 RPM at Tier 1.
# This is a throughput fix first and a cost fix second.
MODEL = "gpt-5.6-luna"

# type must be "web_search", not the older "web_search_preview".
WEB_SEARCH_TOOL: dict[str, Any] = {"type": "web_search"}


class OpenAISearchEngine(BaseEngine):
    """OpenAI with live web search (surface: ChatGPT-with-search).

    Distinct from ``OpenAIEngine`` (parametric memory). ``query_with_citations``
    returns the source URLs OpenAI retrieved. Loads ``OPENAI_API_KEY``. Never
    raises from ``query``/``query_with_citations``.
    """

    ENGINE_NAME: str = "openai_search"
    MODEL_ID: str = MODEL
    # gpt-5.6-* reject a non-default temperature and this adapter sends none, so the
    # surface runs at the provider default. Retrieval varies run to run regardless (L5).
    SAMPLING: Literal["pinned", "default", "none"] = "default"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env (see .env.example).")
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.ENGINE_TIMEOUT_SECONDS,
            max_retries=settings.ENGINE_MAX_RETRIES,
        )

    def query(self, prompt: str) -> str | None:
        text, _citations = self.query_with_citations(prompt)
        return text

    def query_with_citations(self, prompt: str) -> tuple[str | None, list[str]]:
        # One isolated call: a single input string, the hosted web_search tool, and an
        # EXPLICIT store=False. The Responses API defaults to store=True — leaving it
        # implicit would have OpenAI retain every answer, which is exactly the state
        # this codebase's Layer-2 isolation discipline exists to prevent. See §2c: the
        # isolation test's forbidden-param set needs one narrow amendment for this.
        payload: dict[str, Any] = {
            "model": MODEL,
            "input": prompt,
            "tools": [WEB_SEARCH_TOOL],
            "store": False,
        }
        record_payload(self.ENGINE_NAME, payload)
        try:
            response = self._client.responses.create(**payload)
        except openai.RateLimitError:
            logger.warning("OpenAI search rate limit hit for model %s", MODEL)
            return None, []
        except openai.APITimeoutError:
            logger.warning("OpenAI search request timed out for model %s", MODEL)
            return None, []
        except openai.APIError as exc:
            logger.warning("OpenAI search API error: %s", exc)
            return None, []
        except Exception as exc:  # never let an engine crash the pipeline
            logger.warning("OpenAI search unexpected error: %s", exc)
            return None, []

        text = getattr(response, "output_text", None)
        urls: list[str] = []
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", None) or []:
                for annotation in getattr(content, "annotations", None) or []:
                    if getattr(annotation, "type", None) != "url_citation":
                        continue
                    url = getattr(annotation, "url", None)
                    if url:
                        urls.append(str(url))
        return text, urls
```

Update the `if __name__ == "__main__":` block to match; it only calls
`query_with_citations`, so it needs no structural change.

**Response shape relied on** (verified from OpenAI's web search tool guide):
`response.output_text` is the answer; `response.output` is a list of items —
`web_search_call` items and `message` items, only the latter carrying content;
`message.content[].annotations[]` holds entries with `type == "url_citation"` and a `url`.
The defensive `getattr` chain is deliberate: this shape is newer than the rest of the
codebase and an `AttributeError` inside an engine would violate the never-raises contract.

### 2b. Lift the concurrency cap — `src/pipeline/prompt_runner.py` ⚠️ REQUIRED

**The rewrite alone does not deliver the throughput win.** Lines 33–35 hard-cap this
surface to one in-flight request:

```python
PROVIDER_CONCURRENCY_OVERRIDES: dict[str, int] = {
    "openai_search": 1,
}
```

`_ProviderGate.__init__` (line 50) applies it by default, so `openai_search` stays
serialized no matter what model it calls. Remove the entry (leaving an empty dict is fine
— the class handles it) and **rewrite the 15-line comment above it**, lines 19–32, which
currently documents the 6k TPM cap as the standing reason for the override. Replace with a
short note that the surface moved to the Responses `web_search` tool on `gpt-5.6-luna`,
which bills against the model's own 500k TPM limit, and that the override is kept as a
mechanism for future per-engine caps.

Do not silently delete the history — the measured 6k/17,230/0-of-10 facts are why the
override existed and belong in the replacement comment as past tense.

### 2c. Isolation test — `tests/test_isolation.py` ⚠️ has a conflict to resolve

`test_openai_search_payload_isolated` (line 168) will fail three ways: it monkeypatches
`_CapturingOpenAI` (which fakes `chat.completions.create`), asserts
`_assert_isolated_chat_payload` on a `messages` key that no longer exists, and asserts
`DATED_MODEL.search(payload["model"])` on a now-undated id.

**And there is a subtler conflict.** `FORBIDDEN_STATE_PARAMS` (lines 25–36) already
contains **`store`** and **`previous_response_id`**. So a payload carrying `store: False`
trips the forbidden-param assertion — even though `store: False` is the *refusal* of
retention, i.e. the guarantee the rule exists to protect, not a violation of it. The set
was written against a Chat Completions world where the param appearing at all meant "keep
this."

Resolve it narrowly. Add a shared helper and use it in **both** assert functions rather
than weakening either:

```python
def _forbidden_state_params(payload: dict[str, Any]) -> set[str]:
    """Stateful params present in an outgoing payload.

    ``store`` is the one entry that can appear legitimately. The Responses API defaults
    to ``store=True``, so an explicit ``store: False`` is how an engine REFUSES retention
    — present-and-False is the isolation guarantee being asserted, not broken.
    Present-and-truthy is still the violation this set was written to catch.
    """
    found = FORBIDDEN_STATE_PARAMS & set(payload)
    if payload.get("store") is False:
        found.discard("store")
    return found
```

Then have `_assert_isolated_chat_payload` (line 42) use `_forbidden_state_params(payload)`
in place of its inline intersection, and add the Responses-shaped double and helper:

```python
class _CapturingOpenAIResponses:
    """Stands in for the OpenAI client's Responses API; records every create() kwargs."""

    captured: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.responses = self

    def create(self, **kwargs: Any) -> Any:
        _CapturingOpenAIResponses.captured.append(kwargs)
        annotation = SimpleNamespace(type="url_citation", url="https://example.com/a")
        content = SimpleNamespace(annotations=[annotation])
        message = SimpleNamespace(type="message", content=[content])
        return SimpleNamespace(output_text="ok", output=[message])


def _assert_isolated_responses_payload(payload: dict[str, Any], prompt: str) -> None:
    """Test B for Responses-API-shaped payloads: one input, nothing retained."""
    assert payload["input"] == prompt
    assert payload.get("store") is False, (
        "the Responses API defaults to store=True; an engine that lets OpenAI retain "
        "the response is not making an isolated call"
    )
    forbidden = _forbidden_state_params(payload)
    assert not forbidden, f"stateful params in outgoing payload: {forbidden}"
```

and rewrite the test:

```python
def test_openai_search_payload_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.engines import openai_search_engine as mod

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(mod, "OpenAI", _CapturingOpenAIResponses)
    _CapturingOpenAIResponses.captured = []
    engine = mod.OpenAISearchEngine()
    text, urls = engine.query_with_citations("best budgeting app")
    assert text == "ok" and urls == ["https://example.com/a"]
    (payload,) = _CapturingOpenAIResponses.captured
    _assert_isolated_responses_payload(payload, "best budgeting app")
    assert [t["type"] for t in payload["tools"]] == ["web_search"]
    _assert_sampling_label_matches(mod.OpenAISearchEngine, payload)
```

**Also amend `src/engines/base.py:36`**, whose docstring states the invariant as "no
stateful endpoint or params: … no `store`". As written the new engine violates it in
letter while honouring it in substance. Reword to something like "no `store: true`" and
say why an explicit `store: false` is the strengthened form of the same rule.

No other test is affected: every other `_CapturingOpenAI` use is the parametric fixture
(lines 93–100, 156), `tests/test_engine_liveness.py` mentions `openai_search` only as
string data, and `tests/test_engines.py` never touches it. Confirm with
`grep -rn "openai_search\|OpenAISearchEngine\|gpt-5-search-api" tests/ src/`.

### 2d. `requirements.txt`

Line 5 is `openai>=1.30.0`, which **predates the Responses API** — `OpenAI.responses` does
not exist on it, so `mypy src/` will fail on `self._client.responses.create`. Bump the pin
**and actually upgrade the environment**; editing the file alone does not install anything:

```bash
pip install -U openai
python -c "from openai import OpenAI; print(hasattr(OpenAI(api_key='x'), 'responses'))"
```

Pin at or above whatever version that check passes on. Do not guess the floor.

### 2e. Put the surface back in the local template

`src/prompts/local_templates.py:135` lists
`"gemini_grounded;perplexity;google_ai_mode;openai"` — `openai_search` was removed because
it answered nothing. Add it back, and rewrite the rationale comment at lines 117–131,
which now describes a configuration that no longer exists.

### 2f. `src/engines/model_pins.py`

Add a new key (there is no existing `openai_search` entry to replace):

```python
    "openai_search": (
        "gpt-5.6-luna via the Responses web_search tool. OpenAI publishes no dated "
        "snapshot for the 5.6 family (verified live 2026-08-01: each model page's "
        "Snapshots section lists only the bare id) and returns no system_fingerprint, "
        "so neither drift signal exists. Accepted knowingly: the previous pin "
        "`gpt-5-search-api-2025-10-14` WAS dated but answered 0 of 10 cells against a "
        "6,000 TPM account cap, and a dated pin on a surface that returns nothing is "
        "worth less than an undated pin that returns data. DRIFT IS UNDETECTABLE HERE."
    ),
```

---

## 3. `gemini_grounded` → `gemini-3.6-flash`

### Why

`gemini-2.5-flash` is two generations behind what a person gets in the Gemini app. This is
a **fidelity purchase, not a saving** — say so in the build-log entry. On cost it is
strictly worse:

| | free allowance (paid tier) | $/call inside it | billing unit |
|---|---|---|---|
| `gemini-2.5-flash` | 1,500 **per day** | $0.0035 | per **prompt** |
| `gemini-3.6-flash` | 5,000 **per month** | $0.0104 | per **search executed** |

+$0.52/audit at 75 cells. Grounding on 3.x is **not available on the free tier** — Tier 1
billing is required (confirmed present on this account).

### Edit — `src/engines/gemini_grounded_engine.py:23`

```python
MODEL = "gemini-2.5-flash"
```
becomes
```python
# Stable GA name — Google offers no dated snapshots for stable models (isolation plan,
# L3); dated forms exist only on previews. Repinned off gemini-2.5-flash 2026-08-01:
# 2.5 is two generations behind the surface this engine claims to measure. Costs MORE
# (3.x grounding bills per search executed, not per prompt, and the free allowance is
# 5,000/month rather than 1,500/day) — bought for fidelity, not savings.
MODEL = "gemini-3.6-flash"
```

### Edit — `src/engines/model_pins.py:36`

`gemini_grounded` already has an `UNDATED_PINS` entry, but its reason names
`gemini-2.5-flash`. Update the string to `gemini-3.6-flash`. Leave the `gemini` entry
alone unless §9 is also actioned.

### Tests

`test_gemini_grounded_payload_isolated` (line 326) asserts the prompt, that a tool is
requested, and the sampling label — no model id. Passes unchanged.

---

## 4. `runs_per_query` 5 → 3

`K` is how many times each query is asked of each engine per cycle, to average out
nondeterminism. 25 queries × K=3 = **75 cells per engine**.

Two places set it, and **both** need changing or the two paths disagree:

### Edit — `src/config/settings.py:105`

```python
DEFAULT_RUNS_PER_QUERY: int = int(os.getenv("RUNS_PER_QUERY", "5"))
```
becomes the same line with `"3"`.

⚠️ **Lines 92–104 are a long, measured justification for K=5** — the 2026-06-19
determinism baseline, the 2026-07-28 re-measurement (openai min 60% / mean 80%, anthropic
min 60% / mean 92%), and the conclusion "Both still suggest K=5, so this default holds."
Leaving that comment above a `"3"` makes the code contradict itself in the same breath,
which is the exact failure mode §2b and §5 exist to clean up elsewhere. **Rewrite it** to
record the K=3 decision and what it accepts:

- K=5 was chosen on measured worst-brand label agreement of ~60% on `gemini` and
  `perplexity`. That measurement stands; it is not being refuted.
- This surface set is **entirely retrieval surfaces**, where the retrieved document set
  varies run to run independently of the model — i.e. the noise K exists to average is
  *higher* here, not lower.
- At K=3 one flipped run moves a query's reading by 33 points instead of 20, and 2-of-3
  vs 3-of-3 is not meaningfully distinguishable.
- The decision is a deliberate cost/breadth trade (25 queries × 3 rather than 15 × 5 at
  identical cell count), taken 2026-08-01. Record it as a decision, not as a finding.

Keep the historical measurements in the comment as past tense. They are why anyone would
question K=3 later, and deleting them destroys the only record of what the number cost.

`MAX_RUNS_PER_QUERY` (line 91) is a ceiling, not a default — leave it at 5.

### Edit — `src/prompts/local_templates.py:139`

```python
        ["config", "runs_per_query", "5", "", ""],
```
becomes `"3"`. A CSV template carries its own value and does **not** read
`DEFAULT_RUNS_PER_QUERY`, so changing only `settings.py` would leave every template-driven
run at 5.

### Check

`grep -rn "runs_per_query\|RUNS_PER_QUERY" src/ tests/` before finishing — any other
hard-coded 5 (API defaults, CLI flags, fixtures) is a place the two paths can drift.
Tests that pin `runs_per_query` explicitly are fine and should not be changed to match.

---

## 5. `src/pipeline/cost.py` — fix the estimates

Four figures move. Two are **under-estimates**, which is the direction that actually hurts
because `ROUGH_COST_PER_CALL` feeds `MAX_AUDIT_COST_USD`; two are over-estimates being
corrected downward. Cite the **pricing page, not the model page**, in every comment — an
OpenAI model page carried a two-day-stale Luna price on 2026-08-01.

| Key | Line | Current | Set to | Direction | Basis |
|---|---|---|---|---|---|
| `openai_search` | 29 | 0.030 | **0.014** | over → down | 16,700 in @ $0.20 + 530 out @ $1.20 + $10/1k tool fee |
| `anthropic_search` | 36 | 0.051 | **0.037** | over → down | 10,928 in @ $2 + 534 out @ $10 + $10/1k search fee (Sonnet 5, Aug price) |
| `gemini_grounded` | 37 | 0.010 | **0.011** | **UNDER → up** | 3.6-flash tokens only, inside the 5,000/mo allowance |
| `JUDGE_COST_PER_CALL` | 65 | 0.003 | **0.0098** | **UNDER → up** | cached single-Sonnet judge + verifier at the observed flag rate |

Three caveats to write into the comments rather than leave implicit:

- **`anthropic_search` is a FLOOR.** The 10,928/534 profile is n=1 on a query that
  triggered one web search; a question that searches three times costs more. It is ~50% of
  *engine* spend on this set. Say so.
- **`anthropic_search` reverts to ~0.051 on 2026-09-01** when Sonnet 5's introductory
  pricing ends. Note the date inline so the next reader knows the number has an expiry.
- **`gemini_grounded` is tiered.** $0.011 inside the monthly allowance; **add $0.014 per
  search executed** beyond it. A flat figure cannot express that — put the beyond-quota
  number in the comment.

No test asserts these constants, so this section breaks nothing.

---

## 6. ⚠️ The judge figure interacts with the spend guard — read before shipping §5

`estimate_total_cost_for_queries` (`cost.py:142`) adds `JUDGE_COST_PER_CALL * total_calls`
to the number checked against `MAX_AUDIT_COST_USD` (default $25, `settings.py:107-111`).

On this set — 6 surfaces × 25 queries × K=3 = **450 cells** — raising the judge rate from
$0.003 to $0.0098 takes the judge component from $1.35 to **$4.41**. Added to $5.52 of
engine spend, the guard will see **~$9.93** where it previously saw ~$6.87. Both sit well
under the $25 cap at this size, but the margin narrows as query count or K rises.

That is correct behaviour for an API-judged run. **But if the run is prejudged on the
subscription, the real judge cost is $0** and $4.41 of phantom spend is being charged
against the cap. `estimate_total_cost_for_queries` already takes a `judge: bool` — make
sure the prejudge path passes `judge=False`, and check whether the API/CLI callers do.
Otherwise this correction moves the guard closer to rejecting audits that are in fact
cheaper than before.

Verify the interaction before shipping §5, and record the outcome in the build-log entry.

---

## 7. Verification

### Gate (required, per `CLAUDE.md`)

```bash
mypy src/ && ruff check src/ && pytest tests/
```

### Liveness — the step that catches the failure that actually happens

`src/pipeline/preflight.py:73` sends one real query per engine (`PROBE_PROMPT`) via
`BaseEngine.probe` and drops surfaces that cannot answer. A provider listing cannot
substitute: `models.list` still advertises ids that 404 on use, which is exactly how the
previous `openai_search` pin died silently while runs reported success.

Run one query at K=1 across all six surfaces and confirm **every** one returns text.
`openai_search` must return non-empty text **and** citations — the whole point of the
rewrite.

### Instrument the first real run — five estimates are unmeasured

Set `PAYLOAD_LOG_PATH` and capture, for at least one call per surface:

1. **`openai_search` token usage.** The 16,700-in / 530-out profile was measured on
   `gpt-5-search-api`, not on Luna + the tool, and the tool's `return_token_budget`
   default is undisclosed. Log `response.usage` and correct `cost.py` from it.
2. **`openai_search` reasoning tokens.** Luna is a reasoning model; reasoning bills as
   output and is not in the 530 estimate.
3. **`gemini_grounded` search count.** Log `groundingMetadata` — 3.x bills per search
   executed, so one-vs-three searches is the difference between 40 and 13 audits/month
   inside the free allowance.
4. **`gemini-3.6-flash` answer length.** The cost model assumes it matches 2.5-flash's
   1,385-token mean; output dominates and 3.6's output rate is 3× higher.
5. **`anthropic_search`'s real token profile** across the query set, not n=1.

Write the measured numbers back into `cost.py` and note them in the build-log entry.

---

## 8. Not changing, but worth knowing

**`perplexity` / `sonar`** — no change. But Perplexity's **Sonar Chat Completions is
deprecated** in favour of the Agent API, and this adapter posts to the Chat Completions
endpoint. Same liveness risk pattern as the dead OpenAI pin; preflight will catch it.

**`anthropic_search`'s tool version** is `web_search_20250305`. A newer
`web_search_20260209` exists. Changing it would change what the surface retrieves, so it
is a separate, measured decision — not a drive-by edit. `test_isolation.py:243` asserts
the current value, which is the guard working as intended.

**Pick ONE Google SERP surface per ICP.** `metrics.coverage()` pools all cells into the
headline number, so running `gemini_grounded` + `google_ai_mode` + `google_ai_overviews`
makes Google 3 of 6 surfaces — 50% of the sample — against OpenAI at 17%.
`local_templates.py:126-130` already made this call for the local ICP: AI Mode replaces AI
Overviews, because AIO returned **0 of 5** local-intent queries and `engine_routing.py`
skips them. **Consumer → `google_ai_overviews`. Local → `google_ai_mode`.** If both are
wanted, report them via `coverage_by_engine()` rather than letting both feed the pooled
score.

---

## 9. Explicitly out of scope

- **The judge.** `JUDGE_MODEL` stays `claude-sonnet-4-5-20250929`. Moving it to Sonnet 5
  costs `temperature=0` (Sonnet 5 400s on it), and the gold sets are currently too thin in
  flag-bearing items to measure whether that is safe — `docs/project-queue.md:20-30`.
  Engines first; the judge after a flag-powered gold set exists.
- **The parametric surfaces** `openai`, `anthropic`, `gemini`. Not in this set. If they are
  ever re-enabled: `src/engines/anthropic_engine.py:53` sends `temperature`, which **400s
  on Sonnet 5** — that repin needs the parameter dropped and `SAMPLING = "default"` added
  (it currently inherits `"pinned"` from `base.py:70`).
- **Rewriting the L3 dated-pin rule.** This spec adds two `UNDATED_PINS` entries, which is
  the mechanism working as designed. The broader question — that no current-generation
  model from *any* of the four providers publishes a dated snapshot, so the rule now only
  pins the platform to legacy models — needs a written decision from Abhi and Josh, not a
  code change. See `docs/model-selection-2026-08.md` §4.

---

## 10. Timing

**Repin between client cycles, not mid-engagement.** Answers captured under different pins
are not comparable cycle-over-cycle, so a mid-engagement repin makes part of a client's
apparent "movement" your own churn. All three repins should land together, at one cycle
boundary, and the build-log entry should record the date so a later reader can explain a
discontinuity in the numbers.

## 11. Definition of done

- [ ] `runs_per_query` = **3** in BOTH `settings.py:105` and
      `local_templates.py:139`; the K=5 justification comment at `settings.py:92-104`
      rewritten to record the decision rather than contradict it
- [ ] `anthropic_search` pins `claude-sonnet-5`; `UNDATED_PINS` entry added
- [ ] `openai_search` calls `responses.create` with `tools=[{"type": "web_search"}]` and
      explicit `store=False`; returns text **and** citations; `UNDATED_PINS` entry added
- [ ] **`PROVIDER_CONCURRENCY_OVERRIDES["openai_search"]` removed** and its comment
      (`prompt_runner.py:19-32`) rewritten — without this the rewrite changes nothing
- [ ] `openai_search` added back to `local_templates.py:135`; rationale comment at
      lines 117–131 rewritten
- [ ] `gemini_grounded` pins `gemini-3.6-flash`; its `UNDATED_PINS` reason updated
- [ ] `requirements.txt` bumped **and `pip install -U openai` actually run**
- [ ] `_forbidden_state_params` helper added; both assert helpers use it; `base.py:36`
      docstring reworded so `store: False` is the strengthened rule, not a violation
- [ ] `test_openai_search_payload_isolated` rewritten for the Responses shape; no existing
      isolation assertion weakened
- [ ] `cost.py` updated for all four figures, with floor / expiry / tiering caveats in the
      comments
- [ ] §6 checked: prejudged runs pass `judge=False` to `estimate_total_cost_for_queries`
- [ ] `mypy src/ && ruff check src/ && pytest tests/` all green
- [ ] a real one-query run returns text from every surface, citations from `openai_search`
- [ ] measured token/search counts written back into `cost.py`
- [ ] one append-only entry in `docs/build-log.md`

---

### Sources for every price and limit here

Verified live 2026-08-01.
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) ·
[Anthropic deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations) ·
[OpenAI pricing](https://developers.openai.com/api/docs/pricing) ·
[OpenAI models](https://developers.openai.com/api/docs/models) ·
[OpenAI web search tool](https://developers.openai.com/api/docs/guides/tools-web-search) ·
[OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits) ·
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) ·
[Gemini models](https://ai.google.dev/gemini-api/docs/models)

**Unverified — the implementing agent must confirm, not assume:**

- The exact `openai` SDK version floor for `client.responses`.
- That the Responses API `store` parameter still defaults to `True`. The spec sets
  `store=False` regardless; an isolation guarantee should not depend on a provider default.
- Whether `gpt-5.6-luna` accepts `reasoning: {"effort": "none"}`. If it does, it is a
  latency and output-token lever worth measuring. The spec deliberately sends no
  `reasoning` parameter so the surface runs at the provider default, which is closer to
  what a consumer gets.
- Tier 1 RPM/TPM for `gemini-3.6-flash` — Google no longer publishes per-model limits and
  points at AI Studio. Reported as fine on this account; re-check if the fan-out 429s.
