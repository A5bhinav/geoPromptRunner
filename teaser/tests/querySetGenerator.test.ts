/**
 * Unit tests for ClaudeQuerySetGenerator's PURE validation/repair logic. No
 * network, no LLM — we call validateAndRepair directly with synthetic LLM output
 * and assert the hard rules hold (and are repaired when violated).
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { fallbackQueries, validateAndRepair } from "../src/queryset/ClaudeQuerySetGenerator.ts";
import type { CompanyProfile } from "../src/types/domain.ts";
import type { IntentBucket } from "../src/types/platform.ts";

function profile(over: Partial<CompanyProfile> = {}): CompanyProfile {
  return {
    url: "https://acme.io",
    name: "Acme",
    category: "CRM",
    competitors: [
      { name: "Salesforce", aliases: [], confirmed: false },
      { name: "HubSpot", aliases: [], confirmed: false },
    ],
    clientDomains: ["acme.io"],
    productClaims: [],
    resolvedAt: "1970-01-01T00:00:00Z",
    resolverModel: "mock",
    ...over,
  };
}

function raw(text: string, intent: IntentBucket) {
  return { text, intent };
}

test("well-formed LLM output is passed through and gets ids + weights", () => {
  const queries = validateAndRepair(profile(), [
    raw("What's the best CRM for a startup?", "category"),
    raw("Which CRM do teams recommend in 2026?", "category"),
    raw("What are the best alternatives to Salesforce?", "comparison"),
    raw("HubSpot vs other CRM options — which should I pick?", "comparison"),
    raw("Is Acme any good?", "brand"),
  ]);
  // All present, sequential ids, weights assigned, persona null.
  assert.equal(queries.length, 5);
  assert.equal(queries[0]?.query_id, "q01");
  assert.equal(queries[4]?.query_id, "q05");
  for (const q of queries) {
    assert.ok(q.weight > 0);
    assert.equal(q.persona, null);
  }
});

test("client named in a non-brand query is dropped (rule 1)", () => {
  const queries = validateAndRepair(profile(), [
    // illegal: client named in a category query
    raw("Is Acme the best CRM?", "category"),
    raw("What are the best alternatives to Salesforce?", "comparison"),
    raw("HubSpot vs other CRM options?", "comparison"),
    raw("Is Acme any good?", "brand"),
  ]);
  const texts = queries.map((q) => q.text);
  assert.ok(!texts.includes("Is Acme the best CRM?"), "illegal client-named category dropped");
  // The only surviving query naming the client must be the brand one.
  const clientNamed = queries.filter((q) => q.text.toLowerCase().includes("acme"));
  for (const q of clientNamed) assert.equal(q.intent, "brand");
});

test("comparison query naming no competitor is dropped (rule 3)", () => {
  const queries = validateAndRepair(profile(), [
    raw("Which CRM is best overall?", "comparison"), // names no competitor -> dropped
    raw("What are the best alternatives to Salesforce?", "comparison"),
    raw("HubSpot vs other tools?", "comparison"),
    raw("Is Acme any good?", "brand"),
  ]);
  assert.ok(!queries.some((q) => q.text === "Which CRM is best overall?"));
  for (const q of queries.filter((x) => x.intent === "comparison")) {
    const namesCompetitor = ["salesforce", "hubspot"].some((c) => q.text.toLowerCase().includes(c));
    assert.ok(namesCompetitor, `comparison query must name a competitor: ${q.text}`);
  }
});

test("fewer than 2 client-free comparisons are synthesized (rule 2)", () => {
  // Only one comparison, and it names the client -> 0 client-free comparisons.
  const queries = validateAndRepair(profile(), [
    raw("How do I pick a CRM that scales?", "problem_aware"),
    raw("Acme vs Salesforce — which is better?", "comparison"),
    raw("Is Acme any good?", "brand"),
  ]);
  const clientFreeComparisons = queries.filter(
    (q) => q.intent === "comparison" && !q.text.toLowerCase().includes("acme"),
  );
  assert.ok(
    clientFreeComparisons.length >= 2,
    `expected >=2 client-free comparisons, got ${clientFreeComparisons.length}`,
  );
});

test("a brand query is synthesized when the LLM omits one", () => {
  const queries = validateAndRepair(profile(), [
    raw("What's the best CRM for a team?", "category"),
    raw("What are the best alternatives to Salesforce?", "comparison"),
    raw("HubSpot vs other CRM options?", "comparison"),
  ]);
  const brand = queries.filter((q) => q.intent === "brand");
  assert.equal(brand.length, 1, "exactly one brand query synthesized");
  assert.ok(brand[0]?.text.includes("Acme"), "brand query names the client");
});

test("empty/garbage LLM output falls back to the template set", () => {
  const queries = validateAndRepair(profile(), []);
  assert.ok(queries.length >= 3, "fallback template set produced");
  // Fallback still satisfies the hard rules.
  const clientFreeComparisons = queries.filter(
    (q) => q.intent === "comparison" && !q.text.toLowerCase().includes("acme"),
  );
  assert.ok(clientFreeComparisons.length >= 2);
  assert.ok(queries.some((q) => q.intent === "brand"));
});

test("invalid intents are dropped", () => {
  const queries = validateAndRepair(profile(), [
    // @ts-expect-error intentionally invalid intent to test runtime filtering
    raw("Some text", "nonsense"),
    raw("What are the best alternatives to Salesforce?", "comparison"),
    raw("HubSpot vs other tools?", "comparison"),
    raw("Is Acme any good?", "brand"),
  ]);
  assert.ok(!queries.some((q) => q.text === "Some text"));
});

// T5/C4: a category (or adjacent) query that drifted off the client's specific
// category — no category signal token — is dropped, while an on-category one stays.
test("category queries that drift off the specific category are dropped (C4)", () => {
  const queries = validateAndRepair(profile(), [
    raw("What's the best CRM for a startup?", "category"), // on-category → kept
    raw("What's the best tool for a growing startup?", "category"), // drifted, no "CRM" → dropped
    raw("What are the best alternatives to Salesforce?", "comparison"),
    raw("HubSpot vs other CRM options?", "comparison"),
    raw("Is Acme any good?", "brand"),
  ]);
  const texts = queries.map((q) => q.text);
  assert.ok(texts.includes("What's the best CRM for a startup?"), "on-category query kept");
  assert.ok(
    !texts.includes("What's the best tool for a growing startup?"),
    "off-category drift dropped",
  );
});

test("rules hold even with a single competitor", () => {
  const queries = validateAndRepair(
    profile({ competitors: [{ name: "Salesforce", aliases: [], confirmed: false }] }),
    [],
  );
  const clientFreeComparisons = queries.filter(
    (q) => q.intent === "comparison" && !q.text.toLowerCase().includes("acme"),
  );
  assert.ok(clientFreeComparisons.length >= 2);
  for (const q of clientFreeComparisons) {
    assert.ok(q.text.toLowerCase().includes("salesforce"), "names the one competitor");
  }
});

// --- W2.3: kind-selected fallback query templates ---------------------------------
// The plan said "delete the startup fallbacks". Deleting is fine; REPLACING them with
// local-only templates would leave the consumer path with no correct fallback at all.

function localProfileForQueries(over: Record<string, unknown> = {}) {
  return {
    url: "https://berkeleyplumbingco.com",
    name: "Berkeley Plumbing Co",
    aliases: [],
    businessKind: "local_service" as const,
    location: { city: "Berkeley", region: "California", country: "US" },
    category: "plumber",
    competitors: [],
    clientDomains: ["berkeleyplumbingco.com"],
    productClaims: [],
    resolvedAt: "2026-07-27T00:00:00.000Z",
    resolverModel: "m",
    ...over,
  };
}

test("the local fallback set is geo-anchored and uses local intents", () => {
  const qs = fallbackQueries(localProfileForQueries());
  const texts = qs.map((q) => q.text);

  assert.ok(texts.some((t) => t.includes("best plumber in Berkeley".replace("best", "Best"))));
  for (const q of qs) {
    assert.ok(
      ["local_intent", "hybrid", "informational", "brand"].includes(q.intent),
      `consumer intent ${q.intent} leaked into the local fallback`,
    );
  }
  // Every non-brand local query carries the city.
  for (const q of qs) {
    if (q.intent === "local_intent" || q.intent === "hybrid") {
      assert.ok(q.text.includes("Berkeley"), `local query without a city: ${q.text}`);
    }
  }
});

test("the local fallback NEVER names a competitor", () => {
  // A local rival can only come from captured local-pack entities (W2.4). A fallback
  // that invented a "vs <competitor>" query would reintroduce the fabrication risk.
  const qs = fallbackQueries(
    localProfileForQueries({
      competitors: [{ name: "Roto-Rooter", aliases: [], confirmed: true }],
    }),
  );
  for (const q of qs) {
    assert.ok(!q.text.includes("Roto-Rooter"), `fallback named a competitor: ${q.text}`);
    assert.notEqual(q.intent, "comparison");
  }
});

test("a local profile with no city fails loudly rather than measuring nowhere", () => {
  assert.throws(
    () => fallbackQueries(localProfileForQueries({ location: undefined })),
    /no city on the profile/,
  );
});

test("the consumer fallback is unchanged in shape and carries no startup phrasing", () => {
  const consumer = {
    ...localProfileForQueries(),
    name: "Acme Ring",
    url: "https://acmering.io",
    businessKind: "product" as const,
    location: undefined,
    category: "sleep-tracking smart ring",
    competitors: [{ name: "Oura", aliases: [], confirmed: true }],
  };
  const qs = fallbackQueries(consumer);
  const all = qs.map((q) => q.text).join("\n");

  // The stale B2B-SaaS-era phrasing is gone...
  assert.ok(!all.includes("growing startup"));
  assert.ok(!all.includes("scales with my needs"));
  // ...but the consumer branch still resolves to consumer-shaped queries.
  assert.ok(all.includes("sleep-tracking smart ring"));
  assert.ok(!all.includes("Berkeley"));
  for (const q of qs) {
    assert.ok(!["local_intent", "hybrid", "informational"].includes(q.intent));
  }
});
