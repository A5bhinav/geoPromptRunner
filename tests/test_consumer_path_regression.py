"""W0.4 — the consumer-path regression lock.

The SMB pivot (``docs/smb-pivot-build-plan.md``) ADDS the local-service ICP; it does
not replace the consumer-product one. Both ship. Phases 1-4 of that plan touch six
symbols the consumer path also reads, and the plan's §0.6 rule is that every one of
them is **forked by business kind, never edited in place**.

This file is the enforcement arm of that rule. It pins today's consumer behaviour so
an in-place edit fails loudly instead of silently degrading the consumer ICP — which
matters most for the symbols with no loud failure mode of their own (prompt wording,
platform lists, template contents).

**A failure here is the lock working.** The fix is to fork the symbol on
``business_kind`` and restore the consumer assertion unchanged — NEVER to relax the
assertion so local behaviour can pass through it.

The single exception is ``test_judge_prompt_fingerprint_is_pinned``: the W3.3 judge
bump legitimately changes that hash, and the pin is updated in that same commit.
Every other assertion in this file changing is a bug.
"""

from __future__ import annotations

from src.audit.offsite.tools import REVIEW_PLATFORMS
from src.engines.base import BaseEngine
from src.pipeline.discovery import _EXTRACT_PROMPT, discover_competitors
from src.pipeline.judge import _judgment_tool, _single_fingerprint
from src.pipeline.orchestrator import _TEASER_BUCKETS
from src.prompts.csv_loader import build_template_csv, parse_csv_files
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet
from src.storage.models import QueryResult

# --- W2.2 guard: build_template_csv() is user-facing ------------------------------
# Served as a download at GET /api/template.csv (src/api/app.py). The build plan
# originally said "replace the Oura starter template"; that would change what every
# consumer prospect downloads. W2.2 parameterises it instead — the no-argument call
# must stay byte-identical.


def test_consumer_template_csv_is_byte_identical() -> None:
    """The no-argument template is the Oura consumer starter, unchanged.

    A local/trade template is reachable only via an explicit argument (W2.2). If this
    fails because a trade template became the default, the fix is the default, not
    this test.
    """
    template = build_template_csv()

    # Pin the full config block: client, category, competitors, engines, runs, domains.
    assert "config,client_name,Oura" in template
    assert "config,category,smart ring" in template
    assert "config,competitors,Whoop;Ultrahuman;Samsung Galaxy Ring;RingConn" in template
    assert "config,engines,openai;anthropic;gemini" in template
    assert "config,runs_per_query,3" in template
    assert "config,client_domains,ouraring.com" in template

    # Consumer intents only — no local bucket may leak into the default template.
    assert "category" in template and "comparison" in template
    assert "brand" in template and "problem_aware" in template
    for local_bucket in ("local_intent", "hybrid", "informational"):
        assert local_bucket not in template, (
            f"local bucket {local_bucket!r} leaked into the default consumer template"
        )

    # And it still round-trips through the parser it is a template for.
    result = parse_csv_files([("template.csv", template)])
    assert result.ok, f"consumer template no longer parses: {result.errors}"


def test_consumer_template_csv_query_rows_unchanged() -> None:
    """The four starter queries are the consumer set, each with its consumer intent."""
    template = build_template_csv()
    assert "query,q1,best smart ring 2026,category" in template
    assert "comparison" in template and "Oura vs Whoop for sleep tracking" in template
    assert "query,q3,is the Oura Ring worth it,brand" in template
    assert "problem_aware" in template


# --- W2.1 guard: teaser bucket selection ------------------------------------------
# _TEASER_BUCKETS (orchestrator.py) is hardcoded to (CATEGORY, COMPARISON) and filters
# the query set. A local set built from local_intent/hybrid/informational intersects it
# in ZERO queries — the local teaser would silently produce an empty run. W2.1 forks it
# into a kind-keyed mapping; the consumer pair must survive that unchanged.


def test_consumer_teaser_buckets_unchanged() -> None:
    """The consumer teaser selects category + comparison — the 'here's who ChatGPT
    recommends instead of you' moment. Local buckets get their own mapping."""
    assert tuple(_TEASER_BUCKETS) == (IntentBucket.CATEGORY, IntentBucket.COMPARISON)


def test_consumer_teaser_selection_picks_the_same_queries() -> None:
    """Behavioural twin of the constant pin: given a mixed consumer set, the teaser
    filter selects exactly the category and comparison queries."""
    queries = [
        Query(query_id="q1", text="best smart ring 2026", intent=IntentBucket.CATEGORY),
        Query(query_id="q2", text="Oura vs Whoop", intent=IntentBucket.COMPARISON),
        Query(query_id="q3", text="is Oura worth it", intent=IntentBucket.BRAND),
        Query(query_id="q4", text="how do I sleep better", intent=IntentBucket.PROBLEM_AWARE),
        Query(query_id="q5", text="what is HRV", intent=IntentBucket.ADJACENT_AUTHORITY),
    ]
    selected = [q.query_id for q in queries if q.intent in _TEASER_BUCKETS]
    assert selected == ["q1", "q2"]


def test_consumer_query_sets_still_load_after_bucket_additions() -> None:
    """Adding local members to IntentBucket must not break consumer set construction.

    IntentBucket is a StrEnum and load_query_set validates against it, so additions are
    backward-compatible by construction — this pins that they stay so.
    """
    qs = QuerySet(
        version="v1",
        locked_at="2026-01-01",
        category="smart ring",
        client="Oura",
        competitors=["Whoop"],
        queries=[Query(query_id="q1", text="best smart ring", intent=IntentBucket.CATEGORY)],
    )
    assert qs.queries[0].intent is IntentBucket.CATEGORY
    for name in ("PROBLEM_AWARE", "CATEGORY", "COMPARISON", "BRAND", "ADJACENT_AUTHORITY"):
        assert hasattr(IntentBucket, name), f"consumer bucket {name} was removed"


# --- W2.7 guard: the discovery extraction prompt ----------------------------------
# _EXTRACT_PROMPT is one module-level constant consumed at discovery.py:62. The plan
# said "reprompt for local business names"; done in place that degrades consumer
# discovery SILENTLY — extraction quality has no loud failure mode. W2.7 forks it.


def test_consumer_extract_prompt_is_product_shaped() -> None:
    """The consumer extraction prompt still asks for products/tools/companies."""
    assert "software products, tools, or companies" in _EXTRACT_PROMPT
    assert "{response}" in _EXTRACT_PROMPT


class _EchoExtractor(BaseEngine):
    """Records the prompt it was handed and returns a fixed name list."""

    ENGINE_NAME = "echo"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def query(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return "Whoop\nUltrahuman\nOura"


def _result(response: str) -> QueryResult:
    return QueryResult(
        query_id="q1",
        query_text="best smart ring",
        intent="category",
        engine_name="openai",
        run_index=0,
        response=response,
        latency_ms=1,
        error=None,
    )


def test_consumer_discovery_uses_the_product_prompt_and_ranks_unknowns() -> None:
    """End-to-end on the consumer path: the product-shaped prompt is what reaches the
    extractor, and known brands are dropped from the ranking."""
    extractor = _EchoExtractor()
    found = discover_competitors(
        [_result("Oura and Whoop are the leaders.")],
        known=["Oura"],
        extractor=extractor,
    )

    assert len(extractor.prompts) == 1
    assert "software products, tools, or companies" in extractor.prompts[0]
    assert "Oura and Whoop are the leaders." in extractor.prompts[0]
    assert found == [("Whoop", 1), ("Ultrahuman", 1)]


# --- W4.1 guard: review platforms -------------------------------------------------
# The plan already says "keep both sets and select by business kind" for this one.
# Pinned anyway: it is the single most tempting symbol to overwrite, since the local
# list (Yelp/GBP/BBB/Angi) is longer and feels like a superset. It is not — the
# consumer ICP still needs exactly these three.


def test_consumer_review_platforms_unchanged() -> None:
    """Trustpilot + the two app stores. G2 and B2B review sites stay excluded, and no
    local directory may be appended to the consumer tuple."""
    assert REVIEW_PLATFORMS == ("trustpilot.com", "apps.apple.com", "play.google.com")

    local_only = ("yelp.com", "bbb.org", "angi.com", "thumbtack.com", "homeadvisor.com")
    for platform in local_only:
        assert platform not in REVIEW_PLATFORMS, (
            f"{platform} is a local-service directory; it belongs in a kind-keyed local "
            "tuple, not appended to the consumer one"
        )


# --- W3.3 guard: the judge prompt fingerprint -------------------------------------
# THE ONE ASSERTION IN THIS FILE THAT MAY LEGITIMATELY CHANGE — and only in the W3.3
# commit, which bumps _PROMPT_LAYOUT and invalidates every cached verdict on purpose.
# Anywhere else, a change here means a judge prompt was edited without the deliberate
# cache-invalidation ceremony, which silently turns prejudge into a $0-savings no-op.


def test_judge_prompt_fingerprint_is_pinned() -> None:
    """Re-pinned 2026-07-27 by W3.3 — the ONE sanctioned change to this constant.

    Was ``5e8caed0…b13b3d`` (907d447, pre-pivot). W3.1 appended four service-area flag
    types to the accuracy block and the tool-schema enum, and W3.3 bumped
    ``_PROMPT_LAYOUT`` alongside them, so every cached verdict became a miss on
    purpose. Re-warm with the prejudge skill (free) rather than re-judging on the API.

    If this fails and you are NOT in a deliberate, _PROMPT_LAYOUT-bumping commit: you
    edited a judge prompt, the tool schema, or the prompt layout by accident. Revert
    it — an unbumped prompt edit silently turns prejudge into a $0-savings no-op.
    """
    pinned = "c9e86fcad1f7d17d03cbda3b266e5ec1698bb5257d6f92b2c07c78d8a6701d10"
    assert _single_fingerprint(_judgment_tool()) == pinned, (
        "judge prompt fingerprint changed — every cached verdict just became a miss. "
        "Legitimate ONLY in the W3.3 commit (see docs/smb-pivot-build-plan.md §W3.3)."
    )


# --- W2.7 fork verification -------------------------------------------------------
# The consumer assertions above pin that _EXTRACT_PROMPT is unchanged. These confirm
# the local variant exists SEPARATELY rather than having replaced it.


def test_local_extraction_prompt_is_a_fork_not_a_rewrite() -> None:
    from src.pipeline.discovery import extract_prompt_for

    consumer = extract_prompt_for("product")
    local = extract_prompt_for("local_service")

    assert "software products, tools, or companies" in consumer
    assert "local businesses" in local
    assert consumer != local
    # Unknown kinds fall back to consumer — the pre-pivot default.
    assert extract_prompt_for("anything-else") == consumer
    assert extract_prompt_for() == consumer


# --- W3.1/W3.4: the accuracy block change was APPEND-ONLY --------------------------
# W3.4 gets to choose the CHEAP resolution (re-run the consumer gold sets and confirm
# agreement holds) only if W3.1 was surgical: no existing rule reworded, no existing
# flag type renamed. If someone later edits a consumer rule "while they're in there",
# the cheap path silently stops being valid and the 96/88/93 figures quietly stop
# describing the shipped judge. These pins make that edit loud.


def test_consumer_accuracy_flag_types_are_unchanged() -> None:
    """The original five keep their exact wire values — they are persisted in
    judgments rows and gold sets, so a rename would orphan historical data."""
    from src.storage.models import AccuracyFlagType

    for name, value in [
        ("WRONG_PRICING", "wrong_pricing"),
        ("MISSING_OR_INVENTED_FEATURE", "missing_or_invented_feature"),
        ("COMPETITOR_CONFUSION", "competitor_confusion"),
        ("IDENTITY", "identity"),
        ("STALE", "stale"),
    ]:
        assert getattr(AccuracyFlagType, name).value == value


def test_consumer_accuracy_rules_are_byte_identical() -> None:
    """Every consumer per-type rule, verbatim as it stood pre-pivot at 907d447."""
    from src.pipeline.judge import _ACCURACY_BLOCK

    consumer_rules = [
        "- wrong_pricing: only if the answer states a specific price/subscription figure",
        "- stale: you MUST flag it when the answer names an old model/version/date a",
        "- missing_or_invented_feature: only if a sheet feature line or its \"is NOT /",
        "- identity: only if the answer states who/what the brand is in a way a sheet",
        "- competitor_confusion: only if the answer attributes a named rival's",
    ]
    for rule in consumer_rules:
        assert rule in _ACCURACY_BLOCK, f"consumer rule reworded: {rule!r}"

    # The delete gate and the hard verbatim gate are the two guards that keep the
    # judge from over-flagging. Neither may be softened to accommodate local flags.
    assert "STOP — RUN THIS DELETE GATE ON EVERY FLAG BEFORE YOU OUTPUT." in _ACCURACY_BLOCK
    assert "HARD GATE: \"reality\" MUST be a span copied VERBATIM" in _ACCURACY_BLOCK
    assert "OMISSION: an omission is NEVER a flag." in _ACCURACY_BLOCK


def test_local_flags_are_structurally_inert_on_a_product_sheet() -> None:
    """The local flags need no gating to stay off the consumer path.

    Every flag requires a VERBATIM contradicting line from the fact sheet, and the
    appended rules each name the sheet line they need (an hours line, a service-area
    line, a contact line, a licence line). A consumer product's sheet has none of
    those, so a local flag has nothing valid to cite. This pins the wording that
    makes that true — if a future edit drops the "only if ... line contradicts"
    construction, the flag could start firing on product answers.
    """
    from src.pipeline.judge import _ACCURACY_BLOCK

    for rule, required_line in [
        ("- wrong_hours:", "an hours or availability line contradicts"),
        ("- wrong_service_area:", "that a service-area line\n  contradicts"),
        ("- wrong_contact:", "a sheet contact line contradicts"),
        ("- licensing:", "certification status that a sheet line contradicts"),
    ]:
        assert rule in _ACCURACY_BLOCK, f"missing local rule {rule!r}"
        assert required_line in _ACCURACY_BLOCK, (
            f"{rule} no longer requires a contradicting sheet line — it could now fire "
            f"on a consumer product answer"
        )

    # And they are introduced as explicitly conditional on the sheet having such lines.
    assert "if the sheet has no such line" in _ACCURACY_BLOCK


def test_local_platforms_were_forked_not_appended_to_the_consumer_tuple() -> None:
    """W4.1's fork verified from the consumer side.

    The plan already said "keep both sets and select by kind" for this one, but it is
    the most tempting symbol to overwrite — the local list is longer and feels like a
    superset. It is not: a phone app has no BBB page.
    """
    from src.audit.offsite.tools import LOCAL_REVIEW_PLATFORMS, review_platforms_for

    assert review_platforms_for("product") == REVIEW_PLATFORMS
    assert REVIEW_PLATFORMS == ("trustpilot.com", "apps.apple.com", "play.google.com")
    assert not set(REVIEW_PLATFORMS) & set(LOCAL_REVIEW_PLATFORMS)


def test_consumer_schema_expectations_unchanged() -> None:
    """W4.3 forks the per-page-category expected schema types. A consumer homepage
    still wants Organization, not LocalBusiness."""
    from src.audit.checks.schema import category_expectations

    consumer = category_expectations("product")
    assert consumer["homepage"] == {"Organization"}
    assert consumer["pricing"] == {"Product", "Offer"}
    assert category_expectations() == consumer
    assert category_expectations("unknown-kind") == consumer

    local = category_expectations("local_service")
    assert local["homepage"] == {"LocalBusiness"}
    assert local != consumer
