import assert from "node:assert/strict";
import { test } from "node:test";
import {
  competitorVerb,
  engineLabel,
  headline,
  leadSentence,
  proofCaption,
  reproNote,
  stakesLine,
} from "../src/render/copy.ts";
import type { Finding, HeadlineNumber } from "../src/types/domain.ts";
import type { Prominence } from "../src/types/platform.ts";

function lead(prominence: Prominence | null, repro?: { observed: number; confirming: number }): Finding {
  return {
    role: "lead",
    source: "losing_query",
    queryId: "q1",
    intent: "category",
    engineName: "perplexity",
    competitor: "Whoop",
    prominence,
    verbatimQuery: "best strength training wearable?",
    verbatimAnswer: "Whoop is the top pick.",
    citations: [],
    rankScore: 50,
    runsObserved: repro?.observed ?? 1,
    runsConfirming: repro?.confirming ?? 1,
  };
}

test("competitorVerb: 'recommends' only for recommended_first", () => {
  assert.equal(competitorVerb(lead("recommended_first")).active, "recommends");
  assert.equal(competitorVerb(lead("mid_pack")).active, "features");
  assert.equal(competitorVerb(lead("buried")).active, "mentions");
  assert.equal(competitorVerb(lead("also_ran")).active, "mentions");
});

test("competitorVerb: unknown prominence (null) downgrades to 'mentions' — cold outreach never prints its strongest verb on an unmeasured claim (S7)", () => {
  assert.equal(competitorVerb(lead(null)).active, "mentions");
});

test("leadSentence grades its verb by prominence", () => {
  assert.ok(leadSentence("Fort", lead("recommended_first")).includes("it recommends Whoop"));
  assert.ok(leadSentence("Fort", lead("also_ran")).includes("it mentions Whoop"));
  assert.ok(!leadSentence("Fort", lead("also_ran")).includes("recommends"));
});

test("proofCaption grades its verb by prominence", () => {
  assert.ok(proofCaption("Fort", lead("recommended_first")).includes("Whoop is recommended"));
  assert.ok(proofCaption("Fort", lead("mid_pack")).includes("Whoop is featured"));
});

test("headline: 'sending your buyers' needs recommended_first; else a presence claim", () => {
  assert.equal(
    headline("Fort", lead("recommended_first")),
    "AI is sending your buyers to Whoop — not Fort.",
  );
  assert.equal(
    headline("Fort", lead("buried")),
    "When your buyers ask AI, Whoop is in the answer — Fort isn't.",
  );
});

test("stakesLine only claims the client's measured absence, not competitor presence", () => {
  // 2 of 7 queries had nobody tracked in them — the stakes line must not say
  // every missed query pointed buyers to a competitor.
  const h: HeadlineNumber = { companyAppears: 1, competitorAppears: 4, competitorName: "Whoop", n: 7 };
  const s = stakesLine("Fort", h);
  assert.ok(s.includes("6 of 7"), "gap = n - companyAppears");
  assert.ok(!s.toLowerCase().includes("pointed to a competitor"), "no per-query competitor claim");
});

test("stakesLine singular query", () => {
  const h: HeadlineNumber = { companyAppears: 2, competitorAppears: 3, competitorName: "Whoop", n: 3 };
  assert.ok(stakesLine("Fort", h).includes("1 of 3 buyer query answered"));
});

// R7: an unknown engine id must never leak into a deliverable as raw snake_case,
// and the Bing Copilot family is labelled.
test("engineLabel humanizes an unknown engine id and knows Copilot", () => {
  assert.equal(engineLabel("bing_copilot"), "Copilot");
  assert.equal(engineLabel("copilot"), "Copilot");
  assert.equal(engineLabel("some_new_engine"), "Some New Engine");
  assert.equal(engineLabel("perplexity"), "Perplexity");
});

test("reproNote: printed only when the loss held on every run (>=2)", () => {
  assert.equal(reproNote(lead("recommended_first", { observed: 3, confirming: 3 })), "Asked 3 separate times — Whoop came up every time. This isn't a one-off.");
  // A single sample makes no repeatability claim.
  assert.equal(reproNote(lead("recommended_first", { observed: 1, confirming: 1 })), "");
  // Held on only 2 of 3 → not "every time" → no claim.
  assert.equal(reproNote(lead("recommended_first", { observed: 3, confirming: 2 })), "");
});
