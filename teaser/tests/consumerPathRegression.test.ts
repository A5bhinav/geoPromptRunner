/**
 * W0.4 — the consumer-path regression lock (TypeScript half).
 *
 * The SMB pivot (`docs/smb-pivot-build-plan.md`) ADDS the local-service ICP; it does
 * not replace the consumer-product one. Both ship. The plan's §0.6 rule is that every
 * shared symbol is **forked by business kind, never edited in place**.
 *
 * This file pins today's consumer behaviour on the teaser side so an in-place edit
 * fails loudly. It guards W0.1 (the businessKind classifier), W2.3 (query-gen
 * fallbacks), W2.4 (the local resolver path), W2.5 (geographic competitor validation)
 * and W2.6 (local copy).
 *
 * **A failure here is the lock working.** The fix is to fork on businessKind and
 * restore the consumer assertion unchanged — NEVER to relax the assertion so local
 * behaviour can pass through it.
 *
 * Deliberately pins OUTPUTS and prompt semantics, not the extraction schema's field
 * list: W0.1 legitimately adds `businessKind` to that schema, and a pin that broke on
 * a purely additive field would train people to edit this file casually.
 *
 * Pure — no network, no LLM.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildProfile,
  PROFILE_SYSTEM_PROMPT,
  type ExtractedProfile,
} from "../src/resolver/profileExtraction.ts";
import { normalizeRelationships, pruneRelatedCompetitors } from "../src/resolver/relationshipCheck.ts";
import { MockQuerySetGenerator } from "../src/queryset/MockQuerySetGenerator.ts";
import { buildAuditCsv } from "../src/platform/csv.ts";
import { competitorVerb, competitorProminenceWord, headline, leadSentence } from "../src/render/copy.ts";
import type { CompanyProfile, Finding } from "../src/types/domain.ts";

const FIXED = new Date("2026-06-22T00:00:00.000Z");

/** A resolved consumer-product profile — the ICP that must not regress. */
function consumerProfile(): CompanyProfile {
  return {
    url: "https://acmering.io",
    name: "Acme Ring",
    aliases: [],
    category: "sleep-tracking smart ring",
    competitors: [
      { name: "Oura", aliases: [], confirmed: true },
      { name: "Whoop", aliases: [], confirmed: true },
    ],
    clientDomains: ["acmering.io"],
    productClaims: [],
    resolvedAt: FIXED.toISOString(),
    resolverModel: "mock",
  };
}

/** A consumer-product extraction — the ICP that must not regress. */
function consumerExtraction(): ExtractedProfile {
  return {
    name: "Acme Ring",
    aliases: ["Acme"],
    category: "sleep-tracking smart ring",
    competitors: [
      { name: "Oura", aliases: ["Oura Ring"] },
      { name: "Whoop", aliases: ["WHOOP"] },
    ],
    clientDomains: ["acmering.io"],
    productClaims: [{ claim: "$299 with no subscription", sourceUrl: "https://acmering.io/pricing" }],
  };
}

// --- W0.1 / W2.4 guard: consumer profile resolution -------------------------------
// W0.1 adds a businessKind classifier that throws on local_service; W2.4 flips it to
// a route. Neither may alter what a consumer-product site resolves to.

test("consumer profile resolves to today's exact CompanyProfile", () => {
  const p = buildProfile("https://www.acmering.io", consumerExtraction(), "claude-sonnet-5", FIXED);

  assert.equal(p.url, "https://www.acmering.io");
  assert.equal(p.name, "Acme Ring");
  assert.equal(p.category, "sleep-tracking smart ring");
  assert.deepEqual(p.aliases, ["Acme"]);
  assert.deepEqual(p.clientDomains, ["acmering.io"]);
  assert.equal(p.resolverModel, "claude-sonnet-5");
  assert.equal(p.resolvedAt, FIXED.toISOString());

  // Competitors: order preserved, aliases preserved, ALWAYS confirmed:false
  // (the human input-confirm gate is what flips them).
  assert.deepEqual(p.competitors, [
    { name: "Oura", aliases: ["Oura Ring"], confirmed: false },
    { name: "Whoop", aliases: ["WHOOP"], confirmed: false },
  ]);

  assert.deepEqual(p.productClaims, [
    { claim: "$299 with no subscription", sourceUrl: "https://acmering.io/pricing" },
  ]);
});

test("a consumer product resolves WITHOUT a location", () => {
  // W1.1 adds an optional `location` to CompanyProfile for service-area businesses.
  // A nationally-marketed consumer product has no service area and must not acquire
  // one — a spurious location would localise its queries and invalidate the audit.
  const p = buildProfile("https://www.acmering.io", consumerExtraction(), "claude-sonnet-5", FIXED);
  const withLocation = p as CompanyProfile & { location?: unknown };
  assert.equal(withLocation.location, undefined);
});

test("the blank/degenerate category hard-failure still fires", () => {
  // The existing C6 guard. W0.1 adds a SECOND throw next to it (local_service with no
  // local support); it must not absorb or weaken this one.
  for (const category of ["", "   ", "product", "Product"]) {
    assert.throws(
      () => buildProfile("https://acme.io", { ...consumerExtraction(), category }, "m", FIXED),
      /could not determine a specific product category/,
      `category ${JSON.stringify(category)} should still hard-fail`,
    );
  }
});

test("the extraction prompt still asks for a narrow consumer category and direct substitutes", () => {
  // W2.4 adds local trade/city/competitor extraction. Done in place — rewriting this
  // shared prompt for local — it would degrade consumer category resolution silently.
  assert.match(PROFILE_SYSTEM_PROMPT, /MOST SPECIFIC consumer-facing category/);
  assert.match(PROFILE_SYSTEM_PROMPT, /DIRECT SUBSTITUTE in the SAME specific category/);
  assert.match(PROFILE_SYSTEM_PROMPT, /2-5 REAL, CURRENTLY-OPERATING rival brands/);
  // The anti-fabrication clause is load-bearing for a cold-outreach artifact.
  assert.match(PROFILE_SYSTEM_PROMPT, /Do not invent competitors or claims/);
});

// --- W2.3 guard: query-generation fallbacks ---------------------------------------
// The plan said "delete the startup fallbacks". Deleting is fine; REPLACING them with
// local-only templates would leave the consumer path with no correct fallback at all.
// The consumer branch must still resolve to something consumer-shaped.

test("the consumer fallback query set stays consumer-shaped and carries no local phrasing", async () => {
  const set = await new MockQuerySetGenerator().generate(consumerProfile());
  assert.ok(set.queries.length >= 6, "consumer fallback must still produce a usable set");

  const all = set.queries.map((q) => q.text).join("\n");
  // The category is threaded into the templates (not replaced by a trade slot).
  assert.ok(all.includes("sleep-tracking smart ring"), "category must reach the templates");

  // No local phrasing may leak onto the consumer path.
  for (const local of ["near me", "{city}", "in Berkeley", "plumber", "HVAC"]) {
    assert.ok(!all.includes(local), `local phrasing ${JSON.stringify(local)} leaked into consumer queries`);
  }

  // Consumer intents only.
  const intents = new Set(set.queries.map((q) => q.intent));
  for (const intent of intents) {
    assert.ok(
      ["category", "comparison", "brand", "problem_aware", "adjacent_authority"].includes(intent),
      `non-consumer intent ${intent} leaked into the consumer fallback set`,
    );
  }
});

// --- W2.5 guard: competitor validation is geography-free on the consumer path ------
// W2.5 adds a service-area overlap judgment. A nationally-marketed product has no
// service area; running the overlap check on it would drop legitimate rivals on a
// dimension that does not apply. The geographic check must be gated to local_service.

test("consumer competitor pruning keeps same-category rivals and is recall-safe", () => {
  const profile = consumerProfile();
  const rels = normalizeRelationships(
    [
      { competitor: "Oura", verdict: "independent", category: "same_category", evidence: "separate company" },
      { competitor: "Whoop", verdict: "unknown", category: "unknown", evidence: "no evidence" },
    ],
    profile,
  );

  const result = pruneRelatedCompetitors(profile, rels);

  // Both survive: an independent same-category rival, and an unknown (recall-safe).
  assert.deepEqual(result.profile.competitors.map((c: { name: string }) => c.name), ["Oura", "Whoop"]);
  assert.equal(result.dropped.length, 0);
});

test("a same-category competitor is never dropped for lacking a location", () => {
  // W2.5's service-area overlap judgment must be gated to local_service. If it ever
  // runs on the consumer path, a national product — which has no service area — would
  // start losing legitimate rivals on a dimension that does not apply to it.
  const profile = consumerProfile();
  const rels = normalizeRelationships(
    [
      { competitor: "Oura", verdict: "independent", category: "same_category", evidence: "national brand" },
      { competitor: "Whoop", verdict: "independent", category: "same_category", evidence: "national brand" },
    ],
    profile,
  );

  const result = pruneRelatedCompetitors(profile, rels);
  assert.equal(result.dropped.length, 0, "no consumer rival may be dropped on geography");
  assert.equal(result.profile.competitors.length, 2);
});

// --- W2.6 guard: teaser copy --------------------------------------------------------
// W2.6 rewrites copy for local ("buyers" -> "customers"/"homeowners", drops the
// share-of-voice chart). All of it is scoped to the local path; the consumer strings
// and — critically — the prominence-graded claim-fidelity rules stay exactly as-is.

function finding(prominence: Finding["prominence"]): Finding {
  return {
    engineName: "openai",
    verbatimQuery: "best smart ring 2026",
    competitor: "Oura",
    prominence,
  } as Finding;
}

test("consumer copy is unchanged and stays prominence-graded", () => {
  assert.equal(
    headline("Acme Ring", finding("recommended_first")),
    "AI is sending your buyers to Oura — not Acme Ring.",
  );
  assert.equal(
    headline("Acme Ring", finding("mid_pack")),
    "When your buyers ask AI, Oura is in the answer — Acme Ring isn't.",
  );
  assert.match(leadSentence("Acme Ring", finding("recommended_first")), /^Ask ChatGPT/);
});

test("claim-fidelity grading survives the local copy work", () => {
  // The teaser may never claim more than the judge measured. "recommends" is reserved
  // for recommended_first; weaker prominence grades down. The local path INHERITS this
  // — it does not get its own ungraded verbs.
  assert.deepEqual(competitorVerb(finding("recommended_first")), {
    active: "recommends",
    passive: "is recommended",
  });
  assert.deepEqual(competitorVerb(finding("mid_pack")), { active: "features", passive: "is featured" });
  assert.deepEqual(competitorVerb(finding("buried")), { active: "mentions", passive: "is mentioned" });

  assert.equal(competitorProminenceWord(finding("recommended_first")), "recommended");
  assert.equal(competitorProminenceWord(finding("mid_pack")), "featured");
  assert.equal(competitorProminenceWord(finding("also_ran")), "mentioned");
});

// --- W1.4 guard: the audit CSV contract -------------------------------------------
// The `config,location` row is emitted ONLY for service-area businesses. A consumer
// product's CSV must stay byte-identical to the pre-pivot one, since the platform
// parses both and the consumer ICP is still live.

test("a consumer product's audit CSV carries no location row", async () => {
  const csv = buildAuditCsv(
    consumerProfile(),
    { version: "v1", queries: [{ query_id: "q1", text: "best smart ring", intent: "category", weight: 1, persona: null }] },
    { engines: ["openai"], runsPerQuery: 3, judge: true },
  );

  assert.ok(!csv.includes("location"), "no location row may appear for a product");
  // The config block is exactly the pre-pivot set of keys.
  const configKeys = csv
    .split("\n")
    .filter((l) => l.startsWith("config,"))
    .map((l) => l.split(",")[1]);
  assert.deepEqual(configKeys, [
    "client_name",
    "category",
    "client_domains",
    "competitors",
    "engines",
    "runs_per_query",
    "judge",
  ]);
});

test("a located business emits the canonical location row", async () => {
  const csv = buildAuditCsv(
    {
      ...consumerProfile(),
      businessKind: "local_service",
      category: "plumbing service",
      location: { city: "Berkeley", region: "California", country: "United States", serviceArea: ["Oakland"] },
    },
    { version: "v1", queries: [{ query_id: "q1", text: "best plumber in Berkeley", intent: "category", weight: 1, persona: null }] },
    { engines: ["google_ai_overviews"], runsPerQuery: 5, judge: true },
  );

  // Quoted because the canonical form contains commas — "," stays the CSV column
  // delimiter, so the cell must be quoted rather than split across columns.
  assert.ok(csv.includes('config,location,"Berkeley,California,United States"'), csv);
  // serviceArea widens the query; it does not move the search origin, so it must
  // not leak into the location cell.
  assert.ok(!csv.includes("Oakland"));
});
