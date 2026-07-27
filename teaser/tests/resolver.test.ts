/**
 * Unit tests for the PURE resolver helpers: profile normalization from Claude's
 * raw extraction, the labeled-markdown builder, and crawl4ai internal-link
 * picking. No network, no LLM.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildProfile,
  buildExtractionInput,
  isDefunctBrand,
} from "../src/resolver/Crawl4aiClaudeResolver.ts";
import { pickInternalTargets } from "../src/resolver/Crawl4aiClient.ts";
import { canonicalLocation } from "../src/types/domain.ts";
import {
  MIN_PROFILE_TEXT_CHARS,
  LOCAL_SERVICE_PATH_READY,
  PROFILE_SCHEMA,
  PROFILE_SYSTEM_PROMPT,
  assertSufficientProfileText,
  assertSupportedBusinessKind,
  businessKindOf,
  attachLocalCompetitors,
  MAX_LOCAL_COMPETITORS,
  normalizeLocation,
  profileTextLength,
} from "../src/resolver/profileExtraction.ts";

const FIXED = new Date("2026-06-22T00:00:00.000Z");

function extracted(over: Record<string, unknown> = {}) {
  return {
    name: "Acme",
    category: "CRM",
    competitors: [
      { name: "Salesforce", aliases: ["SFDC"] },
      { name: "HubSpot", aliases: [] },
    ],
    clientDomains: ["acme.io"],
    productClaims: [{ claim: "Free tier available", sourceUrl: "https://acme.io/pricing" }],
    ...over,
  } as Parameters<typeof buildProfile>[1];
}

test("buildProfile maps a clean extraction into the exact CompanyProfile shape", () => {
  const p = buildProfile("https://www.acme.io", extracted(), "claude-opus-4-8", FIXED);
  assert.equal(p.url, "https://www.acme.io");
  assert.equal(p.name, "Acme");
  assert.equal(p.category, "CRM");
  assert.equal(p.resolverModel, "claude-opus-4-8");
  assert.equal(p.resolvedAt, "2026-06-22T00:00:00.000Z");
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["Salesforce", "HubSpot"],
  );
  // Competitors ALWAYS come back unconfirmed — the human gate confirms them.
  for (const c of p.competitors) assert.equal(c.confirmed, false);
  assert.deepEqual(p.competitors[0]?.aliases, ["SFDC"]);
  assert.equal(p.productClaims.length, 1);
});

test("client host is always present in clientDomains (sans www, deduped)", () => {
  const p = buildProfile("https://www.acme.io", extracted({ clientDomains: ["acme.io", "ACME.io"] }), "m", FIXED);
  assert.deepEqual(p.clientDomains, ["acme.io"]);
});

test("blank name falls back to a hostname-derived brand (category present)", () => {
  const p = buildProfile(
    "https://acme-hq.io",
    extracted({ name: "  " }),
    "m",
    FIXED,
  );
  assert.equal(p.name, "Acme Hq");
  assert.equal(p.category, "CRM");
});

// C6: a blank or degenerate "product" category is a HARD FAILURE, not a silent
// "best product for a growing startup" teaser. buildProfile refuses to build one.
test("blank category is a hard failure (throws)", () => {
  assert.throws(
    () => buildProfile("https://acme-hq.io", extracted({ category: "" }), "m", FIXED),
    /could not determine a specific product category/,
  );
});

test('a degenerate "product" category also hard-fails', () => {
  assert.throws(
    () => buildProfile("https://acme-hq.io", extracted({ category: "product" }), "m", FIXED),
    /could not determine a specific product category/,
  );
});

// S4: client aliases are normalized (trimmed, de-duped vs the name) onto the profile.
test("client aliases are threaded onto the profile", () => {
  const p = buildProfile(
    "https://ynab.com",
    extracted({ name: "You Need A Budget", aliases: ["YNAB", " YNAB ", "You Need A Budget"] }),
    "m",
    FIXED,
  );
  assert.deepEqual(p.aliases, ["YNAB"]);
});

test("competitors are de-duped case-insensitively and blanks dropped", () => {
  const p = buildProfile(
    "https://acme.io",
    extracted({
      competitors: [
        { name: "Salesforce", aliases: [] },
        { name: "salesforce", aliases: ["dup"] },
        { name: "  ", aliases: [] },
        { name: "HubSpot", aliases: [] },
      ],
    }),
    "m",
    FIXED,
  );
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["Salesforce", "HubSpot"],
  );
});

test("isDefunctBrand flags known-dead brands by name or alias, case-insensitively", () => {
  assert.equal(isDefunctBrand("Mint"), true);
  assert.equal(isDefunctBrand("mint.com"), true);
  assert.equal(isDefunctBrand("Budgeting App", ["Intuit Mint"]), true); // via alias
  assert.equal(isDefunctBrand("Monarch Money"), false); // live rival stays
  assert.equal(isDefunctBrand(""), false);
});

test("buildProfile drops defunct competitors (Mint) but keeps live ones", () => {
  const p = buildProfile(
    "https://copilot.money",
    extracted({
      competitors: [
        { name: "Mint", aliases: ["mint.com"] },
        { name: "YNAB", aliases: [] },
        { name: "Monarch Money", aliases: [] },
      ],
    }),
    "m",
    FIXED,
  );
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["YNAB", "Monarch Money"],
  );
});

test("buildProfile drops a defunct brand named only via an alias", () => {
  const p = buildProfile(
    "https://copilot.money",
    extracted({
      competitors: [
        { name: "The Mint App", aliases: ["Intuit Mint"] }, // alias is the dead brand
        { name: "YNAB", aliases: [] },
      ],
    }),
    "m",
    FIXED,
  );
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["YNAB"],
  );
});

test("product claims with an empty claim are dropped, text trimmed", () => {
  const p = buildProfile(
    "https://acme.io",
    extracted({
      productClaims: [
        { claim: "  ", sourceUrl: "x" },
        { claim: "  Costs $5/mo  ", sourceUrl: "  https://acme.io  " },
      ],
    }),
    "m",
    FIXED,
  );
  assert.equal(p.productClaims.length, 1);
  assert.equal(p.productClaims[0]?.claim, "Costs $5/mo");
  assert.equal(p.productClaims[0]?.sourceUrl, "https://acme.io");
});

test("buildExtractionInput labels each page with its url", () => {
  const input = buildExtractionInput([
    { url: "https://acme.io", markdown: "# Home" },
    { url: "https://acme.io/pricing", markdown: "# Pricing" },
  ]);
  assert.ok(input.includes("## https://acme.io\n\n# Home"));
  assert.ok(input.includes("## https://acme.io/pricing\n\n# Pricing"));
});

test("pickInternalTargets selects pricing-style links, deduped and capped", () => {
  const links = [
    { href: "https://acme.io/about", text: "About" },
    { href: "https://acme.io/pricing", text: "Pricing" },
    { href: "https://acme.io/pricing", text: "Pricing (dup)" },
    { href: "https://acme.io/x", text: "Alternatives to us" },
    { href: "https://acme.io/compare", text: "Compare" },
    { href: "https://acme.io/blog", text: "Blog" },
  ];
  const targets = pickInternalTargets(links, 2);
  assert.equal(targets.length, 2);
  assert.equal(targets[0], "https://acme.io/pricing");
  // second is matched by anchor text "Alternatives..." (the /x href)
  assert.equal(targets[1], "https://acme.io/x");
});

test("pickInternalTargets returns [] when nothing matches", () => {
  const targets = pickInternalTargets(
    [
      { href: "https://acme.io/about", text: "About" },
      { href: "https://acme.io/blog", text: "Blog" },
    ],
    3,
  );
  assert.deepEqual(targets, []);
});

test("profileTextLength sums trimmed readable chars across pages", () => {
  assert.equal(profileTextLength(["  hello  ", "world!"]), "hello".length + "world!".length);
  assert.equal(profileTextLength([]), 0);
  assert.equal(profileTextLength(["   ", ""]), 0);
});

test("assertSufficientProfileText throws on a thin challenge page (fails safe)", () => {
  // A Cloudflare interstitial served at HTTP 200 — a few words of noise.
  const challenge = "Just a moment... Enable JavaScript and cookies to continue.";
  assert.ok(challenge.length < MIN_PROFILE_TEXT_CHARS);
  assert.throws(
    () => assertSufficientProfileText([challenge], "https://calai.app"),
    /insufficient content to profile/,
  );
  assert.throws(() => assertSufficientProfileText([], "https://x.com"), /insufficient content/);
});

test("assertSufficientProfileText passes a real page with enough text", () => {
  const real = "Cal AI is an AI-powered calorie tracking app for your phone. ".repeat(6);
  assert.ok(real.length >= MIN_PROFILE_TEXT_CHARS);
  assertSufficientProfileText([real], "https://calai.app"); // must not throw
});

// --- W0.1: the businessKind classifier -------------------------------------------
// Until the local path exists (Phases 1-2), a service-area business is REFUSED rather
// than silently mis-profiled. The teaser today would emit a confident, wrong artifact
// for a plumber — national franchises or invented locals named as "competitors".
// Forward-compatible by design: this same classifier becomes the W2.4 router.

test("the local path is now ROUTED, not refused (W2.4 flipped the gate)", () => {
  assert.equal(LOCAL_SERVICE_PATH_READY, true);
  const p = buildProfile(
    "https://berkeleyplumbingco.com",
    extracted({
      businessKind: "local_service",
      name: "Berkeley Plumbing Co",
      category: "plumbing service",
      location: { city: "Berkeley", region: "California", country: "United States", serviceArea: [] },
    }),
    "claude-sonnet-5",
    FIXED,
  );
  assert.equal(p.businessKind, "local_service");
  assert.deepEqual(p.location, { city: "Berkeley", region: "California", country: "United States" });
});

test("a local profile is built with NO competitors — LLM recall is discarded", () => {
  // THE anti-fabrication guarantee, enforced structurally. The extraction prompt asks
  // for "REAL, CURRENTLY-OPERATING rival brands... use real, well-known names", which
  // for a local trade yields national franchises or plausible inventions. Whatever the
  // model returned is dropped; only attachLocalCompetitors (which requires captured
  // local-pack entities) can name a local rival.
  const p = buildProfile(
    "https://joesbarbershop.com",
    extracted({
      businessKind: "local_service",
      name: "Joe's Barbershop",
      category: "barbershop",
      competitors: [
        { name: "Supercuts", aliases: [] },
        { name: "Great Clips", aliases: [] },
      ],
    }),
    "claude-sonnet-5",
    FIXED,
  );
  assert.deepEqual(p.competitors, [], "no competitor may reach a local profile from extraction");
});

test("a consumer profile still takes its competitors from the extraction", () => {
  const p = buildProfile("https://acme.io", extracted({ businessKind: "product" }), "m", FIXED);
  assert.deepEqual(p.competitors.map((c) => c.name), ["Salesforce", "HubSpot"]);
});

test("a consumer product still resolves, and carries businessKind product", () => {
  const p = buildProfile("https://acme.io", extracted({ businessKind: "product" }), "m", FIXED);
  assert.equal(p.businessKind, "product");
  assert.equal(p.category, "CRM");
  assert.equal(p.competitors.length, 2);
});

test("a legacy extraction with no businessKind defaults to product (back-compat)", () => {
  // Optional on ExtractedProfile for legacy fixtures only; the schema marks it
  // required, so a live extraction always returns it.
  const p = buildProfile("https://acme.io", extracted(), "m", FIXED);
  assert.equal(p.businessKind, "product");
});

test("businessKindOf is the one canonical default", () => {
  assert.equal(businessKindOf({}), "product");
  assert.equal(businessKindOf({ businessKind: undefined }), "product");
  assert.equal(businessKindOf({ businessKind: "product" }), "product");
  assert.equal(businessKindOf({ businessKind: "local_service" }), "local_service");
});

test("assertSupportedBusinessKind is a no-op for products", () => {
  assertSupportedBusinessKind("product", "https://acme.io"); // must not throw
});

test("businessKind is a required, enumerated field in the extraction contract", () => {
  // required + additionalProperties:false means Claude must classify every site;
  // it can never quietly omit the field and fall through to the product default.
  assert.ok(PROFILE_SCHEMA.required.includes("businessKind"));
  assert.deepEqual(PROFILE_SCHEMA.properties.businessKind.enum, ["product", "local_service"]);
  assert.match(PROFILE_SYSTEM_PROMPT, /businessKind: "local_service" if this business serves/);
});

// --- W1.1 / W1.2: location plumbing ----------------------------------------------
// A location is kept ONLY when city+region+country are all present. A partial one
// ("Berkeley", no state) serializes to a canonical string SearchApi resolves to "the
// most popular match" — a different metro entirely, silently measuring the wrong
// market. Dropping to undefined makes the absence visible instead.

test("normalizeLocation keeps a complete location, trimmed", () => {
  const loc = normalizeLocation({
    city: " Berkeley ",
    region: " California ",
    country: " United States ",
  });
  assert.deepEqual(loc, { city: "Berkeley", region: "California", country: "United States" });
});

test("normalizeLocation REJECTS an ISO country code", () => {
  // Verified live against SearchApi 2026-07-27: location="Berkeley,California,US"
  // is rejected with "Location was not found", while ",United States" resolves. An
  // unresolvable location silently falls back to an unpinned locale — it measures
  // the wrong market while looking like it worked — so drop it, same as a partial.
  assert.equal(normalizeLocation({ city: "Berkeley", region: "California", country: "US" }), undefined);
  assert.equal(normalizeLocation({ city: "Berkeley", region: "California", country: "us" }), undefined);
  assert.equal(normalizeLocation({ city: "Toronto", region: "Ontario", country: "CA" }), undefined);
});

test("normalizeLocation drops a PARTIAL location rather than guessing", () => {
  assert.equal(normalizeLocation({ city: "Berkeley", region: "", country: "United States" }), undefined);
  assert.equal(normalizeLocation({ city: "", region: "California", country: "United States" }), undefined);
  assert.equal(normalizeLocation({ city: "Berkeley", region: "California", country: "  " }), undefined);
  assert.equal(normalizeLocation(null), undefined);
  assert.equal(normalizeLocation(undefined), undefined);
});

test("normalizeLocation de-dupes serviceArea and drops the primary city echoed back", () => {
  const loc = normalizeLocation({
    city: "Berkeley",
    region: "California",
    country: "United States",
    serviceArea: ["Oakland", " oakland ", "berkeley", "", "Albany"],
  });
  assert.deepEqual(loc?.serviceArea, ["Oakland", "Albany"]);
});

test("normalizeLocation omits serviceArea entirely when none survive", () => {
  const loc = normalizeLocation({
    city: "Berkeley",
    region: "California",
    country: "United States",
    serviceArea: [],
  });
  assert.deepEqual(loc, { city: "Berkeley", region: "California", country: "United States" });
  assert.ok(!("serviceArea" in (loc ?? {})));
});

test("canonicalLocation builds the SearchApi location string (serviceArea excluded)", () => {
  // Verified against SearchApi's Google-engine docs (2026-07): `location` takes a
  // canonical NAME and SearchApi builds the uule itself. serviceArea widens the
  // query, it does not move the search origin — so it must not leak in here.
  assert.equal(
    canonicalLocation({
      city: "Berkeley",
      region: "California",
      country: "United States",
      serviceArea: ["Oakland"],
    }),
    "Berkeley,California,United States",
  );
});

test("a consumer product never acquires a location, even if one is extracted", () => {
  // Absent is MEANINGFUL on the consumer path: a national product has no service
  // area, and a spurious one would geo-anchor its queries and invalidate the audit.
  const p = buildProfile(
    "https://acme.io",
    extracted({
      businessKind: "product",
      location: { city: "Berkeley", region: "California", country: "United States", serviceArea: [] },
    }),
    "m",
    FIXED,
  );
  assert.equal(p.location, undefined);
});

test("location is a required key in the extraction contract (null, not omitted)", () => {
  // Required means Claude must DECIDE. If it could omit the key we couldn't tell
  // "not a service-area business" from "forgot to look".
  assert.ok(PROFILE_SCHEMA.required.includes("location"));
  assert.match(PROFILE_SYSTEM_PROMPT, /Return null when the site is not service-area-bound/);
  assert.match(PROFILE_SYSTEM_PROMPT, /do NOT infer a location from the brand name/);
});

// --- W2.4: entity-sourced local competitors ---------------------------------------
// The ONLY path from a real business to a named local rival. Pure: the caller does
// the capture and hands entities in, so the fabrication guarantee is checkable
// without a network.

function localProfile(over: Record<string, unknown> = {}) {
  return {
    url: "https://berkeleyplumbingco.com",
    name: "Berkeley Plumbing Co",
    aliases: ["BPC"],
    businessKind: "local_service" as const,
    location: { city: "Berkeley", region: "California", country: "United States" },
    category: "plumbing service",
    competitors: [],
    clientDomains: ["berkeleyplumbingco.com"],
    productClaims: [],
    resolvedAt: FIXED.toISOString(),
    resolverModel: "m",
    ...over,
  };
}

function entity(name: string, over: Record<string, unknown> = {}) {
  return {
    name,
    address: "1 Main St",
    category: "Plumber",
    rating: 4.5,
    reviews: 100,
    ludocid: null,
    position: null,
    ...over,
  };
}

test("attachLocalCompetitors names rivals from captured entities, unconfirmed", () => {
  const p = attachLocalCompetitors(localProfile(), [
    entity("Bay Area Rooter"),
    entity("Berkeley Drain Co"),
  ]);
  assert.deepEqual(p.competitors, [
    { name: "Bay Area Rooter", aliases: [], confirmed: false },
    { name: "Berkeley Drain Co", aliases: [], confirmed: false },
  ]);
});

test("the client itself is dropped from its own competitor list", () => {
  // Google's local pack naturally returns the client. Naming a shop as its own
  // competitor is an obvious tell that the artifact is machine-generated.
  const p = attachLocalCompetitors(localProfile(), [
    entity("Berkeley Plumbing Co"), // the client, by name
    entity("BPC"), // the client, by alias
    entity("Bay Area Rooter"),
  ]);
  assert.deepEqual(p.competitors.map((c) => c.name), ["Bay Area Rooter"]);
});

test("duplicates are collapsed case-insensitively and the list is capped", () => {
  const many = ["A Co", "a co", "B Co", "C Co", "D Co", "E Co", "F Co"].map((n) => entity(n));
  const p = attachLocalCompetitors(localProfile(), many);
  assert.equal(p.competitors.length, MAX_LOCAL_COMPETITORS);
  assert.deepEqual(p.competitors.map((c) => c.name), ["A Co", "B Co", "C Co", "D Co"]);
});

test("attachLocalCompetitors FAILS LOUDLY rather than leaving a teaser rival-less", () => {
  // The alternative is a teaser claiming "AI recommends <nobody> instead of you", or
  // a fallback to model recall. Both are worse than no teaser.
  assert.throws(() => attachLocalCompetitors(localProfile(), []), /no local competitors could be sourced/);
  // Only the client came back — still nothing usable.
  assert.throws(
    () => attachLocalCompetitors(localProfile(), [entity("Berkeley Plumbing Co")]),
    /Refusing to build a local teaser/,
  );
  // Blank names are not rivals.
  assert.throws(() => attachLocalCompetitors(localProfile(), [entity("   ")]), /no local competitors/);
});

test("attachLocalCompetitors refuses a consumer product", () => {
  const consumer = localProfile({ businessKind: "product", location: undefined });
  assert.throws(
    () => attachLocalCompetitors(consumer, [entity("Bay Area Rooter")]),
    /is a product/,
  );
});
