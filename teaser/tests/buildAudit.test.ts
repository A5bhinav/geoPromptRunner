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
      { bucket: "category", mention_rate: 0.1, citation_rate: 0.0, answered_cells: 6, total_cells: 6 },
      { bucket: "comparison", mention_rate: 0.0, citation_rate: null, answered_cells: 3, total_cells: 3 },
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
  assert.equal(d.achievableGrade, "B"); // D -> B default target (two bands up, capped at A-)
  assert.match(d.headline, /best budgeting app/);
  assert.match(d.headline, /Acme shows up in/);
  assert.equal(d.headlineNumber.competitorName, "Monarch Money");
  // The brand query (q4, the only one naming Acme) is EXCLUDED from the headline
  // denominator (S3) — it names the client by construction, so counting it would
  // inflate the number. That leaves 3 winnable queries, Acme in none of them.
  assert.equal(d.headlineNumber.clientAppears, 0);
  assert.equal(d.headlineNumber.competitorAppears, 3);
  assert.equal(d.headlineNumber.n, 3);

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

// A prompt-carrying answer builder for the multi-competitor / gating tests — the
// bugs below only surface with real prompts (A-vs-B detection) and >=2 rivals.
function mkA(
  qid: string,
  intent: AnswerRecord["intent"],
  engine: string,
  resp: string,
  prompt: string,
  run = 0,
): AnswerRecord {
  return {
    query_id: qid,
    intent,
    prompt,
    engine_name: engine,
    run_index: run,
    response: resp,
    citations: [],
    timestamp: "t",
  };
}

// T1: the paid §3 evidence must inherit the teaser's gates — an A-vs-B head-to-head
// and a brand query can't become evidence cards; a legit category loss still does.
test("evidence excludes A-vs-B and brand rows, keeps a real category loss (T1)", () => {
  const report = baseReport({
    losing_queries: [
      { query_id: "c1", intent: "category", engine_name: "perplexity", competitor: "Monarch Money" },
      { query_id: "avb", intent: "comparison", engine_name: "openai", competitor: "YNAB" },
      { query_id: "b1", intent: "brand", engine_name: "perplexity", competitor: "Monarch Money" },
    ],
    site_audit: null,
  });
  const ans = [
    mkA("c1", "category", "perplexity", "Monarch Money is the best budgeting app.", "best budgeting app?"),
    mkA("avb", "comparison", "openai", "Between them, YNAB edges out Monarch Money.", "YNAB vs Monarch Money — which is better?"),
    mkA("b1", "brand", "perplexity", "Acme is decent but Monarch Money is better.", "is Acme any good?"),
  ];
  const d = buildAudit("run-t1", "budgeting app", report, ans);
  const qids = d.evidence.flatMap((g) => g.findings.map((f) => f.queryId));
  assert.ok(qids.includes("c1"), "a real category loss is evidence");
  assert.ok(!qids.includes("avb"), "the A-vs-B head-to-head is excluded");
  assert.ok(!qids.includes("b1"), "the brand query is excluded");
});

// T2: honest-hero picks the count-based rival, and the verdict's % is derived from
// that same count — never mention_rate_top_competitor (a possibly-different brand).
test("multi-competitor verdict names the honest-hero rival with a consistent % (T2)", () => {
  const report = baseReport({
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "perplexity", competitor: "YNAB" },
      { query_id: "q2", intent: "category", engine_name: "openai", competitor: "YNAB" },
      { query_id: "q3", intent: "comparison", engine_name: "perplexity", competitor: "Monarch Money" },
    ],
    site_audit: null,
  });
  const ans = [
    mkA("q1", "category", "perplexity", "YNAB is the best budgeting app.", "best budgeting app?"),
    mkA("q2", "category", "openai", "Most people pick YNAB.", "top budgeting app?"),
    mkA("q3", "comparison", "perplexity", "Monarch Money is a solid alternative.", "alternatives to Mint?"),
  ];
  const d = buildAudit("run-t2", "budgeting app", report, ans);
  // YNAB out-appears the client the most (2), NOT the share-based top_competitor
  // "Monarch Money" (1) → honest-hero names YNAB.
  assert.equal(d.headlineNumber.competitorName, "YNAB");
  assert.equal(d.headlineNumber.competitorAppears, 2);
  assert.equal(d.headlineNumber.n, 3);
  // Verdict % comes from the same count (2/3 = 67%), so brand and number agree.
  assert.match(d.verdictSentence, /YNAB in 67%/);
  assert.ok(!d.verdictSentence.includes("Monarch"), "no share-based brand leaks into the verdict");
});

// T4: the audit must quote a run that reproduces the loss, not run_index 0 blindly.
test("evidence quotes a run that reproduces the loss, not run 0 (T4)", () => {
  const report = baseReport({
    competitors: ["Monarch Money"],
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "perplexity", competitor: "Monarch Money" },
    ],
    site_audit: null,
  });
  const ans = [
    // run 0: competitor NOT foregrounded → doesn't back the claim.
    mkA("q1", "category", "perplexity", "The best budgeting apps vary by need.", "best budgeting app?", 0),
    // run 1: client absent, Monarch present → the reproducing loss; must be quoted.
    mkA("q1", "category", "perplexity", "Monarch Money is the top pick.", "best budgeting app?", 1),
  ];
  const d = buildAudit("run-t4", "budgeting app", report, ans);
  const f = d.evidence.flatMap((g) => g.findings).find((x) => x.queryId === "q1");
  assert.ok(f, "the category loss is present");
  assert.match(f!.verbatimAnswer, /top pick/, "quotes run 1 (reproduces), not run 0");
});

// T7: competitor aliases, when supplied, thread into the audit's matchers.
test("competitor aliases thread into the audit matchers (T7)", () => {
  const report = baseReport({
    competitors: ["Monarch Money"],
    losing_queries: [
      { query_id: "q1", intent: "category", engine_name: "perplexity", competitor: "Monarch Money" },
    ],
    site_audit: null,
  });
  // The answer names the rival only by its alias "Monarch".
  const ans = [mkA("q1", "category", "perplexity", "Monarch is the top pick.", "best budgeting app?")];
  const withAlias = buildAudit("r", "budgeting app", report, ans, {
    competitorAliases: { "Monarch Money": ["Monarch"] },
  });
  assert.equal(withAlias.headlineNumber.competitorName, "Monarch Money");
  assert.equal(withAlias.headlineNumber.competitorAppears, 1);
  // Without the alias the bare-name matcher misses "Monarch" → nobody out-appears
  // the client → honest-hero drops the competitor name.
  const without = buildAudit("r", "budgeting app", report, ans);
  assert.equal(without.headlineNumber.competitorName, "");
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
