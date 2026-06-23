/**
 * CLI: `npm run teaser -- <url> [--out <dir>]`
 *
 * Runs the full pipeline (mocks by default) and writes a draft teaser to disk:
 *   <out>/<slug>.html   — the print-ready one-pager (open it in a browser)
 *   <out>/<slug>.json   — the structured TeaserDraft (report + verbatim answers)
 *
 * This is the Phase-1 vertical slice end-to-end, with no credentials required.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { buildDeps, usingMocks } from "./config.ts";
import { runTeaserPipeline } from "./pipeline.ts";
import { renderHtml } from "./render/pdf.ts";

function parseArgs(argv: string[]): { url: string | null; out: string } {
  let url: string | null = null;
  let out = "out";
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") {
      out = argv[++i] ?? out;
    } else if (a && !a.startsWith("--")) {
      url = a;
    }
  }
  return { url, out };
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "teaser";
}

async function main(): Promise<void> {
  const { url, out } = parseArgs(process.argv.slice(2));
  if (!url) {
    console.error("usage: npm run teaser -- <url> [--out <dir>]");
    process.exit(1);
    return;
  }

  const mocks = usingMocks();
  if (mocks) {
    console.warn("⚠️  Running with MOCK adapters (no platform/scraper/LLM). Findings are synthetic.\n");
  } else {
    console.log("→ Running against the real platform (GEO_PLATFORM_URL). This can take several minutes.\n");
  }

  // The mock returns "done" on the first poll; a real audit takes minutes, so
  // poll on a real interval with a long ceiling (600 × 3s ≈ 30 min).
  const pollOpts = mocks ? {} : { pollIntervalMs: 3000, maxPolls: 600 };
  const result = await runTeaserPipeline(url, buildDeps(), pollOpts);
  if (!result.ok) {
    console.error(`✗ pipeline stopped at [${result.stage}]: ${result.reason}`);
    process.exit(2);
    return;
  }

  const draft = result.draft;
  const outDir = resolve(out);
  await mkdir(outDir, { recursive: true });
  const slug = slugify(draft.companyName);
  const htmlPath = join(outDir, `${slug}.html`);
  const jsonPath = join(outDir, `${slug}.json`);

  await writeFile(htmlPath, renderHtml(draft), "utf8");
  await writeFile(jsonPath, JSON.stringify(draft, null, 2), "utf8");

  const h = draft.headlineNumber;
  console.log(`✓ Draft teaser for ${draft.companyName} (${draft.prospectUrl})`);
  console.log(`  hero engine : ${draft.heroEngine}`);
  console.log(`  headline    : ${draft.companyName} ${h.companyAppears}/${h.n} vs ${h.competitorName} ${h.competitorAppears}/${h.n}`);
  console.log(`  lead query  : "${draft.lead.verbatimQuery}"`);
  console.log(`  table rows  : ${draft.table.length}`);
  console.log(`\n  → ${htmlPath}`);
  console.log(`  → ${jsonPath}`);
  console.log(`\n  Open the .html to review. Approve + PDF export are the next steps (renderPdf stub).`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
