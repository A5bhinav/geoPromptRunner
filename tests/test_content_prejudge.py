"""Chunk 2: the content prejudge (dump -> page -> inject) and its key parity — the
keys it writes are the exact ones the live ContentJudge looks up."""

from __future__ import annotations

import json

from scripts.content_judge_via_workflow import _load_in, main
from src.audit.checks.content_judge import CONTENT_CHECKS, content_cache_key
from src.audit.checks.content_judge_cache import InMemoryContentJudgeCache
from src.config import settings
from src.storage import db


def test_content_prejudge_end_to_end_and_key_parity(monkeypatch, tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    # One shared in-memory content notebook across dump / inject (they each build one
    # via make_content_judge_cache — point them at the same instance).
    shared = InMemoryContentJudgeCache()
    monkeypatch.setattr(
        "src.audit.checks.content_judge_cache.make_content_judge_cache", lambda: shared
    )
    fake_pages = [
        {"normalized_url": "https://x/pricing", "extracted_text": "Fort is a budgeting app."},
        {"normalized_url": "https://x/empty", "extracted_text": None},  # skipped (no text)
    ]
    monkeypatch.setattr(db, "get_site_audit_pages", lambda _rid: fake_pages)

    in_path = tmp_path / "c.in.json"
    raws_path = tmp_path / "c.raws.json"

    # 1) dump — reads pages, computes keys, renders one prompt per page.
    assert main(["dump", "run-1", "--out", str(in_path)]) == 0
    capsys.readouterr()  # clear
    d = _load_in(str(in_path))
    pages = d["pages"]
    assert isinstance(pages, list) and len(pages) == 1  # empty-text page dropped
    page = pages[0]
    text = str(page["text"])
    # dump's per-check key IS content_cache_key (the live-judge lookup) — parity.
    key_by_check = {c["check_id"]: c["key"] for c in page["checks"]}
    for c in CONTENT_CHECKS:
        assert key_by_check[c.check_id] == content_cache_key(settings.JUDGE_MODEL, c, text)

    # 2) page — prints a combined prompt + the check ids a subagent judges.
    assert main(["page", str(in_path), "0"]) == 0
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert set(printed["check_ids"]) == {c.check_id for c in CONTENT_CHECKS}
    assert "Page text:" in printed["prompt"] and "budgeting app" in printed["prompt"]

    # 3) inject — fabricate the subagent's per-page verdicts and write them.
    verdicts = [
        {
            "check_id": c.check_id,
            "sub_answers": [
                {"key": q.key, "reasoning": "r", "evidence_quote": "", "answer": "unknown"}
                for q in c.sub_questions
            ],
        }
        for c in CONTENT_CHECKS
    ]
    raws_path.write_text(json.dumps({"pages": [{"page_index": 0, "verdicts": verdicts}]}))
    assert main(["inject", str(in_path), str(raws_path)]) == 0

    # Every (page, check) is now warm under the key the live judge looks up.
    keys = [content_cache_key(settings.JUDGE_MODEL, c, text) for c in CONTENT_CHECKS]
    got = shared.get_many(keys)
    assert {v.check_id for v in got.values()} == {c.check_id for c in CONTENT_CHECKS}


def test_inject_skips_bad_entries(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    shared = InMemoryContentJudgeCache()
    monkeypatch.setattr(
        "src.audit.checks.content_judge_cache.make_content_judge_cache", lambda: shared
    )
    # Minimal in.json with one page + one real check.
    check = CONTENT_CHECKS[0]
    text = "some text"
    key = content_cache_key(settings.JUDGE_MODEL, check, text)
    in_path = tmp_path / "c.in.json"
    in_path.write_text(
        json.dumps(
            {
                "run_id": "r",
                "model": settings.JUDGE_MODEL,
                "pages": [
                    {"url": "u", "text": text, "checks": [{"check_id": check.check_id, "key": key}]}
                ],
            }
        )
    )
    raws = tmp_path / "raws.json"
    # null page, out-of-range index, unknown check id — all skipped, none crash.
    raws.write_text(
        json.dumps(
            {
                "pages": [
                    None,
                    {"page_index": 9, "verdicts": []},
                    {"page_index": 0, "verdicts": [{"check_id": "not_a_check", "sub_answers": []}]},
                ]
            }
        )
    )
    assert main(["inject", str(in_path), str(raws)]) == 0
    assert shared.get_many([key]) == {}  # nothing valid was stored
