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

function draft(over: Partial<TeaserDraft> = {}): TeaserDraft {
  return {
    prospectUrl: "https://acme.io",
    companyName: "Acme",
    category: "budgeting app",
    runDate: "2026-06-20",
    heroEngine: "perplexity",
    headline: "AI is sending your buyers to YNAB — not Acme.",
    leadSentence: "lead",
    headlineNumber: { companyAppears: 0, competitorAppears: 1, competitorName: "YNAB", n: 1 },
    stakesLine: "stakes",
    cta: "cta",
    lead,
    table: [],
    report,
    answers,
    status: "draft",
    ...over,
  };
}

// The <style> block always defines .review-banner, so assert on the rendered
// banner <div> (and its copy), not the bare class name.
const BANNER_DIV = '<div class="review-banner">';

test("a draft renders the send-gate banner", () => {
  const html = renderTeaserHtml(draft({ status: "draft" }));
  assert.ok(html.includes(BANNER_DIV), "banner present");
  assert.ok(html.includes("Draft — not for sending"));
});

test("an approved, fresh draft renders NO banner (clean sendable deliverable)", () => {
  const html = renderTeaserHtml(draft({ status: "approved" }), {}, { stale: false });
  assert.ok(!html.includes(BANNER_DIV), "no banner when approved + fresh");
});

test("an approved but stale draft still warns", () => {
  const html = renderTeaserHtml(draft({ status: "approved" }), {}, { stale: true });
  assert.ok(html.includes(BANNER_DIV));
  assert.ok(html.includes("Stale — re-run before sending"));
});

test("the eyebrow shows the run date and a valid-through date", () => {
  const html = renderTeaserHtml(draft());
  assert.ok(html.includes("2026-06-20"), "run date");
  assert.ok(html.includes("valid through 2026-07-20"), "shelf-life date");
});

test("reproNote renders when the loss held on every run", () => {
  const html = renderTeaserHtml(draft());
  assert.ok(html.includes("Asked 3 separate times"), "reproducibility line present");
});
