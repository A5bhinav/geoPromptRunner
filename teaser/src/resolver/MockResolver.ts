/**
 * MockResolver — derives a plausible CompanyProfile from the URL's hostname, with
 * no network and no LLM. Competitors are placeholders (clearly marked unconfirmed)
 * so the human input-confirm gate has something to correct.
 *
 * Replace with FirecrawlClaudeResolver (same interface) when scraping + a Claude
 * key are available. See BUILD_PLAN.md §4b.
 */

import type { CompanyProfile, Competitor } from "../types/domain.ts";
import type { Resolver } from "./Resolver.ts";

function hostnameOf(url: string): string {
  const withScheme = /^https?:\/\//.test(url) ? url : `https://${url}`;
  try {
    return new URL(withScheme).hostname.replace(/^www\./, "");
  } catch {
    return url.replace(/^www\./, "");
  }
}

/** "acme-hq.io" -> "Acme Hq" (a readable placeholder brand name). */
function brandFromHostname(host: string): string {
  const core = host.split(".")[0] ?? host;
  return core
    .split(/[-_]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export class MockResolver implements Resolver {
  async resolve(url: string): Promise<CompanyProfile> {
    const host = hostnameOf(url);
    const name = brandFromHostname(host);

    // Placeholder competitors — UNCONFIRMED on purpose; the input gate must fix
    // them. Deliberately DISTINCT from the client name (a real resolver returns
    // real rival brands; names that merely prefix the client would confuse entity
    // matching, which is exactly the kind of thing the human confirm gate catches).
    const competitors: Competitor[] = [
      { name: "Northstar", aliases: [], confirmed: false },
      { name: "Vantage", aliases: [], confirmed: false },
    ];

    return {
      url,
      name,
      category: "B2B SaaS tool", // placeholder; real resolver classifies the category
      competitors,
      clientDomains: [host],
      productClaims: [],
      resolvedAt: new Date(0).toISOString(), // fixed epoch -> deterministic in mock
      resolverModel: "mock",
    };
  }
}
