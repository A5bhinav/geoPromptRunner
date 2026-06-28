import assert from "node:assert/strict";
import { test } from "node:test";
import { answerSnippet, renderProofCard } from "../src/render/proofCard.ts";
import type { Finding } from "../src/types/domain.ts";

/** A real-engine answer like Perplexity returns: Markdown bold, a table, [n] markers. */
const PERPLEXITY_RAW =
  'Neither **Northstar** nor **Vantage** is a suitable app for general ' +
  '**expense tracking** because both are specialized platforms. ' +
  '| Feature | Northstar | Vantage | | :---| :---| :---| | **Primary Purpose** | ' +
  'Hedge fund risk [7] | Cloud cost [1] |';

test("answerSnippet strips the table, keeping only the leading prose", () => {
  const s = answerSnippet(PERPLEXITY_RAW);
  assert.ok(!s.includes("|"), "no table cells survive");
  assert.ok(!s.includes(":---"), "no table separators survive");
  assert.ok(s.startsWith("Neither **Northstar**"), "leading prose is kept");
});

test("answerSnippet drops [n] citation markers", () => {
  assert.ok(!answerSnippet("Best option is Northstar [7] today.").includes("[7]"));
});

test("answerSnippet truncates long prose on a boundary with an ellipsis", () => {
  const long = "Sentence one is here. " + "word ".repeat(200);
  const s = answerSnippet(long, 80);
  assert.ok(s.length <= 82, "respects the cap (plus ellipsis)");
  // Either ends at a sentence boundary or is marked truncated.
  assert.ok(s.endsWith(".") || s.endsWith("…"));
});

test("answerSnippet leaves short, clean answers untouched (mock answers)", () => {
  const mock = 'For "best crm?", the most recommended option is Salesforce.';
  assert.equal(answerSnippet(mock), mock);
});

function finding(over: Partial<Finding> = {}): Finding {
  return {
    role: "lead",
    source: "losing_query",
    queryId: "q01",
    intent: "comparison",
    engineName: "perplexity",
    competitor: "Northstar",
    verbatimQuery: "Northstar vs Vantage?",
    verbatimAnswer: PERPLEXITY_RAW,
    citations: ["https://nops.io/x"],
    rankScore: 50,
    ...over,
  };
}

test("renderProofCard renders bold as <strong>, never literal **", () => {
  const html = renderProofCard("Anoria", finding(), "2026-06-24");
  assert.ok(html.includes("<strong>"), "Markdown bold becomes real bold");
  assert.ok(!html.includes("**"), "no literal asterisks reach the card");
  assert.ok(!html.includes("| Feature |"), "no Markdown table reaches the card");
});

test("renderProofCard still highlights the competitor", () => {
  const html = renderProofCard("Anoria", finding(), "2026-06-24");
  assert.ok(html.includes('<mark class="competitor">'), "competitor is highlighted");
});
