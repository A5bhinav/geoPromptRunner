/**
 * Dependency wiring. Each real adapter drops in here behind the same interface,
 * gated by an env var, with no change to the pipeline.
 *
 *   GEO_PLATFORM_URL  -> use HttpPlatformClient (real audits) instead of the mock
 *   CRAWL4AI_BASE_URL + ANTHROPIC_API_KEY -> real Crawl4aiClaudeResolver
 *   ANTHROPIC_API_KEY -> real ClaudeQuerySetGenerator
 *
 * All three adapters are now wireable. With no env at all the flow still runs
 * fully offline on the mocks; each real adapter lights up when its env is set.
 */

import { HttpPlatformClient } from "./platform/HttpPlatformClient.ts";
import { MockPlatformClient } from "./platform/MockPlatformClient.ts";
import { ClaudeQuerySetGenerator } from "./queryset/ClaudeQuerySetGenerator.ts";
import { MockQuerySetGenerator } from "./queryset/MockQuerySetGenerator.ts";
import { Crawl4aiClaudeResolver } from "./resolver/Crawl4aiClaudeResolver.ts";
import { FetchClaudeResolver } from "./resolver/FetchClaudeResolver.ts";
import { MockResolver } from "./resolver/MockResolver.ts";
import { hasClaudeKey } from "./llm/claude.ts";
import type { QuerySetGenerator } from "./queryset/QuerySetGenerator.ts";
import type { Resolver } from "./resolver/Resolver.ts";
import type { PlatformClient } from "./platform/PlatformClient.ts";
import type { PipelineDeps } from "./pipeline.ts";

/**
 * The platform adapter: real HttpPlatformClient when GEO_PLATFORM_URL points at
 * a running geoPromptRunner API, else the offline mock. Optional
 * GEO_PLATFORM_TIMEOUT_MS caps each HTTP call.
 */
function buildPlatform(): PlatformClient {
  const baseUrl = process.env.GEO_PLATFORM_URL;
  if (!baseUrl) return new MockPlatformClient();
  const rawTimeout = Number(process.env.GEO_PLATFORM_TIMEOUT_MS);
  const timeoutMs = Number.isFinite(rawTimeout) && rawTimeout > 0 ? rawTimeout : 0;
  // GEO_PLATFORM_API_KEY -> X-API-Key (needed when the platform sets GEO_API_KEY).
  const apiKey = process.env.GEO_PLATFORM_API_KEY;
  return new HttpPlatformClient({ baseUrl, timeoutMs, apiKey });
}

/** True when a real crawl4ai endpoint is configured (presence implies reachability intent). */
function crawl4aiConfigured(): boolean {
  return Boolean(process.env.CRAWL4AI_BASE_URL || process.env.CRAWL4AI_API_TOKEN);
}

/**
 * Resolver selection (in priority order):
 *   1. crawl4ai configured + Claude key -> Crawl4aiClaudeResolver (best: JS render)
 *   2. Claude key only                  -> FetchClaudeResolver (direct fetch, no Docker)
 *   3. neither                          -> MockResolver (offline, fabricated profile)
 *
 * The direct-fetch resolver makes real profiles work with just ANTHROPIC_API_KEY,
 * so an audit no longer silently falls back to a fabricated profile whenever the
 * crawl4ai container isn't running.
 */
function buildResolver(): Resolver {
  if (!hasClaudeKey()) return new MockResolver();
  if (crawl4aiConfigured()) return new Crawl4aiClaudeResolver();
  return new FetchClaudeResolver();
}

/**
 * Query-set generator: the real ClaudeQuerySetGenerator whenever a Claude key is
 * present (no crawler needed — it works off the profile); else the mock.
 */
function buildQuerySetGenerator(): QuerySetGenerator {
  if (hasClaudeKey()) return new ClaudeQuerySetGenerator();
  return new MockQuerySetGenerator();
}

export function buildDeps(): PipelineDeps {
  return {
    resolver: buildResolver(),
    querySetGenerator: buildQuerySetGenerator(),
    platform: buildPlatform(),
  };
}

/**
 * True while any adapter is still a mock (used by the CLI to warn). Real
 * coverage means: platform via GEO_PLATFORM_URL, resolver via crawl4ai+Claude,
 * and query-set generator via Claude.
 */
export function usingMocks(): boolean {
  const realPlatform = Boolean(process.env.GEO_PLATFORM_URL);
  const realResolver = hasClaudeKey(); // fetch resolver needs only the Claude key
  const realQuerySet = hasClaudeKey();
  return !(realPlatform && realResolver && realQuerySet);
}

/**
 * True when the PLATFORM adapter is the offline mock (no GEO_PLATFORM_URL).
 *
 * The poll cadence keys off this, NOT off usingMocks(): a real audit takes
 * minutes (poll on an interval), the mock returns "done" on the first poll —
 * and that is true regardless of whether the resolver / query-set generator are
 * still mocked. Using usingMocks() here would wrongly pick the instant cadence
 * for a real-platform run that happens to have a mock resolver.
 */
export function usingMockPlatform(): boolean {
  return !process.env.GEO_PLATFORM_URL;
}

/** Which adapter each dependency resolved to — "real" (live service) or "mock". */
export interface AdapterModes {
  platform: "real" | "mock";
  resolver: "real" | "mock";
  querySet: "real" | "mock";
}

/**
 * Report the real/mock mode of each adapter, using the exact same gates
 * buildDeps() uses. The teaser must surface this so a teaser built on a mock
 * resolver (a fabricated company profile) or mock platform (synthetic findings)
 * is never mistaken for a real audit.
 */
export function adapterModes(): AdapterModes {
  return {
    platform: process.env.GEO_PLATFORM_URL ? "real" : "mock",
    resolver: hasClaudeKey() ? "real" : "mock",
    querySet: hasClaudeKey() ? "real" : "mock",
  };
}

/** Names of the adapters currently running on a mock (empty list = fully real). */
export function mockedAdapters(): (keyof AdapterModes)[] {
  const modes = adapterModes();
  return (Object.keys(modes) as (keyof AdapterModes)[]).filter((k) => modes[k] === "mock");
}

/** How to make each adapter real — shown when --require-real aborts. */
export const REAL_ADAPTER_HINTS: Record<keyof AdapterModes, string> = {
  platform: "set GEO_PLATFORM_URL to a running platform API (e.g. http://localhost:8000)",
  resolver: "set ANTHROPIC_API_KEY (direct-fetch resolver); for JS-heavy sites also set CRAWL4AI_BASE_URL + start crawl4ai",
  querySet: "set ANTHROPIC_API_KEY",
};
