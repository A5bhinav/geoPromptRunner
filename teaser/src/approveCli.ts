/**
 * CLI: `npm run approve -- <teaserId>`
 *
 * The human sign-off gate, drivable headless. A generated teaser is persisted as
 * a DRAFT (it renders a "not for sending" banner); approving flips it to
 * status="approved" on the platform (POST /teasers/{id}/approve), which is the
 * transition that clears the banner on the next render. Only an approved teaser
 * is meant to be sent.
 *
 * Requires GEO_PLATFORM_URL (+ GEO_PLATFORM_API_KEY) — there's no local teasers
 * store to approve against.
 */

import "./env.ts";

import { buildDeps } from "./config.ts";
import { usingMockPlatform } from "./config.ts";

async function main(): Promise<void> {
  const teaserId = process.argv.slice(2).find((a) => a && !a.startsWith("--"));
  if (!teaserId) {
    console.error("usage: npm run approve -- <teaserId>");
    process.exit(1);
    return;
  }
  if (usingMockPlatform()) {
    console.error(
      "✗ no platform configured (GEO_PLATFORM_URL unset) — nothing to approve. " +
        "Approval writes to the platform's teasers store.",
    );
    process.exit(2);
    return;
  }

  const ok = await buildDeps().platform.approveTeaser(teaserId);
  if (!ok) {
    console.error(
      `✗ could not approve teaser ${teaserId} — check the id, GEO_PLATFORM_URL, and GEO_PLATFORM_API_KEY.`,
    );
    process.exit(2);
    return;
  }
  console.log(`✓ teaser ${teaserId} approved — re-render (regen) to drop the draft banner before sending.`);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
