import assert from "node:assert/strict";
import { test } from "node:test";
import {
  assembleDraft,
  profileFromStored,
  regenerateFromDraft,
} from "../src/pipeline.ts";
import type { Finding, TeaserDraft } from "../src/types/domain.ts";
import type { AnswerRecord, ReportPayload } from "../src/types/platform.ts";

function baseReport(): ReportPayload {
  return {
    client_name: "Acme",
    run_date: "2026-06-20",
    query_set_version: "t",
    runs_per_query: 1,
    engines: ["perplexity", "openai"],
    competitors: ["YNAB"],
    client_domains: ["acme.io"],
    detection: "judge",
    scorecard: {
      visibility_grade: null,
      share_of_model_client: 0,
      top_competitor: "YNAB",
      top_competitor_share: 1,
      mention_rate_client: 0,
      mention_rate_top_competitor: 1,
      citation_rate_client: 0,
      accuracy_assessed: false,
      accuracy_flag_count: null,
    },
    leaderboard: [],
    by_bucket: [],
    accuracy_flags: [],
    sources: [],
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "openai", competitor: "YNAB" },
    ],
  };
}

function answers(): AnswerRecord[] {
  return [
    {
      query_id: "q1",
      intent: "category",
      prompt: "best budgeting app?",
      engine_name: "openai",
      run_index: 0,
      response: "YNAB is the top pick.",
      citations: [],
      timestamp: "t",
    },
  ];
}

const staleLead: Finding = {
  role: "lead",
  source: "losing_query",
  queryId: "old",
  intent: "comparison",
  engineName: "perplexity",
  competitor: "Stale",
  verbatimQuery: "old query",
  verbatimAnswer: "old answer",
  citations: [],
  rankScore: 0,
};

function savedDraft(): TeaserDraft {
  return {
    prospectUrl: "https://acme.io",
    companyName: "Acme",
    category: "budgeting app",
    runDate: "2026-06-20",
    heroEngine: "perplexity",
    headline: "OLD HEADLINE FROM A PREVIOUS VERSION",
    leadSentence: "old lead",
    headlineNumber: { companyAppears: 9, competitorAppears: 9, competitorName: "Stale", n: 9 },
    stakesLine: "old stakes",
    cta: "old cta",
    lead: staleLead,
    table: [],
    report: baseReport(),
    answers: answers(),
    status: "draft",
  };
}

test("regenerateFromDraft rebuilds from stored report+answers with current copy", () => {
  const r = regenerateFromDraft(savedDraft());
  assert.equal(r.ok, true);
  if (!r.ok) return;
  // Copy is re-derived with the current generator, not the stale stored string.
  assert.notEqual(r.draft.headline, "OLD HEADLINE FROM A PREVIOUS VERSION");
  assert.ok(r.draft.headline.includes("YNAB"), "headline names the stored top competitor");
  // Selection is re-run from stored data (stale lead is replaced).
  assert.equal(r.draft.lead.competitor, "YNAB");
  assert.equal(r.draft.lead.queryId, "q1");
  // Stored report + answers are carried through unchanged.
  assert.equal(r.draft.report.client_name, "Acme");
  assert.equal(r.draft.answers.length, 1);
});

test("regenerateFromDraft fails cleanly when the saved teaser has no stored report", () => {
  const bad = { ...savedDraft(), report: undefined } as unknown as TeaserDraft;
  const r = regenerateFromDraft(bad);
  assert.equal(r.ok, false);
});

test("profileFromStored fills competitors from the report (empty aliases, no crawl)", () => {
  const p = profileFromStored(baseReport(), { url: "https://acme.io", category: "budgeting app" });
  assert.equal(p.name, "Acme");
  assert.deepEqual(
    p.competitors.map((c) => c.name),
    ["YNAB"],
  );
  assert.equal(p.competitors[0]?.aliases.length, 0);
});

test("assembleDraft surfaces a clean reason when nothing loses", () => {
  const empty = { ...baseReport(), losing_queries: [] };
  const r = assembleDraft(
    profileFromStored(empty, { url: "https://acme.io", category: "budgeting app" }),
    empty,
    [],
    "https://acme.io",
  );
  assert.equal(r.ok, false);
});
