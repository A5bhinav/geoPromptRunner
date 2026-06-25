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
