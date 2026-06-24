/**
 * Load environment config so the teaser reuses the platform's EXISTING secrets
 * (ANTHROPIC_API_KEY, plus any GEO_* / CRAWL4AI_* settings) from the repo-root
 * `.env` — without duplicating the key anywhere.
 *
 * Why this is needed: the teaser runs as its own process (the `npm run teaser`
 * CLI, or a child of the web `/api/teaser` route) and does NOT inherit the
 * Python API's dotenv loading. Without this, `process.env.ANTHROPIC_API_KEY`
 * would be unset unless the launching shell happened to export it, and the
 * pipeline would silently fall back to the mock adapters.
 *
 * Precedence: variables already present in the process environment win — Node's
 * `loadEnvFile` does not override them — so an explicit `export ANTHROPIC_API_KEY`
 * (or a value injected by the spawning process) still takes priority over the
 * file. A teaser-local `teaser/.env`, if present, wins over the repo-root one.
 *
 * Side-effecting module: import it once, first, at a process entry point
 * (src/cli.ts). It is intentionally NOT imported by the library/test modules so
 * the test suite stays hermetic.
 */

import { existsSync } from "node:fs";
import { resolve } from "node:path";

// Highest priority first. loadEnvFile skips keys already set (including ones set
// by an earlier file in this list), so teaser-local overrides the repo root.
const candidates = [
  resolve(import.meta.dirname, "../.env"), // teaser/.env (optional, teaser-specific)
  resolve(import.meta.dirname, "../../.env"), // repo-root .env (the platform's shared keys)
];

for (const file of candidates) {
  if (!existsSync(file)) continue;
  try {
    process.loadEnvFile(file);
  } catch {
    // A malformed or unreadable .env must never crash the teaser run.
  }
}
