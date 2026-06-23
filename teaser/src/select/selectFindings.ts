/**
 * Lead-finding selection — ranks the platform's losing_queries to pick the hero
 * finding + 2 pattern-table rows, and computes the headline number.
 *
 * Rule (BUILD_PLAN.md §7 #8): the highest-intent losing cell (comparison >
 * category > ...), on the most credible engine, with a named competitor. The
 * pattern table is the next 2 DISTINCT queries (so it's clearly not cherry-picked).
 *
 * Deterministic and pure — no clocks, no randomness. This is teaserAuto's IP.
 */

import type {
  CompanyProfile,
  Finding,
  HeadlineNumber,
} from "../types/domain.ts";
import type {
  AnswerRecord,
  IntentBucket,
  LosingRow,
  ReportPayload,
} from "../types/platform.ts";
import { buildMatcher } from "./entity.ts";

/** Higher = more commercially valuable / more visceral in a teaser. */
const INTENT_PRIORITY: Record<IntentBucket, number> = {
  comparison: 5,
  category: 4,
  problem_aware: 3,
  adjacent_authority: 2,
  brand: 1,
};

/** Engine credibility for hero selection + scoring (BUILD_PLAN.md §4d). */
const ENGINE_CREDIBILITY: Record<string, number> = {
  perplexity: 5,
  ai_overviews: 5,
  google_ai_overviews: 5,
  openai: 3,
  openai_search: 4,
  gemini: 2,
  gemini_grounded: 3,
  anthropic: 2,
  anthropic_search: 3,
};

function engineScore(engine: string): number {
  return ENGINE_CREDIBILITY[engine] ?? 1;
}

function scoreRow(row: LosingRow): number {
  return INTENT_PRIORITY[row.intent] * 10 + engineScore(row.engine_name);
}

export type SelectionResult =
  | { ok: true; lead: Finding; table: Finding[]; headline: HeadlineNumber; heroEngine: string }
  | { ok: false; reason: string };

function findAnswer(
  answers: AnswerRecord[],
  queryId: string,
  engineName: string,
): AnswerRecord | undefined {
  // Prefer run_index 0; fall back to any run that actually returned a response.
  const cell = answers.filter((a) => a.query_id === queryId && a.engine_name === engineName);
  return cell.find((a) => a.run_index === 0 && a.response) ?? cell.find((a) => a.response);
}

function toFinding(
  row: LosingRow,
  role: "lead" | "table",
  answers: AnswerRecord[],
): Finding | null {
  const answer = findAnswer(answers, row.query_id, row.engine_name);
  if (!answer || !answer.response) return null;
  return {
    role,
    source: "losing_query",
    queryId: row.query_id,
    intent: row.intent,
    engineName: row.engine_name,
    competitor: row.competitor,
    verbatimQuery: answer.prompt,
    verbatimAnswer: answer.response,
    citations: answer.citations,
    rankScore: scoreRow(row),
  };
}

function computeHeadline(
  profile: CompanyProfile,
  report: ReportPayload,
  answers: AnswerRecord[],
  competitorName: string,
): HeadlineNumber {
  const clientMatch = buildMatcher(
    profile.name,
    profile.competitors.flatMap(() => []), // client aliases would go here
  );
  const competitor = report.competitors.find((c) => c === competitorName) ?? competitorName;
  const competitorMatch = buildMatcher(competitor);

  const byQuery = new Map<string, { client: boolean; competitor: boolean }>();
  for (const a of answers) {
    if (!a.response) continue;
    const entry = byQuery.get(a.query_id) ?? { client: false, competitor: false };
    if (clientMatch(a.response)) entry.client = true;
    if (competitorMatch(a.response)) entry.competitor = true;
    byQuery.set(a.query_id, entry);
  }

  let companyAppears = 0;
  let competitorAppears = 0;
  for (const v of byQuery.values()) {
    if (v.client) companyAppears++;
    if (v.competitor) competitorAppears++;
  }
  return {
    companyAppears,
    competitorAppears,
    competitorName: competitor,
    n: byQuery.size,
  };
}

export function selectFindings(
  profile: CompanyProfile,
  report: ReportPayload,
  answers: AnswerRecord[],
): SelectionResult {
  if (report.detection !== "judge") {
    return {
      ok: false,
      reason: `detection mode is "${report.detection}" — needs the judge for a printable finding`,
    };
  }
  if (report.losing_queries.length === 0) {
    return { ok: false, reason: "no losing queries — the client is not being left out" };
  }

  const ranked = [...report.losing_queries].sort((a, b) => scoreRow(b) - scoreRow(a));

  // Hero engine = the most credible engine that actually appears in a losing cell.
  const heroEngine = ranked
    .map((r) => r.engine_name)
    .sort((a, b) => engineScore(b) - engineScore(a))[0]!;

  // Lead: top-ranked losing cell, preferring the hero engine.
  const leadRow =
    ranked.find((r) => r.engine_name === heroEngine) ?? ranked[0]!;
  const lead = toFinding(leadRow, "lead", answers);
  if (!lead) {
    return { ok: false, reason: "could not join the lead finding to a verbatim answer" };
  }

  // Table: next 2 DISTINCT queries (not the lead's query), best-scored each.
  const seen = new Set<string>([leadRow.query_id]);
  const table: Finding[] = [];
  for (const row of ranked) {
    if (table.length >= 2) break;
    if (seen.has(row.query_id)) continue;
    const f = toFinding(row, "table", answers);
    if (!f) continue;
    seen.add(row.query_id);
    table.push(f);
  }

  const headline = computeHeadline(profile, report, answers, leadRow.competitor);

  return { ok: true, lead, table, headline, heroEngine };
}
