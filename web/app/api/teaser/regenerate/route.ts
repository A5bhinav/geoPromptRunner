/**
 * POST /api/teaser/regenerate — rebuild a teaser from a previously-saved draft's
 * STORED report + answers, with no engine calls (no re-running the audit).
 *
 * Runs the teaser package's regenerate entrypoint (src/render/regenCli.ts) as a
 * child Node process: it re-runs finding selection + copy + render with the
 * current code, so teaser improvements reach an already-run prospect for free.
 * Returns { ok, draft, html } — the caller can preview it and Save it as a new
 * teaser. Mirrors /api/teaser/render so the teaser package stays the single
 * source of truth for the pipeline.
 */

import { spawn } from "node:child_process";
import { join } from "node:path";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TEASER_DIR = join(process.cwd(), "..", "teaser");

interface RegenRequest {
  draft?: unknown;
}

function runRegen(payload: string): Promise<string> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(
      process.execPath,
      ["--experimental-strip-types", "src/render/regenCli.ts"],
      { cwd: TEASER_DIR, env: process.env },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolvePromise(stdout);
      else reject(new Error(stderr.trim() || `regenCli exited ${code}`));
    });
    child.stdin.on("error", () => {/* ignore EPIPE if the child died early */});
    child.stdin.write(payload);
    child.stdin.end();
  });
}

export async function POST(req: Request): Promise<NextResponse> {
  let body: RegenRequest;
  try {
    body = (await req.json()) as RegenRequest;
  } catch {
    return NextResponse.json({ ok: false, reason: "invalid JSON body" }, { status: 400 });
  }
  if (!body.draft || typeof body.draft !== "object") {
    return NextResponse.json({ ok: false, reason: "draft is required" }, { status: 400 });
  }

  try {
    const out = await runRegen(JSON.stringify({ draft: body.draft }));
    const parsed = JSON.parse(out) as { ok: boolean; draft?: unknown; html?: string; reason?: string };
    if (!parsed.ok) {
      return NextResponse.json({ ok: false, reason: parsed.reason ?? "regenerate failed" }, { status: 422 });
    }
    return NextResponse.json({ ok: true, draft: parsed.draft, html: parsed.html });
  } catch (err) {
    const reason = err instanceof Error ? err.message : "failed to regenerate teaser";
    return NextResponse.json({ ok: false, reason }, { status: 500 });
  }
}
