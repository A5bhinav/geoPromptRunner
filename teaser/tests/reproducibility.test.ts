import assert from "node:assert/strict";
import { test } from "node:test";
import {
  countReproduction,
  reproduces,
  selectFindings,
} from "../src/select/selectFindings.ts";
import { buildMatcher } from "../src/select/entity.ts";
import type { CompanyProfile } from "../src/types/domain.ts";
import type { AnswerRecord, ReportPayload } from "../src/types/platform.ts";

function ans(query_id: string, run_index: number, response: string): AnswerRecord {
  return {
    query_id,
    intent: "category",
    prompt: "best budgeting app?",
    engine_name: "openai",
    run_index,
    response,
    citations: [],
    timestamp: "t",
  };
}

test("countReproduction counts runs where client is absent and competitor present", () => {
  const client = buildMatcher("Acme");
  const comp = buildMatcher("YNAB");
  const answers = [
    ans("q1", 0, "YNAB is the top pick."), // confirms
    ans("q1", 1, "YNAB wins again."), // confirms
    ans("q1", 2, "Acme and YNAB both work."), // client present → not confirming
  ];
  const r = countReproduction(answers, "q1", "openai", client, comp);
  assert.deepEqual(r, { observed: 3, confirming: 2 });
});

test("reproduces requires all observed runs to confirm and at least 2 runs", () => {
  assert.equal(reproduces({ observed: 3, confirming: 3 }), true);
  assert.equal(reproduces({ observed: 2, confirming: 2 }), true);
  assert.equal(reproduces({ observed: 3, confirming: 2 }), false);
  assert.equal(reproduces({ observed: 1, confirming: 1 }), false); // single sample
  assert.equal(reproduces({ observed: 0, confirming: 0 }), false);
});

function profile(): CompanyProfile {
  return {
    url: "https://acme.io",
    name: "Acme",
    category: "budgeting app",
    competitors: [{ name: "YNAB", aliases: [], confirmed: true }],
    clientDomains: ["acme.io"],
    productClaims: [],
    resolvedAt: "1970-01-01T00:00:00Z",
    resolverModel: "mock",
  };
}

// q1 is category (normally the hero over a comparison) but FLAKY across runs;
// q2 is a comparison that reproduces on every run. The reproducing loss must win
// the hero slot — a claim a prospect can re-run and see beats a higher-intent
// one that doesn't hold up.
function report(): ReportPayload {
  return {
    client_name: "Acme",
    run_date: "2026-06-20",
    query_set_version: "t",
    runs_per_query: 2,
    engines: ["openai", "perplexity"],
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
      { query_id: "q1", intent: "category", engine_name: "openai", competitor: "YNAB", prominence: "recommended_first" },
      { query_id: "q2", intent: "comparison", engine_name: "perplexity", competitor: "YNAB", prominence: "recommended_first" },
    ],
  };
}

function answers(): AnswerRecord[] {
  return [
    // q1 category: flaky — run 1 names Acme, so the loss doesn't reproduce.
    { query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "openai", run_index: 0, response: "YNAB is the top pick.", citations: [], timestamp: "t" },
    { query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "openai", run_index: 1, response: "Acme and YNAB are both great.", citations: [], timestamp: "t" },
    // q2 comparison: YNAB present, Acme absent on BOTH runs — reproduces.
    { query_id: "q2", intent: "comparison", prompt: "alternatives to Monarch?", engine_name: "perplexity", run_index: 0, response: "YNAB is a strong pick.", citations: [], timestamp: "t" },
    { query_id: "q2", intent: "comparison", prompt: "alternatives to Monarch?", engine_name: "perplexity", run_index: 1, response: "Most people pick YNAB.", citations: [], timestamp: "t" },
  ];
}

test("lead prefers a loss that reproduces across runs over a higher-intent flaky one", () => {
  const r = selectFindings(profile(), report(), answers());
  assert.equal(r.ok, true);
  if (!r.ok) return;
  assert.equal(r.lead.queryId, "q2", "reproducing comparison wins the hero slot over the flaky category");
  assert.equal(r.lead.runsObserved, 2);
  assert.equal(r.lead.runsConfirming, 2);
});
