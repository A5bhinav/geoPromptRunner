/**
 * Audit CLI: `npm run audit -- <run_id> [options]`
 *
 * Consumes a COMPLETED full audit run (it does not run its own audit) and emits a
 * client-ready AI Visibility Audit:
 *   <out>/<slug>-audit.html  — the multi-page report (open in a browser)
 *   <out>/<slug>-audit.json  — the structured AuditDraft (report + verbatim answers)
 *   <out>/<slug>-audit.pdf   — the print-ready leave-behind (best-effort)
 *
 * Options:
 *   --out <dir>        output directory (default: out)
 *   --category <text>  the consumer category label for the §1 headline (e.g. "smart ring")
 *   --per-bucket <n>   evidence proof cards per journey stage (default 2; doc §15.4)
 *   --require-real     refuse to run against the mock platform (a mock run isn't a real audit)
 *   --json             print {ok, draft, html, deliverableId} to stdout and write nothing
 *
 * Needs GEO_PLATFORM_URL pointed at the platform that produced <run_id>.
 */

// Side-effect import FIRST: load the repo-root .env (GEO_PLATFORM_URL, keys).
import "./env.ts";

import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { buildDeps, usingMockPlatform } from "./config.ts";
import { buildAudit } from "./select/buildAudit.ts";
import { renderAuditHtmlString, renderAuditPdf } from "./render/audit/pdf.ts";

interface Args {
  runId: string | null;
  out: string;
  category: string;
  perBucket: number | null;
  json: boolean;
  requireReal: boolean;
}

function parseArgs(argv: string[]): Args {
  const args: Args = {
    runId: null,
    out: "out",
    category: "",
    perBucket: null,
    json: false,
    requireReal: process.env.TEASER_REQUIRE_REAL === "1",
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") args.out = argv[++i] ?? args.out;
    else if (a === "--category") args.category = argv[++i] ?? args.category;
    else if (a === "--per-bucket") {
      const n = Number(argv[++i]);
      args.perBucket = Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
    } else if (a === "--json") args.json = true;
    else if (a === "--require-real") args.requireReal = true;
    else if (a && !a.startsWith("--")) args.runId = a;
  }
  return args;
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "audit";
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (!args.runId) {
    const usage =
      "usage: npm run audit -- <run_id> [--category <text>] [--out <dir>] [--per-bucket n] [--json] [--require-real]";
    if (args.json) process.stdout.write(JSON.stringify({ ok: false, stage: "input", reason: "missing run_id" }));
    else console.error(usage);
    process.exit(1);
    return;
  }

  // --require-real: a generated audit must be built on a real platform run, never
  // the in-memory mock (which also can't hold a run_id across processes).
  if (args.requireReal && usingMockPlatform()) {
    const reason = "--require-real: refusing to run against the mock platform (set GEO_PLATFORM_URL)";
    if (args.json) process.stdout.write(JSON.stringify({ ok: false, stage: "config", reason }));
    else console.error(`✗ ${reason}`);
    process.exit(2);
    return;
  }

  const platform = buildDeps().platform;

  // Fetch the finished run's report + verbatim answers.
  let report;
  let answers;
  try {
    [report, answers] = await Promise.all([platform.getReport(args.runId), platform.getAnswers(args.runId)]);
  } catch (err) {
    const reason = `could not fetch run ${args.runId}: ${err instanceof Error ? err.message : String(err)}`;
    if (args.json) process.stdout.write(JSON.stringify({ ok: false, stage: "fetch", reason }));
    else console.error(`✗ ${reason}`);
    process.exit(2);
    return;
  }

  // Guard: the audit needs the judge path (grade/accuracy/prominence) to be meaningful.
  if (report.detection !== "judge") {
    const reason = `run detection is "${report.detection}" — the audit needs a judge run (grade + accuracy)`;
    if (args.json) process.stdout.write(JSON.stringify({ ok: false, stage: "guard", reason }));
    else console.error(`✗ ${reason}`);
    process.exit(2);
    return;
  }

  const draft = buildAudit(
    args.runId,
    args.category,
    report,
    answers,
    args.perBucket ? { evidencePerBucket: args.perBucket } : {},
  );
  const html = renderAuditHtmlString(draft);

  if (args.json) {
    const deliverableId = await platform.saveAuditDeliverable(draft, html);
    process.stdout.write(JSON.stringify({ ok: true, draft, html, deliverableId }));
    return;
  }

  const outDir = resolve(args.out);
  await mkdir(outDir, { recursive: true });
  const slug = slugify(draft.clientName);
  const htmlPath = join(outDir, `${slug}-audit.html`);
  const jsonPath = join(outDir, `${slug}-audit.json`);
  const pdfPath = join(outDir, `${slug}-audit.pdf`);

  await writeFile(htmlPath, html, "utf8");
  await writeFile(jsonPath, JSON.stringify(draft, null, 2), "utf8");

  const deliverableId = await platform.saveAuditDeliverable(draft, html);

  let pdfWritten = false;
  try {
    await writeFile(pdfPath, await renderAuditPdf(draft));
    pdfWritten = true;
  } catch (err) {
    console.warn(`⚠️  PDF not written: ${err instanceof Error ? err.message : String(err)}\n`);
  }

  const h = draft.headlineNumber;
  console.log(`✓ AI Visibility Audit for ${draft.clientName} (run ${args.runId})`);
  console.log(`  grade       : ${draft.grade ? draft.grade.letter : "uncalibrated"}${draft.achievableGrade ? ` → ${draft.achievableGrade}` : ""}`);
  console.log(`  headline    : ${draft.clientName} ${h.clientAppears}/${h.n} vs ${h.competitorName || "—"} ${h.competitorAppears}/${h.n}`);
  console.log(`  evidence    : ${draft.evidence.reduce((s, g) => s + g.findings.length, 0)} proof cards across ${draft.evidence.length} stages`);
  console.log(`  diagnosis   : ${draft.diagnosis.present ? `${draft.diagnosis.categories.length} categories` : "no site audit"}`);
  console.log(`\n  → ${htmlPath}`);
  console.log(`  → ${jsonPath}`);
  if (pdfWritten) console.log(`  → ${pdfPath}`);
  if (deliverableId) console.log(`  → saved to Supabase (deliverable ${deliverableId})`);
  console.log(
    pdfWritten
      ? `\n  Open the .pdf (the leave-behind) or the .html to review.`
      : `\n  Open the .html (print-ready). Run \`npx playwright install chromium\` to enable PDF export.`,
  );
}

main().catch((err) => {
  if (process.argv.includes("--json")) {
    process.stdout.write(JSON.stringify({ ok: false, stage: "internal", reason: String(err) }));
  } else {
    console.error(err);
  }
  process.exit(1);
});
