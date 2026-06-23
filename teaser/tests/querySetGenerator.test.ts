/**
 * Unit tests for ClaudeQuerySetGenerator's PURE validation/repair logic. No
 * network, no LLM — we call validateAndRepair directly with synthetic LLM output
 * and assert the hard rules hold (and are repaired when violated).
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { validateAndRepair } from "../src/queryset/ClaudeQuerySetGenerator.ts";
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
