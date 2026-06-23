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
 * Resolver: the real Crawl4aiClaudeResolver when crawl4ai is configured AND a
 * Claude key is present (both are needed — crawl for markdown, Claude to extract);
 * otherwise the offline MockResolver.
 */
function buildResolver(): Resolver {
  if (crawl4aiConfigured() && hasClaudeKey()) return new Crawl4aiClaudeResolver();
  return new MockResolver();
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
  const realResolver = crawl4aiConfigured() && hasClaudeKey();
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
