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
  prominence: null,
  verbatimQuery: "old query",
  verbatimAnswer: "old answer",
  citations: [],
  rankScore: 0,
  runsObserved: 1,
  runsConfirming: 1,
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

// T3: a teaser regenerated from storage must rehydrate client aliases, so an
// answer that names the client only by an alias is counted as PRESENCE, not a
// loss. The stored report carries only names, so the aliases ride on the draft.
test("regeneration rehydrates client aliases: an alias-only client mention isn't a loss", () => {
  const report: ReportPayload = {
    ...baseReport(),
    client_name: "You Need A Budget",
    competitors: ["Monarch Money"],
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "openai", competitor: "Monarch Money" },
    ],
  };
  const ans: AnswerRecord[] = [
    {
      query_id: "q1",
      intent: "category",
      prompt: "best budgeting app?",
      engine_name: "openai",
      run_index: 0,
      // client present ONLY via the alias "YNAB"; competitor also present.
      response: "YNAB and Monarch Money are both solid.",
      citations: [],
      timestamp: "t",
    },
  ];
  const base: TeaserDraft = { ...savedDraft(), report, answers: ans, category: "budgeting app" };

  // Alias-blind (no rehydrated aliases): the alias-only mention is missed, so the
  // client reads as absent and the query is (wrongly) printed as a loss.
  const blind = regenerateFromDraft({ ...base, clientAliases: [], competitorAliases: {} });
  assert.equal(blind.ok, true, "without aliases the alias-only mention is wrongly a loss");

  // With aliases rehydrated: the client is present via "YNAB" → the competitor no
  // longer out-appears it → no honest hero → not a printable loss.
  const withAliases = regenerateFromDraft({
    ...base,
    clientAliases: ["YNAB"],
    competitorAliases: { "Monarch Money": [] },
  });
  assert.equal(withAliases.ok, false, "the alias-only mention counts as presence, not a loss");
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
