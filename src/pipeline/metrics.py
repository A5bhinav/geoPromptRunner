from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from urllib.parse import urlparse

from src.pipeline.parser import MentionType, detect_mention
from src.storage.models import QueryResult

__all__ = [
    "domain_of",
    "is_brand_citation",
    "mention_rate",
    "mention_rate_by_bucket",
    "citation_rate",
    "citation_rate_by_bucket",
    "share_of_voice",
    "top_cited_domains",
]


def domain_of(url: str) -> str:
    """Return the bare host of ``url`` (lowercased, leading ``www.`` stripped)."""
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _normalize_domains(domains: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for d in domains:
        d = d.strip().lower()
        if d.startswith("www."):
            d = d[4:]
        if d:
            out.add(d)
    return out


def is_brand_citation(url: str, client_domains: Iterable[str]) -> bool:
    """True if ``url`` points at one of the client's domains (incl. subdomains)."""
    host = domain_of(url)
    for d in _normalize_domains(client_domains):
        if host == d or host.endswith("." + d):
            return True
    return False


def _answered(results: list[QueryResult]) -> list[QueryResult]:
    """Results where the engine actually returned text (errors/None excluded)."""
    return [r for r in results if r["response"] is not None]


def _by_bucket(results: list[QueryResult]) -> dict[str, list[QueryResult]]:
    buckets: dict[str, list[QueryResult]] = {}
    for r in results:
        buckets.setdefault(r["intent"], []).append(r)
    return buckets


def mention_rate(results: list[QueryResult], brand: str) -> float:
    """Fraction of answered results in which ``brand`` is mentioned.

    Denominator is results with a response (engine failures are missing data,
    not "not mentioned"). Returns 0.0 when nothing was answered.
    """
    answered = _answered(results)
    if not answered:
        return 0.0
    hits = sum(
        1
        for r in answered
        if detect_mention(brand, r["response"] or "") is not MentionType.NOT_MENTIONED
    )
    return hits / len(answered)


def mention_rate_by_bucket(results: list[QueryResult], brand: str) -> dict[str, float]:
    """Mention rate split by intent bucket."""
    return {bucket: mention_rate(rows, brand) for bucket, rows in _by_bucket(results).items()}


def citation_rate(results: list[QueryResult], client_domains: Iterable[str]) -> float:
    """Fraction of answered results that cite/link one of the client's domains."""
    domains = _normalize_domains(client_domains)
    if not domains:
        return 0.0
    answered = _answered(results)
    if not answered:
        return 0.0
    hits = sum(1 for r in answered if any(is_brand_citation(u, domains) for u in r["citations"]))
    return hits / len(answered)


def citation_rate_by_bucket(
    results: list[QueryResult], client_domains: Iterable[str]
) -> dict[str, float]:
    """Citation rate split by intent bucket."""
    return {
        bucket: citation_rate(rows, client_domains) for bucket, rows in _by_bucket(results).items()
    }


def _appearances(results: list[QueryResult], brand: str) -> int:
    return sum(
        1
        for r in _answered(results)
        if detect_mention(brand, r["response"] or "") is not MentionType.NOT_MENTIONED
    )


def share_of_voice(
    results: list[QueryResult], brand: str, competitors: list[str]
) -> dict[str, float]:
    """Each named player's share of all client+competitor mentions.

    A brand mentioned in more answers has a larger share. Returns a mapping of
    brand/competitor name -> share in [0, 1]; shares sum to 1 when anyone was
    mentioned, else all zero.
    """
    names = [brand, *competitors]
    counts = {name: _appearances(results, name) for name in names}
    total = sum(counts.values())
    if total == 0:
        return {name: 0.0 for name in names}
    return {name: counts[name] / total for name in names}


def top_cited_domains(results: list[QueryResult], limit: int = 10) -> list[tuple[str, int]]:
    """Recurring cited domains, ranked — the "sources behind our category"."""
    counter: Counter[str] = Counter()
    for r in results:
        for url in r["citations"]:
            host = domain_of(url)
            if host:
                counter[host] += 1
    return counter.most_common(limit)


if __name__ == "__main__":
    # Mock a small cycle: 3 buckets, brand cited in some, competitors present.
    def _qr(
        qid: str, intent: str, engine: str, run: int, resp: str | None, cites: list[str]
    ) -> QueryResult:
        return QueryResult(
            query_id=qid,
            intent=intent,
            prompt="(mock)",
            engine_name=engine,
            run_index=run,
            response=resp,
            citations=cites,
            timestamp="t",
        )

    results = [
        _qr("cat-01", "category", "openai", 0, "The best CRM is Acme.", ["https://acme.com/crm"]),
        _qr("cat-01", "category", "openai", 1, "Salesforce and HubSpot lead here.", []),
        _qr(
            "cmp-01",
            "comparison",
            "openai",
            0,
            "HubSpot alternatives include Acme.",
            ["https://www.g2.com/acme"],
        ),
        _qr("brd-01", "brand", "anthropic", 0, "Acme is recommended for startups.", []),
        _qr("brd-01", "brand", "anthropic", 1, None, []),  # engine failure -> excluded
    ]
    client_domains = ["acme.com"]
    competitors = ["Salesforce", "HubSpot"]

    print(f"overall mention rate: {mention_rate(results, 'Acme'):.0%}")
    print(
        "mention rate by bucket:",
        {k: f"{v:.0%}" for k, v in mention_rate_by_bucket(results, "Acme").items()},
    )
    print(f"overall citation rate: {citation_rate(results, client_domains):.0%}")
    print(
        "share of voice:",
        {k: f"{v:.0%}" for k, v in share_of_voice(results, "Acme", competitors).items()},
    )
    print("top cited domains:", top_cited_domains(results))
