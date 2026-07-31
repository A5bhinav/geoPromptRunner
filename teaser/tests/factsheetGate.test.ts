/**
 * §8's send-permission table on the TypeScript side.
 *
 * This mirrors `SENDABLE_SEVERITIES` in `src/audit/factsheet/gate.py`, and a
 * mirror is exactly the thing that drifts. The asymmetry that matters: a flag
 * wrongly withheld costs a finding, a flag wrongly sent is a false accusation in
 * a document we mailed a stranger. So every assertion below is on the deny side.
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

import { maySendFlag, type Verification } from "../src/types/platform.ts";

const TIERS: Verification[] = [
  "public_source_only",
  "cross_confirmed",
  "client_confirmed",
];

test("an unconfirmed sheet may send low and med", () => {
  assert.equal(maySendFlag("public_source_only", "low"), true);
  assert.equal(maySendFlag("public_source_only", "med"), true);
});

test("an unconfirmed sheet may NOT send high", () => {
  // One public source is not enough to accuse a named vendor of a
  // decision-changing error in cold outreach.
  assert.equal(maySendFlag("public_source_only", "high"), false);
});

test("a corroborated or confirmed sheet may send any known severity", () => {
  for (const tier of ["cross_confirmed", "client_confirmed"] as Verification[]) {
    for (const severity of ["low", "med", "high"]) {
      assert.equal(maySendFlag(tier, severity), true, `${tier}/${severity}`);
    }
  }
});

test("a missing tier refuses everything", () => {
  // No sheet, or a payload predating the field. A flag with no provenance is
  // precisely the one not to mail a stranger.
  for (const severity of ["low", "med", "high"]) {
    assert.equal(maySendFlag(null, severity), false);
    assert.equal(maySendFlag(undefined, severity), false);
  }
});

test("an unrecognised severity is refused, not coerced", () => {
  // "critical" is the tier the audit-packaging spec (P0-T2) adds. Until it is in
  // the table it must not slip through as "not in the deny list" — otherwise it
  // ships to strangers off an unconfirmed sheet on the day it lands.
  for (const tier of TIERS) {
    for (const severity of ["critical", "CRITICAL", "", "urgent", "High"]) {
      assert.equal(maySendFlag(tier, severity), false, `${tier}/${severity}`);
    }
  }
});

test("an unknown tier refuses rather than throwing", () => {
  assert.equal(maySendFlag("signed" as Verification, "low"), false);
});
