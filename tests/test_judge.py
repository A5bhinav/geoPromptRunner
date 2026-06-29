from __future__ import annotations

from src.pipeline.judge import (
    _ACCURACY_BLOCK,
    _ACCURACY_ONLY_INSTRUCTIONS,
    _STRUCTURAL_INSTRUCTIONS,
    _VERIFIER_INSTRUCTIONS,
    AccuracyFlagType,
    Framing,
    Prominence,
    Severity,
    _accuracy_tool,
    _brand_lines,
    _cascade_identity,
    _judgment_tool,
    _parse_brands,
    _parse_flags,
    _single_fingerprint,
    _structural_tool,
    _verdict_keep,
    _verifier_tool,
)


def test_parse_brands_fills_missing_and_coerces() -> None:
    raw = {
        "brands": [
            {
                "brand": "YNAB",
                "present": True,
                "prominence": "recommended_first",
                "framing": "positive",
            },
            {"brand": "Centsible", "present": True, "prominence": "buried", "framing": "bogus"},
        ]
    }
    brands = _parse_brands(raw, client="Centsible", competitors=["YNAB", "Rocket Money"])
    by = {b.brand: b for b in brands}

    # Client + every competitor is always present in the output (order: client first).
    assert [b.brand for b in brands] == ["Centsible", "YNAB", "Rocket Money"]
    assert by["YNAB"].prominence == Prominence.RECOMMENDED_FIRST.value
    # Unknown framing coerces to neutral.
    assert by["Centsible"].framing == Framing.NEUTRAL.value
    # Brand the judge omitted -> filled as absent / not present / neutral.
    assert by["Rocket Money"].present is False
    assert by["Rocket Money"].prominence == Prominence.ABSENT.value


def test_present_false_forces_absent_prominence() -> None:
    raw = {
        "brands": [{"brand": "X", "present": False, "prominence": "mid_pack", "framing": "neutral"}]
    }
    brands = _parse_brands(raw, client="X", competitors=[])
    assert brands[0].prominence == Prominence.ABSENT.value


def test_parse_flags_filters_invalid() -> None:
    raw = {
        "client_accuracy_flags": [
            {
                "type": "wrong_pricing",
                "claim": "$20/mo",
                "reality": "free + $5/mo",
                "severity": "high",
            },
            {"type": "not_a_real_type", "claim": "x", "reality": "y", "severity": "low"},  # dropped
            {
                "type": "stale",
                "claim": "",
                "reality": "",
                "severity": "low",
            },  # nothing checkable -> dropped
            {
                "type": "identity",
                "claim": "owned by Intuit",
                "reality": "independent",
            },  # severity defaults
        ]
    }
    flags = _parse_flags(raw)
    assert len(flags) == 2
    assert flags[0].type == AccuracyFlagType.WRONG_PRICING.value
    assert flags[1].type == AccuracyFlagType.IDENTITY.value
    assert flags[1].severity == Severity.MED.value  # default when omitted


def test_parse_flags_handles_missing_key() -> None:
    assert _parse_flags({}) == []


# --- cascade (two-tier judge) ---


def test_cascade_tools_split_responsibilities() -> None:
    """Structural tool emits brands only; accuracy tool emits client flags only."""
    s = _structural_tool()
    a = _accuracy_tool()
    assert s["name"] == "record_brands"
    assert a["name"] == "record_flags"
    assert list(s["input_schema"]["properties"]) == ["brands"]
    assert s["input_schema"]["required"] == ["brands"]
    assert list(a["input_schema"]["properties"]) == ["client_accuracy_flags"]
    assert a["input_schema"]["required"] == ["client_accuracy_flags"]
    # Enums are sourced from the data-layer types, so the structural brand schema
    # offers exactly the Prominence/Framing values the parser accepts.
    brand_props = s["input_schema"]["properties"]["brands"]["items"]["properties"]
    assert set(brand_props["prominence"]["enum"]) == {p.value for p in Prominence}
    assert set(brand_props["framing"]["enum"]) == {f.value for f in Framing}


def test_cascade_prompts_isolate_fact_sheet() -> None:
    """The structural prompt never sees the fact sheet; the accuracy prompt does."""
    structural = _STRUCTURAL_INSTRUCTIONS.format(
        query="best ring", answer="Oura is great.", brand_lines=_brand_lines("Oura", ["Ultrahuman"])
    )
    assert "SECRET-SHEET-LINE" not in structural
    assert "Oura [CLIENT]" in structural and "Ultrahuman" in structural
    accuracy = _ACCURACY_ONLY_INSTRUCTIONS.format(
        query="best ring",
        answer="Oura is $999.",
        client="Oura",
        accuracy_block="Price: $399. SECRET-SHEET-LINE",
    )
    assert "SECRET-SHEET-LINE" in accuracy


def test_brand_lines_marks_client() -> None:
    lines = _brand_lines("Oura", ["Ultrahuman", "Samsung"])
    assert lines.splitlines() == ["- Oura [CLIENT]", "- Ultrahuman", "- Samsung"]


def test_cascade_cache_identity_is_distinct_and_stable() -> None:
    """Cascade verdicts get a composite, non-colliding cache identity; the same
    model pair is stable, a different pair differs."""
    model_id, fp = _cascade_identity("claude-haiku-4-5", "claude-sonnet-4-5-20250929")
    model_id2, fp2 = _cascade_identity("claude-haiku-4-5", "claude-sonnet-4-5-20250929")
    assert model_id == model_id2 and fp == fp2  # deterministic
    assert model_id == "cascade:claude-haiku-4-5+claude-sonnet-4-5-20250929"
    # Distinct from any single-model judge identity (different keyspace).
    assert not model_id.startswith("claude-")
    assert fp != _single_fingerprint(_judgment_tool())
    # Swapping a model changes both id and fingerprint (forces a re-judge).
    other_id, other_fp = _cascade_identity("claude-haiku-4-5", "claude-opus-4-8")
    assert other_id != model_id and other_fp != fp


# --- adversarial flag verifier (queue #9 precision fix) ---


def test_verifier_tool_shape() -> None:
    t = _verifier_tool()
    assert t["name"] == "record_verdict"
    assert set(t["input_schema"]["properties"]) == {"keep", "reason"}
    assert t["input_schema"]["required"] == ["keep", "reason"]
    assert t["input_schema"]["properties"]["keep"]["type"] == "boolean"


def test_verdict_keep_is_recall_safe() -> None:
    # A real keep / drop is honored...
    assert _verdict_keep({"keep": True, "reason": "real contradiction"}) is True
    assert _verdict_keep({"keep": False, "reason": "confirmation"}) is False
    # ...but a failed call (None) or a malformed verdict (missing key) KEEPS the
    # flag — the verifier never silently drops a real error (protects recall).
    assert _verdict_keep(None) is True
    assert _verdict_keep({"reason": "no keep field"}) is True


def test_verifier_prompt_carries_the_one_flag_and_sheet() -> None:
    prompt = _VERIFIER_INSTRUCTIONS.format(
        client="Oura",
        answer="Oura costs $399.",
        fact_sheet="Oura Ring 5: $399",
        type="wrong_pricing",
        claim="Oura costs $399",
        reality="Oura Ring 5: $399",
    )
    assert "wrong_pricing" in prompt and "Oura costs $399" in prompt
    assert "Oura Ring 5: $399" in prompt
    # The verifier prompt is independent of the main accuracy block.
    assert _ACCURACY_BLOCK not in prompt
