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

// Side-effect import FIRST: load the repo-root .env so the teaser reuses the
// platform's existing ANTHROPIC_API_KEY (and GEO_*/CRAWL4AI_* config) before any
// adapter wiring reads process.env. Must precede the ./config import.
import "./env.ts";

import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import {
  adapterModes,
  buildDeps,
  mockedAdapters,
  REAL_ADAPTER_HINTS,
  usingMockPlatform,
} from "./config.ts";
import { runTeaserPipeline, type PipelineOptions } from "./pipeline.ts";
import { renderHtml, renderPdf } from "./render/pdf.ts";

interface Args {
  url: string | null;
  out: string;
  json: boolean;
  engines: string[] | null;
  maxQueries: number | null;
  runs: number | null;
  requireReal: boolean;
}

function parseArgs(argv: string[]): Args {
  const args: Args = {
    url: null,
    out: "out",
    json: false,
    engines: null,
    maxQueries: null,
    runs: null,
    // Hard-fail rather than silently mock — for the actual client run. Also
    // settable via TEASER_REQUIRE_REAL=1 so the web route can enforce it.
    requireReal: process.env.TEASER_REQUIRE_REAL === "1",
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") {
      args.out = argv[++i] ?? args.out;
    } else if (a === "--json") {
      args.json = true;
    } else if (a === "--require-real") {
      args.requireReal = true;
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
    console.error("usage: npm run teaser -- <url> [--out <dir>] [--engines a,b] [--max-queries n] [--runs n] [--json] [--require-real]");
    process.exit(1);
    return;
  }

  // --require-real: refuse to run on any mock adapter, so the real client run
  // can't silently produce a teaser built on a fabricated profile / synthetic
  // findings. Lists exactly what is mocked and how to make it real.
  if (args.requireReal) {
    const mocked = mockedAdapters();
    if (mocked.length) {
      const detail = mocked.map((m) => `${m} (${REAL_ADAPTER_HINTS[m]})`).join("; ");
      const reason = `--require-real: refusing to run on mock adapter(s): ${detail}`;
      if (args.json) {
        process.stdout.write(JSON.stringify({ ok: false, stage: "config", reason }));
      } else {
        console.error(`✗ ${reason}`);
      }
      process.exit(2);
      return;
    }
  }

  const deps = buildDeps();
  const result = await runTeaserPipeline(args.url, deps, buildOptions(args));

  // --json mode: emit a single machine-readable object on stdout and nothing else,
  // so a calling process (the web route) can parse it directly.
  if (args.json) {
    if (!result.ok) {
      process.stdout.write(JSON.stringify({ ok: false, stage: result.stage, reason: result.reason }));
      process.exit(2);
      return;
    }
    const html = renderHtml(result.draft);
    // Persist every generated teaser to the platform's teasers store (best-effort).
    // `teaserId` lets the web UI drive review on the row the CLI just created
    // instead of saving it a second time. `adapters` lets the caller tell a real
    // audit from one built on a mock resolver/platform.
    const teaserId = await deps.platform.saveTeaser(result.draft, html);
    process.stdout.write(
      JSON.stringify({
        ok: true,
        draft: result.draft,
        html,
        adapters: adapterModes(),
        teaserId,
      }),
    );
    return;
  }

  // Human mode: name exactly which adapters are real vs mock — a teaser built on
  // a mock resolver (fabricated profile) or mock platform (synthetic findings)
  // must never look like a real audit. The platform-wait message keys off the
  // PLATFORM adapter only: whenever GEO_PLATFORM_URL is set the audit really can
  // take minutes, regardless of whether the resolver/query-set are still mocks.
  const mocked = mockedAdapters();
  if (mocked.length) {
    console.warn(
      `⚠️  MOCK adapter(s): ${mocked.join(", ")} — those parts are synthetic, NOT real data. ` +
        `Re-run with --require-real to hard-fail instead of mocking.\n`,
    );
  }
  if (!usingMockPlatform()) {
    console.log("→ Running the audit against the real platform (GEO_PLATFORM_URL). This can take several minutes.\n");
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

  const htmlContent = renderHtml(draft);
  await writeFile(htmlPath, htmlContent, "utf8");
  await writeFile(jsonPath, JSON.stringify(draft, null, 2), "utf8");

  // Persist every teaser to the platform's teasers store (best-effort) so all
  // runs are captured for review + training data, not just web-UI ones.
  const teaserId = await deps.platform.saveTeaser(draft, htmlContent);

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
  if (teaserId) {
    console.log(`  → saved to Supabase (teaser id ${teaserId})`);
  } else if (!usingMockPlatform()) {
    console.warn(`  ⚠️  could not save the teaser to Supabase (continuing).`);
  }
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
