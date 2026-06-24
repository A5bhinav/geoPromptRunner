import assert from "node:assert/strict";
import { test } from "node:test";
import { selectFindings, selectWhyGaps } from "../src/select/selectFindings.ts";
import type { CompanyProfile } from "../src/types/domain.ts";
import type { AnswerRecord, ReportPayload, SiteAuditPayload } from "../src/types/platform.ts";

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

test("lead favors a demand-side loss (category) over a comparison; comparison goes to the table", () => {
  const r = selectFindings(profile(), baseReport(), answers());
  assert.equal(r.ok, true);
  if (!r.ok) return;
  // q1 is category (demand-side) -> hero lead over q2 comparison, even though q2
  // is on the more credible engine. The hero engine follows the lead, and the
  // comparison still appears in the pattern table (corroboration, not the hook).
  assert.equal(r.lead.queryId, "q1");
  assert.equal(r.lead.intent, "category");
  assert.equal(r.heroEngine, "openai");
  assert.equal(r.lead.verbatimQuery, "best CRM?");
  assert.ok(r.table.some((f) => f.queryId === "q2"));
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

// Regression for the hero-engine-overrides-intent bug: a high-intent finding on a
// LESS credible engine must still win the lead over a low-intent finding on the
// most credible engine. The old code picked the hero engine by credibility alone,
// then took the best row on it — which discarded the comparison cell below.
test("lead follows intent even when the comparison is on a less-credible engine", () => {
  const report = baseReport({
    losing_queries: [
      // comparison (intent 5) on openai (cred 3) -> score 53
      { query_id: "q1", intent: "comparison", engine_name: "openai", competitor: "Salesforce" },
      // brand (intent 1) on perplexity (cred 5) -> score 15
      { query_id: "q2", intent: "brand", engine_name: "perplexity", competitor: "Salesforce" },
    ],
  });
  const ans: AnswerRecord[] = [
    {
      query_id: "q1", intent: "comparison", prompt: "best CRM vs Salesforce?",
      engine_name: "openai", run_index: 0, response: "Salesforce wins.", citations: [], timestamp: "t",
    },
    {
      query_id: "q2", intent: "brand", prompt: "is Acme any good?",
      engine_name: "perplexity", run_index: 0, response: "Salesforce is better.", citations: [], timestamp: "t",
    },
  ];
  const r = selectFindings(profile(), report, ans);
  assert.equal(r.ok, true);
  if (!r.ok) return;
  // The comparison cell (q1) outscores the brand cell, so it leads — and the hero
  // engine follows the lead rather than being chosen on credibility alone.
  assert.equal(r.lead.queryId, "q1");
  assert.equal(r.lead.intent, "comparison");
  assert.equal(r.heroEngine, "openai");
});

// Regression for #2: a competitor named only by an alias still counts in the
// headline. Salesforce's alias "SFDC" appears in q1's answer; the bare-name
// matcher would have missed it and undercounted competitorAppears.
test("headline counts competitor mentioned only by an alias", () => {
  const p = profile();
  p.competitors = [{ name: "Salesforce", aliases: ["SFDC"], confirmed: true }];
  const ans: AnswerRecord[] = [
    {
      query_id: "q1", intent: "category", prompt: "best CRM?", engine_name: "openai",
      run_index: 0, response: "SFDC is the leader.", citations: [], timestamp: "t",
    },
    {
      query_id: "q2", intent: "comparison", prompt: "alternatives?", engine_name: "perplexity",
      run_index: 0, response: "Salesforce alternatives include HubSpot.", citations: [], timestamp: "t",
    },
  ];
  const r = selectFindings(p, baseReport(), ans);
  assert.equal(r.ok, true);
  if (!r.ok) return;
  // Both queries name the competitor (q1 via alias, q2 by name).
  assert.equal(r.headline.competitorAppears, 2);
});

function siteAudit(roadmap: SiteAuditPayload["roadmap"], present = true): SiteAuditPayload {
  return {
    present,
    domain: "acme.io",
    pages_crawled: 3,
    checks: [],
    summary: {},
    errors: 0,
    offsite: [],
    roadmap,
  };
}

test("selectWhyGaps: [] without a site audit / no gaps", () => {
  assert.deepEqual(selectWhyGaps(null), []);
  assert.deepEqual(selectWhyGaps(undefined), []);
  assert.deepEqual(selectWhyGaps(siteAudit([])), []);
  assert.deepEqual(selectWhyGaps(siteAudit([], false)), []); // present:false
});

test("selectWhyGaps orders by phase, fail-before-partial, then impact", () => {
  const gaps = selectWhyGaps(
    siteAudit([
      { category: "content", check_name: "fact density", status: "partial", impact_label: "Low", effort: "low", phase: 2 },
      { category: "technical", check_name: "robots.txt allows AI crawlers", status: "fail", impact_label: "High", effort: "low", phase: 1 },
      { category: "schema", check_name: "schema.org markup", status: "fail", impact_label: "Medium", effort: "medium", phase: 2 },
    ]),
    2,
  );
  assert.equal(gaps.length, 2);
  assert.equal(gaps[0]!.label, "robots.txt allows AI crawlers"); // phase 1 wins
  assert.equal(gaps[1]!.label, "schema.org markup"); // phase 2 fail/Medium beats phase 2 partial/Low
  assert.equal(gaps[0]!.status, "fail");
});

// Regression for #4: a losing row with no named competitor is not printable.
test("losing rows without a named competitor are refused", () => {
  const report = baseReport({
    losing_queries: [
      { query_id: "q1", intent: "comparison", engine_name: "perplexity", competitor: "  " },
      { query_id: "q2", intent: "category", engine_name: "openai", competitor: "" },
    ],
  });
  const r = selectFindings(profile(), report, answers());
  assert.equal(r.ok, false);
});
