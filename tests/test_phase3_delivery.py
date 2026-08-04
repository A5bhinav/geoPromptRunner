"""Phase 3 — layering the delivery (audit-packaging P3-T1..T6).

The report is the deliverable; this is everything that gets it in front of
someone. Each piece has one failure it exists to prevent:

- a digest whose subject is identical every week, which trains the reader to skip it;
- a digest with no "what we're doing", which is where recurring reports lose readers;
- a share link that asks for a login, which is what kills forwardability;
- a fix-pack that promises an outcome, which is the FTC-enforcement pattern.
"""

from __future__ import annotations

import pytest

from src.api.digest import build_digest
from src.api.sharing import (
    ShareError,
    mint_share_token,
    verify_share_token,
)
from src.config import settings
from src.pipeline.fixpack import render_finding_brief, render_fix_pack

# --- fixtures -----------------------------------------------------------------


def _group(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "theme": "pricing_offer",
        "theme_label": "Models state the wrong price or offer",
        "title": "Fort's pricing is stated wrongly",
        "severity": "critical",
        "instance_count": 6,
        "engines": ["perplexity"],
        "intents": ["comparison"],
        "occurrence": {
            "observed": 6,
            "total": 6,
            "first_seen_date": "2026-06-13",
            "last_seen_date": "2026-06-13",
            "phrase": "observed in 6 of 6 runs on 2026-06-13",
        },
        "representative_claims": ["The Fort band costs $349."],
        "member_cluster_ids": ["abc"],
        "reality": "$289 pre-order, $319 retail.",
        "evidence": [
            {
                "prompt": "how much is Fort?",
                "engine_name": "perplexity",
                "model_id": "sonar",
                "intent": "comparison",
                "observed_at": "2026-06-13T22:28:18Z",
                "excerpt": "The Fort band costs $349.",
                "reality": "$289 pre-order.",
            }
        ],
        "evidence_total": 6,
        "fix_channel": "owned_site",
        "owner": "Marketing",
        "effort": "S",
        "action": "Publish current Fort pricing as plain text with a last-updated date.",
        "verification": "Check whether next cycle's answers quote the published figure.",
        "priority": 4.0,
        "flag_types": ["wrong_pricing"],
        "lifecycle_status": "new",
        "cycles_open": 1,
        "first_seen_date": "2026-06-13",
    }
    base.update(overrides)
    return base


def _report(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "client_name": "Fort",
        "run_date": "2026-06-20",
        "exec_summary": "Fort appears in 6 of 24 sampled answers (25%) across 4 engines.",
        "comparison_blocked_reason": "",
        "scorecard": {
            "ai_visibility": {
                "successes": 6,
                "n": 24,
                "n_eff": 10.2,
                "rate": 0.25,
                "ci_low": 0.1,
                "ci_high": 0.47,
                "label": "6 of 24 sampled answers (25%)",
            },
            "open_findings": {"themes": 1, "critical": 1, "instances": 6, "by_severity": {}},
        },
        "what_changed": {
            "available": True,
            "accountability": "1 of 2 findings from last cycle is resolved, 1 still open.",
            "opening": 2,
            "resolved": 1,
            "still_open": 1,
            "new": 0,
            "regressed": 0,
            "closing": 1,
            "resolved_all_time": 1,
            "cycles_considered": 2,
            "movements": [
                {
                    "key": "perplexity",
                    "before_successes": 2,
                    "before_n": 12,
                    "after_successes": 6,
                    "after_n": 12,
                    "delta_pp": 33.3,
                    "direction": "up",
                    "phrase": "perplexity: Up from 2 of 12 to 6 of 12 runs",
                    "flat_reason": "",
                }
            ],
            "prior_run_date": "2026-06-13",
        },
        "priority_actions": [_group()],
        "finding_groups": [_group()],
    }
    base.update(overrides)
    return base


# --- P3-T3: the digest, four states -------------------------------------------


def test_the_subject_carries_a_number_and_a_delta_in_every_state() -> None:
    """A subject identical every week trains the reader to skip it — and for a
    format nobody has to visit, the open rate IS the product."""
    states = {
        "improved": _report(),
        "flat": _report(
            what_changed={
                **_report()["what_changed"],  # type: ignore[dict-item]
                "movements": [
                    {
                        "key": "perplexity",
                        "before_successes": 6,
                        "before_n": 12,
                        "after_successes": 6,
                        "after_n": 12,
                        "delta_pp": 0.0,
                        "direction": "flat",
                        "phrase": "perplexity: held steady at 6 of 12 runs",
                        "flat_reason": "the interval includes zero at this sample size",
                    }
                ],
            }
        ),
        "no_prior": _report(what_changed=None, comparison_blocked_reason="no_prior_run"),
        "blocked": _report(what_changed=None, comparison_blocked_reason="query_set_changed"),
    }
    subjects = set()
    for label, report in states.items():
        subject = build_digest(report).subject  # type: ignore[arg-type]
        assert any(ch.isdigit() for ch in subject), f"{label}: no number in the subject"
        assert "Fort" in subject
        assert "Weekly GEO Report" not in subject
        subjects.add(subject)
    assert len(subjects) == len(states), "each state must produce a distinguishable subject"


def test_every_digest_has_a_what_were_doing_section() -> None:
    """Including when the answer is "nothing" — that is where readers are lost."""
    for report in (
        _report(),
        _report(priority_actions=[], finding_groups=[]),
        _report(what_changed=None, priority_actions=[]),
    ):
        digest = build_digest(report)  # type: ignore[arg-type]
        assert "WHAT WE'RE DOING" in digest.text
        section = digest.text.split("WHAT WE'RE DOING")[1].strip()
        assert section.startswith("-"), "the section must never be empty"


def test_a_flat_week_says_it_held_steady() -> None:
    flat = _report(
        what_changed={
            **_report()["what_changed"],  # type: ignore[dict-item]
            "movements": [
                {
                    "key": "perplexity",
                    "before_successes": 6,
                    "before_n": 12,
                    "after_successes": 6,
                    "after_n": 12,
                    "delta_pp": 0.0,
                    "direction": "flat",
                    "phrase": "perplexity: held steady at 6 of 12 runs",
                    "flat_reason": "the interval includes zero",
                }
            ],
        }
    )
    digest = build_digest(flat)  # type: ignore[arg-type]
    assert "held steady" in digest.text
    assert "result, not a missing one" in digest.text


def test_the_digest_never_claims_a_cause_it_cannot_evidence() -> None:
    text = build_digest(_report()).text.lower()  # type: ignore[arg-type]
    for banned in ("because you", "caused by", "thanks to our", "as a result of our"):
        assert banned not in text


def test_the_digest_reads_its_numbers_from_the_payload() -> None:
    """A digest that derives its own figures is a second source of truth, and the
    first thing a client notices is the email disagreeing with the report."""
    digest = build_digest(_report())  # type: ignore[arg-type]
    assert "1 of 2 findings from last cycle is resolved" in digest.text


def test_the_html_escapes_client_content() -> None:
    """Client names are untrusted input and the digest is raw HTML."""
    # exec_summary=None so the CLIENT NAME reaches the headline — with a summary
    # present the name never renders and the test would prove nothing.
    report = _report(client_name="Fort & <script>alert(1)</script>", exec_summary=None)
    html = build_digest(report).html  # type: ignore[arg-type]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


# --- P3-T4: shareable links ---------------------------------------------------


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GEO_API_KEY", "test-signing-key")


def test_a_valid_link_round_trips() -> None:
    token = mint_share_token("run-1")
    assert verify_share_token(token).run_id == "run-1"


def test_an_expired_link_is_refused() -> None:
    token = mint_share_token("run-1", ttl_seconds=1, now=1000)
    with pytest.raises(ShareError, match="expired"):
        verify_share_token(token, now=2000)


def test_a_tampered_link_is_refused() -> None:
    token = mint_share_token("run-1")
    body, _, signature = token.partition(".")
    with pytest.raises(ShareError, match="not valid"):
        verify_share_token(f"{body}x.{signature}")


def test_a_link_signed_with_another_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    token = mint_share_token("run-1")
    monkeypatch.setattr(settings, "GEO_API_KEY", "a-different-key")
    with pytest.raises(ShareError, match="not valid"):
        verify_share_token(token)


def test_a_password_protected_link_needs_the_password() -> None:
    token = mint_share_token("run-1", password="hunter2")
    with pytest.raises(ShareError, match="password"):
        verify_share_token(token)
    with pytest.raises(ShareError, match="password"):
        verify_share_token(token, password="wrong")
    assert verify_share_token(token, password="hunter2").run_id == "run-1"


def test_revocation_is_per_token_not_per_run() -> None:
    """Otherwise "revoke" means "revoke every link anyone was ever sent"."""
    first = mint_share_token("run-1", token_id="t1")
    second = mint_share_token("run-1", token_id="t2")
    revoked = frozenset({"t1"})
    with pytest.raises(ShareError, match="revoked"):
        verify_share_token(first, revoked_ids=revoked)
    assert verify_share_token(second, revoked_ids=revoked).run_id == "run-1"


def test_minting_without_a_signing_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A signature over an empty key is forgeable by anyone who reads the file."""
    monkeypatch.setattr(settings, "GEO_API_KEY", "")
    with pytest.raises(ShareError, match="GEO_API_KEY"):
        mint_share_token("run-1")


def test_the_signature_is_checked_before_anything_else() -> None:
    """A 404-vs-403 split on expiry would let a visitor enumerate run ids."""
    with pytest.raises(ShareError, match="not valid"):
        verify_share_token("garbage.garbage", now=10**12)


# --- P3-T6: the fix pack ------------------------------------------------------


def test_a_brief_carries_everything_needed_to_act_without_the_report() -> None:
    brief = render_finding_brief(_group(), "Fort")  # type: ignore[arg-type]
    for required in (
        "Fort's pricing is stated wrongly",
        "Marketing",
        "observed in 6 of 6 runs",
        "$289 pre-order",
        "how much is Fort?",  # the verbatim prompt
        "sonar",  # the pinned model
        "How we'll check",
    ):
        assert required in brief, required


def test_a_brief_states_verification_as_a_check_not_a_promise() -> None:
    """The FTC pattern against guaranteed-ranking claims applies to this line.

    Scoped to the Fix and How-we'll-check sections. The standing disclaimer at
    the foot of the brief uses "guarantee" in a NEGATION ("is not a guarantee of
    what you will see"), which is the opposite of the claim being banned — a
    whole-document scan would forbid the very sentence that keeps this honest.
    """
    brief = render_finding_brief(_group(), "Fort")  # type: ignore[arg-type]
    actionable = brief.split("### Fix")[1].split("---")[0].lower()
    for banned in ("guarantee", "will rank", "will get you", "ensures", "we'll get you"):
        assert banned not in actionable, banned


def test_a_brief_carries_the_non_reproducibility_framing() -> None:
    brief = render_finding_brief(_group(), "Fort")  # type: ignore[arg-type]
    assert "not a guarantee of what you will see if you ask right now" in brief


def test_a_capped_evidence_list_says_so_in_the_brief() -> None:
    brief = render_finding_brief(_group(evidence_total=94), "Fort")  # type: ignore[arg-type]
    assert "Showing 1 of 94" in brief


def test_the_pack_orders_findings_exactly_as_the_report_does() -> None:
    """The ordering IS a claim; the brief and the card may not disagree."""
    groups = [_group(title="first"), _group(title="second")]
    pack = render_fix_pack(groups, "Fort", "2026-06-20")  # type: ignore[arg-type]
    assert pack.index("first") < pack.index("second")


def test_an_empty_pack_says_nothing_is_open_rather_than_rendering_blank() -> None:
    pack = render_fix_pack([], "Fort")
    assert "No findings are open" in pack


def test_each_block_is_self_contained() -> None:
    """ "Paste one into a ticket without the rest" has to actually be true."""
    pack = render_fix_pack([_group(), _group(title="second")], "Fort")  # type: ignore[arg-type]
    # Split on H2 line-starts only — "### " subheadings inside a brief share the
    # prefix and would shred each block into pieces.
    blocks = [b for b in pack.split("\n## ")[1:]]
    assert len(blocks) == 2
    for block in blocks:
        assert "Owner:" in block and "How we'll check" in block


# --- P3-T1 / P3-T2 / P3-T5: the wiring ----------------------------------------


def test_the_drill_down_endpoint_returns_one_cell_and_404s_cleanly() -> None:
    """Answers are already stored — this is retrieval, not a new measurement.

    It exists because the evidence trail was otherwise reachable only by
    downloading the whole answers.md, and a finding a client cannot check is one
    they have to take on trust.
    """
    from fastapi.testclient import TestClient

    from src.api import runner
    from src.api.app import app
    from src.storage.models import QueryResult

    row = QueryResult(
        query_id="cat-01",
        intent="category",
        prompt="best wearable",
        engine_name="perplexity",
        run_index=0,
        response="an answer",
        citations=[],
        timestamp="2026-06-13T22:28:18Z",
    )
    original = runner.get_answers
    runner.get_answers = lambda run_id: [row] if run_id == "r1" else None  # type: ignore[assignment]
    try:
        client = TestClient(app)
        # The `_api_key` fixture above is autouse, so the API is in KEYED mode for
        # this file — the drill-down sits behind the same gate as every other data
        # route, which is the intended behaviour and worth exercising here.
        auth = {"X-API-Key": "test-signing-key"}
        assert client.get("/audits/r1/answers/cat-01/perplexity/0").status_code == 401

        found = client.get("/audits/r1/answers/cat-01/perplexity/0", headers=auth)
        assert found.status_code == 200
        assert found.json()["prompt"] == "best wearable"
        assert client.get("/audits/r1/answers/cat-01/perplexity/9", headers=auth).status_code == 404
        assert (
            client.get("/audits/nope/answers/cat-01/perplexity/0", headers=auth).status_code == 404
        )
    finally:
        runner.get_answers = original  # type: ignore[assignment]


def test_the_filter_controls_never_print() -> None:
    """A filtered PDF that looks complete is the same bug as a section that
    silently vanishes — the controls are screen-only and the count says so."""
    from tests.report_surface import render_source

    view = render_source()
    assert 'className="no-print flex flex-wrap items-center gap-2"' in view
    assert "Showing {visible.length} of {groups.length} findings" in view


def test_the_severity_bar_counts_what_is_visible() -> None:
    """A summary that ignores the filter is a summary of a different report."""
    from tests.report_surface import render_source

    assert "<SeveritySummaryBar counts={bySeverity} />" in render_source()


def test_the_pdf_endpoint_delegates_to_the_p1_t7_worker() -> None:
    """One renderer, not two. The worker owns every Chromium-specific trap."""
    from pathlib import Path

    app_src = (Path(__file__).resolve().parents[1] / "src" / "api" / "app.py").read_text()
    assert "render-report-pdf.mjs" in app_src
    # Exit 2 is "Chromium missing" — an environment problem, not a failed render.
    assert "returncode == 2" in app_src


def test_a_missing_browser_degrades_to_the_print_ready_page() -> None:
    """The repo's convention: a missing browser costs you the PDF, not the
    deliverable. A 503 leaves an operator with nothing while a perfectly good
    printable page sits one URL away."""
    from pathlib import Path

    app_src = (Path(__file__).resolve().parents[1] / "src" / "api" / "app.py").read_text()
    assert "X-PDF-Fallback" in app_src
    assert "?mode=print" in app_src
    assert "status_code=302" in app_src


# --- P3-T1 / P3-T4: the pieces a human actually touches -----------------------


def test_the_finding_card_can_fetch_the_full_answer() -> None:
    """The endpoint alone is not the feature — it needs a caller.

    A client who doubts an excerpt needs the sentence IN CONTEXT, and the
    alternative was downloading the whole answers export.
    """
    from tests.report_surface import render_source

    view = render_source()
    assert "function AnswerPanel" in view
    assert "getAnswerCell(" in view
    assert "<mark" in view, "the flagged claim must be highlighted in context"


def test_the_shared_link_has_a_page_a_human_can_open() -> None:
    """A shareable link nobody can click is not a shareable link."""
    from pathlib import Path

    page = Path(__file__).resolve().parents[1] / "web" / "app" / "shared" / "[token]" / "page.tsx"
    assert page.exists(), "there is no /shared/[token] route"
    source = page.read_text()
    assert "getSharedReport(" in source
    # No `runId` PROP: the Judge / re-judge / export controls are gated on it, so
    # a shared viewer cannot reach anything that spends money. Asserted on the
    # JSX prop rather than the word, which appears in the comment explaining it.
    assert "<ReportView report={report} />" in source
    assert "runId={" not in source


def test_the_shared_client_sends_no_api_key() -> None:
    """The token IS the auth — attaching a key would make it a login wall."""
    from pathlib import Path

    api = (Path(__file__).resolve().parents[1] / "web" / "lib" / "api.ts").read_text()
    shared = api.split("export async function getSharedReport")[1].split("export async function")[0]
    assert "authHeaders" not in shared
