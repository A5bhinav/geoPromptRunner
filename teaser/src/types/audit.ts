/**
 * Audit Generator domain types — the assembled, reviewable AI Visibility Audit
 * (the paid deliverable). Analogue of TeaserDraft (types/domain.ts), but
 * multi-section. See docs/auditGenerator.md §6.
 *
 * Everything here is assembled (not measured) from a completed run's
 * ReportPayload + AnswerRecord[]; the generator never re-runs engines.
 */

import type { Finding } from "./domain.ts";
import type {
  AnswerRecord,
  BucketRow,
  FlagRow,
  IntentBucket,
  LeaderRow,
  ReportPayload,
  RoadmapRow,
  SiteCheckRow,
  SiteFindingRow,
  SourceRow,
} from "./platform.ts";

/** §1 — the A–F grade (from scorecard.visibility_grade). */
export interface AuditGrade {
  letter: string;
  score: number;
  rationale: string;
  accuracyPenalty: number;
  nFlags: number;
}

/** The "appears in X of N answers" gap that leads the cover (§1) and §2. */
export interface AuditHeadlineNumber {
  clientAppears: number;
  competitorAppears: number;
  competitorName: string;
  n: number;
}

/** §3 — verbatim losing answers grouped by buyer-journey stage. */
export interface EvidenceGroup {
  bucket: IntentBucket;
  findings: Finding[];
}

/** §6 — one of the 7 rubric categories, rolled up to a single verdict. */
export interface DiagnosisCategory {
  category: number; // 1..7
  verdict: "pass" | "partial" | "fail";
  checks: SiteCheckRow[]; // failing/partial first, then passes
}

/** §7 — roadmap rows grouped by fix phase (1 Accessibility → 4 Off-site). */
export interface RoadmapPhase {
  phase: number; // 1..4
  rows: RoadmapRow[];
}

/**
 * Analyst copy overrides (the human-in-the-loop edit overlay). Each field, when
 * present, replaces the generated copy at render time — how review-UI edits reach
 * the downloaded PDF. Mirrors the `edited_fields` column. Analogue of TeaserEdits.
 */
export interface AuditEdits {
  headline?: string;
  verdictSentence?: string;
  achievableGrade?: string;
  projectedImpact?: string;
  nextSteps?: string;
}

/** A fully-assembled draft AI Visibility Audit, ready for review/render. */
export interface AuditDraft {
  runId: string;
  clientName: string;
  clientDomains: string[];
  category: string;
  runDate: string;
  engines: string[];

  // §1 — Verdict (gap-led cover; grade as trajectory). See doc §15.7.
  grade: AuditGrade | null;
  achievableGrade: string | null; // analyst target ("A- (90d)"); never a fabricated score
  headline: string; // gap-led hero line — analyst-editable
  verdictSentence: string; // one-line verdict — analyst-editable
  headlineNumber: AuditHeadlineNumber;

  // §2 — Where you stand (baseline)
  leaderboard: LeaderRow[];
  byBucket: BucketRow[];
  shareOfVoiceClient: number;
  topCompetitor: string | null;
  topCompetitorShare: number | null;

  // §3 — Evidence (grouped by journey stage)
  evidence: EvidenceGroup[];

  // §4 — What AI gets wrong (accuracy)
  accuracy: { assessed: boolean; flags: FlagRow[]; penalty: number };

  // §5 — Who's winning & why (competitive gap)
  competitiveGap: { offsite: SiteFindingRow[]; citedSources: SourceRow[] };

  // §6 — Why AI skips you (diagnosis)
  diagnosis: {
    present: boolean;
    categories: DiagnosisCategory[];
    pagesCrawled: number;
    errors: number;
  };

  // §7 — The roadmap
  roadmap: { present: boolean; phases: RoadmapPhase[] };

  // §8 — Projected impact + engagement (analyst-authored scaffolding)
  engagement: { projectedImpact: string; nextSteps: string };

  // review lifecycle (mirrors TeaserDraft.status)
  status: "draft" | "approved" | "rejected" | "exported";

  // reproducibility — cached so the audit re-renders as engines drift
  report: ReportPayload;
  answers: AnswerRecord[];
}
