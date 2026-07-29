"""The report's methodology section must describe the run, not the current config.

docs/report.md asserted a `gpt-4o` judge long after JUDGE_MODEL moved to Sonnet, and
"temperature pinned to 0" for a run containing a surface that cannot take a temperature.
Both were hand-typed prose in the renderer. These tests hold the replacement to its
contract: read provenance off the stored run, and where the run doesn't record something,
say so instead of substituting today's settings.
"""

from __future__ import annotations

from scripts.build_detailed_report import _provenance
from scripts.render_report_md import (
    judge_phrase,
    runs_phrase,
    sampling_lines,
    sentence_case,
)
from src.api.engine_registry import engine_class, sampling_for


def _meta(prov: dict[str, object], engines: list[str] | None = None) -> dict[str, object]:
    return {"engines": engines or ["openai", "anthropic"], "provenance": prov}


# --- The engine-side facts ------------------------------------------------------


def test_sampling_labels_match_the_engines_that_actually_pin_a_temperature() -> None:
    assert sampling_for("anthropic") == "pinned"
    # Rejects the parameter outright (gpt-5.6-luna) — the reason this work exists.
    assert sampling_for("openai") == "default"
    # SERP capture: no model, so no sampling to control.
    assert sampling_for("google_ai_mode") == "none"


def test_a_repinned_engine_reports_an_undeterminable_regime() -> None:
    # The run recorded a model this engine no longer pins, so the regime then cannot be
    # asserted from the adapter now — a repin can change it, which is exactly what the
    # 2026-07-28 openai repin did.
    assert sampling_for("openai", "gpt-4o-2024-08-06") is None
    # Matching pin -> the label is safe to apply.
    current = engine_class("openai")
    assert current is not None
    assert sampling_for("openai", current.MODEL_ID) == "default"


def test_unknown_engine_is_none_rather_than_a_guess() -> None:
    assert sampling_for("not_an_engine") is None


# --- What the run blob carries --------------------------------------------------


def test_provenance_reads_the_run_row() -> None:
    row: dict[str, object] = {
        "runs_per_query": 5,
        "engine_models": {"anthropic": "claude-sonnet-4-5-20250929"},
        "judge_model": "claude-sonnet-4-5-20250929",
    }
    prov = _provenance(row, ["anthropic", "openai"])
    assert prov["judge_model"] == "claude-sonnet-4-5-20250929"
    assert prov["runs_per_query"] == 5
    # An engine with no recorded model is None, not omitted — the report has to be able
    # to say "model not recorded" for it.
    assert prov["engine_models"] == {"anthropic": "claude-sonnet-4-5-20250929", "openai": None}


def test_provenance_of_a_run_that_recorded_nothing_is_all_none() -> None:
    prov = _provenance({}, ["openai"])
    assert prov["judge_model"] is None
    assert prov["runs_per_query"] is None
    assert prov["engine_models"] == {"openai": None}


# --- What the renderer says -----------------------------------------------------


def test_judge_phrase_names_the_recorded_model() -> None:
    phrase = judge_phrase(_meta({"judge_model": "claude-sonnet-4-5-20250929"}))
    assert "`claude-sonnet-4-5-20250929`" in phrase


def test_judge_phrase_admits_an_unrecorded_model_instead_of_naming_one() -> None:
    phrase = judge_phrase(_meta({"judge_model": None}))
    assert "not recorded" in phrase
    # The specific failure being prevented: never print a model the run didn't record.
    assert "gpt-4o" not in phrase and "sonnet" not in phrase.lower()


def test_sampling_lines_state_each_engines_regime_separately() -> None:
    lines = sampling_lines(
        _meta(
            {
                "engine_models": {"openai": "gpt-5.6-luna", "anthropic": "claude-sonnet-4-5"},
                "sampling": {"openai": "default", "anthropic": "pinned"},
            }
        )
    )
    joined = "\n".join(lines)
    assert "`openai`" in joined and "provider default" in joined
    assert "`anthropic`" in joined and "temperature pinned" in joined
    # No bare "pinned to 0": the value of ENGINE_TEMPERATURE is not stored on the run.
    assert "pinned to 0" not in joined


def test_sampling_line_for_a_repinned_engine_declines_to_assert() -> None:
    (line,) = sampling_lines(
        _meta(
            {"engine_models": {"openai": "gpt-4o-2024-08-06"}, "sampling": {"openai": None}},
            engines=["openai"],
        )
    )
    assert "not determinable" in line
    assert "`gpt-4o-2024-08-06`" in line  # the model it DID record is still reported


def test_runs_phrase_reads_the_run_and_admits_when_it_cannot() -> None:
    assert runs_phrase(_meta({"runs_per_query": 5})) == "5 runs per query."
    assert runs_phrase(_meta({"runs_per_query": 1})) == "1 run per query."
    assert "not recorded" in runs_phrase(_meta({}))


def test_sentence_case_does_not_mangle_identifiers() -> None:
    # str.capitalize() would lowercase the rest, turning JUDGE_MODEL into judge_model
    # and corrupting any model id that carries capitals.
    assert sentence_case("one judge (JUDGE_MODEL is configurable)").startswith("One judge")
    assert "JUDGE_MODEL" in sentence_case("one judge (JUDGE_MODEL is configurable)")
