/**
 * Print a report route to PDF through headless Chromium (audit-packaging P1-T7).
 *
 * Replaces a human pressing `window.print()`, which is neither reproducible nor
 * schedulable and silently drops anything below the fold.
 *
 *   node scripts/render-report-pdf.mjs <run-id> [--out FILE] [--base URL]
 *
 * Degrades the way the rest of this repo does: if Chromium is not installed it
 * says so and exits 2, rather than pretending the PDF failed for another reason.
 *
 * ── What does not work, and why this file looks the way it does ──────────────
 *
 * `position: running()` and `string-set()` are NOT implemented in Chromium and
 * are not coming — `string-set()` is an open, unresolved Chromium issue, and the
 * `@page` margin-box work that shipped in Chrome 131 explicitly scoped them out.
 * Only Paged.js, Prince and WeasyPrint implement them. So a section-aware running
 * header ("Findings — continued") is impossible here in any mode; the only
 * mechanism is Playwright's headerTemplate/footerTemplate, which is static.
 *
 * Four traps, all of which fail silently:
 *   1. `displayHeaderFooter: true` is REQUIRED or the templates are ignored
 *      entirely — no error, just no header.
 *   2. Template default font-size is effectively ZERO. Set it inline or the
 *      header renders as an invisible hairline.
 *   3. Templates render in an ISOLATED IFRAME: no external stylesheet, no
 *      webfonts by relative path, images must be base64 data-URIs. Headless
 *      Chrome also refuses to fetch `url()` resources inside `@page` CSS, so a
 *      logo referenced that way just never appears.
 *   4. `margin.top`/`margin.bottom` must RESERVE space for the templates or the
 *      header is clipped by the content.
 */

import { writeFile } from "node:fs/promises";
import process from "node:process";

const INSTALL_HINT =
  "PDF export needs Playwright + Chromium — run `npm install` in web/ then " +
  "`npx playwright install chromium`.";

/** Margins. THE one source — `@page` in sable.css is `margin: 0` on purpose.
 * Mixing `@page { margin }` with these is an open Playwright bug with
 * unpredictable output, so exactly one of the two may be non-zero.
 * `top`/`bottom` reserve room for the header/footer templates. */
const MARGIN = { top: "0.9in", bottom: "0.75in", left: "0.6in", right: "0.6in" };

/** Everything a header needs, inline, because the iframe can reach nothing. */
function templates({ clientName, runDate, brandName }) {
  const base = "font-family: Helvetica, Arial, sans-serif; font-size: 8px; color: #697585;";
  return {
    headerTemplate: `
      <style>* { margin: 0; padding: 0; }</style>
      <div style="${base} width: 100%; padding: 0.35in 0.6in 0; display: flex;
                  justify-content: space-between;">
        <span>${escapeHtml(clientName)} — AI visibility report</span>
        <span>${escapeHtml(runDate)}</span>
      </div>`,
    footerTemplate: `
      <style>* { margin: 0; padding: 0; }</style>
      <div style="${base} width: 100%; padding: 0 0.6in 0.3in; display: flex;
                  justify-content: space-between;">
        <span>Measurement by ${escapeHtml(brandName)}. Not affiliated with, sponsored by, or
          endorsed by OpenAI, Anthropic, Google or Perplexity.</span>
        <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
      </div>`,
  };
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

/**
 * @param {{runId: string, baseUrl?: string, clientName?: string, runDate?: string,
 *          brandName?: string, timeoutMs?: number}} opts
 * @returns {Promise<Uint8Array>}
 */
export async function renderReportPdf(opts) {
  const {
    runId,
    baseUrl = "http://localhost:3000",
    clientName = "",
    runDate = "",
    brandName = "Sable",
    timeoutMs = 60_000,
  } = opts;

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch {
    throw new Error(INSTALL_HINT);
  }

  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    throw new Error(`${INSTALL_HINT} (${err instanceof Error ? err.message : String(err)})`);
  }

  // One long-lived Browser, a FRESH CONTEXT per render. Contexts are cheap and
  // isolated, so no cookie or cache bleed between tenants; a new Browser costs
  // 1-2s of cold launch. Always closed in `finally` — a leaked context
  // accumulates until the worker OOMs.
  const context = await browser.newContext();
  try {
    const page = await context.newPage();
    const url = `${baseUrl.replace(/\/$/, "")}/audits/${encodeURIComponent(runId)}?mode=print`;
    await page.goto(url, { waitUntil: "networkidle", timeout: timeoutMs });

    // `networkidle` only means HTTP quiesced. Client-rendered SVG finishes on
    // LATER animation frames, so capturing here would print half-drawn charts.
    // The app raises this flag itself once every chart has laid out and fonts
    // have settled (see web/lib/render-mode.tsx).
    await page.waitForFunction(() => document.body.dataset.reportReady === "true", null, {
      timeout: timeoutMs,
    });

    const heading = clientName || (await page.title());
    return await page.pdf({
      format: "Letter",
      printBackground: true, // or the severity ramp prints as blank chips
      displayHeaderFooter: true,
      ...templates({ clientName: heading, runDate, brandName }),
      margin: MARGIN,
      preferCSSPageSize: false, // do NOT also honour @page margins — pick one
    });
  } finally {
    await context.close();
    await browser.close();
  }
}

// --- CLI ---------------------------------------------------------------------

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const args = process.argv.slice(2);
  const runId = args.find((a) => !a.startsWith("--"));
  const flag = (name, fallback) => {
    const i = args.indexOf(`--${name}`);
    return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
  };
  if (!runId) {
    console.error("usage: node scripts/render-report-pdf.mjs <run-id> [--out FILE] [--base URL]");
    process.exit(1);
  }
  const out = flag("out", `report-${runId}.pdf`);
  try {
    const pdf = await renderReportPdf({
      runId,
      baseUrl: flag("base", "http://localhost:3000"),
      clientName: flag("client", ""),
      runDate: flag("date", ""),
    });
    await writeFile(out, pdf);
    console.log(`wrote ${out} (${(pdf.length / 1024).toFixed(0)} KB)`);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(message);
    process.exit(message.startsWith(INSTALL_HINT) ? 2 : 1);
  }
}
