/**
 * Print-layout guard for the report route (audit-packaging P1-T7/T8).
 *
 *   node scripts/check-print-layout.mjs <run-id> [--base URL]
 *
 * Checks the DOM under `emulateMedia({ media: 'print' })` rather than parsing a
 * PDF. That catches the failure EARLIER, needs no PDF parser, and points at the
 * element that broke instead of at a page number.
 *
 * Three classes of bug, all invisible on the live page:
 *
 *   1. **Content that never renders.** Print does not scroll the viewport, so
 *      `IntersectionObserver` never fires: lazy images stay blank, `ssr:false`
 *      sections vanish, a windowed table emits only its visible slice. Asserted
 *      by checking that the LAST row of the longest table is in the DOM.
 *   2. **Cards split across a page boundary.** A finding whose evidence lands on
 *      the next page reads as a different finding.
 *   3. **A capture that fires too early.** The readiness flag must actually be
 *      raised, or the worker would print half-drawn charts.
 *
 * Exit 0 = clean, 1 = a real layout failure, 2 = Chromium missing (skip).
 */

import process from "node:process";

const INSTALL_HINT =
  "Print-layout check needs Playwright + Chromium — run `npm install` in web/ " +
  "then `npx playwright install chromium`.";

// Letter at 96dpi, minus the 0.9in/0.75in margins reserved in
// render-report-pdf.mjs. Keep in step with MARGIN there.
const PAGE_HEIGHT_PX = Math.round((11 - 0.9 - 0.75) * 96);

async function main() {
  const args = process.argv.slice(2);
  const runId = args.find((a) => !a.startsWith("--"));
  const baseIndex = args.indexOf("--base");
  const baseUrl = baseIndex >= 0 && args[baseIndex + 1] ? args[baseIndex + 1] : "http://localhost:3000";
  if (!runId) {
    console.error("usage: node scripts/check-print-layout.mjs <run-id> [--base URL]");
    return 1;
  }

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch {
    console.error(INSTALL_HINT);
    return 2;
  }

  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    console.error(`${INSTALL_HINT} (${err instanceof Error ? err.message : String(err)})`);
    return 2;
  }

  const failures = [];
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    await page.emulateMedia({ media: "print" });
    await page.goto(`${baseUrl.replace(/\/$/, "")}/audits/${encodeURIComponent(runId)}?mode=print`, {
      waitUntil: "networkidle",
      timeout: 60_000,
    });

    // (3) The readiness contract. If this times out the worker would have
    // captured a half-rendered page, so it is a failure, not a warning.
    try {
      await page.waitForFunction(() => document.body.dataset.reportReady === "true", null, {
        timeout: 30_000,
      });
    } catch {
      failures.push("readiness flag never raised — the PDF worker would capture too early");
    }

    const report = await page.evaluate((pageHeight) => {
      const cards = [...document.querySelectorAll(".report-card")];

      // NOT checked here: whether a card straddles a page boundary.
      //
      // `emulateMedia({media:'print'})` applies print STYLES but does not
      // paginate — layout stays continuous, so `getBoundingClientRect()` reports
      // where a card would fall under naive slicing and cannot see Chromium
      // honouring `break-inside: avoid` at actual print time. A "page-height
      // multiple" heuristic here reports every card that happens to cross a
      // boundary as broken, which on the first real run was three confident
      // false failures. Pagination is verified against the produced PDF instead
      // (`tests/test_print_pipeline.py`), which is the only place it is real.
      //
      // What this file checks is the class of bug that IS visible here and is
      // invisible everywhere else: content that never renders at all.
      const oversizedCards = cards.filter(
        (el) => el.getBoundingClientRect().height > pageHeight,
      ).length;

      const tables = [...document.querySelectorAll("table")];
      const longest = tables.sort(
        (a, b) => b.querySelectorAll("tbody tr").length - a.querySelectorAll("tbody tr").length,
      )[0];
      const rows = longest ? longest.querySelectorAll("tbody tr").length : 0;
      const lastRowText = longest
        ? (longest.querySelector("tbody tr:last-child")?.textContent ?? "").trim().slice(0, 60)
        : "";

      const blankLazyImages = [...document.querySelectorAll("img")].filter(
        (img) => img.loading === "lazy" && !img.complete,
      ).length;

      // Charts must have real SVG geometry, not a zero-size ResponsiveContainer.
      //
      // Direct children of `.recharts-wrapper` only: recharts reuses the
      // `recharts-surface` class for the 14x14 SVG inside each LEGEND ITEM, and
      // a bare class selector reports those as collapsed charts. That produced a
      // confident, wrong "2 of 5 charts have no size" on the first real run.
      const svgs = [...document.querySelectorAll(".recharts-wrapper > svg.recharts-surface")];
      const collapsedCharts = svgs.filter((s) => {
        const r = s.getBoundingClientRect();
        return r.width < 50 || r.height < 50;
      }).length;

      return {
        cards: cards.length,
        oversizedCards,
        rows,
        lastRowText,
        blankLazyImages,
        charts: svgs.length,
        collapsedCharts,
        findingCards: cards.length,
        evidenceBlocks: document.querySelectorAll(".report-card blockquote").length,
      };
    }, PAGE_HEIGHT_PX);

    if (report.oversizedCards > 0) {
      // An element taller than one page cannot honour `break-inside: avoid` —
      // the rule is simply ignored, so the card WILL split wherever it lands.
      failures.push(
        `${report.oversizedCards} finding card(s) are taller than one page — ` +
          "`break-inside: avoid` cannot hold them together",
      );
    }
    if (report.rows > 0 && !report.lastRowText) {
      failures.push("the longest table's last row is empty — windowed rendering dropped content");
    }
    if (report.blankLazyImages > 0) {
      failures.push(`${report.blankLazyImages} lazy image(s) never loaded — blank in the PDF`);
    }
    if (report.charts > 0 && report.collapsedCharts > 0) {
      failures.push(
        `${report.collapsedCharts} of ${report.charts} charts have no size — ` +
          "ResponsiveContainer did not resize for print",
      );
    }
    if (report.findingCards > 0 && report.evidenceBlocks < report.findingCards) {
      failures.push("a finding card printed without its quoted evidence");
    }

    console.log(
      `cards=${report.cards} charts=${report.charts} longest-table-rows=${report.rows} ` +
        `page-height=${PAGE_HEIGHT_PX}px`,
    );
  } finally {
    await context.close();
    await browser.close();
  }

  if (failures.length > 0) {
    for (const f of failures) console.error(`FAIL: ${f}`);
    return 1;
  }
  console.log("print layout OK");
  return 0;
}

process.exit(await main());
