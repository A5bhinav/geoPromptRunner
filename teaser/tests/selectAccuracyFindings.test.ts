/**
 * F3 — accuracy flags become printable findings, behind three gates.
 *
 * Every test here is a way an unbacked accusation could reach a stranger:
 * a severity the sheet has not earned, a flag that cannot name its engine, or
 * one with no verbatim answer to quote.
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

import { selectAccuracyFindings } from "../src/select/selectFindings.ts";
import type { AnswerRecord, FlagRow, ReportPayload, Verification } from "../src/types/platform.ts";

function flag(over: Partial<FlagRow> = {}): FlagRow {
  return {
    type: "wrong_pricing",
    severity: "med",
    claim: "Fort costs $349",
    reality: "Pre-order price $289, struck-through $348.",
    query_id: "brd-02",
    engine_name: "perplexity",
    intent: "brand",
    run_index: 0,
    ...over,
  };
}

function answer(over: Partial<AnswerRecord> = {}): AnswerRecord {
  return {
    query_id: "brd-02",
    engine_name: "perplexity",
    intent: "brand",
    run_index: 0,
    prompt: "how much does the Fort wearable cost?",
    response: "The Fort band retails for $349.",
    citations: ["https://fort.cx/order"],
    ...over,
  } as AnswerRecord;
}

function report(flags: FlagRow[], tier: Verification | null): ReportPayload {
  return {
    accuracy_flags: flags,
    fact_sheet_verification: tier,
  } as unknown as ReportPayload;
}

test("a med flag on an unconfirmed sheet is printable", () => {
  const out = selectAccuracyFindings(report([flag()], "public_source_only"), [answer()]);
  assert.equal(out.length, 1);
  const found = out[0];
  assert.ok(found);
  assert.equal(found.source, "accuracy_flag");
  assert.equal(found.role, "lead");
  assert.equal(found.engineName, "perplexity");
  assert.equal(found.verbatimAnswer, "The Fort band retails for $349.");
  assert.equal(found.flag?.reality, "Pre-order price $289, struck-through $348.");
  // No rival — the subject is the client's own facts.
  assert.equal(found.competitor, "");
  assert.equal(found.prominence, null);
});

test("a HIGH flag on an unconfirmed sheet is suppressed, not downgraded", () => {
  const out = selectAccuracyFindings(
    report([flag({ severity: "high" })], "public_source_only"),
    [answer()],
  );
  assert.deepEqual(out, []);
});

test("the same HIGH flag ships once the client confirms the sheet", () => {
  const out = selectAccuracyFindings(
    report([flag({ severity: "high" })], "client_confirmed"),
    [answer()],
  );
  assert.equal(out.length, 1);
  assert.equal(out[0]?.flag?.severity, "high");
});

test("no fact sheet means no accuracy findings at all", () => {
  // A flag with no sheet behind it has no provenance a client could check.
  assert.deepEqual(selectAccuracyFindings(report([flag()], null), [answer()]), []);
});

test("a flag with no provenance is dropped", () => {
  // Legacy payloads predating P0-T1: cannot name the engine, so cannot be
  // attributed, so cannot be printed.
  const out = selectAccuracyFindings(
    report([flag({ query_id: "", engine_name: "" })], "client_confirmed"),
    [answer()],
  );
  assert.deepEqual(out, []);
});

test("a flag that joins to no verbatim answer is dropped", () => {
  const out = selectAccuracyFindings(
    report([flag({ query_id: "brd-99" })], "client_confirmed"),
    [answer()],
  );
  assert.deepEqual(out, []);
});

test("one finding per cell even when two lines are contradicted", () => {
  const out = selectAccuracyFindings(
    report([flag(), flag({ type: "stale", claim: "ships 2026" })], "client_confirmed"),
    [answer()],
  );
  assert.equal(out.length, 1, "the same cell contradicting two lines is one observation");
});

test("findings rank by severity then deterministically", () => {
  const flags = [
    flag({ severity: "low", query_id: "cat-01", engine_name: "gemini_grounded" }),
    flag({ severity: "high", query_id: "brd-02", engine_name: "perplexity" }),
    flag({ severity: "med", query_id: "cmp-03", engine_name: "openai" }),
  ];
  const answers = [
    answer({ query_id: "cat-01", engine_name: "gemini_grounded" }),
    answer({ query_id: "brd-02", engine_name: "perplexity" }),
    answer({ query_id: "cmp-03", engine_name: "openai" }),
  ];
  const out = selectAccuracyFindings(report(flags, "client_confirmed"), answers);
  assert.deepEqual(out.map((f) => f.flag?.severity), ["high", "med", "low"]);
  assert.equal(out[0]?.role, "lead");
  assert.deepEqual(out.slice(1).map((f) => f.role), ["table", "table"]);
});

test("accuracy findings never claim a reproduction they did not measure", () => {
  const out = selectAccuracyFindings(report([flag()], "public_source_only"), [answer()]);
  // 1/1 would read as "we tried once and it held". The judge scored one cell.
  assert.equal(out[0]?.runsObserved, 0);
  assert.equal(out[0]?.runsConfirming, 0);
});

test("max caps the number of findings", () => {
  const flags = [1, 2, 3, 4].map((i) => flag({ query_id: `q-${i}` }));
  const answers = [1, 2, 3, 4].map((i) => answer({ query_id: `q-${i}` }));
  assert.equal(selectAccuracyFindings(report(flags, "client_confirmed"), answers, 2).length, 2);
});
