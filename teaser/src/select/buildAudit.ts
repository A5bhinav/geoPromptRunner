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
import { countReproduction, findAnswer, isUnwinnableQuery } from "./selectFindings.ts";
import { answerSnippet } from "../render/proofCard.ts";

// --- ranking constants (mirror selectFindings: engine credibility × intent) ---

const INTENT_PRIORITY: Record<IntentBucket, number> = {
  comparison: 5,
  category: 4,
  problem_aware: 3,
  adjacent_authority: 2,
  brand: 1,
  // Local mirrors the consumer shape: the query closest to hiring ranks highest.
  local_intent: 5,
  hybrid: 4,
  informational: 3,
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
 * problem-aware → category → comparison. We surface losses in that order so the
 * audit reads as a pattern across the funnel, not cherry-picking. "brand" is
 * intentionally ABSENT (T1): a brand query names the client by construction, so
 * it can't be an honest "client absent, competitor recommended" evidence card.
 */
const EVIDENCE_BUCKET_ORDER: IntentBucket[] = [
  "problem_aware",
  "category",
  "comparison",
  "adjacent_authority",
];

export interface BuildAuditOptions {
  /** Evidence proof cards per journey-stage bucket (§3). Default 2 (doc §15.4: K=2–3). */
  evidencePerBucket?: number;
  /**
   * Client name variants — threaded into the audit's client matcher so an
   * alias-only client mention counts as present (R4/T7). Absent → match on name
   * only (the from-run_id audit path has no alias source today).
   */
  clientAliases?: string[];
  /** Competitor name → aliases, threaded into the competitor matchers (R4/T7). */
  competitorAliases?: Record<string, string[]>;
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
  // At most two bands up and never above A- — a conservative target the analyst
  // confirms, not a promise. (The old map claimed F→B / B→A / A→A, breaking both
  // the "one or two bands" and "capped at A-" limits the doc/comment assert.)
  const map: Record<string, string> = { F: "C", D: "B", C: "B+", B: "A-", A: "A-" };
  return map[base] ?? null;
}

function pctOf(fraction: number | null | undefined): number {
  return Math.round(Math.max(0, Math.min(1, fraction ?? 0)) * 100);
}

// --- §1/§2 headline number (appears in X of N), computed from verbatim answers --

interface QueryAnalysis {
  /** Brand + A-vs-B query ids — excluded from the denominator AND the evidence. */
  excluded: Set<string>;
  /** Winnable queries where the client is present. */
  clientAppears: number;
  /** competitor name → winnable queries where it is present. */
  compCount: Map<string, number>;
  /** Winnable query count (the "of N" denominator). */
  n: number;
}

/**
 * Score the winnable demand-side set ONCE (S1/S2/S3, parity with the teaser):
 * brand queries name the client and A-vs-B head-to-heads never had the client as
 * a candidate, so both are excluded from the denominator AND from evidence. The
 * result feeds computeHeadline (honest-hero) and buildEvidence (gate) from one
 * source, so the §1 number and the §3 cards can never disagree about which
 * queries count. Matchers are alias-aware (passed in) — R4/T7.
 */
function analyzeQueries(
  report: ReportPayload,
  answers: AnswerRecord[],
  clientMatch: (t: string) => boolean,
  competitorMatchers: ((t: string) => boolean)[],
): QueryAnalysis {
  const excluded = new Set<string>();
  for (const a of answers) {
    if (a.intent === "brand" || isUnwinnableQuery(a.prompt ?? "", clientMatch, competitorMatchers)) {
      excluded.add(a.query_id);
    }
  }
  const byQuery = new Map<string, { client: boolean; comps: Set<string> }>();
  for (const a of answers) {
    if (!a.response || excluded.has(a.query_id)) continue;
    const entry = byQuery.get(a.query_id) ?? { client: false, comps: new Set<string>() };
    if (clientMatch(a.response)) entry.client = true;
    report.competitors.forEach((c, i) => {
      if (competitorMatchers[i]!(a.response as string)) entry.comps.add(c);
    });
    byQuery.set(a.query_id, entry);
  }
  let clientAppears = 0;
  const compCount = new Map<string, number>();
  for (const v of byQuery.values()) {
    if (v.client) clientAppears++;
    for (const c of v.comps) compCount.set(c, (compCount.get(c) ?? 0) + 1);
  }
  return { excluded, clientAppears, compCount, n: byQuery.size };
}

function computeHeadline(report: ReportPayload, analysis: QueryAnalysis): AuditHeadlineNumber {
  const { clientAppears, compCount, n } = analysis;
  // Honest-hero (R3): name the rival that OUT-APPEARS the client the most (not
  // the scorecard's top-share brand, which can be one the client actually beats
  // on these queries). If NO competitor out-appears the client, drop the name so
  // the headline softens to a client-only statement instead of asserting a loss
  // its own numbers contradict. Iterate in report order for a deterministic pick.
  let competitorName = "";
  let competitorAppears = 0;
  for (const c of report.competitors) {
    const appears = compCount.get(c) ?? 0;
    if (appears > competitorAppears) {
      competitorAppears = appears;
      competitorName = c;
    }
  }
  if (competitorAppears <= clientAppears) {
    competitorName = "";
    competitorAppears = 0;
  }
  return { clientAppears, competitorAppears, competitorName, n };
}

// --- §3 evidence ----------------------------------------------------------------

function toFinding(
  row: LosingRow,
  answers: AnswerRecord[],
  clientMatch: (t: string) => boolean,
  competitorMatch: (t: string) => boolean,
): Finding | null {
  // Prefer a run that REPRODUCES the loss (client absent, competitor present) so
  // the quoted proof actually backs the claim (T4, parity with the teaser) — not
  // run_index 0 blindly, which could quote a run where the loss didn't hold.
  const prefer = (resp: string) => !clientMatch(resp) && competitorMatch(resp);
  const answer = findAnswer(answers, row.query_id, row.engine_name, prefer);
  if (!answer || !answer.response) return null;
  const repro = countReproduction(answers, row.query_id, row.engine_name, clientMatch, competitorMatch);
  return {
    role: "lead",
    source: "losing_query",
    queryId: row.query_id,
    intent: row.intent,
    engineName: row.engine_name,
    competitor: row.competitor,
    prominence: row.prominence ?? null,
    verbatimQuery: answer.prompt,
    verbatimAnswer: answer.response,
    citations: answer.citations,
    rankScore: scoreRow(row),
    runsObserved: repro.observed,
    runsConfirming: repro.confirming,
  };
}

function buildEvidence(
  report: ReportPayload,
  answers: AnswerRecord[],
  perBucket: number,
  analysis: QueryAnalysis,
  clientMatch: (t: string) => boolean,
  competitorMatcherFor: (name: string) => (t: string) => boolean,
): EvidenceGroup[] {
  const named = report.losing_queries.filter((r) => r.competitor.trim() !== "");
  const groups: EvidenceGroup[] = [];
  for (const bucket of EVIDENCE_BUCKET_ORDER) {
    const rows = named
      .filter((r) => r.intent === bucket)
      // Exclude brand / A-vs-B rows (T1), and require the competitor to OUT-APPEAR
      // the client (honest-hero parity with selectFindings' heroPool) — an evidence
      // card must not name a rival the client actually beats on these queries.
      .filter((r) => !analysis.excluded.has(r.query_id))
      .filter((r) => (analysis.compCount.get(r.competitor) ?? 0) > analysis.clientAppears)
      .sort(
        (a, b) =>
          scoreRow(b) - scoreRow(a) ||
          a.query_id.localeCompare(b.query_id) ||
          a.engine_name.localeCompare(b.engine_name),
      );
    const findings: Finding[] = [];
    const seenQueries = new Set<string>();
    for (const row of rows) {
      if (findings.length >= perBucket) break;
      if (seenQueries.has(row.query_id)) continue; // one card per query within a bucket
      const competitorMatch = competitorMatcherFor(row.competitor);
      const f = toFinding(row, answers, clientMatch, competitorMatch);
      if (!f) continue;
      // Proof-foregrounding gate (R6, parity with the teaser): the card renders
      // only the LEADING prose (answerSnippet) and labels it "<competitor>
      // recommended instead" — so the competitor must actually appear in that
      // shown snippet, or the card contradicts its own callout.
      if (!competitorMatch(answerSnippet(f.verbatimAnswer))) continue;
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
        (a, b) =>
          (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0) ||
          a.check_key.localeCompare(b.check_key),
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
            (IMPACT_RANK[(a.impact_label ?? "").toLowerCase()] ?? 0) ||
          a.check_name.localeCompare(b.check_name),
      ),
    }));
}

// --- §1 copy (deterministic templating; analyst-editable) -----------------------

function verdictLine(report: ReportPayload, h: AuditHeadlineNumber): string {
  // Percentages are derived from the SAME winnable-query counts as the §1
  // headline (h.clientAppears/h.competitorAppears over h.n), NOT the scorecard's
  // all-query mention_rate. This fixes two bugs at once: (R1) "named" not
  // "recommended" over a mention-rate number, and (T2) the old compPct came from
  // mention_rate_top_competitor — the SHARE-based top brand — while h.competitorName
  // is the COUNT-based honest-hero pick, so in a multi-competitor report the
  // verdict attributed one brand's % to a different named brand. One basis =
  // brand and % always agree, and the verdict matches the "X of N" headline (T6).
  const clientPct = h.n > 0 ? pctOf(h.clientAppears / h.n) : 0;
  if (h.competitorName) {
    const compPct = h.n > 0 ? pctOf(h.competitorAppears / h.n) : 0;
    return (
      `${report.client_name} is named in ${clientPct}% of the buyer queries we measured; ` +
      `${h.competitorName} in ${compPct}%. The gap is the visibility you're losing at the moment buyers decide.`
    );
  }
  return `${report.client_name} is named in ${clientPct}% of the buyer queries we measured.`;
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

  // Alias-aware matchers, built once (R4/T7). The from-run_id audit path has no
  // alias source, so these default to name-only; a caller that has a resolved
  // profile can pass clientAliases/competitorAliases and the matchers use them.
  const competitorAliases = opts.competitorAliases ?? {};
  const clientMatch = buildMatcher(report.client_name, opts.clientAliases ?? []);
  const competitorMatcherFor = (name: string) => buildMatcher(name, competitorAliases[name] ?? []);
  const competitorMatchers = report.competitors.map(competitorMatcherFor);
  const analysis = analyzeQueries(report, answers, clientMatch, competitorMatchers);

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

  const headlineNumber = computeHeadline(report, analysis);

  const accuracyFlags = [...report.accuracy_flags].sort(
    (a, b) =>
      (SEVERITY_RANK[b.severity] ?? 0) - (SEVERITY_RANK[a.severity] ?? 0) ||
      a.claim.localeCompare(b.claim),
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

    evidence: buildEvidence(report, answers, perBucket, analysis, clientMatch, competitorMatcherFor),

    accuracy: {
      assessed: report.scorecard.accuracy_assessed,
      flags: report.scorecard.accuracy_assessed ? accuracyFlags : [],
      penalty: grade?.accuracyPenalty ?? 0,
    },

    competitiveGap: {
      offsite: site?.offsite ?? [],
      citedSources: [...report.sources]
        .sort((a, b) => b.count - a.count || a.domain.localeCompare(b.domain))
        .slice(0, 8),
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
