"""Phase 5 — the commercial layer, and the four ways it could be dishonest.

Each task here has a test the spec singles out, and in every case the test is
about a *refusal*: what the free scan must not send, what the tier must not
meter, what the reference panel must not be called, what the white-label must not
leak.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.pipeline.free_scan import (
    FREE_SCAN_ENGINES,
    MAX_FREE_SCAN_COST_USD,
    FreeScanTooExpensive,
    check_free_scan_cost,
    gate_findings,
)
from src.pipeline.reference_panel import (
    MIN_PANEL_N,
    PanelMember,
    build_band,
    panel_label,
    place_client,
)
from src.pipeline.tiers import Tier, check_run, limits_for

REPO = Path(__file__).resolve().parents[1]

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_PY_DOCSTRING = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
_PY_COMMENT = re.compile(r"^\s*#.*$", re.MULTILINE)


def _css_rules(path: Path) -> str:
    """A stylesheet with its comments removed.

    Every scan below is about what the sheet DECLARES. The comments necessarily
    name the banned things in order to explain why they are banned ("no
    Cormorant", "handing a tenant a red"), so matching prose would make the rules
    unwritable — the same reason tests/report_surface.py strips comments.
    """
    return _CSS_COMMENT.sub("", path.read_text())


def _python_code(path: Path) -> str:
    """Python with docstrings and comments removed, for the same reason."""
    return _PY_COMMENT.sub("", _PY_DOCSTRING.sub("", path.read_text()))


# --- P5-T1: the free scan -----------------------------------------------------


def test_a_free_scan_cannot_exceed_its_own_cap() -> None:
    """MAX_AUDIT_COST_USD (25) guards a paying client's bill. An anonymous form
    with a 25-dollar ceiling is a denial-of-wallet waiting to happen."""
    with pytest.raises(FreeScanTooExpensive):
        check_free_scan_cost(15, FREE_SCAN_ENGINES, cost_per_call_usd=1.0)


def test_the_free_scan_cap_is_far_below_the_audit_cap() -> None:
    from src.config import settings

    assert MAX_FREE_SCAN_COST_USD < settings.MAX_AUDIT_COST_USD / 10


def test_a_free_scan_is_refused_before_any_call() -> None:
    """Discovering an overspend during the calls means it already happened, and
    the person who triggered it is not identifiable."""
    with pytest.raises(FreeScanTooExpensive):
        check_free_scan_cost(400, FREE_SCAN_ENGINES, cost_per_call_usd=0.001)
    with pytest.raises(FreeScanTooExpensive):
        check_free_scan_cost(10, ("a", "b", "c", "d"), cost_per_call_usd=0.001)


def test_a_scan_within_its_limits_is_allowed() -> None:
    estimate = check_free_scan_cost(15, FREE_SCAN_ENGINES, cost_per_call_usd=0.02)
    assert estimate.calls == 30
    assert estimate.estimated_usd <= MAX_FREE_SCAN_COST_USD


def test_specific_claims_are_absent_from_the_ungated_response() -> None:
    """The spec's own test. Gating, not hiding: a payload that carries the claims
    and marks them private has already sent them, and the first person to open
    dev tools has the audit for free."""
    secret = "The Fort band costs $349."
    public = gate_findings(
        client_name="Fort",
        findings=[{"claim": secret, "prompt": "Fort vs Whoop?", "engine_name": "perplexity"}],
        checks_run=15,
        checks_with_a_problem=6,
    )
    serialized = repr(public)
    assert secret not in serialized
    assert "$349" not in serialized
    assert "perplexity" not in serialized
    assert "Fort vs Whoop" not in serialized


def test_the_ungated_response_still_carries_the_count_with_its_denominator() -> None:
    public = gate_findings(
        client_name="Fort", findings=[1, 2, 3], checks_run=15, checks_with_a_problem=6
    )
    assert "6 of 15" in public["headline"]
    assert public["findings_withheld"] == 2  # three found, one teased


def test_a_scan_that_measured_nothing_says_so_rather_than_claiming_zero() -> None:
    public = gate_findings(
        client_name="Fort", findings=[], checks_run=0, checks_with_a_problem=0
    )
    assert "nothing could be checked" in public["headline"]


# --- P5-T5: tier enforcement --------------------------------------------------


@pytest.mark.parametrize("tier", [t.value for t in Tier])
def test_every_tier_enforces_all_three_dimensions(tier: str) -> None:
    caps = limits_for(tier)
    breaches = check_run(
        tier,
        n_prompts=caps.max_prompts + 1,
        n_engines=caps.max_engines + 1,
        n_competitors=caps.max_competitors + 1,
    )
    assert {b.dimension for b in breaches} == {"prompts", "surfaces", "competitors"}


def test_a_run_inside_its_limits_passes() -> None:
    caps = limits_for(Tier.TRACK.value)
    assert (
        check_run(
            Tier.TRACK.value,
            n_prompts=caps.max_prompts,
            n_engines=caps.max_engines,
            n_competitors=caps.max_competitors,
            runs_per_query=caps.max_runs_per_query,
        )
        == []
    )


def test_all_breaches_are_returned_not_just_the_first() -> None:
    """A caller who fixes one limit and resubmits only to hit the next has been
    made to guess at the shape of their own plan three times."""
    assert len(check_run(Tier.FREE.value, n_prompts=99, n_engines=9, n_competitors=9)) >= 3


def test_an_unknown_tier_fails_closed() -> None:
    assert limits_for("enterprise-platinum") == limits_for(Tier.FREE.value)


def test_no_code_path_gates_on_refresh_frequency() -> None:
    """The spec's explicit test, and the point of the whole module.

    Cadence is a cost-to-you metric masquerading as a value metric; every
    competitor gives daily refresh away; and metering it creates the trap where a
    flat week reads as wasted money — in a product whose value proposition
    includes "held steady at 8 of 12 for the third week".
    """
    code = _python_code(REPO / "src" / "pipeline" / "tiers.py")
    for banned in ("cadence", "interval", "refresh", "per_week", "per_day", "last_run"):
        assert banned not in code.lower(), f"tiers.py meters {banned}"


def test_seats_are_unlimited_at_every_tier() -> None:
    """A team that has to ration logins does not share the report, and a report
    nobody reads does not get renewed."""
    assert all(limits_for(t.value).unlimited_seats for t in Tier)


def test_runs_per_cycle_are_never_capped_below_the_recovery_case() -> None:
    """A client must never be locked out of recovering from a failed run — the
    run they cannot repeat is the one that produced a broken report."""
    for tier in Tier:
        assert limits_for(tier.value).max_runs_per_query >= 1


# --- P5-T4: the reference panel -----------------------------------------------


def _panel(n: int, vertical: str = "wearables") -> list[PanelMember]:
    return [
        PanelMember(f"Brand {i}", vertical, successes=i, n=12, run_date="2026-06-13")
        for i in range(1, n + 1)
    ]


def test_a_segment_below_the_floor_renders_no_band_at_all() -> None:
    """The spec's suppression test. Four brands is four brands wearing a
    distribution's clothes."""
    band = build_band("wearables", _panel(MIN_PANEL_N - 1))
    assert band["available"] is False
    assert band["p50"] == 0.0
    assert str(MIN_PANEL_N) in band["caution"]


def test_a_suppressed_band_still_says_how_many_it_had() -> None:
    """"We have four" is information; a blank space is a rendering bug."""
    assert "4 reference brands" in build_band("wearables", _panel(4))["caution"]


def test_a_thin_but_usable_band_renders_with_a_stated_caution() -> None:
    band = build_band("wearables", _panel(7))
    assert band["available"] is True
    assert "indicative" in band["caution"]


def test_a_full_band_carries_no_caution() -> None:
    assert build_band("wearables", _panel(12))["caution"] == ""


def test_the_label_never_contains_benchmark() -> None:
    """The spec's own test. Famous brands score systematically higher than a
    median client — calling their distribution a peer benchmark tells a client
    they are behind their peers when what they are behind is Nike."""
    band = build_band("wearables", _panel(12))
    for text in (band["label"], panel_label("wearables"), place_client(band, 0.5)):
        assert "benchmark" not in text.lower()
    assert "reference panel" in band["label"].lower()


def test_the_panel_module_never_emits_the_word_benchmark() -> None:
    """Every string this module can PRODUCE. The docstring says "peer benchmark"
    in order to forbid it, which is prose, not output."""
    code = _python_code(REPO / "src" / "pipeline" / "reference_panel.py")
    for literal in re.findall(r'"([^"]*)"', code) + re.findall(r"'([^']*)'", code):
        assert "benchmark" not in literal.lower()


def test_the_band_reports_percentiles_and_never_a_mean() -> None:
    """At n=15–30 one viral brand drags a mean somewhere no panel member sits."""
    code = _python_code(REPO / "src" / "pipeline" / "reference_panel.py")
    assert "statistics.mean" not in code
    assert "statistics.fmean" not in code

    band = build_band("wearables", _panel(12))
    assert band["p25"] <= band["p50"] <= band["p75"]


def test_every_band_discloses_its_n_and_window_inline() -> None:
    """A percentile with no sample size beside it is the same failure as a rate
    with no denominator."""
    band = build_band("wearables", _panel(12))
    placement = place_client(band, 0.5)
    assert f"n={band['n']}" in placement
    assert band["window"] in placement


def test_the_client_is_excluded_from_its_own_panel() -> None:
    """Comparing a brand to a distribution it is inside flatters or punishes it
    by its own contribution."""
    members = [*_panel(6), PanelMember("Fort", "wearables", 12, 12, "2026-06-13", True)]
    assert build_band("wearables", members)["n"] == 6


def test_placement_is_descriptive_not_a_verdict() -> None:
    band = build_band("wearables", _panel(12))
    placement = place_client(band, 0.1).lower()
    for judgement in ("underperform", "failing", "poor", "behind your peers"):
        assert judgement not in placement


# --- P5-T3: the white-label skin ----------------------------------------------


def test_the_two_skins_are_genuinely_different() -> None:
    """An abstraction with exactly one implementation is not an abstraction.

    `NEUTRAL` pointed at `.sable` for a whole phase, so every "white-label"
    render shipped Sable's navy, Sable's Cormorant wordmark and Sable's masthead
    accent under a different name.
    """
    brand = (REPO / "web" / "lib" / "brand.ts").read_text()
    sable_class = re.search(r"SABLE[^}]*?themeClass:\s*\"([a-z-]+)\"", brand, re.S)
    neutral_class = re.search(r"NEUTRAL[^}]*?themeClass:\s*\"([a-z-]+)\"", brand, re.S)
    assert sable_class and neutral_class
    assert sable_class.group(1) != neutral_class.group(1)


def test_the_neutral_skin_exists_and_is_loaded() -> None:
    assert (REPO / "web" / "styles" / "neutral.css").exists()
    assert "neutral.css" in (REPO / "web" / "app" / "layout.tsx").read_text()


def test_the_neutral_skin_drops_the_display_serif() -> None:
    """A second typeface is a brand decision, and a resold artifact should not be
    making one on the agency's behalf."""
    assert "cormorant" not in _css_rules(REPO / "web" / "styles" / "neutral.css").lower()


def test_the_neutral_skin_leaks_no_sable_hex() -> None:
    neutral = _css_rules(REPO / "web" / "styles" / "neutral.css").lower()
    for sable_hex in ("#0e2340", "#12325c", "#697585", "#b2b7bc", "#f2f1ec", "#7fa6d9"):
        assert sable_hex not in neutral, f"the white-label skin ships Sable's {sable_hex}"


def test_the_neutral_skin_keeps_the_single_hue_severity_ramp() -> None:
    """Not Sable-specific styling — the packaging rule. Handing a tenant a red
    quietly re-opens the "colour alone" failure the ramp exists to prevent."""
    neutral = _css_rules(REPO / "web" / "styles" / "neutral.css")
    for level in ("--sev-critical", "--sev-high", "--sev-medium", "--sev-low"):
        assert level in neutral
    # No alert hue anywhere: nothing in the red/amber/green families.
    for alert in ("red", "crimson", "#f00", "#ff0000", "amber", "green"):
        assert alert not in neutral.lower()


def test_the_accent_stays_scoped_to_navy_in_both_skins() -> None:
    """Same structural guarantee as Sable's: an accent used on a paper ground
    resolves to nothing and fails visibly, rather than passing review."""
    neutral = _css_rules(REPO / "web" / "styles" / "neutral.css")
    accent_lines = [ln for ln in neutral.splitlines() if "--on-navy-accent" in ln]
    assert accent_lines
    block_start = neutral.index("--on-navy-accent")
    assert ".on-navy" in neutral[:block_start]
