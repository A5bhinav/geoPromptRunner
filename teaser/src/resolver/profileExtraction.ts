/**
 * Shared profile-extraction pieces used by every Claude-backed resolver
 * (crawl4ai-based and direct-fetch). One prompt, one schema, one normalizer so
 * the two resolvers can't drift. The CompanyProfile shape is EXACTLY
 * types/domain.ts; competitors always come back `confirmed:false` — the human
 * input-confirm gate is what flips them to true.
 */

import type {
  BusinessKind,
  BusinessLocation,
  CompanyProfile,
  Competitor,
} from "../types/domain.ts";

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
  /**
   * Which ICP this site is (W0.1). Optional here for legacy fixtures only — the
   * schema marks it required, so a live extraction always returns it. Same
   * precedent as `aliases`. Absent is treated as `product` by `buildProfile`.
   */
  businessKind?: BusinessKind;
  /**
   * NAP-sourced location (W1.2). `null` (not omitted) when the business is not
   * service-area-bound — the schema requires the key so Claude must decide, rather
   * than dropping it and leaving us unable to distinguish "no location" from
   * "forgot to look".
   */
  location?: BusinessLocation | null;
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
    businessKind: { type: "string", enum: ["product", "local_service"] },
    location: {
      type: ["object", "null"],
      additionalProperties: false,
      properties: {
        city: { type: "string" },
        region: { type: "string" },
        country: { type: "string" },
        serviceArea: { type: "array", items: { type: "string" } },
      },
      required: ["city", "region", "country", "serviceArea"],
    },
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
  required: [
    "name",
    "aliases",
    "businessKind",
    "location",
    "category",
    "competitors",
    "clientDomains",
    "productClaims",
  ],
} as const;

export const PROFILE_SYSTEM_PROMPT = `You analyze a company's own website to build a structured profile for a competitive-visibility audit.

You will receive labeled text for one or more pages of a single company's site (homepage, and possibly a pricing/comparison page).

Return:
- name: the company's brand name as customers say it (not the legal entity, not the domain).
- aliases: known variants of the CLIENT's OWN name (a shortened form, an abbreviation, a common misspelling, e.g. "YNAB" for "You Need A Budget"). Use [] if none.
- businessKind: "local_service" if this business serves customers in a specific geographic area and buyers would choose it BASED ON LOCATION — a plumber, HVAC contractor, barbershop, salon, dentist, auto repair shop, roofer, landscaper, restaurant. Signals: a street address or service-area list, "serving <city/county>", phone-first calls-to-action, "near you", licence numbers, emergency/same-day availability. Otherwise "product" — something sold or delivered nationally/online where the buyer's city is irrelevant (an app, a device, a subscription, a DTC brand, a SaaS tool). A company with physical stores is still "product" if buyers nationwide use it without regard to location.
- location: for a "local_service" business ONLY, where it actually serves customers, read from the site's own NAP block (the footer address, a contact/locations page, or schema.org LocalBusiness markup). city = the primary city it operates from; region = the state/province SPELLED AS THE SITE SPELLS IT ("California", not "CA"); country = ISO-3166 alpha-2 uppercase ("US"); serviceArea = any ADDITIONAL named towns, neighborhoods or counties the site explicitly says it serves (use [] if it names none). Return null when the site is not service-area-bound, or when you cannot find a real address/service area on the page — do NOT infer a location from the brand name, a phone area code, or general knowledge. A guessed city silently geo-anchors every query to the wrong place.
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
 * Normalize an extracted location, or return undefined. Pure.
 *
 * Anti-fabrication, matching the posture of every other resolver guard: a location
 * is kept ONLY when city, region and country are all non-blank. A partial location
 * ("Berkeley", no state) would serialize to a canonical string SearchApi resolves to
 * "the most popular match" — which for an ambiguous city name is a different metro
 * entirely, silently measuring the wrong market. Dropping to undefined makes the
 * absence visible instead.
 */
export function normalizeLocation(raw: BusinessLocation | null | undefined): BusinessLocation | undefined {
  if (!raw) return undefined;

  const city = (raw.city ?? "").trim();
  const region = (raw.region ?? "").trim();
  const country = (raw.country ?? "").trim().toUpperCase();
  if (!city || !region || !country) return undefined;

  const seen = new Set<string>();
  const serviceArea: string[] = [];
  for (const area of raw.serviceArea ?? []) {
    const trimmed = (area ?? "").trim();
    const key = trimmed.toLowerCase();
    // Drop blanks, dups, and the primary city echoed back as its own service area.
    if (!trimmed || key === city.toLowerCase() || seen.has(key)) continue;
    seen.add(key);
    serviceArea.push(trimmed);
  }

  return serviceArea.length > 0
    ? { city, region, country, serviceArea }
    : { city, region, country };
}

/**
 * The ICP a profile belongs to, with the one canonical default. Absent means
 * `product`, so every legacy/mock/stored profile keeps its existing behaviour.
 * Read business kind through THIS, never by defaulting inline — the pivot's whole
 * §0.6 fork-by-kind rule rests on one agreed fallback.
 */
export function businessKindOf(profile: Pick<CompanyProfile, "businessKind">): BusinessKind {
  return profile.businessKind ?? "product";
}

/**
 * Whether the local-service path is compiled in and safe to route to.
 *
 * W0.1 shipped the CLASSIFIER while the local path was still being built, so a
 * local_service site was REFUSED rather than silently mis-profiled. **W2.4 flipped
 * this to `true`**: local query generation (W2.2/W2.3), entity-sourced competitors
 * (W1.6 + `attachLocalCompetitors`), geographic competitor validation (W2.5) and
 * local copy (W2.6) all exist now.
 *
 * Note this gate never guarded competitor fabrication on its own — that is enforced
 * structurally: `buildProfile` returns a local profile with NO competitors, and only
 * `attachLocalCompetitors` (which requires captured local-pack entities) can add
 * them. Flipping this flag cannot produce an invented rival.
 */
export const LOCAL_SERVICE_PATH_READY = true;

/**
 * Refuse to profile a service-area business until the local path exists.
 *
 * Pointing the teaser at a plumber today does not error — it emits a confident,
 * plausible, WRONG artifact. The extraction prompt asks for "REAL,
 * CURRENTLY-OPERATING rival brands... use real, well-known names", which for a local
 * trade yields national franchises or invented locals rather than the shops across
 * town. For a cold-outreach artifact, silent-and-wrong is materially worse than
 * crashing — the same principle as the mock-adapter refusal in cli.ts and the
 * thin-content refusal in assertSufficientProfileText.
 */
export function assertSupportedBusinessKind(kind: BusinessKind, url: string): void {
  if (kind === "local_service" && !LOCAL_SERVICE_PATH_READY) {
    throw new Error(
      `${url} looks like a local service-area business, and the local path is not ` +
        `built yet (see docs/smb-pivot-build-plan.md Phases 1-2). Profiling it on the ` +
        `consumer path would name national franchises or invented locals as its ` +
        `"competitors" and produce a confident, wrong teaser — refusing to build one. ` +
        `Re-run once the local path ships, or point this at a consumer product.`,
    );
  }
}

/** A captured local-pack business, as the platform's /local-entities returns it. */
export interface CapturedLocalEntity {
  name: string;
  address: string;
  category: string;
  rating: number | null;
  reviews: number | null;
  ludocid: string | null;
  position: number | null;
}

/** How many local rivals a teaser names. Matches the consumer path's 2-5 band. */
export const MAX_LOCAL_COMPETITORS = 4;

/**
 * Attach local competitors to a local-service profile from CAPTURED entities (W2.4).
 *
 * The only sanctioned way a local rival gets named. Pure — the caller does the
 * capture (`PlatformClient.getLocalEntities`) and hands the results in, so this stays
 * unit-testable and the fabrication guarantee is checkable without a network.
 *
 * Throws when no usable entity survives. **That is deliberate and load-bearing**: the
 * alternative is a teaser that says "AI recommends <nobody> instead of you", or worse,
 * one that falls back to model recall. Failing loudly here is the same safe direction
 * as `assertSufficientProfileText` and the blank-category throw.
 *
 * Entities matching the client itself are dropped — Google's local pack naturally
 * returns the client, and naming a shop as its own competitor is an obvious tell that
 * the artifact is machine-generated.
 */
export function attachLocalCompetitors(
  profile: CompanyProfile,
  entities: readonly CapturedLocalEntity[],
): CompanyProfile {
  if (businessKindOf(profile) !== "local_service") {
    throw new Error(
      `attachLocalCompetitors is for local_service profiles; ${profile.url} is a ` +
        `product. Consumer competitors come from the resolver's extraction.`,
    );
  }

  const clientKeys = new Set(
    [profile.name, ...(profile.aliases ?? [])].map((n) => n.trim().toLowerCase()).filter(Boolean),
  );

  const competitors: Competitor[] = [];
  const seen = new Set<string>();
  for (const entity of entities) {
    const name = (entity.name ?? "").trim();
    const key = name.toLowerCase();
    if (!name || seen.has(key) || clientKeys.has(key)) continue;
    seen.add(key);
    competitors.push({ name, aliases: [], confirmed: false }); // human gate confirms
    if (competitors.length >= MAX_LOCAL_COMPETITORS) break;
  }

  if (competitors.length === 0) {
    throw new Error(
      `no local competitors could be sourced for ${profile.url} from the captured ` +
        `local pack (${entities.length} entities, none usable after dropping the ` +
        `client itself). Refusing to build a local teaser — naming a rival from model ` +
        `recall instead is the one failure that survives human review.`,
    );
  }

  return { ...profile, competitors };
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

  // Business kind is checked FIRST: on a local-service site every downstream field
  // (category, competitors, claims) is extracted by consumer-shaped instructions and
  // is therefore untrustworthy. Fail before any of it can be normalized into a
  // sendable-looking profile.
  const businessKind = extracted.businessKind ?? "product";
  assertSupportedBusinessKind(businessKind, url);

  // A product has no service area by definition. Discarding any location the model
  // volunteered for one keeps "absent" meaningful on the consumer path, so nothing
  // downstream can geo-anchor a nationally-marketed product's queries.
  const location =
    businessKind === "local_service" ? normalizeLocation(extracted.location) : undefined;

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

  // W2.4 — THE anti-fabrication guarantee, enforced structurally rather than by
  // prompt discipline. On the local path the model's `competitors` are DISCARDED
  // wholesale: the extraction prompt asks for "REAL, CURRENTLY-OPERATING rival
  // brands... use real, well-known names", which for a local trade yields national
  // franchises (Roto-Rooter, Supercuts) or plausible-sounding inventions. A local
  // profile therefore leaves buildProfile with NO competitors, and only
  // attachLocalCompetitors — which requires captured local-pack entities — can add
  // them. There is no code path from LLM recall to a named local rival.
  const competitors: Competitor[] = [];
  const seen = new Set<string>();
  const sourced = businessKind === "local_service" ? [] : extracted.competitors;
  for (const c of sourced) {
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
    businessKind,
    ...(location ? { location } : {}),
    category,
    competitors,
    clientDomains,
    productClaims,
    resolvedAt: now.toISOString(),
    resolverModel,
  };
}
