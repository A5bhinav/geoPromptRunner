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
    """Pinned at 907d447, pre-pivot.

    If this fails and you are NOT in the W3.3 commit: you edited a judge prompt, the
    tool schema, or the prompt layout by accident. Revert it.

    If this fails and you ARE in W3.3: update the constant below in that same commit,
    bump _PROMPT_LAYOUT alongside it, and re-warm caches with the prejudge skill.
    """
    pinned = "5e8caed0a4ee2a8c5eec8290248de0dc78f55beb91c6a2997ddaada0a7b13b3d"
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
