/**
 * Regenerate-only entrypoint: read {draft} JSON from stdin (a previously-saved
 * teaser, which carries its stored report + answers), re-run selection + copy +
 * render with the CURRENT code, and print {ok, draft, html} JSON to stdout.
 *
 * No engine calls — this is the "regenerate without re-running the audit" path:
 * it pulls everything from the saved report/answers, so teaser improvements reach
 * an already-run prospect for free. Mirrors renderCli.ts (used by the web route).
 *
 *   node --experimental-strip-types src/render/regenCli.ts  < saved-draft.json
 */

import { regenerateFromDraft } from "../pipeline.ts";
import { renderTeaserHtml } from "./template.ts";
import type { TeaserDraft } from "../types/domain.ts";

interface RegenPayload {
  draft: TeaserDraft;
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString("utf8");
}

async function main(): Promise<void> {
  const raw = await readStdin();
  let payload: RegenPayload;
  try {
    payload = JSON.parse(raw) as RegenPayload;
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, reason: `invalid JSON on stdin: ${String(err)}` }));
    return;
  }
  if (!payload || typeof payload.draft !== "object" || payload.draft === null) {
    process.stdout.write(JSON.stringify({ ok: false, reason: "payload.draft is required" }));
    return;
  }

  const result = regenerateFromDraft(payload.draft);
  if (!result.ok) {
    process.stdout.write(JSON.stringify({ ok: false, reason: result.reason }));
    return;
  }
  const html = renderTeaserHtml(result.draft);
  process.stdout.write(JSON.stringify({ ok: true, draft: result.draft, html }));
}

main().catch((err) => {
  process.stdout.write(
    JSON.stringify({ ok: false, reason: err instanceof Error ? err.message : String(err) }),
  );
  process.exit(1);
});
