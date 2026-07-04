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

test("answerSnippet strips images and inline links, keeping link text", () => {
  const s = answerSnippet("Try ![logo](logo.png) the [Acme docs](https://acme.com/d) now.");
  assert.ok(!s.includes("]("), "no markdown link/image syntax survives");
  assert.ok(s.includes("Acme docs"), "inline link text is kept");
  assert.ok(!s.includes("logo.png"), "image is dropped");
});

test("answerSnippet truncates a numbered list cleanly (no dangling '2.')", () => {
  const raw =
    "There are several tools. Some of the best options include: " +
    "1. Planner 5D is a user-friendly app with a vast library of design elements. " +
    "2. RoomSketcher is another strong option with many floor-plan templates. " +
    "3. SmartDraw offers templates and AI assist.";
  const s = answerSnippet(raw, 180);
  assert.ok(s.endsWith("…"), "marked as truncated with an ellipsis");
  assert.ok(!/\d+\.\s*…$/.test(s), "no dangling list number before the ellipsis");
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

test("answerSnippet preserves a leading **bold** marker (doesn't strip it as a bullet)", () => {
  const s = answerSnippet("**Strong** and **JEFIT** differ in database size.");
  assert.ok(s.startsWith("**Strong**"), "leading bold marker is kept, not eaten");
  assert.equal((s.match(/\*\*/g) ?? []).length % 2, 0, "bold markers stay balanced");
});

test("answerSnippet still strips real leading bullets and headers (marker + space)", () => {
  assert.equal(answerSnippet("- First point about tracking."), "First point about tracking.");
  assert.equal(answerSnippet("# Heading then prose."), "Heading then prose.");
});

function finding(over: Partial<Finding> = {}): Finding {
  return {
    role: "lead",
    source: "losing_query",
    queryId: "q01",
    intent: "comparison",
    engineName: "perplexity",
    competitor: "Northstar",
    prominence: "recommended_first",
    verbatimQuery: "Northstar vs Vantage?",
    verbatimAnswer: PERPLEXITY_RAW,
    citations: ["https://nops.io/x"],
    rankScore: 50,
    runsObserved: 1,
    runsConfirming: 1,
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

// Regression: a competitor name that collides with an HTML tag name ("Strong"
// vs <strong>). Highlighting after boldToHtml used to match the letters inside
// the <strong> tags and shred them into literal "strong>" text.
test("renderProofCard does not corrupt <strong> tags when competitor is 'Strong'", () => {
  const html = renderProofCard(
    "Fitbod",
    finding({
      competitor: "Strong",
      verbatimQuery: "how do Strong and JEFIT compare?",
      verbatimAnswer: "**Strong** and **JEFIT** differ. **Strong** offers a minimalist logger.",
    }),
    "2026-07-04",
  );
  assert.ok(html.includes('<mark class="competitor">Strong</mark>'), "brand word is highlighted");
  assert.ok(html.includes("<strong>"), "bold survives as a real tag");
  assert.ok(!html.includes('<mark class="competitor">strong</mark>'), "the <strong> tag name is NOT wrapped");
  assert.ok(!html.includes("<<mark") && !html.includes("</<mark"), "no shredded/nested tags");
});
