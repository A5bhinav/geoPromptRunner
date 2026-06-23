import assert from "node:assert/strict";
import { test } from "node:test";
import { selectFindings } from "../src/select/selectFindings.ts";
import type { CompanyProfile } from "../src/types/domain.ts";
import type { AnswerRecord, ReportPayload } from "../src/types/platform.ts";

function profile(): CompanyProfile {
  return {
    url: "https://acme.io",
    name: "Acme",
    category: "CRM",
    competitors: [{ name: "Salesforce", aliases: [], confirmed: true }],
    clientDomains: ["acme.io"],
    productClaims: [],
    resolvedAt: "1970-01-01T00:00:00Z",
    resolverModel: "mock",
  };
}

function baseReport(over: Partial<ReportPayload> = {}): ReportPayload {
  return {
    client_name: "Acme",
    run_date: "2026-06-20",
    query_set_version: "t",
    runs_per_query: 1,
    engines: ["perplexity", "openai"],
    competitors: ["Salesforce"],
    client_domains: ["acme.io"],
    detection: "judge",
    scorecard: {
      visibility_grade: null,
      share_of_model_client: 0,
      top_competitor: "Salesforce",
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
      { query_id: "q1", intent: "category", engine_name: "openai", competitor: "Salesforce" },
      { query_id: "q2", intent: "comparison", engine_name: "perplexity", competitor: "Salesforce" },
    ],
    ...over,
  };
}

function answers(): AnswerRecord[] {
  return [
    {
      query_id: "q1",
      intent: "category",
      prompt: "best CRM?",
      engine_name: "openai",
      run_index: 0,
      response: "Salesforce is the top pick.",
      citations: ["https://g2.com/x"],
      timestamp: "t",
    },
    {
      query_id: "q2",
      intent: "comparison",
      prompt: "alternatives to Salesforce?",
      engine_name: "perplexity",
      run_index: 0,
      response: "Salesforce alternatives include HubSpot.",
      citations: [],
      timestamp: "t",
    },
  ];
}

test("lead is the highest-intent losing cell on the most credible engine", () => {
  const r = selectFindings(profile(), baseReport(), answers());
  assert.equal(r.ok, true);
  if (!r.ok) return;
  // q2 is comparison (intent 5) on perplexity (cred 5) -> beats q1 category on openai.
  assert.equal(r.lead.queryId, "q2");
  assert.equal(r.heroEngine, "perplexity");
  assert.equal(r.lead.verbatimQuery, "alternatives to Salesforce?");
});

test("table holds distinct queries, not the lead's", () => {
  const r = selectFindings(profile(), baseReport(), answers());
  assert.equal(r.ok, true);
  if (!r.ok) return;
  for (const f of r.table) assert.notEqual(f.queryId, r.lead.queryId);
});

test("regex detection mode is refused", () => {
  const r = selectFindings(profile(), baseReport({ detection: "regex" }), answers());
  assert.equal(r.ok, false);
});

test("no losing queries -> no finding", () => {
  const r = selectFindings(profile(), baseReport({ losing_queries: [] }), answers());
  assert.equal(r.ok, false);
});

test("headline counts client absent, competitor present", () => {
  const r = selectFindings(profile(), baseReport(), answers());
  assert.equal(r.ok, true);
  if (!r.ok) return;
  assert.equal(r.headline.companyAppears, 0);
  assert.equal(r.headline.competitorAppears, 2);
  assert.equal(r.headline.n, 2);
});
