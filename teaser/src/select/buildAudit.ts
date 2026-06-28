/**
 * buildAudit — assembles a completed run's ReportPayload + verbatim answers into
 * a reviewable AuditDraft (the paid AI Visibility Audit). See docs/auditGenerator.md
 * §8. Deterministic and pure (no clocks, no randomness, no I/O) — this is the
 * generator's IP and is unit-tested per section.
 *
 * Honesty rule (carried from the teaser): every claim traces to data. Nothing is
 * measured here; sections degrade cleanly when their inputs are absent.
 */

import type {
  AuditDraft,
  AuditGrade,
  AuditHeadlineNumber,
  DiagnosisCategory,
  EvidenceGroup,
  RoadmapPhase,
} from "../types/audit.ts";
import type { Finding } from "../types/domain.ts";
import type {
  AnswerRecord,
  IntentBucket,
  LosingRow,
  ReportPayload,
  RoadmapRow,
  SiteCheckRow,
} from "../types/platform.ts";
import { buildMatcher } from "./entity.ts";

// --- ranking constants (mirror selectFindings: engine credibility × intent) ---

const INTENT_PRIORITY: Record<IntentBucket, number> = {
  comparison: 5,
  category: 4,
  problem_aware: 3,
  adjacent_authority: 2,
  brand: 1,
};

const ENGINE_CREDIBILITY: Record<string, number> = {
  perplexity: 5,
  ai_overviews: 5,
  google_ai_overviews: 5,
  openai_search: 4,
  openai: 3,
  gemini_grounded: 3,
  anthropic_search: 3,
  gemini: 2,
  anthropic: 2,
};

function engineScore(engine: string): number {
  return ENGINE_CREDIBILITY[engine] ?? 1;
}

function scoreRow(row: LosingRow): number {
  return (INTENT_PRIORITY[row.intent] ?? 0) * 10 + engineScore(row.engine_name);
}

const SEVERITY_RANK: Record<string, number> = { high: 3, med: 2, low: 1 };
const STATUS_RANK: Record<string, number> = { fail: 3, partial: 2, pass: 1, ungradeable: 0 };
const IMPACT_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

/**
 * Journey-stage order for the evidence section (§3): a buyer moves
 * problem-aware → category → comparison → brand. We surface losses in that order
 * so the audit reads as a pattern across the funnel, not cherry-picking.
 */
const EVIDENCE_BUCKET_ORDER: IntentBucket[] = [
  "problem_aware",
  "category",
  "comparison",
  "brand",
  "adjacent_authority",
];

export interface BuildAuditOptions {
  /** Evidence proof cards per journey-stage bucket (§3). Default 2 (doc §15.4: K=2–3). */
  evidencePerBucket?: number;
}

// --- §1 grade trajectory --------------------------------------------------------

/**
 * A default "achievable in 90 days" target letter — a GOAL the analyst confirms,
 * never a measured score (doc §1 / §15.7). Conservative: one or two bands up,
 * capped at A-, framed as a target at render time.
 */
function defaultAchievableGrade(letter: string | null): string | null {
  if (!letter) return null;
  const base = letter.charAt(0).toUpperCase();
  const map: Record<string, string> = { F: "B", D: "B+", C: "A-", B: "A", A: "A" };
  return map[base] ?? null;
}

function pctOf(fraction: number | null | undefined): number {
  return Math.round(Math.max(0, Math.min(1, fraction ?? 0)) * 100);
}

// --- §1/§2 headline number (appears in X of N), computed from verbatim answers --

function computeHeadline(
  report: ReportPayload,
  answers: AnswerRecord[],
): AuditHeadlineNumber {
  const competitorName = report.scorecard.top_competitor ?? report.competitors[0] ?? "";
  const clientMatch = buildMatcher(report.client_name);
  const competitorMatch = competitorName ? buildMatcher(competitorName) : () => false;

  const byQuery = new Map<string, { client: boolean; competitor: boolean }>();
  for (const a of answers) {
    if (!a.response) continue;
    const entry = byQuery.get(a.query_id) ?? { client: false, competitor: false };
    if (clientMatch(a.response)) entry.client = true;
    if (competitorMatch(a.response)) entry.competitor = true;
    byQuery.set(a.query_id, entry);
  }
  let clientAppears = 0;
  let competitorAppears = 0;
  for (const v of byQuery.values()) {
    if (v.client) clientAppears++;
    if (v.competitor) competitorAppears++;
  }
  return { clientAppears, competitorAppears, competitorName, n: byQuery.size };
}

// --- §3 evidence ----------------------------------------------------------------

function findAnswer(
  answers: AnswerRecord[],
  queryId: string,
  engineName: string,
): AnswerRecord | undefined {
  const cell = answers.filter((a) => a.query_id === queryId && a.engine_name === engineName);
  return cell.find((a) => a.run_index === 0 && a.response) ?? cell.find((a) => a.response);
}

function toFinding(row: LosingRow, answers: AnswerRecord[]): Finding | null {
  const answer = findAnswer(answers, row.query_id, row.engine_name);
  if (!answer || !answer.response) return null;
  return {
    role: "lead",
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

function buildEvidence(
  report: ReportPayload,
  answers: AnswerRecord[],
  perBucket: number,
): EvidenceGroup[] {
  const named = report.losing_queries.filter((r) => r.competitor.trim() !== "");
  const groups: EvidenceGroup[] = [];
  for (const bucket of EVIDENCE_BUCKET_ORDER) {
    const rows = named
      .filter((r) => r.intent === bucket)
      .sort((a, b) => scoreRow(b) - scoreRow(a));
    const findings: Finding[] = [];
    const seenQueries = new Set<string>();
    for (const row of rows) {
      if (findings.length >= perBucket) break;
      if (seenQueries.has(row.query_id)) continue; // one card per query within a bucket
      const f = toFinding(row, answers);
      if (!f) continue;
      seenQueries.add(row.query_id);
      findings.push(f);
    }
    if (findings.length) groups.push({ bucket, findings });
  }
  return groups;
}

// --- §6 diagnosis ---------------------------------------------------------------

function rollUpVerdict(checks: SiteCheckRow[]): "pass" | "partial" | "fail" {
  let worst = 0;
  for (const c of checks) worst = Math.max(worst, STATUS_RANK[c.status] ?? 0);
  return worst >= 3 ? "fail" : worst === 2 ? "partial" : "pass";
}

function buildDiagnosis(checks: SiteCheckRow[]): DiagnosisCategory[] {
  const byCategory = new Map<number, SiteCheckRow[]>();
  for (const c of checks) {
    const list = byCategory.get(c.category) ?? [];
    list.push(c);
    byCategory.set(c.category, list);
  }
  return [...byCategory.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([category, rows]) => ({
      category,
      verdict: rollUpVerdict(rows),
      checks: [...rows].sort(
        (a, b) => (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0),
      ),
    }));
}

// --- §7 roadmap -----------------------------------------------------------------

function buildRoadmap(roadmap: RoadmapRow[]): RoadmapPhase[] {
  const byPhase = new Map<number, RoadmapRow[]>();
  for (const r of roadmap) {
    const list = byPhase.get(r.phase) ?? [];
    list.push(r);
    byPhase.set(r.phase, list);
  }
  return [...byPhase.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([phase, rows]) => ({
      phase,
      rows: [...rows].sort(
        (a, b) =>
          (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0) ||
          (IMPACT_RANK[(b.impact_label ?? "").toLowerCase()] ?? 0) -
            (IMPACT_RANK[(a.impact_label ?? "").toLowerCase()] ?? 0),
      ),
    }));
}

// --- §1 copy (deterministic templating; analyst-editable) -----------------------

function verdictLine(report: ReportPayload, h: AuditHeadlineNumber): string {
  const clientPct = pctOf(report.scorecard.mention_rate_client);
  const compPct = pctOf(report.scorecard.mention_rate_top_competitor);
  if (h.competitorName) {
    return (
      `${report.client_name} is recommended in ${clientPct}% of buyer queries; ` +
      `${h.competitorName} in ${compPct}%. The gap is the visibility you're losing at the moment buyers decide.`
    );
  }
  return `${report.client_name} is recommended in ${clientPct}% of buyer queries.`;
}

// --- §8 engagement scaffolding (analyst edits these; no fabricated numbers) ------

function engagementScaffold(report: ReportPayload, h: AuditHeadlineNumber): {
  projectedImpact: string;
  nextSteps: string;
} {
  const gap = Math.max(0, h.n - h.clientAppears);
  return {
    projectedImpact:
      `Closing the Phase 1–2 gaps typically moves a brand from "absent" to "in the consideration set" ` +
      `on the high-intent queries first — here that's the ${gap} buyer ${gap === 1 ? "query" : "queries"} ` +
      `where ${report.client_name} is currently left out. [Analyst: set a concrete 90-day target.]`,
    nextSteps:
      `Recommended engagement: implement the roadmap in phase order (accessibility → content → schema → off-site), ` +
      `then re-audit in 90 days to measure the visibility lift. [Analyst: tailor scope + retainer.]`,
  };
}

// --- top-level assembly ---------------------------------------------------------

export function buildAudit(
  runId: string,
  category: string,
  report: ReportPayload,
  answers: AnswerRecord[],
  opts: BuildAuditOptions = {},
): AuditDraft {
  const perBucket = opts.evidencePerBucket ?? 2;
  const site = report.site_audit;
  const sitePresent = Boolean(site && site.present);

  const gp = report.scorecard.visibility_grade;
  const grade: AuditGrade | null = gp
    ? {
        letter: gp.letter,
        score: gp.score,
        rationale: gp.rationale,
        accuracyPenalty: gp.accuracy_penalty,
        nFlags: gp.n_flags,
      }
    : null;

  const headlineNumber = computeHeadline(report, answers);

  const accuracyFlags = [...report.accuracy_flags].sort(
    (a, b) => (SEVERITY_RANK[b.severity] ?? 0) - (SEVERITY_RANK[a.severity] ?? 0),
  );

  // §1 copy uses the real category label (passed in; the report lacks one).
  const headline = headlineLineWithCategory(report, headlineNumber, category);
  const verdictSentence = verdictLine(report, headlineNumber);

  return {
    runId,
    clientName: report.client_name,
    clientDomains: report.client_domains,
    category,
    runDate: report.run_date,
    engines: report.engines,

    grade,
    achievableGrade: defaultAchievableGrade(grade?.letter ?? null),
    headline,
    verdictSentence,
    headlineNumber,

    leaderboard: report.leaderboard,
    byBucket: report.by_bucket,
    shareOfVoiceClient: report.scorecard.share_of_model_client,
    topCompetitor: report.scorecard.top_competitor,
    topCompetitorShare: report.scorecard.top_competitor_share,

    evidence: buildEvidence(report, answers, perBucket),

    accuracy: {
      assessed: report.scorecard.accuracy_assessed,
      flags: report.scorecard.accuracy_assessed ? accuracyFlags : [],
      penalty: grade?.accuracyPenalty ?? 0,
    },

    competitiveGap: {
      offsite: site?.offsite ?? [],
      citedSources: [...report.sources].sort((a, b) => b.count - a.count).slice(0, 8),
    },

    diagnosis: {
      present: sitePresent,
      categories: sitePresent ? buildDiagnosis(site!.checks) : [],
      pagesCrawled: site?.pages_crawled ?? 0,
      errors: site?.errors ?? 0,
    },

    roadmap: {
      present: sitePresent && Boolean(site!.roadmap?.length),
      phases: sitePresent ? buildRoadmap(site!.roadmap) : [],
    },

    engagement: engagementScaffold(report, headlineNumber),

    status: "draft",
    report,
    answers,
  };
}

/** §1 headline with the real category label (the report carries none). */
function headlineLineWithCategory(
  report: ReportPayload,
  h: AuditHeadlineNumber,
  category: string,
): string {
  const cat = category && category.trim() ? category.trim() : "option in your category";
  if (h.competitorName) {
    return (
      `When buyers ask AI for the best ${cat}, ${report.client_name} shows up in ` +
      `${h.clientAppears} of ${h.n} answers — ${h.competitorName} shows up in ${h.competitorAppears}.`
    );
  }
  return `${report.client_name} shows up in ${h.clientAppears} of ${h.n} high-intent buyer queries.`;
}
