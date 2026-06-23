/**
 * POST /api/teaser — generate a teaser one-pager from a prospect URL.
 *
 * Runs the teaser pipeline (../../teaser) as a child Node process, pointing its
 * platform adapter at the FastAPI via GEO_PLATFORM_URL so the audit is real but
 * deliberately small. The CLI's --json mode returns the draft + rendered HTML on
 * stdout, which we pass straight back to the client.
 *
 * Kept server-side (not imported into the bundle) so the teaser keeps running in
 * its own node runtime — no Next bundler fight with its .ts-extension imports —
 * and the Python API is untouched.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { join } from "node:path";
import { NextResponse } from "next/server";

const execFileAsync = promisify(execFile);

// child_process needs the Node runtime; the audit can run for minutes.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 800;

// Where the platform API lives (same default as lib/api.ts). GEO_PLATFORM_URL
// makes the teaser run a real audit; unset → the teaser falls back to mocks.
const PLATFORM_URL =
  process.env.GEO_PLATFORM_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";
const PLATFORM_API_KEY =
  process.env.GEO_PLATFORM_API_KEY || process.env.GEO_API_KEY || process.env.NEXT_PUBLIC_GEO_API_KEY || "";

const TEASER_DIR = join(process.cwd(), "..", "teaser");

interface TeaserRequest {
  url?: unknown;
  engines?: unknown;
  maxQueries?: unknown;
  runs?: unknown;
}

function isHttpUrl(value: string): boolean {
  try {
    const u = new URL(/^https?:\/\//.test(value) ? value : `https://${value}`);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export async function POST(req: Request): Promise<NextResponse> {
  let body: TeaserRequest;
  try {
    body = (await req.json()) as TeaserRequest;
  } catch {
    return NextResponse.json({ ok: false, stage: "input", reason: "invalid JSON body" }, { status: 400 });
  }

  const url = typeof body.url === "string" ? body.url.trim() : "";
  if (!url || !isHttpUrl(url)) {
    return NextResponse.json({ ok: false, stage: "input", reason: "a valid http(s) URL is required" }, { status: 400 });
  }

  // Build CLI args. Engines/maxQueries/runs are optional; the CLI/pipeline supply
  // sensible defaults when omitted.
  const cliArgs = ["--experimental-strip-types", "src/cli.ts", url, "--json"];
  const engines = Array.isArray(body.engines)
    ? body.engines.filter((e): e is string => typeof e === "string" && e.length > 0)
    : [];
  if (engines.length) cliArgs.push("--engines", engines.join(","));
  const maxQueries = Number(body.maxQueries);
  if (Number.isFinite(maxQueries) && maxQueries > 0) cliArgs.push("--max-queries", String(Math.floor(maxQueries)));
  const runs = Number(body.runs);
  if (Number.isFinite(runs) && runs > 0) cliArgs.push("--runs", String(Math.floor(runs)));

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
      timeout: 1000 * 60 * 13,
    });
    return NextResponse.json(parseCliJson(stdout));
  } catch (err: unknown) {
    // The CLI exits non-zero on a pipeline stop but still prints a {ok:false,...}
    // object on stdout — surface that rather than a generic 500.
    const e = err as { stdout?: string; killed?: boolean; message?: string };
    if (e.stdout) {
      const parsed = parseCliJson(e.stdout);
      return NextResponse.json(parsed, { status: 200 });
    }
    const reason = e.killed
      ? "teaser generation timed out"
      : e.message || "failed to run the teaser pipeline";
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
    return { ok: false, stage: "internal", reason: "could not parse teaser output" };
  }
}
