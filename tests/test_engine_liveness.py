"""A dead engine must never pass as a silent one.

Run e186c524 (2026-07-28) finished `done 30/30` while `openai_search` answered 0 of
10 cells — its pinned model was 404. Every assertion here pins one of the places
that failure was invisible.
"""

from __future__ import annotations

import pytest

from src.api.reports import build_report
from src.config import settings
from src.engines.base import BaseEngine
from src.pipeline import preflight
from src.pipeline.orchestrator import AuditOutcome, EnginesUnavailable, run_audit
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet
from src.storage.models import QueryResult


def _qr(qid: str, engine: str, resp: str | None, *, intent: str = "category") -> QueryResult:
    return QueryResult(
        query_id=qid,
        intent=intent,
        prompt="(test)",
        engine_name=engine,
        run_index=0,
        response=resp,
        citations=[],
        timestamp="t",
    )


def _outcome(results: list[QueryResult]) -> AuditOutcome:
    return AuditOutcome(
        run_id="r1",
        client_name="Acme",
        client_domains=["acme.com"],
        competitors=["YNAB"],
        query_set_version="v1",
        runs_per_query=1,
        results=results,
    )


def test_dead_engine_is_not_credited_with_measuring_the_client() -> None:
    report = build_report(
        _outcome(
            [
                _qr("q1", "perplexity", "Acme and YNAB are options."),
                _qr("q2", "perplexity", "YNAB only."),
                _qr("q1", "openai_search", None),
                _qr("q2", "openai_search", None),
            ]
        )
    )
    # The engine list is built from answer existence, not row existence.
    assert report["engines"] == ["perplexity"]
    assert report["dead_engines"] == ["openai_search"]


def test_scorecard_carries_the_denominator_behind_its_rates() -> None:
    report = build_report(
        _outcome(
            [
                _qr("q1", "perplexity", "Acme is an option."),
                _qr("q1", "openai_search", None),
            ]
        )
    )
    # Two cells attempted, one answered — a rate computed over half the intended
    # evidence must say so rather than presenting itself as a full measurement.
    assert report["scorecard"]["attempted_cells"] == 2
    assert report["scorecard"]["answered_cells"] == 1


def test_unanswered_bucket_is_distinguishable_from_an_absent_client() -> None:
    report = build_report(
        _outcome(
            [
                # "category" answered and the client is genuinely absent.
                _qr("c1", "perplexity", "YNAB only.", intent="category"),
                # "brand" never answered at all.
                _qr("b1", "openai_search", None, intent="brand"),
            ]
        )
    )
    rows = {r["bucket"]: r for r in report["by_bucket"]}
    # Both rates read 0.0 — only the coverage fields separate the two cases, which is
    # why a renderer must print "—" for the second rather than "0%".
    assert rows["category"]["mention_rate"] == 0.0
    assert rows["brand"]["mention_rate"] == 0.0
    assert (rows["category"]["answered_cells"], rows["category"]["total_cells"]) == (1, 1)
    assert (rows["brand"]["answered_cells"], rows["brand"]["total_cells"]) == (0, 1)


# --- The preflight probe -------------------------------------------------------
#
# conftest disables ENGINE_PREFLIGHT for the suite, so these tests turn it back on
# explicitly. That split is deliberate: everywhere else a stub engine's recorded
# prompts should be measurement cells only.


class _Stub(BaseEngine):
    """Engine returning a scripted sequence of responses, recording every prompt."""

    def __init__(self, name: str, responses: list[str | None]) -> None:
        self.ENGINE_NAME = name
        self.MODEL_ID = f"{name}-model-2026-01-01"
        self._responses = list(responses)
        self.calls: list[str] = []

    def query(self, prompt: str) -> str | None:
        self.calls.append(prompt)
        return self._responses.pop(0) if self._responses else "fallback answer"


def test_probe_marks_a_dead_engine_dead_and_a_live_one_live() -> None:
    live = _Stub("live", ["a real answer"])
    dead = _Stub("dead", [None, None])
    probes = {p.engine_name: p for p in preflight.probe_engines([live, dead])}
    assert probes["live"].alive is True
    assert probes["dead"].alive is False
    # The reason must name the plausible causes — a bare "failed" sends whoever reads
    # the run record digging through logs.
    assert "deprecated" in probes["dead"].detail


def test_probe_retries_once_so_a_transient_failure_is_not_fatal() -> None:
    flaky = _Stub("flaky", [None, "answered on the second try"])
    (probe,) = preflight.probe_engines([flaky])
    assert probe.alive is True
    assert probe.needed_retry is True
    assert len(flaky.calls) == 2


def test_probe_never_raises_when_an_engine_breaches_the_contract() -> None:
    class _Exploding(BaseEngine):
        ENGINE_NAME = "exploding"
        MODEL_ID = "x"

        def query(self, prompt: str) -> str | None:
            raise RuntimeError("engines are not supposed to do this")

    (probe,) = preflight.probe_engines([_Exploding()])
    assert probe.alive is False


def test_a_serp_engine_with_no_ai_overview_is_alive_not_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression that matters most in this file.

    The first preflight defined liveness as "returned answer text" for every engine and
    dropped a healthy ``google_ai_overviews`` from a live run, because Google showed no
    AI Overview for the probe query. Google shows none for MOST queries — an empty
    capture is data, not a failure. Liveness for a SERP surface is "the request
    succeeded", so this must stay alive with zero chars.
    """
    import httpx

    from src.engines.dataforseo_ai_overviews import DataForSEOAIOverviewsEngine

    monkeypatch.setattr(settings, "DATAFORSEO_LOGIN", "login")
    monkeypatch.setattr(settings, "DATAFORSEO_PASSWORD", "password")
    engine = DataForSEOAIOverviewsEngine(location="Berkeley,California,United States")

    class _Response:
        status_code = 200

        def __init__(self, body: dict[str, object]) -> None:
            self._body = body

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._body

    class _Client:
        """A SERP request that SUCCEEDS but carries no ai_overview block."""

        def post(self, *args: object, **kwargs: object) -> _Response:
            return _Response(
                {"status_code": 20000, "tasks": [{"result": [{"items": [{"type": "organic"}]}]}]}
            )

        def close(self) -> None:
            return None

    engine._client = _Client()  # type: ignore[assignment]  # test double, get/close only
    alive, chars, citations = engine.probe("anything")
    assert alive is True
    assert (chars, citations) == (0, 0)

    # A transport failure IS dead — the distinction the base implementation lost.
    class _BrokenClient:
        def post(self, *args: object, **kwargs: object) -> _Response:
            raise httpx.ConnectError("no route to host")

        def close(self) -> None:
            return None

    engine._client = _BrokenClient()  # type: ignore[assignment]  # test double
    assert engine.probe("anything")[0] is False


def test_probe_prompt_cannot_be_mistaken_for_a_measurement() -> None:
    # It must not name a brand or a client category, because a probe answer that
    # looked like a query answer could be mistaken for evidence.
    assert "{" not in preflight.PROBE_PROMPT
    assert preflight.PROBE_PROMPT.strip() != ""


def test_split_by_liveness_reports_dead_engines_like_a_missing_key() -> None:
    live, skipped, record = preflight.split_by_liveness(
        [_Stub("good", ["answer"]), _Stub("bad", [None, None])]
    )
    assert [e.ENGINE_NAME for e in live] == ["good"]
    assert [name for name, _ in skipped] == ["bad"]
    # The record is what gets persisted, so it must be JSON-safe and explain itself.
    assert record["bad"] == {
        "model_id": "bad-model-2026-01-01",
        "alive": False,
        "chars": 0,
        "citations": 0,
        "needed_retry": False,
        # None here because a plain stub has no vendor message; a real engine that got
        # one (e.g. "Please verify your account") carries it through instead.
        "provider_error": None,
    }


def test_a_vendor_reason_beats_our_guess_in_the_run_record() -> None:
    """When the provider says WHY, that must reach the run — not just a log line.

    "liveness probe returned no answer (model deprecated, key rejected, or provider
    down)" is three guesses. "[40104] Please verify your account" is an instruction.
    """
    stub = _Stub("blocked", [None, None])
    stub.last_error = "HTTP 403 [40104] Please verify your account before using the API."
    (probe,) = preflight.probe_engines([stub])
    assert probe.alive is False
    assert probe.provider_error is not None
    assert "verify your account" in probe.detail

    # A fresh stub: _Stub pops its scripted responses, and the probe above consumed
    # both, so reusing it would answer from the fallback and read as alive.
    blocked = _Stub("blocked", [None, None])
    blocked.last_error = "HTTP 403 [40104] Please verify your account before using the API."
    _live, skipped, record = preflight.split_by_liveness([blocked])
    assert "verify your account" in skipped[0][1]
    assert record["blocked"]["provider_error"] == blocked.last_error


def _qset() -> QuerySet:
    return QuerySet(
        version="v1",
        locked_at="2026-07-28",
        category="plumbing service",
        client="Acme",
        competitors=[],
        queries=[Query(query_id="q1", text="best plumber in Berkeley", intent=IntentBucket.BRAND)],
    )


def test_run_audit_drops_a_dead_engine_before_spending_the_fan_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENGINE_PREFLIGHT", True)
    good = _Stub("good", ["probe answer", "cell answer"])
    dead = _Stub("dead", [None, None])
    outcome = run_audit(_qset(), [good, dead], runs_per_query=1, persist=False, progress=False)
    # The dead engine cost 2 probe calls, not a whole query set, and produced no rows.
    assert len(dead.calls) == 2
    assert {r["engine_name"] for r in outcome.results} == {"good"}


def test_run_audit_refuses_to_run_with_zero_live_engines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENGINE_PREFLIGHT", True)
    # A run against no live surface yields a report full of honest-looking zeros.
    # Stopping loudly is the point.
    with pytest.raises(EnginesUnavailable):
        run_audit(
            _qset(),
            [_Stub("dead1", [None, None]), _Stub("dead2", [None, None])],
            runs_per_query=1,
            persist=False,
            progress=False,
        )


def test_preflight_off_restores_the_previous_behaviour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ENGINE_PREFLIGHT", False)
    dead = _Stub("dead", [None])
    outcome = run_audit(_qset(), [dead], runs_per_query=1, persist=False, progress=False)
    # Exactly one call — the measurement cell, no probe — and the empty result is
    # still recorded, which is what Phase 1's coverage reporting then surfaces.
    assert len(dead.calls) == 1
    assert len(outcome.results) == 1


def test_a_fully_live_run_reports_every_engine() -> None:
    # The no-regression direction: nothing is dropped when everything answers.
    report = build_report(
        _outcome(
            [
                _qr("q1", "perplexity", "Acme."),
                _qr("q1", "openai_search", "Acme."),
                _qr("q1", "gemini_grounded", "Acme."),
            ]
        )
    )
    assert report["engines"] == ["gemini_grounded", "openai_search", "perplexity"]
    assert report["dead_engines"] == []
