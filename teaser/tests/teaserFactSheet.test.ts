/**
 * The teaser attaches an approved fact sheet BY ID, never by embedding its rows.
 *
 * This is the high-volume path, and it was the one that could never show an
 * accuracy finding: nothing populated a sheet, so `fact_sheet_verification` was
 * null on every teaser run and the send gate suppressed everything downstream.
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

import { buildAuditCsv } from "../src/platform/csv.ts";
import type { CompanyProfile, GeneratedQuerySet } from "../src/types/domain.ts";

const profile: CompanyProfile = {
  url: "https://acme.io",
  name: "Acme",
  category: "budgeting app",
  competitors: [{ name: "YNAB", aliases: [], confirmed: true }],
  clientDomains: ["acme.io"],
  productClaims: [],
  factClaims: [{ key: "pricing", value: "Free tier plus $8/mo pro." }],
  resolvedAt: "2026-07-31",
  resolverModel: "test",
};

const querySet: GeneratedQuerySet = {
  version: "t",
  queries: [
    { query_id: "q1", text: "best budgeting app?", intent: "category", weight: 1, persona: null },
  ],
};

const opts = { engines: ["perplexity"], runsPerQuery: 3, judge: true };

test("fact rows are emitted when NO sheet is attached", () => {
  // Unchanged behaviour for every prospect without a reviewed sheet.
  const csv = buildAuditCsv(profile, querySet, opts);
  assert.ok(csv.includes("fact,pricing,"));
});

test("dropping factClaims removes the fact block entirely", () => {
  // What the pipeline does when a sheet IS attached. The platform refuses a run
  // carrying both a sheet id and fact rows — two sources of ground truth for one
  // measurement — so the rows must go, not merely be ignored.
  const csv = buildAuditCsv({ ...profile, factClaims: undefined }, querySet, opts);
  assert.ok(!csv.includes("\nfact,"));
});

test("dropping the fact block changes nothing else about the CSV", () => {
  const withRows = buildAuditCsv(profile, querySet, opts).split("\n");
  const without = buildAuditCsv({ ...profile, factClaims: undefined }, querySet, opts).split("\n");
  const factLines = withRows.filter((l) => l.startsWith("fact,"));
  assert.equal(factLines.length, 1);
  assert.deepEqual(
    withRows.filter((l) => !l.startsWith("fact,")),
    without,
  );
});
