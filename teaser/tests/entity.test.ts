import assert from "node:assert/strict";
import { test } from "node:test";
import { buildMatcher } from "../src/select/entity.ts";

// S5: a comma-joined competitor string ("Whoop, Fitbit") must become real
// alternatives, not a single literal that never fires inside prose.
test("buildMatcher splits a comma-joined competitor into alternatives", () => {
  const m = buildMatcher("Whoop, Fitbit");
  assert.equal(m("I recommend Fitbit for most people."), true);
  assert.equal(m("Whoop is a great tracker."), true);
});

// S5: an ambiguous common-word brand matches case-SENSITIVELY so the everyday
// word ("mint" the herb) doesn't register as the brand ("Mint").
test("buildMatcher matches an ambiguous common-word brand case-sensitively", () => {
  const m = buildMatcher("Mint");
  assert.equal(m("Try Mint for budgeting."), true); // the brand (capitalized)
  assert.equal(m("add fresh mint to the tea"), false); // the herb, not the brand
});

// Normal (unambiguous) brand names stay case-insensitive.
test("buildMatcher stays case-insensitive for normal brand names", () => {
  const m = buildMatcher("YNAB");
  assert.equal(m("i really love ynab"), true);
});

test("buildMatcher word-boundaries: a brand name inside a longer word doesn't match", () => {
  const m = buildMatcher("Loop"); // ambiguous → case-sensitive
  assert.equal(m("Loop is the app."), true);
  assert.equal(m("there is a loophole here"), false);
});
