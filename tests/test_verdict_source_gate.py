"""LIC-T20: a subscription-judged verdict cannot be sold as an API-judged one.

The hole this closes is invisible by construction. The prejudge flow writes into
the PRODUCTION cache keyspace — that is what makes "warm on the subscription,
then judge for $0" work — so downstream a prejudge verdict and an API verdict are
the same table, the same shape, the same report. Nothing distinguished them.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.api import app as api_app
from src.api import identity as identity_mod
from src.api.identity import CallerIdentity
from src.licensing import verdict_source
from src.licensing.verdict_source import check_delivery
from src.pipeline.judge_cache import InMemoryJudgeCache
from src.storage import db


# --- the predicate -----------------------------------------------------------


def test_an_api_only_run_is_deliverable() -> None:
    verdict = check_delivery(["api"], is_platform=False)
    assert verdict.allowed and verdict.reason == ""


def test_a_single_prejudge_verdict_poisons_the_whole_report() -> None:
    """One is enough. A report is delivered whole; there is no partial delivery."""
    verdict = check_delivery(["api", "prejudge"], is_platform=False)
    assert not verdict.allowed
    assert "prejudge" in verdict.reason
    # It has to name the remedy, or an operator will look for a way around it.
    assert "re-judge" in verdict.reason.lower()


def test_opus_dev_is_refused_too() -> None:
    assert not check_delivery(["opus_dev"], is_platform=False).allowed


def test_an_untagged_verdict_is_refused_not_assumed_good() -> None:
    """Verdicts written before tagging existed are `unknown`. The prejudge loop is
    the NORMAL dev workflow here, so an untagged verdict is more likely than not a
    subscription verdict — "cannot prove" has to mean "cannot sell"."""
    for untagged in (None, [], [""], ["not-a-real-source"], 42):
        if untagged in (None, []):
            # No verdicts at all is an UNJUDGED run, which renders fine.
            assert check_delivery(untagged, is_platform=False).allowed
        else:
            assert not check_delivery(untagged, is_platform=False).allowed


def test_a_platform_admin_may_render_anything() -> None:
    """The dev loop depends on rendering exactly these runs."""
    verdict = check_delivery(["prejudge", "opus_dev"], is_platform=True)
    assert verdict.allowed
    # ...and can still SEE what they are looking at.
    assert verdict.sources == ("opus_dev", "prejudge")


def test_normalize_never_upgrades_an_unreadable_tag_to_api() -> None:
    for raw in (None, "", "API!", 7, ["api"], "apii"):
        assert verdict_source.normalize_source(raw) == verdict_source.UNKNOWN
    assert verdict_source.normalize_source(" API ") == verdict_source.API


# --- the cache carries provenance -------------------------------------------


def test_the_cache_records_which_judge_wrote_each_verdict() -> None:
    cache = InMemoryJudgeCache()
    cache.put_many([("k1", ([], [], True))], source=verdict_source.PREJUDGE)
    cache.put_many([("k2", ([], [], True))])  # defaults to api
    assert cache.sources_for(["k1", "k2"]) == {"k1": "prejudge", "k2": "api"}


def test_an_absent_cache_key_has_no_source_rather_than_a_default() -> None:
    """The caller turns "absent" into `unknown`. If this returned `api` for a
    miss, an outage would silently produce sellable-looking verdicts."""
    assert InMemoryJudgeCache().sources_for(["never-written"]) == {}


# --- the API boundary --------------------------------------------------------


class _Run(dict[str, object]):
    pass


@pytest.fixture
def _agency_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A run owned by a company an agency manages, judged partly on prejudge."""
    monkeypatch.setattr(
        db, "get_audit_run", lambda rid: _Run(id=rid, company_id="c1",
                                             verdict_sources=["api", "prejudge"])
    )
    monkeypatch.setattr(
        db,
        "get_company",
        lambda cid: db.Company(id="c1", name="managed.com", slug="managed.com",
                               domain="managed.com", managing_agency_id="org-1"),
    )


def test_an_agency_owned_run_with_a_prejudge_verdict_is_refused_at_render(
    _agency_run: None,
) -> None:
    """The spec's acceptance criterion. Note this fires even though the CALLER is
    a platform admin: the rule is about who the report is FOR."""
    with pytest.raises(HTTPException) as exc:
        api_app._require_deliverable("run-1")
    assert exc.value.status_code == 409
    assert "prejudge" in str(exc.value.detail)


def test_the_same_run_is_refused_through_a_share_link(_agency_run: None) -> None:
    """Checked on the READ, not only at mint: a run can be re-judged from a warm
    notebook after its link has already gone out."""
    with pytest.raises(HTTPException) as exc:
        api_app._require_deliverable("run-1", anonymous_visitor=True)
    assert exc.value.status_code == 409


def test_a_founder_owned_run_still_delivers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The founders' own manual-service clients have no managing agency. Gating
    those would have broken live client links on deploy, for runs that predate
    verdict tagging entirely."""
    monkeypatch.setattr(
        db, "get_audit_run", lambda rid: _Run(id=rid, company_id="c2", verdict_sources=None)
    )
    monkeypatch.setattr(
        db,
        "get_company",
        lambda cid: db.Company(id="c2", name="direct.com", slug="direct.com",
                               domain="direct.com", managing_agency_id=None),
    )
    api_app._require_deliverable("run-2")                             # no raise
    api_app._require_deliverable("run-2", anonymous_visitor=True)     # no raise


def test_an_agency_owned_api_only_run_delivers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate must not block the product it exists to protect."""
    monkeypatch.setattr(
        db, "get_audit_run", lambda rid: _Run(id=rid, company_id="c1", verdict_sources=["api"])
    )
    monkeypatch.setattr(
        db,
        "get_company",
        lambda cid: db.Company(id="c1", name="managed.com", slug="managed.com",
                               domain="managed.com", managing_agency_id="org-1"),
    )
    api_app._require_deliverable("run-3")
    api_app._require_deliverable("run-3", anonymous_visitor=True)


def test_a_non_platform_caller_is_gated_even_on_an_untenanted_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the rule: once LIC-T6 gives agency staff a real identity,
    they are gated regardless of how the run's ownership is recorded."""
    monkeypatch.setattr(
        db, "get_audit_run", lambda rid: _Run(id=rid, company_id=None,
                                              verdict_sources=["prejudge"])
    )
    monkeypatch.setattr(
        identity_mod,
        "current_identity",
        lambda: CallerIdentity(user_id="u1", is_platform_admin=False, organization_id="org-1"),
    )
    with pytest.raises(HTTPException) as exc:
        api_app._require_deliverable("run-4")
    assert exc.value.status_code == 409


def test_the_gate_opens_rather_than_503s_when_storage_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Taking the whole report surface down because one metadata read failed
    trades a real outage for a hypothetical one."""

    def _down(_rid: str) -> None:
        raise db.StorageError("down")

    monkeypatch.setattr(db, "get_audit_run", _down)
    api_app._require_deliverable("run-5")  # no raise
