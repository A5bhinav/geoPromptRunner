/**
 * Lead-finding selection — ranks the platform's losing_queries to pick the hero
 * finding + 2 pattern-table rows, and computes the headline number.
 *
 * Lead rule: the most persuasive DEMAND-SIDE loss. A buyer asking for the
 * client's category ("best <category>") or describing its problem — and getting
 * a competitor — is a cleaner, harder-to-dismiss hook than a head-to-head
 * between two rivals the buyer named themselves (where a third brand not
 * appearing is a much higher bar). So the LEAD ranks by `leadScore`
 * (category/problem_aware weighted above comparison), engine credibility breaking
 * ties. The PATTERN TABLE still favors high-commercial-intent comparison rows
 * (`scoreRow`), so the head-to-heads corroborate the lead instead of fronting it.
 * The hero engine follows the lead (its engine), keeping the proof card + headline
 * on one engine; the table is the next 2 DISTINCT queries (not cherry-picked).
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
  SiteAuditPayload,
} from "../types/platform.ts";
import { buildMatcher } from "./entity.ts";

/**
 * Commercial-intent priority — used to rank the PATTERN TABLE rows (comparison
 * is bottom-funnel and the strongest corroboration).
 */
const INTENT_PRIORITY: Record<IntentBucket, number> = {
  comparison: 5,
  category: 4,
  problem_aware: 3,
  adjacent_authority: 2,
  brand: 1,
};

/**
 * LEAD priority — favors demand-side queries where the buyer is open and the
 * client's absence is unambiguous (category > problem_aware), over comparison
 * queries that name rivals (a weaker hook for the hero slot). Comparisons still
 * dominate the table via INTENT_PRIORITY.
 */
const LEAD_INTENT_PRIORITY: Record<IntentBucket, number> = {
  category: 5,
  problem_aware: 4,
  comparison: 3,
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
  // `?? 0` guards against an intent the platform adds that we don't yet weight:
  // without it the lookup is undefined and the whole score becomes NaN, which
  // silently corrupts the sort. Unknown intent ranks last, like unknown engines.
  return (INTENT_PRIORITY[row.intent] ?? 0) * 10 + engineScore(row.engine_name);
}

/** Lead ranking — demand-side intent dominates (×10), engine credibility breaks ties. */
function leadScore(row: LosingRow): number {
  return (LEAD_INTENT_PRIORITY[row.intent] ?? 0) * 10 + engineScore(row.engine_name);
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
  answers: AnswerRecord[],
  competitorName: string,
): HeadlineNumber {
  // The client has no alias source in CompanyProfile today, so match on its name.
  const clientMatch = buildMatcher(profile.name);
  // Feed the competitor's known aliases so an answer that names it only by an
  // alias (e.g. "YNAB" for "You Need A Budget") still counts toward competitorAppears —
  // otherwise the headline understates the gap the teaser exists to show.
  const competitorAliases =
    profile.competitors.find((c) => c.name === competitorName)?.aliases ?? [];
  const competitorMatch = buildMatcher(competitorName, competitorAliases);

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
    competitorName,
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

  // Only rows that name a competitor are printable — the teaser names the rival
  // the client is losing to (BUILD_PLAN.md §7 #8: "with a named competitor").
  const named = report.losing_queries.filter((r) => r.competitor.trim() !== "");
  if (named.length === 0) {
    return { ok: false, reason: "no losing query names a competitor — nothing to print against" };
  }

  // Lead = the highest-leadScore cell that joins to a verbatim answer. Ranking by
  // leadScore puts a demand-side loss (category/problem_aware) in the hero slot;
  // the hero engine follows the lead (NOT the globally-most-credible engine), so
  // the proof card and headline stay on one engine. We skip any top row whose
  // answer can't be joined rather than failing outright.
  const leadRanked = [...named].sort((a, b) => leadScore(b) - leadScore(a));
  let leadRow: LosingRow | null = null;
  let lead: Finding | null = null;
  for (const row of leadRanked) {
    const f = toFinding(row, "lead", answers);
    if (f) {
      leadRow = row;
      lead = f;
      break;
    }
  }
  if (!leadRow || !lead) {
    return { ok: false, reason: "could not join any losing finding to a verbatim answer" };
  }
  const heroEngine = leadRow.engine_name;

  // Table: next 2 DISTINCT queries (not the lead's), ranked by COMMERCIAL intent
  // (scoreRow) so the high-intent comparison rows corroborate the lead.
  const tableRanked = [...named].sort((a, b) => scoreRow(b) - scoreRow(a));
  const seen = new Set<string>([leadRow.query_id]);
  const table: Finding[] = [];
  for (const row of tableRanked) {
    if (table.length >= 2) break;
    if (seen.has(row.query_id)) continue;
    const f = toFinding(row, "table", answers);
    if (!f) continue;
    seen.add(row.query_id);
    table.push(f);
  }

  const headline = computeHeadline(profile, answers, leadRow.competitor);

  return { ok: true, lead, table, headline, heroEngine };
}

/** One "why AI skips you" gap — a fixable on/off-site cause behind the loss. */
export interface WhyGap {
  /** The check name (a positive statement of what good looks like). */
  label: string;
  status: string; // fail | partial
  impact: string; // High | Medium | Low
}

const IMPACT_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };
const STATUS_RANK: Record<string, number> = { fail: 2, partial: 1 };

/**
 * Pick the top fixable gaps behind the visibility loss — the "why AI skips you"
 * block. The site-audit roadmap is already gaps-only (fail/partial); we order by
 * fix phase (technical accessibility first), then fail-before-partial, then
 * impact, and take the top `max`. Returns [] when no site audit ran.
 */
export function selectWhyGaps(
  site: SiteAuditPayload | null | undefined,
  max = 3,
): WhyGap[] {
  if (!site || !site.present || !Array.isArray(site.roadmap) || site.roadmap.length === 0) {
    return [];
  }
  return [...site.roadmap]
    .sort(
      (a, b) =>
        a.phase - b.phase ||
        (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0) ||
        (IMPACT_RANK[(b.impact_label ?? "").toLowerCase()] ?? 0) -
          (IMPACT_RANK[(a.impact_label ?? "").toLowerCase()] ?? 0),
    )
    .slice(0, max)
    .map((r) => ({ label: r.check_name, status: r.status, impact: r.impact_label }));
}
