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
