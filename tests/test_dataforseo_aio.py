"""DataForSEO as the AI Overviews vendor.

Covers the request contract, the parser's failure behaviour, and — since 2026-07-28 — the
response layout, pinned against real captured bodies in ``tests/fixtures/``.

Those fixtures earned their place. The parser written from documentation was **2.1x wrong
on AI Overviews and 3.1x wrong on AI Mode**, concatenating each element's copy of the
answer onto the whole-answer ``markdown``, and every unit test in this file passed while
it did. That is the same failure mode as the 2026-07-27 location-format bug: a vendor
format written from docs and then tested against our own wrong assumption.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.api.engine_registry import build_engines
from src.config import settings
from src.engines.dataforseo_ai_overviews import (
    DATAFORSEO_SERP_URL,
    DataForSEOAIOverviewsEngine,
    parse_ai_overview,
)


@pytest.fixture
def creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATAFORSEO_LOGIN", "login")
    monkeypatch.setattr(settings, "DATAFORSEO_PASSWORD", "password")


def test_the_engine_name_is_the_surface_not_the_vendor(creds: None) -> None:
    """The invariant that let the vendor change cost nothing downstream.

    The routing policy, the cost table, the teaser's labels/colours/credibility and every
    stored run's `engine_name` are keyed on "google_ai_overviews". SearchApi served this
    surface until 2026-07-28 under the SAME name, which is why swapping to DataForSEO
    touched none of them — and why a future vendor must keep it too.
    """
    from src.api.engine_registry import ENGINE_SOURCES

    assert DataForSEOAIOverviewsEngine.ENGINE_NAME == "google_ai_overviews"
    assert "google_ai_overviews" in ENGINE_SOURCES
    # A SERP capture has no model parameter, so it never pollutes run metadata.
    assert DataForSEOAIOverviewsEngine.MODEL_ID == ""


def test_build_engines_passes_the_location_through_to_dataforseo(creds: None) -> None:
    engines, skipped = build_engines(
        ["google_ai_overviews"], location="Berkeley,California,United States"
    )
    assert skipped == []
    engine = engines[0]
    assert isinstance(engine, DataForSEOAIOverviewsEngine)
    assert engine._location == "Berkeley,California,United States"


def test_missing_credentials_raise_rather_than_capture_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DATAFORSEO_LOGIN", None)
    monkeypatch.setattr(settings, "DATAFORSEO_PASSWORD", None)
    with pytest.raises(ValueError, match="DATAFORSEO"):
        DataForSEOAIOverviewsEngine()


def test_request_matches_the_documented_contract(creds: None) -> None:
    """Verified against DataForSEO's docs: array body, location_name in the same
    comma-no-space hierarchy this repo already stores for SearchApi."""
    engine = DataForSEOAIOverviewsEngine(location="Berkeley,California,United States")
    task = engine._task("best plumber in Berkeley")
    assert task["keyword"] == "best plumber in Berkeley"
    assert task["location_name"] == "Berkeley,California,United States"
    # Both AI-Overview flags on: without load_async_ai_overview the capture silently
    # misses Overviews Google serves asynchronously, which would under-report the surface
    # in exactly the invisible way this codebase keeps getting bitten by.
    assert task["load_async_ai_overview"] is True
    assert task["expand_ai_overview"] is True
    assert DATAFORSEO_SERP_URL.endswith("/serp/google/organic/live/advanced")


def test_no_location_means_no_location_field(creds: None) -> None:
    # Absent, not empty-string: an empty locale sent to a vendor is a real request for
    # "somewhere", which is not a local measurement.
    assert "location_name" not in DataForSEOAIOverviewsEngine()._task("q")


def test_no_ai_overview_in_the_body_is_not_an_error(creds: None) -> None:
    """The common case. Google shows no Overview on most SERPs and on essentially no
    local-intent ones, so this must read as 'no data', never as a failure."""
    body: dict[str, Any] = {
        "status_code": 20000,
        "tasks": [{"result": [{"items": [{"type": "organic", "title": "Some result"}]}]}],
    }
    assert parse_ai_overview(body) == (None, [])


def test_parser_never_raises_on_a_malformed_body(creds: None) -> None:
    for body in (
        {},
        {"tasks": []},
        {"tasks": [{}]},
        {"tasks": [{"result": []}]},
        {"tasks": [{"result": [{}]}]},
        {"tasks": [{"result": [{"items": "not-a-list"}]}]},
        {"tasks": [{"result": [{"items": [None, 42, "x"]}]}]},
    ):
        assert parse_ai_overview(body) == (None, [])


def test_elements_are_assembled_only_when_top_level_markdown_is_missing(
    creds: None,
) -> None:
    """The fallback path, and the dedupe rule.

    A real element always carries the whole answer in top-level ``markdown`` and repeats
    it across ``items`` — taking both is what made the first parser 2.1x too long. Here
    ``markdown`` is absent, so assembling from ``items`` is correct rather than duplicative.
    """
    body: dict[str, Any] = {
        "status_code": 20000,
        "tasks": [
            {
                "result": [
                    {
                        "items": [
                            {"type": "organic", "title": "ignore me"},
                            {
                                "type": "ai_overview",
                                "items": [
                                    {"text": "A sudden pressure drop is usually the valve."},
                                    {"markdown": "Check the regulator next."},
                                ],
                                "references": [
                                    {"url": "https://a.example/one", "title": "One"},
                                    {"url": "https://b.example/two", "title": "Two"},
                                    {"url": "https://a.example/one", "title": "dupe"},
                                ],
                            },
                        ]
                    }
                ]
            }
        ],
    }
    text, urls = parse_ai_overview(body)
    assert text is not None
    assert "usually the valve" in text
    assert "Check the regulator next." in text
    # Citation order is Google's ranking; duplicates collapse without reordering.
    assert urls == ["https://a.example/one", "https://b.example/two"]


def test_top_level_markdown_wins_over_the_repeated_elements(creds: None) -> None:
    """The actual bug, pinned. Both are present in every real body; taking both
    concatenates the answer with itself."""
    body: dict[str, Any] = {
        "status_code": 20000,
        "tasks": [
            {
                "result": [
                    {
                        "items": [
                            {
                                "type": "ai_overview",
                                "markdown": "The whole answer.",
                                "items": [
                                    {"markdown": "The whole"},
                                    {"markdown": "answer."},
                                ],
                            }
                        ]
                    }
                ]
            }
        ],
    }
    text, _urls = parse_ai_overview(body)
    assert text == "The whole answer."


def test_a_task_level_error_is_a_failure_not_an_empty_overview(
    creds: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DataForSEO returns HTTP 200 with a per-task status code, so an auth failure or an
    exhausted balance arrives looking like a perfectly fine response. Reading that as
    'no Overview' would silently turn a billing problem into a measured absence."""
    engine = DataForSEOAIOverviewsEngine(location="Berkeley,California,United States")

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"status_code": 40200, "status_message": "Payment Required."}

    monkeypatch.setattr(engine._client, "post", lambda *a, **k: _Response())
    assert engine._fetch("q") is None
    assert engine.query_with_citations("q") == (None, [])
    # And it must fail the liveness probe, so the run reports the surface as dead rather
    # than quietly measuring nothing.
    assert engine.probe("q")[0] is False


# --- Verified against captured live responses -----------------------------------
#
# The fixtures are REAL bodies (2026-07-28), trimmed only by dropping the organic/video
# blocks the parser never reads. They exist because the docs-written parser was 2.1x
# wrong on AI Overviews and 3.1x wrong on AI Mode, and every unit test passed anyway —
# the same failure mode as the 2026-07-27 location-format bug.


def _fixture(name: str) -> dict[str, Any]:
    import json
    import pathlib

    return json.loads((pathlib.Path(__file__).parent / "fixtures" / name).read_text())


def _overview_item(body: dict[str, Any]) -> dict[str, Any]:
    items = body["tasks"][0]["result"][0]["items"]
    return next(i for i in items if i.get("type") == "ai_overview")


def test_ai_overview_text_is_the_elements_own_markdown_not_a_concatenation() -> None:
    body = _fixture("dataforseo_ai_overview.json")
    text, urls = parse_ai_overview(body)
    # Byte-exact against what Google actually showed. The bug this pins: walking every
    # nested node concatenated the top-level markdown with each `items` element repeating
    # the same prose, giving 5601 chars for a 2665-char answer.
    assert text == _overview_item(body)["markdown"]
    assert len(text or "") == 2665
    assert len(urls) == 4
    assert all(u.startswith("http") for u in urls)
    # Deduped: the same citation appears on both the overview and its elements.
    assert len(urls) == len(set(urls))


def test_ai_mode_shares_the_shape_and_the_parser() -> None:
    from src.engines.dataforseo_ai_mode import parse_ai_mode

    body = _fixture("dataforseo_ai_mode.json")
    # The AI Mode endpoint returns an item literally typed "ai_overview" — which is why
    # one parser serves both and the double-count fix can only be made once.
    assert _overview_item(body)["type"] == "ai_overview"
    text, urls = parse_ai_mode(body)
    assert text == _overview_item(body)["markdown"]
    assert len(text or "") == 2835
    assert parse_ai_mode(body) == parse_ai_overview(body)
    assert len(urls) == 27


def test_ai_mode_answers_the_local_intent_query_ai_overviews_cannot() -> None:
    """The entire justification for the swap, pinned to a real capture.

    AI Overviews returned nothing for a local-intent query in either measured run (0 of 5
    and 0 of 5). AI Mode answers "best plumber in Berkeley" with a ranked table naming
    the client — which is the finding a local audit exists to produce.
    """
    from src.engines.dataforseo_ai_mode import parse_ai_mode

    text, _urls = parse_ai_mode(_fixture("dataforseo_ai_mode.json"))
    assert text is not None
    assert "Albert Nahman" in text
    assert "LemonTree Plumbing" in text


def test_a_table_element_survives_into_the_answer_text() -> None:
    """AI Mode emits `ai_overview_table_element` for ranked comparisons. The table is
    part of the answer a customer reads, so it must not be dropped on the floor."""
    from src.engines.dataforseo_ai_mode import parse_ai_mode

    body = _fixture("dataforseo_ai_mode.json")
    kinds = {e.get("type") for e in _overview_item(body)["items"]}
    assert "ai_overview_table_element" in kinds
    text, _ = parse_ai_mode(body)
    assert text is not None and "| Plumber | Rating |" in text
