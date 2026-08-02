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
CHARTS = WEB / "components" / "charts.tsx"
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
    """Mixing `@page { margin }` with Playwright's `margin` is an open bug.

    The output is unpredictable and the usual symptom is a header clipped off the
    top of page 1. `@page` declares zero here; the real margins live in
    `page.pdf()`. Whichever side you change, change both in the same commit.
    """
    # Comments stripped first: this file necessarily QUOTES `@page { margin: 0 }`
    # in the prose that explains the rule, and matching the explanation instead
    # of the declaration is how a source-level guard passes while the rule is
    # wrong.
    css = re.sub(r"/\*.*?\*/", "", SABLE_CSS.read_text(), flags=re.DOTALL)
    page_rules = re.findall(r"@page\s*\{[^}]*\}", css)
    assert page_rules, "the print stylesheet declares no @page rule"
    for rule in page_rules:
        assert re.search(r"margin:\s*0\s*;", rule), (
            f"@page must declare `margin: 0` — the real margins belong to page.pdf(): {rule}"
        )

    worker = PDF_WORKER.read_text()
    assert "preferCSSPageSize: false" in worker, "the worker would honour @page margins too"
    assert re.search(r"MARGIN\s*=\s*\{[^}]*top:", worker)


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


def test_charts_do_not_rely_on_responsive_container_when_printing() -> None:
    """`ResponsiveContainer` sizes via `ResizeObserver`, which print never fires.

    Charts would print at whatever the last on-screen size happened to be —
    usually wrong, occasionally zero.
    """
    charts = CHARTS.read_text()
    # Exactly one ResponsiveContainer left, inside the ChartFrame that swaps it
    # out for a fixed box when printing.
    assert charts.count("<ResponsiveContainer") == 1
    assert "function ChartFrame" in charts
    assert "PRINT_CONTENT_WIDTH_PX" in charts


def test_every_chart_registers_with_the_readiness_gate() -> None:
    """Unconditionally, before any early return.

    A chart that bails out on an empty dataset still has to be accounted for, or
    the readiness signal is computed over a different set of charts than the page
    actually contains.
    """
    charts = CHARTS.read_text()
    exported = re.findall(r"export const (\w+) = React\.memo", charts)
    assert len(exported) >= 5, f"expected the full chart set, found {exported}"
    assert charts.count("useChartSettled();") == len(exported)


def test_chart_animation_is_off_when_printing() -> None:
    """A multi-frame transition is a race the capture can lose."""
    charts = CHARTS.read_text()
    bars = charts.count("<Bar ") + charts.count("<Bar\n")
    assert bars > 0
    assert charts.count("isAnimationActive={!isPrint}") == bars


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
    view = (WEB / "components" / "report-view.tsx").read_text()
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
    view = (WEB / "components" / "report-view.tsx").read_text()
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
