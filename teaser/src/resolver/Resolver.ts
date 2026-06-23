/**
 * Resolver: URL -> CompanyProfile.
 *
 * Real implementation (later): Firecrawl/Jina to fetch homepage + comparison
 * pages -> Claude to extract name/category/competitors/domains. MockResolver
 * returns a deterministic profile derived from the hostname so the flow runs
 * with no scraper and no LLM key.
 */

import type { CompanyProfile } from "../types/domain.ts";

export interface Resolver {
  resolve(url: string): Promise<CompanyProfile>;
}
