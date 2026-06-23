/**
 * POST /api/teaser/render — re-render a teaser's printable HTML from its draft
 * plus reviewer copy edits.
 *
 * Mirrors /api/teaser: runs the teaser package's render-only entrypoint
 * (src/render/renderCli.ts) as a child Node process and returns the HTML, so the
 * single source of truth for the one-pager layout stays in the teaser package.
 * The review UI calls this when a reviewer edits headline/lead/stakes/CTA, then
 * persists the returned HTML so the downloaded PDF/HTML reflects the edits.
 */

import { spawn } from "node:child_process";
import { join } from "node:path";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TEASER_DIR = join(process.cwd(), "..", "teaser");

interface RenderRequest {
  draft?: unknown;
  edited_fields?: unknown;
}

function runRenderer(payload: string): Promise<string> {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(
      process.execPath,
      ["--experimental-strip-types", "src/render/renderCli.ts"],
      { cwd: TEASER_DIR, env: process.env },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolvePromise(stdout);
      else reject(new Error(stderr.trim() || `renderCli exited ${code}`));
    });
    child.stdin.on("error", () => {/* ignore EPIPE if the child died early */});
    child.stdin.write(payload);
    child.stdin.end();
  });
}

export async function POST(req: Request): Promise<NextResponse> {
  let body: RenderRequest;
  try {
    body = (await req.json()) as RenderRequest;
  } catch {
    return NextResponse.json({ ok: false, reason: "invalid JSON body" }, { status: 400 });
  }
  if (!body.draft || typeof body.draft !== "object") {
    return NextResponse.json({ ok: false, reason: "draft is required" }, { status: 400 });
  }

  const edits =
    body.edited_fields && typeof body.edited_fields === "object" ? body.edited_fields : {};
  try {
    const html = await runRenderer(JSON.stringify({ draft: body.draft, edits }));
    return NextResponse.json({ ok: true, html });
  } catch (err) {
    const reason = err instanceof Error ? err.message : "failed to render teaser";
    return NextResponse.json({ ok: false, reason }, { status: 500 });
  }
}
