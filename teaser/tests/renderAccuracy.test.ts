/**
 * B3: an accuracy finding reaches the rendered teaser — and the copy obeys the
 * audit-packaging voice rules, which are legal posture rather than style.
 *
 * Fixtures mirror renderBanner.test.ts so this exercises the real renderer with a
 * complete payload rather than a stub thin enough to hide a crash.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { renderTeaserHtml } from "../src/render/template.ts";
import type { Finding, TeaserDraft } from "../src/types/domain.ts";
import type { AnswerRecord, ReportPayload } from "../src/types/platform.ts";

const lead: Finding = {
  role: "lead",
  source: "losing_query",
  queryId: "q1",
  intent: "category",
  engineName: "perplexity",
  competitor: "YNAB",
  prominence: "recommended_first",
  verbatimQuery: "best budgeting app?",
  verbatimAnswer: "YNAB is the top pick.",
  citations: [],
  rankScore: 50,
  runsObserved: 3,
  runsConfirming: 3,
};

const report: ReportPayload = {
  client_name: "Acme",
  run_date: "2026-06-20",
  query_set_version: "t",
  runs_per_query: 3,
  engines: ["perplexity"],
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
  losing_queries: [],
};

const answers: AnswerRecord[] = [
  { query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "perplexity", run_index: 0, response: "YNAB is the top pick.", citations: [], timestamp: "t" },
];


function accuracyFinding(over: Partial<Finding> = {}): Finding {
  return {
    role: "lead",
    source: "accuracy_flag",
    queryId: "brd-02",
    intent: "brand",
    engineName: "perplexity",
    competitor: "",
    prominence: null,
    verbatimQuery: "how much does it cost?",
    verbatimAnswer: "It retails for $349.",
    citations: [],
    rankScore: 2,
    runsObserved: 0,
    runsConfirming: 0,
    flag: {
      type: "wrong_pricing",
      severity: "med",
      claim: "It retails for $349",
      reality: "Pre-order price $289.",
    },
    ...over,
  };
}

function draft(findings: Finding[]): TeaserDraft {
  return {
    prospectUrl: "https://acme.io",
    companyName: "Acme",
    category: "budgeting app",
    runDate: "2026-06-20",
    heroEngine: "perplexity",
    headline: "h",
    leadSentence: "lead",
    headlineNumber: { companyAppears: 0, competitorAppears: 1, competitorName: "YNAB", n: 1 },
    stakesLine: "stakes",
    cta: "cta",
    lead,
    table: [],
    accuracyFindings: findings,
    report,
    answers,
    status: "draft",
  };
}

test("an accuracy finding renders with its engine, claim and the correct fact", () => {
  const html = renderTeaserHtml(draft([accuracyFinding()]));
  assert.ok(html.includes("What AI states about Acme"));
  assert.ok(html.includes("It retails for $349"));
  assert.ok(html.includes("Pre-order price $289."));
});

test("the copy uses 'states', never a loaded verb", () => {
  // Anthropomorphising a NAMED vendor is imprecise and legally careless, and
  // stale-but-once-true is a different claim from fabricated.
  const html = renderTeaserHtml(draft([accuracyFinding()]));
  assert.ok(/\bstates\b/.test(html));
  for (const banned of ["hallucinat", "falsely claims", "lies about", "made up"]) {
    assert.ok(!html.toLowerCase().includes(banned), banned);
  }
});

test("no occurrence line is printed for an accuracy finding", () => {
  // runsObserved is 0 on purpose: the judge scored ONE cell. "1 of 1" would read
  // as a reproducibility claim we never measured.
  const html = renderTeaserHtml(draft([accuracyFinding()]));
  assert.ok(!html.includes("1 of 1"));
  assert.ok(!html.includes("0 of 0"));
});

test("the non-reproducibility disclosure ships with the section", () => {
  const html = renderTeaserHtml(draft([accuracyFinding()]));
  assert.ok(html.toLowerCase().includes("reproduce"));
});

test("no accuracy findings means no section at all", () => {
  assert.ok(!renderTeaserHtml(draft([])).includes("What AI states about"));
});
