from __future__ import annotations

from src.prompts.csv_loader import (
    build_template_csv,
    parse_csv_files,
)

_HEADER = "block,key,value,intent,persona"


def _csv(*rows: str) -> str:
    """Build a CSV body from the fixed header plus the given comma-rows."""
    return "\n".join([_HEADER, *rows]) + "\n"


# A clean single-file audit (the Oura example from the UI plan).
_OURA = """block,key,value,intent,persona
config,client_name,Oura,,
config,category,smart ring,,
config,competitors,Whoop;Ultrahuman;RingConn,,
config,engines,openai;anthropic;gemini,,
config,runs_per_query,3,,
config,client_domains,ouraring.com,,
fact,identity,"Smart ring for sleep/recovery; founded 2013 in Finland",,
fact,pricing,"Ring 5 $399 base + $5.99/mo membership",,
query,q1,best smart ring 2026,category,health-conscious consumer
query,q2,Oura vs Whoop for sleep tracking,comparison,sleep-conscious consumer
query,q3,is the Oura Ring worth it,brand,first-time shopper
"""


def test_parses_clean_single_file() -> None:
    result = parse_csv_files([("oura.csv", _OURA)])
    assert result.ok, [e.message for e in result.errors]
    audit = result.audit
    assert audit is not None
    assert audit.config.client_name == "Oura"
    assert audit.config.category == "smart ring"
    assert audit.config.competitors == ["Whoop", "Ultrahuman", "RingConn"]
    assert audit.config.engines == ["openai", "anthropic", "gemini"]
    assert audit.config.runs_per_query == 3
    assert audit.config.client_domains == ["ouraring.com"]
    assert len(audit.query_set.queries) == 3
    assert audit.fact_sheet is not None
    assert "founded 2013" in audit.fact_sheet
    assert "Ring 5 $399" in audit.fact_sheet


def test_intents_map_onto_buckets() -> None:
    result = parse_csv_files([("oura.csv", _OURA)])
    assert result.audit is not None
    intents = {q.intent.value for q in result.audit.query_set.queries}
    assert intents == {"category", "comparison", "brand"}
    personas = {q.persona for q in result.audit.query_set.queries}
    assert "sleep-conscious consumer" in personas


def test_split_files_merge_into_one_audit() -> None:
    run_file = _csv(
        "config,client_name,Oura,,",
        "config,category,smart ring,,",
        "config,engines,openai,,",
        "query,q1,best smart ring 2026,category,",
        "query,q2,Oura vs Whoop,comparison,",
    )
    facts_file = _csv(
        'fact,identity,"Smart ring for sleep",,',
        "fact,pricing,$399,,",
    )
    result = parse_csv_files([("run.csv", run_file), ("facts.csv", facts_file)])
    assert result.ok, [e.message for e in result.errors]
    assert result.audit is not None
    assert len(result.audit.query_set.queries) == 2
    assert result.audit.fact_sheet is not None
    assert "Smart ring for sleep" in result.audit.fact_sheet
    by_name = {p.filename: p for p in result.audit.provenance}
    assert by_name["run.csv"].n_query == 2
    assert by_name["facts.csv"].n_fact == 2
    assert by_name["run.csv"].n_fact == 0


def test_merge_is_order_independent() -> None:
    a = _csv("config,client_name,X,,", "config,category,c,,", "query,q1,t,brand,")
    b = _csv('fact,identity,"hello",,')
    forward = parse_csv_files([("a.csv", a), ("b.csv", b)])
    backward = parse_csv_files([("b.csv", b), ("a.csv", a)])
    assert forward.ok and backward.ok
    assert forward.audit is not None and backward.audit is not None
    assert forward.audit.fact_sheet == backward.audit.fact_sheet


def test_duplicate_query_id_across_files_errors() -> None:
    a = _csv("config,client_name,X,,", "config,category,c,,", "query,q1,first,brand,")
    b = _csv("query,q1,second,brand,")
    result = parse_csv_files([("a.csv", a), ("b.csv", b)])
    assert not result.ok
    assert any("duplicate query id" in e.message for e in result.errors)


def test_conflicting_config_key_errors() -> None:
    a = _csv("config,client_name,Oura,,", "config,category,c,,", "query,q1,t,brand,")
    b = _csv("config,client_name,Whoop,,")
    result = parse_csv_files([("a.csv", a), ("b.csv", b)])
    assert not result.ok
    assert any("conflicting config" in e.message for e in result.errors)


def test_same_config_value_twice_is_fine() -> None:
    a = _csv("config,client_name,Oura,,", "config,category,c,,", "query,q1,t,brand,")
    b = _csv("config,client_name,Oura,,")
    result = parse_csv_files([("a.csv", a), ("b.csv", b)])
    assert result.ok, [e.message for e in result.errors]


def test_bad_intent_errors_but_still_previews() -> None:
    text = _csv("config,client_name,X,,", "config,category,c,,", "query,q1,t,bogus,")
    result = parse_csv_files([("a.csv", text)])
    assert not result.ok
    assert any("unknown intent" in e.message for e in result.errors)
    assert len(result.preview.queries) == 1
    assert result.preview.queries[0].valid_intent is False


def test_missing_required_config_errors() -> None:
    text = _csv("config,category,c,,", "query,q1,t,brand,")
    result = parse_csv_files([("a.csv", text)])
    assert not result.ok
    assert any("client_name" in e.message for e in result.errors)


def test_no_queries_errors() -> None:
    text = _csv("config,client_name,X,,", "config,category,c,,", "fact,identity,hi,,")
    result = parse_csv_files([("a.csv", text)])
    assert not result.ok
    assert any("no query rows" in e.message for e in result.errors)


def test_no_facts_is_allowed() -> None:
    text = _csv("config,client_name,X,,", "config,category,c,,", "query,q1,t,brand,")
    result = parse_csv_files([("a.csv", text)])
    assert result.ok
    assert result.audit is not None
    assert result.audit.fact_sheet is None


def test_unknown_engine_errors() -> None:
    text = _csv(
        "config,client_name,X,,",
        "config,category,c,,",
        "config,engines,openai;notreal,,",
        "query,q1,t,brand,",
    )
    result = parse_csv_files([("a.csv", text)])
    assert not result.ok
    assert any("unknown engine" in e.message for e in result.errors)


def test_bad_runs_per_query_errors() -> None:
    text = _csv(
        "config,client_name,X,,",
        "config,category,c,,",
        "config,runs_per_query,zero,,",
        "query,q1,t,brand,",
    )
    result = parse_csv_files([("a.csv", text)])
    assert not result.ok
    assert any("runs_per_query" in e.message for e in result.errors)


def test_missing_columns_errors() -> None:
    result = parse_csv_files([("bad.csv", "foo,bar\n1,2\n")])
    assert not result.ok
    assert any("missing required columns" in e.message for e in result.errors)


def test_template_round_trips_clean() -> None:
    template = build_template_csv()
    result = parse_csv_files([("template.csv", template)])
    assert result.ok, [e.message for e in result.errors]
    assert result.audit is not None
    assert result.audit.config.client_name == "Oura"
    assert len(result.audit.query_set.queries) == 4
