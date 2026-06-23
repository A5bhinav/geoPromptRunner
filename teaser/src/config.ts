/**
 * Dependency wiring. Each real adapter drops in here behind the same interface,
 * gated by an env var, with no change to the pipeline.
 *
 *   GEO_PLATFORM_URL  -> use HttpPlatformClient (real audits) instead of the mock
 *   FIRECRAWL_API_KEY -> use the real resolver (later)
 *   ANTHROPIC_API_KEY -> use the Claude query-set generator (later)
 *
 * The platform adapter is wired; resolver + query-set generator stay mocked so
 * the flow still runs with only the platform reachable (and fully offline with
 * no env at all).
 */

import { HttpPlatformClient } from "./platform/HttpPlatformClient.ts";
import { MockPlatformClient } from "./platform/MockPlatformClient.ts";
import { MockQuerySetGenerator } from "./queryset/MockQuerySetGenerator.ts";
import { MockResolver } from "./resolver/MockResolver.ts";
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

export function buildDeps(): PipelineDeps {
  // TODO(real adapters):
  //   if (process.env.FIRECRAWL_API_KEY) resolver = new FirecrawlResolver(...)
  //   if (process.env.ANTHROPIC_API_KEY) querySetGenerator = new ClaudeQuerySetGenerator(...)
  return {
    resolver: new MockResolver(),
    querySetGenerator: new MockQuerySetGenerator(),
    platform: buildPlatform(),
  };
}

/** True once any real adapter is configured (used by the CLI to warn). */
export function usingMocks(): boolean {
  return !process.env.GEO_PLATFORM_URL;
}
