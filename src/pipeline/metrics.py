from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlparse

from src.pipeline.parser import MentionType, detect_mention
from src.storage.models import QueryResult

__all__ = [
    "domain_of",
    "is_brand_citation",
    "CellVerdict",
    "brand_verdicts",
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


# --- Per-(query, engine) aggregation ------------------------------------------
#
# A query is run multiple times per cycle to average out LLM nondeterminism, so
# the unit of measurement is the (query, engine) *cell*, not the individual run.
# Each cell collapses its runs to a single verdict by majority of the runs that
# actually returned a response. Engine failures (None) are missing data, not a
# "no" — they're excluded from the denominator.


@dataclass(frozen=True)
class CellVerdict:
    """Aggregated outcome for one query on one engine across its runs."""

    query_id: str
    engine_name: str
    intent: str
    hit: bool | None  # None = no run returned a response (no data)
    hit_runs: int
    answered_runs: int


def _cells(results: list[QueryResult]) -> dict[tuple[str, str], list[QueryResult]]:
    cells: dict[tuple[str, str], list[QueryResult]] = {}
    for r in results:
        cells.setdefault((r["query_id"], r["engine_name"]), []).append(r)
    return cells


def _verdicts(
    results: list[QueryResult], predicate: Callable[[QueryResult], bool]
) -> list[CellVerdict]:
    """Collapse runs to one verdict per (query, engine) by majority of answered runs."""
    verdicts: list[CellVerdict] = []
    for (query_id, engine_name), rows in _cells(results).items():
        answered = [r for r in rows if r["response"] is not None]
        hits = sum(1 for r in answered if predicate(r))
        # Majority = present in at least half of the answered runs (rounded up).
        hit = None if not answered else hits * 2 >= len(answered)
        verdicts.append(
            CellVerdict(
                query_id=query_id,
                engine_name=engine_name,
                intent=rows[0]["intent"],
                hit=hit,
                hit_runs=hits,
                answered_runs=len(answered),
            )
        )
    return verdicts


def _rate(verdicts: list[CellVerdict]) -> float:
    answered = [v for v in verdicts if v.hit is not None]
    if not answered:
        return 0.0
    return sum(1 for v in answered if v.hit) / len(answered)


def _by_bucket(verdicts: list[CellVerdict]) -> dict[str, list[CellVerdict]]:
    buckets: dict[str, list[CellVerdict]] = {}
    for v in verdicts:
        buckets.setdefault(v.intent, []).append(v)
    return buckets


def _mention_predicate(brand: str) -> Callable[[QueryResult], bool]:
    def pred(r: QueryResult) -> bool:
        return detect_mention(brand, r["response"] or "") is not MentionType.NOT_MENTIONED

    return pred


def _citation_predicate(domains: set[str]) -> Callable[[QueryResult], bool]:
    def pred(r: QueryResult) -> bool:
        return any(is_brand_citation(u, domains) for u in r["citations"])

    return pred


def brand_verdicts(results: list[QueryResult], brand: str) -> list[CellVerdict]:
    """Per-(query, engine) mention verdict for ``brand`` (runs aggregated)."""
    return _verdicts(results, _mention_predicate(brand))


def mention_rate(results: list[QueryResult], brand: str) -> float:
    """Fraction of (query, engine) cells in which ``brand`` is mentioned."""
    return _rate(brand_verdicts(results, brand))


def mention_rate_by_bucket(results: list[QueryResult], brand: str) -> dict[str, float]:
    """Mention rate split by intent bucket."""
    return {bucket: _rate(vs) for bucket, vs in _by_bucket(brand_verdicts(results, brand)).items()}


def citation_rate(results: list[QueryResult], client_domains: Iterable[str]) -> float:
    """Fraction of (query, engine) cells that cite one of the client's domains."""
    domains = _normalize_domains(client_domains)
    if not domains:
        return 0.0
    return _rate(_verdicts(results, _citation_predicate(domains)))


def citation_rate_by_bucket(
    results: list[QueryResult], client_domains: Iterable[str]
) -> dict[str, float]:
    """Citation rate split by intent bucket."""
    domains = _normalize_domains(client_domains)
    if not domains:
        return {}
    return {
        bucket: _rate(vs)
        for bucket, vs in _by_bucket(_verdicts(results, _citation_predicate(domains))).items()
    }


def share_of_voice(
    results: list[QueryResult], brand: str, competitors: list[str]
) -> dict[str, float]:
    """Each named player's share of all client+competitor mentions.

    Counts one appearance per (query, engine) cell — a brand mentioned across
    all three runs of one query counts once, not three times — so share isn't
    biased toward whichever queries happened to answer most.
    """
    names = [brand, *competitors]
    counts = {name: sum(1 for v in brand_verdicts(results, name) if v.hit) for name in names}
    total = sum(counts.values())
    if total == 0:
        return {name: 0.0 for name in names}
    return {name: counts[name] / total for name in names}


def top_cited_domains(results: list[QueryResult], limit: int = 10) -> list[tuple[str, int]]:
    """Recurring cited domains, ranked — the "sources behind our category".

    A domain is counted once per (query, engine) cell, not once per run, so the
    ranking reflects how broadly a source recurs rather than run repetition.
    """
    counter: Counter[str] = Counter()
    for rows in _cells(results).values():
        seen: set[str] = set()
        for r in rows:
            for url in r["citations"]:
                host = domain_of(url)
                if host:
                    seen.add(host)
        counter.update(seen)
    return counter.most_common(limit)


if __name__ == "__main__":

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

    # cat-01 on openai: Acme mentioned in 2 of 3 runs -> cell counts as a hit once.
    results = [
        _qr("cat-01", "category", "openai", 0, "The best CRM is Acme.", ["https://acme.com/crm"]),
        _qr("cat-01", "category", "openai", 1, "Acme is a solid option.", []),
        _qr("cat-01", "category", "openai", 2, "Salesforce and HubSpot lead here.", []),
        _qr(
            "cmp-01",
            "comparison",
            "openai",
            0,
            "HubSpot alternatives include Acme.",
            ["https://www.g2.com/acme"],
        ),
        _qr("brd-01", "brand", "anthropic", 0, None, []),  # engine failure -> excluded
    ]
    competitors = ["Salesforce", "HubSpot"]
    print(f"mention rate (Acme): {mention_rate(results, 'Acme'):.0%}")
    print("by bucket:", {k: f"{v:.0%}" for k, v in mention_rate_by_bucket(results, "Acme").items()})
    print(f"citation rate: {citation_rate(results, ['acme.com']):.0%}")
    print(
        "share of voice:",
        {k: f"{v:.0%}" for k, v in share_of_voice(results, "Acme", competitors).items()},
    )
    print("top cited domains:", top_cited_domains(results))
