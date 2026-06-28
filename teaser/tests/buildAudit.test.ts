import assert from "node:assert/strict";
import { test } from "node:test";
import { buildAudit } from "../src/select/buildAudit.ts";
import type { AnswerRecord, ReportPayload, SiteAuditPayload } from "../src/types/platform.ts";

function siteAudit(): SiteAuditPayload {
  return {
    present: true,
    domain: "acme.com",
    pages_crawled: 7,
    checks: [
      { check_key: "robots_txt", category: 1, page_url: "acme.com", status: "fail", detail: "GPTBot blocked" },
      { check_key: "llms_txt", category: 1, page_url: "acme.com", status: "pass", detail: "present" },
      { check_key: "answer_first_lead", category: 3, page_url: "acme.com/p", status: "partial", detail: "no lead" },
      { check_key: "schema_valid", category: 5, page_url: "acme.com", status: "fail", detail: "no Organization schema" },
    ],
    summary: {},
    errors: 1,
    offsite: [
      { finding_type: "reddit", title: "No Reddit presence found", url: null, confidence: "high" },
      { finding_type: "trustpilot", title: "No Trustpilot profile", url: null, confidence: "medium" },
    ],
    roadmap: [
      { category: "Technical accessibility", check_name: "Unblock GPTBot", status: "fail", impact_label: "High", effort: "low", phase: 1 },
      { category: "Structured data", check_name: "Add Organization schema", status: "fail", impact_label: "Medium", effort: "low", phase: 3 },
      { category: "Content structure", check_name: "Add answer-first leads", status: "partial", impact_label: "Medium", effort: "medium", phase: 2 },
    ],
  };
}

function baseReport(over: Partial<ReportPayload> = {}): ReportPayload {
  return {
    client_name: "Acme",
    run_date: "2026-06-24",
    query_set_version: "v1",
    runs_per_query: 3,
    engines: ["perplexity", "openai"],
    competitors: ["Monarch Money", "YNAB"],
    client_domains: ["acme.com"],
    detection: "judge",
    scorecard: {
      visibility_grade: {
        letter: "D",
        score: 0.2,
        raw_score: 0.35,
        accuracy_penalty: 0.15,
        n_flags: 2,
        rationale: "Absent on high-intent queries; two accuracy errors.",
      },
      share_of_model_client: 0.12,
      top_competitor: "Monarch Money",
      top_competitor_share: 0.5,
      mention_rate_client: 0.2,
      mention_rate_top_competitor: 0.8,
      citation_rate_client: 0.0,
      accuracy_assessed: true,
      accuracy_flag_count: 2,
    },
    leaderboard: [
      { brand: "Monarch Money", is_client: false, visibility: 0.9, mention_rate: 0.8, share_of_model: 0.5 },
      { brand: "Acme", is_client: true, visibility: 0.2, mention_rate: 0.2, share_of_model: 0.12 },
    ],
    by_bucket: [
      { bucket: "category", mention_rate: 0.1, citation_rate: 0.0 },
      { bucket: "comparison", mention_rate: 0.0, citation_rate: null },
    ],
    accuracy_flags: [
      { type: "stale", severity: "low", claim: "Acme is iOS-only", reality: "Android shipped 2026" },
      { type: "wrong_pricing", severity: "high", claim: "Acme costs $20/mo", reality: "Acme is free; $8/mo pro" },
    ],
    sources: [
      { domain: "reddit.com", count: 9 },
      { domain: "nerdwallet.com", count: 4 },
    ],
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "perplexity", competitor: "Monarch Money" },
      { query_id: "q2", intent: "comparison", engine_name: "openai", competitor: "Monarch Money" },
      { query_id: "q3", intent: "problem_aware", engine_name: "perplexity", competitor: "Monarch Money" },
    ],
    site_audit: siteAudit(),
    ...over,
  };
}

function answers(): AnswerRecord[] {
  const mk = (qid: string, intent: AnswerRecord["intent"], engine: string, resp: string): AnswerRecord => ({
    query_id: qid,
    intent,
    prompt: `query ${qid}`,
    engine_name: engine,
    run_index: 0,
    response: resp,
    citations: ["https://reddit.com/x"],
    timestamp: "2026-06-24T00:00:00Z",
  });
  return [
    mk("q1", "category", "perplexity", "The best budgeting app is Monarch Money."),
    mk("q2", "comparison", "openai", "Monarch Money beats the alternatives."),
    mk("q3", "problem_aware", "perplexity", "Try Monarch Money to manage money."),
    mk("q4", "brand", "perplexity", "Acme is a solid budgeting app."),
  ];
}

test("buildAudit assembles all sections from a full judge run", () => {
  const d = buildAudit("run-123", "budgeting app", baseReport(), answers());

  // §1 grade + gap-led headline
  assert.equal(d.runId, "run-123");
  assert.equal(d.grade?.letter, "D");
  assert.equal(d.achievableGrade, "B+"); // D -> B+ default target
  assert.match(d.headline, /best budgeting app/);
  assert.match(d.headline, /Acme shows up in/);
  assert.equal(d.headlineNumber.competitorName, "Monarch Money");
  assert.equal(d.headlineNumber.clientAppears, 1); // only the brand query mentions Acme
  assert.equal(d.headlineNumber.competitorAppears, 3);
  assert.equal(d.headlineNumber.n, 4);

  // §3 evidence grouped by journey order (problem_aware before category before comparison)
  assert.deepEqual(d.evidence.map((g) => g.bucket), ["problem_aware", "category", "comparison"]);
  assert.match(d.evidence[0]?.findings[0]?.verbatimAnswer ?? "", /Monarch Money/);

  // §4 accuracy sorted high -> low
  assert.equal(d.accuracy.assessed, true);
  assert.deepEqual(d.accuracy.flags.map((f) => f.severity), ["high", "low"]);

  // §5 competitive gap
  assert.equal(d.competitiveGap.offsite.length, 2);
  assert.equal(d.competitiveGap.citedSources[0]?.domain, "reddit.com");

  // §6 diagnosis grouped by category with rolled-up verdicts
  assert.equal(d.diagnosis.present, true);
  const cat1 = d.diagnosis.categories.find((c) => c.category === 1);
  assert.equal(cat1?.verdict, "fail"); // robots fail dominates llms pass
  assert.equal(d.diagnosis.categories.find((c) => c.category === 5)?.verdict, "fail");

  // §7 roadmap grouped + ordered by phase
  assert.deepEqual(d.roadmap.phases.map((p) => p.phase), [1, 2, 3]);
});

test("buildAudit degrades cleanly when accuracy + site audit are absent", () => {
  const report = baseReport({
    accuracy_flags: [],
    site_audit: null,
    scorecard: { ...baseReport().scorecard, accuracy_assessed: false },
  });
  const d = buildAudit("run-x", "budgeting app", report, answers());
  assert.equal(d.accuracy.assessed, false);
  assert.deepEqual(d.accuracy.flags, []);
  assert.equal(d.diagnosis.present, false);
  assert.deepEqual(d.diagnosis.categories, []);
  assert.equal(d.roadmap.present, false);
  assert.deepEqual(d.roadmap.phases, []);
  assert.equal(d.competitiveGap.offsite.length, 0);
  // evidence still works (it comes from losing_queries + answers, not the site audit)
  assert.ok(d.evidence.length > 0);
});
