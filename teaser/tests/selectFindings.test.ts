import assert from "node:assert/strict";
import { test } from "node:test";
import { selectFindings, selectWhyGaps } from "../src/select/selectFindings.ts";
import type { CompanyProfile } from "../src/types/domain.ts";
import type { AnswerRecord, ReportPayload, SiteAuditPayload } from "../src/types/platform.ts";

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

function baseReport(over: Partial<ReportPayload> = {}): ReportPayload {
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
      { query_id: "q2", intent: "comparison", engine_name: "perplexity", competitor: "YNAB" },
    ],
    ...over,
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
      citations: ["https://reddit.com/x"],
      timestamp: "t",
    },
    {
      query_id: "q2",
      intent: "comparison",
      prompt: "alternatives to YNAB?",
      engine_name: "perplexity",
      run_index: 0,
      response: "YNAB alternatives include Monarch Money.",
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
  assert.equal(r.lead.verbatimQuery, "best budgeting app?");
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
      { query_id: "q1", intent: "comparison", engine_name: "openai", competitor: "YNAB" },
      // brand (intent 1) on perplexity (cred 5) -> score 15
      { query_id: "q2", intent: "brand", engine_name: "perplexity", competitor: "YNAB" },
    ],
  });
  const ans: AnswerRecord[] = [
    {
      query_id: "q1", intent: "comparison", prompt: "best budgeting app vs YNAB?",
      engine_name: "openai", run_index: 0, response: "YNAB wins.", citations: [], timestamp: "t",
    },
    {
      query_id: "q2", intent: "brand", prompt: "is Acme any good?",
      engine_name: "perplexity", run_index: 0, response: "YNAB is better.", citations: [], timestamp: "t",
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
// headline. Monarch Money's alias "Monarch" appears in q1's answer; the bare-name
// matcher would have missed it and undercounted competitorAppears.
test("headline counts competitor mentioned only by an alias", () => {
  const p = profile();
  p.competitors = [{ name: "Monarch Money", aliases: ["Monarch"], confirmed: true }];
  const report = baseReport({
    scorecard: { ...baseReport().scorecard, top_competitor: "Monarch Money" },
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "openai", competitor: "Monarch Money" },
      { query_id: "q2", intent: "comparison", engine_name: "perplexity", competitor: "Monarch Money" },
    ],
  });
  const ans: AnswerRecord[] = [
    {
      query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "openai",
      run_index: 0, response: "Monarch is the leader.", citations: [], timestamp: "t",
    },
    {
      query_id: "q2", intent: "comparison", prompt: "alternatives?", engine_name: "perplexity",
      run_index: 0, response: "Monarch Money alternatives include YNAB.", citations: [], timestamp: "t",
    },
  ];
  const r = selectFindings(p, report, ans);
  assert.equal(r.ok, true);
  if (!r.ok) return;
  // Both queries name the competitor (q1 via alias "Monarch", q2 by full name).
  assert.equal(r.headline.competitorAppears, 2);
});

// Honest-hero gate (#2): a hero whose headline its own aggregate contradicts is
// refused. Here the client (Acme) appears in BOTH queries while YNAB appears in
// only one — companyAppears 2 > competitorAppears 1 — so "AI sends buyers to
// YNAB" is false and there's no other competitor to fall back to.
test("refuses a self-contradicting hero: client out-appears the only competitor", () => {
  const report = baseReport({
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "openai", competitor: "YNAB" },
      { query_id: "q2", intent: "comparison", engine_name: "perplexity", competitor: "YNAB" },
    ],
  });
  const ans: AnswerRecord[] = [
    { query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "openai", run_index: 0, response: "Acme and YNAB are both solid.", citations: [], timestamp: "t" },
    { query_id: "q2", intent: "comparison", prompt: "alternatives to Monarch?", engine_name: "perplexity", run_index: 0, response: "Acme is a great pick.", citations: [], timestamp: "t" },
  ];
  const r = selectFindings(profile(), report, ans);
  assert.equal(r.ok, false);
});

// The gate filters PER competitor: a competitor the client out-appears (Monarch,
// tied 1–1) is skipped, but the hero still forms on one the client truly loses to
// (YNAB, 2 vs 1). companyAppears is competitor-independent, so only the
// competitor's own visibility decides.
test("hero forms on a competitor the client truly loses to, skipping a tied one", () => {
  const p = profile();
  p.competitors = [
    { name: "YNAB", aliases: [], confirmed: true },
    { name: "Monarch Money", aliases: ["Monarch"], confirmed: true },
  ];
  const report = baseReport({
    competitors: ["YNAB", "Monarch Money"],
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "perplexity", competitor: "Monarch Money" },
      { query_id: "q2", intent: "category", engine_name: "openai", competitor: "YNAB" },
      { query_id: "q3", intent: "category", engine_name: "openai", competitor: "YNAB" },
    ],
  });
  const ans: AnswerRecord[] = [
    // Acme's ONLY appearance is q1, alongside Monarch -> company 1, Monarch 1 (tied → skipped)
    { query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "perplexity", run_index: 0, response: "Acme edges out Monarch.", citations: [], timestamp: "t" },
    // YNAB present, Acme absent in q2 & q3 -> YNAB 2 > company 1 (honest)
    { query_id: "q2", intent: "category", prompt: "top budgeting app?", engine_name: "openai", run_index: 0, response: "YNAB is the top pick.", citations: [], timestamp: "t" },
    { query_id: "q3", intent: "category", prompt: "best app to budget?", engine_name: "openai", run_index: 0, response: "Most people pick YNAB.", citations: [], timestamp: "t" },
  ];
  const r = selectFindings(p, report, ans);
  assert.equal(r.ok, true);
  if (!r.ok) return;
  assert.equal(r.lead.competitor, "YNAB");
  assert.notEqual(r.lead.queryId, "q1");
});

// Proof-foregrounding gate: the hero's proof card shows only the leading prose,
// so the lead competitor must appear THERE. q1 outscores q2 (category+perplexity
// vs comparison+openai) but its shown answer foregrounds an untracked brand
// (Monarch) with YNAB only in a trailing table — so the hero must fall to q2,
// whose answer actually leads with YNAB.
test("hero skips a higher-scoring cell whose shown answer foregrounds an untracked brand", () => {
  const report = baseReport({
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "perplexity", competitor: "YNAB" },
      { query_id: "q2", intent: "comparison", engine_name: "openai", competitor: "YNAB" },
    ],
  });
  const ans: AnswerRecord[] = [
    // YNAB present only AFTER the table pipe -> counts for honesty, NOT shown in the proof snippet.
    { query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "perplexity", run_index: 0, response: "Monarch is the best budgeting app for most people. | App | Pick |\n| YNAB | yes |", citations: [], timestamp: "t" },
    // YNAB leads the prose -> shown.
    { query_id: "q2", intent: "comparison", prompt: "alternatives to Monarch?", engine_name: "openai", run_index: 0, response: "YNAB is the top pick here.", citations: [], timestamp: "t" },
  ];
  const r = selectFindings(profile(), report, ans);
  assert.equal(r.ok, true);
  if (!r.ok) return;
  assert.equal(r.lead.queryId, "q2");
});

test("refuses when NO losing query foregrounds the competitor in the shown answer", () => {
  const report = baseReport({
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "perplexity", competitor: "YNAB" },
    ],
  });
  const ans: AnswerRecord[] = [
    // YNAB is honest (appears, client doesn't) but only inside the trailing table — never in the snippet.
    { query_id: "q1", intent: "category", prompt: "best budgeting app?", engine_name: "perplexity", run_index: 0, response: "Monarch leads for most budgeters. | App | Rank |\n| YNAB | 2 |", citations: [], timestamp: "t" },
  ];
  const r = selectFindings(profile(), report, ans);
  assert.equal(r.ok, false);
  if (r.ok) return;
  assert.match(r.reason, /provable hero/);
});

function siteAudit(
  roadmap: SiteAuditPayload["roadmap"],
  present = true,
  checks: SiteAuditPayload["checks"] = [],
): SiteAuditPayload {
  return {
    present,
    domain: "acme.io",
    pages_crawled: 3,
    checks,
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

// B: when our own crawl probe was edge-blocked, the phase-1 technical-access gaps
// reflect our client being blocked (not the prospect's policy) and must not be
// printed as the prospect's failings. Content/offsite gaps survive.
const ROADMAP_MIX: SiteAuditPayload["roadmap"] = [
  { category: "technical_accessibility", check_name: "robots.txt allows AI crawlers", status: "fail", impact_label: "High", effort: "low", phase: 1 },
  { category: "technical_accessibility", check_name: "content reachable, not gated", status: "fail", impact_label: "High", effort: "low", phase: 1 },
  { category: "content_substance", check_name: "on-site comparison content", status: "fail", impact_label: "Medium", effort: "medium", phase: 2 },
];
const BLOCKED_CHECKS: SiteAuditPayload["checks"] = [
  { check_key: "crawler_access", category: 1, page_url: "/", status: "fail", detail: "Homepage didn't return 200 for a normal browser; can't assess crawler access." },
  { check_key: "gated_content", category: 1, page_url: "/", status: "fail", detail: "Homepage is gated for GPTBot: / (HTTP 403)." },
];

test("selectWhyGaps drops technical-access gaps when our crawl probe was edge-blocked", () => {
  const gaps = selectWhyGaps(siteAudit(ROADMAP_MIX, true, BLOCKED_CHECKS), 3);
  assert.deepEqual(gaps.map((g) => g.label), ["on-site comparison content"]);
  assert.ok(!gaps.some((g) => /robots|gated|reachable/.test(g.label)), "no access falsehoods survive");
});

test("selectWhyGaps keeps technical-access gaps when the crawl reached the site", () => {
  const reached: SiteAuditPayload["checks"] = [
    { check_key: "crawler_access", category: 1, page_url: "/", status: "pass", detail: "All probed AI crawler UAs reach the site." },
    { check_key: "robots_txt", category: 1, page_url: "/", status: "fail", detail: "All tracked AI crawlers are blocked in robots.txt." },
  ];
  const gaps = selectWhyGaps(siteAudit(ROADMAP_MIX, true, reached), 3);
  assert.ok(gaps.some((g) => g.label === "robots.txt allows AI crawlers"), "a genuine, confirmed block still shows");
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
