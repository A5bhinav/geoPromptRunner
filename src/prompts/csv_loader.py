from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.config import settings
from src.prompts.intent import IntentBucket
from src.prompts.query_set import Query, QuerySet

__all__ = [
    "KNOWN_ENGINES",
    "REQUIRED_CONFIG_KEYS",
    "RunConfig",
    "ValidationIssue",
    "FileProvenance",
    "ConfigItem",
    "FactItem",
    "QueryItem",
    "PreviewData",
    "ParsedAudit",
    "ParseResult",
    "parse_csv_files",
    "build_template_csv",
]

# Canonical engine names the CSV's `config,engines` row may reference. Kept here
# (in the input-contract layer) so both the parser and the API engine registry
# validate against one list. "mock" is a keyless engine for testing the UI end
# to end without spending real API calls.
KNOWN_ENGINES: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "gemini",
        "perplexity",
        "openai_search",
        "anthropic_search",
        "gemini_grounded",
        "google_ai_overviews",
        "mock",
    }
)

# Config keys an audit cannot run without. Everything else has a sane default.
REQUIRED_CONFIG_KEYS: tuple[str, ...] = ("client_name", "category")

# The fixed column schema every uploaded CSV must use.
_COLUMNS: tuple[str, ...] = ("block", "key", "value", "intent", "persona")
_BLOCKS: frozenset[str] = frozenset({"config", "fact", "query"})

# Cell-internal list separator (so commas stay the CSV delimiter).
_LIST_SEP = ";"

_DEFAULT_RUNS_PER_QUERY = settings.DEFAULT_RUNS_PER_QUERY


@dataclass(frozen=True)
class RunConfig:
    """Run settings assembled from the merged ``config`` rows."""

    client_name: str
    category: str
    competitors: list[str]
    engines: list[str]
    runs_per_query: int
    client_domains: list[str]
    judge: bool  # run the LLM judge after the audit (needs OPENAI_API_KEY)


@dataclass(frozen=True)
class ValidationIssue:
    """One reason an upload can't run, tagged with where it came from."""

    message: str
    file: str | None = None  # which uploaded file (None = applies to the merged set)
    block: str | None = None
    key: str | None = None


@dataclass(frozen=True)
class FileProvenance:
    """What one uploaded file contributed to the merged audit."""

    filename: str
    n_config: int
    n_fact: int
    n_query: int

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.n_config:
            parts.append("config")
        if self.n_fact:
            parts.append(f"{self.n_fact} fact{'s' if self.n_fact != 1 else ''}")
        if self.n_query:
            parts.append(f"{self.n_query} quer{'ies' if self.n_query != 1 else 'y'}")
        return " + ".join(parts) if parts else "nothing recognized"


@dataclass(frozen=True)
class ConfigItem:
    key: str
    value: str
    source_file: str


@dataclass(frozen=True)
class FactItem:
    key: str
    value: str
    source_file: str


@dataclass(frozen=True)
class QueryItem:
    """A query row as parsed, before strict QuerySet construction.

    ``valid_intent`` lets the preview flag a bad intent inline without failing
    the whole parse.
    """

    query_id: str
    text: str
    intent: str
    persona: str | None
    source_file: str
    valid_intent: bool


@dataclass(frozen=True)
class PreviewData:
    """Everything the Preview screen renders — present even when invalid."""

    config: list[ConfigItem] = field(default_factory=list)
    facts: list[FactItem] = field(default_factory=list)
    queries: list[QueryItem] = field(default_factory=list)
    provenance: list[FileProvenance] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedAudit:
    """The validated, run-ready audit assembled from the merged CSVs."""

    config: RunConfig
    query_set: QuerySet
    fact_sheet: str | None  # None when no fact rows were supplied
    facts: list[FactItem]
    provenance: list[FileProvenance]


@dataclass(frozen=True)
class ParseResult:
    """Outcome of parsing an upload batch: a preview, any errors, and — when
    clean — the run-ready audit."""

    preview: PreviewData
    errors: list[ValidationIssue]
    audit: ParsedAudit | None

    @property
    def ok(self) -> bool:
        return not self.errors and self.audit is not None


def _split_list(value: str) -> list[str]:
    """Split a ``;``-separated cell into a clean list (empties dropped)."""
    return [part.strip() for part in value.split(_LIST_SEP) if part.strip()]


def _normalize_header(fieldnames: Sequence[str] | None) -> dict[str, str] | None:
    """Map normalized column name -> actual header in the file, or None if the
    required columns are missing."""
    if not fieldnames:
        return None
    lookup = {name.strip().lower(): name for name in fieldnames if name is not None}
    for required in ("block", "key", "value"):
        if required not in lookup:
            return None
    return lookup


def _cell(row: dict[str, str], header: dict[str, str], name: str) -> str:
    """Read a normalized column from a DictReader row (stripped, '' if absent)."""
    actual = header.get(name)
    if actual is None:
        return ""
    value = row.get(actual)
    return value.strip() if value else ""


def _build_fact_sheet(facts: list[FactItem]) -> str | None:
    if not facts:
        return None
    return "\n".join(f"{f.key}: {f.value}" if f.key else f.value for f in facts)


def parse_csv_files(files: list[tuple[str, str]]) -> ParseResult:
    """Parse and merge one or more CSVs into one audit.

    ``files`` is a list of ``(filename, raw_text)`` pairs. Every file uses the
    same ``block,key,value,intent,persona`` schema; rows are routed by ``block``
    and merged across all files (queries accumulate, facts concatenate, config
    keys merge). Validation runs on the merged result. Always returns a
    ``PreviewData`` so the UI can render what parsed even when there are errors;
    ``audit`` is populated only when ``errors`` is empty.
    """
    errors: list[ValidationIssue] = []

    config_items: list[ConfigItem] = []
    facts: list[FactItem] = []
    queries: list[QueryItem] = []
    provenance: list[FileProvenance] = []

    seen_query_ids: dict[str, str] = {}  # query_id -> first file that defined it
    config_values: dict[str, tuple[str, str]] = {}  # key -> (value, first file)

    for filename, raw_text in files:
        reader = csv.DictReader(io.StringIO(raw_text))
        header = _normalize_header(reader.fieldnames)
        if header is None:
            errors.append(
                ValidationIssue(
                    message=(
                        "missing required columns; header must include block, key, value "
                        "(and optionally intent, persona)"
                    ),
                    file=filename,
                )
            )
            provenance.append(FileProvenance(filename, 0, 0, 0))
            continue

        n_config = n_fact = n_query = 0

        for line_no, row in enumerate(reader, start=2):  # line 1 is the header
            block = _cell(row, header, "block").lower()
            key = _cell(row, header, "key")
            value = _cell(row, header, "value")
            intent = _cell(row, header, "intent")
            persona = _cell(row, header, "persona")

            if not block and not key and not value:
                continue  # blank padding row

            if block not in _BLOCKS:
                errors.append(
                    ValidationIssue(
                        message=(
                            f"row {line_no}: unknown block {block or '(empty)'!r}; "
                            "expected one of config, fact, query"
                        ),
                        file=filename,
                        block=block or None,
                    )
                )
                continue

            if block == "config":
                if not key:
                    errors.append(
                        ValidationIssue(
                            message=f"row {line_no}: config row is missing a key",
                            file=filename,
                            block="config",
                        )
                    )
                    continue
                prior = config_values.get(key)
                if prior is not None and prior[0] != value:
                    errors.append(
                        ValidationIssue(
                            message=(
                                f"conflicting config for {key!r}: {prior[0]!r} (in {prior[1]}) "
                                f"vs {value!r} (in {filename})"
                            ),
                            file=filename,
                            block="config",
                            key=key,
                        )
                    )
                    continue
                if prior is None:
                    config_values[key] = (value, filename)
                config_items.append(ConfigItem(key=key, value=value, source_file=filename))
                n_config += 1

            elif block == "fact":
                facts.append(FactItem(key=key, value=value, source_file=filename))
                n_fact += 1

            else:  # query
                if not key:
                    errors.append(
                        ValidationIssue(
                            message=f"row {line_no}: query row is missing a query id (key column)",
                            file=filename,
                            block="query",
                        )
                    )
                    continue
                if not value:
                    errors.append(
                        ValidationIssue(
                            message=f"row {line_no}: query {key!r} has no text (value column)",
                            file=filename,
                            block="query",
                            key=key,
                        )
                    )
                    continue
                if key in seen_query_ids:
                    errors.append(
                        ValidationIssue(
                            message=(
                                f"duplicate query id {key!r} (also defined in "
                                f"{seen_query_ids[key]})"
                            ),
                            file=filename,
                            block="query",
                            key=key,
                        )
                    )
                    continue
                seen_query_ids[key] = filename
                valid_intent = intent in {b.value for b in IntentBucket}
                if not valid_intent:
                    valid = ", ".join(b.value for b in IntentBucket)
                    errors.append(
                        ValidationIssue(
                            message=(
                                f"query {key!r} has unknown intent {intent or '(empty)'!r}; "
                                f"expected one of: {valid}"
                            ),
                            file=filename,
                            block="query",
                            key=key,
                        )
                    )
                queries.append(
                    QueryItem(
                        query_id=key,
                        text=value,
                        intent=intent,
                        persona=persona or None,
                        source_file=filename,
                        valid_intent=valid_intent,
                    )
                )
                n_query += 1

        provenance.append(FileProvenance(filename, n_config, n_fact, n_query))

    merged_config = {k: v for k, (v, _f) in config_values.items()}

    # --- Merged-set validation (runs once, on everything combined) ---
    for required in REQUIRED_CONFIG_KEYS:
        if not merged_config.get(required):
            errors.append(
                ValidationIssue(
                    message=f"missing required config key {required!r} (no file supplied it)",
                    block="config",
                    key=required,
                )
            )

    runs_per_query = _DEFAULT_RUNS_PER_QUERY
    raw_runs = merged_config.get("runs_per_query")
    if raw_runs:
        try:
            runs_per_query = int(raw_runs)
            if runs_per_query < 1:
                raise ValueError
        except ValueError:
            errors.append(
                ValidationIssue(
                    message=f"runs_per_query must be an integer >= 1, got {raw_runs!r}",
                    block="config",
                    key="runs_per_query",
                )
            )
            runs_per_query = _DEFAULT_RUNS_PER_QUERY

    engines = _split_list(merged_config.get("engines", ""))
    unknown_engines = [e for e in engines if e not in KNOWN_ENGINES]
    if unknown_engines:
        valid = ", ".join(sorted(KNOWN_ENGINES))
        errors.append(
            ValidationIssue(
                message=f"unknown engine(s) {', '.join(unknown_engines)}; expected one of: {valid}",
                block="config",
                key="engines",
            )
        )

    if not queries:
        errors.append(
            ValidationIssue(message="no query rows found in any file; an audit needs at least one")
        )

    preview = PreviewData(
        config=config_items,
        facts=facts,
        queries=queries,
        provenance=provenance,
    )

    audit: ParsedAudit | None = None
    if not errors:
        config = RunConfig(
            client_name=merged_config["client_name"],
            category=merged_config["category"],
            competitors=_split_list(merged_config.get("competitors", "")),
            engines=engines,
            runs_per_query=runs_per_query,
            client_domains=_split_list(merged_config.get("client_domains", "")),
            judge=merged_config.get("judge", "").strip().lower() in {"true", "1", "yes"},
        )
        today = datetime.now(UTC).date().isoformat()
        query_set = QuerySet(
            version=merged_config.get("version") or f"csv-{today}",
            locked_at=merged_config.get("locked_at") or today,
            category=config.category,
            client=config.client_name,
            competitors=config.competitors,
            queries=[
                Query(
                    query_id=q.query_id,
                    text=q.text,
                    intent=IntentBucket(q.intent),
                    persona=q.persona,
                )
                for q in queries
            ],
        )
        audit = ParsedAudit(
            config=config,
            query_set=query_set,
            fact_sheet=_build_fact_sheet(facts),
            facts=facts,
            provenance=provenance,
        )

    return ParseResult(preview=preview, errors=errors, audit=audit)


def build_template_csv() -> str:
    """A starter CSV (the Oura example from the UI plan) users can edit."""
    rows: list[list[str]] = [
        list(_COLUMNS),
        ["config", "client_name", "Oura", "", ""],
        ["config", "category", "smart ring", "", ""],
        ["config", "competitors", "Whoop;Ultrahuman;Samsung Galaxy Ring;RingConn", "", ""],
        ["config", "engines", "openai;anthropic;gemini", "", ""],
        ["config", "runs_per_query", "3", "", ""],
        ["config", "client_domains", "ouraring.com", "", ""],
        [
            "fact",
            "identity",
            "Smart ring for sleep/recovery; founded 2013 in Finland; CEO Tom Hale",
            "",
            "",
        ],
        [
            "fact",
            "pricing",
            "Ring 5 $399 base / $499 premium + required $5.99/mo membership",
            "",
            "",
        ],
        [
            "fact",
            "features",
            "Sleep stages, HRV, SpO2, temperature; Ring 5 shipped 2026, 40% smaller than Ring 4",
            "",
            "",
        ],
        ["query", "q1", "best smart ring 2026", "category", "health-conscious consumer"],
        [
            "query",
            "q2",
            "Oura vs Whoop for sleep tracking",
            "comparison",
            "health-conscious consumer",
        ],
        ["query", "q3", "is the Oura Ring worth it", "brand", "health-conscious consumer"],
        [
            "query",
            "q4",
            "how do I improve my sleep with a wearable",
            "problem_aware",
            "health-conscious consumer",
        ],
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return buffer.getvalue()


if __name__ == "__main__":
    template = build_template_csv()
    print("--- template.csv ---")
    print(template)
    result = parse_csv_files([("template.csv", template)])
    print(f"ok={result.ok}  errors={len(result.errors)}")
    for issue in result.errors:
        print(f"  ! {issue.file or '(merged)'}: {issue.message}")
    if result.audit is not None:
        a = result.audit
        print(
            f"client={a.config.client_name!r} category={a.config.category!r} "
            f"engines={a.config.engines} runs={a.config.runs_per_query}"
        )
        print(f"{len(a.query_set.queries)} queries, fact_sheet={'yes' if a.fact_sheet else 'no'}")
        for p in a.provenance:
            print(f"  {p.filename}: {p.summary}")
