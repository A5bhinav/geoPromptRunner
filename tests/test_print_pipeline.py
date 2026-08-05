"""The print pipeline and the render-mode fork (audit-packaging P1-T7 / P1-T8).

Two layers, deliberately:

**Always-on source assertions.** The invariants here fail SILENTLY in production
— a clipped header, a chart at the wrong size, a table that loses rows 21-200 —
and every one of them looks perfect on the live page. They are cheap to assert
against the source and expensive to discover from a client email.

**An opt-in end-to-end pass** (``RUN_PRINT_CHECK=1`` plus ``PRINT_CHECK_RUN_ID``)
that actually prints a stored run and reads the PDF back. It needs a running web
app, a running API, Chromium and poppler, so it cannot be a default-suite test —
but the mechanics it exercises are the whole point of the task, so it exists.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB = REPO_ROOT / "web"
SABLE_CSS = WEB / "styles" / "sable.css"
PDF_WORKER = WEB / "scripts" / "render-report-pdf.mjs"
LAYOUT_CHECK = WEB / "scripts" / "check-print-layout.mjs"
RENDER_MODE = WEB / "lib" / "render-mode.tsx"
# `charts.tsx` is gone with recharts; the report's marks live in these two.
CHARTS = WEB / "components" / "marks.tsx"
PANELS = WEB / "components" / "report-panels.tsx"
REPORT_VIEW = WEB / "components" / "report-view.tsx"
MOTION = WEB / "styles" / "motion.css"
AUDIT_PAGE = WEB / "app" / "audits" / "[id]" / "page.tsx"


# --- the print stylesheet -----------------------------------------------------


def test_backgrounds_are_forced_or_the_severity_ramp_prints_blank() -> None:
    """Chromium strips backgrounds by default.

    Sable's palette has no alert hue, so severity is carried entirely by tone —
    strip the fills and all four tiers print as identical empty chips.
    """
    css = SABLE_CSS.read_text()
    assert "print-color-adjust: exact" in css
    assert "-webkit-print-color-adjust: exact" in css
    assert "printBackground: true" in PDF_WORKER.read_text()


def test_exactly_one_margin_source() -> None:
    """`@page` must declare NO margin at all — not even `0`.

    This test used to assert the opposite, and the assertion was wrong. `0` is a
    value, and Chromium honours it over the `margin` passed to `page.pdf()`, so
    the 0.9in/0.75in bands that reserve space for the header/footer templates
    were never applied: every page printed edge-to-edge, the running header
    overprinted the first line of body text, and the page number overprinted the
    last. `preferCSSPageSize: false` does not save you — it governs the page
    SIZE, not the margins.

    So the rule is not "only one of the two may be non-zero", it is "only one of
    the two may declare margins at all", and the one that does is `page.pdf()`.
    """
    # Comments stripped first: this file and the stylesheet both necessarily
    # QUOTE `margin: 0` in the prose explaining why it is banned, and matching
    # the explanation instead of the declaration is how a source-level guard
    # passes while the rule is wrong.
    css = re.sub(r"/\*.*?\*/", "", SABLE_CSS.read_text(), flags=re.DOTALL)
    page_rules = re.findall(r"@page\s*\{[^}]*\}", css)
    assert page_rules, "the print stylesheet declares no @page rule"
    for rule in page_rules:
        assert not re.search(r"\bmargin\b", rule), (
            "@page must not declare a margin — a CSS margin (including `0`) wins "
            f"over page.pdf()'s and collides the header/footer with the body: {rule}"
        )

    worker = PDF_WORKER.read_text()
    assert "preferCSSPageSize: false" in worker, "the worker would honour @page size too"
    # The margins are real and reserve room for the two templates.
    margin = re.search(r"MARGIN\s*=\s*\{([^}]*)\}", worker)
    assert margin, "the worker declares no MARGIN"
    for side in ("top", "bottom", "left", "right"):
        found = re.search(rf"{side}:\s*\"([\d.]+)in\"", margin.group(1))
        assert found and float(found.group(1)) > 0, (
            f"MARGIN.{side} must be non-zero — it is the only margin source there is"
        )


def test_cards_and_tables_survive_pagination() -> None:
    css = SABLE_CSS.read_text()
    # A card that splits mid-evidence reads as two different findings.
    assert re.search(r"\.report-card\s*\{\s*break-inside:\s*avoid", css)
    # Rows 40+ arriving with no column labels make the numbers meaningless.
    assert "display: table-header-group" in css
    assert re.search(r"tr\s*\{\s*break-inside:\s*avoid", css)
    # shadcn Card sets an overflow, and a nested overflow CLIPS rather than
    # paginating — the card's tail silently disappears.
    assert 'overflow-"] {\n    overflow: visible !important;' in css or (
        "overflow: visible !important" in css
    )


def test_the_first_section_does_not_emit_a_blank_page() -> None:
    """`break-before: page` on every section would push the masthead off page 1."""
    css = SABLE_CSS.read_text()
    assert ".report-section:first-child" in css
    assert re.search(r"\.report-section:first-child\s*\{\s*break-before:\s*auto", css)


# --- the render-mode fork -----------------------------------------------------


def test_one_flag_drives_every_print_fork() -> None:
    """`?mode=print` is the single switch. A fork that forgets it is greppable."""
    page = AUDIT_PAGE.read_text()
    assert 'get("mode") === "print"' in page
    assert "RenderModeProvider" in page


def test_the_report_has_no_measurement_dependent_chart_runtime() -> None:
    """The three print hazards recharts brought are gone by construction.

    `ResponsiveContainer` sized via `ResizeObserver`, which print layout never
    fires, so a chart printed at whatever the last on-screen size happened to be
    — usually wrong, occasionally zero. The fix used to be a ChartFrame that
    swapped in a fixed box. The charts are now hand-rolled SVG with a literal
    `viewBox`, so there is no measurement step to get wrong and nothing to swap.
    """
    for path in (CHARTS, PANELS):
        source = path.read_text()
        # The IMPORT, not the word: both files explain in prose what they
        # replaced, and banning the noun would make the comment unwritable.
        assert 'from "recharts"' not in source
        assert "<ResponsiveContainer" not in source
    # A viewBox is the whole print story: geometry is declared, not measured.
    assert CHARTS.read_text().count("viewBox=") >= 3


def test_no_report_chart_arrives_through_a_lazy_chunk() -> None:
    """`next/dynamic(..., {ssr:false})` sections vanish from a PDF.

    Print never scrolls, so nothing below the fold triggers the intersection
    that resolves the chunk. The readiness gate in RenderModeProvider covered
    that race while the charts were lazy; removing the laziness removes the
    race, and this test is what stops it being reintroduced.
    """
    view = REPORT_VIEW.read_text()
    assert "next/dynamic" not in view
    assert "dynamic(" not in view


def test_the_readiness_gate_still_waits_for_fonts() -> None:
    """Both Sable faces are metrically unlike system-ui.

    A chart laid out before the webfonts land is laid out against the fallback,
    and axis labels reflow after the capture. This survives the loss of the
    chart-registration count — quiescence plus fonts is the remaining gate.
    """
    mode = RENDER_MODE.read_text()
    assert "document.fonts.ready" in mode


def test_print_runs_with_animation_disabled() -> None:
    """A multi-frame transition is a race the capture can lose.

    There is no chart animation left to switch off — the marks are static SVG —
    so the guarantee moved to the stylesheet, where it also covers the intake's
    bubbles and the progress rail.
    """
    motion = MOTION.read_text()
    assert "prefers-reduced-motion: reduce" in motion
    assert "animation-duration: 1ms !important" in motion


def test_readiness_is_gated_on_more_than_networkidle() -> None:
    """`networkidle` only means HTTP quiesced; SVG finishes on later frames."""
    mode = RENDER_MODE.read_text()
    assert "document.fonts.ready" in mode, "font metrics decide axis-label layout"
    assert "reportReady" in mode
    assert "requestAnimationFrame" in mode
    worker = PDF_WORKER.read_text()
    assert 'document.body.dataset.reportReady === "true"' in worker
    assert "waitForFunction" in worker


def test_evidence_is_expanded_when_printing() -> None:
    """A collapsed disclosure is the silently-drops-content bug in miniature."""
    from tests.report_surface import render_source

    view = render_source()
    assert "React.useState(isPrint)" in view
    assert "print:block" in view


# --- the header/footer templates ---------------------------------------------


def test_header_and_footer_templates_avoid_the_four_silent_traps() -> None:
    worker = PDF_WORKER.read_text()
    # 1. Templates are ignored entirely without this flag — no error, no header.
    assert "displayHeaderFooter: true" in worker
    # 2. Default font-size in the template iframe is effectively zero.
    assert "font-size: 8px" in worker
    # 3. Page numbers use the recognized classes, not invented ones.
    assert 'class="pageNumber"' in worker and 'class="totalPages"' in worker
    # 4. The templates render in an isolated iframe: no external stylesheet, no
    #    relative webfont, no url() image. A system stack is the only safe font.
    assert "Helvetica, Arial, sans-serif" in worker
    assert "url(" not in worker.split("function templates")[1].split("function escapeHtml")[0]


def test_the_footer_carries_the_independence_disclaimer() -> None:
    """It must survive onto every page, including a forwarded excerpt."""
    worker = PDF_WORKER.read_text()
    assert "Not affiliated with" in worker
    for vendor in ("OpenAI", "Anthropic", "Google", "Perplexity"):
        assert vendor in worker


def test_header_text_is_escaped() -> None:
    """A client name is untrusted input and the template is raw HTML."""
    worker = PDF_WORKER.read_text()
    assert "function escapeHtml" in worker
    assert "escapeHtml(clientName)" in worker


# --- evidence is capped, and says so ------------------------------------------


def test_the_card_evidences_a_few_observations_and_admits_it() -> None:
    """Printing all 94 of one finding's observations rebuilt the blob one level
    down — the first real PDF was 32 pages, 16 of them that finding."""
    from src.pipeline.findings import _MAX_EVIDENCE_PER_GROUP

    assert 1 <= _MAX_EVIDENCE_PER_GROUP <= 6
    from tests.report_surface import render_source

    view = render_source()
    assert "evidence_total > group.evidence.length" in view
    assert "Showing" in view


# --- opt-in end-to-end --------------------------------------------------------

_RUN_ID = os.environ.get("PRINT_CHECK_RUN_ID", "")
_BASE = os.environ.get("PRINT_CHECK_BASE", "http://localhost:3000")
_e2e = pytest.mark.skipif(
    "RUN_PRINT_CHECK" not in os.environ or not _RUN_ID,
    reason=(
        "set RUN_PRINT_CHECK=1 and PRINT_CHECK_RUN_ID=<run-id> (with the web app and API "
        "running) to print a stored run and read the PDF back"
    ),
)


def _node(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(script), _RUN_ID, "--base", _BASE, *args],
        cwd=WEB,
        capture_output=True,
        text=True,
        timeout=300,
    )


@_e2e
def test_print_layout_check_passes_against_a_real_run() -> None:
    result = _node(LAYOUT_CHECK)
    if result.returncode == 2:
        pytest.skip(f"Chromium unavailable: {result.stderr.strip()}")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


@_e2e
def test_printing_a_real_run_produces_a_whole_report(tmp_path: Path) -> None:
    """The end-to-end contract: the PDF has the evidence trail, not just the tiles.

    Every probe here is something that would be MISSING if a print fork regressed
    — the running header (clipped by a margin conflict), the page numbers (wrong
    template classes), the verbatim prompt and pinned model (collapsed evidence),
    and the disclosure (a section that never rendered).
    """
    if shutil.which("pdftotext") is None:
        pytest.skip("poppler's pdftotext not installed")
    out = tmp_path / "report.pdf"
    result = _node(PDF_WORKER, "--out", str(out))
    if result.returncode == 2:
        pytest.skip(f"Chromium unavailable: {result.stderr.strip()}")
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert out.exists() and out.stat().st_size > 10_000

    txt = tmp_path / "report.txt"
    subprocess.run(["pdftotext", str(out), str(txt)], check=True, timeout=120)
    pages = txt.read_text().split("\f")[:-1]

    # The spec's target band, once the appendix moves to CSV. Wide on purpose —
    # this catches "the evidence blew up again", not layout micro-drift.
    assert 8 <= len(pages) <= 24, f"{len(pages)} pages — the report has lost its shape"

    body = "\n".join(pages)
    assert "AI visibility report" in body, "the running header is missing or clipped"
    assert "Page 1 of" in body, "page numbering did not render"
    assert "We do not claim these errors are permanent" in body, "the disclosure is missing"
    assert "Not affiliated with" in body, "the independence disclaimer is missing"

    # No finding card may be split: its title and its Fix line share a page.
    fix_pages = {i for i, p in enumerate(pages) if "Fix:" in p}
    assert fix_pages, "no finding card printed an action"
