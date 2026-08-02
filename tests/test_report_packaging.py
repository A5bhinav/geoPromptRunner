"""The packaged deliverable: what a client actually reads (audit-packaging P1).

These are the rules that cost credibility or create legal exposure when broken,
so they are asserted rather than reviewed:

- no internal id ever reaches a client,
- no rate without its denominator,
- no letter grade and no composite score anywhere,
- every Critical/High finding carries a verbatim prompt, a named model and a date,
- the non-reproducibility disclosure ships verbatim, exactly once,
- one counting unit per client-facing view.

The web assertions read the TSX source rather than a rendered DOM: this repo has
no JS test runner (``tests/test_frontend.py`` runs ``tsc`` and the teaser suite),
and a source-level guard still fails loudly the moment someone renders a query id
or reintroduces the grade. Upgrade them to real render tests if a runner lands.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.api.reports import (
    INDEPENDENCE_DISCLAIMER,
    NON_REPRODUCIBILITY_DISCLOSURE,
    ReportPayload,
    build_report,
)
from src.pipeline.orchestrator import AuditOutcome
from src.storage.models import AccuracyFlag, AnswerJudgment, BrandJudgment, QueryResult

WEB = Path(__file__).resolve().parents[1] / "web"
REPORT_COMPONENTS = [
    WEB / "components" / "report-view.tsx",
    WEB / "components" / "charts.tsx",
    WEB / "components" / "badges.tsx",
]

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def code_of(path: Path) -> str:
    """A source file with its comments removed.

    Every scan below is about what the component RENDERS, and the comments in
    these files necessarily quote the banned strings in order to explain why they
    are banned ("never `l.query_id`", "not 'hallucinates'"). Matching the prose
    would make the rules unwritable.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", path.read_text()))


# --- fixtures -----------------------------------------------------------------


def _result(
    qid: str, intent: str, engine: str, run: int, prompt: str, resp: str | None
) -> QueryResult:
    return QueryResult(
        query_id=qid,
        intent=intent,
        prompt=prompt,
        engine_name=engine,
        run_index=run,
        response=resp,
        citations=[],
        timestamp=f"2026-06-1{run + 1}T09:00:00Z",
    )


def _flag(
    kind: str, claim: str, reality: str, sev: str, qid: str, engine: str, intent: str, run: int
) -> AccuracyFlag:
    return AccuracyFlag(
        type=kind,
        claim=claim,
        reality=reality,
        severity=sev,
        query_id=qid,
        engine_name=engine,
        intent=intent,
        run_index=run,
        observed_at=f"2026-06-1{run + 1}T09:00:00Z",
    )


PRICING_CLAIM = "The Fort band costs $349."
IDENTITY_CLAIM = "There isn't a widely recognized brand called 'Fort'."


@pytest.fixture
def report() -> ReportPayload:
    """A small but realistic judged run: two findings, three engines, three runs."""
    results = [
        _result("cmp-02", "comparison", engine, run, "Fort vs Whoop — which is better?", "…")
        for engine in ("perplexity", "openai_search")
        for run in range(3)
    ] + [
        _result("brd-01", "brand", "gemini_grounded", run, "What is Fort?", "…") for run in range(3)
    ]

    judgments: list[AnswerJudgment] = []
    for r in results:
        flags: list[AccuracyFlag] = []
        if r["query_id"] == "cmp-02":
            flags.append(
                _flag(
                    "wrong_pricing",
                    PRICING_CLAIM,
                    "$289 pre-order, $319 retail.",
                    "high",
                    r["query_id"],
                    r["engine_name"],
                    r["intent"],
                    r["run_index"],
                )
            )
        elif r["run_index"] < 2:  # 2 of 3 runs — a genuinely intermittent finding
            flags.append(
                _flag(
                    "missing_or_invented_feature",
                    "Fort does not track heart rate.",
                    "Fort tracks all-day cardio, sleep, HRV and stress.",
                    "med",
                    r["query_id"],
                    r["engine_name"],
                    r["intent"],
                    r["run_index"],
                )
            )
        judgments.append(
            AnswerJudgment(
                query_id=r["query_id"],
                engine_name=r["engine_name"],
                intent=r["intent"],
                run_index=r["run_index"],
                assessed=True,
                # The brand query is a LOSING cell: the competitor is named and
                # the client is not. That asymmetry is what `losing_queries` is
                # for, and a fixture where the client is always present would
                # leave the verbatim-prompt rule untested.
                brands=[
                    BrandJudgment(
                        brand="Fort",
                        present=r["query_id"] != "brd-01",
                        prominence="mid_pack" if r["query_id"] != "brd-01" else "absent",
                        framing="neutral",
                    ),
                    BrandJudgment(
                        brand="Whoop",
                        present=True,
                        prominence="recommended_first",
                        framing="positive",
                    ),
                ],
                accuracy_flags=flags,
            )
        )

    outcome = AuditOutcome(
        run_id="run-1",
        client_name="Fort",
        client_domains=["fort.cx"],
        competitors=["Whoop"],
        query_set_version="csv-2026-06-03",
        runs_per_query=3,
        results=results,
        engine_models={
            "perplexity": "sonar",
            "openai_search": "gpt-5.6-luna",
            "gemini_grounded": "gemini-3.6-flash",
        },
    )
    return build_report(
        outcome, judgments=judgments, fact_sheet_present=True, run_date="2026-06-13"
    )


# --- no internal id ever reaches a client -------------------------------------


def test_losing_rows_carry_the_verbatim_question(report: ReportPayload) -> None:
    """P1-T3. `cmp-05` is the most actionable data in the report made unreadable."""
    assert report["losing_queries"], "fixture should produce losing cells"
    for row in report["losing_queries"]:
        assert row["prompt"], f"{row['query_id']} has no prompt text to render"
        assert not re.fullmatch(r"(cat|cmp|pa|brd|brand|adj)-\d+", row["prompt"])


def test_the_report_view_never_renders_a_query_id() -> None:
    source = code_of(WEB / "components" / "report-view.tsx")
    assert "l.query_id" not in source, "the losing-queries table is rendering an internal id"
    # The id may still be READ (as a React key or a join), but never interpolated
    # as visible text.
    assert "{l.prompt" in source or "l.prompt ?" in source


def test_every_finding_title_is_a_template_not_model_prose(report: ReportPayload) -> None:
    for group in report["finding_groups"]:
        assert group["title"]
        assert "{client}" not in group["title"], "the client slot was never substituted"
        assert "$349" not in group["title"], "the title inherited the model's own wording"


# --- no rate without its denominator ------------------------------------------


def test_ai_visibility_ships_as_a_count_with_its_denominator(report: ReportPayload) -> None:
    tile = report["scorecard"]["ai_visibility"]
    assert tile["n"] > 0
    assert tile["label"].startswith(f"{tile['successes']} of {tile['n']}")
    assert 0.0 <= tile["ci_low"] <= tile["rate"] <= tile["ci_high"] <= 1.0


def test_the_interval_is_design_corrected_not_naive(report: ReportPayload) -> None:
    """n_eff < n at K=3, because three runs of one prompt are not three looks."""
    tile = report["scorecard"]["ai_visibility"]
    assert tile["n_eff"] < tile["n"]


def test_every_finding_states_how_many_runs_produced_it(report: ReportPayload) -> None:
    for group in report["finding_groups"]:
        occ = group["occurrence"]
        assert occ["total"] >= occ["observed"] >= 1
        assert "of" in occ["phrase"]
        assert str(occ["observed"]) in occ["phrase"] and str(occ["total"]) in occ["phrase"]


def test_an_intermittent_finding_is_not_reported_as_universal(report: ReportPayload) -> None:
    """2 of 3 must read as 2 of 3 — the whole point of the occurrence line."""
    intermittent = [g for g in report["finding_groups"] if g["theme"] == "feature_omitted"]
    assert intermittent, "fixture should produce the 2-of-3 finding"
    assert intermittent[0]["occurrence"] == {
        **intermittent[0]["occurrence"],
        "observed": 2,
        "total": 3,
    }


# --- no letter grade, no composite score --------------------------------------


def test_the_payload_keeps_the_grade_for_back_compat_but_nothing_renders_it() -> None:
    view = code_of(WEB / "components" / "report-view.tsx")
    assert "gradeColor" not in view, "the grade colouring function is back"
    assert "visibility_grade" not in view, "the report is rendering the grade again"
    assert "AI Visibility Grade" not in view


def test_no_letter_grade_string_can_appear_in_the_rendered_tiles(report: ReportPayload) -> None:
    """Every headline number is COUNTED or MEASURED — never an invented score."""
    tile_values = [
        report["scorecard"]["ai_visibility"]["label"],
        str(report["scorecard"]["open_findings"]["themes"]),
        str(report["scorecard"]["open_findings"]["critical"]),
    ]
    for value in tile_values:
        assert not re.fullmatch(r"[A-F][+-]?", value.strip())


def test_the_four_tiles_are_all_counted_or_measured(report: ReportPayload) -> None:
    scorecard = report["scorecard"]
    assert "ai_visibility" in scorecard  # measured
    assert "open_findings" in scorecard  # counted
    assert "share_of_model_client" in scorecard  # measured
    assert "oldest_open" in scorecard  # counted (None until the lifecycle lands)


# --- one counting unit --------------------------------------------------------


def test_headline_counts_are_themes_and_instances_stay_secondary(report: ReportPayload) -> None:
    open_findings = report["scorecard"]["open_findings"]
    assert open_findings["themes"] == len(report["finding_groups"])
    assert open_findings["instances"] == sum(g["instance_count"] for g in report["finding_groups"])
    # The two must be genuinely different here, or the test proves nothing.
    assert open_findings["instances"] > open_findings["themes"]


def test_severity_counts_are_themes_and_sum_to_the_theme_total(report: ReportPayload) -> None:
    open_findings = report["scorecard"]["open_findings"]
    assert sum(open_findings["by_severity"].values()) == open_findings["themes"]


def test_no_flag_is_lost_in_the_grouping(report: ReportPayload) -> None:
    """A grouping that drops a finding is worse than one that groups it oddly."""
    observed_instances = sum(g["instance_count"] for g in report["finding_groups"])
    assert observed_instances == 8  # 6 pricing cells + 2 intermittent feature cells


def test_the_report_collapses_to_a_readable_number_of_findings(report: ReportPayload) -> None:
    assert len(report["finding_groups"]) <= 15


# --- evidence -----------------------------------------------------------------


def test_every_critical_and_high_finding_is_checkable(report: ReportPayload) -> None:
    """Engine + timestamp + verbatim prompt, or it is not shippable."""
    serious = [g for g in report["finding_groups"] if g["severity"] in ("critical", "high")]
    assert serious, "fixture should produce at least one"
    for group in serious:
        assert group["evidence"], f"{group['title']} has no evidence"
        for e in group["evidence"]:
            assert e["prompt"], "a finding with no verbatim prompt is not shippable"
            assert e["engine_name"]
            assert e["observed_at"]
            assert e["excerpt"]
            assert e["model_id"], "the pinned model that answered must be named"


def test_a_pricing_error_escalates_to_critical(report: ReportPayload) -> None:
    pricing = [g for g in report["finding_groups"] if g["theme"] == "pricing_offer"]
    assert pricing and pricing[0]["severity"] == "critical"


def test_findings_are_ordered_worst_first(report: ReportPayload) -> None:
    order = ["critical", "high", "med", "low"]
    ranks = [order.index(g["severity"]) for g in report["finding_groups"]]
    assert ranks == sorted(ranks), "findings must never render chronologically"


# --- actions ------------------------------------------------------------------


def test_every_finding_has_an_action_with_an_owner_and_an_effort(report: ReportPayload) -> None:
    """A finding with no action is the #1 cited driver of churn in this category."""
    for group in report["finding_groups"]:
        assert group["action"] and "{client}" not in group["action"]
        assert group["owner"] in {"Marketing", "PR", "Eng", "Legal"}
        assert group["effort"] in {"S", "M", "L"}
        assert group["verification"]


def test_the_action_list_is_a_plan_not_a_backlog(report: ReportPayload) -> None:
    assert len(report["priority_actions"]) <= 7
    assert report["priority_actions"] == report["finding_groups"][: len(report["priority_actions"])]


def test_no_action_promises_an_outcome(report: ReportPayload) -> None:
    """The FTC pattern against guaranteed-ranking SEO claims applies identically."""
    banned = ("guarantee", "guaranteed", "will rank", "will get you", "ensures that")
    for group in report["finding_groups"]:
        text = f"{group['action']} {group['verification']}".lower()
        for phrase in banned:
            assert phrase not in text, f"{group['title']} promises an outcome: {phrase!r}"


# --- executive summary --------------------------------------------------------


def test_the_exec_summary_is_well_formed_and_leaves_no_placeholders(report: ReportPayload) -> None:
    summary = report["exec_summary"]
    assert summary and "{" not in summary and "}" not in summary
    assert report["client_name"] in summary


def test_the_exec_summary_degrades_rather_than_lying_with_no_data() -> None:
    empty = build_report(
        AuditOutcome(
            run_id=None,
            client_name="Fort",
            client_domains=[],
            competitors=[],
            query_set_version="v1",
            runs_per_query=3,
            results=[],
        )
    )
    assert "could not be measured" in empty["exec_summary"]
    assert empty["scorecard"]["ai_visibility"]["n"] == 0
    assert empty["scorecard"]["ai_visibility"]["label"] == "insufficient data"


def test_a_first_cycle_says_so_rather_than_implying_a_direction(report: ReportPayload) -> None:
    assert report["comparison_blocked_reason"] == "no_prior_run"
    assert "first cycle" in report["exec_summary"]


def test_a_changed_query_set_blocks_the_comparison_honestly() -> None:
    """Only compare like instruments — never silently across a changed one."""
    outcome = AuditOutcome(
        run_id="r2",
        client_name="Fort",
        client_domains=[],
        competitors=[],
        query_set_version="csv-2026-07-01",
        runs_per_query=3,
        results=[_result("cat-01", "category", "perplexity", 0, "best wearable", "…")],
    )
    changed = build_report(outcome, prior_run=("r1", "csv-2026-06-03"))
    assert changed["comparison_blocked_reason"] == "query_set_changed"

    same = build_report(outcome, prior_run=("r1", "csv-2026-07-01"))
    assert same["comparison_blocked_reason"] == ""


# --- disclosures --------------------------------------------------------------


def test_the_non_reproducibility_disclosure_ships_verbatim(report: ReportPayload) -> None:
    """Do not paraphrase it. It is worded to be honest without self-undermining."""
    assert report["methodology_disclosure"] == NON_REPRODUCIBILITY_DISCLOSURE
    assert "will reproduce on demand" in report["methodology_disclosure"]
    assert (
        "not a guarantee of what you will see if you ask right now"
        in (report["methodology_disclosure"])
    )


def test_the_independence_disclaimer_ships_verbatim(report: ReportPayload) -> None:
    assert report["independence_disclaimer"] == INDEPENDENCE_DISCLAIMER
    for vendor in ("OpenAI", "Anthropic", "Google", "Perplexity"):
        assert vendor in report["independence_disclaimer"]


def test_each_disclosure_renders_exactly_once() -> None:
    view = code_of(WEB / "components" / "report-view.tsx")
    assert view.count("report.methodology_disclosure}") == 1
    assert view.count("report.independence_disclaimer}") == 1


# --- copy that is off-limits --------------------------------------------------


def test_no_component_anthropomorphises_a_named_vendors_model() -> None:
    """ "Lies", "hallucinates" — imprecise, and legally careless about a vendor."""
    banned = ("hallucinat", "is lying", "lies about", "falsely claim")
    for path in REPORT_COMPONENTS:
        source = code_of(path).lower()
        for phrase in banned:
            assert phrase not in source, f"{path.name} uses {phrase!r} about a model"


def test_no_component_uses_the_off_limits_marketing_phrases() -> None:
    banned = ("peer benchmark", "factcheck", "what people actually ask ai", "guaranteed")
    for path in REPORT_COMPONENTS:
        source = code_of(path).lower()
        for phrase in banned:
            assert phrase not in source, f"{path.name} contains {phrase!r}"


# --- brand --------------------------------------------------------------------


def test_sky_is_unreachable_outside_the_on_navy_scope() -> None:
    """Encoded in the token layer, so misuse is a bug rather than a review note."""
    css = code_of(WEB / "styles" / "sable.css")
    # The hex appears exactly once, and only inside the `.on-navy` block.
    assert css.count("#7fa6d9") == 1
    on_navy_start = css.index(".on-navy")
    assert css.index("#7fa6d9") > on_navy_start
    assert "--sky:" not in css, "Sky must not exist as a root-scope token"


def test_the_severity_ramp_is_the_navy_ramp_with_no_alert_hue() -> None:
    css = code_of(WEB / "styles" / "sable.css")
    for token in ("--sev-critical", "--sev-high", "--sev-medium", "--sev-low"):
        assert token in css
    # Sable has no red and no gold; "no colours outside the palette" is explicit.
    assert "#fdb515" not in css and "#003262" not in css  # the `weir` system
    assert not re.search(r"#(f[0-9a-f]{2}0000|ff0000|dc2626|ef4444)", css, re.I)


def test_report_components_take_colour_from_tokens_not_raw_hex() -> None:
    """A raw hex in a report component is a near-miss colour waiting to happen."""
    for path in (WEB / "components" / "report-view.tsx", WEB / "components" / "badges.tsx"):
        source = code_of(path)
        # `currentColor` and `#fff` on a navy fill are the two sanctioned literals;
        # anything else must come from a `var(--…)` token.
        stray = [h for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", source) if h.lower() != "#fff"]
        assert not stray, f"{path.name} hardcodes {stray}"


def test_severity_never_relies_on_colour_alone() -> None:
    """Load-bearing: a single-hue ramp cannot carry the distinction by itself."""
    badges = code_of(WEB / "components" / "badges.tsx")
    assert "SeverityIcon" in badges
    for tier in ("critical", "high", "med", "low"):
        assert f'"{tier}"' in badges
    for shape in ("polygon", "circle", "rect"):
        assert shape in badges, f"the {shape} severity glyph is missing"


def test_the_brand_lives_behind_one_config_object() -> None:
    """An agency white-label replaces the whole skin, not just an accent."""
    brand = code_of(WEB / "lib" / "brand.ts")
    assert "export const SABLE" in brand and "export const NEUTRAL" in brand
    view = code_of(WEB / "components" / "report-view.tsx")
    assert "brand.name" in view and "brand.showMark" in view
    assert '"Sable"' not in view, "the report hardcodes the tenant name"


def test_the_donut_is_gone() -> None:
    """Arc-angle comparison across six non-adjacent segments is unreadable."""
    charts = code_of(WEB / "components" / "charts.tsx")
    assert "ShareDonut" not in charts
    assert "ShareStackedBar" in charts
    assert "PieChart" not in charts


def test_the_heatmap_prints_numbers_in_every_cell() -> None:
    """Colour to scan, digits to verify. Colour alone also fails accessibility."""
    charts = code_of(WEB / "components" / "charts.tsx")
    assert "EngineHeatmap" in charts
    assert "{cell.present}/{cell.cells}" in charts


# --- prior-run resolution (P2-T1) ---------------------------------------------


def test_prior_run_resolution_skips_unfinished_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """An interrupted run measured a smaller thing.

    Comparing against it would report the shortfall as a drop in the client's
    visibility — the single most damaging false claim this product can make — so
    a non-`done` run is not a comparable prior run at all.
    """
    from src.api import runner
    from src.storage import db

    monkeypatch.setattr(
        db,
        "list_audit_runs",
        lambda client: [
            {"id": "old", "created_at": "2026-06-01", "status": "done", "query_set_version": "v1"},
            {
                "id": "half",
                "created_at": "2026-06-08",
                "status": "failed",
                "query_set_version": "v1",
            },
        ],
    )
    assert runner._prior_comparable_run("new", "Fort", "2026-06-13") == ("old", "v1")


def test_prior_run_resolution_returns_none_on_a_first_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api import runner
    from src.storage import db

    monkeypatch.setattr(db, "list_audit_runs", lambda client: [])
    assert runner._prior_comparable_run("new", "Fort", "2026-06-13") is None


def test_prior_run_resolution_degrades_rather_than_taking_out_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A storage blip reads as a first cycle, which is conservative and honest."""
    from src.api import runner
    from src.storage import db

    def _boom(client: str) -> list[dict[str, object]]:
        raise db.StorageError("supabase unreachable")

    monkeypatch.setattr(db, "list_audit_runs", _boom)
    assert runner._prior_comparable_run("new", "Fort", "2026-06-13") is None


def test_no_fact_sheet_reads_as_not_assessed_never_as_accurate() -> None:
    """Zero findings looks identical whether nothing was checked or everything
    checked out. They are opposite claims, and congratulating a client on an
    audit that never ran is the overclaim this sentence exists to avoid.

    Caught on a real stored run (Fort, ec2a1bca), which has no fact sheet and was
    being told the models described it accurately.
    """
    no_sheet = build_report(
        AuditOutcome(
            run_id="r",
            client_name="Fort",
            client_domains=[],
            competitors=[],
            query_set_version="v1",
            runs_per_query=3,
            results=[
                _result("cat-01", "category", "perplexity", 0, "best wearable", "Fort is one.")
            ],
        ),
        judgments=[
            AnswerJudgment(
                query_id="cat-01",
                engine_name="perplexity",
                intent="category",
                run_index=0,
                assessed=True,
                brands=[
                    BrandJudgment(
                        brand="Fort", present=True, prominence="mid_pack", framing="neutral"
                    )
                ],
                accuracy_flags=[],
            )
        ],
        fact_sheet_present=False,
    )
    assert no_sheet["scorecard"]["accuracy_assessed"] is False
    assert "not assessed" in no_sheet["exec_summary"]
    assert "accurately" not in no_sheet["exec_summary"]


# --- regressions found on the real Fort run (ff231808) -------------------------


def test_cards_are_themes_not_claim_clusters() -> None:
    """The spec's own acceptance: the Fitbit / pickleball / not-recognized flags
    all land in ONE group.

    They share almost no tokens, so they cluster apart; they are one root cause
    with one fix. Grouping on `(theme, cluster_id)` instead produced 54 cards from
    the real 115-flag Fort run — the blob this work exists to remove.
    """
    from src.pipeline.findings import build_finding_groups

    claims = [
        "Fort is confused with Fitbit's tracker line.",
        "Fort is a pickleball scoring app.",
        "There isn't a widely recognized brand called 'Fort'.",
    ]
    result = build_finding_groups(
        [
            _flag(
                "identity",
                c,
                "Fort is a strength-training wearable.",
                "high",
                "brd-01",
                "perplexity",
                "brand",
                i,
            )
            for i, c in enumerate(claims)
        ],
        client="Fort",
        prompts_by_query={"brd-01": "what is Fort?"},
        runs_by_cell={("brd-01", "perplexity"): 3},
        total_engines=4,
    )
    assert len(result.groups) == 1
    assert result.groups[0].theme == "identity_disambiguation"
    # …and the distinct claims survive one level down, for the lifecycle engine.
    assert len(result.groups[0].member_cluster_ids) == 3
    assert result.groups[0].instance_count == 3


def test_a_theme_card_quotes_one_claim_per_cluster_not_three_restatements() -> None:
    from src.pipeline.findings import build_finding_groups

    flags = [
        _flag(
            "wrong_pricing",
            claim,
            "$289 pre-order.",
            "high",
            "cmp-01",
            "perplexity",
            "comparison",
            i,
        )
        for i, claim in enumerate(
            ["It costs $349.", "It costs $349!", "Retail is $319 plus a fee.", "The price is $289."]
        )
    ]
    group = build_finding_groups(
        flags,
        client="Fort",
        prompts_by_query={"cmp-01": "how much is Fort?"},
        runs_by_cell={("cmp-01", "perplexity"): 4},
        total_engines=4,
    ).groups[0]
    # $349/$349! collapse; $319 and $289 are separate findings (the numeric guard).
    assert len(group.member_cluster_ids) == 3
    assert len(set(group.representative_claims)) == len(group.representative_claims)


def test_a_run_without_provenance_refuses_to_claim_reproducibility() -> None:
    """ "Observed in 4 of 4 runs" asserts perfect reproducibility.

    A run stored before per-cell provenance existed recorded no cells at all, so
    it has no basis for that claim — and rounding `total` up to `observed` made it
    anyway, on every finding in every legacy run.
    """
    from src.pipeline.findings import build_finding_groups

    legacy = [
        AccuracyFlag(
            type="stale", claim=f"It ships in 202{i}.", reality="Ships Q2 2027.", severity="high"
        )
        for i in range(4)
    ]
    group = build_finding_groups(
        legacy,
        client="Fort",
        prompts_by_query={},
        runs_by_cell={},
        total_engines=4,
    ).groups[0]
    phrase = group.occurrence.phrase()
    assert group.occurrence.total == 0
    assert " of " not in phrase, "a denominator was invented"
    assert "predates per-answer provenance" in phrase
    assert group.evidence == []
    # Ranking still works: severity and breadth order it, rather than every score
    # collapsing to zero because breadth was measured as 0 engines.
    assert group.priority > 0


def test_a_stored_run_keeps_its_evidence_trail(report: ReportPayload) -> None:
    """Provenance must survive storage, not just the live path.

    `flag_to_dict` writes four keys on purpose — it is shared with the judge
    cache, which is keyed per ANSWER and must stay byte-identical — so the stored
    flag dicts carry no cell. `db._row_to_judgment` re-stamps them from the row's
    own columns and `build_report` adds the timestamp from `query_results`.

    Without both, EVERY run read back from storage has anonymous flags forever:
    no verbatim prompt, no named model, no date, so `build_finding_groups`
    correctly refuses to build an evidence bundle and every card loses its
    evidence trail. It looked like a legacy-run problem until a freshly-judged
    run was read back and had the same gap.
    """
    from src.storage.db import _judgment_to_row, _row_to_judgment

    original = AnswerJudgment(
        query_id="cmp-02",
        engine_name="perplexity",
        intent="comparison",
        run_index=1,
        assessed=True,
        brands=[],
        accuracy_flags=[AccuracyFlag("wrong_pricing", PRICING_CLAIM, "$289 pre-order.", "high")],
    )
    restored = _row_to_judgment(_judgment_to_row("run-1", original))
    flag = restored.accuracy_flags[0]
    assert flag.has_provenance
    assert (flag.query_id, flag.engine_name, flag.intent, flag.run_index) == (
        "cmp-02",
        "perplexity",
        "comparison",
        1,
    )


def test_the_evidence_names_the_model_that_answered_not_the_current_pin() -> None:
    """After a repin, re-deriving the model would misattribute a stored answer.

    The June Fort run was answered by claude-sonnet-4-5 and gemini-2.5-flash;
    those surfaces are pinned to sonnet-5 and gemini-3.6-flash today. The run
    row's `engine_models` is the only honest source.
    """
    outcome = AuditOutcome(
        run_id="r",
        client_name="Fort",
        client_domains=[],
        competitors=[],
        query_set_version="v1",
        runs_per_query=1,
        results=[_result("cmp-02", "comparison", "anthropic_search", 0, "Fort vs Whoop?", "…")],
        engine_models={"anthropic_search": "claude-sonnet-4-5-20250929"},
    )
    built = build_report(
        outcome,
        judgments=[
            AnswerJudgment(
                query_id="cmp-02",
                engine_name="anthropic_search",
                intent="comparison",
                run_index=0,
                assessed=True,
                brands=[],
                accuracy_flags=[
                    _flag(
                        "wrong_pricing",
                        PRICING_CLAIM,
                        "$289 pre-order.",
                        "high",
                        "cmp-02",
                        "anthropic_search",
                        "comparison",
                        0,
                    )
                ],
            )
        ],
        fact_sheet_present=True,
    )
    evidence = built["finding_groups"][0]["evidence"][0]
    assert evidence["model_id"] == "claude-sonnet-4-5-20250929"
    assert evidence["observed_at"], "the date must come from the query_results row"


# --- what changed (P2-T5) -----------------------------------------------------


def _cycle(run_id: str, date: str, themes: set[str], coverage: float = 1.0):  # type: ignore[no-untyped-def]
    from src.pipeline.lifecycle import CycleObservation, RunMeta

    return CycleObservation(
        run=RunMeta(run_id, date, "done", coverage, "csv-2026-06-03"),
        themes=frozenset(themes),
    )


def _report_with(prior_cycles, prior_engine_counts=None, report_fixture=None):  # type: ignore[no-untyped-def]
    """Rebuild the standard fixture with a history behind it."""
    results = [
        _result("cmp-02", "comparison", "perplexity", run, "Fort vs Whoop?", "…")
        for run in range(3)
    ]
    judgments = [
        AnswerJudgment(
            query_id="cmp-02",
            engine_name="perplexity",
            intent="comparison",
            run_index=r["run_index"],
            assessed=True,
            brands=[
                BrandJudgment(brand="Fort", present=True, prominence="mid_pack", framing="neutral")
            ],
            accuracy_flags=[
                _flag(
                    "wrong_pricing",
                    PRICING_CLAIM,
                    "$289 pre-order.",
                    "high",
                    "cmp-02",
                    "perplexity",
                    "comparison",
                    r["run_index"],
                )
            ],
        )
        for r in results
    ]
    return build_report(
        AuditOutcome(
            run_id="current",
            client_name="Fort",
            client_domains=[],
            competitors=[],
            query_set_version="csv-2026-06-03",
            runs_per_query=3,
            results=results,
            engine_models={"perplexity": "sonar"},
        ),
        judgments=judgments,
        fact_sheet_present=True,
        run_date="2026-06-20",
        prior_run=("prior", "csv-2026-06-03"),
        prior_cycles=prior_cycles,
        prior_engine_counts=prior_engine_counts,
    )


def test_no_prior_run_shows_no_comparison_rather_than_an_empty_one(report: ReportPayload) -> None:
    assert report["what_changed"]["available"] is False
    assert report["comparison_blocked_reason"] == "no_prior_run"


def test_a_persisting_finding_is_labelled_as_such() -> None:
    built = _report_with([_cycle("prior", "2026-06-13", {"pricing_offer"})])
    assert built["what_changed"]["available"] is True
    group = next(g for g in built["finding_groups"] if g["theme"] == "pricing_offer")
    assert group["lifecycle_status"] == "persisting"
    assert group["cycles_open"] == 2


def test_a_regression_outranks_a_same_severity_new_finding() -> None:
    """A fix that did not hold is worse news than a fresh problem."""
    history = [
        _cycle("c1", "2026-06-01", {"pricing_offer"}),
        _cycle("c2", "2026-06-08", set()),
        _cycle("c3", "2026-06-13", set()),
    ]
    built = _report_with(history)
    group = next(g for g in built["finding_groups"] if g["theme"] == "pricing_offer")
    assert group["lifecycle_status"] == "regressed"
    assert group["cycles_open"] == 1
    # And it sorts first among the cards.
    assert built["finding_groups"][0]["theme"] == "pricing_offer"


def test_the_accountability_arithmetic_closes_in_the_payload() -> None:
    built = _report_with([_cycle("prior", "2026-06-13", {"pricing_offer", "company_facts"})])
    changed = built["what_changed"]
    assert changed["opening"] == changed["resolved"] + changed["still_open"]
    assert changed["closing"] == changed["still_open"] + changed["new"] + changed["regressed"]
    assert changed["accountability"]


def test_a_flat_cycle_still_says_something() -> None:
    """A weekly product that reports nothing in a flat week loses its reader."""
    built = _report_with(
        [_cycle("prior", "2026-06-13", {"pricing_offer"})],
        prior_engine_counts={"perplexity": (3, 3)},
    )
    movements = built["what_changed"]["movements"]
    assert movements, "flat surfaces must be listed, not omitted"
    assert all(m["phrase"] for m in movements)
    flat = [m for m in movements if m["direction"] == "flat"]
    assert all(m["flat_reason"] for m in flat), "a flat cell must explain itself"


def test_a_thin_prior_cycle_is_not_evidence() -> None:
    """The coverage gate: half a run's cells is not a cycle to compare against."""
    built = _report_with([_cycle("prior", "2026-06-13", set(), coverage=0.4)])
    assert built["what_changed"]["available"] is False
    group = next(g for g in built["finding_groups"] if g["theme"] == "pricing_offer")
    assert group["lifecycle_status"] == "new", "a gated-out cycle cannot make this persisting"


def test_the_theme_rules_version_rides_in_the_payload(report: ReportPayload) -> None:
    assert report["theme_rules_version"]
    assert len(report["theme_rules_version"]) == 16
