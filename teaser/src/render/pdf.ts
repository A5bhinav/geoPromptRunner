/**
 * PDF rendering — the PDF is the deliverable (BUILD_PLAN.md). This is the seam.
 *
 * MVP: we write the self-contained HTML and (when Playwright/Puppeteer is
 * installed) print it to PDF. To keep the placeholder build dependency-free,
 * renderPdf is a stub that throws a clear "not wired yet" error pointing at the
 * HTML output. Wire a real printer here in Phase 1 finish — no other code changes.
 */

import type { TeaserDraft } from "../types/domain.ts";
import { renderTeaserHtml } from "./template.ts";

export function renderHtml(draft: TeaserDraft): string {
  return renderTeaserHtml(draft);
}

export async function renderPdf(_draft: TeaserDraft): Promise<Uint8Array> {
  // Intentional placeholder. Real impl (later):
  //   import { chromium } from "playwright";
  //   const browser = await chromium.launch();
  //   const page = await browser.newPage();
  //   await page.setContent(renderHtml(_draft), { waitUntil: "networkidle" });
  //   const pdf = await page.pdf({ format: "A4", printBackground: true });
  //   await browser.close();
  //   return pdf;
  throw new Error(
    "renderPdf is not wired yet — install playwright and complete src/render/pdf.ts. " +
      "For now, open the generated .html (it is print-ready).",
  );
}
