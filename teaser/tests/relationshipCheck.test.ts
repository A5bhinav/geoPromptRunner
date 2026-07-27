import assert from "node:assert/strict";
import { test } from "node:test";
import { extractJsonBlock } from "../src/llm/claude.ts";
import {
  isRelatedVerdict,
  normalizeRelationships,
  pruneRelatedCompetitors,
  type CompetitorRelationship,
} from "../src/resolver/relationshipCheck.ts";
import type { CompanyProfile } from "../src/types/domain.ts";

function profile(competitors: string[]): CompanyProfile {
  return {
    url: "https://calai.app",
    name: "Cal AI",
    category: "calorie tracking app",
    competitors: competitors.map((name) => ({ name, aliases: [], confirmed: false })),
    clientDomains: ["calai.app"],
    productClaims: [],
    resolvedAt: "2026-07-03T00:00:00Z",
    resolverModel: "claude-haiku-4-5",
  };
}

// --- extractJsonBlock ---------------------------------------------------------

test("extractJsonBlock parses a bare JSON array", () => {
  const v = extractJsonBlock('[{"competitor":"X","verdict":"independent","evidence":""}]');
  assert.deepEqual(v, [{ competitor: "X", verdict: "independent", evidence: "" }]);
});

test("extractJsonBlock strips ```json fences and ignores trailing prose", () => {
  const text = 'Here are my findings:\n```json\n[{"competitor":"MyFitnessPal","verdict":"same_company"}]\n```\nHope that helps!';
  assert.deepEqual(extractJsonBlock(text), [
    { competitor: "MyFitnessPal", verdict: "same_company" },
  ]);
});

test("extractJsonBlock is string-aware: a brace inside a quoted value doesn't end early", () => {
  const text = '[{"competitor":"A","evidence":"per techcrunch.com (deal } closed)"}]';
  assert.deepEqual(extractJsonBlock(text), [
    { competitor: "A", evidence: "per techcrunch.com (deal } closed)" },
  ]);
});

test("extractJsonBlock throws when there is no JSON value", () => {
  assert.throws(() => extractJsonBlock("no json here"), /no JSON value/);
});

// --- normalizeRelationships ---------------------------------------------------

test("normalizeRelationships maps names case-insensitively and coerces verdicts", () => {
  const p = profile(["MyFitnessPal", "Cronometer"]);
  const raw = [
    { competitor: "myfitnesspal", verdict: "COMPETITOR_ACQUIRED_CLIENT", evidence: "techcrunch.com" },
    { competitor: "Cronometer", verdict: "independent", evidence: "" },
  ];
  const out = normalizeRelationships(raw, p);
  const mfp = out.find((r) => r.competitor === "MyFitnessPal");
  assert.equal(mfp?.verdict, "competitor_acquired_client");
  assert.equal(mfp?.evidence, "techcrunch.com");
  assert.equal(out.find((r) => r.competitor === "Cronometer")?.verdict, "independent");
});

test("normalizeRelationships fills omitted competitors as unknown (kept) and ignores stray names", () => {
  const p = profile(["MyFitnessPal", "Cronometer"]);
  const raw = [
    { competitor: "MyFitnessPal", verdict: "same_company", evidence: "x" },
    { competitor: "SomeUnlistedBrand", verdict: "same_company", evidence: "y" }, // not in profile → ignored
  ];
  const out = normalizeRelationships(raw, p);
  assert.equal(out.length, 2); // one per profile competitor, stray dropped
  assert.equal(out.find((r) => r.competitor === "Cronometer")?.verdict, "unknown");
});

test("normalizeRelationships coerces garbage/unknown verdict strings to unknown", () => {
  const p = profile(["X"]);
  const out = normalizeRelationships([{ competitor: "X", verdict: "acquired!!" }], p);
  assert.equal(out[0]?.verdict, "unknown");
});

test("normalizeRelationships tolerates a non-array (all competitors → unknown)", () => {
  const p = profile(["X", "Y"]);
  const out = normalizeRelationships({ oops: true }, p);
  assert.equal(out.length, 2);
  assert.ok(out.every((r) => r.verdict === "unknown"));
});

// --- pruneRelatedCompetitors --------------------------------------------------

test("pruneRelatedCompetitors drops entangled brands, keeps independent + unknown", () => {
  const p = profile(["MyFitnessPal", "Cronometer", "Lose It!", "MacroFactor"]);
  const rels: CompetitorRelationship[] = [
    { competitor: "MyFitnessPal", verdict: "competitor_acquired_client", evidence: "techcrunch.com" },
    { competitor: "Cronometer", verdict: "independent", evidence: "" },
    { competitor: "Lose It!", verdict: "unknown", evidence: "no verdict returned" },
    { competitor: "MacroFactor", verdict: "same_company", evidence: "merger" },
  ];
  const { profile: pruned, dropped } = pruneRelatedCompetitors(p, rels);
  assert.deepEqual(
    pruned.competitors.map((c) => c.name),
    ["Cronometer", "Lose It!"], // independent + unknown kept
  );
  assert.deepEqual(
    dropped.map((d) => d.name).sort(),
    ["MacroFactor", "MyFitnessPal"],
  );
});

test("pruneRelatedCompetitors returns the SAME profile object when nothing is dropped", () => {
  const p = profile(["Cronometer"]);
  const rels: CompetitorRelationship[] = [
    { competitor: "Cronometer", verdict: "independent", evidence: "" },
  ];
  const res = pruneRelatedCompetitors(p, rels);
  assert.equal(res.profile, p); // unchanged reference
  assert.equal(res.dropped.length, 0);
});

test("pruneRelatedCompetitors can empty the competitor set (all entangled)", () => {
  const p = profile(["MyFitnessPal"]);
  const rels: CompetitorRelationship[] = [
    { competitor: "MyFitnessPal", verdict: "competitor_acquired_client", evidence: "x" },
  ];
  const { profile: pruned, dropped } = pruneRelatedCompetitors(p, rels);
  assert.equal(pruned.competitors.length, 0);
  assert.equal(dropped.length, 1);
});

test("isRelatedVerdict: the three entanglement verdicts drop; independent/unknown keep", () => {
  assert.equal(isRelatedVerdict("competitor_acquired_client"), true);
  assert.equal(isRelatedVerdict("client_acquired_competitor"), true);
  assert.equal(isRelatedVerdict("same_company"), true);
  assert.equal(isRelatedVerdict("independent"), false);
  assert.equal(isRelatedVerdict("unknown"), false);
});

// --- W2.5: service-area overlap (local_service only) ------------------------------
// CategoryVerdict has no geography: a Phoenix plumber and a Berkeley plumber are both
// same_category and both passed. Recall-safe — only an explicit different_area drops.

function localProfileWithRivals() {
  return {
    url: "https://berkeleyplumbingco.com",
    name: "Berkeley Plumbing Co",
    aliases: [],
    businessKind: "local_service" as const,
    location: { city: "Berkeley", region: "California", country: "US" },
    category: "plumbing service",
    competitors: [
      { name: "Bay Area Rooter", aliases: [], confirmed: true },
      { name: "Phoenix Pipe Pros", aliases: [], confirmed: true },
      { name: "Mystery Plumbing", aliases: [], confirmed: true },
    ],
    clientDomains: ["berkeleyplumbingco.com"],
    productClaims: [],
    resolvedAt: "2026-07-27T00:00:00.000Z",
    resolverModel: "m",
  };
}

test("a same-trade different-metro rival is dropped with service-area provenance", () => {
  const profile = localProfileWithRivals();
  const rels = normalizeRelationships(
    [
      { competitor: "Bay Area Rooter", verdict: "independent", category: "same_category", service_area: "same_area", evidence: "berkeley" },
      { competitor: "Phoenix Pipe Pros", verdict: "independent", category: "same_category", service_area: "different_area", evidence: "phoenix az" },
      { competitor: "Mystery Plumbing", verdict: "independent", category: "same_category", service_area: "unknown", evidence: "" },
    ],
    profile,
  );

  const { profile: pruned, dropped } = pruneRelatedCompetitors(profile, rels);

  // Same metro kept; unknown kept (recall-safe); only the explicit different_area drops.
  assert.deepEqual(pruned.competitors.map((c) => c.name), ["Bay Area Rooter", "Mystery Plumbing"]);
  assert.equal(dropped.length, 1);
  assert.equal(dropped[0]?.name, "Phoenix Pipe Pros");
  assert.equal(dropped[0]?.serviceAreaMismatch, true);
  // The drop reason is distinguishable from a category mismatch.
  assert.notEqual(dropped[0]?.categoryMismatch, true);
});

test("a missing service_area key defaults to unknown and keeps the competitor", () => {
  const profile = localProfileWithRivals();
  const rels = normalizeRelationships(
    [{ competitor: "Bay Area Rooter", verdict: "independent", category: "same_category", evidence: "" }],
    profile,
  );
  assert.equal(rels.find((r) => r.competitor === "Bay Area Rooter")?.serviceAreaMatch, "unknown");
  const { dropped } = pruneRelatedCompetitors(profile, rels);
  assert.equal(dropped.length, 0);
});
