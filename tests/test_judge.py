from __future__ import annotations

from src.pipeline.judge import (
    _ACCURACY_BLOCK,
    _ACCURACY_ONLY_INSTRUCTIONS,
    _ANSWER_HEAD,
    _BASE_INSTRUCTIONS,
    _RUBRIC_TAIL,
    _STRUCTURAL_INSTRUCTIONS,
    _SYSTEM,
    _VERIFIER_INSTRUCTIONS,
    AccuracyFlagType,
    Framing,
    Judge,
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


# --- prejudge parity: the invariants the subscription pre-judge path rests on ---
# The prejudge Workflow (scripts/judge_via_workflow.py + prejudge_workflow.js) judges
# stored answers on the subscription and writes them into the SAME judge cache the live
# API judge reads. That only works if (a) the per-answer HEAD / shared RUBRIC split it
# uses reassembles the real judge prompt exactly, and (b) the cache key it computes is
# byte-identical to the one a live Judge() looks up. These tests pin both so a future
# edit to judge.py can't silently turn prejudge into a $0-savings no-op.


def test_answer_head_rubric_split_reassembles_base_instructions() -> None:
    """dump renders the prompt as HEAD (question+answer) + shared RUBRIC. Both halves
    must reassemble _BASE_INSTRUCTIONS exactly, and each must own only its own
    placeholders — else the batch prompt drifts from the single-judge prompt."""
    assert _ANSWER_HEAD + _RUBRIC_TAIL == _BASE_INSTRUCTIONS
    assert "{query}" in _ANSWER_HEAD and "{answer}" in _ANSWER_HEAD
    assert "{brand_lines}" in _RUBRIC_TAIL and "{accuracy_instructions}" in _RUBRIC_TAIL
    # No cross-contamination of placeholders between the two halves.
    assert "{brand_lines}" not in _ANSWER_HEAD and "{query}" not in _RUBRIC_TAIL


def test_dump_cache_key_matches_live_judge_lookup(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The key scripts/judge_via_workflow.py `dump` computes (from judge._cache_model_id
    + judge._prompt_fingerprint) must be the exact key a live Judge() looks up — so a
    prejudged verdict is a cache HIT and the judge never calls the API. Seed a sentinel
    under the dump-computed key and assert judge_answer_cached returns it WITHOUT ever
    calling judge_answer (a miss would mean the keys drifted)."""
    from src.config import settings
    from src.pipeline.judge_cache import JudgeCache

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key-never-called")
    judge = Judge()
    cache = JudgeCache(str(tmp_path / "parity.sqlite"))
    try:
        client, competitors, fact_sheet = "Fort", ["Acme", "Globex"], "Membership: $5.99/month"
        query, answer = "best budgeting app?", "I recommend Fort."

        # The key EXACTLY as scripts/judge_via_workflow.py _dump computes it.
        dump_key = cache.key(
            model=judge._cache_model_id,
            prompt_fingerprint=judge._prompt_fingerprint,
            client=client,
            competitors=competitors,
            fact_sheet=fact_sheet,
            prompt=query,
            answer=answer,
        )
        sentinel: tuple[list, list, bool] = ([], [], True)
        cache.put_many([(dump_key, sentinel)])

        # If the live lookup key ever diverges from dump_key, this would be a miss and
        # fall through to judge_answer — which must NOT happen.
        def _boom(*_a: object, **_k: object) -> object:
            raise AssertionError("cache MISS: dump key != live judge lookup key (parity broken)")

        monkeypatch.setattr(judge, "judge_answer", _boom)
        got = judge.judge_answer_cached(query, answer, client, competitors, fact_sheet, cache)
        assert got == sentinel
    finally:
        cache.close()


def test_single_judge_caches_shared_rubric_prefix(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The single judge sends the shared rubric as ONE cached system block placed before
    the per-answer head, so the API prompt-caches it across a run. Guards that wiring:
    the rubric + fact sheet are in the cached prefix, and the variable answer is only in
    the (uncached) user message."""
    from src.config import settings

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key-never-called")
    judge = Judge()
    system, user = judge._single_judge_messages(
        "which app?", "An answer naming Fortbudget.", "Fort", ["Acme"], "Membership: $5.99/month"
    )
    assert len(system) == 1
    block = system[0]
    assert block["cache_control"] == {"type": "ephemeral"}  # the shared prefix is cached
    assert block["text"].startswith(_SYSTEM)  # system preamble leads the cached block
    assert "Brands to score" in block["text"] and "$5.99" in block["text"]  # rubric + sheet cached
    # The per-answer head (the variable part) is the uncached user message, not the prefix.
    assert "An answer naming Fortbudget." in user
    assert "An answer naming Fortbudget." not in block["text"]
    assert "which app?" in user


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
