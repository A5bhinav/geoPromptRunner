/**
 * Types mirroring the geoPromptRunner platform's public surface.
 *
 * These are copied field-for-field from the platform so that MockPlatformClient
 * and the real HTTP client are drop-in interchangeable. Sources:
 *   - ReportPayload + sub-rows: src/api/reports.py
 *   - QueryResult (answers):     src/storage/models.py
 *   - AccuracyFlag types/sev:    src/storage/models.py
 *
 * If the platform changes its schema, change it HERE and both clients follow.
 */

/** Funnel-stage intent buckets (src/prompts/intent.py). */
export type IntentBucket =
  | "problem_aware"
  | "category"
  | "comparison"
  | "brand"
  | "adjacent_authority";

/** How a brand appears in one answer (judge layer). */
export type Prominence =
  | "recommended_first"
  | "mid_pack"
  | "buried"
  | "also_ran"
  | "absent";

export type AccuracyFlagType =
  | "wrong_pricing"
  | "missing_or_invented_feature"
  | "competitor_confusion"
  | "identity"
  | "stale";

export type Severity = "high" | "med" | "low";

/** Which detection path produced the report. "regex" lacks grade/accuracy. */
export type DetectionMode = "judge" | "regex";

// --- ReportPayload sub-rows (src/api/reports.py) -----------------------------

export interface GradePayload {
  letter: string;
  score: number;
  raw_score: number;
  accuracy_penalty: number;
  n_flags: number;
  rationale: string;
}

export interface LeaderRow {
  brand: string;
  is_client: boolean;
  visibility: number | null; // null in regex mode (needs the judge)
  mention_rate: number;
  share_of_model: number;
}

export interface BucketRow {
  bucket: string;
  mention_rate: number;
  citation_rate: number | null;
}

export interface FlagRow {
  type: AccuracyFlagType;
  severity: Severity;
  claim: string;
  reality: string;
}

export interface SourceRow {
  domain: string;
  count: number;
}

/** A (query, engine) cell where the client is absent but a competitor is present. */
export interface LosingRow {
  query_id: string;
  intent: IntentBucket;
  engine_name: string;
  competitor: string;
}

export interface ScorecardPayload {
  visibility_grade: GradePayload | null;
  share_of_model_client: number;
  top_competitor: string | null;
  top_competitor_share: number | null;
  mention_rate_client: number;
  mention_rate_top_competitor: number | null;
  citation_rate_client: number | null;
  accuracy_assessed: boolean;
  accuracy_flag_count: number | null;
}

/** The full report — teaserAuto's primary input. */
export interface ReportPayload {
  client_name: string;
  run_date: string;
  query_set_version: string;
  runs_per_query: number;
  engines: string[];
  competitors: string[];
  client_domains: string[];
  detection: DetectionMode;
  scorecard: ScorecardPayload;
  leaderboard: LeaderRow[];
  by_bucket: BucketRow[];
  accuracy_flags: FlagRow[];
  sources: SourceRow[];
  losing_queries: LosingRow[];
}

// --- Raw answers (for the proof card) ----------------------------------------

/**
 * One engine's verbatim answer to one query on one run (platform QueryResult).
 * `prompt` is the query text; `response` is the verbatim engine answer that the
 * proof card re-renders. The platform exposes these via /answers.md|/results.csv;
 * we model them structurally so the proof renderer doesn't parse markdown.
 */
export interface AnswerRecord {
  query_id: string;
  intent: IntentBucket;
  prompt: string;
  engine_name: string;
  run_index: number;
  response: string | null;
  citations: string[];
  timestamp: string;
}

// --- Run status (poll) -------------------------------------------------------

export type RunState = "queued" | "running" | "done" | "failed" | "cancelled";

export interface RunStatus {
  run_id: string;
  client_name: string;
  state: RunState;
  completed: number;
  total: number;
  error: string | null;
}
