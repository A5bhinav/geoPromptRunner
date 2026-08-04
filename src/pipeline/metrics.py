from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from src.pipeline.parser import MentionType, detect_mention
from src.storage.models import QueryResult

__all__ = [
    "domain_of",
    "is_brand_citation",
    "CellVerdict",
    "Coverage",
    "coverage",
    "coverage_by_bucket",
    "coverage_by_engine",
    "MIN_RUNS_FOR_STABILITY",
    "Stability",
    "stability_from",
    "cell_agreement",
    "stability",
    "stability_by_engine",
    "brand_verdicts",
    "mention_rate",
    "mention_rate_by_bucket",
    "citation_rate",
    "citation_rate_by_bucket",
    "share_of_voice",
    "competitive_ranking",
    "top_cited_domains",
    "LosingQuery",
    "losing_queries",
]


@lru_cache(maxsize=8192)
def domain_of(url: str) -> str:
    """Return the bare host of ``url`` (lowercased, leading ``www.`` stripped).

    Cached: the same citation URLs are parsed many times across a report (brand
    citation checks, per-bucket rates, top-domain ranking), so memoize the parse.
    """
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


# --- Coverage: how much was actually measured -----------------------------------
#
# `_rate` deliberately excludes unanswered cells from its denominator, which keeps
# every rate honest but makes a rate of 0.0 ambiguous: it reads the same whether a
# brand was absent from ten answers or whether no answer ever arrived. Coverage is
# the missing companion — it reports the denominator itself, so a caller can tell
# "absent" from "never measured" and render "—" instead of "0%".
#
# This exists because a real run (e186c524, 2026-07-28) had an engine whose model
# was 404 for every call. Nothing in the rates was wrong; the report simply could
# not say that one third of its cells had no data behind them.


@dataclass(frozen=True)
class Coverage:
    """How many cells returned an answer, out of how many were attempted."""

    answered_cells: int
    total_cells: int

    @property
    def is_measured(self) -> bool:
        """True when at least one cell returned an answer.

        A rate over ``is_measured is False`` carries no information and must not be
        rendered as a number — a brand cannot be absent from an answer that never
        existed.
        """
        return self.answered_cells > 0


def coverage(verdicts: list[CellVerdict]) -> Coverage:
    """Coverage across ``verdicts`` (a cell counts as answered if any run answered)."""
    return Coverage(
        answered_cells=sum(1 for v in verdicts if v.hit is not None),
        total_cells=len(verdicts),
    )


def coverage_by_bucket(results: list[QueryResult], brand: str) -> dict[str, Coverage]:
    """Coverage split by intent bucket, keyed to match ``mention_rate_by_bucket``.

    Takes ``brand`` only to reuse the same cell aggregation the rates use; coverage
    itself is brand-independent (whether a cell answered has nothing to do with who
    was named in it).
    """
    return {
        bucket: coverage(vs) for bucket, vs in _by_bucket(brand_verdicts(results, brand)).items()
    }


def coverage_by_engine(results: list[QueryResult]) -> dict[str, Coverage]:
    """Coverage per engine, computed from stored rows.

    The report-side twin of the live per-engine counter in ``src/api/runner.py``:
    because it works from persisted results, a run rebuilt from storage after a
    restart reports the same honesty as one watched live.
    """
    out: dict[str, tuple[int, int]] = {}
    for (_query_id, engine_name), rows in _cells(results).items():
        answered, total = out.get(engine_name, (0, 0))
        out[engine_name] = (
            answered + (1 if any(r["response"] is not None for r in rows) else 0),
            total + 1,
        )
    return {name: Coverage(answered_cells=a, total_cells=t) for name, (a, t) in out.items()}


# --- Stability: did the verdict reproduce across the cell's repeat runs? --------
#
# `_verdicts` already collapses a cell by majority and keeps `hit_runs`/`answered_runs`
# — but every consumer reads only the collapsed `hit`, so a 3-of-5 coin flip and a 5-of-5
# unanimous read render identically. That was survivable while every engine ran at
# ENGINE_TEMPERATURE=0. It isn't now: `openai` is pinned to a model that rejects the
# parameter outright and samples at its default temperature (see openai_engine.MODEL),
# so one surface in every run is measurably noisier than the rest and nothing said so.
#
# Same lesson Coverage taught: a cell with a single answered run LOOKS unanimous while
# carrying no reproducibility information at all. Such cells are excluded from the
# denominator rather than counted as stable — `is_measured` is False, not 100%.

#: Below this many answered runs, a cell says nothing about reproducibility.
MIN_RUNS_FOR_STABILITY = 2


@dataclass(frozen=True)
class Stability:
    """How reproducibly a set of cells returned the same verdict across their runs."""

    repeated_cells: int  # cells with >= MIN_RUNS_FOR_STABILITY answered runs
    split_cells: int  # of those, the ones whose runs disagreed
    mean_agreement: float  # mean modal agreement across the repeated cells

    @property
    def is_measured(self) -> bool:
        """True when at least one cell ran enough times to say anything.

        False means *not measured* — never "perfectly stable". A cycle at
        RUNS_PER_QUERY=1 produces no reproducibility evidence at all, and rendering
        that as 100% agreement would invent confidence out of a missing measurement.
        """
        return self.repeated_cells > 0

    @property
    def split_rate(self) -> float:
        """Share of repeated cells whose runs disagreed. 0.0 when nothing was repeated
        — guard on ``is_measured`` before rendering this."""
        return self.split_cells / self.repeated_cells if self.repeated_cells else 0.0


def stability_from(runs: Iterable[tuple[int, int]]) -> Stability:
    """Pure core: ``(modal_runs, answered_runs)`` pairs → a ``Stability``.

    Each caller decides what "agreeing" means for its own verdict — the binary
    mention read here, the (present, prominence, framing) label on the judge path —
    and this rolls the pairs up identically for both, so the two paths can never
    report stability on different scales.
    """
    agreements = [m / n for m, n in runs if n >= MIN_RUNS_FOR_STABILITY]
    if not agreements:
        return Stability(repeated_cells=0, split_cells=0, mean_agreement=0.0)
    return Stability(
        repeated_cells=len(agreements),
        split_cells=sum(1 for a in agreements if a < 1.0),
        mean_agreement=sum(agreements) / len(agreements),
    )


def cell_agreement(verdict: CellVerdict) -> float | None:
    """Modal agreement of one cell's binary read, or None if it wasn't repeated.

    Modal, not hit-share: a cell that read "absent" in all five runs is perfectly
    stable at 5/5, even though ``hit_runs`` is 0.
    """
    if verdict.answered_runs < MIN_RUNS_FOR_STABILITY:
        return None
    return _modal_runs(verdict) / verdict.answered_runs


def _modal_runs(verdict: CellVerdict) -> int:
    return max(verdict.hit_runs, verdict.answered_runs - verdict.hit_runs)


def stability(verdicts: list[CellVerdict]) -> Stability:
    """Reproducibility of ``verdicts`` across their repeat runs."""
    return stability_from((_modal_runs(v), v.answered_runs) for v in verdicts)


def stability_by_engine(results: list[QueryResult], brand: str) -> dict[str, Stability]:
    """Stability per engine — the split that motivates the metric.

    Engines no longer share a sampling regime (one surface cannot take a temperature),
    so a single run-wide agreement number would average a deterministic engine against
    a sampling one and describe neither.
    """
    by_engine: dict[str, list[CellVerdict]] = {}
    for v in brand_verdicts(results, brand):
        by_engine.setdefault(v.engine_name, []).append(v)
    return {name: stability(vs) for name, vs in by_engine.items()}


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


def citation_verdicts(
    results: list[QueryResult], client_domains: Iterable[str]
) -> list[CellVerdict]:
    """Per-cell "did this cite the client" verdicts — the counts behind the rate.

    The public twin of what ``citation_rate`` averages. A report may not render a
    rate without its denominator, and dividing then multiplying back by an
    assumed denominator is how a 7-of-12 becomes a 58% that rounds to a different
    count than the one in the table beside it.
    """
    domains = _normalize_domains(client_domains)
    if not domains:
        return []
    return _verdicts(results, _citation_predicate(domains))


def citation_rate(results: list[QueryResult], client_domains: Iterable[str]) -> float:
    """Fraction of (query, engine) cells that cite one of the client's domains."""
    verdicts = citation_verdicts(results, client_domains)
    return _rate(verdicts) if verdicts else 0.0


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


def competitive_ranking(results: list[QueryResult], brands: list[str]) -> list[tuple[str, float]]:
    """Each brand's mention rate, ranked highest first — the standing table."""
    return sorted(
        ((brand, mention_rate(results, brand)) for brand in brands),
        key=lambda x: x[1],
        reverse=True,
    )


@dataclass(frozen=True)
class LosingQuery:
    """A (query, engine) cell where the client is absent but a competitor isn't."""

    query_id: str
    intent: str
    engine_name: str
    competitors_present: list[str]


def losing_queries(
    results: list[QueryResult], brand: str, competitors: list[str]
) -> list[LosingQuery]:
    """The exact (query, engine) cells the client loses — absent while a rival shows.

    The methodology's connective tissue: never present a rate in isolation, name
    the specific queries it's costing them. A cell is "losing" when the client is
    not mentioned (per the aggregated verdict) but at least one competitor is.
    """
    brand_by_cell = {(v.query_id, v.engine_name): v for v in brand_verdicts(results, brand)}
    competitor_verdicts = {
        comp: {(v.query_id, v.engine_name): v for v in brand_verdicts(results, comp)}
        for comp in competitors
    }

    losses: list[LosingQuery] = []
    for cell, bv in brand_by_cell.items():
        if bv.hit:  # client present -> not a loss
            continue
        present = [
            comp
            for comp in competitors
            if (cv := competitor_verdicts[comp].get(cell)) is not None and cv.hit
        ]
        if present:
            losses.append(
                LosingQuery(
                    query_id=cell[0],
                    intent=bv.intent,
                    engine_name=cell[1],
                    competitors_present=present,
                )
            )
    return sorted(losses, key=lambda x: (x.query_id, x.engine_name))


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
        _qr(
            "cat-01",
            "category",
            "openai",
            0,
            "The best budgeting app is Acme.",
            ["https://acme.com/budgeting"],
        ),
        _qr("cat-01", "category", "openai", 1, "Acme is a solid option.", []),
        _qr("cat-01", "category", "openai", 2, "YNAB and Monarch Money lead here.", []),
        _qr(
            "cmp-01",
            "comparison",
            "openai",
            0,
            "Monarch Money alternatives include Acme.",
            ["https://www.trustpilot.com/review/acme.com"],
        ),
        _qr("brd-01", "brand", "anthropic", 0, None, []),  # engine failure -> excluded
    ]
    competitors = ["YNAB", "Monarch Money"]
    print(f"mention rate (Acme): {mention_rate(results, 'Acme'):.0%}")
    print("by bucket:", {k: f"{v:.0%}" for k, v in mention_rate_by_bucket(results, "Acme").items()})
    print(f"citation rate: {citation_rate(results, ['acme.com']):.0%}")
    print(
        "share of voice:",
        {k: f"{v:.0%}" for k, v in share_of_voice(results, "Acme", competitors).items()},
    )
    print("top cited domains:", top_cited_domains(results))
