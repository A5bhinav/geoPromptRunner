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
