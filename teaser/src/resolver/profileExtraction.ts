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

/**
 * Below this many chars of readable text across the fetched page(s), we REFUSE to
 * profile. A bot-challenge interstitial (Cloudflare's "Just a moment…" is served
 * at HTTP 200) or a JS-only SPA shell yields only a few words of noise, and
 * extracting a company profile from that risks a hallucinated name/competitors
 * that poison the whole teaser (the Mint/MyFitnessPal failure class, from a bad
 * fetch). Failing here — no teaser — is the safe direction. A real homepage has
 * thousands of chars; genuine sub-threshold pages can't yield competitors anyway.
 */
export const MIN_PROFILE_TEXT_CHARS = 200;

/** Total readable characters across the pages handed to the profiler. Pure. */
export function profileTextLength(texts: readonly string[]): number {
  return texts.reduce((n, t) => n + (t ?? "").trim().length, 0);
}

/**
 * Throw unless the fetched pages carry enough readable text to profile. Callers
 * pass the per-page text (FetchClaudeResolver) or markdown (Crawl4ai) they were
 * about to hand to Claude — so a thin/challenge/shell page fails fast with a
 * clear, actionable message instead of producing a fabricated profile.
 */
export function assertSufficientProfileText(texts: readonly string[], url: string): void {
  const chars = profileTextLength(texts);
  if (chars < MIN_PROFILE_TEXT_CHARS) {
    throw new Error(
      `insufficient content to profile ${url} (${chars} readable chars, need ` +
        `${MIN_PROFILE_TEXT_CHARS}). The page is likely JS-only or bot-blocked ` +
        `(a challenge or SPA shell served at 200) — profiling from noise would ` +
        `fabricate the company/competitors. Try crawl4ai or a different URL.`,
    );
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
  /** Known variants of the CLIENT's own brand name (optional for legacy fixtures). */
  aliases?: string[];
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
    aliases: { type: "array", items: { type: "string" } },
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
  required: ["name", "aliases", "category", "competitors", "clientDomains", "productClaims"],
} as const;

export const PROFILE_SYSTEM_PROMPT = `You analyze a company's own website to build a structured profile for a competitive-visibility audit.

You will receive labeled text for one or more pages of a single company's site (homepage, and possibly a pricing/comparison page).

Return:
- name: the company's brand name as customers say it (not the legal entity, not the domain).
- aliases: known variants of the CLIENT's OWN name (a shortened form, an abbreviation, a common misspelling, e.g. "YNAB" for "You Need A Budget"). Use [] if none.
- category: the MOST SPECIFIC consumer-facing category that distinguishes this company from ADJACENT products — the narrow sub-category a buyer cross-shopping DIRECT substitutes would name, not the generic parent. Return the narrowest TRUE category, e.g. "strength-training wearable" NOT "fitness tracker"; "zero-based budgeting app" NOT "finance app"; "meal-kit delivery service" NOT "food app". Use consumer language, not internal jargon — but do NOT broaden to a generic parent category.
- competitors: 2-5 REAL, CURRENTLY-OPERATING rival brands. Each MUST be a DIRECT SUBSTITUTE in the SAME specific category above — a product a buyer would genuinely cross-shop against this company, NOT merely an adjacent product or a famous brand in the broader parent category (e.g. for a strength-training wearable, do NOT return a general fitness tracker just because it's well known). Use real, well-known names — NOT made-up names and NOT names that merely prefix this company. EXCLUDE any product that has been discontinued, shut down, or sunset and no longer serves customers (a dead brand poisons the audit — buyers can't switch to a product that no longer exists). For each, list any aliases/name variants (e.g. "WHOOP", "Whoop band"); use [] if none.
- clientDomains: domains owned by this company (include the site's own domain).
- productClaims: 0-6 concrete, falsifiable claims the site makes (pricing, a required subscription, a flagship feature, the current model/version) that could seed a fact sheet. sourceUrl is the page the claim came from. Use [] if you can't ground any.

Base everything ONLY on the provided page content. Do not invent competitors or claims you cannot support from the text.`;

/**
 * Discontinued / shut-down brands that must NEVER seed a teaser. A defunct
 * competitor in the profile makes the query generator emit "alternatives to
 * <dead brand>" questions and pick an embarrassing hero — observed live with
 * Mint (Intuit shut it down 2024-03-23) on 2026-07-03. This is a hand-maintained
 * DETERMINISTIC backstop; the extraction prompt is the primary, general filter.
 * Keep entries HIGH-CONFIDENCE: a wrong entry silently drops a live rival.
 * Match is case-insensitive against the competitor name OR any of its aliases.
 */
export interface DefunctBrand {
  /** Canonical name plus known variant spellings. Matched lowercased. */
  names: string[];
  /** Why it's out — dated, so the list can be re-audited over time. */
  note: string;
}

export const DEFUNCT_BRANDS: readonly DefunctBrand[] = [
  {
    names: ["mint", "mint.com", "intuit mint", "mint by intuit"],
    note: "Intuit shut Mint down 2024-03-23; users redirected to Credit Karma.",
  },
];

const DEFUNCT_LOOKUP: ReadonlySet<string> = new Set(
  DEFUNCT_BRANDS.flatMap((b) => b.names.map((n) => n.toLowerCase())),
);

/**
 * True when a competitor's name or any alias matches a known-defunct brand.
 * Pure — safe to unit-test and to call from buildProfile's normalizer.
 */
export function isDefunctBrand(name: string, aliases: readonly string[] = []): boolean {
  return [name, ...aliases]
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean)
    .some((c) => DEFUNCT_LOOKUP.has(c));
}

/**
 * Normalize Claude's raw extraction into a CompanyProfile. Pure — no network,
 * no LLM — so it can be unit-tested. Enforces the domain invariants:
 *   - competitors are de-duped, non-empty, ALWAYS confirmed:false, and any
 *     known-defunct brand (DEFUNCT_BRANDS) is dropped
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
  // A blank (or degenerate "product") category is a HARD FAILURE, not a silent
  // fallback: the old `|| "product"` produced "best product for a growing
  // startup" queries and a bland-but-wrong teaser that could still be sent. If
  // the resolver couldn't name a real category, we'd rather build no teaser (the
  // same safe direction as assertSufficientProfileText). Audit finding C6.
  const category = extracted.category.trim();
  if (!category || category.toLowerCase() === "product") {
    throw new Error(
      `resolver could not determine a specific product category for ${url} ` +
        `(got ${JSON.stringify(extracted.category)}). Profiling would emit generic ` +
        `"best product" queries — refusing to build a teaser from an empty category.`,
    );
  }

  const aliases: string[] = [];
  const seenAliases = new Set<string>([name.toLowerCase()]);
  for (const a of extracted.aliases ?? []) {
    const trimmed = a.trim();
    const key = trimmed.toLowerCase();
    if (!trimmed || seenAliases.has(key)) continue; // drop blanks, the name itself, and dups
    seenAliases.add(key);
    aliases.push(trimmed);
  }

  const competitors: Competitor[] = [];
  const seen = new Set<string>();
  for (const c of extracted.competitors) {
    const cname = c.name.trim();
    if (!cname) continue;
    const key = cname.toLowerCase();
    if (seen.has(key)) continue;
    const aliases = (c.aliases ?? []).map((a) => a.trim()).filter(Boolean);
    // Drop discontinued brands before they can seed queries or become the hero.
    if (isDefunctBrand(cname, aliases)) continue;
    seen.add(key);
    competitors.push({
      name: cname,
      aliases,
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
    aliases,
    category,
    competitors,
    clientDomains,
    productClaims,
    resolvedAt: now.toISOString(),
    resolverModel,
  };
}
