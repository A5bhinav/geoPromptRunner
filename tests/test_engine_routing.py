"""Intent-scoped engine routing: don't pay a surface to capture nothing.

The policy under test is a single denylist entry — ``google_ai_overviews`` is not asked
``local_intent`` queries, because Google shows the local pack there rather than an AI
Overview (0 of 5 in run e186c524; ~15% industry-wide vs ~93% for the local pack).
"""

from __future__ import annotations

import pytest

from src.pipeline import engine_routing
from src.pipeline.cost import estimate_cost_for_queries
from src.pipeline.engine_routing import (
    ENGINE_POLICY,
    routed_cell_count,
    routed_totals_by_name,
    should_run,
)
from src.pipeline.prompt_runner import run_query_set
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query
from tests.test_engine_liveness import _Stub


def _local_queries() -> list[Query]:
    """A miniature local set: the 4 buckets a trade template actually uses."""
    return [
        Query(query_id="loc-01", text="best plumber in Berkeley", intent=IntentBucket.LOCAL_INTENT),
        Query(
            query_id="loc-02",
            text="emergency plumber Berkeley",
            intent=IntentBucket.LOCAL_INTENT,
        ),
        Query(query_id="hyb-01", text="plumber cost in Berkeley", intent=IntentBucket.HYBRID),
        Query(
            query_id="inf-01",
            text="why is my water pressure low",
            intent=IntentBucket.INFORMATIONAL,
        ),
        Query(query_id="brd-01", text="is Acme Plumbing good", intent=IntentBucket.BRAND),
    ]


def test_ai_overviews_skips_local_intent_and_keeps_the_rest() -> None:
    assert should_run("google_ai_overviews", IntentBucket.LOCAL_INTENT) is False
    for bucket in (IntentBucket.HYBRID, IntentBucket.INFORMATIONAL, IntentBucket.BRAND):
        assert should_run("google_ai_overviews", bucket) is True


def test_ai_mode_has_no_routing_skip() -> None:
    """The reason AI Mode replaces AI Overviews on the local path.

    Overviews is routed out of local_intent because Google doesn't show one there. AI
    Mode answers whatever it is asked, so it must be asked everything — a skip here would
    reintroduce the exact coverage hole the swap was made to close.
    """
    for bucket in IntentBucket:
        assert should_run("google_ai_mode", bucket) is True
    assert "google_ai_mode" not in ENGINE_POLICY


def test_every_other_engine_is_asked_everything() -> None:
    # Only one engine should carry a policy. A second entry is a real decision that
    # needs its own evidence, so this test is the tripwire for adding one silently.
    assert set(ENGINE_POLICY) == {"google_ai_overviews"}
    for name in ("perplexity", "openai_search", "gemini_grounded", "anthropic_search"):
        for bucket in IntentBucket:
            assert should_run(name, bucket) is True


def test_the_policy_carries_its_evidence() -> None:
    # An unexplained routing rule becomes folk knowledge nobody can re-derive — the
    # same reason SAMPLING_BANDS records measured_on/measured_note.
    rationale = ENGINE_POLICY["google_ai_overviews"].rationale
    assert "local pack" in rationale
    assert "e186c524" in rationale


def test_routed_totals_give_each_engine_its_own_denominator() -> None:
    queries = _local_queries()  # 2 local_intent, 3 others
    totals = routed_totals_by_name(queries, ["google_ai_overviews", "perplexity"], 5)
    assert totals["perplexity"] == 5 * 5  # every query
    assert totals["google_ai_overviews"] == 3 * 5  # local_intent skipped
    assert routed_cell_count(queries, [_Stub("perplexity", [])], 5) == 25


def test_the_fan_out_does_not_ask_the_routed_out_cells() -> None:
    aio = _Stub("google_ai_overviews", [])
    ppx = _Stub("perplexity", [])
    results = run_query_set(_local_queries(), [aio, ppx], runs_per_query=1)
    # The point of the whole phase: the SERP surface never sees a local_intent query.
    assert "best plumber in Berkeley" not in aio.calls
    assert "best plumber in Berkeley" in ppx.calls
    assert len(aio.calls) == 3
    assert len(ppx.calls) == 5
    # And no rows exist for the skipped cells, so they can't be read as unanswered.
    aio_rows = [r for r in results if r["engine_name"] == "google_ai_overviews"]
    assert {r["query_id"] for r in aio_rows} == {"hyb-01", "inf-01", "brd-01"}


def test_routing_lowers_the_cost_estimate_it_is_charged_against() -> None:
    from src.pipeline.cost import ROUGH_COST_PER_CALL

    queries = _local_queries()
    engines = [_Stub("google_ai_overviews", []), _Stub("perplexity", [])]
    estimated, total_calls = estimate_cost_for_queries(queries, engines, 5)
    # 25 perplexity cells + 15 AIO cells, not 50.
    assert total_calls == 40
    # Priced off the table rather than hardcoded: this test is about ROUTING, so a
    # vendor price change must not break it — only a change in which cells run should.
    expected = (
        15 * ROUGH_COST_PER_CALL["google_ai_overviews"]
        + 25 * ROUGH_COST_PER_CALL["perplexity"]
    )
    assert estimated == pytest.approx(expected)


def test_the_estimate_counts_the_probe_and_the_offsite_agent() -> None:
    """Both are real spend the budget guard used to be blind to."""
    from src.pipeline.cost import (
        OFFSITE_RUN_COST_USD,
        PREFLIGHT_COST_PER_ENGINE,
        estimate_total_cost_for_queries,
    )

    queries = _local_queries()
    engines = [_Stub("perplexity", [])]
    base, calls = estimate_total_cost_for_queries(queries, engines, 1, False)
    with_extras, calls_again = estimate_total_cost_for_queries(
        queries, engines, 1, False, preflight=True, offsite=True
    )
    assert with_extras == pytest.approx(
        base + PREFLIGHT_COST_PER_ENGINE * len(engines) + OFFSITE_RUN_COST_USD
    )
    # Neither is a measurement cell, so the progress denominator must not move.
    assert calls == calls_again == 5


def test_legacy_count_based_estimate_is_unchanged() -> None:
    """The routing-aware functions were ADDED beside `estimate_cost`, not instead of it,
    so callers holding only a query count keep their exact previous behaviour."""
    from src.pipeline.cost import ROUGH_COST_PER_CALL, estimate_cost

    engines = [_Stub("google_ai_overviews", []), _Stub("perplexity", [])]
    estimated, calls = estimate_cost(5, engines, 5)
    assert calls == 50  # un-routed: every engine x every query x every run
    per_query = ROUGH_COST_PER_CALL["google_ai_overviews"] + ROUGH_COST_PER_CALL["perplexity"]
    assert estimated == pytest.approx(5 * 5 * per_query)


def test_the_local_templates_engine_list_is_a_pinned_decision() -> None:
    """Which surfaces a local audit measures is a decision with evidence behind it, not
    a string that should drift silently.

    - `gemini_grounded` leads: Google's own AI answer, official API, already-paid tier,
      free grounding quota, richest surface on a live probe.
    - `google_ai_mode` is the Google answer surface, NOT `google_ai_overviews`: AI Mode
      answers every intent, while Overviews is absent from ~85% of local-intent SERPs.
    - `openai` is parametric (gpt-5.6-luna): ~100% coverage at ~$0.0015/call.
    - `openai_search` is present again as of 2026-08-01. It was dropped on 2026-07-28
      because OpenAI capped search-class models at 6,000 tokens/min on this account
      while one answer cost ~17,200, so a real run lost every cell to 429s. The surface
      now calls the Responses `web_search` tool on gpt-5.6-luna, which bills against the
      calling model's limits (500k TPM at Tier 1), so the cap no longer applies.
    """
    from src.prompts.assemble import DEFAULT_LOCAL_ENGINES
    from src.prompts.csv_loader import build_template_csv
    from src.prompts.local_templates import TRADES

    expected = "gemini_grounded;perplexity;google_ai_mode;openai;openai_search"
    # The downloadable template and the assembled CSV must name the same surfaces —
    # they are two copies of one decision (see assemble.DEFAULT_LOCAL_ENGINES).
    assert ";".join(DEFAULT_LOCAL_ENGINES) == expected
    for trade in TRADES:
        csv_text = build_template_csv(trade)
        assert f"config,engines,{expected}" in csv_text


def test_an_unknown_engine_defaults_to_running_everything() -> None:
    # A newly added engine must measure normally until someone measures otherwise.
    for bucket in IntentBucket:
        assert should_run("some_future_engine", bucket) is True


def test_policies_are_denylists_not_allowlists() -> None:
    """Structural guard on the design decision, not just its current values.

    An allowlist would have to enumerate BRAND — shared by both ICP families — and so
    could strip a surface from consumer queries while looking like a local-only change.
    """
    policy = ENGINE_POLICY["google_ai_overviews"]
    assert hasattr(policy, "skip_intents")
    assert not hasattr(policy, "intents")
    assert policy.skip_intents == frozenset({IntentBucket.LOCAL_INTENT})
    # A default-constructed policy must skip nothing.
    assert engine_routing.EnginePolicy().skip_intents == frozenset()
