/**
 * Shared profile-extraction pieces used by every Claude-backed resolver
 * (crawl4ai-based and direct-fetch). One prompt, one schema, one normalizer so
 * the two resolvers can't drift. The CompanyProfile shape is EXACTLY
 * types/domain.ts; competitors always come back `confirmed:false` — the human
 * input-confirm gate is what flips them to true.
 */

import type { CompanyProfile, Competitor } from "../types/domain.ts";

/** Hostname (sans leading www.) — used for clientDomains + a name fallback. */
export function hostnameOf(url: string): string {
  const withScheme = /^https?:\/\//.test(url) ? url : `https://${url}`;
  try {
    return new URL(withScheme).hostname.replace(/^www\./, "");
  } catch {
    return url.replace(/^www\./, "");
  }
}

/** "acme-hq.io" -> "Acme Hq" — a readable name fallback if Claude omits one. */
export function brandFromHostname(host: string): string {
  const core = host.split(".")[0] ?? host;
  return core
    .split(/[-_]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** The raw shape Claude returns (validated/normalized into CompanyProfile). */
export interface ExtractedProfile {
  name: string;
  category: string;
  competitors: { name: string; aliases: string[] }[];
  clientDomains: string[];
  productClaims: { claim: string; sourceUrl: string }[];
}

/** JSON schema for the extraction. Every object: additionalProperties:false + all-required. */
export const PROFILE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    name: { type: "string" },
    category: { type: "string" },
    competitors: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          name: { type: "string" },
          aliases: { type: "array", items: { type: "string" } },
        },
        required: ["name", "aliases"],
      },
    },
    clientDomains: { type: "array", items: { type: "string" } },
    productClaims: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          claim: { type: "string" },
          sourceUrl: { type: "string" },
        },
        required: ["claim", "sourceUrl"],
      },
    },
  },
  required: ["name", "category", "competitors", "clientDomains", "productClaims"],
} as const;

export const PROFILE_SYSTEM_PROMPT = `You analyze a company's own website to build a structured profile for a competitive-visibility audit.

You will receive labeled text for one or more pages of a single company's site (homepage, and possibly a pricing/comparison page).

Return:
- name: the company's brand name as customers say it (not the legal entity, not the domain).
- category: a short, consumer-facing product category (e.g. "budgeting app", "smart ring", "meal-kit service"). Use the language a consumer would use, not internal jargon.
- competitors: 2-5 REAL rival brands a buyer would compare this company against. Use real, well-known competitor names — NOT made-up names and NOT names that merely prefix this company. For each, list any aliases/name variants (e.g. "WHOOP", "Whoop band"); use [] if none.
- clientDomains: domains owned by this company (include the site's own domain).
- productClaims: 0-6 concrete, falsifiable claims the site makes (pricing, a required subscription, a flagship feature, the current model/version) that could seed a fact sheet. sourceUrl is the page the claim came from. Use [] if you can't ground any.

Base everything ONLY on the provided page content. Do not invent competitors or claims you cannot support from the text.`;

/**
 * Normalize Claude's raw extraction into a CompanyProfile. Pure — no network,
 * no LLM — so it can be unit-tested. Enforces the domain invariants:
 *   - competitors are de-duped, non-empty, and ALWAYS confirmed:false
 *   - clientDomains always includes the site host
 *   - name/category fall back to a hostname-derived brand if Claude returns blank
 */
export function buildProfile(
  url: string,
  extracted: ExtractedProfile,
  resolverModel: string,
  now: Date = new Date(),
): CompanyProfile {
  const host = hostnameOf(url);

  const name = extracted.name.trim() || brandFromHostname(host);
  const category = extracted.category.trim() || "product";

  const competitors: Competitor[] = [];
  const seen = new Set<string>();
  for (const c of extracted.competitors) {
    const cname = c.name.trim();
    if (!cname) continue;
    const key = cname.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    competitors.push({
      name: cname,
      aliases: (c.aliases ?? []).map((a) => a.trim()).filter(Boolean),
      confirmed: false, // the human input gate confirms competitors
    });
  }

  const clientDomains: string[] = [];
  const seenDomains = new Set<string>();
  for (const d of [host, ...extracted.clientDomains]) {
    const dd = d.trim().toLowerCase().replace(/^www\./, "");
    if (!dd || seenDomains.has(dd)) continue;
    seenDomains.add(dd);
    clientDomains.push(dd);
  }

  const productClaims = (extracted.productClaims ?? [])
    .map((pc) => ({ claim: pc.claim.trim(), sourceUrl: pc.sourceUrl.trim() }))
    .filter((pc) => pc.claim);

  return {
    url,
    name,
    category,
    competitors,
    clientDomains,
    productClaims,
    resolvedAt: now.toISOString(),
    resolverModel,
  };
}
