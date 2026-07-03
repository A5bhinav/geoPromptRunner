import assert from "node:assert/strict";
import { test } from "node:test";
import { daysBetween, isStale, SHELF_LIFE_DAYS, validThrough } from "../src/freshness.ts";

test("SHELF_LIFE_DAYS is 30", () => {
  assert.equal(SHELF_LIFE_DAYS, 30);
});

test("validThrough adds the shelf life to the run date (pure, no clock)", () => {
  assert.equal(validThrough("2026-06-20"), "2026-07-20"); // +30 days
  assert.equal(validThrough(""), ""); // unparseable → omitted by caller
  assert.equal(validThrough("not-a-date"), "");
});

test("daysBetween counts whole days", () => {
  assert.equal(daysBetween("2026-06-20", new Date("2026-06-20T00:00:00Z")), 0);
  assert.equal(daysBetween("2026-06-20", new Date("2026-07-20T00:00:00Z")), 30);
  assert.equal(daysBetween("2026-06-20", new Date("2026-07-21T00:00:00Z")), 31);
});

test("isStale flips the day AFTER the shelf life ends", () => {
  assert.equal(isStale("2026-06-20", new Date("2026-07-20T00:00:00Z")), false); // exactly 30 days → still valid
  assert.equal(isStale("2026-06-20", new Date("2026-07-21T00:00:00Z")), true); // 31 days → stale
});

test("isStale never blocks on an unknown date", () => {
  assert.equal(isStale("", new Date("2030-01-01T00:00:00Z")), false);
});
