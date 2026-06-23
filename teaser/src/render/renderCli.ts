/**
 * Render-only entrypoint: read {draft, edits} JSON from stdin and print the
 * teaser one-pager HTML to stdout.
 *
 * Used by the web review UI (web/app/api/teaser/render) to re-render the
 * printable copy when a reviewer edits headline/lead/stakes/CTA, so those edits
 * actually reach the downloaded HTML/PDF instead of being saved but ignored.
 *
 *   node --experimental-strip-types src/render/renderCli.ts  < payload.json
 */

import { renderTeaserHtml, type TeaserEdits } from "./template.ts";
import type { TeaserDraft } from "../types/domain.ts";

interface RenderPayload {
  draft: TeaserDraft;
  edits?: TeaserEdits;
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
    process.stderr.write(`renderCli: invalid JSON on stdin: ${String(err)}\n`);
    process.exit(1);
    return;
  }
  if (!payload || typeof payload.draft !== "object" || payload.draft === null) {
    process.stderr.write("renderCli: payload.draft is required\n");
    process.exit(1);
    return;
  }
  process.stdout.write(renderTeaserHtml(payload.draft, payload.edits ?? {}));
}

main().catch((err) => {
  process.stderr.write(`renderCli: ${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
});
