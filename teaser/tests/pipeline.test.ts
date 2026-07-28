import assert from "node:assert/strict";
import { test } from "node:test";
import { MockPlatformClient } from "../src/platform/MockPlatformClient.ts";
import { MockQuerySetGenerator } from "../src/queryset/MockQuerySetGenerator.ts";
import { MockResolver } from "../src/resolver/MockResolver.ts";
import { runTeaserPipeline } from "../src/pipeline.ts";

test("end-to-end pipeline produces a draft from a URL (all mocks)", async () => {
  const deps = {
    resolver: new MockResolver(),
    querySetGenerator: new MockQuerySetGenerator(),
    platform: new MockPlatformClient(),
  };
  const result = await runTeaserPipeline("https://acme-hq.io", deps);
  assert.equal(result.ok, true);
  if (!result.ok) return;

  const d = result.draft;
  assert.equal(d.companyName, "Acme Hq");
  assert.ok(d.lead.verbatimAnswer.length > 0, "lead has a verbatim answer");
  assert.ok(d.table.length >= 1, "has pattern-table rows");
  assert.ok(d.headlineNumber.n > 0, "headline has queries");
  // Brand-intent queries are dropped from the teaser (they name the client), so no
  // answer carries brand intent and the client is absent from every measured query.
  assert.ok(!d.answers.some((a) => a.intent === "brand"), "no brand-intent query in the audit");
  assert.equal(
    d.headlineNumber.companyAppears,
    0,
    "client absent from every unprompted query (brand query dropped)",
  );
  assert.equal(d.headlineNumber.competitorAppears, d.headlineNumber.n, "competitor present on every query");
  assert.equal(d.headlineNumber.competitorName, "Northstar");
  assert.equal(d.status, "draft");
});

test("confirm gate can abort the run", async () => {
  const deps = {
    resolver: new MockResolver(),
    querySetGenerator: new MockQuerySetGenerator(),
    platform: new MockPlatformClient(),
  };
  const result = await runTeaserPipeline("https://acme-hq.io", deps, {
    confirm: async () => null,
  });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.stage, "confirm");
});

// --- W1.6 + W2.4: the local path sources competitors from the captured local pack ---
//
// This wiring is the whole reason `LOCAL_SERVICE_PATH_READY` can be true. Without it a
// local business flows down the consumer path and the resolver's LLM names "competitors"
// from recall — which for a local trade yields national franchises or invented locals.
// A fabricated rival in a teaser emailed to a real shop owner is the one failure that
// survives human review, so these tests pin the guarantees rather than the happy path.

function localDeps(entities: { name: string }[] | Error) {
  const platform = new MockPlatformClient();
  platform.getLocalEntities = async () => {
    if (entities instanceof Error) throw entities;
    return entities.map((e, i) => ({
      name: e.name,
      address: "",
      category: "Plumber",
      rating: null,
      reviews: null,
      ludocid: null,
      position: i + 1,
      phone: null,
      website: null,
    }));
  };
  const resolver = new MockResolver();
  const inner = resolver.resolve.bind(resolver);
  resolver.resolve = async (url: string) => ({
    ...(await inner(url)),
    businessKind: "local_service" as const,
    category: "plumber",
    location: { city: "Berkeley", region: "California", country: "United States" },
  });
  return { resolver, querySetGenerator: new MockQuerySetGenerator(), platform };
}

test("a local teaser names only businesses captured from the local pack", async () => {
  const deps = localDeps([
    { name: "LemonTree Plumbing" },
    { name: "J J Rooter & Plumbing" },
  ]);
  const result = await runTeaserPipeline("https://berkeley-plumber.example", deps);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  // The captured names replaced whatever the resolver would have guessed.
  const named = JSON.stringify(result.draft);
  assert.ok(
    named.includes("LemonTree Plumbing") || named.includes("J J Rooter & Plumbing"),
    "a captured local-pack business must be the named rival",
  );
});

test("a local business with no readable location is refused, not guessed", async () => {
  const deps = localDeps([{ name: "LemonTree Plumbing" }]);
  const inner = deps.resolver.resolve.bind(deps.resolver);
  deps.resolver.resolve = async (url: string) => {
    const p = await inner(url);
    return { ...p, location: undefined };
  };
  const result = await runTeaserPipeline("https://berkeley-plumber.example", deps);
  // An unpinned capture names businesses in the wrong metro — worse than no teaser.
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.stage, "resolve");
  assert.match(result.reason, /location/i);
});

test("an empty local pack refuses rather than falling back to model recall", async () => {
  const deps = localDeps([]);
  await assert.rejects(
    () => runTeaserPipeline("https://berkeley-plumber.example", deps),
    /no local competitors could be sourced/,
    "an empty capture must throw, never quietly produce a teaser with invented rivals",
  );
});
