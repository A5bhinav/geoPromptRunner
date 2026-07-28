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
/**
 * Must stay in lockstep with `IntentBucket` in `src/prompts/intent.py` — these
 * strings cross the CSV boundary and the platform validates them against that enum,
 * so a value here that the platform doesn't know fails the upload.
 *
 * Two families, selected by business kind (pivot §0.6). `brand` is shared: "is X
 * legit" is the same question whether X is an app or a plumber.
 */
export type IntentBucket =
  // consumer-product funnel
  | "problem_aware"
  | "category"
  | "comparison"
  | "adjacent_authority"
  // local-service intents
  | "local_intent"
  | "hybrid"
  | "informational"
  // shared
  | "brand";

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
  /**
   * Cells in this bucket that returned an answer, out of cells attempted. When
   * answered_cells is 0 the rates above carry no information — render "—", never
   * "0%". A brand cannot be absent from an answer that never existed.
   */
  answered_cells: number;
  total_cells: number;
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
  /**
   * Judge prominence of the competitor in this cell. The platform's judge path
   * only emits recommended_first cells today, but the copy layer must not
   * assume that — it grades its verb ("recommends" vs "mentions") off this.
   * Optional: rows persisted before this field existed (and regex-path rows,
   * which the teaser refuses anyway) don't carry it.
   */
  prominence?: Prominence | null;
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
/** One on-site/off-site check verdict (src/api/reports.py SiteCheckRow). */
export interface SiteCheckRow {
  check_key: string;
  category: number;
  page_url: string;
  status: string; // pass | partial | fail | ungradeable
  detail: string;
}

/** One off-site finding (Wikidata/reviews/community/listicle/press). */
export interface SiteFindingRow {
  finding_type: string;
  title: string;
  url: string | null;
  confidence: string; // high | medium | low
}

/** One prioritized roadmap gap — the "why + fix" behind the visibility loss. */
export interface RoadmapRow {
  category: string;
  check_name: string;
  status: string; // partial | fail
  impact_label: string; // High | Medium | Low
  effort: string; // low | medium | high
  phase: number; // 1..4
}

/** Site-audit results (technique-checklist scrape) attached to the report. */
export interface SiteAuditPayload {
  present: boolean;
  domain: string;
  pages_crawled: number;
  checks: SiteCheckRow[];
  summary: Record<string, number>;
  errors: number;
  offsite: SiteFindingRow[];
  roadmap: RoadmapRow[];
}

export interface LocalPackRow {
  query_id: string;
  prompt: string;
  position: number | null;
  name: string;
  is_client: boolean;
  address: string | null;
  rating: number | null;
  reviews: number | null;
  phone: string | null;
  website: string | null;
}

/**
 * Google's local pack for the run's local-intent queries — the surface that actually
 * answers them (~93% of local-intent SERPs, vs ~15% showing an AI Overview).
 *
 * Deliberately NOT part of mention_rate / share_of_model / the visibility grade: a
 * ranked business list is not an AI answer. `client_positions` maps query_id to the
 * client's rank in that pack, or null when the client is absent from it — which is a
 * finding, not missing data.
 */
export interface LocalPackPayload {
  present: boolean;
  location: string;
  sources: string[];
  queries_captured: number;
  entities: LocalPackRow[];
  client_positions: Record<string, number | null>;
}

export interface ReportPayload {
  client_name: string;
  run_date: string;
  query_set_version: string;
  runs_per_query: number;
  /** Engines that returned at least one answer — i.e. that actually measured this
   * client. Built from answer existence, not row existence, so a surface whose model
   * 404'd is not listed here as having measured anything. */
  engines: string[];
  /** Engines that ran and returned nothing at all. Surfaced rather than dropped: a
   * failed surface is a fact about the run's coverage. Optional so a report rendered
   * from an older stored run still parses. */
  dead_engines?: string[];
  competitors: string[];
  client_domains: string[];
  detection: DetectionMode;
  scorecard: ScorecardPayload;
  leaderboard: LeaderRow[];
  by_bucket: BucketRow[];
  accuracy_flags: FlagRow[];
  sources: SourceRow[];
  losing_queries: LosingRow[];
  /** On-site + off-site technique-checklist audit; null when the crawl didn't run. */
  site_audit?: SiteAuditPayload | null;
  /** Google local pack for local-intent queries; null on a consumer run, or on a local
   * run with no pinned location. Optional so older stored reports still parse. */
  local_pack?: LocalPackPayload | null;
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
