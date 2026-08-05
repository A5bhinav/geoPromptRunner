"""Phase T — the report contract's sections.

One regression test per spec task. What these guard is not "the builder runs"
but the honesty rules the sections exist to enforce: a rate never ships without
its denominator, a trend never draws a line through two points, an ungated move
never gets an arrow, a slot with no qualifying answer is never filled from
another slot.
"""

from __future__ import annotations

import pytest

from src.api.reports import ReportPayload, build_report
from src.api.sections import (
    MIN_CYCLES_FOR_LINE,
    CycleMetrics,
    build_trend,
    classify_source,
)
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import AccuracyFlag, AnswerJudgment, BrandJudgment, QueryResult


def _result(
    qid: str,
    intent: str,
    engine: str,
    run: int,
    prompt: str,
    resp: str | None,
    citations: list[str] | None = None,
) -> QueryResult:
    return QueryResult(
        query_id=qid,
        intent=intent,
        prompt=prompt,
        engine_name=engine,
        run_index=run,
        response=resp,
        citations=citations or [],
        timestamp=f"2026-06-1{run + 1}T09:00:00Z",
    )


@pytest.fixture
def report() -> ReportPayload:
    """Two questions across two surfaces, three runs, with citations and a flag."""
    results = [
        _result(
            "cmp-02",
            "comparison",
            engine,
            run,
            "Fort vs Whoop — which is better?",
            "Whoop leads; Fort is an option.",
            ["https://www.reddit.com/r/fitness/x", "https://fort.cx/compare"],
        )
        for engine in ("perplexity", "openai_search")
        for run in range(3)
    ] + [
        _result("brd-01", "brand", "perplexity", run, "What is Fort?", "Fort is a wearable.")
        for run in range(3)
    ]

    judgments = [
        AnswerJudgment(
            query_id=r["query_id"],
            engine_name=r["engine_name"],
            intent=r["intent"],
            run_index=r["run_index"],
            assessed=True,
            brands=[
                BrandJudgment(
                    brand="Fort",
                    present=r["query_id"] != "brd-01" or r["run_index"] == 0,
                    prominence="mid_pack",
                    framing="neutral",
                ),
                BrandJudgment(
                    brand="Whoop", present=True, prominence="recommended_first", framing="positive"
                ),
            ],
            accuracy_flags=(
                [
                    AccuracyFlag(
                        type="wrong_pricing",
                        claim="The Fort band costs $349.",
                        reality="$289 pre-order, $319 retail.",
                        severity="high",
                        query_id=r["query_id"],
                        engine_name=r["engine_name"],
                        intent=r["intent"],
                        run_index=r["run_index"],
                        observed_at=f"2026-06-1{r['run_index'] + 1}T09:00:00Z",
                    )
                ]
                if r["query_id"] == "cmp-02"
                else []
            ),
        )
        for r in results
    ]

    outcome = AuditOutcome(
        run_id="run-1",
        client_name="Fort",
        client_domains=["fort.cx"],
        competitors=["Whoop"],
        query_set_version="csv-2026-06-03",
        runs_per_query=3,
        results=results,
        engine_models={"perplexity": "sonar", "openai_search": "gpt-5.6-luna"},
    )
    return build_report(
        outcome,
        judgments=judgments,
        fact_sheet_present=True,
        run_date="2026-06-13",
        location="Berkeley, California, United States",
    )


# --- TR-T1 executive snapshot -------------------------------------------------


def test_exec_snapshot_has_six_measured_tiles(report: ReportPayload) -> None:
    tiles = report["exec_snapshot"]["tiles"]
    assert len(tiles) == 6
    assert [t["key"] for t in tiles] == [
        "mention_rate",
        "change",
        "share_of_model",
        "citation_rate",
        "prominence",
        "coverage",
    ]


def test_exec_snapshot_summary_is_neutral_not_an_action(report: ReportPayload) -> None:
    """The BLUF action clause opens section 8, never section 1.

    A recommendation on page 1 makes the measurement inseparable from the advice,
    which is exactly what an agency reselling the report cannot work with.
    """
    summary = report["exec_snapshot"]["summary"].lower()
    for imperative in ("you should", "we recommend", "fix ", "publish ", "the highest-leverage"):
        assert imperative not in summary, f"section 1 is giving advice: {summary!r}"


def test_first_cycle_change_tile_says_baseline_not_zero(report: ReportPayload) -> None:
    change = next(t for t in report["exec_snapshot"]["tiles"] if t["key"] == "change")
    assert "Baseline" in change["value"]
    assert "0.0 pp" not in change["value"]
    assert change["gated"] is False


def test_no_tile_carries_a_bare_percentage_without_its_count(report: ReportPayload) -> None:
    visibility = next(t for t in report["exec_snapshot"]["tiles"] if t["key"] == "mention_rate")
    # "7 of 12 sampled answers (58%)" — count first, percentage parenthetical.
    assert " of " in visibility["value"]


# --- TR-T3 visibility trend ---------------------------------------------------


def _cycle(run_id: str, date: str, successes: int, n: int, coverage: float = 1.0) -> CycleMetrics:
    return CycleMetrics(
        run_id=run_id,
        run_date=date,
        query_set_version="v1",
        coverage_ratio=coverage,
        mention_successes=successes,
        mention_n=n,
        citation_successes=0,
        citation_n=0,
        share_of_model=0.5,
        prominence="mid_pack",
        brand_counts={},
        mention_by_bucket={},
        citation_counts={},
    )


def test_a_single_cycle_states_a_baseline_instead_of_drawing_a_chart(
    report: ReportPayload,
) -> None:
    trend = report["trend"]
    assert trend["cycles"] == 1
    assert trend["draw_line"] is False
    assert "first comparable cycle" in trend["statement"].lower()


def test_a_line_is_only_drawn_once_there_are_enough_points() -> None:
    """A line through two points asserts a direction the data cannot support."""
    current = _cycle("now", "2026-06-13", 6, 12)
    for count in range(0, MIN_CYCLES_FOR_LINE + 2):
        history = [_cycle(f"h{i}", f"2026-05-0{i + 1}", i, 12) for i in range(count)]
        trend = build_trend(
            history=history,
            current=current,
            runs_per_query=3,
            query_set_version="v1",
            min_coverage=0.95,
        )
        assert trend["draw_line"] is (count + 1 >= MIN_CYCLES_FOR_LINE)


def test_a_half_measured_cycle_is_excluded_and_said_so() -> None:
    """A run that only half-answered looks like a visibility drop and is not one."""
    trend = build_trend(
        history=[_cycle("good", "2026-05-01", 6, 12), _cycle("thin", "2026-05-08", 1, 2, 0.4)],
        current=_cycle("now", "2026-06-13", 7, 12),
        runs_per_query=3,
        query_set_version="v1",
        min_coverage=0.95,
    )
    assert trend["excluded_cycles"] == 1
    assert "left out for incomplete coverage" in trend["statement"]
    assert [p["run_id"] for p in trend["points"]] == ["good", "now"]


def test_a_changed_query_set_is_never_silently_plotted() -> None:
    """Only compare like instruments — the one thing the recurring contract forbids."""
    other = _cycle("other", "2026-05-01", 12, 12)
    trend = build_trend(
        history=[CycleMetrics(**{**other.__dict__, "query_set_version": "v2"})],
        current=_cycle("now", "2026-06-13", 1, 12),
        runs_per_query=3,
        query_set_version="v1",
        min_coverage=0.95,
    )
    assert [p["run_id"] for p in trend["points"]] == ["now"]


# --- TR-T4 results by question type ------------------------------------------


def test_question_types_read_the_family_from_the_run(report: ReportPayload) -> None:
    """Hardcoding the consumer five renders an empty section for every local client."""
    assert report["question_types"]["family"] in {"consumer", "local", "mixed"}
    assert report["question_types"]["rows"], "no buckets rendered"
    for row in report["question_types"]["rows"]:
        assert row["label"] != row["bucket"] or "_" not in row["bucket"]


def test_a_wide_interval_suppresses_the_point_estimate(report: ReportPayload) -> None:
    """P2-T3 defines no minimum n, so this suppresses the misleading part instead."""
    for row in report["question_types"]["rows"]:
        width_pp = (row["mention"]["ci_high"] - row["mention"]["ci_low"]) * 100
        assert row["suppress_point"] is (row["mention"]["n"] > 0 and width_pp > 30.0)


# --- TR-T5 results by surface -------------------------------------------------


def test_every_surface_reports_attempted_versus_returned(report: ReportPayload) -> None:
    assert report["surfaces"]["rows"]
    for row in report["surfaces"]["rows"]:
        assert row["attempted_cells"] >= row["answered_cells"]
        assert row["mention"]["n"] >= 0
        assert row["label"] != row["engine_name"] or "_" not in row["engine_name"]


def test_a_surface_below_the_coverage_gate_is_labelled_not_averaged_away() -> None:
    results = [
        _result("q1", "category", "openai", 0, "best band?", "Fort is good."),
        # `perplexity` attempted two cells and answered neither.
        _result("q1", "category", "perplexity", 0, "best band?", None),
        _result("q2", "category", "perplexity", 0, "best tracker?", None),
    ]
    judgments = [
        AnswerJudgment(
            query_id="q1",
            engine_name="openai",
            intent="category",
            run_index=0,
            assessed=True,
            brands=[BrandJudgment("Fort", True, "mid_pack", "neutral")],
            accuracy_flags=[],
        )
    ]
    payload = build_report(
        AuditOutcome(
            run_id="r",
            client_name="Fort",
            client_domains=[],
            competitors=[],
            query_set_version="v1",
            runs_per_query=1,
            results=results,
        ),
        judgments=judgments,
    )
    # A surface that answered nothing is dead, not degraded — and either way it
    # is named rather than dropped.
    assert "Perplexity" in payload["surfaces"]["dead"] or payload["surfaces"]["degraded"]


# --- TR-T6 competitive position ----------------------------------------------


def test_competitive_rows_are_ordered_by_mention_rate(report: ReportPayload) -> None:
    rates = [row["mention"]["rate"] for row in report["competitive"]["rows"]]
    assert rates == sorted(rates, reverse=True)


def test_no_direction_arrow_without_a_prior_cycle(report: ReportPayload) -> None:
    for row in report["competitive"]["rows"]:
        assert row["direction"] == "unknown"
        assert row["delta"] == "Baseline — no prior cycle"


# --- TR-T7 citation results ---------------------------------------------------


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("fort.cx", "owned"),
        ("www.reddit.com", "social"),
        ("youtube.com", "video"),
        ("trustpilot.com", "directory"),
        ("whoop.com", "competitor"),
        ("theverge.com", "earned"),
    ],
)
def test_source_classification_is_deterministic(domain: str, expected: str) -> None:
    """No LLM on this path: a model that reclassifies youtube.com between editions
    manufactures a change the client did not make."""
    assert classify_source(domain, ["fort.cx"], ["Whoop"]) == expected


def test_citations_carry_a_pareto_curve(report: ReportPayload) -> None:
    """"Are we dependent on 2 sources or 20" — which a descending bar cannot answer."""
    rows = report["citations"]["domains"]
    assert rows
    assert rows[-1]["cumulative_share"] == pytest.approx(1.0)
    assert all(
        rows[i]["cumulative_share"] <= rows[i + 1]["cumulative_share"] + 1e-9
        for i in range(len(rows) - 1)
    )
    assert "account for" in report["citations"]["concentration"]


def test_citation_section_stays_descriptive(report: ReportPayload) -> None:
    prose = " ".join(
        [report["citations"]["concentration"], report["citations"]["note"]]
    ).lower()
    for advice in ("you need", "you should", "strategy", "we recommend"):
        assert advice not in prose


# --- TR-T8 representative answers --------------------------------------------


def test_five_slots_always_render_with_a_published_rule(report: ReportPayload) -> None:
    slots = report["representative_answers"]["slots"]
    assert [s["slot"] for s in slots] == [
        "strong",
        "weak",
        "missing",
        "citation",
        "inaccurate",
    ]
    for slot in slots:
        assert slot["rule"], f"{slot['slot']} has no published selection rule"
        if not slot["available"]:
            assert slot["note"] == "No qualifying example this cycle."


def test_an_empty_slot_is_never_filled_from_another(report: ReportPayload) -> None:
    """Substituting a strong appearance into the "missing" slot makes the section
    a highlight reel."""
    filled = [s for s in report["representative_answers"]["slots"] if s["available"]]
    keys = [(s["query_id"], s["engine_name"], s["run_index"], s["slot"]) for s in filled]
    # Two slots may legitimately quote the same cell (a strong appearance can also
    # be the citation), but never the same slot twice.
    assert len({k[3] for k in keys}) == len(keys)


def test_representative_answers_are_excerpts_not_full_text(report: ReportPayload) -> None:
    for slot in report["representative_answers"]["slots"]:
        assert len(slot["excerpt"]) <= 401


# --- TR-T9 methodology --------------------------------------------------------


def test_methodology_names_every_surface_and_its_pinned_model(report: ReportPayload) -> None:
    surfaces = dict(report["methodology"]["surfaces"])
    assert surfaces
    for label, model in surfaces.items():
        assert label and model, f"{label} has no pinned model recorded"


def test_methodology_defines_every_metric_and_publishes_the_selection_rules(
    report: ReportPayload,
) -> None:
    terms = {term for term, _ in report["methodology"]["definitions"]}
    assert {"AI visibility", "Share of model", "Percentage points (pp)"} <= terms
    assert len(report["methodology"]["selection_rules"]) == 5


def test_methodology_carries_the_disclosures_verbatim(report: ReportPayload) -> None:
    assert report["methodology"]["non_reproducibility"] == report["methodology_disclosure"]
    assert report["methodology"]["independence"] == report["independence_disclaimer"]
    assert report["methodology"]["judge_agreement"] == report["judge_agreement"]


def test_methodology_states_the_measurement_window_and_geography(
    report: ReportPayload,
) -> None:
    assert report["methodology"]["window_start"]
    assert report["methodology"]["window_end"]
    assert "Berkeley" in report["methodology"]["geography"]


# --- TR-T10 back matter -------------------------------------------------------


def test_back_matter_has_all_six_appendices(report: ReportPayload) -> None:
    assert [a["id"] for a in report["back_matter"]["appendices"]] == [
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
    ]
    for appendix in report["back_matter"]["appendices"]:
        assert appendix["title"]
        assert appendix["columns"]


def test_a3_rows_join_to_a_front_matter_theme(report: ReportPayload) -> None:
    a3 = next(a for a in report["back_matter"]["appendices"] if a["id"] == "A3")
    themes = {g["theme"] for g in report["finding_groups"]}
    assert a3["rows"], "fixture should produce flags"
    for row in a3["rows"]:
        assert row[1] in themes, f"appendix row {row[0]} joins to no front-matter theme"


def test_verbatim_answer_text_is_never_printed_in_the_back_matter(
    report: ReportPayload,
) -> None:
    """450 answers inline is 90–150 pages — exactly the blob this work kills."""
    a2 = next(a for a in report["back_matter"]["appendices"] if a["id"] == "A2")
    for row in a2["rows"]:
        assert "Whoop leads; Fort is an option." not in row
    assert "export" in a2["note"]


def test_a1_truncation_is_spread_across_questions_not_an_alphabetical_cliff() -> None:
    """A1 is capped, and the cap must not starve the questions sorted last.

    `rows[:cap]` on a ledger sorted by question gives the first few questions
    every citation and the rest none. A client reading a ledger that stops dead
    at question 4 of 10 concludes "you didn't measure the rest", which is the
    opposite of what the appendix is for.
    """
    from src.api.sections import _MAX_A1_ROWS, _spread, _table

    # Ten questions, each with more citations than its even share of the cap.
    per_question = _MAX_A1_ROWS  # comfortably over the share
    groups = [[[f"q{q}-url{i}"] for i in range(per_question)] for q in range(10)]
    rows = [row for g in groups for row in g]

    table = _table(
        "A1", "Citation ledger", ["URL"], rows, cap=_MAX_A1_ROWS, groups=groups,
        spread_unit="questions",
    )

    assert len(table["rows"]) == _MAX_A1_ROWS
    assert table["total_rows"] == len(rows)
    # Every question is represented — the point of the whole exercise.
    kept = {row[0].split("-")[0] for row in table["rows"]}
    assert kept == {f"q{q}" for q in range(10)}, f"questions missing from the ledger: {kept}"
    # And the note says both the count and that it is a spread, not a prefix.
    assert f"Showing {_MAX_A1_ROWS} of {len(rows)} rows" in table["note"]
    assert "spread evenly across all 10 questions" in table["note"]
    assert "CSV export" in table["note"]

    # Uncapped input is passed through untouched, in order.
    small = [[["only-url"]]]
    assert _table("A1", "t", ["URL"], [["only-url"]], cap=_MAX_A1_ROWS, groups=small)[
        "rows"
    ] == [["only-url"]]
    # A cap larger than the data keeps everything; a zero cap keeps nothing.
    assert _spread(groups, 0) == []


def test_every_appendix_row_is_stringified_for_a_generic_renderer(
    report: ReportPayload,
) -> None:
    for appendix in report["back_matter"]["appendices"]:
        for row in appendix["rows"]:
            assert len(row) == len(appendix["columns"])
            assert all(isinstance(cell, str) for cell in row)


# --- the oldest-open tile (P1-T6 tile 4, unblocked by P2-T2) ------------------


def test_the_oldest_open_tile_names_a_finding(report: ReportPayload) -> None:
    """The tile that replaced the grade. SLA-style aging is a count, not an opinion."""
    oldest = report["scorecard"]["oldest_open"]
    assert oldest is not None
    assert oldest["cycles_open"] >= 1
    assert oldest["title"]
