/**
 * CLI: `npm run teaser -- <url> [options]`
 *
 * Runs the pipeline and, by default, writes a draft teaser to disk:
 *   <out>/<slug>.html   — the print-ready one-pager (open it in a browser)
 *   <out>/<slug>.json   — the structured TeaserDraft (report + verbatim answers)
 *
 * Options:
 *   --out <dir>          output directory (default: out)
 *   --engines <csv>      platform engines, comma-separated (default: pipeline default)
 *   --max-queries <n>    cap the query set to the leanest N (smaller teaser audit)
 *   --runs <n>           runs per query (default: 1)
 *   --json               print {ok, draft, html} (or {ok:false,...}) to stdout and
 *                        write nothing — the contract the web /api/teaser route consumes
 *
 * With GEO_PLATFORM_URL set the audit runs against the real platform; otherwise the
 * mock adapters run the whole flow with no credentials.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { buildDeps, usingMocks, usingMockPlatform } from "./config.ts";
import { runTeaserPipeline, type PipelineOptions } from "./pipeline.ts";
import { renderHtml, renderPdf } from "./render/pdf.ts";

interface Args {
  url: string | null;
  out: string;
  json: boolean;
  engines: string[] | null;
  maxQueries: number | null;
  runs: number | null;
}

function parseArgs(argv: string[]): Args {
  const args: Args = { url: null, out: "out", json: false, engines: null, maxQueries: null, runs: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") {
      args.out = argv[++i] ?? args.out;
    } else if (a === "--json") {
      args.json = true;
    } else if (a === "--engines") {
      const v = argv[++i] ?? "";
      args.engines = v.split(",").map((s) => s.trim()).filter(Boolean);
    } else if (a === "--max-queries") {
      const n = Number(argv[++i]);
      args.maxQueries = Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
    } else if (a === "--runs") {
      const n = Number(argv[++i]);
      args.runs = Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
    } else if (a && !a.startsWith("--")) {
      args.url = a;
    }
  }
  return args;
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "teaser";
}

/** Pipeline options from CLI flags + a mock/real-aware polling cadence. */
function buildOptions(args: Args): Partial<PipelineOptions> {
  // Cadence keys off the PLATFORM only: the mock platform returns "done" on the
  // first poll; a real audit takes minutes, so poll on a real interval with a
  // long ceiling (600 × 3s ≈ 30 min). A mock resolver/query-set generator does
  // not change how long the platform audit takes, so it must not shorten this.
  const opts: Partial<PipelineOptions> = usingMockPlatform()
    ? {}
    : { pollIntervalMs: 3000, maxPolls: 600 };
  if (args.engines && args.engines.length) opts.engines = args.engines;
  if (args.maxQueries) opts.maxQueries = args.maxQueries;
  if (args.runs) opts.runsPerQuery = args.runs;
  return opts;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) {
    if (args.json) {
      process.stdout.write(JSON.stringify({ ok: false, stage: "input", reason: "missing url" }));
      process.exit(1);
    }
    console.error("usage: npm run teaser -- <url> [--out <dir>] [--engines a,b] [--max-queries n] [--runs n] [--json]");
    process.exit(1);
    return;
  }

  const result = await runTeaserPipeline(args.url, buildDeps(), buildOptions(args));

  // --json mode: emit a single machine-readable object on stdout and nothing else,
  // so a calling process (the web route) can parse it directly.
  if (args.json) {
    if (!result.ok) {
      process.stdout.write(JSON.stringify({ ok: false, stage: result.stage, reason: result.reason }));
      process.exit(2);
      return;
    }
    process.stdout.write(JSON.stringify({ ok: true, draft: result.draft, html: renderHtml(result.draft) }));
    return;
  }

  // Human mode: warn about adapter mode, then write the files. The platform-wait
  // message keys off the PLATFORM adapter only (usingMockPlatform): whenever
  // GEO_PLATFORM_URL is set the audit really can take minutes, regardless of
  // whether the resolver/query-set generator are still mocks.
  if (usingMockPlatform()) {
    console.warn("⚠️  MOCK platform (no GEO_PLATFORM_URL) — findings are synthetic.\n");
  } else {
    console.log("→ Running against the real platform (GEO_PLATFORM_URL). This can take several minutes.\n");
    if (usingMocks()) {
      console.warn("⚠️  Some adapters (resolver/query-set) are still mocks — parts of the input are synthetic.\n");
    }
  }
  if (!result.ok) {
    console.error(`✗ pipeline stopped at [${result.stage}]: ${result.reason}`);
    process.exit(2);
    return;
  }

  const draft = result.draft;
  const outDir = resolve(args.out);
  await mkdir(outDir, { recursive: true });
  const slug = slugify(draft.companyName);
  const htmlPath = join(outDir, `${slug}.html`);
  const jsonPath = join(outDir, `${slug}.json`);
  const pdfPath = join(outDir, `${slug}.pdf`);

  await writeFile(htmlPath, renderHtml(draft), "utf8");
  await writeFile(jsonPath, JSON.stringify(draft, null, 2), "utf8");

  // The PDF is the deliverable. Best-effort: if Playwright/Chromium isn't
  // installed, keep the run successful (the .html is print-ready) and tell the
  // user how to enable PDF export.
  let pdfWritten = false;
  try {
    await writeFile(pdfPath, await renderPdf(draft));
    pdfWritten = true;
  } catch (err) {
    console.warn(`⚠️  PDF not written: ${err instanceof Error ? err.message : String(err)}\n`);
  }

  const h = draft.headlineNumber;
  console.log(`✓ Draft teaser for ${draft.companyName} (${draft.prospectUrl})`);
  console.log(`  hero engine : ${draft.heroEngine}`);
  console.log(`  headline    : ${draft.companyName} ${h.companyAppears}/${h.n} vs ${h.competitorName} ${h.competitorAppears}/${h.n}`);
  console.log(`  lead query  : "${draft.lead.verbatimQuery}"`);
  console.log(`  table rows  : ${draft.table.length}`);
  console.log(`\n  → ${htmlPath}`);
  console.log(`  → ${jsonPath}`);
  if (pdfWritten) console.log(`  → ${pdfPath}`);
  console.log(
    pdfWritten
      ? `\n  Open the .pdf (the deliverable) or the .html to review.`
      : `\n  Open the .html to review (print-ready). Run \`npx playwright install chromium\` to enable PDF export.`,
  );
}

main().catch((err) => {
  // In --json mode a stray throw must still be parseable by the caller.
  if (process.argv.includes("--json")) {
    process.stdout.write(JSON.stringify({ ok: false, stage: "internal", reason: String(err) }));
  } else {
    console.error(err);
  }
  process.exit(1);
});
