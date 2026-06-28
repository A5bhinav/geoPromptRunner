/**
 * Audit render-only entrypoint: read {draft, edits} JSON from stdin and print the
 * AI Visibility Audit HTML to stdout. Used by the web review UI
 * (web/app/api/audit/render) to re-render when a reviewer edits the headline /
 * verdict / engagement copy, so those edits reach the downloaded HTML/PDF.
 *
 *   node --experimental-strip-types src/render/audit/renderCli.ts < payload.json
 */

import type { AuditDraft, AuditEdits } from "../../types/audit.ts";
import { renderAuditHtml } from "./template.ts";

interface RenderPayload {
  draft: AuditDraft;
  edits?: AuditEdits;
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("utf8");
}

async function main(): Promise<void> {
  const raw = await readStdin();
  let payload: RenderPayload;
  try {
    payload = JSON.parse(raw) as RenderPayload;
  } catch (err) {
    process.stderr.write(`audit renderCli: invalid JSON on stdin: ${String(err)}\n`);
    process.exit(1);
    return;
  }
  if (!payload || typeof payload.draft !== "object" || payload.draft === null) {
    process.stderr.write("audit renderCli: payload.draft is required\n");
    process.exit(1);
    return;
  }
  process.stdout.write(renderAuditHtml(payload.draft, payload.edits ?? {}));
}

main().catch((err) => {
  process.stderr.write(`audit renderCli: ${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
});
