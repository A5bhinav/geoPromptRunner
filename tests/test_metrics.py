from __future__ import annotations

from src.pipeline import metrics
from src.storage.models import QueryResult


def _qr(
    qid: str,
    engine: str,
    run: int,
    resp: str | None,
    *,
    intent: str = "category",
    cites: list[str] | None = None,
) -> QueryResult:
    return QueryResult(
        query_id=qid,
        intent=intent,
        prompt="(mock)",
        engine_name=engine,
        run_index=run,
        response=resp,
        citations=cites or [],
        timestamp="t",
    )


def test_runs_aggregate_to_majority_per_cell() -> None:
    # Mentioned in 2 of 3 runs -> the single cell counts as a hit.
    results = [
        _qr("q1", "openai", 0, "Acme is great."),
        _qr("q1", "openai", 1, "Acme works well."),
        _qr("q1", "openai", 2, "YNAB only."),
    ]
    assert metrics.mention_rate(results, "Acme") == 1.0

    # Mentioned in only 1 of 3 -> below majority -> not a hit.
    results = [
        _qr("q1", "openai", 0, "Acme is great."),
        _qr("q1", "openai", 1, "YNAB only."),
        _qr("q1", "openai", 2, "Monarch Money only."),
    ]
    assert metrics.mention_rate(results, "Acme") == 0.0


def test_failed_runs_are_excluded_not_counted_as_misses() -> None:
    # One cell fully failed (no data) -> excluded from the denominator.
    results = [
        _qr("q1", "openai", 0, "Acme is great."),
        _qr("q2", "openai", 0, None),
        _qr("q2", "openai", 1, None),
    ]
    assert metrics.mention_rate(results, "Acme") == 1.0  # 1 of 1 answered cell


def test_share_of_voice_dedups_runs() -> None:
    # Acme in all 3 runs of one query = one appearance, not three.
    results = [
        _qr("q1", "openai", 0, "Acme and YNAB."),
        _qr("q1", "openai", 1, "Acme and YNAB."),
        _qr("q1", "openai", 2, "Acme and YNAB."),
    ]
    sov = metrics.share_of_voice(results, "Acme", ["YNAB"])
    assert sov == {"Acme": 0.5, "YNAB": 0.5}


def test_mention_rate_by_bucket() -> None:
    results = [
        _qr("c1", "openai", 0, "Acme is here.", intent="category"),
        _qr("b1", "openai", 0, "YNAB only.", intent="brand"),
    ]
    by_bucket = metrics.mention_rate_by_bucket(results, "Acme")
    assert by_bucket == {"category": 1.0, "brand": 0.0}


def test_coverage_separates_absent_from_never_measured() -> None:
    # The case that motivated Coverage: `mention_rate` is 0.0 for BOTH of these, so
    # the rate alone cannot tell a real absence from a surface that never answered.
    absent = [
        _qr("q1", "openai", 0, "YNAB only."),
        _qr("q2", "openai", 0, "Monarch only."),
    ]
    never_measured = [
        _qr("q1", "openai", 0, None),
        _qr("q2", "openai", 0, None),
    ]
    assert metrics.mention_rate(absent, "Acme") == 0.0
    assert metrics.mention_rate(never_measured, "Acme") == 0.0

    cov_absent = metrics.coverage(metrics.brand_verdicts(absent, "Acme"))
    cov_none = metrics.coverage(metrics.brand_verdicts(never_measured, "Acme"))
    assert (cov_absent.answered_cells, cov_absent.total_cells) == (2, 2)
    assert cov_absent.is_measured is True
    assert (cov_none.answered_cells, cov_none.total_cells) == (0, 2)
    assert cov_none.is_measured is False


def test_coverage_by_engine_flags_a_dead_engine() -> None:
    # A 404'd model writes a row per attempted cell but answers nothing (run
    # e186c524). Coverage must report it as unmeasured while leaving live engines
    # untouched.
    results = [
        _qr("q1", "perplexity", 0, "Acme is great."),
        _qr("q2", "perplexity", 0, "Acme again."),
        _qr("q1", "openai_search", 0, None),
        _qr("q2", "openai_search", 0, None),
    ]
    by_engine = metrics.coverage_by_engine(results)
    assert by_engine["perplexity"].is_measured is True
    assert by_engine["openai_search"].is_measured is False
    assert by_engine["openai_search"].total_cells == 2


def test_coverage_by_bucket_keys_match_mention_rate_by_bucket() -> None:
    # The two must be joinable by bucket key, or the report can't pair a rate with
    # the denominator behind it.
    results = [
        _qr("c1", "openai", 0, "Acme is here.", intent="category"),
        _qr("b1", "openai", 0, None, intent="brand"),
    ]
    rates = metrics.mention_rate_by_bucket(results, "Acme")
    cov = metrics.coverage_by_bucket(results, "Acme")
    assert set(rates) == set(cov)
    assert cov["category"].is_measured is True
    assert cov["brand"].is_measured is False


def test_citation_rate_and_domains() -> None:
    results = [
        _qr("q1", "openai", 0, "See Acme.", cites=["https://www.acme.com/budgeting"]),
        _qr("q2", "openai", 0, "See others.", cites=["https://reddit.com/x"]),
    ]
    assert metrics.citation_rate(results, ["acme.com"]) == 0.5
    assert metrics.top_cited_domains(results) == [("acme.com", 1), ("reddit.com", 1)]


def test_domain_helpers() -> None:
    assert metrics.domain_of("https://WWW.Acme.com/path") == "acme.com"
    assert metrics.is_brand_citation("https://blog.acme.com/x", ["acme.com"]) is True
    assert metrics.is_brand_citation("https://acme.io/x", ["acme.com"]) is False


# --- Stability (repeat-run reproducibility) ------------------------------------


def test_stability_separates_a_split_cell_from_a_unanimous_one() -> None:
    # q1: mentioned in 2 of 3 runs -> a split read that majority-vote hides.
    # q2: absent from all 3 -> unanimous, even though hit_runs is 0.
    results = [
        _qr("q1", "openai", 0, "Acme is great."),
        _qr("q1", "openai", 1, "Acme works well."),
        _qr("q1", "openai", 2, "YNAB only."),
        _qr("q2", "openai", 0, "YNAB only."),
        _qr("q2", "openai", 1, "YNAB only."),
        _qr("q2", "openai", 2, "YNAB only."),
    ]
    s = metrics.stability(metrics.brand_verdicts(results, "Acme"))
    assert s.is_measured is True
    assert s.repeated_cells == 2
    assert s.split_cells == 1  # only q1
    assert s.mean_agreement == (2 / 3 + 1.0) / 2


def test_single_run_cells_are_not_measured_rather_than_perfectly_stable() -> None:
    # One run per cell looks unanimous but compares nothing — the trap Coverage
    # taught us. is_measured must be False, NOT 100% agreement.
    results = [_qr("q1", "openai", 0, "Acme is great."), _qr("q2", "openai", 0, "YNAB only.")]
    s = metrics.stability(metrics.brand_verdicts(results, "Acme"))
    assert s.is_measured is False
    assert s.repeated_cells == 0
    assert s.mean_agreement == 0.0


def test_unanswered_runs_are_excluded_from_the_stability_denominator() -> None:
    # An engine failure is missing data, not a disagreement.
    results = [
        _qr("q1", "openai", 0, "Acme is great."),
        _qr("q1", "openai", 1, "Acme works well."),
        _qr("q1", "openai", 2, None),
    ]
    v = metrics.brand_verdicts(results, "Acme")[0]
    assert v.answered_runs == 2
    assert metrics.cell_agreement(v) == 1.0
    assert metrics.stability([v]).split_cells == 0


def test_stability_is_reported_per_engine() -> None:
    results = [
        # openai splits 1 of 2; anthropic agrees in both runs.
        _qr("q1", "openai", 0, "Acme is great."),
        _qr("q1", "openai", 1, "YNAB only."),
        _qr("q1", "anthropic", 0, "Acme is great."),
        _qr("q1", "anthropic", 1, "Acme works well."),
    ]
    by_engine = metrics.stability_by_engine(results, "Acme")
    assert by_engine["openai"].split_cells == 1
    assert by_engine["anthropic"].split_cells == 0
    assert by_engine["anthropic"].mean_agreement == 1.0


def test_build_report_surfaces_per_engine_stability() -> None:
    from src.api.reports import build_report
    from src.pipeline.orchestrator import AuditOutcome

    outcome = AuditOutcome(
        run_id=None,
        client_name="Acme",
        client_domains=["acme.com"],
        competitors=["Rival"],
        query_set_version="v1",
        runs_per_query=2,
        results=[
            _qr("q1", "openai", 0, "Acme is great."),
            _qr("q1", "openai", 1, "Rival only."),  # split
            _qr("q1", "anthropic", 0, "Acme is great."),
            _qr("q1", "anthropic", 1, "Acme works well."),  # agrees
        ],
    )
    rows = {r["engine_name"]: r for r in build_report(outcome)["stability"]}
    assert rows["openai"]["split_cells"] == 1
    assert rows["anthropic"]["split_cells"] == 0
    assert rows["anthropic"]["mean_agreement"] == 1.0


def test_build_report_omits_stability_when_nothing_was_repeated() -> None:
    from src.api.reports import build_report
    from src.pipeline.orchestrator import AuditOutcome

    outcome = AuditOutcome(
        run_id=None,
        client_name="Acme",
        client_domains=["acme.com"],
        competitors=["Rival"],
        query_set_version="v1",
        runs_per_query=1,
        results=[_qr("q1", "openai", 0, "Acme is great.")],
    )
    # No row at all — an unrepeated engine must not render as 100% agreement.
    assert build_report(outcome)["stability"] == []
