/**
 * POST /api/audit — generate an AI Visibility Audit from a COMPLETED run_id.
 *
 * Runs the audit generator (../../teaser, `src/auditCli.ts`) as a child Node
 * process, pointing its platform adapter at the FastAPI via GEO_PLATFORM_URL so
 * it reads the finished run. The CLI's --json mode returns {draft, html,
 * deliverableId} on stdout, which we pass straight back to the client. Mirrors
 * /api/teaser (kept server-side so the generator runs in its own node runtime).
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { join } from "node:path";
import { NextResponse } from "next/server";

const execFileAsync = promisify(execFile);

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const PLATFORM_URL =
  process.env.GEO_PLATFORM_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PLATFORM_API_KEY =
  process.env.GEO_PLATFORM_API_KEY ||
  process.env.GEO_API_KEY ||
  process.env.NEXT_PUBLIC_GEO_API_KEY ||
  "";

const TEASER_DIR = join(process.cwd(), "..", "teaser");

interface AuditRequest {
  runId?: unknown;
  category?: unknown;
  perBucket?: unknown;
}

export async function POST(req: Request): Promise<NextResponse> {
  let body: AuditRequest;
  try {
    body = (await req.json()) as AuditRequest;
  } catch {
    return NextResponse.json({ ok: false, stage: "input", reason: "invalid JSON body" }, { status: 400 });
  }

  const runId = typeof body.runId === "string" ? body.runId.trim() : "";
  if (!runId) {
    return NextResponse.json({ ok: false, stage: "input", reason: "a run_id is required" }, { status: 400 });
  }

  const cliArgs = ["--experimental-strip-types", "src/auditCli.ts", runId, "--json"];
  const category = typeof body.category === "string" ? body.category.trim() : "";
  if (category) cliArgs.push("--category", category);
  const perBucket = Number(body.perBucket);
  if (Number.isFinite(perBucket) && perBucket > 0) cliArgs.push("--per-bucket", String(Math.floor(perBucket)));

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    GEO_PLATFORM_URL: PLATFORM_URL,
    ...(PLATFORM_API_KEY ? { GEO_PLATFORM_API_KEY: PLATFORM_API_KEY } : {}),
  };

  try {
    const { stdout } = await execFileAsync(process.execPath, cliArgs, {
      cwd: TEASER_DIR,
      env,
      maxBuffer: 64 * 1024 * 1024,
      timeout: 1000 * 60 * 4,
    });
    return NextResponse.json(parseCliJson(stdout));
  } catch (err: unknown) {
    const e = err as { stdout?: string; killed?: boolean; message?: string };
    if (e.stdout) return NextResponse.json(parseCliJson(e.stdout), { status: 200 });
    const reason = e.killed ? "audit generation timed out" : e.message || "failed to run the audit generator";
    return NextResponse.json({ ok: false, stage: "internal", reason }, { status: 500 });
  }
}

/** Parse the CLI's single-line JSON, tolerating any leading non-JSON noise. */
function parseCliJson(stdout: string): unknown {
  const text = stdout.trim();
  try {
    return JSON.parse(text);
  } catch {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(text.slice(start, end + 1));
      } catch {
        /* fall through */
      }
    }
    return { ok: false, stage: "internal", reason: "could not parse audit output" };
  }
}
