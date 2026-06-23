/**
 * PDF rendering — the PDF is the deliverable (BUILD_PLAN.md §0). We render the
 * self-contained HTML (template.ts) and print it to PDF with Playwright's
 * headless Chromium.
 *
 * Playwright is loaded lazily (dynamic import) so the rest of the package — and
 * the test suite — never depend on the browser binaries being installed. If the
 * `playwright` package or its Chromium build is missing, renderPdf throws a
 * clear, actionable error and callers can fall back to the print-ready .html.
 */

import type { TeaserDraft } from "../types/domain.ts";
import { renderTeaserHtml } from "./template.ts";
import type { TeaserEdits } from "./template.ts";

export function renderHtml(draft: TeaserDraft, edits?: TeaserEdits): string {
  return renderTeaserHtml(draft, edits);
}

const INSTALL_HINT =
  "PDF export needs Playwright + Chromium — run `npm install` in teaser/ then " +
  "`npx playwright install chromium`. The generated .html is print-ready in the meantime.";

/** Print the teaser one-pager to an A4 PDF via headless Chromium. */
export async function renderPdf(draft: TeaserDraft, edits?: TeaserEdits): Promise<Uint8Array> {
  // Variable specifier so tsc treats this as a dynamic `any` import — the build
  // and typecheck stay green whether or not `playwright` is installed.
  const spec = "playwright";
  let chromium: { launch: () => Promise<unknown> } | undefined;
  try {
    ({ chromium } = (await import(spec)) as { chromium: { launch: () => Promise<unknown> } });
  } catch {
    throw new Error(INSTALL_HINT);
  }

  type Page = {
    setContent: (html: string, opts: { waitUntil: string }) => Promise<void>;
    pdf: (opts: { format: string; printBackground: boolean }) => Promise<Uint8Array>;
  };
  type Browser = { newPage: () => Promise<Page>; close: () => Promise<void> };

  let browser: Browser;
  try {
    browser = (await chromium.launch()) as Browser;
  } catch (err) {
    // Package present but the Chromium binary isn't installed (or failed to launch).
    throw new Error(`${INSTALL_HINT} (${err instanceof Error ? err.message : String(err)})`);
  }
  try {
    const page = await browser.newPage();
    await page.setContent(renderHtml(draft, edits), { waitUntil: "networkidle" });
    return await page.pdf({ format: "A4", printBackground: true });
  } finally {
    await browser.close();
  }
}
