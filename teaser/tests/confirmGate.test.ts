import assert from "node:assert/strict";
import { test } from "node:test";
import { applySelection, confirmAll, parseSelection } from "../src/confirmGate.ts";
import type { CompanyProfile, GeneratedQuerySet } from "../src/types/domain.ts";

function profile(): CompanyProfile {
  return {
    url: "https://fort.fit",
    name: "Fort",
    category: "strength training wearable",
    competitors: [
      { name: "Whoop", aliases: [], confirmed: false },
      { name: "Oura", aliases: ["Oura Ring"], confirmed: false },
      { name: "Garmin", aliases: [], confirmed: false },
    ],
    clientDomains: ["fort.fit"],
    productClaims: [],
    resolvedAt: "2026-07-01T00:00:00Z",
    resolverModel: "claude-haiku-4-5",
  };
}

function querySet(): GeneratedQuerySet {
  return {
    version: "t1",
    queries: [
      { query_id: "q1", text: "best strength training wearable?", intent: "category", weight: 5, persona: null },
      { query_id: "q2", text: "Whoop vs Oura Ring for lifting?", intent: "comparison", weight: 4, persona: null },
      { query_id: "q3", text: "is Garmin good for strength training?", intent: "comparison", weight: 3, persona: null },
      { query_id: "q4", text: "Fort wearable reviews", intent: "brand", weight: 1, persona: null },
    ],
  };
}

test("parseSelection: yes/empty keeps all, no aborts", () => {
  assert.deepEqual(parseSelection("", 3), { kind: "all" });
  assert.deepEqual(parseSelection("y", 3), { kind: "all" });
  assert.deepEqual(parseSelection("YES", 3), { kind: "all" });
  assert.deepEqual(parseSelection("n", 3), { kind: "abort" });
});

test("parseSelection: number lists are 1-based, deduped, validated", () => {
  assert.deepEqual(parseSelection("1,3", 3), { kind: "keep", indices: [0, 2] });
  assert.deepEqual(parseSelection("2 2", 3), { kind: "keep", indices: [1] });
  assert.equal(parseSelection("4", 3).kind, "invalid");
  assert.equal(parseSelection("0", 3).kind, "invalid");
  assert.equal(parseSelection("whoop", 3).kind, "invalid");
});

test("applySelection marks kept competitors confirmed and drops the rest", () => {
  const r = applySelection(profile(), querySet(), [0, 2]);
  assert.deepEqual(
    r.profile.competitors.map((c) => c.name),
    ["Whoop", "Garmin"],
  );
  assert.ok(r.profile.competitors.every((c) => c.confirmed));
});

test("applySelection prunes queries naming a dropped competitor — including by alias", () => {
  // Drop Oura: q2 names it only via the alias "Oura Ring" and must go too.
  const r = applySelection(profile(), querySet(), [0, 2]);
  assert.deepEqual(
    r.querySet.queries.map((q) => q.query_id),
    ["q1", "q3", "q4"],
  );
  assert.deepEqual(r.droppedQueries, ["Whoop vs Oura Ring for lifting?"]);
});

test("applySelection keeps all queries when nothing is dropped", () => {
  const r = applySelection(profile(), querySet(), [0, 1, 2]);
  assert.equal(r.querySet.queries.length, 4);
  assert.deepEqual(r.droppedQueries, []);
});

test("confirmAll flips every competitor to confirmed without touching queries", () => {
  const r = confirmAll(profile(), querySet());
  assert.ok(r.profile.competitors.every((c) => c.confirmed));
  assert.equal(r.querySet.queries.length, 4);
});
