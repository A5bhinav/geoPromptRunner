"""The local report's six hard rules, enforced.

``docs/report-template-local.md`` calls these "not style preferences" — each exists
because breaking it produces a claim we cannot back in front of a shop owner. A comment
in the renderer is not enforcement; these are.
"""

from __future__ import annotations

import pytest

from src.api.reports import LocalPackPayload, build_local_pack_payload
from src.audit.local_report import render_local_report
from src.engines.local_pack import LocalEntity, LocalPackCapture
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import (
    AccuracyFlag,
    AccuracyFlagType,
    AnswerJudgment,
    BrandJudgment,
    QueryResult,
    Severity,
)

CLIENT = "Albert Nahman Plumbing"
MARKET = "Berkeley,California,United States"
RIVAL = "LemonTree Plumbing"


def _result(query_id: str, engine: str, run: int, response: str | None) -> QueryResult:
    return QueryResult(
        query_id=query_id,
        intent="local_intent",
        prompt="best plumber in Berkeley",
        engine_name=engine,
        run_index=run,
        response=response,
        citations=[],
        timestamp="t",
    )


def _judgment(
    query_id: str,
    engine: str,
    run: int,
    *,
    rival: str = RIVAL,
    prominence: str = "recommended_first",
    client_present: bool = False,
    flags: list[AccuracyFlag] | None = None,
) -> AnswerJudgment:
    return AnswerJudgment(
        query_id=query_id,
        engine_name=engine,
        intent="local_intent",
        run_index=run,
        assessed=True,
        brands=[
            BrandJudgment(
                brand=CLIENT, present=client_present, prominence="absent", framing="neutral"
            ),
            BrandJudgment(brand=rival, present=True, prominence=prominence, framing="positive"),
        ],
        accuracy_flags=flags or [],
    )


def _outcome(results: list[QueryResult]) -> AuditOutcome:
    return AuditOutcome(
        run_id="r1",
        client_name=CLIENT,
        client_domains=["albertnahmanplumbing.com"],
        competitors=[RIVAL],
        query_set_version="local-plumbing-v1",
        runs_per_query=3,
        results=results,
    )


def _pack(names: list[str], client_rank: int | None = None) -> LocalPackPayload:
    capture = LocalPackCapture(
        query_id="loc-01",
        prompt="best plumber in Berkeley",
        source="serper_places",
        entities=[
            LocalEntity(
                name=n,
                address="",
                category="Plumber",
                rating=None,
                reviews=None,
                ludocid=None,
                position=i + 1,
                phone=None,
                website=None,
            )
            for i, n in enumerate(names)
        ],
    )
    payload = build_local_pack_payload([capture], CLIENT, MARKET)
    assert payload is not None
    return payload


# --- Rule 6: print the location, always ------------------------------------------


def test_refuses_to_render_without_a_location() -> None:
    """A report built from an unpinned locale describes the wrong market. Refusing is
    the point — printing it and hoping someone notices is the failure."""
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="location"):
            render_local_report(_outcome([]), trade="plumbing", location=bad)


def test_the_location_appears_in_the_measurement_section() -> None:
    out = render_local_report(
        _outcome([]), trade="plumbing", location=MARKET, run_date="2026-07-28"
    )
    assert MARKET in out
    assert "## 6 · How this was measured" in out


# --- Rule 1: never print an aggregate appearance ratio ----------------------------


def test_no_aggregate_appearance_ratio_anywhere() -> None:
    """'Appears in 4 of 11 queries' reads as a visibility rate and is not one — the
    denominator is a query set we chose."""
    results = [
        _result("loc-01", "google_ai_mode", i, f"{RIVAL} is the top pick.") for i in range(3)
    ]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL]),
        judgments=[_judgment("loc-01", "google_ai_mode", i) for i in range(3)],
        run_date="2026-07-28",
    )
    # No percentages, and no "N of M" framing over the query set.
    assert "%" not in out
    assert " of 3 queries" not in out
    assert "mention rate" not in out.lower()


# --- Rule 2: never claim more than the judge measured -----------------------------


@pytest.mark.parametrize(
    ("prominence", "expected_verb", "forbidden"),
    [
        ("recommended_first", "recommends", None),
        ("mid_pack", "features", "recommends"),
        ("buried", "mentions", "recommends"),
        ("also_ran", "mentions", "recommends"),
    ],
)
def test_the_verb_grades_off_judged_prominence(
    prominence: str, expected_verb: str, forbidden: str | None
) -> None:
    """"recommends" is reserved for recommended_first. A weaker prominence must grade
    down — the report cannot upgrade what the judge saw."""
    results = [_result("loc-01", "google_ai_mode", 0, f"{RIVAL} is an option.")]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL]),
        judgments=[_judgment("loc-01", "google_ai_mode", 0, prominence=prominence)],
        run_date="2026-07-28",
    )
    assert expected_verb in out
    if forbidden:
        assert forbidden not in out


# --- Rule 3: never name an uncaptured competitor ----------------------------------


def test_a_rival_the_local_pack_never_captured_is_not_named() -> None:
    """The unrecoverable failure for this product is a fabricated competitor printed in
    a report handed to a real shop owner. The local pack is the only allowlist."""
    results = [_result("loc-01", "google_ai_mode", 0, "Ghost Plumbing Co is the best.")]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        # The pack captured a DIFFERENT business; the judged rival is not in it.
        local_pack=_pack(["Someone Else Plumbing"]),
        judgments=[_judgment("loc-01", "google_ai_mode", 0, rival="Ghost Plumbing Co")],
        run_date="2026-07-28",
    )
    assert "Ghost Plumbing Co" not in out


def test_no_captured_entities_means_no_competitor_section_at_all() -> None:
    results = [_result("loc-01", "google_ai_mode", 0, f"{RIVAL} is the best.")]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=None,
        judgments=[_judgment("loc-01", "google_ai_mode", 0)],
        run_date="2026-07-28",
    )
    assert RIVAL not in out
    assert "no competitor can be named" in out.lower()


def test_a_longer_google_listing_still_matches_the_judged_rival() -> None:
    """The gate must not be so strict it drops a real rival: Google's listing is
    routinely longer than the name an engine says."""
    results = [_result("loc-01", "google_ai_mode", 0, f"{RIVAL} is the best.")]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack(["LemonTree Plumbing, Heating & Drain"]),
        judgments=[_judgment("loc-01", "google_ai_mode", 0, rival=RIVAL)],
        run_date="2026-07-28",
    )
    assert RIVAL in out


# --- Rule 4: no accuracy FIGURE until W3.4 ----------------------------------------


def test_flags_render_with_evidence_but_no_accuracy_figure() -> None:
    """The flags are the point of §4 — each carries its own verbatim evidence. What is
    frozen is the accuracy RATE, until W3.4 calibration passes."""
    flag = AccuracyFlag(
        type=AccuracyFlagType.WRONG_CONTACT,
        severity=Severity.HIGH,
        claim="Call (510) 000-0000",
        reality="The real number is (510) 408-7879",
    )
    results = [_result("loc-01", "google_ai_mode", 0, "Call (510) 000-0000.")]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL]),
        judgments=[_judgment("loc-01", "google_ai_mode", 0, flags=[flag])],
        run_date="2026-07-28",
    )
    # The finding and its evidence appear...
    assert "(510) 000-0000" in out
    assert "(510) 408-7879" in out
    # ...but no accuracy/agreement figure, and the reader is told it's uncalibrated.
    assert "%" not in out
    assert "not been re-calibrated" in out


# --- Rule 5: no reproducibility claim without the runs to back it -----------------


def test_reproducibility_is_claimed_only_when_every_run_confirms() -> None:
    results = [_result("loc-01", "google_ai_mode", i, f"{RIVAL} is best.") for i in range(3)]
    judgments = [_judgment("loc-01", "google_ai_mode", i) for i in range(3)]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL]),
        judgments=judgments,
        run_date="2026-07-28",
    )
    assert "Asked 3 separate times" in out

    # One run where the rival is absent breaks the claim entirely.
    judgments[2] = AnswerJudgment(
        query_id="loc-01",
        engine_name="google_ai_mode",
        intent="local_intent",
        run_index=2,
        assessed=True,
        brands=[BrandJudgment(brand=CLIENT, present=False, prominence="absent", framing="neutral")],
        accuracy_flags=[],
    )
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL]),
        judgments=judgments,
        run_date="2026-07-28",
    )
    assert "Asked 3 separate times" not in out
    assert "Not enough repeat observations" in out


def test_the_sampling_note_says_the_band_is_unmeasured() -> None:
    """SAMPLING_BANDS ships empty on purpose, so every local report must say its
    runs-per-query is a global default rather than a measured figure."""
    out = render_local_report(_outcome([]), trade="plumbing", location=MARKET)
    assert "not established" in out


# --- The client's own rank, the most actionable local number ----------------------


def test_the_client_rank_in_its_own_city_pack_is_printed() -> None:
    out = render_local_report(
        _outcome([]),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL, CLIENT]),  # client is #2
        run_date="2026-07-28",
    )
    assert "ranks **#2**" in out


def test_an_absent_client_is_stated_not_omitted() -> None:
    out = render_local_report(
        _outcome([]),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL, "Another Plumber"]),
        run_date="2026-07-28",
    )
    assert "not in the pack" in out


def test_an_unjudged_run_does_not_invent_a_lead() -> None:
    """§1 quotes a verbatim answer with a graded verb. Without the judge there is no
    prominence to grade against, so the section must say so rather than pattern-match."""
    results = [_result("loc-01", "google_ai_mode", 0, f"{RIVAL} is the best.")]
    out = render_local_report(
        _outcome(results),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL]),
        judgments=None,
        run_date="2026-07-28",
    )
    assert "has not been judged" in out
    assert "recommends" not in out


# --- CLI selection: a stored location is what makes a run local -------------------


def test_the_trade_is_inferred_from_either_entry_point() -> None:
    """Two entry points stamp the trade differently, and both must resolve.

    A run built from a trade template carries it in the query-set version
    ("local-plumbing-v1"); a run from an uploaded CSV carries only the category
    ("plumbing service"). Missing both used to render "looking for a local in
    Berkeley" — a non-word in front of a client.
    """
    import argparse

    from src.cli import _local_report_args

    class _Row(dict):  # type: ignore[type-arg]
        pass

    for row, expected in (
        (
            {"location": MARKET, "query_set_version": "local-plumbing-v1", "category": ""},
            "plumbing",
        ),
        (
            {"location": MARKET, "query_set_version": "csv-1", "category": "plumbing service"},
            "plumbing",
        ),
        # No template yet for this trade: fall back to the category, never "local".
        (
            {"location": MARKET, "query_set_version": "csv-1", "category": "roofing contractor"},
            "roofing contractor",
        ),
    ):
        import src.cli as cli

        original = cli.db.get_audit_run
        cli.db.get_audit_run = lambda _rid, _row=row: _Row(_row)  # type: ignore[assignment]
        try:
            args = argparse.Namespace(run_id="r1", trade=None)
            result = _local_report_args(args)
        finally:
            cli.db.get_audit_run = original  # type: ignore[assignment]
        assert result is not None
        assert result == (expected, MARKET)


def test_a_run_without_a_location_is_not_a_local_report() -> None:
    """The consumer path must be untouched: no stored location, no local rendering."""
    import argparse

    import src.cli as cli
    from src.cli import _local_report_args

    original = cli.db.get_audit_run
    cli.db.get_audit_run = lambda _rid: {"location": None, "category": "smart ring"}  # type: ignore[assignment]
    try:
        assert _local_report_args(argparse.Namespace(run_id="r1", trade=None)) is None
    finally:
        cli.db.get_audit_run = original  # type: ignore[assignment]


def test_the_directory_checklist_reads_real_offsite_status() -> None:
    """The §3 checklist must reflect what the offsite agent actually found.

    It couldn't: `SiteFindingRow` was flattened to finding_type/title/url/confidence,
    dropping the per-platform breakdown, while this renderer read `platform`/`present`
    keys that never existed. §3 therefore reported "not checked" even after a full Cat 6
    run. The row now carries `platforms`, and this pins the three states apart —
    "not found" and "not checked" are different claims and only one of them is safe to
    make when nobody looked.
    """
    from src.api.reports import SiteAuditPayload, SiteFindingRow

    site_audit: SiteAuditPayload = {
        "present": True,
        "domain": "albertnahmanplumbing.com",
        "pages_crawled": 2,
        "checks": [],
        "summary": {},
        "errors": 0,
        "offsite": [
            SiteFindingRow(
                finding_type="reviews",
                title="Review presence on 2/8 platforms",
                url=None,
                confidence="medium",
                platforms={"yelp.com": True, "google.com/maps": True, "bbb.org": False},
            )
        ],
        "roadmap": [],
    }
    out = render_local_report(
        _outcome([]), trade="plumbing", location=MARKET, site_audit=site_audit,
        run_date="2026-07-28",
    )
    assert "**Google Business Profile — 🟢 listed**" in out
    assert "| yelp.com | 🟢 listed |" in out
    assert "| bbb.org | 🔴 not found |" in out
    # A platform the agent never probed stays "not checked" — never "not found".
    assert "| nextdoor.com | ⚪ not checked |" in out


def test_local_pack_presence_overrides_a_false_gbp_probe() -> None:
    """GBP is weighted 3.0, and its probe produces false negatives.

    The check is `site:google.com/maps "<brand>"`, a deterministic stand-in for the
    Places API — and on a real run it reported "not found" for a business our own
    capture shows ranking #1 in that city's pack with a Google business id. The pack is
    generated FROM the GBP entity, so presence in it is strictly stronger evidence.

    A false "you have no Google Business Profile" is the most alarming line in §3 and one
    an owner can disprove in five seconds, which would discredit the whole report.
    """
    from src.api.reports import SiteAuditPayload, SiteFindingRow

    site_audit: SiteAuditPayload = {
        "present": True,
        "domain": "albertnahmanplumbing.com",
        "pages_crawled": 1,
        "checks": [],
        "summary": {},
        "errors": 0,
        "offsite": [
            SiteFindingRow(
                finding_type="reviews",
                title="Review presence on 7/8 platforms",
                url=None,
                confidence="medium",
                # The probe says the client has no Google Business Profile.
                platforms={"google.com/maps": False, "yelp.com": True},
            )
        ],
        "roadmap": [],
    }
    # ...but the capture ranks the client #1 in that city's pack.
    out = render_local_report(
        _outcome([]),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([CLIENT, RIVAL]),
        site_audit=site_audit,
        run_date="2026-07-28",
    )
    assert "**Google Business Profile — 🟢 listed**" in out

    # And when the client is genuinely absent from the pack, the probe stands.
    out_absent = render_local_report(
        _outcome([]),
        trade="plumbing",
        location=MARKET,
        local_pack=_pack([RIVAL, "Another Plumber"]),
        site_audit=site_audit,
        run_date="2026-07-28",
    )
    assert "**Google Business Profile — 🔴 not found**" in out_absent


def test_the_roadmap_renders_from_the_real_row_fields() -> None:
    """RoadmapRow has category/check_name/status/impact_label/effort/phase — no prose
    "title" or "why". Reading those absent keys rendered every item as "**** —" on a
    real run, i.e. a numbered list of nothing where §5 tells the owner what to do."""
    from src.api.reports import RoadmapRow, SiteAuditPayload

    site_audit: SiteAuditPayload = {
        "present": True,
        "domain": "albertnahmanplumbing.com",
        "pages_crawled": 1,
        "checks": [],
        "summary": {},
        "errors": 0,
        "offsite": [],
        "roadmap": [
            RoadmapRow(
                category="technical_accessibility",
                check_name="AI crawler UAs not blocked at the CDN/WAF",
                status="fail",
                impact_label="High",
                effort="low",
                phase=1,
            ),
            RoadmapRow(
                category="structured_data",
                check_name="schema.org markup valid",
                status="partial",
                impact_label="Medium",
                effort="low",
                phase=2,
            ),
        ],
    }
    out = render_local_report(
        _outcome([]), trade="plumbing", location=MARKET, site_audit=site_audit,
        run_date="2026-07-28",
    )
    assert "AI crawler UAs not blocked at the CDN/WAF (missing)" in out
    assert "schema.org markup valid (partial)" in out
    assert "High impact" in out
    # The synthesizer already sequences by phase; the report must not re-sort.
    assert out.index("AI crawler UAs") < out.index("schema.org markup")
    assert "****" not in out


def test_judged_roadmap_items_are_marked_uncalibrated() -> None:
    """A shop owner must be able to tell a measurement from a model's opinion.

    Deterministic checks (robots, schema, sitemap) are measured. The Cat 3/4 content
    checks are an LLM reading the page, and that judge has never passed the κ≥0.6 gate —
    no gold set is labelled. Both land in the same §5 table, so the judged ones carry a
    marker and a footnote. Unmarked rows must stay unmarked.
    """
    from src.api.reports import RoadmapRow, SiteAuditPayload

    site_audit: SiteAuditPayload = {
        "present": True,
        "domain": "x.com",
        "pages_crawled": 15,
        "checks": [],
        "summary": {},
        "errors": 0,
        "offsite": [],
        "roadmap": [
            RoadmapRow(
                category="technical_accessibility",
                check_name="AI crawler UAs not blocked at the CDN/WAF",
                status="fail",
                impact_label="High",
                effort="low",
                phase=1,
            ),
            RoadmapRow(
                category="content_structure",
                check_name="definition first",
                status="fail",
                impact_label="Medium",
                effort="medium",
                phase=2,
            ),
        ],
    }
    out = render_local_report(
        _outcome([]), trade="plumbing", location=MARKET, site_audit=site_audit,
        run_date="2026-07-28",
    )
    assert "definition first † (missing)" in out
    assert "AI crawler UAs not blocked at the CDN/WAF (missing)" in out
    assert "AI crawler UAs not blocked at the CDN/WAF † " not in out
    assert "has not yet been calibrated" in out


def test_no_footnote_when_no_judged_item_is_in_the_roadmap() -> None:
    """The caveat must not appear on a report that has nothing to caveat."""
    from src.api.reports import RoadmapRow, SiteAuditPayload

    site_audit: SiteAuditPayload = {
        "present": True, "domain": "x.com", "pages_crawled": 2, "checks": [],
        "summary": {}, "errors": 0, "offsite": [],
        "roadmap": [
            RoadmapRow(
                category="technical_accessibility", check_name="XML sitemap present",
                status="partial", impact_label="Medium", effort="low", phase=1,
            )
        ],
    }
    out = render_local_report(
        _outcome([]), trade="plumbing", location=MARKET, site_audit=site_audit,
        run_date="2026-07-28",
    )
    assert "†" not in out
    assert "has not yet been calibrated" not in out


def test_judged_check_names_cannot_drift_from_the_judge() -> None:
    """`_JUDGED_CHECK_NAMES` is hardcoded to keep this module free of the judge's
    Anthropic import. This is what stops the two silently diverging: add a content check
    and forget the marker, and an uncalibrated line would render as a measured one."""
    from src.audit.checks.content_judge import CONTENT_CHECKS
    from src.audit.local_report import _JUDGED_CHECK_NAMES

    derived = {c.check_id.replace("_", " ") for c in CONTENT_CHECKS}
    assert _JUDGED_CHECK_NAMES == derived


def test_the_roadmap_collapses_per_page_rows_into_one_fix_each() -> None:
    """The roadmap is built per page, which was invisible at 2 pages and unusable at 20.

    A real audit produced 75 items with "original data" repeating 12 times. Nobody can
    act on that. Grouping keeps the synthesizer's ordering and turns the repetition into
    the useful part: how much of the site is affected.
    """
    from src.api.reports import RoadmapRow, SiteAuditPayload

    def row(name: str, status: str) -> RoadmapRow:
        return RoadmapRow(
            category="content_substance", check_name=name, status=status,
            impact_label="Low", effort="high", phase=2,
        )

    site_audit: SiteAuditPayload = {
        "present": True, "domain": "x.com", "pages_crawled": 15, "checks": [],
        "summary": {}, "errors": 0, "offsite": [],
        "roadmap": [
            row("robots.txt allows AI crawlers", "fail"),
            *[row("original data", "partial")] * 12,
            *[row("external citations", "fail")] * 3,
        ],
    }
    out = render_local_report(
        _outcome([]), trade="plumbing", location=MARKET, site_audit=site_audit,
        run_date="2026-07-28",
    )
    # 16 input rows -> 3 distinct fixes.
    assert out.count("| original data") == 1
    assert "original data † (partial on 12 pages)" in out
    assert "external citations † (missing on 3 pages)" in out
    # A single-occurrence fix keeps its plain wording — no "on 1 pages".
    assert "robots.txt allows AI crawlers (fail" not in out
    assert "on 1 pages" not in out
    # Ordering is the synthesizer's; first occurrence wins.
    assert out.index("robots.txt allows") < out.index("original data")
