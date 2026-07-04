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
 *   --runs <n>           runs per query (default: 3 — repeated so a claim reproduces)
 *   --json               print {ok, draft, html} (or {ok:false,...}) to stdout and
 *                        write nothing — the contract the web /api/teaser route consumes
 *   --yes                skip the interactive confirm gate (profile/competitor review)
 *   --allow-mock         permit mock adapters (keyless demo); by default the CLI
 *                        refuses to run on any mock so a sent teaser is never fabricated
 *
 * Real adapters are the default: a teaser is only worth sending if it's built on a
 * real crawl + real audit. Set GEO_PLATFORM_URL + ANTHROPIC_API_KEY, or pass
 * --allow-mock (TEASER_ALLOW_MOCK=1) to run the whole flow on mocks with no creds.
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
import { interactiveConfirm } from "./confirmGate.ts";
import { isStale } from "./freshness.ts";
import { runTeaserPipeline, type PipelineOptions } from "./pipeline.ts";
import { relationshipGuard } from "./resolver/relationshipCheck.ts";
import { renderHtml, renderPdf } from "./render/pdf.ts";

interface Args {
  url: string | null;
  out: string;
  json: boolean;
  engines: string[] | null;
  maxQueries: number | null;
  runs: number | null;
  requireReal: boolean;
  yes: boolean;
}

function parseArgs(argv: string[]): Args {
  const args: Args = {
    url: null,
    out: "out",
    json: false,
    engines: null,
    maxQueries: null,
    runs: null,
    // Real adapters are the DEFAULT for the outreach CLI: a teaser is only worth
    // sending if it's built on a real crawl + real audit, not a fabricated mock
    // profile. Opt into mocks explicitly (keyless demo) with --allow-mock or
    // TEASER_ALLOW_MOCK=1. --require-real / TEASER_REQUIRE_REAL=1 stay honored as
    // an explicit force (and pre-date this default), but are now redundant.
    requireReal: process.env.TEASER_ALLOW_MOCK === "1" ? false : true,
    yes: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") {
      args.out = argv[++i] ?? args.out;
    } else if (a === "--json") {
      args.json = true;
    } else if (a === "--require-real") {
      args.requireReal = true;
    } else if (a === "--allow-mock") {
      args.requireReal = false;
    } else if (a === "--yes" || a === "-y") {
      args.yes = true;
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

  // Human confirm gate (BUILD_PLAN §7 #7): ON by default in interactive runs —
  // the resolver's competitors are unconfirmed LLM output, and a wrong one
  // becomes a false claim in a sent teaser. Skipped in --json mode (the web
  // route drives its own review UI) and with --yes; a non-TTY run can't prompt,
  // so it proceeds with a loud warning instead of hanging.
  if (!args.json && !args.yes) {
    if (process.stdin.isTTY) {
      opts.confirm = interactiveConfirm;
    } else {
      console.warn(
        "⚠️  confirm gate skipped: no TTY to prompt on. Competitors are UNREVIEWED " +
          "LLM output — review the draft before sending. Pass --yes to silence this.\n",
      );
    }
  }

  // Relationship guard: only meaningful on a REAL resolved profile (a mock
  // resolver invents competitors we won't web-check). Logs to stderr so --json
  // stdout stays a single clean object. Recall-safe inside relationshipGuard.
  if (adapterModes().resolver === "real") {
    opts.relationshipCheck = (profile) =>
      relationshipGuard(profile, (msg) => console.error(msg));
  }
  return opts;
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) {
    if (args.json) {
      process.stdout.write(JSON.stringify({ ok: false, stage: "input", reason: "missing url" }));
      process.exit(1);
    }
    console.error("usage: npm run teaser -- <url> [--out <dir>] [--engines a,b] [--max-queries n] [--runs n] [--json] [--allow-mock] [--yes]");
    process.exit(1);
    return;
  }

  // Refuse to run on any mock adapter (the default), so an outreach teaser can't
  // be silently built on a fabricated profile / synthetic findings. Lists exactly
  // what is mocked and how to make it real; --allow-mock opts into a keyless demo.
  if (args.requireReal) {
    const mocked = mockedAdapters();
    if (mocked.length) {
      const detail = mocked.map((m) => `${m} (${REAL_ADAPTER_HINTS[m]})`).join("; ");
      const reason =
        `refusing to run on mock adapter(s): ${detail}. ` +
        `Pass --allow-mock (or TEASER_ALLOW_MOCK=1) for a keyless demo.`;
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
    const html = renderHtml(result.draft, {}, { stale: isStale(result.draft.runDate, new Date()) });
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
      `⚠️  MOCK adapter(s): ${mocked.join(", ")} — those parts are synthetic, NOT real data ` +
        `(--allow-mock). Drop it and set the real adapters for a sendable teaser.\n`,
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

  const stale = isStale(draft.runDate, new Date());
  const htmlContent = renderHtml(draft, {}, { stale });
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
    await writeFile(pdfPath, await renderPdf(draft, {}, { stale }));
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
    console.log(`  → saved to Supabase (teaser id ${teaserId}) as a DRAFT`);
    console.log(`     approve before sending:  npm run approve -- ${teaserId}`);
  } else if (!usingMockPlatform()) {
    console.warn(`  ⚠️  could not save the teaser to Supabase (continuing).`);
  }
  // The generated artifact is an unapproved DRAFT (it carries a review banner).
  // Make the gate explicit in the console too.
  console.log(`\n  This is a DRAFT — review the competitor + claims, then approve before sending.`);
  console.log(
    pdfWritten
      ? `  Open the .pdf (the deliverable) or the .html to review.`
      : `  Open the .html to review (print-ready). Run \`npx playwright install chromium\` to enable PDF export.`,
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
