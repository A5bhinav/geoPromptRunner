/**
 * Audit PDF rendering — the multi-page PDF is the leave-behind deliverable.
 * Mirrors render/pdf.ts: render the self-contained HTML, print to PDF via lazy
 * Playwright/Chromium. Falls back cleanly to the print-ready .html when the
 * browser binaries aren't installed.
 */

import type { AuditDraft, AuditEdits } from "../../types/audit.ts";
import { renderAuditHtml } from "./template.ts";

export function renderAuditHtmlString(draft: AuditDraft, edits?: AuditEdits): string {
  return renderAuditHtml(draft, edits);
}

const INSTALL_HINT =
  "PDF export needs Playwright + Chromium — run `npm install` in teaser/ then " +
  "`npx playwright install chromium`. The generated .html is print-ready in the meantime.";

/** Print the multi-page audit to an A4 PDF via headless Chromium. */
export async function renderAuditPdf(draft: AuditDraft, edits?: AuditEdits): Promise<Uint8Array> {
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
    throw new Error(`${INSTALL_HINT} (${err instanceof Error ? err.message : String(err)})`);
  }
  try {
    const page = await browser.newPage();
    await page.setContent(renderAuditHtml(draft, edits), { waitUntil: "networkidle" });
    return await page.pdf({ format: "A4", printBackground: true });
  } finally {
    await browser.close();
  }
}
